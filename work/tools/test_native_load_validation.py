import copy
import unittest
from native_load_validation import validate, units_digest


class NativeEvidenceTests(unittest.TestCase):
    def fixture(self):
        ref = 'a027/0000#0'; signature = units_digest([42])
        state = {'heap': 0x2200000, 'used_blocks': [], 'largest_free': 1000}
        report = dict(expected_count=1, expected_refs=[ref],
            records=[dict(ref=ref, actual_units=1, actual_sha256=signature, expected_units=1,
                          expected_sha256=signature, terminator=65535, capacity=2, native_call_completed=True, stored_actual_units=1, stored_actual_sha256=signature,
                          stored_expected_units=1, stored_expected_sha256=signature, decompression_called=False, semantic_units=1, semantic_gap=None)],
            lifecycles=[dict(narc=27, bank=0, before=state, after=copy.deepcopy(state))],
            archive_paths_observed={'27': 'a/0/2/7', '277': 'battle/string/battle_string.narc'},
            stress=[dict(handles=2, reads=6, bank_refs=[[27,0],[277,0]], before=state, after=copy.deepcopy(state))],
            errors=[], allocation_failures=[], null_writes=[], heap_table_errors=[], heap_checks=4,
            code_guards_passed=True, source_unchanged=True, script_unchanged=True, save_unchanged=True, reference_unchanged=True, semantic_gaps=[])
        return report, {ref: (1, signature, 1, signature, False, 1, signature)}

    def test_complete_evidence(self):
        report, expected = self.fixture()
        self.assertEqual(validate(report, expected)['status'], 'pass')

    def test_missing_duplicate_or_changed_output_rejected(self):
        for mutation in ('missing', 'duplicate', 'wrong_output', 'no_native_call'):
            with self.subTest(mutation=mutation):
                report, expected = self.fixture()
                if mutation == 'missing': report['records'] = []
                if mutation == 'duplicate': report['records'] *= 2
                if mutation == 'wrong_output': report['records'][0]['actual_sha256'] = '0'*64
                if mutation == 'no_native_call': report['records'][0]['native_call_completed'] = False
                report['status'] = 'pass'; report['coverage_complete'] = True
                self.assertEqual(validate(report, expected)['status'], 'fail')

    def test_leak_cannot_be_hidden_by_summary(self):
        report, expected = self.fixture()
        report['lifecycles'][0]['after']['largest_free'] -= 16
        report['lifecycles'][0]['balanced'] = True
        self.assertEqual(validate(report, expected)['status'], 'fail')

    def test_semantic_gap_is_never_an_unqualified_pass(self):
        report, expected = self.fixture()
        ref = next(iter(expected)); data = list(expected[ref]); data[5] = 2; expected[ref] = tuple(data)
        self.assertEqual(validate(report, expected)['status'], 'fail')
        report['records'][0].update(semantic_units=2, semantic_gap='embedded terminator')
        report['semantic_gaps'] = [{'ref': ref}]
        self.assertEqual(validate(report, expected)['status'], 'passed_with_semantic_gaps')

    def test_missing_instrumentation_rejected(self):
        for key in ('heap_checks', 'allocation_failures', 'code_guards_passed', 'stress'):
            report, expected = self.fixture(); report.pop(key)
            with self.subTest(key=key): self.assertEqual(validate(report, expected)['status'], 'fail')


if __name__ == '__main__': unittest.main()
