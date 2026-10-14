"""Unit tests for builder/build.py: the toolchain pin, the payload's schema and limits, no ROM bytes in the payload,
a byte-identical double build, steering compiled out, and the committed payload/ matching a fresh build.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_build*.py'

The build tests need arm-none-eabi-gcc 16.2.0 and binutils 2.47 and skip without them. The ROM checks read the
untouched Chinese ROM, the rc8 release and main's standard build (docs/build-contract.md, "Inputs") and skip when
they are missing.
"""
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[2]
REPO = AI_DIR.parents[1]
BUILD_PY = AI_DIR / 'builder' / 'build.py'
PAYLOAD = AI_DIR / 'payload'
CN_ROM = REPO / 'work' / 'rom' / 'origin_v4.0.3_cn.nds'
RC8_ROM = REPO / 'work' / 'build' / 'advanced-ai' / 'base' / 'rc8_release.nds'
MAIN_ROM = REPO / 'work' / 'build' / 'advanced-ai' / 'base' / 'main_standard.nds'
TOOLS = REPO / 'work' / 'tools'
ITCM, TEXT_SPEED_END = 0x01FF8000, 0x01FF8FC0    # the ITCM block, and its end after text speed (work/patches/text-speed)
EN_ITCM = 0x01FF9500


def load_builder():
    spec = importlib.util.spec_from_file_location('advai_build', BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def toolchain_or_skip():
    try:
        builder.toolchain()
    except builder.BuildError as e:
        raise unittest.SkipTest('needs the pinned toolchain: %s' % e) from None


def read_rom(path):
    import ndspy.rom
    if not path.is_file():
        raise unittest.SkipTest('%s not found' % path.relative_to(REPO))
    return ndspy.rom.NintendoDSRom.fromFile(str(path))


def overlay_bytes(rom, ov, address, size):
    o = rom.loadArm9Overlays()[ov]
    return bytes(o.data)[address - o.ramAddress:address - o.ramAddress + size]


def arm9_bytes(rom, address, size):
    main = bytes(rom.loadArm9().sections[0].data)
    return main[address - 0x02000000:address - 0x02000000 + size]


class ToolchainPin(unittest.TestCase):
    BANNER = 'GNU ld (GNU Binutils) %s'

    def test_pinned_versions_pass(self):
        for binutils in ('2.47', '2.47.20260726'):
            got = builder.toolchain_versions('16.2.0\n', {'ld': self.BANNER % binutils, 'as': self.BANNER % binutils})
            self.assertEqual(got, {'gcc': '16.2.0', 'binutils': '2.47'})

    def test_other_versions_refused(self):
        for gcc, binutils in (('16.1.0', '2.47'), ('16.2.1', '2.47'), ('15.2.0', '2.47'), ('16.2.0', '2.46'),
                              ('16.2.0', '2.48'), ('16.2.0', '2.47.1'), ('', '2.47')):
            with self.subTest(gcc=gcc, binutils=binutils), self.assertRaises(builder.BuildError):
                builder.toolchain_versions(gcc, {'ld': self.BANNER % binutils})

    def test_build_refuses_other_gcc_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / 'bin'
            fake.mkdir()
            for name in ('gcc',) + builder.BINUTILS:
                script = fake / ('arm-none-eabi-' + name)
                version = '16.1.0' if name == 'gcc' else 'GNU %s (GNU Binutils) 2.47' % name
                script.write_text('#!/bin/sh\necho "%s"\n' % version)
                script.chmod(script.stat().st_mode | stat.S_IEXEC)
            out = Path(t) / 'out'
            env = dict(os.environ, PATH='%s:/usr/bin:/bin' % fake)
            proc = subprocess.run([sys.executable, str(BUILD_PY), '--layout', 'en', '--out', str(out)],
                                  capture_output=True, text=True, env=env)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('16.1.0', proc.stderr)
            self.assertIn('16.2.0', proc.stderr)
            self.assertFalse(out.exists())


class EnglishBuild(unittest.TestCase):
    """Two builds of the en layout, one keeping its ELF."""

    @classmethod
    def setUpClass(cls):
        toolchain_or_skip()
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.out, cls.out2, cls.work = t / 'a', t / 'b', t / 'work'
        cls.payload, _ = builder.build('en', cls.out, work=cls.work)
        builder.build('en', cls.out2)
        cls.bins = {n: (cls.out / n).read_bytes() for n in ('slot.bin', 'itcm.bin', 'main.bin')}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_double_build_identical(self):
        for n in ('payload.json', 'slot.bin', 'itcm.bin', 'main.bin'):
            with self.subTest(file=n):
                self.assertEqual((self.out / n).read_bytes(), (self.out2 / n).read_bytes())

    def test_committed_payload_is_this_build(self):
        if not (PAYLOAD / 'payload.json').is_file():
            self.skipTest('payload/ not written yet')
        for n in ('payload.json', 'slot.bin', 'itcm.bin', 'main.bin'):
            with self.subTest(file=n):
                self.assertEqual((PAYLOAD / n).read_bytes(), (self.out / n).read_bytes(),
                                 'payload/%s is stale: rebuild with build.py --layout en --out %s' % (n, PAYLOAD))

    def test_schema(self):
        p = self.payload
        self.assertEqual(json.loads((self.out / 'payload.json').read_text()), p)
        self.assertEqual(p['format'], 1)
        self.assertEqual(p['layout'], 'en')
        self.assertEqual(p['toolchain'], {'gcc': '16.2.0', 'binutils': '2.47'})
        for name in ('src/advai.c', 'src/replace.c', 'src/lead.c', 'src/engine.h', 'src/tune.h', 'src/ids.h',
                     'src/link.ld', 'src/aiselect.s', 'src/check_flag.s', 'builder/build.py',
                     'builder/layouts/en.json'):
            with self.subTest(source=name):
                self.assertEqual(p['sources'][name], hashlib.sha256((AI_DIR / name).read_bytes()).hexdigest())
        self.assertEqual(set(p['regions']), {'slot', 'itcm', 'itcm_ram', 'main'})
        for name, region in p['regions'].items():
            self.assertRegex(region['ram'], r'^0x[0-9A-F]{8}$')
            self.assertRegex(region['limit'], r'^0x[0-9A-F]{8}$')
            self.assertIsInstance(region['size'], int)
            if 'file' in region:
                self.assertEqual(region['size'], len(self.bins[region['file']]), name)
                self.assertEqual(p['files'][region['file']], hashlib.sha256(self.bins[region['file']]).hexdigest())
        self.assertEqual(p['overlay10']['ram'], '0x021E4DA0')
        self.assertEqual(int(p['overlay10']['bss'], 16), p['regions']['slot']['bss'])
        self.assertEqual(p['overlay10']['static_init'], ['0x021F6DE8', '0x021F6DEC'])
        for name, address in p['symbols'].items():
            self.assertRegex(address, r'^0x[0-9A-F]{8}$', name)

    def test_symbols_thumb_and_entry_points(self):
        s = {n: int(a, 16) for n, a in self.payload['symbols'].items()}
        self.assertEqual(s['adv_entry'], 0x021F6E21)
        for fn in ('ai_serves', 'ai_slot_select', 'ai_entry', 'ai_bag_check', 'check_flag', 'ai_replace', 'ai_lead',
                   'ai_resume', 'ai_slot_free', 'write_action'):
            self.assertTrue(s[fn] & 1, '%s lacks the Thumb bit' % fn)
        for obj in ('g_tune', 'ai_debug', 'live', 'fs'):
            self.assertFalse(s[obj] & 1, obj)
        self.assertEqual(s['ai_serves'], EN_ITCM | 1, 'aiselect.s must be first in the itcm region')
        self.assertEqual(s['ai_lead'], 0x023D4001, 'ai_lead must be first in the main region (its hook)')
        self.assertEqual(s['__bss_start'], 0x021F6E20 + len(self.bins['slot.bin']))

    def test_regions_within_limits(self):
        r = {n: {k: int(v, 16) if isinstance(v, str) and v.startswith('0x') else v for k, v in x.items()}
             for n, x in self.payload['regions'].items()}
        self.assertEqual((r['slot']['ram'], r['slot']['limit']), (0x021F6E20, 0x022007E0))
        self.assertEqual((r['itcm']['ram'], r['itcm']['limit']), (EN_ITCM, 0x01FFEE00))
        self.assertEqual((r['itcm_ram']['ram'], r['itcm_ram']['limit']), (0x01FFEE00, 0x01FFFF8C))
        self.assertEqual((r['main']['ram'], r['main']['limit']), (0x023D4000, 0x023DC000))
        self.assertLessEqual(r['slot']['ram'] + r['slot']['size'] + r['slot']['bss'], r['slot']['limit'])
        self.assertLessEqual(r['itcm']['ram'] + r['itcm']['size'], r['itcm']['limit'])
        self.assertLessEqual(r['itcm_ram']['ram'] + r['itcm_ram']['size'], r['itcm_ram']['limit'])
        self.assertLessEqual(r['main']['ram'] + r['main']['size'], r['main']['limit'])
        spans = [(r['slot']['ram'], r['slot']['limit']), (r['itcm']['ram'], r['itcm']['limit']),
                 (r['itcm_ram']['ram'], r['itcm_ram']['limit']), (r['main']['ram'], r['main']['limit'])]
        for name, address in self.payload['symbols'].items():
            a = int(address, 16) & ~1
            self.assertTrue(any(lo <= a < hi for lo, hi in spans), '%s at %08X is outside every region' % (name, a))

    def test_itcm_bss_zeroes_work_ram(self):
        """The itcm section's bss (zeroed by the boot's autoload) covers every .itcm_bss variable, such as g_narc,
        which the AI opens only while it is 0, and stops below the fixed test records at 0x01FFFF8C."""
        itcm = self.payload['regions']['itcm']
        lo = int(itcm['ram'], 16) + itcm['size']
        hi = lo + itcm['bss']
        self.assertLessEqual(hi, 0x01FFFF8C)
        elf = str(self.work / 'ai.elf')
        sections = subprocess.run(['arm-none-eabi-readelf', '-SW', elf], capture_output=True, text=True,
                                  check=True).stdout
        index = re.search(r'\[\s*(\d+)\]\s+\.itcm_bss\s', sections).group(1)
        symbols = subprocess.run(['arm-none-eabi-readelf', '-sW', elf], capture_output=True, text=True,
                                 check=True).stdout
        work_ram = [(f[7], int(f[1], 16), int(f[2], 0)) for f in (line.split() for line in symbols.splitlines())
                    if len(f) >= 8 and f[6] == index and f[3] == 'OBJECT']
        self.assertIn('g_narc', [n for n, _, _ in work_ram])
        self.assertGreater(len(work_ram), 10)
        for name, address, size in work_ram:
            with self.subTest(symbol=name):
                self.assertTrue(lo <= address and address + size <= hi,
                                '%s %08X+%X is outside the zeroed %08X-%08X' % (name, address, size, lo, hi))

    def test_hooks_and_words(self):
        s = {n: int(a, 16) for n, a in self.payload['symbols'].items()}
        hooks = self.payload['hooks']
        self.assertEqual([(h['address'], h['target']) for h in hooks],
                         [('0x02223D10', 'ai_slot_select'), ('0x02203736', 'ai_entry'), ('0x02203C06', 'ai_replace'),
                          ('0x022029CC', 'ai_bag_check'), ('0x022153C2', 'ai_lead')])
        for h in hooks:
            self.assertEqual((h['file'], h['kind']), ('overlay14', 'bl'))
            self.assertEqual(h['after'], builder.thumb_bl(int(h['address'], 16), s[h['target']] & ~1).hex())
        self.assertEqual([(w['file'], w['address'], w['before'], w['after']) for w in self.payload['words']],
                         [('arm9', '0x020D1A28', 'itcm_end', '00000002'), ('arm9', '0x020D1970', '00c03d02', '00403d02')])
        self.assertEqual(self.payload['words'][0]['before_max'], self.payload['regions']['itcm']['ram'])

    def test_steering_compiled_out(self):
        """Only ai_serves reads a flag: no path reaches check_flag(0x218), so flag 0x218 cannot turn steering on."""
        dump = subprocess.run(['arm-none-eabi-objdump', '-d', str(self.work / 'ai.elf')], capture_output=True,
                              text=True, check=True).stdout
        callers, fn = set(), None
        for line in dump.splitlines():
            m = re.match(r'[0-9a-f]{8} <(.+)>:$', line)
            if m:
                fn = m.group(1)
            elif re.search(r'\sbl\s.*<check_flag>', line):
                callers.add(fn)
        self.assertEqual(callers, {'ai_serves'})
        self.assertNotIn('steer_marked', self.payload['symbols'])

    def test_no_rom_bytes(self):
        """The payload holds only compiled code: no 64-byte block of overlay 11 (the image overlay 10 starts with)."""
        rom = read_rom(CN_ROM)
        o11 = bytes(rom.loadArm9Overlays()[11].data)
        blob = b''.join(self.bins.values())
        self.assertNotIn(o11[:256], blob)
        self.assertNotEqual(self.bins['slot.bin'][:256], o11[:256])
        for at in range(0, len(o11) - 64, 64):
            block = o11[at:at + 64]
            if len(set(block)) >= 24:       # skip zero runs and tables a compiler could also emit
                self.assertNotIn(block, blob, 'overlay 11 bytes at +0x%X are in the payload' % at)
        self.assertNotIn(o11[:32].hex(), (self.out / 'payload.json').read_text())


class LayoutSites(unittest.TestCase):
    """en.json against the ROMs it installs on: the hook sites hold `before` in the Chinese ROM, the rc8 release and
    main's standard build; the arena words hold the rc8 release's bytes, or for "itcm_end" the end of the ROM's ITCM
    block, at most `before_max`."""

    def test_en_before_bytes(self):
        layout = json.loads((AI_DIR / 'builder' / 'layouts' / 'en.json').read_text())
        roms = {'cn': read_rom(CN_ROM), 'rc8': read_rom(RC8_ROM), 'main': read_rom(MAIN_ROM)}
        for h in layout['hooks']:
            for name, rom in roms.items():
                with self.subTest(hook=h['address'], rom=name):
                    self.assertEqual(overlay_bytes(rom, 14, int(h['address'], 16), 4).hex(), h['before'])
        for w in layout['words']:
            for name in ('rc8', 'main'):
                rom = roms[name]
                value = int.from_bytes(arm9_bytes(rom, int(w['address'], 16), 4), 'little')
                with self.subTest(word=w['address'], rom=name):
                    if w['before'] == 'itcm_end':
                        itcm = next(s for s in rom.loadArm9().sections if s.ramAddress == ITCM)
                        self.assertEqual(value, ITCM + len(itcm.data))
                        self.assertLessEqual(value, int(w['before_max'], 16))
                    elif name == 'rc8':         # main's standard build has no difficulty yet
                        self.assertEqual(value.to_bytes(4, 'little').hex(), w['before'])

    def test_itcm_origin_clears_every_trainer_display_block(self):
        """The en itcm origin lies 0x100 or more past the largest ITCM block a locale can have: text speed, then
        trainer_display.py's block at its own limits (its code and literal pool, a 16-byte entry per alias and one
        terminating entry, each name at most 64 units of 2 bytes, the end rounded up to 32 bytes)."""
        sys.path.insert(0, str(TOOLS))              # trainer_display imports msgtool when it encodes
        try:
            import trainer_display as td
            self.assertEqual(len(td.encoded('A' * 63)), 64)
            with self.assertRaises(ValueError):
                td.encoded('A' * 64)                # 65 units with the terminator: refused
        finally:
            sys.path.remove(str(TOOLS))
        names = len(td.IDS)
        worst = TEXT_SPEED_END + len(td.CODE) + 12 + (names + 1) * 16 + names * 64 * 2
        worst = (worst + 31) & ~31
        self.assertEqual(worst, 0x01FF9320)
        layout = json.loads((AI_DIR / 'builder' / 'layouts' / 'en.json').read_text())
        self.assertGreaterEqual(int(layout['regions']['itcm']['origin'], 16), worst + 0x100)


if __name__ == '__main__':
    unittest.main()
