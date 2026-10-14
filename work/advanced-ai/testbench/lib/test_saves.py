"""Unit tests of lib/saves.py's derivation of the test saves (no emulator, no game data: the saves are made up here).

  .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/lib -p 'test_*.py'

The last test also derives the saves from the reference party_nostatus and checks all six against the reference
SHA-256s; it runs only where that save and a ROM of the hack are in place (it skips elsewhere).
"""
import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tbpaths  # noqa: E402,F401
import saves  # noqa: E402
import savetool  # noqa: E402
from savetool import FLAGS, FOOTER, IMAGE_SIZE, LOCATION, OBJECTS, OBJECT_SIZE, PARTY, Mon, Save  # noqa: E402

CAMERA = savetool.CAMERA
STORY_FLAG = 0x200                  # a flag the derivation must leave as the base has it


def make_mon(species, level=30, max_hp=90, hp=45, status=0x08, egg=False, pid=0x1234):
    m = Mon(bytes(236))
    m.pid = pid
    m.head = struct.pack('<I', pid) + m.head[4:]
    struct.pack_into('<H', m.blocks['A'], 0, species)
    struct.pack_into('<I', m.blocks['A'], 4, 0xCAFEBABE)                 # another trainer's ID
    m.blocks['D'][0:16] = bytes.fromhex('3101320133013401ffff000000000000')   # another trainer's name
    m.blocks['D'][0x1C] = 0x80 | 20                                       # a female trainer, met at level 20
    struct.pack_into('<I', m.blocks['B'], 0x10, (1 << 30) if egg else 0)
    struct.pack_into('<I', m.party, 0, status)
    m.party[4] = level
    struct.pack_into('<HH', m.party, 6, hp, max_hp)
    return m.encode()


def make_base(mons, trainer_71_beaten=True):
    """A raw image: one valid general-block slot with a party of `mons` (raw), another player, a story flag, a map."""
    data = bytearray(IMAGE_SIZE)
    struct.pack_into('<III', data, FOOTER, 1, 0, savetool.SAVE_MAGIC)
    sv = Save(data=data)
    sv.put('<16s', savetool.NAME, bytes.fromhex('3a013b01ffff' + '00' * 10))
    sv.put('<I', saves.PROFILE_ID, 0x11112222)
    sv.put('<I', savetool.MONEY, 123456)
    sv.put('<B', saves.PROFILE_GENDER, 1)
    sv.put('<H', savetool.OPTIONS, 0x0005)
    sv.put('<I', PARTY - 4, len(mons))
    for k, raw in enumerate(mons):
        sv.data[sv.base + PARTY + 236 * k:sv.base + PARTY + 236 * (k + 1)] = raw
    sv.set_flag(STORY_FLAG)
    if trainer_71_beaten:
        sv.set_flag(saves.TRAINER_BEATEN + saves.BENCH_TRAINER)
    sv.put('<5i', LOCATION, 67, -1, 564, 392, 0)
    sv.put('<I', OBJECTS + OBJECT_SIZE, 1)                                 # an active map object
    return sv.to_bytes()


