"""Pickup table in the CN v4.0.3 ROM and the English builds (overlay 14).

See work/notes/chinese_source_rom_verify_common.md, COM-05. Weights are
conditional on the separate 10% activation gate, not per-battle chances.
The fix honey-gather (work/patches/honey-gather) rewrites the post-battle
collector in place: the gate moves from 0x0222BD2A to 0x0222BD38, the item
and weight tables stay where they are.
"""
import struct

ITEMS_ADDRESS = 0x0224E3AC
WEIGHTS_ADDRESS = 0x0224E3D8
GATE_ADDRESS = 0x0222BD2A          # the Chinese ROM's collector: movs r0, #10; bl chance
GATE_ADDRESSES = (GATE_ADDRESS, 0x0222BD38)   # ... and the collector as the fix honey-gather rewrites it
CHANCE_FN = 0x022264C0             # returns nonzero with the given percent chance
ITEM_COUNT = 22
BAND_COUNT = 10


def bl_target(data, base, addr):
    """Target of the Thumb BL pair at addr, or None."""
    o = addr - base
    if o < 0 or o + 4 > len(data):
        return None
    hi, lo = struct.unpack_from('<HH', data, o)
    if hi >> 11 != 0x1E or lo >> 11 != 0x1F:
        return None
    off = ((hi & 0x7FF) << 12) | ((lo & 0x7FF) << 1)
    if off & 0x400000:
        off -= 0x800000
    return addr + 4 + off


def is_gate(data, base, addr):
    """`movs r0, #10` followed by `bl chance` at addr."""
    o = addr - base
    return data[o:o + 2] == b'\x0a\x20' and bl_target(data, base, addr + 2) == CHANCE_FN


def parse_table(data, base):
    """Read the reviewed overlay layout and reject shifted or invalid tables."""
    if not any(is_gate(data, base, addr) for addr in GATE_ADDRESSES):
        raise ValueError('Pickup activation gate differs from reviewed 10% code')
    start = WEIGHTS_ADDRESS - base
    weights = data[start:start + ITEM_COUNT * BAND_COUNT]
    if len(weights) != ITEM_COUNT * BAND_COUNT:
        raise ValueError('Truncated Pickup weights')
    ids = struct.unpack_from('<22H', data, ITEMS_ADDRESS - base)
    if 0 in ids or len(set(ids)) != ITEM_COUNT:
        raise ValueError('Invalid Pickup item IDs')
    rows = [dict(item=item, rates=list(weights[i * BAND_COUNT:(i + 1) * BAND_COUNT]))
            for i, item in enumerate(ids)]
    if any(sum(row['rates'][band] for row in rows) != 100 for band in range(BAND_COUNT)):
        raise ValueError('Pickup level-band weights must total 100')
    return dict(activationPercent=10,
                bands=[dict(min=10 * band + 1, max=10 * band + 10) for band in range(BAND_COUNT)],
                items=rows)


def read_table(rom_path):
    """Read fresh bytes; overlay 14 is not in the general documentation cache."""
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
    overlay = rom.loadArm9Overlays([14])[14]
    return parse_table(overlay.data, overlay.ramAddress)
