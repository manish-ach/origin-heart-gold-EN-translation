import unittest
from text_safety_check import apply_capacities, assess_record
from text_expansion_check import measure_expansion

class SafetyTests(unittest.TestCase):
    def contract(self, **extra):
        return dict(bank='a027/0000', ids=None, capacity_units=3, stage='stored',
                    evidence_level='rom_guarded', status='passed', **extra)
    def test_exact_and_one_over(self):
        c=self.contract()
        for units,status in [([1,2,65535],'passed'),([1,2,3,65535],'failed')]:
            self.assertEqual(apply_capacities(units,measure_expansion(units),[c],'a027/0000',0)[0]['status'],status)
    def test_known_consumer_does_not_certify_other_consumers(self):
        r=assess_record([1,65535],[2,65535],'a027/0000#0',[self.contract()])
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(r['capacity'][0]['status'],'passed')
    def test_unmapped_text_is_accounted_incomplete(self):
        r=assess_record([1,65535],[2,65535],'a027/0001#0',[self.contract()])
        self.assertIn('no_capacity_contract',r['gaps'])
    def test_missing_guard_cannot_pass(self):
        c=self.contract();c['status']='incomplete'
        self.assertEqual(apply_capacities([1,65535],measure_expansion([1,65535]),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_unknown_variable_cannot_fit_by_stored_length(self):
        c=self.contract();c['stage']='expanded'
        u=[65534,256,1,0,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_policy_overflow_detected_without_promoting_policy_fit(self):
        c=self.contract();c.update(status='incomplete',evidence_level='policy_only')
        for u,status in [([1,65535],'incomplete'),([1,2,3,65535],'failed')]:
            self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],status)
    def test_decoded_command_needs_expansion_contract(self):
        c=self.contract();c['stage']='decompressed'
        u=[65534,256,1,0,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_removed_variable_fails_even_when_capacity_unknown(self):
        r=assess_record([65534,256,1,0,65535],[2,65535],'a027/0001#0',[])
        self.assertEqual(r['status'],'failed')

    def test_missing_guard_status_is_incomplete(self):
        c=self.contract();del c['status']
        u=[1,65535]
        self.assertEqual(apply_capacities(u,measure_expansion(u),[c],'a027/0000',0)[0]['status'],'incomplete')
    def test_inherited_overflow_is_explicit_not_new_bug(self):
        u=[1,2,3,65535]
        r=assess_record(u,u,'a027/0000#0',[self.contract()])
        self.assertEqual(r['status'],'incomplete')
        self.assertTrue(r['capacity'][0]['inherited'])
