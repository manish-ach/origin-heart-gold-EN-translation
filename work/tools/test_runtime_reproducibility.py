"""Synthetic files and environment evidence; never initializes an emulator."""
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_reproducibility as R


class InputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.bin"
        self.path.write_bytes(b"synthetic input")
        self.paths = {role: self.path for role in R.REQUIRED_INPUTS}

    def test_unchanged_inputs_pass_and_survive_removal_after_report(self):
        before = R.capture_inputs(self.paths)
        proof = R.verify_inputs(before, R.capture_inputs(self.paths))
        self.assertEqual(R.evidence_status(proof), "passed")
        self.path.unlink()
        self.assertEqual(R.evidence_status(proof), "passed")

    def test_same_length_mutation_is_incomplete(self):
        before = R.capture_inputs(self.paths)
        self.path.write_bytes(b"SYNTHETIC INPUT")
        proof = R.verify_inputs(before, R.capture_inputs(self.paths))
        self.assertEqual(proof["status"], "incomplete")
        self.assertEqual(R.evidence_status(proof), "incomplete")
        self.assertTrue(all("changed" in gap for gap in proof["gaps"]))

    def test_deleted_inputs_are_incomplete(self):
        before = R.capture_inputs(self.paths)
        self.path.unlink()
        proof = R.verify_inputs(before, R.capture_inputs(self.paths))
        self.assertEqual(R.evidence_status(proof), "incomplete")
        self.assertIn("error", proof["after"]["checker"])

    def test_newly_created_input_cannot_repair_missing_initial_snapshot(self):
        self.path.unlink()
        before = R.capture_inputs(self.paths)
        self.path.write_bytes(b"synthetic input")
        self.assertEqual(R.verify_inputs(before, R.capture_inputs(self.paths))["status"], "incomplete")

    def test_changed_symlink_target_is_incomplete(self):
        link = self.path.parent / "link"
        link.symlink_to(self.path)
        before = R.capture_inputs({"fixture": link})
        replacement = self.path.parent / "replacement"
        replacement.write_bytes(self.path.read_bytes())
        link.unlink()
        link.symlink_to(replacement)
        proof = R.verify_inputs(before, R.capture_inputs({"fixture": link}))
        self.assertEqual(R.evidence_status(proof, ("fixture",)), "incomplete")

    def test_non_file_is_error(self):
        self.assertIn("error", R.capture_inputs({"fixture": self.path.parent})["fixture"])

    def test_fifo_rejected_before_open(self):
        fifo = self.path.parent / "fifo"
        os.mkfifo(fifo)
        with patch.object(os, "open", side_effect=AssertionError("Must not open FIFO")):
            self.assertIn("error", R.capture_inputs({"fixture": fifo})["fixture"])

    def test_mutation_during_hash_is_incomplete(self):
        real_digest = R.hashlib.sha256()
        class MutatingDigest:
            def update(inner, chunk):
                real_digest.update(chunk)
                self.path.write_bytes(b"replacement while hashing")
            def hexdigest(inner):
                return real_digest.hexdigest()
        with patch.object(R.hashlib, "sha256", return_value=MutatingDigest()):
            result = R.capture_inputs({"fixture": self.path})
        self.assertIn("changed while hashing", result["fixture"]["error"])

    def test_nonstring_roles_are_incomplete(self):
        before = R.capture_inputs(self.paths)
        before[1] = before["checker"]
        self.assertEqual(R.verify_inputs(before, before)["status"], "incomplete")

    def test_forged_status_missing_roles_and_malformed_identities_fail(self):
        before = R.capture_inputs(self.paths)
        proof = R.verify_inputs(before, copy.deepcopy(before))
        mutations = [lambda p: p["after"]["checker"].update(sha256="0" * 64),
                     lambda p: p["after"].pop("manifest"),
                     lambda p: p["before"]["checker"].update(size=True),
                     lambda p: p["before"]["checker"].update(path="relative"),
                     lambda p: p["before"]["checker"].update(error="read failure"),
                     lambda p: p.update(schema_version=True),
                     lambda p: p.update(gaps=["unresolved"])]
        for mutate in mutations:
            candidate = copy.deepcopy(proof)
            mutate(candidate)
            self.assertEqual(R.evidence_status(candidate), "incomplete")
        self.assertEqual(R.evidence_status(R.verify_inputs({}, {})), "incomplete")

    def test_extra_input_changes_fail_even_outside_required_roles(self):
        before = R.capture_inputs(self.paths | {"helper": self.path})
        after = copy.deepcopy(before)
        after["helper"]["sha256"] = "0" * 64
        self.assertEqual(R.verify_inputs(before, after)["status"], "incomplete")


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.library = self.folder / "native.bin"
        self.library.write_bytes(b"synthetic library")
        self.emu = SimpleNamespace(lib=SimpleNamespace(_name=str(self.library)))

    def environment(self, name="config", pid=123):
        config = self.folder / name
        config.mkdir(exist_ok=True)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}), patch.object(os, "getpid", return_value=pid):
            isolation = R.begin_worker(config)
        with patch.object(R.importlib.metadata, "version", return_value="1.0"):
            return R.worker_environment(self.emu, isolation)

    def test_worker_records_native_hash_and_uncontrolled_clock(self):
        record = self.environment()
        self.assertEqual(R.worker_environment_status(record), "passed")
        self.assertEqual(record["native_library"], R.capture_inputs({"native": self.library})["native"])
        self.assertIs(record["clock"]["controlled"], False)
        self.assertIsNone(record["native_version"]["value"])

    def test_config_not_empty_before_native_is_incomplete(self):
        config = self.folder / "dirty"
        config.mkdir()
        (config / "sidecar").write_text("existing save")
        self.assertEqual(R.worker_environment_status(self.environment("dirty")), "incomplete")

    def test_wrong_environment_path_is_incomplete(self):
        config = self.folder / "config"
        config.mkdir()
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.folder)}):
            isolation = R.begin_worker(config)
        self.assertEqual(R.worker_environment_status(R.worker_environment(self.emu, isolation)), "incomplete")

    def test_absent_isolation_is_incomplete(self):
        self.assertEqual(R.worker_environment_status(R.worker_environment(self.emu, R.begin_worker(None))), "incomplete")

    def test_unresolved_loaded_native_library_is_incomplete(self):
        record = self.environment()
        self.emu.lib._name = "libdesmume.dylib"
        result = R.worker_environment(self.emu, record["isolation"])
        self.assertEqual(R.worker_environment_status(result), "incomplete")

    def test_two_fresh_comparable_workers_pass(self):
        self.assertEqual(R.pair_environment_status(self.environment("zh", 123),
                                                   self.environment("en", 124)), "passed")

    def test_pair_reused_context_and_mismatching_runtime_fail(self):
        zh, en = self.environment("zh", 123), self.environment("en", 124)
        mutations = [lambda e: e["isolation"].update(pid=123),
                     lambda e: e["isolation"].update(config_path=zh["isolation"]["config_path"],
                                                     xdg_config_home=zh["isolation"]["config_path"]),
                     lambda e: e["native_library"].update(sha256="0" * 64),
                     lambda e: e["packages"].update({"py-desmume": "2.0"}),
                     lambda e: e["clock"].update(controlled=True),
                     lambda e: e["clock"].update(controlled=0),
                     lambda e: e["settings"].update(reset_after_import=1),
                     lambda e: e["settings"].update(cycle_with_joystick=True),
                     lambda e: e["isolation"].update(config_empty_before_native=1),
                     lambda e: e["isolation"].update(pid=True),
                     lambda e: e["packages"].pop("Pillow")]
        for mutate in mutations:
            candidate = copy.deepcopy(en)
            mutate(candidate)
            self.assertEqual(R.pair_environment_status(zh, candidate), "incomplete")


if __name__ == "__main__":
    unittest.main()
