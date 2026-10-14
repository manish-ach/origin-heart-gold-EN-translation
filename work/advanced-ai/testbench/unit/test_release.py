"""Release tests: builder/release.py refuses every input a release must not be built from, and its release.json
chains the hashes from the standard build to the xdelta.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_release*.py'

No game data: difficulty's candidate is test_install's synthetic ROM, with a synthetic difficulty receipt and
verification beside it; the USA ROM is random bytes with their own SHA-1; xdelta3's pin and the git state are given
to release() instead of read from the machine. The refusals need nothing else. The cases that write a patch need
xdelta3 on PATH (any version: its pin is given) and skip without it.
"""
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_install as ti  # noqa: E402
from test_install import install, verify  # noqa: E402
import release  # noqa: E402

PINNED = (release.tb.XDELTA3_VERSION, True)
CLEAN = {"head": "c" * 40, "payload_commit": "d" * 40, "changed": []}
STANDARD = {"path": "/build/origin_hg_v4.0.3_en_wip.nds", "bytes": 1234, "sha256": "ab" * 32}
HAS_XDELTA3 = shutil.which("xdelta3") is not None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Release(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.payload = ti.synthetic_payload(self.dir / "payload")
        self.marks = ti.write_marks(self.dir / "marks.json")
        self.rom = ti.synthetic_rom()
        self.pins = ti.synthetic_pins(self.rom)
        self.diff = self.dir / "difficulty"
        self.diff.mkdir()
        self.candidate = self.diff / "candidate.nds"
        self.candidate.write_bytes(self.rom)
        self.receipt = self.diff / "receipt.json"
        self.write_receipt()
        self.verification = self.diff / "verification.json"
        self.write_verification()
        self.base = self.dir / "usa.nds"
        self.base.write_bytes(ti.blob(99, 0x40000) + self.rom[0x40000:])
        self.out = self.dir / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def write_receipt(self, rom=None, **fields):
        rom = self.rom if rom is None else rom
        r = {"format": 1, "status": "built, installed, reopened and logically verified", "tool_mode": "release",
             "input": STANDARD, "output": {"path": str(self.candidate), "bytes": len(rom), "sha256": sha256(rom)},
             "tools": {"clang": {"matches_release_pin": True}, "armips": {"matches_release_pin": True}},
             "native_gameplay_acceptance": False} | fields
        self.receipt.write_text(json.dumps(r))

    def write_verification(self, **fields):
        v = {"status": "passed", "tool_mode": "release", "receipt": {"sha256": sha256(self.receipt.read_bytes())},
             "output": {"sha256": sha256(self.candidate.read_bytes())}} | fields
        self.verification.write_text(json.dumps(v))

    def run_release(self, **kw):
        args = dict(difficulty_verification=self.verification, base=self.base, payload_dir=self.payload,
                    marks_path=self.marks, pins=self.pins, base_sha1=hashlib.sha1(self.base.read_bytes()).hexdigest(),
                    xdelta=lambda: PINNED, git=lambda: CLEAN)
        return release.release(self.receipt, kw.pop("out_dir", self.out), **(args | kw))

    def refused(self, fragment, **kw):
        with self.assertRaises(install.Refused) as cm:
            self.run_release(**kw)
        self.assertIn(fragment, str(cm.exception))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()), "a refused release wrote into --out-dir")
        return str(cm.exception)

    # -- refusals: nothing is written --------------------------------------------------------------------------
    def test_refuses_a_development_difficulty(self):
        self.write_receipt(tool_mode="development")
        self.write_verification(tool_mode="development")
        message = self.refused("difficulty was built in development mode")
        self.assertIn("difficulty's verification ran in development mode", message)
        self.assertIn("--allow-development", message)

    def test_refuses_difficulty_tools_off_their_release_pins(self):
        self.write_receipt(tools={"clang": {"matches_release_pin": False}, "armips": {"matches_release_pin": True}})
        self.write_verification()
        self.refused("difficulty's tools off their release pins: clang")

    def test_refuses_without_difficultys_verification(self):
        self.refused("no --difficulty-verification", difficulty_verification=None)

    def test_refuses_a_verification_that_did_not_pass_or_is_for_something_else(self):
        self.write_verification(status="failed")
        self.refused("did not pass")
        self.write_verification(receipt={"sha256": "00" * 32})
        self.refused("verifies another receipt")
        self.write_verification(output={"sha256": "00" * 32})
        self.refused("verifies another ROM")

    def test_refuses_an_unpinned_xdelta3(self):
        self.refused("xdelta3 3.0.11 is not build.py's pin", xdelta=lambda: ("3.0.11", False))

    def test_refuses_an_uncommitted_payload_or_no_git(self):
        changed = CLEAN | {"changed": [" M work/advanced-ai/payload/slot.bin"]}
        self.refused("differ from HEAD:  M work/advanced-ai/payload/slot.bin", git=lambda: changed)
        self.refused("no git", git=lambda: None)

    def test_refuses_a_candidate_that_is_not_the_receipts_output(self):
        self.candidate.write_bytes(self.rom[:-1] + b"\xff")
        self.refused("no file is difficulty's candidate")
        self.candidate.write_bytes(self.rom)
        other = self.dir / "other.nds"
        other.write_bytes(ti.synthetic_rom(itcm_len=ti.MAIN_ITCM))
        self.refused(str(other), candidate=other)

    def test_refuses_another_base_rom(self):
        self.refused("is not Pokémon HeartGold (USA)", base_sha1="0" * 40)

    def test_refuses_an_out_dir_under_work_release(self):
        out = release.RELEASES / "v0.0.0-test-never-created"
        self.refused("is under work/release/", out_dir=out, allow_development=True)
        self.assertFalse(out.exists())

    def test_refuses_a_publication_that_needs_recovery(self):
        (self.diff / release.PUBLICATION_JOURNAL).write_text("{}")
        self.refused("needs recovery")

    def test_refuses_a_tag_that_is_not_a_file_name(self):
        self.refused("--tag '../x'", tag="../x")

    def test_refuses_a_receipt_without_input_and_output(self):
        self.receipt.write_text(json.dumps({"format": 1}))
        self.refused("is not a difficulty receipt")

    def test_an_install_refusal_leaves_no_release_receipt(self):
        """A candidate without difficulty: install.py refuses after release.py's own checks passed, and the
        release.json of an earlier run is gone, so the folder does not claim a release."""
        rom = ti.synthetic_rom(autoloads=2)
        self.candidate.write_bytes(rom)
        self.write_receipt(rom)
        self.write_verification()
        self.out.mkdir()
        (self.out / release.RECEIPT).write_text("{}")
        with self.assertRaisesRegex(install.Refused, "no difficulty"):
            self.run_release()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [])

    def test_cli_refuses_and_exits_1(self):
        self.write_receipt(tool_mode="development")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = release.main(["--difficulty-receipt", str(self.receipt), "--out-dir", str(self.out)])
        self.assertEqual(code, 1)
        self.assertIn("release.py: refused: ", err.getvalue())
        self.assertFalse(self.out.exists())

    # -- finding the candidate ---------------------------------------------------------------------------------
    def test_finds_the_candidate_beside_the_receipt(self):
        out = {"path": str(self.dir / "moved" / "candidate.nds"), "bytes": len(self.rom), "sha256": sha256(self.rom)}
        path, data = release.find_candidate(self.receipt, out)
        self.assertEqual((path, data), (self.candidate, self.rom))
        named = self.dir / "difficulty_dev_main.receipt.json"
        (self.dir / "difficulty_dev_main.nds").write_bytes(self.rom)
        self.assertEqual(release.find_candidate(named, out)[0], self.dir / "difficulty_dev_main.nds")

    # -- the release ---------------------------------------------------------------------------------------------
    @unittest.skipUnless(HAS_XDELTA3, "needs xdelta3 on PATH")
    def test_receipt_chains_every_hash(self):
        r = self.run_release(tag="v9.9.9-rc1")
        ai_rom = self.out / release.AI_ROM
        patch = self.out / "Origin_HeartGold_v4.0.3_EN_v9.9.9-rc1.xdelta"
        data, patch_data = ai_rom.read_bytes(), patch.read_bytes()
        self.assertEqual(json.loads((self.out / release.RECEIPT).read_text()), r)
        self.assertTrue(r["releasable"])
        self.assertEqual(r["not_releasable_because"], [])
        self.assertEqual(r["standard_build"], STANDARD)
        self.assertEqual(r["difficulty"]["receipt"]["sha256"], sha256(self.receipt.read_bytes()))
        self.assertEqual(r["difficulty"]["verification"]["sha256"], sha256(self.verification.read_bytes()))
        self.assertEqual(r["difficulty"]["candidate"]["sha256"], sha256(self.rom))
        self.assertEqual(r["advanced_ai"]["git"], CLEAN)
        self.assertEqual(r["advanced_ai"]["payload"]["payload.json"],
                         sha256((self.payload / "payload.json").read_bytes()))
        self.assertEqual(r["advanced_ai"]["marks_sha256"], sha256(Path(self.marks).read_bytes()))
        installed = Path(str(ai_rom) + ".receipt.json")
        self.assertEqual(r["advanced_ai"]["install_receipt"]["sha256"], sha256(installed.read_bytes()))
        inst = json.loads(installed.read_text())
        self.assertEqual((inst["input"]["sha256"], inst["output"]["sha256"]), (sha256(self.rom), sha256(data)))
        self.assertEqual(inst["difficulty"]["mode"], "release")
        self.assertEqual(r["ai_rom"]["sha256"], sha256(data))
        self.assertEqual(r["base"]["sha1"], hashlib.sha1(self.base.read_bytes()).hexdigest())
        self.assertEqual((r["xdelta"]["sha1"], r["xdelta"]["sha256"]),
                         (hashlib.sha1(patch_data).hexdigest(), sha256(patch_data)))
        self.assertEqual(r["readme_lines"], [f"Patch:    {patch.name}", f"  SHA-1   {r['xdelta']['sha1']}",
                                             f"Result ROM SHA-1: {hashlib.sha1(data).hexdigest()}"])
        report = verify.verify(data, self.payload, self.marks, self.rom, overlay11_sha256=self.pins.overlay11_sha256)
        self.assertTrue(report["ok"], report["errors"])
        # the patch, applied on its own, gives the AI ROM; its header holds build.py's names, not ours
        back = self.dir / "back.nds"
        subprocess.run(["xdelta3", "-d", "-s", str(self.base), str(patch), str(back)], check=True)
        self.assertEqual(back.read_bytes(), data)
        header = subprocess.run(["xdelta3", "printhdr", str(patch)], capture_output=True, text=True).stdout
        self.assertIn(f"XDELTA filename (output):     {release.tb.PATCH_TARGET_NAME}", header)
        self.assertIn(f"XDELTA filename (source):     {release.tb.PATCH_SOURCE_NAME}", header)
        self.assertIn("VCDIFF secondary compressor:  lzma", header)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         sorted([release.AI_ROM, installed.name, patch.name, release.RECEIPT]))

    @unittest.skipUnless(HAS_XDELTA3, "needs xdelta3 on PATH")
    def test_development_output_is_marked_not_releasable(self):
        self.write_receipt(tool_mode="development")
        self.write_verification(tool_mode="development")
        r = self.run_release(allow_development=True, xdelta=lambda: ("3.2.1", False))
        self.assertFalse(r["releasable"])
        self.assertEqual(r["not_releasable_because"], [
            "difficulty was built in development mode", "difficulty's verification ran in development mode",
            f"xdelta3 3.2.1 is not build.py's pin {release.tb.XDELTA3_VERSION}"])
        self.assertTrue((self.out / "Origin_HeartGold_v4.0.3_EN_wip-development.xdelta").is_file())
        self.assertFalse((self.out / "Origin_HeartGold_v4.0.3_EN_wip.xdelta").exists())
        self.assertEqual(r["xdelta"]["xdelta3_pinned"], False)
        # the flag alone marks it too, even when every input is a release one
        self.write_receipt()
        self.write_verification()
        r = self.run_release(allow_development=True)
        self.assertEqual((r["releasable"], r["not_releasable_because"]), (False, ["--allow-development"]))


if __name__ == "__main__":
    unittest.main()
