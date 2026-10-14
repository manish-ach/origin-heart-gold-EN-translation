"""Golden test: the vendored sources, built with the Spanish layout (builder/layouts/es.json), reproduce the Spanish
rc44 release's AI byte for byte. This proves src/ is a faithful extraction of commit dc8577c.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_golden*.py'

Compared with rc44 (docs/build-contract.md, "Inputs"): overlay 10's slot code (0x021F6E20 to its end), its y9 entry
(size, bss, static initialisers), the ITCM code appended at 0x01FF8620, the main-RAM AI code from 0x0226D4C0, and the
five core hooks' BLs. The expected sha256s are recorded below, so the test still checks the build when the ROM is
missing.

Needs the Spanish workspace repository, named by ADVAI_ES_REPO=/path/to/spanish/repo (no default): the es layout's
other asm sources (hard mode, starter, ...) come from `git archive dc8577c work_es/tools/asm` into a temporary
directory, never into this repository. Needs arm-none-eabi-gcc 16.2.0 and binutils 2.47. Skips with the reason when
an input is missing.
"""
import hashlib
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[2]
REPO = AI_DIR.parents[1]
RC44_ROM = REPO / 'work' / 'build' / 'advanced-ai' / 'es' / 'rc44.nds'
ES_REPO = os.environ.get('ADVAI_ES_REPO')

# sha256 of rc44's bytes: overlay 10 from 0x021F6E20 to its end, ITCM section from 0x01FF8620 to its end, main
# section 0x02264920 from 0x0226D4C0 to its end
EXPECTED = {
    'slot.bin': 'ec5e271b33d322a130ad619c3ccd6dc370874a27ed6a369c68aee08b28ca4ea7',
    'itcm.bin': 'c5d00f8a20cfe815e9bc0a7b3ba748c6cc164b97124a26ff9f24e28d3109ad75',
    'main.bin': '028e0a334b13c7a6132c61cb3bb601c69c0927032faa6082a940847f3c998691',
}
ROOM_LINE = ('AI room: slot code 34144 + bss 2528 (2688 free), ITCM code 25836 (756 free), .itcm_bss 4056 (436 free '
             'below 01FFFF8C), main RAM AI code 24184 (41352 free)')
O11_END = 0x12080           # overlay 11's image (0x12060) and its 0x20-byte bss, at the start of overlay 10


def load_builder():
    spec = importlib.util.spec_from_file_location('advai_build', AI_DIR / 'builder' / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def has_commit(repo, commit):
    return (repo / '.git').exists() and subprocess.run(
        ['git', '-C', str(repo), 'cat-file', '-e', commit + '^{commit}'], capture_output=True).returncode == 0


class Golden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = b = load_builder()
        if not ES_REPO:
            raise unittest.SkipTest('ADVAI_ES_REPO is not set: point it at the Spanish workspace repository')
        if not has_commit(Path(ES_REPO), b.ES_COMMIT):
            raise unittest.SkipTest('ADVAI_ES_REPO=%s has no commit %s' % (ES_REPO, b.ES_COMMIT))
        try:
            b.toolchain()
        except b.BuildError as e:
            raise unittest.SkipTest('needs the pinned toolchain: %s' % e) from None
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        tree = b.es_archive(ES_REPO, t / 'es')
        cls.payload, cls.room = b.build('es', t / 'out', es_tree=tree)
        cls.bins = {n: (t / 'out' / n).read_bytes() for n in EXPECTED}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_recorded_hashes(self):
        for n, digest in EXPECTED.items():
            with self.subTest(file=n):
                self.assertEqual(hashlib.sha256(self.bins[n]).hexdigest(), digest)

    def test_room(self):
        self.assertEqual(self.builder.room_line(self.room), ROOM_LINE)

    def test_rc44_bytes(self):
        import ndspy.rom
        if not RC44_ROM.is_file():
            self.skipTest('%s not found' % RC44_ROM.relative_to(REPO))
        rom = ndspy.rom.NintendoDSRom.fromFile(str(RC44_ROM))
        o10 = rom.loadArm9Overlays()[10]
        sections = {s.ramAddress: bytes(s.data) for s in rom.loadArm9().sections}
        self.assertEqual(bytes(o10.data)[O11_END:], self.bins['slot.bin'], 'overlay 10 slot code')
        self.assertEqual(sections[0x01FF8000][0x620:], self.bins['itcm.bin'], 'ITCM code')
        self.assertEqual(sections[0x02264920][0x0226D4C0 - 0x02264920:], self.bins['main.bin'], 'main-RAM AI code')
        ov = self.payload['overlay10']
        self.assertEqual((o10.ramAddress, len(o10.data), o10.bssSize),
                         (int(ov['ram'], 16), O11_END + len(self.bins['slot.bin']), int(ov['bss'], 16)))
        self.assertEqual(['0x%08X' % o10.staticInitStart, '0x%08X' % o10.staticInitEnd], ov['static_init'])
        o14 = rom.loadArm9Overlays()[14]
        for h in self.payload['hooks']:
            at = int(h['address'], 16) - o14.ramAddress
            with self.subTest(hook=h['target']):
                self.assertEqual(bytes(o14.data)[at:at + 4].hex(), h['after'])


if __name__ == '__main__':
    unittest.main()
