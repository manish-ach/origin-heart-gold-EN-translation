"""Check the built website (site/dist/): every internal link and #anchor must resolve.

    (cd site && npx astro build) && python3 work/tools/site/check_site.py
    python3 work/tools/site/check_site.py --jargon   # also count developer jargon in guide, trainer and location pages

Exit 1 when a link or anchor is broken.
"""
import argparse
import collections
import html
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
DIST = os.path.join(REPO, 'site', 'dist')

HREF = re.compile(r'<a\b[^>]*\bhref="([^"]+)"')
ID = re.compile(r'\bid="([^"]+)"')
# Player-facing text should not need these. Hidden technical references (class="tech") are excluded.
JARGON = [('coordinate', re.compile(r'≈\d+,\d+')), ('flag', re.compile(r'\bflag \d+')),
          ('var', re.compile(r'\bvar 0x[0-9a-fA-F]+')), ('script file', re.compile(r'\b(?:script )?files? \d+')),
          ('line ref', re.compile(r'\bL\d{3,}\b')), ('map id', re.compile(r'\bmap \d+')),
          ('decision id', re.compile(r'\bD-\d{4}\b'))]


def pages(base):
    for root, _dirs, files in os.walk(DIST):
        for f in files:
            if f.endswith('.html'):
                path = os.path.join(root, f)
                rel = '/' + os.path.relpath(path, DIST).replace(os.sep, '/')
                rel = rel[:-len('index.html')] if rel.endswith('/index.html') else rel
                yield base.rstrip('/') + rel, path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default='/', help='the site base path the build used (GUIDE_BASE)')
    ap.add_argument('--jargon', action='store_true')
    a = ap.parse_args(argv)
    if not os.path.isdir(DIST):
        print('no build at site/dist; run `npx astro build` in site/ first')
        return 2
    ids, links, text = {}, [], {}
    for url, path in pages(a.base):
        h = open(path, encoding='utf-8').read()
        ids[url] = set(ID.findall(h))
        for href in HREF.findall(h):
            links.append((url, html.unescape(href)))
        if a.jargon and any(k in url for k in ('/guide/', '/trainers/', '/locations/')):
            body = re.sub(r'<details class="tech"[^>]*>.*?</details>|<span class="tech"[^>]*>.*?</span>', '', h, flags=re.S)
            body = re.sub(r'<(script|style)\b.*?</\1>', '', body, flags=re.S)
            text[url] = html.unescape(re.sub(r'<[^>]+>', ' ', body))
    broken = collections.defaultdict(list)
    for src, href in links:
        if re.match(r'^[a-z]+:', href) or href.startswith('//'):
            continue
        target = urllib.parse.urljoin(src, href)
        p = urllib.parse.urlparse(target)
        path = urllib.parse.unquote(p.path)
        if not path.endswith('/') and not os.path.splitext(path)[1]:
            path += '/'
        if os.path.splitext(path)[1] and path not in ids:
            if os.path.exists(os.path.join(DIST, path[len(a.base.rstrip('/')):].lstrip('/'))):
                continue
        if path not in ids:
            broken[src].append(href + '  (no page)')
        elif p.fragment and urllib.parse.unquote(p.fragment) not in ids[path]:
            broken[src].append(href + '  (no anchor)')
    n = sum(len(v) for v in broken.values())
    for src in sorted(broken):
        print(src)
        for b in sorted(set(broken[src]))[:20]:
            print('   ', b)
    print('%d pages, %d links checked, %d broken' % (len(ids), len(links), n))
    if a.jargon:
        tot = collections.Counter()
        per = collections.Counter()
        for url, t in text.items():
            for name, rx in JARGON:
                c = len(rx.findall(t))
                tot[name] += c
                per[url] += c
        print('developer jargon in guide, trainer and location pages (outside the Technical source boxes):')
        for name, _ in JARGON:
            print('  %-12s %d' % (name, tot[name]))
        for url, c in per.most_common(15):
            if c:
                print('  %4d  %s' % (c, url))
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
