#!/usr/bin/env python3
"""Step 3: apply tm_v3.jsonl to v4 (a027 + battle_string).

Tiers per v4 CJK string (first hit wins):
  exact        normalized key identical (NFKC, breaks/whitespace dropped, v3 variant fold)
  exact_loose  identical after also masking tags ({VAR..} -> §) and trailing punctuation/~
               (translation usable but tags must be re-checked)
  fuzzy        difflib ratio >= 0.80 on the loose key (bigram-prefiltered); NOT auto-accepted.
               'fuzzy90' = ratio >= 0.90, 'fuzzy80' = 0.80-0.90.
Output: work/translate/tm_v4_matches.jsonl, work/translate/tm_v4_coverage.json
"""
import difflib, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

set_fold(json.load(open(os.path.join(OUT, 'char_fold_v3.json')))['fold'])
tm = [json.loads(l) for l in open(os.path.join(OUT, 'tm_v3.jsonl'), encoding='utf-8')]


def en_key(e):
    e = e.replace('{COMPRESSED}', '')
    for b in BREAK_TAGS:
        e = e.replace(b, ' ')
    return re.sub(r'\s+', ' ', e).strip().lower()


by_key = defaultdict(list)
by_loose = defaultdict(list)
for r in tm:
    by_key[r['zh_key']].append(r)
    by_loose[norm(r['zh'], loose=True)].append(r)


def candidates(recs, bank, sid, narc):
    groups = {}
    for r in recs:
        k = en_key(r['en'])
        g = groups.setdefault(k, {'en': r['en'], 'sources': [], 'clean': False, 'flags': set()})
        g['sources'].append([r['v3_bank'], r['id']])
        g['clean'] |= r['quality'] == 'clean'
        g['flags'] |= set(f for f in r['flags'] if f != 'conflict')
        if narc == 'a027' and r['v3_bank'] == bank and r['id'] == sid:
            g['same_position'] = True
            g['en'] = r['en']
    out = []
    for g in groups.values():
        g['flags'] = sorted(g['flags'])
        g['same_position'] = g.get('same_position', False)
        out.append(g)
    out.sort(key=lambda g: (not g['same_position'], not g['clean'], -len(g['sources'])))
    return out


# fuzzy index over unique loose keys
lkeys = [k for k in by_loose if len(k) >= 4]
def grams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}
inv = defaultdict(list)
for idx, k in enumerate(lkeys):
    for g in grams(k):
        inv[g].append(idx)
MAXDF = 1500


def fuzzy(k):
    if len(k) < 6:
        return None
    gs = grams(k)
    cnt = Counter()
    for g in gs:
        lst = inv.get(g)
        if lst and len(lst) <= MAXDF:
            cnt.update(lst)
    best = None
    L = len(k)
    for idx, c in cnt.most_common(25):
        cand = lkeys[idx]
        if c < 0.5 * len(gs) or not (0.75 * L <= len(cand) <= 1.33 * L):
            continue
        sm = difflib.SequenceMatcher(None, k, cand, autojunk=False)
        if sm.real_quick_ratio() < 0.8 or sm.quick_ratio() < 0.8:
            continue
        r = sm.ratio()
        if r >= 0.8 and (best is None or r > best[0]):
            best = (r, cand)
    return best


sources = [('a027', load_narc('v4', 'a027')), ('battle_string', load_narc('v4', 'battle_string'))]
cov = {}
tot = Counter()
fh = open(os.path.join(OUT, 'tm_v4_matches.jsonl'), 'w', encoding='utf-8')
for narc, banks in sources:
    for b in sorted(banks):
        c = Counter()
        for i, t in enumerate(banks[b]):
            if not has_cjk(t):
                continue
            n = cjk_count(t)
            c['cjk_strings'] += 1
            c['cjk_chars'] += n
            k = norm(t)
            tier, score, recs, src_zh = None, None, None, None
            if k in by_key:
                tier, score, recs = 'exact', 1.0, by_key[k]
            else:
                lk = norm(t, loose=True)
                if lk in by_loose:
                    tier, score, recs = 'exact_loose', 1.0, by_loose[lk]
                else:
                    f = fuzzy(lk)
                    if f:
                        score = round(f[0], 3)
                        tier = 'fuzzy90' if f[0] >= 0.9 else 'fuzzy80'
                        recs = by_loose[f[1]]
            if not tier:
                continue
            c[tier] += 1
            c[tier + '_chars'] += n
            cands = candidates(recs, b, i, narc)
            rec = {'narc': narc, 'bank': b, 'id': i, 'zh': t, 'tier': tier, 'score': score,
                   'n_variants': len(cands), 'candidates': cands}
            if tier.startswith('fuzzy') or tier == 'exact_loose':
                rec['tm_zh'] = recs[0]['zh']
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
        cov[f'{narc}/{b}'] = dict(c)
        tot.update(c)
fh.close()
summary = dict(tot)
for t in ('exact', 'exact_loose', 'fuzzy90', 'fuzzy80'):
    summary[t + '_pct_strings'] = round(100 * tot[t] / tot['cjk_strings'], 2)
    summary[t + '_pct_chars'] = round(100 * tot[t + '_chars'] / tot['cjk_chars'], 2)
json.dump({'summary': summary, 'per_bank': cov}, open(os.path.join(OUT, 'tm_v4_coverage.json'), 'w'), indent=1)
print(json.dumps(summary, indent=1))
