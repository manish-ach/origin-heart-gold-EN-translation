"""Trainer marks: data/trainer_marks.json is the Spanish build's lists, and nothing in the hack reads header byte 2.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_marks*.py'

- The lists: 453 important and 129 keep-lead trainer ids, sorted, unique, within the 1024 records of a/0/5/5, never
  trainer 0; equal to IMPORTANT_TRAINERS and KEEP_LEAD_TRAINERS in the Spanish build.py at commit dc8577c (read
  at test time from the Spanish workspace repository named by ADVAI_ES_REPO; skips when it is unset) and to bits 0
  and 1 of byte 2 in Spanish rc44.
- Byte 2 is 0 in every trainer header of the Chinese ROM and the rc8 release.
- Nobody reads byte 2 (data/README.md, "Byte 2 is free"): the only callers of TrainerData_ReadTrData (0x02072700,
  the one reader of a/0/5/5) and TrainerData_GetAttr (0x020725F4) are the four and two reviewed sites, GetAttr is
  never asked for attribute 2, and the reviewed readers' code is the Chinese ROM's in the rc8 release.
ROMs come from work/rom/ and work/build/advanced-ai/ (each case skips when its ROM is missing).
"""
import ast
import json
import os
import struct
import subprocess
import unittest
from pathlib import Path

import ndspy.narc
import ndspy.rom

AI_DIR = Path(__file__).resolve().parents[2]
REPO = AI_DIR.parents[1]
MARKS = AI_DIR / "data" / "trainer_marks.json"
ES_REPO = Path(os.environ["ADVAI_ES_REPO"]) if os.environ.get("ADVAI_ES_REPO") else None
ES_COMMIT = "dc8577c"
CN_ROM = REPO / "work" / "rom" / "origin_v4.0.3_cn.nds"
RC8_RELEASE = REPO / "work" / "build" / "advanced-ai" / "base" / "rc8_release.nds"
RC44 = REPO / "work" / "build" / "advanced-ai" / "es" / "rc44.nds"

READ_TR_DATA, GET_ATTR = 0x02072700, 0x020725F4
# (file, call site) of every BL to them, reviewed in data/README.md
READ_TR_DATA_CALLERS = {("arm9", 0x0207257C), ("arm9", 0x020725FC), ("ov14", 0x0222C1DE), ("ov92", 0x021F1EBA)}
GET_ATTR_CALLERS = {("arm9", 0x0203FC40): 9, ("arm9", 0x020541EE): 1}
# the reviewed readers' code: EnemyTrainerSet_Init, TrainerData_GetAttr, and the two overlay readers
READERS = [("arm9", 0x02072544, 0x020725F0), ("arm9", 0x020725F4, 0x02072654),
           ("ov14", 0x0222C1BC, 0x0222C264), ("ov92", 0x021F1EB0, 0x021F1F10)]


def load_marks():
    return json.loads(MARKS.read_text())


def code_blobs(rom):
    arm = rom.loadArm9()
    out = {"arm9": (0x02000000, bytes(arm.sections[0].data))}
    for s in arm.sections[1:]:
        out[f"autoload {s.ramAddress:#x}"] = (s.ramAddress, bytes(s.data))
    for i, o in rom.loadArm9Overlays().items():
        out[f"ov{i}"] = (o.ramAddress, bytes(o.data))
    return out


def thumb_calls(blobs, target):
    """Every Thumb BL/BLX in the code that reaches target: {(file, site)}."""
    found = set()
    for name, (base, data) in blobs.items():
        for off in range(0, len(data) - 3, 2):
            h1, h2 = struct.unpack_from("<HH", data, off)
            if h1 & 0xF800 != 0xF000 or h2 & 0xE800 != 0xE800:
                continue
            o = (h1 & 0x7FF) << 12 | (h2 & 0x7FF) << 1
            o -= 0x800000 if o & 0x400000 else 0
            t = base + off + 4 + o
            if (t & ~3 if h2 & 0xF800 == 0xE800 else t) == target:
                found.add((name, base + off))
    return found


