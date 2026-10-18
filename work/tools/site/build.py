"""Rebuild the website content from the game data and the guide, then build and check the site.

    python3 work/tools/site/build.py            # data + guide + PDF + astro build + link check
    python3 work/tools/site/build.py --content  # only regenerate site/src/data and site/src/content (what CI can't do)
    python3 work/tools/site/build.py --check    # exit 1 if generated content is out of date (for pre-commit)
    python3 work/tools/site/build.py --content --rom release:v1.0.0-rc9   # at a release: document that release

The ROM is only needed for the data step; CI builds from the committed site/src content. --rom (default
release:latest, see work/tools/docs/romdata.py "choosing the ROM") goes to gen_docs.py and export_data.py.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
SITE = os.path.join(REPO, 'site')
PY = sys.executable


def run(cmd, cwd=REPO):
    print('$', ' '.join(cmd))
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode:
        sys.exit(r.returncode)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--content', action='store_true', help='only regenerate the site content')
    ap.add_argument('--check', action='store_true', help='fail if the generated content is stale')
    ap.add_argument('--rom', help='the ROM the docs and the data describe (default: release:latest)')
    a = ap.parse_args(argv)
    flag = ['--check'] if a.check else []
    rom = ['--rom', a.rom] if a.rom else []
    # the guide first: it writes the old-link map export_data.py points quest links through
    run([PY, 'work/tools/site/sync_guide.py'] + flag)
    run([PY, 'work/tools/docs/gen_docs.py'] + flag + rom)
    run([PY, 'work/tools/site/export_data.py'] + flag + rom)
    if a.content or a.check:
        return 0
    if shutil.which('pandoc') and shutil.which('typst'):
        run([PY, 'work/tools/site/build_pdf.py'])
    else:
        print('pandoc/typst not found: skipping the PDF')
    if not os.path.isdir(os.path.join(SITE, 'node_modules')):
        run(['npm', 'ci'], cwd=SITE)
    run(['npx', 'astro', 'build'], cwd=SITE)
    run([PY, 'work/tools/site/check_site.py', '--base', os.environ.get('GUIDE_BASE', '/')])
    return 0


if __name__ == '__main__':
    sys.exit(main())
