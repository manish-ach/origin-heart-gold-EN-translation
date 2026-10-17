"""official_species.json stays consistent with the game data; no ROM required."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import species_comparisons as C

VALID_TYPES = set(C.TYPES) - {'???'} | {'Fairy'}


class OfficialSpeciesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, species = C.load()
        cls.by_slug = {s['slug']: s for s in species}

    def test_parse_personal_reorders_speed_and_merges_single_type(self):
        raw = bytes([45, 49, 49, 45, 65, 65, 12, 12])
        self.assertEqual(C.parse_personal(raw), ([45, 49, 49, 65, 65, 45], ['Grass']))
        with self.assertRaises(ValueError):
            C.parse_personal(bytes(7))

    def test_later_changes_apply_by_stat_name(self):
        stats, types, source = C.official_from_rom('pikachu', [35, 55, 30, 50, 40, 90], ['Electric'])
        self.assertEqual(stats, [35, 55, 40, 50, 50, 90])
        self.assertIn('Generation VI', source)
        self.assertEqual(C.official_from_rom('clefable', [95, 70, 73, 85, 90, 60], ['Normal'])[1], ['Fairy'])

    def test_entries_are_well_formed_and_still_differ(self):
        for slug, entry in self.data['species'].items():
            with self.subTest(slug=slug):
                self.assertIn(slug, self.by_slug)
                if 'comparedWith' in entry:
                    self.assertIn(entry['comparedWith'], self.by_slug)
                    continue
                self.assertEqual(len(entry['stats']), 6)
                self.assertTrue(all(isinstance(v, int) and 1 <= v <= 255 for v in entry['stats']))
                self.assertTrue(entry['types'] and set(entry['types']) <= VALID_TYPES)
                self.assertTrue(entry['source'])
                # An entry equal to the hack would be a stale row on the change pages.
                self.assertTrue(C.differs(entry, self.by_slug[slug]), 'same as the hack: remove the entry')

    def test_known_values(self):
        species = self.data['species']
        self.assertEqual(sum(species['farfetchd']['stats']), 377)
        self.assertEqual(species['blastoise']['types'], ['Water'])
        self.assertEqual(species['crystal-onix']['comparedWith'], 'onix')


if __name__ == '__main__':
    unittest.main()
