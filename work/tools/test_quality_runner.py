"""Synthetic subprocess tests for the local quality gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_runner as Q


class QualityRunnerTests(unittest.TestCase):
    def test_static_text_missing_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            target = folder / "text_static.json"
            target.write_text(json.dumps({"status": "passed"}))
            result = Q.run_check("text_static", [sys.executable, "-c", "pass"], folder, 5, target)
            self.assertNotEqual(result["status"], "passed")

    def test_native_missing_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); target = folder / "native.json"
            target.write_text(json.dumps({"status": "pass"}))
            result = Q.run_check("native_loading", [sys.executable, "-c", "pass"], folder, 5, target)
            self.assertEqual(result["status"], "failed")

    def test_native_semantic_gaps_remain_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); target = folder / "native.json"
            target.write_text(json.dumps({"status": "pass"}))
            evidence = {"status": "passed_with_semantic_gaps", "entry_count": 10, "semantic_gaps": ["a027/0763#66"]}
            with patch("native_load_validation.validate_file", return_value=evidence):
                result = Q.run_check("native_loading", [sys.executable, "-c", "pass"], folder, 5, target)
                self.assertEqual(result["status"], "incomplete")
                failed = Q.run_check("native_loading", [sys.executable, "-c", "raise SystemExit(1)"], folder, 5, target)
                self.assertEqual(failed["status"], "failed")

    def suite_check(self, source):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            suite = folder / "suite"
            suite.mkdir()
            (suite / "test_sample.py").write_text(source, encoding="utf-8")
            payload = folder / "result.json"
            command = [sys.executable, str(Path(Q.__file__)), "--suite-dir", str(suite),
                       "--suite-result", str(payload)]
            return Q.run_check("tools", command, folder, 10, payload)

    def test_skips_are_reported(self):
        record = self.suite_check("import unittest\nclass T(unittest.TestCase):\n"
                                  " @unittest.skip('optional fixture absent')\n def test_skip(self): pass\n"
                                  " def test_pass(self): self.assertTrue(True)\n")
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["summary"]["tests"], 2)
        self.assertEqual(record["summary"]["skipped"], 1)
        self.assertEqual(record["summary"]["skip_details"][0]["reason"], "optional fixture absent")

    def test_assertion_failure(self):
        record = self.suite_check("import unittest\nclass T(unittest.TestCase):\n"
                                  " def test_fail(self): self.assertEqual(1, 2)\n")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["summary"]["failures"], 1)
        self.assertNotEqual(record["returncode"], 0)

    def test_missing_dependency(self):
        record = self.suite_check("import quality_runner_nonexistent_dependency\n")
        self.assertEqual(record["status"], "unavailable")
        self.assertEqual(record["summary"]["errors"], 1)

    def test_zero_tests_fail(self):
        record = self.suite_check("# no tests\n")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["summary"]["tests"], 0)

    def test_timeout_and_partial_log(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = Q.run_check("slow", [sys.executable, "-c",
                "import time; print('started', flush=True); time.sleep(10)"], folder, .2, folder / "missing.json")
            self.assertEqual(record["status"], "timeout")
            self.assertIsNone(record["returncode"])
            self.assertIn("started", (folder / "slow.log").read_text())

    def test_missing_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Q.run_check("absent", [str(Path(directory) / "no-executable")],
                                 Path(directory), 1, Path(directory) / "result.json")
            self.assertEqual(record["status"], "unavailable")

    def test_zero_qa_and_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            payload = folder / "qa.json"
            for banks, status in ((0, "failed"), (1, "passed")):
                Q.write_json(payload, {"summary": {"banks": banks, "strings_checked": 1,
                                                    "errors": 0, "warnings": 3}})
                record = Q.run_check("qa", [sys.executable, "-c", "pass"], folder, 1, payload)
                self.assertEqual(record["status"], status)
                self.assertEqual(record["summary"]["warnings"], 3)

    def test_process_failure_cannot_be_green(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            payload = folder / "result.json"
            Q.write_json(payload, {"status": "passed", "tests": 1})
            record = Q.run_check("tools", [sys.executable, "-c", "raise SystemExit(2)"], folder, 1, payload)
            self.assertEqual(record["status"], "failed")


class ArtifactReportTests(unittest.TestCase):
    def payload(self):
        return {"status": "passed", "export": {"counts": {"strings": 1}, "problems": []},
                "checks": {"identity": "passed", "export": "passed", "artifact": "passed"},
                "verification": {"roundtrip": "ok"}}

    def test_states_and_false_green(self):
        self.assertEqual(Q.artifact_status(self.payload()), "passed")
        for state in ("failed", "incomplete"):
            self.assertEqual(Q.artifact_status({"status": state}), state)
        for field, value in (("verification", {}), ("checks", {})):
            payload = self.payload()
            payload[field] = value
            self.assertEqual(Q.artifact_status(payload), "failed")
        for value in (0, -1, True, "1"):
            payload = self.payload()
            payload["export"]["counts"]["strings"] = value
            self.assertEqual(Q.artifact_status(payload), "failed")
        payload = self.payload()
        payload["export"]["problems"] = ["fallback"]
        self.assertEqual(Q.artifact_status(payload), "failed")

    def test_failed_reason_and_conflicting_process(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            target = folder / "artifacts.json"
            Q.write_json(target, {"status": "failed", "reason": "stale ROM identity"})
            record = Q.run_check("artifacts", [sys.executable, "-c", "raise SystemExit(1)"], folder, 1, target)
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["reason"], "stale ROM identity")
            Q.write_json(target, self.payload())
            record = Q.run_check("artifacts", [sys.executable, "-c", "raise SystemExit(1)"], folder, 1, target)
            self.assertEqual(record["status"], "failed")


class RuntimeReportTests(unittest.TestCase):
    def payload(self, status="passed", child="completed"):
        payload = {"status": status, "counts": {"selected": 1, "executed": 1,
                "passed": int(status == "passed"), "failed": int(status == "failed"),
                "incomplete": int(status == "incomplete")}, "errors": [],
                "scenarios": {"summary": {"status": status, "memory_status": status, "text_status": "passed",
                    "state_status": "not_configured", "state_expectations": {},
                    "summary_status": "not_configured", "summary_expectations": {},
                    "move_status": "not_configured", "move_expectations": {},
                    "text_evidence_gaps": {"zh": [], "en": []},
                    "coverage": {tag: {"status": "passed", "gaps": [], "scope": "temporal checkpoints"}
                                 for tag in ("zh", "en")}, "findings": [],
                    "runs": {"en": {"status": child, "raw": {"text_copy_checks": 1, "text_probe_errors": [], "text_rejections": []}}, "zh": {"status": "completed", "raw": {"text_copy_checks": 1, "text_probe_errors": [], "text_rejections": []}}}}}}


        identity = {"path": "/synthetic/input", "size": 1, "sha256": "a" * 64}
        roles = ("checker", "manifest", "rom_zh", "rom_en", "helper_rendering", "helper_reproducibility", "save:summary")
        inputs = {role: dict(identity) for role in roles}
        payload["reproducibility"] = Q.REPRO.verify_inputs(inputs, inputs)
        entry = payload['scenarios']['summary']
        entry.update(fixture_integrity=Q.REPRO.verify_inputs({'fixture': dict(identity)}, {'fixture': dict(identity)}),
                     environment_status='passed', rendering_expectations={}, rendering_status='not_configured',
                     rendering_evidence={'status': 'not_configured', 'checkpoints': {}})
        for index, (tag, run) in enumerate(entry['runs'].items()):
            config = '/synthetic/config/' + tag
            run['raw']['environment'] = {
                'schema_version': 1,
                'isolation': {'config_path': config, 'xdg_config_home': config,
                              'config_empty_before_native': True, 'pid': index + 1},
                'native_library': dict(identity),
                'native_version': {'value': None, 'reason': 'py-desmume exposes no version query'},
                'packages': {package: 'synthetic-version' for package in Q.REPRO.PACKAGES},
                'python': 'synthetic-python', 'platform': 'synthetic-platform',
                'settings': dict(Q.REPRO.KNOWN_SETTINGS), 'clock': dict(Q.REPRO.CLOCK)}
        return payload

    def test_runtime_states(self):
        for status in ("passed", "failed", "incomplete"):
            self.assertEqual(Q.runtime_status(self.payload(status)), status)
        self.assertEqual(Q.runtime_status(self.payload("incomplete", "timeout")), "timeout")
        self.assertEqual(Q.runtime_status(self.payload("incomplete", "unavailable")), "unavailable")

    def test_missing_prerequisites(self):
        payload = self.payload("incomplete")
        payload.update(errors=["ROM missing"], scenarios={})
        payload["counts"].update(executed=0, incomplete=0)
        self.assertEqual(Q.runtime_status(payload), "unavailable")

    def test_zero_and_conflicting_counts(self):
        payload = self.payload()
        payload["counts"]["selected"] = 0
        self.assertEqual(Q.runtime_status(payload), "failed")
        payload = self.payload()
        payload["counts"]["passed"] = 0
        with self.assertRaises(ValueError):
            Q.runtime_status(payload)
        payload = self.payload()
        payload["counts"]["executed"] = 0
        self.assertEqual(Q.runtime_status(payload), "failed")
        payload = self.payload()
        for runs in ({}, {"zh": {"status": "completed", "raw": {}}},
                     {"zh": {"status": "completed"}, "en": {"status": "completed"}}):
            payload["scenarios"]["summary"]["runs"] = runs
            self.assertEqual(Q.runtime_status(payload), "failed")

    def test_runtime_record_and_conflicting_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "runtime.json"
            payload = self.payload()
            payload["scenarios"]["summary"]["findings"] = [{"category": "baseline"}]
            Q.write_json(path, payload)
            record = Q.run_check("runtime", [sys.executable, "-c", "pass"], folder, 1, path)
            self.assertEqual(record["status"], "passed")
            self.assertEqual(record["summary"]["findings"], 1)
            record = Q.run_check("runtime", [sys.executable, "-c", "raise SystemExit(2)"], folder, 1, path)
            self.assertEqual(record["status"], "failed")

    def test_aggregate_preserves_nonpass(self):
        for state in ("incomplete", "unavailable", "timeout", "failed"):
            self.assertEqual(Q.aggregate_status(["passed", state]), state)
        self.assertEqual(Q.aggregate_status([]), "failed")
        self.assertEqual(Q.aggregate_status(["incomplete", "failed"]), "failed")

    @unittest.skipUnless(Q.os.name == "posix", "Process groups require POSIX")
    def test_timeout_kills_descendant(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            marker = folder / "child-survived"
            child = "import time; from pathlib import Path; time.sleep(.8); Path(" + repr(str(marker)) + ").touch()"
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); print('spawned',flush=True); time.sleep(10)"
            record = Q.run_check("group", [sys.executable, "-c", parent], folder, .3, folder / "result.json")
            self.assertEqual(record["status"], "timeout")
            self.assertIn("spawned", (folder / "group.log").read_text())
            time.sleep(1)
            self.assertFalse(marker.exists(), "Descendant survived process-group termination")


class RuntimePartyProofTests(unittest.TestCase):
    def payload(self):
        payload = RuntimeReportTests().payload()
        entry = payload['scenarios']['summary']
        entry.update(state_status='passed', party_size=2,
                     state_expectations={'switched': {'relative_to': 'menu', 'order': [1, 0]},
                                         'restored': {'relative_to': 'menu', 'order': [0, 1]}},
                     state_evidence={tag: {'gaps': [], 'mismatches': []} for tag in ('zh', 'en')})
        for run in entry['runs'].values():
            run['raw']['checkpoints'] = {
                name: {'frame': frame, 'party': {'status': 'passed', 'count': 2,
                                                'address': 0x02010000,
                                                'identities': identities}}
                for name, frame, identities in [('menu', 10, [101, 202]),
                                                ('switched', 20, [202, 101]),
                                                ('restored', 30, [101, 202])]}
        return payload

    def test_swap_and_restoration_require_raw_evidence(self):
        self.assertEqual(Q.runtime_status(self.payload()), 'passed')
        for mutation in ('missing', 'unchanged', 'not_restored', 'duplicate', 'wrong_count',
                         'bad_frame', 'invalid_order', 'probe_error', 'missing_pair', 'gap',
                         'bad_address', 'invalid_identity'):
            with self.subTest(mutation=mutation):
                payload = self.payload(); entry = payload['scenarios']['summary']
                shots = entry['runs']['en']['raw']['checkpoints']
                if mutation == 'missing': del shots['switched']['party']
                if mutation == 'unchanged': shots['switched']['party']['identities'] = [101, 202]
                if mutation == 'not_restored': shots['restored']['party']['identities'] = [202, 101]
                if mutation == 'duplicate': shots['menu']['party']['identities'] = [101, 101]
                if mutation == 'wrong_count': shots['menu']['party']['count'] = True
                if mutation == 'bad_frame': shots['switched']['frame'] = 10
                if mutation == 'invalid_order': entry['state_expectations']['switched']['order'] = [0, 0]
                if mutation == 'probe_error': shots['menu']['party']['error'] = 'invalid pointer'
                if mutation == 'missing_pair': del entry['state_evidence']['zh']
                if mutation == 'gap': entry['state_evidence']['en']['gaps'] = ['missing probe']
                if mutation == 'bad_address': shots['menu']['party']['address'] = 0x023FFFFC
                if mutation == 'invalid_identity': shots['menu']['party']['identities'] = [True, 202]
                self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_legacy_and_explicit_state_statuses(self):
        payload = RuntimeReportTests().payload(); entry = payload['scenarios']['summary']
        self.assertEqual(Q.runtime_status(payload), 'passed')
        del entry['state_status']
        self.assertEqual(Q.runtime_status(payload), 'incomplete')
        payload = self.payload(); entry = payload['scenarios']['summary']
        entry['state_status'] = 'failed'
        self.assertEqual(Q.runtime_status(payload), 'failed')
        entry['coverage'] = {}
        self.assertEqual(Q.runtime_status(payload), 'failed')
        entry['state_status'] = 'not_configured'
        self.assertEqual(Q.runtime_status(payload), 'incomplete')


class RuntimeSummaryProofTests(unittest.TestCase):
    def payload(self):
        payload = RuntimeReportTests().payload()
        entry = payload['scenarios']['summary']
        entry.update(summary_status='passed', party_size=2,
                     summary_expectations={'skills_switched': {'since': 'skills', 'slot': 1}},
                     summary_evidence={tag: {'gaps': [], 'mismatches': []} for tag in ('zh', 'en')})
        for run in entry['runs'].values():
            run['raw']['checkpoints'] = {
                'skills': {'frame': 10},
                'skills_switched': {'frame': 20,
                    'party': {'status': 'passed', 'address': 0x02010000, 'count': 2, 'identities': [101, 202]},
                    'summary': {'status': 'passed', 'address': 0x02010000 + 8 + 236,
                                'context_address': 0x02020000, 'party_address': 0x02010000,
                                'screen_address': 0x02030000,
                                'identity': 202, 'slot': 1, 'observed_frame': 15}}}
        return payload

    def test_selection_requires_fresh_owned_identity(self):
        self.assertEqual(Q.runtime_status(self.payload()), 'passed')
        for field, value in [('slot', 0), ('slot', True), ('identity', 101),
                             ('address', 0x02010008), ('party_address', 0x02010004),
                             ('context_address', 0x023FFFF0), ('context_address', 0x02020001),
                             ('screen_address', 0x023FFF00), ('screen_address', None),
                             ('observed_frame', 10), ('observed_frame', 21),
                             ('observed_frame', None), ('status', 'incomplete'), ('error', 'freed')]:
            with self.subTest(field=field, value=value):
                payload = self.payload()
                selection = payload['scenarios']['summary']['runs']['en']['raw']['checkpoints']['skills_switched']['summary']
                selection[field] = value
                self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_missing_and_contradictory_summary_proof(self):
        for mutation in ('missing_pair', 'missing_snapshot', 'bad_party', 'unknown_start', 'gap', 'mismatch'):
            with self.subTest(mutation=mutation):
                payload = self.payload(); entry = payload['scenarios']['summary']
                shots = entry['runs']['en']['raw']['checkpoints']
                if mutation == 'missing_pair': del entry['summary_evidence']['zh']
                if mutation == 'missing_snapshot': del shots['skills_switched']['summary']
                if mutation == 'bad_party': shots['skills_switched']['party']['identities'] = [101, 101]
                if mutation == 'unknown_start': entry['summary_expectations']['skills_switched']['since'] = 'missing'
                if mutation == 'gap': entry['summary_evidence']['en']['gaps'] = ['missing pointer']
                if mutation == 'mismatch': entry['summary_evidence']['en']['mismatches'] = ['skills_switched']
                self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_status_and_failure_precedence(self):
        payload = RuntimeReportTests().payload(); entry = payload['scenarios']['summary']
        self.assertEqual(Q.runtime_status(payload), 'passed')
        del entry['summary_status']
        self.assertEqual(Q.runtime_status(payload), 'incomplete')
        payload = self.payload(); entry = payload['scenarios']['summary']
        entry.update(summary_status='failed', coverage={})
        self.assertEqual(Q.runtime_status(payload), 'failed')
        entry['summary_status'] = 'not_configured'
        self.assertEqual(Q.runtime_status(payload), 'incomplete')


class RuntimeMoveProofTests(unittest.TestCase):
    @staticmethod
    def record(identity, moves, slot):
        # Synthetic encrypted records with shuffle row zero, independent of the
        # production block lookup; no ROM or real Pokemon data is needed.
        import struct
        words = [0] * 64
        words[16:20] = moves
        checksum = sum(words) & 0xFFFF
        seed = checksum
        encoded = []
        for value in words:
            seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
            encoded.append(value ^ (seed >> 16))
        blob = struct.pack('<IHH64H', identity, 0, checksum, *encoded)
        return {'identity': identity, 'checksum': checksum, 'moves': moves,
                'slot': slot, 'address': 0x02010000 + 8 + 236 * slot, 'boxed_hex': blob.hex()}

    def payload(self):
        payload = RuntimeReportTests().payload()
        entry = payload['scenarios']['summary']
        entry.update(move_status='passed', party_size=2,
                     move_expectations={'move_swap': {'relative_to': 'skills', 'slot': 0, 'order': [1, 0, 2, 3]}},
                     move_evidence={tag: {'gaps': [], 'mismatches': []} for tag in ('zh', 'en')})
        for run in entry['runs'].values():
            run['raw']['checkpoints'] = {
                name: {'frame': frame,
                       'party': {'status': 'passed', 'address': 0x02010000, 'count': 2, 'identities': [101, 202]},
                       'moves': {'status': 'passed', 'party_address': 0x02010000, 'observed_frame': frame,
                                 'slots': [self.record(101, moves, 0), self.record(202, [51, 52, 53, 54], 1)]}}
                for name, frame, moves in [('skills', 10, [10, 20, 30, 40]), ('move_swap', 20, [20, 10, 30, 40])]}
        return payload

    def test_copy_decode_and_nontrivial_permutation(self):
        self.assertEqual(Q.runtime_status(self.payload()), 'passed')
        for mutation in ('unchanged', 'other_changed', 'claimed_moves', 'checksum', 'flags', 'truncated',
                         'stale', 'wrong_owner', 'same_moves', 'missing_pair', 'slot_bool', 'no_change_order'):
            with self.subTest(mutation=mutation):
                payload = self.payload(); entry = payload['scenarios']['summary']
                points = entry['runs']['en']['raw']['checkpoints']
                after = points['move_swap']['moves']; record = after['slots'][0]
                if mutation == 'unchanged': after['slots'][0] = self.record(101, [10, 20, 30, 40], 0)
                if mutation == 'other_changed': after['slots'][1] = self.record(202, [52, 51, 53, 54], 1)
                if mutation == 'claimed_moves': record['moves'] = [10, 20, 30, 40]
                if mutation == 'checksum':
                    data = bytearray.fromhex(record['boxed_hex']); data[8] ^= 1; record['boxed_hex'] = data.hex()
                if mutation == 'flags':
                    data = bytearray.fromhex(record['boxed_hex']); data[4] = 2; record['boxed_hex'] = data.hex()
                if mutation == 'truncated': record['boxed_hex'] = record['boxed_hex'][:-2]
                if mutation == 'stale': after['observed_frame'] = 10
                if mutation == 'wrong_owner': record['identity'] = 202
                if mutation == 'same_moves':
                    for point in points.values(): point['moves']['slots'][0] = self.record(101, [10, 10, 30, 40], 0)
                if mutation == 'missing_pair': del entry['move_evidence']['zh']
                if mutation == 'slot_bool': record['slot'] = False
                if mutation == 'no_change_order': entry['move_expectations']['move_swap']['order'] = [0, 1, 2, 3]
                self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_missing_status_and_failure_precedence(self):
        payload = RuntimeReportTests().payload(); entry = payload['scenarios']['summary']
        self.assertEqual(Q.runtime_status(payload), 'passed')
        del entry['move_status']
        self.assertEqual(Q.runtime_status(payload), 'incomplete')
        payload = self.payload(); entry = payload['scenarios']['summary']
        entry.update(move_status='failed', coverage={})
        self.assertEqual(Q.runtime_status(payload), 'failed')

    def test_summary_closure_is_observed_not_inferred_from_moves(self):
        payload = self.payload(); entry = payload['scenarios']['summary']
        entry['move_expectations']['move_swap']['summary_closed'] = True
        for run in entry['runs'].values():
            points = run['raw']['checkpoints']
            points['skills']['summary'] = {'status': 'passed', 'identity': 101, 'address': 0x02010008}
            points['move_swap']['summary'] = {'status': 'incomplete', 'context_address': None,
                                             'screen_address': None, 'observed_frame': -1}
        self.assertEqual(Q.runtime_status(payload), 'passed')
        import copy
        for field, value in [('status', 'passed'), ('screen_address', 0x02030000),
                             ('context_address', 0x02020000), ('observed_frame', 19)]:
            changed = copy.deepcopy(payload)
            changed['scenarios']['summary']['runs']['en']['raw']['checkpoints']['move_swap']['summary'][field] = value
            self.assertEqual(Q.runtime_status(changed), 'incomplete')
        entry['runs']['en']['raw']['checkpoints']['skills']['summary']['identity'] = 202
        self.assertEqual(Q.runtime_status(payload), 'incomplete')


class BufferReportTests(unittest.TestCase):
    def payload(self):
        return {"status": "passed", "capacity": 128, "checked_strings": 791,
                "maximum_stored_units": 120, "findings": [],
                "workspace": {"status": "passed", "checked_strings": 791,
                    "maximum_stored_units": 120, "findings": []}}

    def test_capacity_is_dynamic(self):
        self.assertEqual(Q.buffer_status(self.payload()), "passed")
        payload = self.payload()
        payload["capacity"] = 114
        self.assertEqual(Q.buffer_status(payload), "failed")

    def test_missing_empty_and_contradictory_results(self):
        for key, value in (("checked_strings", 0), ("capacity", 0), ("findings", [{}])):
            payload = self.payload()
            payload[key] = value
            self.assertEqual(Q.buffer_status(payload), "failed")
        payload = self.payload()
        payload["workspace"]["status"] = "failed"
        self.assertEqual(Q.buffer_status(payload), "failed")
        payload = self.payload()
        payload["workspace"]["checked_strings"] = 0
        self.assertEqual(Q.buffer_status(payload), "failed")
        payload = self.payload()
        del payload["workspace"]
        with self.assertRaises(KeyError):
            Q.buffer_status(payload)

    def test_buffer_record_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "buffers.json"
            Q.write_json(path, self.payload())
            record = Q.run_check("buffers", [sys.executable, "-c", "pass"], folder, 1, path)
            self.assertEqual(record["status"], "passed")
            self.assertEqual(record["summary"]["overflows"], 0)
            record = Q.run_check("buffers", [sys.executable, "-c", "raise SystemExit(1)"], folder, 1, path)
            self.assertEqual(record["status"], "failed")


class RuntimeFindingPolicyTests(unittest.TestCase):
    payload = RuntimeReportTests.payload
    def test_findings_cannot_contradict_passing_payload(self):
        for category, expected in (("english_regression", "failed"),
                                   ("baseline_chinese", "incomplete"),
                                   ("baseline_shared", "passed"),
                                   ("prediction", "passed"), ("warning", "passed")):
            payload = self.payload()
            payload["scenarios"]["summary"]["findings"] = [{"category": category}]
            self.assertEqual(Q.runtime_status(payload), expected)


class RuntimeObjectiveProofTests(unittest.TestCase):
    payload = RuntimeReportTests.payload

    def test_memory_success_does_not_prove_objectives(self):
        for coverage in ({}, {"zh": {"status": "passed", "gaps": [], "scope": "checkpoint"}},
                         {tag: {"status": "incomplete", "gaps": ["missing checkpoint"], "scope": "checkpoint"}
                          for tag in ("zh", "en")},
                         {tag: {"status": "passed", "gaps": ["contradictory gap"], "scope": "checkpoint"}
                          for tag in ("zh", "en")},
                         {tag: {"status": "passed", "gaps": [], "scope": ""}
                          for tag in ("zh", "en")}):
            payload = self.payload()
            payload["scenarios"]["summary"]["coverage"] = coverage
            self.assertEqual(Q.runtime_status(payload), "incomplete")

    def test_missing_or_failed_memory_proof(self):
        payload = self.payload()
        del payload["scenarios"]["summary"]["memory_status"]
        self.assertEqual(Q.runtime_status(payload), "incomplete")
        payload["scenarios"]["summary"]["memory_status"] = "failed"
        self.assertEqual(Q.runtime_status(payload), "failed")


class RuntimeTextProofTests(unittest.TestCase):
    payload = RuntimeReportTests.payload

    def test_old_report_missing_text_is_incomplete(self):
        payload = self.payload()
        del payload["scenarios"]["summary"]["text_status"]
        self.assertEqual(Q.runtime_status(payload), "incomplete")

    def test_memory_clean_text_failure_blocks(self):
        payload = self.payload()
        payload["scenarios"]["summary"]["text_status"] = "failed"
        self.assertEqual(Q.runtime_status(payload), "failed")

    def test_one_sided_missing_empty_or_invalid_observations(self):
        for checks in (None, 0, -1, True, "1"):
            payload = self.payload()
            raw = payload["scenarios"]["summary"]["runs"]["en"]["raw"]
            raw["text_copy_checks"] = checks
            self.assertEqual(Q.runtime_status(payload), "incomplete")
        payload = self.payload()
        payload["scenarios"]["summary"]["runs"]["zh"]["raw"]["text_probe_errors"] = ["unsupported source"]
        self.assertEqual(Q.runtime_status(payload), "incomplete")

    def test_no_vacuous_gap_proof(self):
        for gaps in ({}, {"zh": []}, {"zh": [], "en": ["gap"]}):
            payload = self.payload()
            payload["scenarios"]["summary"]["text_evidence_gaps"] = gaps
            self.assertEqual(Q.runtime_status(payload), "incomplete")

    def test_summary_displays_separate_text_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            payload = folder / "runtime.json"
            Q.write_json(payload, self.payload())
            record = Q.run_check("runtime", [sys.executable, "-c", "pass"], folder, 1, payload)
            self.assertEqual(record["summary"]["text_passed"], 1)
            self.assertEqual(record["summary"]["memory_passed"], 1)
            self.assertEqual(record["summary"]["coverage_passed"], 1)


class RuntimeMalformedEvidenceTests(unittest.TestCase):
    payload = RuntimeReportTests.payload

    def test_malformed_containers_fail_without_aborting_runner(self):
        mutations = (
            lambda p: p.update(scenarios=[]),
            lambda p: p['scenarios'].update(summary=1),
            lambda p: p['scenarios']['summary']['runs'].update(en=1),
            lambda p: p['scenarios']['summary'].update(findings=['bad']),
            lambda p: p['scenarios']['summary'].update(findings=[{'category': []}]),
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            target = folder / 'runtime.json'
            for mutation in mutations:
                payload = self.payload()
                mutation(payload)
                Q.write_json(target, payload)
                record = Q.run_check('runtime', [sys.executable, '-c', 'pass'], folder, 1, target)
                self.assertEqual(record['status'], 'failed')
                self.assertIn('invalid result payload', record['reason'])

    def test_malformed_coverage_is_incomplete(self):
        for value in (None, [], {'en': 1, 'zh': 1}):
            payload = self.payload()
            payload['scenarios']['summary']['coverage'] = value
            self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_raw_rejection_cannot_be_hidden_by_passing_summary(self):
        event = {'caller': 123, 'capacity': 5, 'item': 232, 'item_caller': 456}
        payload = self.payload()
        entry = payload['scenarios']['summary']
        entry['runs']['en']['raw']['text_rejections'] = [event]
        self.assertEqual(Q.runtime_status(payload), 'failed')
        entry['coverage'] = {}
        self.assertEqual(Q.runtime_status(payload), 'failed')

    def test_raw_rejection_baseline_policy_is_preserved(self):
        event = {'caller': 123, 'capacity': 5, 'units': 6}
        payload = self.payload()
        entry = payload['scenarios']['summary']
        entry['runs']['zh']['raw']['text_rejections'] = [event]
        self.assertEqual(Q.runtime_status(payload), 'incomplete')
        entry['runs']['en']['raw']['text_rejections'] = [event]
        self.assertEqual(Q.runtime_status(payload), 'passed')

    def test_missing_or_malformed_raw_rejections_cannot_pass(self):
        for value in (None, {}, [1], [{'caller': True, 'capacity': 5, 'units': 6}]):
            payload = self.payload()
            payload['scenarios']['summary']['runs']['en']['raw']['text_rejections'] = value
            self.assertEqual(Q.runtime_status(payload), 'incomplete')


class RuntimeHardeningGateTests(unittest.TestCase):
    payload = RuntimeReportTests.payload

    def test_missing_reproducibility_and_environment_cannot_pass(self):
        mutations = (
            lambda p, e: p.pop('reproducibility'),
            lambda p, e: p['reproducibility']['before'].pop('helper_rendering'),
            lambda p, e: e.pop('fixture_integrity'),
            lambda p, e: e.pop('environment_status'),
            lambda p, e: e['runs']['en']['raw'].pop('environment'),
            lambda p, e: e['runs']['en']['raw']['environment']['isolation'].update(pid=e['runs']['zh']['raw']['environment']['isolation']['pid']),
        )
        for mutate in mutations:
            payload = self.payload()
            mutate(payload, payload['scenarios']['summary'])
            self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_fixture_proof_must_match_fullrun_input(self):
        payload = self.payload()
        fixture = payload['scenarios']['summary']['fixture_integrity']
        for phase in ('before', 'after'):
            fixture[phase]['fixture']['path'] = '/synthetic/unrelated'
        self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_missing_rendering_declaration_cannot_pass(self):
        for field in ('rendering_status', 'rendering_expectations', 'rendering_evidence'):
            payload = self.payload()
            del payload['scenarios']['summary'][field]
            self.assertEqual(Q.runtime_status(payload), 'incomplete')

    def test_known_failure_survives_missing_provenance(self):
        payload = self.payload()
        del payload['reproducibility']
        payload['scenarios']['summary']['text_status'] = 'failed'
        self.assertEqual(Q.runtime_status(payload), 'failed')

    def test_rendering_rechecks_pixels_and_preserves_failure(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory(dir=Q.RENDER.BUILD_ROOT) as folder:
            payload = self.payload()
            entry = payload['scenarios']['summary']
            entry['rendering_expectations'] = {'open': {'profile': Q.RENDER.PROFILE, 'since': 'boot', 'item': 232, 'heap': 6}}
            for tag in ('zh', 'en'):
                path = str(Path(folder) / (tag + '.png'))
                image = Image.new('RGB', Q.RENDER.SIZE, (144, 144, 152))
                draw = ImageDraw.Draw(image)
                draw.rectangle((40, 148, 45, 154), fill=(0, 0, 0))
                draw.rectangle((46, 148, 51, 154), fill=(248, 248, 248))
                image.save(path)
                entry['runs'][tag]['raw']['checkpoints'] = {
                    'boot': {'frame': 10},
                    'open': {'frame': 30, 'screenshot': path,
                             'item_description_reads': [{'frame': 20, 'item': 232, 'heap': 6}]}}
            entry['rendering_evidence'] = Q.RENDER.evaluate(entry['rendering_expectations'], entry['runs'])
            entry['rendering_status'] = 'passed'
            self.assertEqual(Q.runtime_status(payload), 'passed')
            path = entry['runs']['en']['raw']['checkpoints']['open']['screenshot']
            Image.new('RGB', Q.RENDER.SIZE, (144, 144, 152)).save(path)
            # A stale passing label and unrelated missing evidence cannot hide a fresh blank.
            del payload['reproducibility']
            self.assertEqual(Q.runtime_status(payload), 'failed')
            Path(path).unlink()
            self.assertEqual(Q.runtime_status(payload), 'incomplete')
