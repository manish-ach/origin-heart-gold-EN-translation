"""Correct report JSONs whose winner contradicts the game's own end message (before the bench read it, a double KO
or a last faint after the final count sample was scored for the side the count showed alive). Rerunnable.

  .venv/bin/python work/advanced-ai/testbench/versus/fix_outcomes.py [REPORT.json ...]
                    # default: every report in RUNS/aivsai/reports and RUNS/aivsai/holdout/

Ported from the Spanish workspace's qa/aivsai/fix_outcomes.py (dc8577c): the verdict is read in English (our ROM) and
in Spanish (rc44), and the paths are the test bench's.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)

REPORTS = os.path.join(tbpaths.RUNS, 'aivsai', 'reports')
HOLD = os.path.join(tbpaths.RUNS, 'aivsai', 'holdout')


def verdict(log):
    t = open(log, encoding='utf-8').read()
    if '>> ¡Derrotaste a' in t or '>> You defeated' in t:
        return 'original'
    if re.search(r'>> ¡A (?!Policía Felix)[^\n]* no le quedan Pokémon!', t) or \
            re.search(r'>> (?![^\n]*Felix is out)[^\n]* is out of usable Pokémon!', t):
        return 'advanced'
    return None


def find(log):
    """The log where it lives now (held-out runs are moved into holdout/)."""
    if not log:
        return None
    for p in (os.path.join(tbpaths.REPO, log), os.path.join(HOLD, *log.split('/')[-2:])):
        if os.path.isfile(p):
            return p
    return None


def fix(path):
    d = json.load(open(path))
    changed = []
    for g in d.get('results', []):
        log = find(g.get('log', ''))
        if not log or g.get('end') not in ('normal', 'wrong ai'):
            continue
        v = verdict(log)
        if v and g.get('winner') != v:
            changed.append((g['scenario'], g['game'], g.get('winner'), v))
            g['winner'] = v
            g['left']['original' if v == 'advanced' else 'advanced'] = 0
    if changed:
        json.dump(d, open(path, 'w'), indent=1)
    return changed


if __name__ == '__main__':
    paths = sys.argv[1:] or glob.glob(os.path.join(REPORTS, 'report_*.json')) + glob.glob(os.path.join(HOLD, 'report_*.json'))
    for p in sorted(paths):
        for c in fix(p):
            print('%s %s g%d: %s -> %s' % (os.path.basename(p), c[0], c[1], c[2], c[3]))
