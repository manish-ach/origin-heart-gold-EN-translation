#!/usr/bin/env python3
"""Step 1: align v3 (a027, 814 banks) to v4 (a027, 817 banks) by content.

Score(v3 bank a, v4 bank b) = multiset overlap of normalized non-trivial strings
/ max(len_a, len_b)  (Dice-like), with a count-similarity term for banks whose
strings are too generic.  Candidates come from an inverted index on strings.
A monotone DP (Needleman-Wunsch, gaps allowed) picks the final 1:1 map so
banks with no distinctive text (empty/number-only) are placed by their
neighbours.  Also learns a v3->v4 variant-character fold from aligned pairs.
Writes work/translate/bank_map_v3_v4.json and work/translate/char_fold_v3.json.
"""
import json, math, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

v3 = load_narc('v3cn')
v4 = load_narc('v4')


def keys(strings):
    return Counter(k for k in (norm(s) for s in strings) if len(k) >= 2)


def build(fold_pass):
    k3 = {b: keys(s) for b, s in v3.items()}
    k4 = {b: keys(s) for b, s in v4.items()}
    inv = defaultdict(set)
    for b, c in k4.items():
        for k in c:
            inv[k].add(b)
    sim = {}
    for a, c in k3.items():
        cand = Counter()
        for k in c:
            bs = inv.get(k, ())
            if len(bs) <= 8:
                for b in bs:
                    cand[b] += 1
        for b, _ in cand.most_common(6):
            inter = sum((c & k4[b]).values())
            sim[(a, b)] = inter / max(sum(c.values()), sum(k4[b].values()), 1)
    return sim


def count_sim(a, b):
    na, nb = len(v3[a]), len(v4[b])
    if na == nb:
        return 1.0
    return math.exp(-3 * abs(math.log((na + 1) / (nb + 1))))


def dp_align(sim):
    A, B = sorted(v3), sorted(v4)
    n, m = len(A), len(B)
    GAP = -0.25
    NEG = -1e9

    def s(i, j):
        c = sim.get((A[i], B[j]), 0.0)
        cs = count_sim(A[i], B[j])
        # content dominates; count similarity breaks ties / places empty banks
        return 2.0 * c + 0.4 * cs - 0.3
    # banded DP (offset between v3 and v4 index stays small)
    band = 30
    score = {}
    back = {}
    score[(0, 0)] = 0.0
    for i in range(n + 1):
        for j in range(max(0, i - band), min(m, i + band) + 1):
            if (i, j) == (0, 0):
                continue
            best, bk = NEG, None
            if i > 0 and j > 0 and (i - 1, j - 1) in score:
                v = score[(i - 1, j - 1)] + s(i - 1, j - 1)
                if v > best:
                    best, bk = v, 'M'
            if i > 0 and (i - 1, j) in score:
                v = score[(i - 1, j)] + GAP
                if v > best:
                    best, bk = v, 'A'
            if j > 0 and (i, j - 1) in score:
                v = score[(i, j - 1)] + GAP
                if v > best:
                    best, bk = v, 'B'
            score[(i, j)] = best
            back[(i, j)] = bk
    i, j = n, m
    pairs = []
    while (i, j) != (0, 0):
        bk = back[(i, j)]
        if bk == 'M':
            pairs.append((A[i - 1], B[j - 1]))
            i, j = i - 1, j - 1
        elif bk == 'A':
            pairs.append((A[i - 1], None))
            i -= 1
        else:
            pairs.append((None, B[j - 1]))
            j -= 1
    return pairs[::-1]


def learn_fold(pairs):
    cnt = Counter()
    for a, b in pairs:
        if a is None or b is None:
            continue
        for s3, s4 in zip(v3[a], v4[b]):
            x, y = norm(s3), norm(s4)
            if x == y or len(x) != len(y) or len(x) < 2:
                continue
            diff = [(p, q) for p, q in zip(x, y) if p != q]
            if 0 < len(diff) <= 2 and all(CJK_RE.match(p) and CJK_RE.match(q) for p, q in diff):
                cnt.update(diff)
    # keep consistent mappings seen >=3 times, and where p never maps elsewhere much
    by_src = defaultdict(Counter)
    for (p, q), c in cnt.items():
        by_src[p][q] += c
    fold = {}
    for p, qs in by_src.items():
        q, c = qs.most_common(1)[0]
        if c >= 3 and c >= 0.8 * sum(qs.values()):
            fold[p] = q
    return fold


sim = build(0)
pairs = dp_align(sim)
fold = learn_fold(pairs)
# sanity: a folded char must not itself be a common v4 char with a different meaning
v4chars = Counter(c for ss in v4.values() for s in ss for c in s if CJK_RE.match(c))
v3chars = Counter(c for ss in v3.values() for s in ss for c in s if CJK_RE.match(c))
fold = {p: q for p, q in fold.items() if v4chars[p] <= 0.1 * v3chars[p]}
set_fold(fold)
sim = build(1)
pairs = dp_align(sim)

res = []
for a, b in pairs:
    e = {'v3': a, 'v4': b}
    if a is not None and b is not None:
        c = sim.get((a, b), 0.0)
        best_other = max([v for (x, y), v in sim.items() if x == a and y != b], default=0.0)
        na, nb = len(v3[a]), len(v4[b])
        k3 = keys(v3[a])
        e.update({'v3_count': na, 'v4_count': nb, 'content_sim': round(c, 3),
                  'exact_strings_same': sum(1 for x, y in zip(v3[a], v4[b]) if norm(x) == norm(y)),
                  'best_other_sim': round(best_other, 3)})
        same = e['exact_strings_same']
        pos_same = same / max(min(na, nb), 1)
        contain = sum((k3 & keys(v4[b])).values()) / max(sum(k3.values()), 1)
        e['containment_v3_in_v4'] = round(contain, 3)
        e['same_id_ratio'] = round(pos_same, 3)
        if pos_same >= 0.5 or (contain >= 0.5 and c >= best_other):
            conf = 'high'
        elif pos_same >= 0.2 or contain >= 0.2:
            conf = 'medium'
        elif na == nb:
            conf = 'medium-structural'   # text rewritten / nothing distinctive; placed by neighbours, equal count
        else:
            conf = 'low-structural'
        e['confidence'] = conf
    elif a is None:
        e.update({'v4_count': len(v4[b]), 'confidence': 'v4-only (new or rewritten bank)'})
    else:
        e.update({'v3_count': len(v3[a]), 'confidence': 'v3-only (dropped in v4)'})
    res.append(e)

summary = Counter(e['confidence'] for e in res)
offsets = Counter((e['v4'] - e['v3']) for e in res if e['v3'] is not None and e['v4'] is not None)
out = {'description': 'v3 (a/0/2/7, 814 banks) -> v4.0.3 (817 banks) alignment by content (monotone DP over '
                      'normalized-string multiset overlap + count similarity). content_sim = shared normalized '
                      'strings / max(len). exact_strings_same = same-id strings identical after normalization.',
       'summary': dict(summary), 'offset_histogram': {str(k): v for k, v in sorted(offsets.items())},
       'map': res}
json.dump(out, open(os.path.join(OUT, 'bank_map_v3_v4.json'), 'w'), ensure_ascii=False, indent=1)
json.dump({'description': 'v3 (ACG table) -> v4 (Xzonn table) variant character fold learned from aligned strings',
           'fold': fold}, open(os.path.join(OUT, 'char_fold_v3.json'), 'w'), ensure_ascii=False, indent=1)
print(summary, dict(offsets), 'fold', len(fold), list(fold.items())[:30])