def flag(sv, f):
    return sv.u('<B', FLAGS + f // 8)[0] >> f % 8 & 1


def mons(sv):
    return [sv.mon(k) for k in range(6)]


def crc_ok(data):
    sv = Save(data=savetool.image(data))
    stored = sv.u('<H', FOOTER + 0xE)[0]
    return stored == savetool.crc16_ccitt(sv.data[sv.base:sv.base + FOOTER])


EXP100 = 1059860


class Derivation(unittest.TestCase):
    def setUp(self):
        self.base = make_base([make_mon(157, pid=1), make_mon(25, pid=2), make_mon(1, egg=True, pid=3)])
        self.asked = []
        self.out = saves.derive(self.base, lambda sp: self.asked.append(sp) or EXP100)

    def test_party_nostatus_is_the_normalised_base(self):
        sv = Save(data=savetool.image(self.out['party_nostatus']))
        self.assertEqual(bytes(sv.data[sv.base + savetool.NAME:sv.base + savetool.NAME + 16]), saves.PLAYER_NAME)
        self.assertEqual(sv.u('<I', saves.PROFILE_ID)[0], saves.PLAYER_ID)
        self.assertEqual(sv.u('<I', savetool.MONEY)[0], saves.PLAYER_MONEY)
        self.assertEqual(sv.u('<B', saves.PROFILE_GENDER)[0], saves.PLAYER_GENDER)
        self.assertEqual(sv.u('<H', savetool.OPTIONS)[0], saves.PLAYER_OPTIONS)
        self.assertEqual(sv.u('<I', PARTY - 4)[0], 6)
        party = mons(sv)
        # the Egg is dropped and the two other Pokémon repeat in order to fill six
        self.assertEqual([struct.unpack_from('<H', m.blocks['A'], 0)[0] for m in party], [157, 25] * 3)
        for m in party:
            self.assertEqual(struct.unpack_from('<I', m.blocks['A'], 4)[0], saves.PLAYER_ID)
            self.assertEqual(bytes(m.blocks['D'][0:16]), saves.PLAYER_NAME)
            self.assertEqual(m.blocks['D'][0x1C], 20)                    # male trainer bit, the met level kept
            self.assertEqual((struct.unpack_from('<I', m.party, 0)[0], m.party[4]), (0, 30))
            self.assertEqual(struct.unpack_from('<HH', m.party, 6), (90, 90))
        self.assertEqual(flag(sv, saves.TRAINER_BEATEN + saves.BENCH_TRAINER), 0)
        # what comes from the base stays
        self.assertEqual(flag(sv, STORY_FLAG), 1)
        self.assertEqual(sv.u('<5i', LOCATION), (67, -1, 564, 392, 0))
        self.assertEqual(sv.u('<I', OBJECTS + OBJECT_SIZE)[0], 1)

    def test_normalise_is_idempotent(self):
        once = self.out['party_nostatus']
        again = saves.normalise(Save(data=savetool.image(once))).to_bytes()
        self.assertEqual(again, savetool.image(once))

    def test_party_statuses(self):
        sv = Save(data=savetool.image(self.out['party']))
        self.assertEqual([struct.unpack_from('<I', m.party, 0)[0] for m in mons(sv)], list(saves.STATUSES))

    def test_items(self):
        sv = Save(data=savetool.image(self.out['items']))
        for pocket, item, qty in saves.ITEMS:
            off, n = savetool.POCKETS[pocket]
            self.assertIn((item, qty), [sv.u('<HH', off + 4 * k) for k in range(n)])
        self.assertEqual(sv.u('<H', savetool.OPTIONS)[0], saves.PLAYER_OPTIONS | 1 << 6)   # battle style Set

    def test_violet_gym(self):
        sv = Save(data=savetool.image(self.out['violet_gym']))
        for f in saves.GYM_NPC_FLAGS:
            self.assertEqual(flag(sv, f), 1)
        lead = sv.mon(0)
        self.assertEqual(self.asked, [157])                              # level 100's experience for the lead's species
        self.assertEqual(struct.unpack_from('<I', lead.blocks['A'], 8)[0], EXP100)
        self.assertEqual(lead.party[4], 100)
        self.assertEqual(struct.unpack_from('<7H', lead.party, 6), (999,) * 7)
        self.assertEqual(sv.u('<5i', LOCATION), (73, -1, 479, 258, 0))
        self.assertEqual(sv.u('<B', CAMERA)[0], saves.REFERENCE_CAMERA)
        self.assertEqual([sv.u('<I', OBJECTS + OBJECT_SIZE * n)[0] & 1 for n in range(1, 64)], [0] * 63)
        self.assertEqual(sv.u('<6h', OBJECTS + 0x20), (479, 0, 258, 479, 0, 258))

    def test_whiteout(self):
        sv = Save(data=savetool.image(self.out['whiteout']))
        party = mons(sv)
        self.assertEqual((party[0].party[4], struct.unpack_from('<HH', party[0].party, 6)), (5, (1, 1)))
        self.assertEqual([struct.unpack_from('<H', m.party, 6)[0] for m in party[1:]], [0] * 5)

    def test_files(self):
        self.assertEqual(sorted(self.out), sorted(saves.SAVES))
        for name, data in self.out.items():
            self.assertEqual(len(data), IMAGE_SIZE + 122, name)
            self.assertTrue(data.endswith(savetool.DSV_FOOTER), name)
            if name != 'blank':
                self.assertTrue(crc_ok(data), name)
        self.assertEqual(savetool.image(self.out['blank']), b'\xff' * IMAGE_SIZE)

    def test_raw_and_dsv_inputs_agree(self):
        again = saves.derive(savetool.dsv(self.base), lambda sp: EXP100)
        self.assertEqual(again, self.out)


class Inputs(unittest.TestCase):
    def test_refused(self):
        with self.assertRaises(ValueError):
            saves.derive(b'\0' * 1000, lambda sp: 0)                    # not a 512 KiB save
        with self.assertRaises(ValueError):
            saves.derive(bytes(IMAGE_SIZE), lambda sp: 0)               # no save slot
        with self.assertRaises(ValueError):
            saves.derive(make_base([make_mon(1, egg=True)]), lambda sp: 0)   # nothing but an Egg


class Manifest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(tbpaths, 'SAVES', self.dir.name),
                        mock.patch.object(saves, 'MANIFEST', os.path.join(self.dir.name, 'manifest.json'))]
        for p in self.patches:
            p.start()
        self.out = saves.derive(make_base([make_mon(157)]), lambda sp: EXP100)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def test_path_checks_the_manifest(self):
        with contextlib.redirect_stdout(io.StringIO()):
            saves.write_files(self.out, 'base abc')
        p = saves.path('violet_gym')
        self.assertEqual(saves.source('violet_gym'), 'base abc')
        self.assertFalse(saves.reference())
        self.assertIn('not the reference', saves.describe())
        with open(p, 'r+b') as f:                                        # damaged after it was made
            f.seek(0x40)
            f.write(b'\x01')
        with self.assertRaises(SystemExit):
            saves.path('violet_gym')
        self.assertIsNone(saves.source('violet_gym'))

    def test_reference_bytes_are_the_reference_however_made(self):
        with contextlib.redirect_stdout(io.StringIO()):
            saves.write_files(self.out, 'base abc')
        refs = {n: hashlib.sha256(self.out[n]).hexdigest() for n in saves.SAVES}
        with mock.patch.dict(saves.SAVES, refs):
            self.assertEqual(saves.source('violet_gym'), 'reference')
            self.assertTrue(saves.reference())
            self.assertIn('the reference ones', saves.describe())

    def test_missing(self):
        with self.assertRaises(SystemExit):
            saves.path('violet_gym')
        with open(saves.MANIFEST, 'w') as f:
            json.dump({}, f)
        self.assertIsNone(saves.source('violet_gym'))


class Reference(unittest.TestCase):
    def test_the_reference_base_gives_the_reference_saves(self):
        base = os.path.join(tbpaths.SAVES, 'party_nostatus.dsv')
        if not os.path.exists(base) or saves.sha256(base) != saves.SAVES['party_nostatus'] or \
                not os.path.exists(saves.DEFAULT_ROM):
            self.skipTest('needs the reference party_nostatus.dsv and %s' % tbpaths.rel(saves.DEFAULT_ROM))
        from aidata import Data
        d = Data(saves.DEFAULT_ROM)
        with open(base, 'rb') as f:
            out = saves.derive(f.read(), lambda sp: d.exp_for(sp, 100))
        self.assertEqual({n: hashlib.sha256(b).hexdigest() for n, b in out.items()}, saves.SAVES)


if __name__ == '__main__':
    unittest.main()
