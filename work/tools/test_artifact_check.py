"""Artifact orchestration tests using synthetic inputs; no ROM build or emulator."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_check as A


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        self.a = argparse.Namespace(rom=p / "rom.bin", base=p / "base.bin", build_report=p / "build.json",
                                    ws=p / "ws", extract=p / "extract", output=p / "out")
        self.a.rom.write_bytes(b"synthetic artifact")
        self.a.base.write_bytes(b"synthetic base")
        for folder in (self.a.ws, self.a.extract):
            folder.mkdir()
            (folder / "0000.json").write_text("{}")
        self.prior = {"rom": {"sha1": A.hashes(self.a.rom)["sha1"]},
                      "base": {"sha1": A.hashes(self.a.base)["sha1"]},
                      "statuses": ["draft"], "glyphs": [{"font": 0}],
                      "graphics": [{"synthetic": True}], "hardcoded": {"synthetic": True}}
        self.save_report()

    def save_report(self):
        self.a.build_report.write_text(json.dumps(self.prior))

    def export(self, workspace, extract, out, **kwargs):
        self.assertFalse(kwargs["lenient"])
        for narc in A.build.NARCS:
            (out / narc).mkdir(parents=True)
            (out / narc / "0000.json").write_text("{}")
        return {"strings": 2, "en": 2}, []

    def run_check(self, export=None, verifier=None):
        with patch.object(A.msgtool, "load_rom", return_value=object()), \
             patch.object(A.msgtool, "get_file", return_value=b"font"):
            return A.check(self.a, export or self.export, verifier or (lambda *args: {"synthetic": "ok"}))

    def test_success_and_source_unchanged(self):
        before = self.a.rom.read_bytes()
        result = self.run_check()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(self.a.rom.read_bytes(), before)
        self.assertEqual(len(result["inputs"]["ws"]["sha256"]), 64)

    def test_missing_asset_incomplete(self):
        self.a.rom.unlink()
        self.assertEqual(self.run_check()["status"], "incomplete")

    def test_empty_workspace_failed(self):
        (self.a.ws / "0000.json").unlink()
        self.assertEqual(self.run_check()["status"], "failed")

    def test_stale_identity_does_not_export(self):
        self.a.rom.write_bytes(b"changed")
        result = self.run_check(export=lambda *args, **kwargs: self.fail("export must not run"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("stale", result["reason"])

    def test_stale_base(self):
        self.a.base.write_bytes(b"changed")
        self.assertIn("base ROM identity", self.run_check()["reason"])

    def test_export_fallback_fails(self):
        result = self.run_check(export=lambda *args, **kwargs: ({"strings": 2}, ["source mismatch"]))
        self.assertEqual(result["status"], "failed")

    def test_zero_export_fails(self):
        self.assertEqual(self.run_check(export=lambda *args, **kwargs: ({}, []))["status"], "failed")

    def test_zero_banks_fails(self):
        result = self.run_check(export=lambda *args, **kwargs: ({"strings": 2}, []))
        self.assertEqual(result["status"], "failed")
        self.assertIn("zero banks", result["reason"])

    def test_missing_dependency_incomplete(self):
        def missing(*args, **kwargs):
            raise ModuleNotFoundError("ndspy")
        self.assertEqual(self.run_check(export=missing)["status"], "incomplete")

    def test_verifier_failure(self):
        def fail(*args):
            raise AssertionError("message differs")
        result = self.run_check(verifier=fail)
        self.assertEqual(result["status"], "failed")
        self.assertIn("message differs", result["reason"])

    def test_changed_workspace_fails(self):
        def change(*args):
            (self.a.ws / "0000.json").write_text('{"changed":true}')
            return {}
        self.assertIn("ws changed", self.run_check(verifier=change)["reason"])

    def test_optimized_python_incomplete(self):
        with patch.object(A.sys, "flags", argparse.Namespace(optimize=1)):
            self.assertEqual(self.run_check()["status"], "incomplete")

    def test_missing_metadata_incomplete(self):
        del self.prior["graphics"]
        self.save_report()
        self.assertEqual(self.run_check()["status"], "incomplete")

    def test_output_outside_ignored_build_rejected(self):
        for flag in ("--output", "--json"):
            with self.assertRaises(SystemExit) as error:
                A.main([flag, str(Path(self.temp.name) / "forbidden")])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((Path(self.temp.name) / "forbidden").exists())


if __name__ == "__main__":
    unittest.main()
