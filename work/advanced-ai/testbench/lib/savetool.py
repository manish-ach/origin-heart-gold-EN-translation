"""Edit HeartGold battery saves (.dsv) for the runtime tests.

Ported from the Spanish workspace's tools/savetool.py (dc8577c); its `make` lives in lib/saves.py (derive). Changes:
place() takes the camera type as an argument (or reads it from a ROM), a Save can be made from bytes and give its bytes
back, and image()/dsv() convert between a raw 512 KiB battery image (melonDS, flashcarts) and DeSmuME's .dsv (the image
and DeSmuME's 122-byte footer).

Offsets are in the general save block (size 0xF7CC, two slots at 0 and 0x40000; the newer slot by
the footer counter is edited and its CRC is fixed). Party Pokémon use the Gen 4 format: blocks A-D
shuffled by the PID and encrypted with a PRNG seeded by their checksum, party data encrypted with
the PID. Moving the player to another map: the current location record and the saved player
object are set and every other saved object is switched off, so the map starts empty; entering a
door from there loads the next map with its own NPCs.
"""
import struct

from text import text_to_codes

GENERAL_SIZE, SLOT_B, FOOTER = 0xF7CC, 0x40000, 0xF7BC
OPTIONS, NAME, MONEY = 0x60, 0x64, 0x78
BADGES = (0x80, 0x83)              # Johto and Kanto badges, one bit each (CountBadges 0x02029480)
PARTY = 0x98                      # first party Pokémon (count at 0x94), 236 bytes each
POCKETS = {'items': (0x644, 165), 'key': (0x8D8, 50), 'tms': (0x9A0, 151), 'mail': (0xBFC, 12),
           'medicine': (0xC2C, 40), 'berries': (0xCCC, 64), 'balls': (0xDCC, 24), 'battle': (0xE2C, 30)}
FLAGS = 0x118C                    # script flags, one bit each
VARS = FLAGS - 0x2E0              # script vars 0x4000-0x416F, u16 each, just before the flags
DEX = 0x13A8                      # Pokédex (save array 6): magic 0xBEEFCAFE, caught bits at +4, seen bits at +0xCC
POKEGEAR_CARDS = 0xBC88           # Pokégear (save array 0x22 at 0xBC84) +4: bit 25 Map Card, bit 26 Radio Card
LOCATION = 0x1324                 # current position: map, warp, x, y, facing (s32 each)
CAMERA = LOCATION + 0x6A          # the map's camera type, a byte: every warp copies it from the map header, and every
                                  # connection crossing asserts it equals the new map's (arm9 0x020522BE)
MAP_HEADERS = 0x020F37C4          # arm9: 24 bytes per map, +0x14 bits 12-17 the camera type
OBJECTS, OBJECT_SIZE = 0x2480, 0x50   # saved map objects; the player is the first; flags bit 0 = active
FACING = {'up': 0, 'down': 1, 'left': 2, 'right': 3}
IMAGE_SIZE = 0x80000              # the battery image: 4 Mbit flash
SAVE_MAGIC = 0x20060623           # a slot footer's magic
# DeSmuME's .dsv footer after the image: a text marker, its backup info (u32 size, padding size, type, address size,
# memory size, 0) and an end marker; every .dsv of the test bench carries this one (4 Mbit flash, 3-byte addresses)
DSV_FOOTER = (b'|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:'
              + struct.pack('<6I', IMAGE_SIZE, IMAGE_SIZE, 6, 3, IMAGE_SIZE, 0) + b'|-DESMUME SAVE-|')
BLOCK_ORDERS = ['ABCD', 'ABDC', 'ACBD', 'ACDB', 'ADBC', 'ADCB', 'BACD', 'BADC', 'BCAD', 'BCDA', 'BDAC', 'BDCA',
                'CABD', 'CADB', 'CBAD', 'CBDA', 'CDAB', 'CDBA', 'DABC', 'DACB', 'DBAC', 'DBCA', 'DCAB', 'DCBA']


def crc16_ccitt(data):
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def _crypt(buf, seed):
    out = bytearray(buf)
    for k in range(0, len(buf), 2):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        struct.pack_into('<H', out, k, struct.unpack_from('<H', buf, k)[0] ^ (seed >> 16))
    return out


