"""Synthetic images only: no game pixels or text fixtures."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_rendering as R


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=R.BUILD_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.config = {'open': {'profile': R.PROFILE, 'since': 'boot', 'item': 232, 'heap': 6}}
        self.runs = {}
        for language in ('zh', 'en'):
            path = str(Path(self.tmp.name) / (language + '.png'))
            self.make(path)
            self.runs[language] = {'raw': {'checkpoints': {'boot': {'frame': 10}, 'open': {'frame': 30, 'screenshot': path, 'item_description_reads': [{'frame': 20, 'item': 232, 'heap': 6}]}}}}

    def make(self, path, blank=False, size=R.SIZE):
        im = Image.new('RGB', size, (144, 144, 152))
        if not blank:
            draw = ImageDraw.Draw(im)
            draw.rectangle((40, 148, 45, 154), fill=(0, 0, 0))
            draw.rectangle((46, 148, 51, 154), fill=(248, 248, 248))
        im.save(path)

    def point(self, lang='en'):
        return self.runs[lang]['raw']['checkpoints']['open']

    def test_present_and_hash(self):
        proof = R.evaluate(self.config, self.runs)
        self.assertEqual(proof['status'], 'passed')
        self.assertEqual(len(proof['checkpoints']['open']['evidence']['en']['sha256']), 64)

    def test_english_only_blank(self):
        self.make(self.point()['screenshot'], blank=True)
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'failed')

    def test_shared_or_chinese_blank_incomplete(self):
        self.make(self.point('zh')['screenshot'], blank=True)
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')
        self.make(self.point()['screenshot'], blank=True)
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_bad_files(self):
        path = self.point()['screenshot']
        for data in (b'bad', b'x' * (R.MAX_BYTES + 1)):
            Path(path).write_bytes(data)
            self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')
        self.make(path, size=(512, 768))
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')
        Path(path).unlink()
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_fifo_rejected_without_open(self):
        path = Path(self.tmp.name) / 'pipe.png'
        os.mkfifo(path)
        self.point()['screenshot'] = str(path)
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_unknown_palette_and_alpha(self):
        path = self.point()['screenshot']
        for color in ((0, 0, 0, 255), (144, 144, 152, 0)):
            Image.new('RGBA', R.SIZE, color).save(path)
            self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_invalid_context(self):
        original = copy.deepcopy(self.runs)
        for field, value in [('item', True), ('item', 437), ('heap', 7), ('frame', 10), ('frame', 31), ('frame', True)]:
            with self.subTest(field=field, value=value):
                self.runs = copy.deepcopy(original)
                self.point()['item_description_reads'][-1][field] = value
                self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_last_request_and_missing_pair(self):
        self.point()['item_description_reads'].append({'item': 437, 'heap': 6, 'frame': 25})
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')
        del self.runs['en']
        self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_independent_revalidation(self):
        proof = R.evaluate(self.config, self.runs)
        entry = {'rendering_expectations': self.config, 'runs': self.runs,
                 'rendering_evidence': proof, 'rendering_status': proof['status']}
        self.assertEqual(R.evidence_status(entry), 'passed')
        self.make(self.point()['screenshot'], blank=True)
        self.assertEqual(R.evidence_status(entry), 'incomplete')

    def test_outside_build_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'outside.png'
            self.make(path)
            self.point()['screenshot'] = str(path)
            self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')
            link = Path(self.tmp.name) / 'link.png'
            link.symlink_to(path)
            self.point()['screenshot'] = str(link)
            self.assertEqual(R.evaluate(self.config, self.runs)['status'], 'incomplete')

    def test_strict_config(self):
        for value in (None, [], {'open': {}}, {'open': dict(self.config['open'], item=True)}, {'open': dict(self.config['open'], profile='generic')}, {'open': dict(self.config['open'], since='open')}):
            self.assertEqual(R.evaluate(value, self.runs)['status'], 'incomplete')
        self.assertEqual(R.evaluate({}, self.runs)['status'], 'not_configured')


if __name__ == '__main__':
    unittest.main()
