"""Build the printable quest guide (PDF) from guide/*.md with Pandoc and Typst.

    python3 work/tools/site/build_pdf.py                 # -> site/public/downloads/origin-heartgold-guide.pdf
    python3 work/tools/site/build_pdf.py --out guide.pdf

Same source as the website. The PDF leaves out the "Technical source" notes (they stay on the site)
and turns links between chapters into links inside the PDF. Needs `pandoc` (3.x) and `typst` on PATH.
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
GUIDE = os.path.join(REPO, 'guide')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chapters as chapters_mod  # noqa: E402
OUT = os.path.join(REPO, 'site', 'public', 'downloads', 'origin-heartgold-guide.pdf')
SITE_URL = os.environ.get('GUIDE_PUBLIC_URL', '')

TEMPLATE_HEADER = r'''
#set page(paper: "a4", margin: (x: 2cm, y: 2.2cm), numbering: "1",
  header: context { if counter(page).get().first() > 2 [ #set text(8pt, fill: luma(120)); Origin HeartGold · Quest guide #h(1fr) #counter(page).display() ] })
#set text(font: ("Noto Sans", "Helvetica Neue", "Arial", "PingFang SC", "Noto Sans CJK SC"), size: 9.5pt, lang: "en")
#set par(justify: false, leading: 0.6em)
#show heading.where(level: 1): it => { pagebreak(weak: true); block(below: 1em, text(20pt, weight: "bold", fill: rgb("#8c6400"), it.body)) }
#show heading.where(level: 2): it => block(above: 1.4em, below: 0.6em, sticky: true, text(12pt, weight: "bold", it.body))
#show link: it => text(fill: rgb("#8c6400"), it)
#show table: set text(8.5pt)
#show table.cell: set align(left)
'''


def chapters():
    """Guide files that are plain pages and go after the chapters (the quest files only supply quest entries)."""
    files = [f for f in sorted(os.listdir(GUIDE)) if f == '08-ruins-of-alph-silver.md']
    return files + (['known-issues.md'] if os.path.exists(os.path.join(GUIDE, 'known-issues.md')) else [])


def quest_blocks():
    """quest id -> its Markdown entry (H2 to the next H2), read from the numbered guide files."""
    blocks = {}
    for fn in sorted(os.listdir(GUIDE)):
        if not re.match(r'^\d+-.*\.md$', fn) or fn == '08-ruins-of-alph-silver.md':
            continue
        cur = None
        for ln in open(os.path.join(GUIDE, fn), encoding='utf-8').read().split('\n'):
            if ln.startswith('## '):
                cur = [ln]
                continue
            if cur is None:
                continue
            m = re.match(r'^<!--\s*quest:.*?\bid=(q-\d+).*-->\s*$', ln.strip())
            if m and len(cur) <= 2:
                blocks[m.group(1)] = cur
                QUEST_FILE[m.group(1)] = fn
            cur.append(ln)
    return {k: '\n'.join(v) for k, v in blocks.items()}


def chapter_markdown(ch, blocks):
    """One chapter file -> Markdown: title, intro, walkthrough, then its quest entries."""
    out = ['# ' + ch['title'], '', ch['intro'].strip(), '']
    if ch['steps']:
        out += ['## Walkthrough', '']
        for st in ch['steps']:
            out += [st['text'].strip(), '']
            if st.get('unlocks'):
                out += ['Opens up:', ''] + ['- ' + QUEST_TITLES[q] for q in st['unlocks']] + ['']
            if st.get('closes'):
                out += ['**Warning: this closes for good:**', ''] + ['- ' + QUEST_TITLES[q] for q in st['closes']] + ['']
    for q in ch['quests']:
        out += [blocks[q['id']].rstrip('\n'), '']
        extra = [x for x in (q.get('available_note'), q.get('level_note')) if x]
        if extra:
            out += ['*' + ' '.join(extra) + '*', '']
    return '\n'.join(out)


def gh_slug(s):
    s = s.strip().lower()
    s = re.sub(r'[^\w\- ]', '', s, flags=re.UNICODE)
    return s.replace(' ', '-')


def prepare(fn, text):
    """One chapter -> Markdown for the combined document."""
    lines = text.rstrip('\n').split('\n')
    out, skip = [], False
    for ln in lines:
        if re.match(r'^\[← Guide index\]\(README\.md\)\s*$', ln):
            continue
        if ln.strip() == '**Quests on this page:**':
            skip = True
            continue
        if skip:
            if ln.startswith('- ') or not ln.strip():
                continue
            skip = False
        if re.match(r'^\*Sources?:\*', ln):
            continue
        if re.match(r'^<!--\s*quest:.*-->\s*$', ln.strip()):
            continue  # quest metadata for the website (see sync_guide.py)
        out.append(ln)
    md = '\n'.join(out)
    # chapter links: (03-x.md#anchor) -> (#anchor); (03-x.md) -> (#chapter-title)
    def repl(m):
        target, anchor = m.group(1), m.group(2)
        if anchor:
            return '](%s)' % anchor
        return '](#%s)' % CHAPTER_IDS.get(target, '')
    md = re.sub(r'\]\(((?:\d+-[a-z0-9-]+|known-issues|README)\.md)(#[^)]*)?\)', repl, md)
    # links to the website's reference pages, "[Move tutors](/tutors/)": an absolute link to the
    # published site when GUIDE_PUBLIC_URL is set, otherwise just the link text.
    if SITE_URL:
        md = re.sub(r'\]\(/(?!/)([^)\s]*)\)', lambda m: '](%s%s)' % (SITE_URL.rstrip('/') + '/', m.group(1)), md)
    else:
        md = re.sub(r'\[([^\]]*)\]\(/(?!/)[^)\s]*\)', r'\1', md)
    return md


CHAPTER_IDS = {}
QUEST_TITLES = {}
QUEST_FILE = {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args(argv)
    for tool in ('pandoc', 'typst'):
        if not shutil.which(tool):
            print('missing %s on PATH' % tool)
            return 2
    parts = []
    for fn in chapters():
        t = open(os.path.join(GUIDE, fn), encoding='utf-8').read()
        m = re.match(r'# (.+)', t)
        CHAPTER_IDS[fn] = gh_slug(m.group(1)) if m else ''
    intro = open(os.path.join(GUIDE, 'README.md'), encoding='utf-8').read()
    intro_par = '\n\n'.join(p for p in intro.split('\n\n')[1:4] if not p.startswith('#'))
    today = datetime.date.today().isoformat()
    title = ['---', 'title: "Origin HeartGold — Quest Guide"',
             'subtitle: "起源心金 v4.0.3 · English · side quests, puzzles and easy-to-miss events"',
             'date: "%s"' % today, '---', '',
             intro_par, '',
             ('The full guide, with the Pokédex, every location, items, trainers and move tutors, is online at <%s>. '
              'Report mistakes there.' % SITE_URL) if SITE_URL else '', '']
    blocks = quest_blocks()
    for q, text in blocks.items():
        QUEST_TITLES[q] = text.split('\n')[0][3:].strip()
    for ch in chapters_mod.load():
        for q in ch['quests']:  # a link to a whole region file goes to the first chapter that holds one of its quests
            CHAPTER_IDS.setdefault(QUEST_FILE[q['id']], gh_slug(ch['title']))
    for ch in chapters_mod.load():
        parts.append(prepare('chapter', chapter_markdown(ch, blocks)))
    for fn in chapters():
        parts.append(prepare(fn, open(os.path.join(GUIDE, fn), encoding='utf-8').read()))
    md = '\n'.join(title) + '\n\n' + '\n\n'.join(parts) + '\n'
    # An in-document link needs a heading to land on. Targets that only exist on the website (HTML widgets such as
    # the Forest of Time route viewer) have no heading in the PDF: keep the link text, drop the link.
    ids = {gh_slug(m.group(1)) for m in re.finditer(r'^#{1,6} (.+)$', md, flags=re.M)}
    md = re.sub(r'\[([^\]]*)\]\(#([^)\s]+)\)', lambda m: m.group(0) if m.group(2) in ids else m.group(1), md)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'guide.md')
        hdr = os.path.join(tmp, 'header.typ')
        open(src, 'w', encoding='utf-8').write(md)
        open(hdr, 'w', encoding='utf-8').write(TEMPLATE_HEADER)
        cmd = ['pandoc', src, '-f', 'gfm+yaml_metadata_block', '-o', a.out, '--pdf-engine=typst',
               '--toc', '--toc-depth=1', '--resource-path=' + GUIDE, '-H', hdr, '-V', 'papersize=a4']
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-3000:])
            return r.returncode
    print('wrote', os.path.relpath(a.out, REPO), '(%d KB)' % (os.path.getsize(a.out) // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