class Mon:
    """One party Pokémon, decrypted: blocks['A'..'D'] (32 bytes each) and party data."""

    def __init__(self, raw):
        self.pid, _, self.checksum = struct.unpack_from('<IHH', raw, 0)
        self.head = bytes(raw[:8])
        plain = _crypt(raw[8:0x88], self.checksum)
        order = BLOCK_ORDERS[(self.pid >> 13 & 31) % 24]
        self.blocks = {order[k]: bytearray(plain[32 * k:32 * k + 32]) for k in range(4)}
        self.party = _crypt(raw[0x88:0xEC], self.pid)

    def encode(self):
        order = BLOCK_ORDERS[(self.pid >> 13 & 31) % 24]
        plain = b''.join(bytes(self.blocks[c]) for c in order)
        checksum = sum(struct.unpack('<64H', plain)) & 0xFFFF
        head = bytearray(self.head)
        struct.pack_into('<H', head, 6, checksum)
        return bytes(head) + bytes(_crypt(plain, checksum)) + bytes(_crypt(self.party, self.pid))

    def set_species(self, species, name):
        struct.pack_into('<H', self.blocks['A'], 0, species)
        codes = text_to_codes(name)[:10] + [0xFFFF]
        nick = struct.pack('<%dH' % len(codes), *codes)
        self.blocks['C'][0:22] = nick + b'\xff\xff' * ((22 - len(nick)) // 2)

    def set_level(self, level, exp):
        struct.pack_into('<I', self.blocks['A'], 8, exp)
        self.party[4] = level

    def set_stats(self, hp, atk, dfn, spe, spa, spd):
        struct.pack_into('<7H', self.party, 6, hp, hp, atk, dfn, spe, spa, spd)

    def set_status(self, status):
        struct.pack_into('<I', self.party, 0, status)

    def set_hp(self, hp):
        struct.pack_into('<H', self.party, 6, hp)

    def set_hatched(self, egg_location, date=(26, 9, 1)):
        """Hatched from an Egg received on `date` at `egg_location` (met level 0)."""
        self.blocks['D'][0x10:0x13] = bytes(date)
        struct.pack_into('<H', self.blocks['B'], 0x1C, egg_location)
        self.blocks['D'][0x1C] &= 0x80


def image(data):
    """The raw 512 KiB battery image of a raw save (.sav, exactly the image) or a DeSmuME .dsv (the image and a
    footer that ends with DeSmuME's end marker); ValueError for anything else."""
    data = bytes(data)
    if len(data) == IMAGE_SIZE:
        return data
    if len(data) > IMAGE_SIZE and data.endswith(b'|-DESMUME SAVE-|'):
        return data[:IMAGE_SIZE]
    raise ValueError('not a 512 KiB battery save: %d bytes (a raw .sav is exactly %d bytes; a DeSmuME .dsv ends with '
                     'its footer)' % (len(data), IMAGE_SIZE))


def dsv(img):
    """A DeSmuME .dsv of a raw image: the image and DSV_FOOTER."""
    return image(img) + DSV_FOOTER


class Save:
    def __init__(self, path=None, data=None):
        self.data = bytearray(open(path, 'rb').read() if data is None else data)
        counts = []
        for base in (0, SLOT_B):
            cnt, _, magic = struct.unpack_from('<III', self.data, base + FOOTER)
            counts.append(cnt if magic == SAVE_MAGIC else -1)
        if max(counts) < 0:
            raise ValueError('no HeartGold save slot (footer magic %08X) in either half of the image' % SAVE_MAGIC)
        self.base = SLOT_B if counts[1] > counts[0] else 0

    def u(self, fmt, off):
        return struct.unpack_from(fmt, self.data, self.base + off)

    def put(self, fmt, off, *values):
        struct.pack_into(fmt, self.data, self.base + off, *values)

    def mon(self, slot):
        off = self.base + PARTY + 236 * slot
        return Mon(self.data[off:off + 236])

    def set_mon(self, slot, mon):
        off = self.base + PARTY + 236 * slot
        self.data[off:off + 236] = mon.encode()

    def add_item(self, pocket, item, qty):
        off, n = POCKETS[pocket]
        for k in range(n):
            i, q = self.u('<HH', off + 4 * k)
            if i in (0, item):
                self.put('<HH', off + 4 * k, item, qty)
                return
        raise ValueError('pocket %s is full' % pocket)

    def set_options(self, battle_scene_off=None, battle_style_set=None, text_speed=None):
        """Options word: bits 0-3 text speed (0 slow, 1 mid, 2 fast), bit 6 battle style Set, bit 7 battle scene off."""
        v = self.u('<H', OPTIONS)[0]
        if text_speed is not None:
            v = v & ~0xF | text_speed
        if battle_scene_off is not None:
            v = v | 1 << 7 if battle_scene_off else v & ~(1 << 7)
        if battle_style_set is not None:
            v = v | 1 << 6 if battle_style_set else v & ~(1 << 6)
        self.put('<H', OPTIONS, v)

    def set_badges(self, count):
        """The first `count` badges (Johto first, then Kanto)."""
        bits = (1 << count) - 1
        self.put('<B', BADGES[0], bits & 0xFF)
        self.put('<B', BADGES[1], bits >> 8)

    def set_flag(self, flag, on=True):
        byte = FLAGS + flag // 8
        v = self.u('<B', byte)[0]
        self.put('<B', byte, v | 1 << flag % 8 if on else v & ~(1 << flag % 8))

    def place(self, map_id, x, y, facing, rom=None, camera=None):
        """Put the player on (map_id, x, y) with a camera type (`camera`, else that map's from `rom`'s arm9; neither:
        the camera byte stays), and switch off every other saved map object."""
        self.put('<5i', LOCATION, map_id, -1, x, y, FACING[facing])
        if camera is None and rom is not None:
            camera = map_camera(map_id, rom)
        if camera is not None:
            self.put('<B', CAMERA, camera)
        self.put('<6h', OBJECTS + 0x20, x, 0, y, x, 0, y)
        for n in range(1, 64):
            off = OBJECTS + OBJECT_SIZE * n
            flags = self.u('<I', off)[0]
            if flags & 1:
                self.put('<I', off, flags & ~1)

    def to_bytes(self):
        """The save with its edited slot's CRC fixed."""
        crc = crc16_ccitt(self.data[self.base:self.base + FOOTER])
        self.put('<H', FOOTER + 0xE, crc)
        return bytes(self.data)

    def write(self, path):
        data = self.to_bytes()
        with open(path, 'wb') as f:
            f.write(data)


def map_camera(map_id, rom):
    """The map header's camera type, from the ROM's arm9 (an uncompressed arm9: the Origin builds')."""
    with open(rom, 'rb') as f:
        arm9_at, _, arm9_ram = struct.unpack_from('<3I', f.read(0x2C), 0x20)
        f.seek(arm9_at + MAP_HEADERS - arm9_ram + 24 * map_id + 0x14)
        return struct.unpack('<I', f.read(4))[0] >> 12 & 0x3F


def gen4_slow_exp(level):
    return 5 * level ** 3 // 4
