#!/usr/bin/env python3
"""seed_tm - seed the workspace with v3 fan-translation memory (tm_v4_matches.jsonl, tier "exact").

Runs after seed_us.py. For every exact TM hit whose workspace entry is still untranslated
(status "todo", en null; i.e. no US-likely text was applied and nobody has drafted it):
  * drop candidates with broken tags ({U+....} in en, or flags broken_tags / zh_unknown_codes /
    literal_var_text / kana_leftover);
  * pick the best: same_position first, then most sources, then clean;
  * modernise names like seed_us (Gen-4 caps / old spellings -> glossary names);
  * set en, status "tm", origin "tm_v3"; notes count the other variants (no text).

Usage:
    python3 work/translate/scripts/seed_tm.py [--dry-run] [--ws work/translate/banks]
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(WORK, 'tools'))
import ws as wsmod  # noqa: E402
from seed_us import Moderniser  # noqa: E402

BAD_FLAGS = {'broken_tags', 'zh_unknown_codes', 'literal_var_text', 'kana_leftover'}


def usable(c):
    return not (BAD_FLAGS & set(c.get('flags') or [])) and '{U+' not in c['en'] and c['en'].strip()


def rank(c):
    return (bool(c.get('same_position')), len(c.get('sources') or []), bool(c.get('clean')))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ws', default=os.path.join(WORK, 'translate', 'banks'))
    ap.add_argument('--matches', default=os.path.join(WORK, 'translate', 'tm_v4_matches.jsonl'))
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)

    mod = Moderniser()
    by_bank = defaultdict(dict)
    for line in open(a.matches, encoding='utf-8'):
        r = json.loads(line)
        if r.get('tier') == 'exact':
            by_bank[(r['narc'], r['bank'])][r['id']] = r

    c = Counter()
    for (narc, bank) in sorted(by_bank):
        p = Path(a.ws) / narc / ('%04d.json' % bank)
        if not p.exists():
            c['missing_bank'] += len(by_bank[(narc, bank)])
            continue
        b = wsmod.load_json(p)
        changed = False
        for e in b['strings']:
            r = by_bank[(narc, bank)].get(e['id'])
            if r is None:
                continue
            if e.get('status') != 'todo' or e.get('en') is not None:
                c['skipped_existing' if e.get('origin') != 'us' else 'skipped_us_applied'] += 1
                continue
            if 'seed rejected tm_v3' in (e.get('notes') or ''):
                c['skipped_previously_rejected'] += 1
                continue
            if r['zh'] != e['zh']:
                c['skipped_zh_mismatch'] += 1
                continue
            cands = [x for x in r['candidates'] if usable(x)]
            if not cands:
                c['skipped_no_clean_candidate'] += 1
                continue
            cands.sort(key=rank, reverse=True)
            best = cands[0]
            en = mod(best['en'])
            notes = ['v3 TM: %d source(s)%s%s' % (len(best.get('sources') or []),
                                                ', same position' if best.get('same_position') else '',
                                                (', flags ' + ','.join(best['flags'])) if best.get('flags') else '')]
            if en != best['en']:
                notes.append('modernised from the v3 TM text')   # pointer only: never copy source text into notes
                c['modernised'] += 1
            others = [x['en'] for x in r['candidates'] if x is not best]
            if others:
                # count only: never copy v3 text into notes (the candidates stay in tm_v4_matches.jsonl)
                notes.append('other variants: %d more v3 TM candidate%s (tm_v4_matches.jsonl)'
                             % (len(others), '' if len(others) == 1 else 's'))
            e['en'] = en
            e['status'] = 'tm'
            e['origin'] = 'tm_v3'
            e['notes'] = (e.get('notes') + ' | ' if e.get('notes') else '') + '; '.join(notes)
            changed = True
            c['applied'] += 1
            c['applied_' + narc] += 1
        if changed and not a.dry_run:
            wsmod.save_json(p, b)
    print(json.dumps(c, indent=1))


if __name__ == '__main__':
    main()
