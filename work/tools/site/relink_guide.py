"""Point links to the old region pages (/guide/<region>/#quest) at the chapter pages.

The guide used to be one page per region; it is now one page per chapter (guide/chapters/*.toml). sync_guide.py
writes site/src/generated/guide_legacy.json (old page -> chapter, per anchor), and old URLs still forward in the
browser, but links inside the site should go straight to the chapter. This rewrites them in the committed sources
and data (the ROM-based exporters can't be rerun in CI). Idempotent.

    python3 work/tools/site/relink_guide.py           # rewrite
    python3 work/tools/site/relink_guide.py --check   # list files that still hold an old link, exit 1 if any
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
LEGACY = os.path.join(REPO, 'site', 'src', 'generated', 'guide_legacy.json')
ROOTS = ['site/src/data', 'site/src/content/docs', 'site/src/pages', 'site/src/components', 'site/src/lib',
         'work/tools/site', 'work/tools/docs', 'work/docs']
SKIP_DIRS = {'guide', 'generated', '__pycache__', 'node_modules'}  # src/content/docs/guide is generated
EXT = ('.json', '.md', '.mdx', '.astro', '.mjs', '.py', '.ts')
LINK = re.compile(r'((?:\.\./|\./|/)?(?:[A-Za-z0-9_.-]+/)*?guide/)([a-z0-9-]+)/(#[^\s)"\'\\<>]*)?')


def rewrite(text, legacy):
    def repl(m):
        slug = m.group(2)
        if slug not in legacy:
            return m.group(0)
        anchor = (m.group(3) or '')[1:]
        entry = legacy[slug]
        chapter = entry['anchors'].get(anchor, entry['default']) if anchor else entry['default']
        return '%s%s/%s' % (m.group(1), chapter, ('#' + anchor) if anchor in entry['anchors'] else (m.group(3) or ''))
    return LINK.sub(repl, text)


def main(argv):
    legacy = json.load(open(LEGACY, encoding='utf-8'))
    check = '--check' in argv
    dirty = []
    for root in ROOTS:
        for d, dirs, files in os.walk(os.path.join(REPO, root)):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(EXT) or fn == 'relink_guide.py' or fn == 'quest_ledger.json':
                    continue
                path = os.path.join(d, fn)
                text = open(path, encoding='utf-8').read()
                new = rewrite(text, legacy)
                if new != text:
                    dirty.append(os.path.relpath(path, REPO))
                    if not check:
                        with open(path + '.tmp', 'w', encoding='utf-8') as fh:
                            fh.write(new)
                        os.replace(path + '.tmp', path)
    for p in dirty:
        print(('old guide link in: ' if check else 'rewrote: ') + p)
    return 1 if (check and dirty) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
