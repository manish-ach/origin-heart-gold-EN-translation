"""Chapter hidden-item references: source coverage, caveats and safe generation."""
from pathlib import Path
import unittest

import chapters
import sync_guide as guide


class HiddenItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = guide.hidden_item_sections((Path(guide.GUIDE) / 'hidden-items.md').read_text())

    def test_all_locations_are_referenced_and_all_chapter_links_resolve(self):
        linked = set()
        for chapter in chapters.load():
            guide.chapter_hidden_items(chapter, self.sections)
            linked.update(chapter.get('hidden_items', []))
        self.assertEqual(linked, set(self.sections))
        self.assertNotIn('Missing screenshots', linked)

    def test_counts_include_spots_without_screenshots(self):
        self.assertEqual(sum(s['count'] for s in self.sections.values()), 210)
        self.assertEqual(sum(s['missing'] for s in self.sections.values()), 6)
        self.assertEqual(self.sections['Celadon City']['count'], 1)
        self.assertEqual(self.sections['Celadon City']['missing'], 1)

    def test_unknown_or_duplicate_locations_fail_generation(self):
        for names in (['Typo City'], ['Pewter City', 'Pewter City']):
            with self.subTest(names=names), self.assertRaises(SystemExit):
                guide.chapter_hidden_items({'_file': 'example.toml', 'hidden_items': names}, self.sections)

    def test_empty_chapter_has_no_disclosure(self):
        self.assertEqual(guide.chapter_hidden_items({}, self.sections), [])

    def test_native_disclosure_preserves_links_and_caveats_through_mdx(self):
        chapter = {'_file': 'example.toml', 'hidden_items': ['Celadon City', 'Diglett’s Cave']}
        text = '\n'.join(guide.chapter_hidden_items(chapter, self.sections))
        self.assertNotIn(' open', text)
        self.assertNotIn('<img', text)
        self.assertIn('(1 without screenshots)', text)
        for source in (text, guide.escape_mdx(text)):
            page = guide.rewrite_links(source, 1, {}, [])
            self.assertIn('(../hidden-items/#digletts-cave)', page)
            self.assertIn('(../hidden-items/#celadon-city)', page)
            self.assertIn('(../hidden-items/)', page)


if __name__ == '__main__':
    unittest.main()
