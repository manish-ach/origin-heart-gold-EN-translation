import unittest
from text_reference_check import compare_references

class ReferenceTests(unittest.TestCase):
    def run_case(self, **changes):
        args = dict(source_scripts=[b'a'], candidate_scripts=[b'a'], source_map=[(0,0)], candidate_map=[(0,0)],
                    source_std=[(0,0)], candidate_std=[(0,0)], source_counts=[2], candidate_counts=[2])
        args.update(changes)
        return compare_references(**args)
    def test_preservation_does_not_prove_dynamic_safety(self):
        result = self.run_case()
        self.assertEqual(result['preservation_status'], 'passed')
        self.assertEqual(result['status'], 'incomplete')
    def test_mutated_script_mapping_or_inventory_fails(self):
        for change in ({'candidate_scripts':[b'b']}, {'candidate_map':[(0,1)]},
                       {'candidate_std':[(0,1)]}, {'candidate_counts':[1]}):
            self.assertEqual(self.run_case(**change)['status'], 'failed')
    def test_original_invalid_mapping_is_baseline(self):
        r=self.run_case(source_map=[(0,9)],candidate_map=[(0,9)])
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(len(r['baseline_findings']),1)
    def test_empty_inventory_incomplete(self):
        self.assertEqual(self.run_case(source_counts=[],candidate_counts=[])['preservation_status'],'incomplete')
