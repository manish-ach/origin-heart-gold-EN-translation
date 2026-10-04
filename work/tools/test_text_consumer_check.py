import unittest
import text_consumer_check as t
import msgtool


class ConsumerTests(unittest.TestCase):
    def contract(self, **kwargs):
        return dict(id='synthetic', bank='a027/0000', ids=None, stage='stored', capacity_units=8,
                    evidence_level='rom_guarded', **kwargs)

    def test_exact_capacity_includes_terminal(self):
        self.assertEqual(t.check_entries([[1]*7+[65535]], self.contract())[0]['status'], 'passed')

    def test_one_unit_over_capacity(self):
        self.assertEqual(t.check_entries([[1]*8+[65535]], self.contract())[0]['status'], 'failed')

    def test_missing_terminator_incomplete(self):
        self.assertEqual(t.check_entries([[1]*7], self.contract())[0]['status'], 'incomplete')

    def test_compressed_measurement_distinguishes_stages(self):
        units = msgtool.compress_codes([1]*10)
        self.assertLess(t.measure_units(units, 'stored'), t.measure_units(units, 'decompressed'))
        self.assertEqual(t.measure_units(units, 'decompressed'), 11)

    def test_command_expansion_not_guessed(self):
        with self.assertRaises(ValueError):
            t.measure_units([msgtool.CODE_CMD,0x100,1,0,65535], 'decompressed')

    def test_missing_required_id_incomplete(self):
        contract=self.contract(); contract['ids']=[1]
        self.assertEqual(t.check_entries([[65535]], contract)[0]['status'], 'incomplete')

    def test_guard_exact_and_mutation(self):
        base, raw = t.ARM_GUARDS['copy']; data=bytearray.fromhex(raw)
        t.validate_guards(data,base,['copy'])
        data[0]^=1
        with self.assertRaises(ValueError): t.validate_guards(data,base,['copy'])

    def test_guard_truncation(self):
        base, raw=t.ARM_GUARDS['copy']
        with self.assertRaises(ValueError): t.validate_guards(bytes.fromhex(raw)[:-1],base,['copy'])


if __name__ == '__main__': unittest.main()
