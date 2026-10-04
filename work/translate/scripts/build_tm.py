#!/usr/bin/env python3
"""Step 2: harvest zh->en translation memory from v3 Cn / v3 Eng (same bank/id).

A pair is kept when the v3 Cn text contains CJK and the v3 Eng text has no CJK
left and differs from the Chinese.  Breakage is recorded as flags, not dropped.
Output: work/translate/tm_v3.jsonl  (one record per v3 bank/id)
        work/translate/tm_v3_stats.json
"""
import json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

set_fold(json.load(open(os.path.join(OUT, 'char_fold_v3.json')))['fold'])
cn = load_narc('v3cn')
en = load_narc('v3en')

LITERAL_VAR = re.compile(r'(?<![A-Za-z0-9])v0[0-9A-Fa-f]{3}(?![A-Za-z0-9])')
FULLWIDTH = re.compile(r'[！-～　]')


def flags_for(zh, e):
    f = []
    if '{U+' in e:
        f.append('broken_tags')
    if '{U+' in zh:
        f.append('zh_unknown_codes')
    vz, ve = var_sig(zh), var_sig(e)
    cz = {k: v for k, v in vz.items() if not k.startswith('FF')}
    ce = {k: v for k, v in ve.items() if not k.startswith('FF')}
    if cz != ce:
        f.append('var_mismatch')
    elif vz != ve:
        f.append('format_tag_mismatch')   # colour/size codes differ
    if KANA_RE.search(TAG_RE.sub('', e)):
        f.append('kana_leftover')
    if LITERAL_VAR.search(e):
        f.append('literal_var_text')
    if FULLWIDTH.search(TAG_RE.sub('', e)):
        f.append('fullwidth_chars')
    nz = cjk_count(zh)
    ne = len(re.sub(r'\s+', '', TAG_RE.sub('', e)))
    if nz >= 6 and ne < nz * 0.9:
        f.append('suspiciously_short')
    if ne > max(nz, 1) * 9 and ne > 20:
        f.append('suspiciously_long')      # often a misaligned/copied US string
    if any(b in zh for b in ('{CLEAR}', '{SCROLL}')) and not any(b in e for b in ('{CLEAR}', '{SCROLL}')):
        f.append('page_breaks_lost')
    return f


recs = []
stats = Counter()
for b in sorted(cn):
    if b not in en:
        continue
    for i, (z, e) in enumerate(zip(cn[b], en[b])):
        if not has_cjk(z):
            continue
        stats['v3cn_cjk_strings'] += 1
        if has_cjk(e):
            stats['still_chinese'] += 1
            continue
        if norm(z) == norm(e):
            stats['identical'] += 1
            continue
        if not re.sub(r'[\s\u2007\u3000]+', '', TAG_RE.sub('', e)):
            stats['blanked_in_v3en'] += 1     # v3 Eng replaced the text by spaces: not a translation
            continue
        fl = flags_for(z, e)
        recs.append({'zh': z, 'en': e, 'v3_bank': b, 'id': i, 'zh_key': norm(z), 'flags': fl})

# conflicts: same zh key, different English
def en_key(e):
    e = e.replace('{COMPRESSED}', '')
    for b in BREAK_TAGS:
        e = e.replace(b, ' ')
    return re.sub(r'\s+', ' ', e).strip().lower()


by_key = defaultdict(set)
for r in recs:
    by_key[r['zh_key']].add(en_key(r['en']))
for r in recs:
    n = len(by_key[r['zh_key']])
    r['en_variants'] = n
    if n > 1:
        r['flags'].append('conflict')
    r['quality'] = 'clean' if not [f for f in r['flags'] if f not in ('conflict', 'fullwidth_chars', 'format_tag_mismatch')] else 'flagged'

with open(os.path.join(OUT, 'tm_v3.jsonl'), 'w', encoding='utf-8') as fh:
    for r in recs:
        fh.write(json.dumps(r, ensure_ascii=False) + '\n')

fc = Counter(f for r in recs for f in r['flags'])
st = {'pairs': len(recs), 'unique_zh_keys': len(by_key),
      'unique_zh_with_conflicts': sum(1 for v in by_key.values() if len(v) > 1),
      'clean_pairs': sum(1 for r in recs if r['quality'] == 'clean'),
      'banks_with_pairs': len({r['v3_bank'] for r in recs}),
      'cjk_chars_covered': sum(cjk_count(r['zh']) for r in recs),
      'flag_counts': dict(fc.most_common()), **stats}
json.dump(st, open(os.path.join(OUT, 'tm_v3_stats.json'), 'w'), indent=1)
print(json.dumps(st, indent=1))
