"""Synthetic expansion proofs; no game data or ROM writes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text_expansion_check as check


def replacement(maximum, **changes):
    return dict(semantics="replace", max_units=maximum, recursive=False,
                evidence="synthetic formatter contract", **changes)


class ExpansionTests(unittest.TestCase):
    def test_formatter_guard_does_not_grant_message_bounds(self):
        data = b'synthetic engine'
        guards = {'test': (100, 100 + len(data), hashlib.sha256(data).hexdigest())}
        with patch.object(check, 'FORMATTER_GUARDS', guards):
            result = check.inspect_formatter_engine(data, 100)
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(result['message_bounds'], {})
            self.assertIn('slot_producers_and_expanded_bounds', result['required_proofs'])
            self.assertEqual(check.inspect_formatter_engine(data[:-1], 100)['status'], 'incomplete')
            self.assertIsNone(check.inspect_formatter_engine(b'X' + data[1:], 100)['semantics'])

    def test_plain_exact_and_one_over_capacity(self):
        measured = check.measure_expansion([1] * 7 + [0xffff])
        self.assertEqual(measured["expanded_units"], 8)
        self.assertEqual(check.check_capacity(measured, 8)["status"], "passed")
        self.assertEqual(check.check_capacity(measured, 7)["excess_units"], 1)

    def test_padding_stored_but_not_expanded(self):
        measured = check.measure_expansion([1, 0xffff, 0xffff])
        self.assertEqual(measured["stored_units"], 3)
        self.assertEqual(measured["expanded_units"], 2)

    def test_repeated_maximum_placeholders(self):
        units = [1, 0xfffe, 0x103, 1, 0, 0xfffe, 0x103, 1, 0, 0xffff]
        measured = check.measure_expansion(units, {0x103: replacement(7)})
        self.assertEqual(measured["expanded_units"], 16)
        self.assertEqual(check.check_capacity(measured, 15)["status"], "failed")

    def test_exact_args_and_full_command_kind(self):
        units = [0xfffe, 0x103, 1, 4, 0xffff]
        for bounds in ({3: replacement(7)}, {0x103: replacement(7, args=[2])}):
            self.assertEqual(check.measure_expansion(units, bounds)["status"], "incomplete")
        self.assertEqual(check.measure_expansion(units, {0x103: replacement(7, args=[4])})["expanded_units"], 8)

    def test_unknown_numeric_and_battle_commands_not_guessed(self):
        for kind in (0x100, 0x132, 0x400, 0x3400, 0xff01):
            measured = check.measure_expansion([0xfffe, kind, 0, 0xffff])
            self.assertEqual(measured["status"], "incomplete")
            self.assertIsNone(measured["expanded_units"])
            self.assertEqual(check.check_capacity(measured, 99999)["status"], "incomplete")

    def test_retained_controls_count_their_full_record(self):
        spec = dict(semantics="retain", recursive=False, evidence="synthetic control copy")
        measured = check.measure_expansion([0xfffe, 0xff01, 1, 100, 0xe000, 0xffff], {0xff01: spec})
        self.assertEqual(measured["expanded_units"], 6)

    def test_bad_bound_never_passes(self):
        for field, value in (("evidence", ""), ("recursive", True), ("semantics", "pixels"),
                             ("max_units", -1), ("max_units", 7.5), ("max_units", True)):
            spec = replacement(7)
            spec[field] = value
            measured = check.measure_expansion([0xfffe, 0x103, 0, 0xffff], {0x103: spec})
            self.assertEqual(measured["status"], "incomplete")

    def test_compressed_literal_independent_fixture(self):
        # Three 9-bit symbols 1, 2, 3 in a 15-bit payload stream, then ones.
        bits = 1 | (2 << 9) | (3 << 18) | (0x1ff << 27)
        units = [0xf100, bits & 0x7fff, (bits >> 15) & 0x7fff, 0xffff]
        measured = check.measure_expansion(units)
        self.assertEqual(measured["status"], "passed")
        self.assertEqual(measured["expanded_units"], 4)
        self.assertTrue(measured["compressed"])

    def test_invalid_records_fail(self):
        for units in ([], [1], [0xfffe, 0x103], [0xfffe, 0x103, 99, 0xffff],
                      [0xf100, 0], [1, 0xffff, 3], [True, 0xffff], [-1, 0xffff]):
            self.assertEqual(check.measure_expansion(units)["status"], "failed", units)

    def test_invalid_capacity(self):
        for capacity in (0, -1, True, 4.5):
            with self.assertRaises(ValueError):
                check.check_capacity(check.measure_expansion([0xffff]), capacity)


if __name__ == "__main__":
    unittest.main()
