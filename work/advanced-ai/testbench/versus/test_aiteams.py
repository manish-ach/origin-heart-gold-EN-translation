"""Unit tests of versus/aiteams.py's trainer names (no emulator, no ROM).

  .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/versus -p 'test_*.py'

Our build stores five long trainer names in bank 719 as keys ('T00017', work/tools/trainer_display.py, D-2487) and draws
the full name from ITCM. A team label must show the full name the game shows, never the key.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import aiteams  # noqa: E402

sys.path.append(aiteams.TOOLS)
import trainer_display  # noqa: E402


def workspace_rows():
    with open(os.path.join(aiteams.WORKSPACE, 'a027', '0719.json'), encoding='utf-8') as f:
        return {r['id']: r for r in json.load(f)['strings']}


class FullNames(unittest.TestCase):
    def bank(self, n=800):
        """A made-up bank 719: 'Name <id>', with the build's keys at the five full-name ids."""
        names = ['Name %d' % i for i in range(n)]
        for i in trainer_display.IDS:
            names[i] = trainer_display.key(i)
        return names

    def test_keys_become_the_workspace_full_names(self):
        rows = workspace_rows()
        got = aiteams.full_names(self.bank())
        for i in sorted(trainer_display.IDS):
            self.assertEqual(got[i], rows[i]['en'])
            self.assertFalse(got[i].startswith('T000'), got[i])
            self.assertGreater(len(got[i]), 10)       # the reason they are keys: longer than the bank's limit

    def test_other_names_stay(self):
        names = self.bank()
        got = aiteams.full_names(names)
        self.assertEqual([n for i, n in enumerate(got) if i not in trainer_display.IDS],
                         [n for i, n in enumerate(names) if i not in trainer_display.IDS])

    def test_a_bank_without_keys_is_unchanged(self):
        names = ['Name %d' % i for i in range(800)]       # the Spanish rc44, our rc8 release
        self.assertIs(aiteams.full_names(names), names)

    def test_a_key_at_another_id_is_left_alone(self):
        names = ['Name %d' % i for i in range(800)]
        names[18] = trainer_display.key(17)                # not this id's key: a name like any other
        self.assertEqual(aiteams.full_names(names)[18], 'T00017')

    def test_a_key_without_a_full_name_fails(self):
        with tempfile.TemporaryDirectory() as ws:
            os.makedirs(os.path.join(ws, 'a027'))
            rows = [r for i, r in sorted(workspace_rows().items()) if i != 59]
            with open(os.path.join(ws, 'a027', '0719.json'), 'w', encoding='utf-8') as f:
                json.dump({'strings': rows}, f)
            with self.assertRaises(KeyError) as e:
                aiteams.full_names(self.bank(), workspace=ws)
            self.assertIn('T00059', str(e.exception))

    def test_trainer_name_shows_the_full_name(self):
        names = self.bank()
        t = {'headers': [bytes(20)] * len(names), 'names': aiteams.full_names(names)}
        label = aiteams.trainer_name(t, 17)
        self.assertNotIn('T000', label)
        self.assertTrue(label.endswith(workspace_rows()[17]['en']), label)


if __name__ == '__main__':
    unittest.main()
