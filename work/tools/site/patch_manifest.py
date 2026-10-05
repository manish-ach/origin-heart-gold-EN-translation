"""Make the latest.json a release carries next to its .xdelta, for the website's in-browser patcher (/patch/).

    python3 work/tools/site/patch_manifest.py v1.0.0-rc5          # writes work/release/v1.0.0-rc5/latest.json
    python3 work/tools/site/patch_manifest.py                     # the same for the newest work/release/<tag>/
    python3 work/tools/site/patch_manifest.py v1.0.0-rc5 --site   # also serve it from site/public/patch/ locally
    python3 work/tools/site/patch_manifest.py --none              # local preview of the "no patch" fallback

Upload latest.json with the release, before or when you publish it:
    gh release create v1.0.0-rc5 --prerelease work/release/v1.0.0-rc5/{*.xdelta,README.txt,latest.json}
    gh release upload v1.0.0-rc5 work/release/v1.0.0-rc5/latest.json      # for a release that already exists

The site workflow downloads the highest-version release's latest.json and the .xdelta it names, checks the SHA-1 and
serves both from the website (browsers can't fetch GitHub release assets cross-origin). A release without
latest.json leaves the patcher off, with a warning in the workflow run.

latest.json: {"tag", "file", "size", "sha1", "patched_sha1"}. patched_sha1 is the "Result ROM SHA-1:" line of
the release's README.txt; the patcher checks its output against it. site/public/patch/ is in .gitignore.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
RELEASES = os.path.join(REPO, 'work', 'release')
SITE_OUT = os.path.join(REPO, 'site', 'public', 'patch')
MAX_PATCH = 95 * 1024 * 1024  # GitHub Pages refuses files over 100 MB
VCDIFF_MAGIC = b'\xd6\xc3\xc4'

RESULT_SHA1 = re.compile(r'Result ROM SHA-1:\s*([0-9a-fA-F]{40})')
PATCH_SHA1 = re.compile(r'Patch:\s*(\S+\.xdelta)\s*\n\s*SHA-1\s+([0-9a-fA-F]{40})')


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def newest_tag():
    tags = [t for t in os.listdir(RELEASES) if t != 'wip' and os.path.isdir(os.path.join(RELEASES, t))
            and any(f.endswith('.xdelta') for f in os.listdir(os.path.join(RELEASES, t)))]
    if not tags:
        sys.exit('no work/release/<tag>/ with an .xdelta')
    return max(tags, key=lambda t: max(os.path.getmtime(os.path.join(RELEASES, t, f))
                                       for f in os.listdir(os.path.join(RELEASES, t)) if f.endswith('.xdelta')))


def manifest(tag):
    """Check work/release/<tag>/ and return its latest.json data."""
    folder = os.path.join(RELEASES, tag)
    patches = sorted(f for f in os.listdir(folder) if f.endswith('.xdelta')) if os.path.isdir(folder) else []
    if len(patches) != 1:
        sys.exit(f'work/release/{tag}/ must hold exactly one .xdelta, found {patches}')
    name = patches[0]
    path = os.path.join(folder, name)
    readme = os.path.join(folder, 'README.txt')
    text = open(readme, encoding='utf-8', errors='replace').read() if os.path.exists(readme) else ''
    result = RESULT_SHA1.search(text)
    if not result:
        sys.exit(f'work/release/{tag}/README.txt has no "Result ROM SHA-1:" line; the patcher could not verify its output')
    size = os.path.getsize(path)
    if size > MAX_PATCH:
        sys.exit(f'{name} is {size:,} bytes, too big for GitHub Pages')
    with open(path, 'rb') as f:
        if f.read(3) != VCDIFF_MAGIC:
            sys.exit(f'{name} is not an xdelta3 (VCDIFF) patch')
    sha1 = sha1_file(path)
    listed = PATCH_SHA1.search(text)
    if listed and (listed.group(1) != name or listed.group(2).lower() != sha1):
        sys.exit(f'README.txt lists {listed.group(1)} / SHA-1 {listed.group(2)}, but {name} has SHA-1 {sha1}')
    return {'tag': tag, 'file': name, 'size': size, 'sha1': sha1, 'patched_sha1': result.group(1).lower()}


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)
    print(f'{os.path.relpath(path, REPO)}: {json.dumps(data)}')


def serve_locally(data):
    """What the site workflow writes, from the local release instead of GitHub."""
    os.makedirs(SITE_OUT, exist_ok=True)
    for f in os.listdir(SITE_OUT):
        if os.path.isfile(os.path.join(SITE_OUT, f)):
            os.remove(os.path.join(SITE_OUT, f))
    if data is None:
        write_json(os.path.join(SITE_OUT, 'latest.json'), {'available': False, 'reason': 'turned off with --none'})
        return
    shutil.copyfile(os.path.join(RELEASES, data['tag'], data['file']), os.path.join(SITE_OUT, data['file']))
    repo_url = os.environ.get('GUIDE_REPO_URL')
    write_json(os.path.join(SITE_OUT, 'latest.json'), {
        'available': True, 'tag': data['tag'], 'file': data['file'], 'size': data['size'],
        'patched_sha1': data['patched_sha1'],
        'release_url': f'{repo_url}/releases/tag/{data["tag"]}' if repo_url else None,
        'prerelease': '-rc' in data['tag']})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('tag', nargs='?', help='release folder under work/release/ (default: the newest)')
    ap.add_argument('--site', action='store_true', help='also serve the patch from site/public/patch/ locally')
    ap.add_argument('--none', action='store_true', help='write the "no patch" fallback to site/public/patch/')
    a = ap.parse_args(argv)
    if a.none:
        serve_locally(None)
        return 0
    data = manifest(a.tag or newest_tag())
    write_json(os.path.join(RELEASES, data['tag'], 'latest.json'), data)
    if a.site:
        serve_locally(data)
    return 0


if __name__ == '__main__':
    sys.exit(main())
