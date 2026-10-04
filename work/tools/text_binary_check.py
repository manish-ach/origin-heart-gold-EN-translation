#!/usr/bin/env python3
"""Independent, bounded message-container grammar checks (no msgtool dependency).

Passing proves structural grammar only: character mappings, command semantics,
consumer capacities and opaque source equality require separate comparisons.
No bytes are written and no ROM/parser repair is attempted.
"""
from __future__ import annotations

import struct


def _result(**fields):
    return dict(status="passed", errors=[], gaps=[], **fields)


def _error(result, code, **location):
    result["errors"].append(dict(code=code, **location))
    result["status"] = "failed"


def inspect_narc(data: bytes) -> dict:
    """Validate section/FAT bounds before returning bounded member byte copies."""
    out = _result(members=[])
    if len(data) < 16:
        _error(out, "truncated_header")
        return out
    magic, bom, version, total, header, sections = struct.unpack_from("<4sHHIHH", data)
    if (magic, bom, version, header, sections) != (b"NARC", 0xFFFE, 0x100, 16, 3):
        _error(out, "unsupported_header")
        return out
    if total != len(data):
        _error(out, "container_size", declared=total, actual=len(data))
    pos = header
    found = {}
    for expected in (b"BTAF", b"BTNF", b"GMIF"):
        if pos + 8 > len(data):
            _error(out, "truncated_section", offset=pos)
            return out
        tag, size = struct.unpack_from("<4sI", data, pos)
        if tag != expected or size < 8 or size > len(data) - pos:
            _error(out, "invalid_section", offset=pos, expected=expected.decode(), size=size)
            return out
        found[tag] = (pos + 8, pos + size)
        pos += size
    if pos != len(data):
        _error(out, "trailing_container_bytes", offset=pos)
    fat, end = found[b"BTAF"]
    if end - fat < 4:
        _error(out, "truncated_fat")
        return out
    count, reserved = struct.unpack_from("<HH", data, fat)
    if reserved or end - fat != 4 + count * 8:
        _error(out, "fat_inventory_size", count=count)
        return out
    base, image_end = found[b"GMIF"]
    previous = 0
    for index in range(count):
        start, stop = struct.unpack_from("<II", data, fat + 4 + index * 8)
        if start < previous or stop < start or stop > image_end - base:
            _error(out, "member_bounds_or_overlap", member=index, start=start, stop=stop)
            continue
        previous = stop
        out["members"].append(dict(id=index, offset=base + start, size=stop-start,
                                   data=bytes(data[base+start:base+stop])))
    return out


def _record(units, record, out):
    index = record["id"]
    record.update(compressed=False, commands=[], padding=0)
    if not units:
        _error(out, "empty_record", record=index)
        return
    if units[0] == 0xF100:
        record["compressed"] = True
        # 9-bit symbols span 15-bit storage words. Accumulating the bitstream
        # independently avoids reproducing the production codec's cursor logic.
        accumulator = bits = decoded = 0
        terminated = False
        for cursor, word in enumerate(units[1:], 1):
            if word & 0x8000 and word != 0xFFFF:
                _error(out, "compressed_high_bit", record=index, unit=cursor)
                return
            accumulator |= (word & 0x7FFF) << bits
            bits += 15
            while bits >= 9:
                symbol = accumulator & 0x1FF
                accumulator >>= 9
                bits -= 9
                if symbol == 0x1FF:
                    terminated = True
                    break
                decoded += 1
            if terminated:
                if accumulator != (1 << bits)-1 or any(v != 0xFFFF for v in units[cursor+1:]):
                    _error(out, "compressed_trailing_payload", record=index, unit=cursor)
                if units[-1] != 0xFFFF:
                    _error(out, "missing_storage_terminator", record=index)
                record["decoded_units"] = decoded
                record["padding"] = len(units)-cursor-1
                return
        _error(out, "unterminated_compression", record=index)
        return
    cursor = 0
    while cursor < len(units):
        code = units[cursor]
        if code == 0xFFFF:
            if any(v != 0xFFFF for v in units[cursor+1:]):
                _error(out, "trailing_message_payload", record=index, unit=cursor)
            record["padding"] = len(units)-cursor-1
            record["decoded_units"] = cursor
            return
        if code == 0xF100:
            _error(out, "misplaced_compression_header", record=index, unit=cursor)
            return
        if code == 0xFFFE:
            if cursor + 3 > len(units):
                _error(out, "truncated_command_header", record=index, unit=cursor)
                return
            command, argc = units[cursor+1:cursor+3]
            if argc > len(units) - cursor - 3:
                _error(out, "command_arguments_overrun", record=index, unit=cursor, argc=argc)
                return
            record["commands"].append(dict(unit=cursor, command=command,
                                           args=units[cursor+3:cursor+3+argc]))
            cursor += 3 + argc
        else:
            cursor += 1
    _error(out, "missing_terminator", record=index)


def inspect_bank(data: bytes) -> dict:
    """Strictly check encrypted inventory, sequential records and bounded grammar.

    Noncanonical trailers are gaps, never a semantic pass. A caller can classify
    byte-identical opaque original data separately, preserving this raw result.
    """
    out = _result(count=None, records=[])
    if len(data) < 4:
        _error(out, "truncated_bank_header")
        return out
    count, seed = struct.unpack_from("<HH", data)
    out["count"] = count
    table_end = 4 + count * 8
    if table_end > len(data):
        _error(out, "truncated_message_inventory", count=count)
        return out
    previous = table_end
    for index in range(count):
        key16 = (seed * 765 * (index+1)) % 65536
        key32 = key16 * 65537
        encoded_offset, encoded_length = struct.unpack_from("<II", data, 4 + index*8)
        offset, length = encoded_offset ^ key32, encoded_length ^ key32
        if offset != previous or offset % 2 or offset < table_end or offset > len(data) or length > (len(data)-offset)//2:
            _error(out, "record_bounds_or_layout", record=index, offset=offset, stored_units=length)
            return out
        record = dict(id=index, offset=offset, stored_units=length)
        out["records"].append(record)
        units = [value[0] ^ ((596947*(index+1) + unit*18749) % 65536)
                 for unit, value in enumerate(struct.iter_unpack("<H", data[offset:offset+length*2]))]
        _record(units, record, out)
        previous = offset + length*2
    out["trailer_bytes"] = len(data)-previous
    if previous != len(data):
        out["gaps"].append(dict(code="uninterpreted_bank_trailer", offset=previous, size=len(data)-previous))
        if not out["errors"]:
            out["status"] = "incomplete"
    return out
