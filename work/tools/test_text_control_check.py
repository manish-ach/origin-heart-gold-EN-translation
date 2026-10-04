import unittest
import text_control_check as t


def cmd(op, *args):
    return [65534, op, len(args), *args]


def message(*parts):
    return sum(([p] if isinstance(p, int) else p for p in parts), []) + [65535]


class ControlTests(unittest.TestCase):
    def check(self, source, target, **kw):
        return t.check_controls(source, target, 'synthetic/0000#0', **kw)

    def test_plain_layout_changes_pass(self):
        self.assertEqual(self.check(message(1, 0xE000, 2), message(3, 0x25BD, 4))['status'], 'passed')

    def test_unsupported_arity_incomplete(self):
        s = message(cmd(0x0101, 0))
        result = self.check(s, s)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['gaps'][0]['code'], 'command_arity_unproven')

    def test_unknown_opcode_incomplete(self):
        s = message(cmd(0x7777, 1))
        self.assertEqual(self.check(s, s)['status'], 'incomplete')

    def test_missing_variable_fails(self):
        r = self.check(message(cmd(0x0101, 0)), message(1))
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['findings'][0]['code'], 'substitution_contract_changed')

    def test_variable_args_and_multiplicity_preserved(self):
        for candidate in [message(cmd(0x0101, 1)), message(cmd(0x0101, 0), cmd(0x0101, 0))]:
            self.assertEqual(self.check(message(cmd(0x0101, 0)), candidate)['status'], 'failed')

    def test_valid_variable_reordering(self):
        a, b = cmd(0x0101, 0), cmd(0x0107, 1)
        r = self.check(message(a, b), message(b, 0xE000, a), contracts={
            0x0101: {'argc': 1, 'evidence': 'synthetic handler'},
            0x0107: {'argc': 1, 'evidence': 'synthetic handler'}})
        self.assertEqual(r['status'], 'passed')

    def test_stateful_order_preserved(self):
        a, b = cmd(0xFF00, 1), cmd(0xFF00, 2)
        self.assertEqual(self.check(message(a, b), message(b, a))['status'], 'failed')

    def test_variable_cannot_cross_color_boundary(self):
        a, b = cmd(0x0101, 0), cmd(0xFF00, 1)
        r = self.check(message(a, b), message(b, a))
        self.assertEqual(r['findings'][0]['code'], 'substitution_crossed_control_boundary')

    def test_reordering_across_restored_color_is_valid(self):
        a, color, reset = cmd(0x0101, 0), cmd(0xFF00, 1), cmd(0xFF00, 0)
        r = self.check(message(a, color, 1, reset), message(color, 2, reset, a))
        self.assertFalse(r['findings'])

    def test_reordering_across_wait_still_fails(self):
        a, wait = cmd(0x0101, 0), cmd(0x0202, 1)
        r = self.check(message(a, wait), message(wait, a))
        self.assertEqual(r['findings'][0]['code'], 'substitution_crossed_control_boundary')

    def test_malformed_argc(self):
        r = self.check(message(cmd(0x0101, 0)), [65534, 0x0101, 9, 0, 65535])
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['findings'][0]['code'], 'command_arguments_overrun')

    def test_known_arity(self):
        r = self.check(message(cmd(0x0101, 0)), message(cmd(0x0101, 0, 0)),
                       contracts={0x0101: {'argc': 1, 'evidence': 'synthetic handler'}})
        self.assertTrue(any(x['code'] == 'command_arity_mismatch' for x in r['findings']))

    def test_reference_contract(self):
        contract = {0x7777: {'argc': 1, 'evidence': 'synthetic handler',
                            'references': [{'arg': 0, 'count': 3, 'evidence': 'synthetic inventory'}]}}
        r = self.check(message(cmd(0x7777, 2)), message(cmd(0x7777, 3)), contracts=contract)
        self.assertTrue(any(x['code'] == 'reference_out_of_range' for x in r['findings']))

    def test_existing_reference_defect_is_baseline(self):
        contract = {0x7777: {'argc': 1, 'evidence': 'synthetic handler',
                            'references': [{'arg': 0, 'count': 3, 'evidence': 'synthetic inventory'}]}}
        s = message(cmd(0x7777, 3))
        r = self.check(s, s, contracts=contract)
        self.assertEqual(r['status'], 'incomplete')
        self.assertEqual(r['baseline_findings'][0]['code'], 'reference_out_of_range')
        self.assertFalse(r['findings'])

    def test_compressed_empty_and_plain(self):
        self.assertEqual(self.check([0xF100, 65535], message(1))['status'], 'passed')

    def test_compressed_opaque_incomplete(self):
        s = [0xF100, 0x8001, 65535]
        self.assertEqual(self.check(s, s)['status'], 'incomplete')
        self.assertEqual(self.check(message(1), s)['status'], 'failed')

    def test_terminator_as_command_argument(self):
        s = message(cmd(0x0101, 65535))
        self.assertEqual(self.check(s, s)['counts']['source_commands'], 1)

    def test_terminator_required(self):
        self.assertEqual(self.check(message(1), [1])['status'], 'failed')

    def test_bad_u16(self):
        for value in [-1, 65536, True, 'a']:
            self.assertEqual(self.check(message(1), [value, 65535])['status'], 'failed')

    def test_empty_summary_incomplete(self):
        self.assertEqual(t.summarize([])['status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
