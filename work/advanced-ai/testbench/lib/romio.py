"""ROM file access for the test bench: one file or NARC by name, and surgical file replacement (everything else stays
byte-identical).

Ported from the Spanish workspace's tools/romio.py (dc8577c) without its fixed ROM and patch paths: every tool takes
its ROM as an argument.
"""
import struct

import ndspy.narc
import ndspy.rom

TEXT_NARC = 'a/0/2/7'


def read_file(rom_path, path):
    rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
    return bytes(rom.getFileByName(path)), rom.filenames.idOf(path)


def read_narc(rom_path, path):
    data, fid = read_file(rom_path, path)
    return ndspy.narc.NARC(data), fid


def save_narc_like(orig, members):
    """Rebuild a nameless NARC with new members, keeping the original header and
    FNTB bytes and the 4-byte member alignment (ndspy writes a longer FNTB)."""
    orig = bytes(orig)
    off = struct.unpack_from('<H', orig, 12)[0]
    blocks = {}
    while off < len(orig):
        size = struct.unpack_from('<I', orig, off + 4)[0]
        blocks[orig[off:off + 4]] = orig[off:off + size]
        off += size
    fat = struct.unpack_from('<II', blocks[b'BTAF'], 12)  # first member's (start, end)
    gap = blocks[b'GMIF'][8 + fat[1]:8 + fat[1] + 1]
    pad = gap if gap else b'\xFF'
    img, table = bytearray(), bytearray()
    for m in members:
        img += pad * (-len(img) % 4)
        table += struct.pack('<II', len(img), len(img) + len(m))
        img += m
    img += pad * (-len(img) % 4)
    btaf = b'BTAF' + struct.pack('<IHH', 12 + len(table), len(members), 0) + table
    gmif = b'GMIF' + struct.pack('<I', 8 + len(img)) + img
    body = btaf + blocks[b'BTNF'] + gmif
    return orig[:8] + struct.pack('<I', 16 + len(body)) + orig[12:16] + body


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def replace_file(rom_in, rom_out, file_id, data):
    """Write `data` as file `file_id`: in place if it fits, else appended at the end."""
    rom = bytearray(open(rom_in, 'rb').read())
    fat_off = struct.unpack_from('<I', rom, 0x48)[0]
    start, end = struct.unpack_from('<II', rom, fat_off + 8 * file_id)
    if len(data) <= end - start:
        rom[start:end] = data + b'\xFF' * (end - start - len(data))
        new_start = start
    else:
        used = struct.unpack_from('<I', rom, 0x80)[0]
        new_start = (used + 0x1FF) & ~0x1FF
        rom = rom[:used] + b'\xFF' * (new_start - used) + data
        struct.pack_into('<I', rom, 0x80, len(rom))
        capacity = 128 * 1024 << rom[0x14]
        if len(rom) > capacity:
            raise ValueError('ROM would exceed cartridge capacity (%d > %d)' % (len(rom), capacity))
    struct.pack_into('<II', rom, fat_off + 8 * file_id, new_start, new_start + len(data))
    struct.pack_into('<H', rom, 0x15E, crc16(rom[:0x15E]))
    with open(rom_out, 'wb') as f:
        f.write(rom)
