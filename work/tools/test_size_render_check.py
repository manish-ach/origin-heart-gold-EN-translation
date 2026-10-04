import unittest
from size_render_check import case_text,pages,SENTINEL,prepare_cases,render_text
class SizeHarnessTests(unittest.TestCase):
    def test_preserves_production_prefix_and_waits_on_sentinel(self):
        source='{VAR:FF01:200}A{VAR:FF01:100}{SCROLL}{VAR:FF01:200}B{VAR:FF01:100}'
        actual=case_text(source)
        self.assertTrue(actual.startswith(source))
        self.assertEqual(pages(actual),[source.split('{SCROLL}')[0],source.split('{SCROLL}')[1],SENTINEL])
        self.assertTrue(actual.endswith('{SCROLL}'))
    def test_does_not_inject_reset_that_masks_leak(self):
        actual=case_text('{VAR:FF01:200}Broken')
        self.assertNotIn('{VAR:FF01:100}',actual)
    def test_no_extra_blank_page_after_existing_wait(self):
        self.assertEqual(pages(case_text('A{SCROLL}')),['A',SENTINEL])
    def test_preserves_original_newline_negative_control(self):
        source='{VAR:FF01:200}A{NEWLINE}B{VAR:FF01:100}'
        self.assertEqual(pages(case_text(source))[0],source)
    def test_ui_name_variant_keeps_separate_printer_lifecycle(self):
        source={'ref':'a027/0302#26','en':'{VAR:FF01:200}Team {VAR:0103:0}!{SCROLL}','ends_in_enlarged_size':True}
        exact,variant=prepare_cases([source],'extra')
        for item in (exact,variant):
            self.assertTrue(item['ui_case'])
            self.assertEqual((item['harness_font'],item['native_width']),(1,216))
            self.assertNotIn(SENTINEL,render_text(item))
            self.assertNotIn('{VAR:FF01:100}',render_text(item))
        self.assertIn('WWWWWWW',variant['en'])
        self.assertNotIn('ui_case',source)
    def test_unknown_unreset_consumer_is_not_assumed_safe(self):
        with self.assertRaises(ValueError):
            prepare_cases([{'ref':'a027/0616#37','en':'{VAR:FF01:200}A','ends_in_enlarged_size':True}],'extra')
    def test_normal_name_variant_still_requires_normal_sentinel(self):
        source={'ref':'a027/0048#5','en':'{VAR:FF01:200}{VAR:0103:0}{VAR:FF01:100}','ends_in_enlarged_size':False}
        variant=prepare_cases([source],'extra')[0]
        self.assertFalse(variant.get('ui_case',False))
        self.assertIn(SENTINEL,render_text(variant))
if __name__=='__main__':unittest.main()
