"""Redirect site for the old project address (redirect_site.py); synthetic build, no ROM required."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import redirect_site

NEW = 'https://originheartgold.github.io/'
OLD = '/origin-heart-gold-EN-translation/'


class RedirectSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dist = os.path.join(self.tmp.name, 'dist')
        self.out = os.path.join(self.tmp.name, 'out')
        files = {
            'index.html': '<h1>Home</h1>', 'faq/index.html': '<h1>FAQ</h1>', '404.html': 'not found',
            'pokemon/flabébé/index.html': 'x', 'preview/index.html': 'p', 'preview/faq/index.html': 'p',
            'preview/404.html': 'p', 'patch/latest.json': '{}', 'patch/OHG.xdelta': 'VCD',
            'downloads/guide.pdf': '%PDF', 'patch-tool/worker.js': 'js', '_astro/page.css': 'css',
            'pagefind/index.json': '{}', 'preview/_astro/a.js': 'js', 'sitemap-index.xml': '<x/>',
            'sitemap-0.xml': '<x/>', 'robots.txt': 'User-agent: *', '.nojekyll': '',
        }
        for rel, text in files.items():
            path = os.path.join(self.dist, *rel.split('/'))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, rel):
        with open(os.path.join(self.out, *rel.split('/')), encoding='utf-8') as f:
            return f.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.out, *rel.split('/')))

    def test_pages_become_stubs(self):
        stubs, copied, _size = redirect_site.build(self.dist, self.out, NEW, OLD)
        self.assertEqual(stubs, 5)
        self.assertEqual(copied, 4)
        faq = self.read('faq/index.html')
        self.assertIn('<link rel="canonical" href="https://originheartgold.github.io/faq/">', faq)
        self.assertIn('<meta name="robots" content="noindex">', faq)
        self.assertIn('<meta http-equiv="refresh" content="0; url=https://originheartgold.github.io/faq/">', faq)
        self.assertIn('location.replace("https://originheartgold.github.io/faq/" + location.search + location.hash)',
                      faq)
        self.assertIn('<a href="https://originheartgold.github.io/faq/">', faq)
        self.assertIn('href="https://originheartgold.github.io/"', self.read('index.html'))
        self.assertIn('href="https://originheartgold.github.io/pokemon/flab%C3%A9b%C3%A9/"',
                      self.read('pokemon/flabébé/index.html'))

    def test_preview_follows_to_the_new_preview(self):
        redirect_site.build(self.dist, self.out, NEW, OLD)
        self.assertIn('href="https://originheartgold.github.io/preview/faq/"', self.read('preview/faq/index.html'))
        self.assertFalse(self.exists('preview/404.html'))

    def test_downloads_copied_and_internals_left_out(self):
        redirect_site.build(self.dist, self.out, NEW, OLD)
        self.assertEqual(self.read('patch/OHG.xdelta'), 'VCD')
        self.assertEqual(self.read('downloads/guide.pdf'), '%PDF')
        self.assertEqual(self.read('patch-tool/worker.js'), 'js')
        self.assertEqual(self.read('patch/latest.json'), '{}')
        for rel in ('_astro/page.css', 'pagefind/index.json', 'preview/_astro/a.js', 'sitemap-index.xml',
                    'sitemap-0.xml', 'robots.txt', '.nojekyll'):
            self.assertFalse(self.exists(rel), rel)

    def test_404_maps_any_old_path(self):
        redirect_site.build(self.dist, self.out, NEW.rstrip('/'), OLD.strip('/'))
        page = self.read('404.html')
        self.assertIn('var base = "/origin-heart-gold-EN-translation/"', page)
        self.assertIn('location.replace("https://originheartgold.github.io/" + rest + location.search + location.hash)',
                      page)
        self.assertIn('<meta name="robots" content="noindex">', page)
        self.assertNotIn('not found', page)

    def test_refuses_unbuilt_or_reused_folders(self):
        os.remove(os.path.join(self.dist, 'index.html'))
        with self.assertRaises(SystemExit):
            redirect_site.build(self.dist, self.out, NEW, OLD)
        os.makedirs(os.path.join(self.tmp.name, 'used'))
        open(os.path.join(self.tmp.name, 'used', 'x'), 'w').close()
        with open(os.path.join(self.dist, 'index.html'), 'w') as f:
            f.write('home')
        with self.assertRaises(SystemExit):
            redirect_site.build(self.dist, os.path.join(self.tmp.name, 'used'), NEW, OLD)

    def test_script_strings_cannot_close_the_script(self):
        self.assertNotIn('</script>', redirect_site.script_json('a</script>b'))


if __name__ == '__main__':
    unittest.main()
