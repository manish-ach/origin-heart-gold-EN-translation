"""Turn a website build into the redirect site for the OLD project address.

The website moved from https://originheartgold.github.io/origin-heart-gold-EN-translation/ to the host root
https://originheartgold.github.io/ (repo originheartgold/originheartgold.github.io). The old address is still
served by this repo's GitHub Pages; the site workflow deploys this redirect site there so old links keep working.

    python3 work/tools/site/redirect_site.py --dist site/dist --out <dir> \\
        --new-url https://originheartgold.github.io/ --old-base /origin-heart-gold-EN-translation/

For the build in --dist (production at the root, the tester preview in its preview/ folder):
- every HTML page becomes a stub at the same relative path: canonical link to the new URL, noindex, an instant
  meta refresh, a location.replace() that keeps the query and #anchor, and a visible link;
- 404.html sends any other old path to the same path at the new address (query and #anchor kept);
- every other file (patch, PDF, patch tool, save editor, licences, JSON) is copied unchanged, so old download
  links keep working. Build internals (_astro/, pagefind/, sitemaps, robots.txt) are left out.

Exit 1 when --dist has no index.html or a copied file is too big for GitHub Pages.
"""
import argparse
import html
import json
import os
import shutil
import sys
import urllib.parse

MAX_FILE = 95 * 1024 * 1024  # GitHub Pages refuses files over 100 MB
SKIP_DIRS = {'_astro', 'pagefind'}  # page assets and the search index: only the real pages use them
SKIP_FILES = {'robots.txt', '.nojekyll'}


def skipped(rel):
    parts = rel.split('/')
    name = parts[-1]
    return (any(p in SKIP_DIRS for p in parts[:-1]) or name in SKIP_FILES
            or (name.startswith('sitemap') and name.endswith('.xml')))


def page_url(new_url, rel):
    """faq/index.html -> <new>/faq/, index.html -> <new>, other.html -> <new>/other.html."""
    if rel == 'index.html':
        rel = ''
    elif rel.endswith('/index.html'):
        rel = rel[:-len('index.html')]
    return new_url + urllib.parse.quote(rel, safe='/')


def script_json(value):
    """A JSON string that is safe inside an inline <script>."""
    return json.dumps(value).replace('</', '<\\/')


def stub(target):
    t = html.escape(target, quote=True)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Origin HeartGold has moved</title>
<meta name="robots" content="noindex">
<link rel="canonical" href="{t}">
<script>location.replace({script_json(target)} + location.search + location.hash);</script>
<meta http-equiv="refresh" content="0; url={t}">
</head>
<body>
<p>The Origin HeartGold website has moved. This page is now at <a href="{t}">{t}</a>.</p>
</body>
</html>
'''


def not_found(new_url, old_base):
    home = html.escape(new_url, quote=True)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Origin HeartGold has moved</title>
<meta name="robots" content="noindex">
<script>
(function () {{
  var base = {script_json(old_base)}, path = location.pathname;
  var rest = path.indexOf(base) === 0 ? path.slice(base.length) : path.replace(/^\\/+/, '');
  location.replace({script_json(new_url)} + rest + location.search + location.hash);
}})();
</script>
<noscript><meta http-equiv="refresh" content="0; url={home}"></noscript>
</head>
<body>
<p>The Origin HeartGold website has moved to <a href="{home}">{home}</a>.</p>
</body>
</html>
'''


def build(dist, out, new_url, old_base):
    """Write the redirect site for the build in dist to out. Returns (stubs, copied files, copied bytes)."""
    if not new_url.endswith('/'):
        new_url += '/'
    old_base = '/' + old_base.strip('/') + '/' if old_base.strip('/') else '/'
    if not os.path.isfile(os.path.join(dist, 'index.html')):
        raise SystemExit(f'{dist} has no index.html; build the site first')
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f'{out} is not empty; pass a new folder')
    stubs = copied = size = 0
    for root, dirs, files in os.walk(dist):
        dirs.sort()
        for name in sorted(files):
            src = os.path.join(root, name)
            rel = os.path.relpath(src, dist).replace(os.sep, '/')
            if skipped(rel):
                continue
            dst = os.path.join(out, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if name.endswith('.html'):
                if name == '404.html':
                    continue    # the one 404.html at the top of out handles every unknown path
                with open(dst, 'w', encoding='utf-8') as f:
                    f.write(stub(page_url(new_url, rel)))
                stubs += 1
            else:
                n = os.path.getsize(src)
                if n > MAX_FILE:
                    raise SystemExit(f'{rel} is {n} bytes, too big for GitHub Pages')
                shutil.copyfile(src, dst)
                copied += 1
                size += n
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, '404.html'), 'w', encoding='utf-8') as f:
        f.write(not_found(new_url, old_base))
    return stubs, copied, size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dist', required=True, help='the website build (production, with preview/ inside if any)')
    ap.add_argument('--out', required=True, help='a new, empty folder for the redirect site')
    ap.add_argument('--new-url', required=True, help='the new site address, e.g. https://originheartgold.github.io/')
    ap.add_argument('--old-base', required=True, help='the old base path, e.g. /origin-heart-gold-EN-translation/')
    a = ap.parse_args(argv)
    stubs, copied, size = build(a.dist, a.out, a.new_url, a.old_base)
    print(f'{stubs} redirect pages, {copied} files copied ({size / 1048576:.1f} MB), 404.html -> {a.new_url}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
