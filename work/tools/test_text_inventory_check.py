import copy
import json
from pathlib import Path
import tempfile
import unittest

import msgtool as m
from text_inventory_check import check_inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cm = m.Charmap()
        self.cm.enc = {'A': 1, 'B': 2}
        self.cm.dec = {1: 'A', 2: 'B'}
        self.original = m.encrypt_bank(7, [[1, 0xffff], [2, 0xffff]])
        self.source = {'test': [self.original]}
        self.candidate = copy.deepcopy(self.source)
        self.export = m.bank_to_json(0, self.original, self.cm)
        self.save()

    def save(self):
        directory = self.root / 'test'
        directory.mkdir(exist_ok=True)
        (directory / '0000.json').write_text(json.dumps(self.export))

    def check(self):
        self.save()
        return check_inventory(self.source, self.candidate, self.root, self.cm)

    def test_valid(self):
        self.assertEqual(self.check()['status'], 'passed')

    def test_changed_text_matches_export(self):
        self.export['strings'][0]['text'] = 'BB'
        self.candidate['test'][0] = m.json_to_bank(self.export, self.cm)
        self.assertEqual(self.check()['status'], 'passed')

    def test_compressed_export(self):
        self.export['strings'][0]['text'] = '{COMPRESSED}AB'
        self.candidate['test'][0] = m.json_to_bank(self.export, self.cm)
        self.assertEqual(self.check()['status'], 'passed')

    def test_export_id_mutations(self):
        baseline = copy.deepcopy(self.export)
        for ids in ([0], [0, 0], [1, 0], [0, 1, 2], [False, 1]):
            with self.subTest(ids=ids):
                self.export = copy.deepcopy(baseline)
                self.export['strings'] = [{'id': i, 'text': 'A'} for i in ids]
                self.assertEqual(self.check()['status'], 'failed')

    def test_bank_id(self):
        self.export['bank'] = True
        self.assertEqual(self.check()['status'], 'failed')

    def test_extra_bank(self):
        (self.root / 'test' / '0001.json').write_text('{}')
        self.assertEqual(self.check()['status'], 'failed')

    def test_missing_bank(self):
        (self.root / 'test' / '0000.json').unlink()
        result = check_inventory(self.source, self.candidate, self.root, self.cm)
        self.assertEqual(result['status'], 'failed')

    def test_extra_archive(self):
        (self.root / 'surprise').mkdir()
        self.assertEqual(self.check()['status'], 'failed')

    def test_candidate_bank_count(self):
        for banks in ([], [self.original, self.original]):
            self.candidate['test'] = banks
            self.assertEqual(self.check()['status'], 'failed')

    def test_candidate_string_count(self):
        self.candidate['test'][0] = m.encrypt_bank(7, [[1, 0xffff]])
        self.assertEqual(self.check()['status'], 'failed')

    def test_export_mismatch(self):
        self.export['strings'][0]['text'] = 'B'
        self.assertEqual(self.check()['status'], 'failed')

    def test_opaque_bank_preserved_but_incomplete(self):
        self.source['test'] = [b'bad']
        self.candidate = copy.deepcopy(self.source)
        self.export = m.bank_to_json(0, b'bad', self.cm)
        self.assertEqual(self.check()['status'], 'incomplete')
        self.candidate['test'][0] = b'new'
        self.assertEqual(self.check()['status'], 'failed')

    def test_opaque_string(self):
        # An embedded terminator cannot round trip through the text representation.
        raw = m.encrypt_bank(7, [[1, 0xffff, 2]])
        self.source['test'] = [raw]
        self.candidate['test'] = [raw]
        self.export = m.bank_to_json(0, raw, self.cm)
        self.assertIn('raw_hex', self.export['strings'][0])
        self.assertEqual(self.check()['status'], 'incomplete')
        self.export['strings'][0]['text'] = 'B'
        self.candidate['test'][0] = m.json_to_bank(self.export, self.cm)
        self.assertEqual(self.check()['status'], 'failed')

    def test_workspace_chinese_and_inventory(self):
        workspace = self.root / 'workspace'
        (workspace / 'test').mkdir(parents=True)
        obj = {'bank': 0, 'strings': [{'id': 0, 'zh': 'A'}, {'id': 1, 'zh': 'B'}]}
        path = workspace / 'test' / '0000.json'
        # Export and workspace have separate roots in real use.
        export_root = self.root / 'export'
        (export_root / 'test').mkdir(parents=True)
        (export_root / 'test' / '0000.json').write_text(json.dumps(self.export))
        path.write_text(json.dumps(obj))
        self.assertEqual(check_inventory(self.source, self.candidate, export_root, self.cm, workspace)['status'], 'passed')
        obj['strings'][0]['zh'] = 'B'
        path.write_text(json.dumps(obj))
        self.assertEqual(check_inventory(self.source, self.candidate, export_root, self.cm, workspace)['status'], 'failed')
        # A redaction marker (zh_redact.py) counts as the original only when its hash matches.
        import zh_redact
        obj['strings'][0]['zh'] = zh_redact.marker('A')
        path.write_text(json.dumps(obj))
        self.assertEqual(check_inventory(self.source, self.candidate, export_root, self.cm, workspace)['status'], 'passed')
        obj['strings'][0]['zh'] = zh_redact.marker('B')
        path.write_text(json.dumps(obj))
        self.assertEqual(check_inventory(self.source, self.candidate, export_root, self.cm, workspace)['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