def byte2(path):
    rom = ndspy.rom.NintendoDSRom.fromFile(path)
    return [f[2] for f in ndspy.narc.NARC(rom.getFileByName("a/0/5/5")).files]


class Lists(unittest.TestCase):
    def test_counts_order_and_range(self):
        m = load_marks()
        self.assertEqual(set(m), {"important", "keep_lead"})
        self.assertEqual((len(m["important"]), len(m["keep_lead"])), (453, 129))
        for name, ids in m.items():
            with self.subTest(name):
                self.assertEqual(ids, sorted(set(ids)))
                self.assertTrue(all(isinstance(i, int) and 1 <= i <= 1023 for i in ids))
                self.assertNotIn(0, ids)

    def test_equal_to_the_spanish_build(self):
        if ES_REPO is None:
            self.skipTest("set ADVAI_ES_REPO to the Spanish workspace repository to compare with its build.py")
        if not (ES_REPO / ".git").exists():
            self.skipTest(f"ADVAI_ES_REPO={ES_REPO} is not a git repository")
        src = subprocess.run(["git", "-C", str(ES_REPO), "show", f"{ES_COMMIT}:work_es/tools/build.py"],
                             capture_output=True, text=True, check=True).stdout
        lists = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in ("IMPORTANT_TRAINERS", "KEEP_LEAD_TRAINERS")}
        m = load_marks()
        self.assertEqual(m["important"], lists["IMPORTANT_TRAINERS"])
        self.assertEqual(m["keep_lead"], lists["KEEP_LEAD_TRAINERS"])

    @unittest.skipUnless(RC44.exists(), "needs work/build/advanced-ai/es/rc44.nds")
    def test_equal_to_rc44s_bits(self):
        b = byte2(RC44)
        m = load_marks()
        self.assertEqual([i for i, v in enumerate(b) if v & 1], m["important"])
        self.assertEqual([i for i, v in enumerate(b) if v & 2], m["keep_lead"])


class ByteTwoIsFree(unittest.TestCase):
    def roms(self):
        found = [p for p in (CN_ROM, RC8_RELEASE) if p.exists()]
        if not found:
            self.skipTest("needs work/rom/origin_v4.0.3_cn.nds or the rc8 release")
        return found

    def test_byte_2_is_zero(self):
        for path in self.roms():
            with self.subTest(path.name):
                b = byte2(path)
                self.assertEqual(len(b), 1024)
                self.assertEqual(sum(1 for v in b if v), 0)

    def test_only_the_reviewed_code_reads_trainer_headers(self):
        for path in self.roms():
            blobs = code_blobs(ndspy.rom.NintendoDSRom.fromFile(path))
            with self.subTest(path.name):
                self.assertEqual(thumb_calls(blobs, READ_TR_DATA), READ_TR_DATA_CALLERS)
                self.assertEqual(thumb_calls(blobs, GET_ATTR), set(GET_ATTR_CALLERS))
                for (name, site), attr in GET_ATTR_CALLERS.items():
                    base, data = blobs[name]
                    movs = struct.unpack_from("<H", data, site - 2 - base)[0]
                    self.assertEqual(movs, 0x2100 | attr, f"{site:#x}: movs r1, #{attr} before the call")

    @unittest.skipUnless(CN_ROM.exists() and RC8_RELEASE.exists(), "needs the Chinese ROM and the rc8 release")
    def test_reviewed_readers_unchanged_in_rc8(self):
        cn = code_blobs(ndspy.rom.NintendoDSRom.fromFile(CN_ROM))
        en = code_blobs(ndspy.rom.NintendoDSRom.fromFile(RC8_RELEASE))
        for name, lo, hi in READERS:
            with self.subTest(f"{name} {lo:#x}"):
                (b1, d1), (b2, d2) = cn[name], en[name]
                self.assertEqual(d1[lo - b1:hi - b1], d2[lo - b2:hi - b2])


if __name__ == "__main__":
    unittest.main()
