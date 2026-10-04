#!/usr/bin/env python3
"""Guess the US HeartGold (pret/pokeheartgold, us_ref.json) bank for each v4 a027 bank.

v4 banks 0-813 are v3 banks 0-813 (bank_map_v3_v4.json, offset 0); v3/v4 follow the
Japanese/Chinese 814-bank layout while US has 829 (0-828), so the offset drifts.
Monotone DP over (v4 bank, US bank) with pair score from:
  * English content: v4 Latin-only strings, v3 Eng strings of the same bank and
    glossary translations of v4 name strings, matched against normalized US strings
    (IDF-weighted overlap);
  * command signature: cosine of {VAR:xxxx} command-id histograms (US {STRVAR_1 k,..} -> 01kk etc.);
  * string-count similarity.
Writes work/translate/bank_map_us_v4.json
"""
import json, math, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

us = {b['bank']: b for b in json.load(open(os.path.join(OUT, 'us_ref.json')))['banks']}
# official text from the user's own US ROM (work/extract/us/a027, same numbering as pret)
US_ROM = load_narc('us')
for u, ss in US_ROM.items():
    us.setdefault(u, {'bank': u, 'file': 'msg_%04d.gmm' % u, 'map_code': None, 'maps': [], 'refs': []})
    us[u]['strings'] = ss
    us[u]['count'] = len(ss)
v4 = load_narc('v4')
v3en = load_narc('v3en')
GL = {}
for f in ('species', 'moves', 'items', 'abilities', 'locations', 'types', 'natures'):
    for k, v in json.load(open(os.path.join(WORK, 'glossary', f + '.json'))).items():
        GL.setdefault(k, v['en'])


def enorm(s):
    s = s.replace('\\n', ' ').replace('\\r', ' ').replace('\\f', ' ')
    s = TAG_RE.sub(' ', s).lower().replace('é', 'e').replace('’', "'")
    s = re.sub(r"[^a-z0-9']+", ' ', s)
    return s.strip()


US_CMD = {'COLOR': 'FF00', 'SIZE': 'FF01', 'YESNO': '0200', 'PAUSE': '0201', 'WAIT': '0202',
          'CURSOR_X': '0203', 'CURSOR_Y': '0204', 'ALN_CENTER': '0205', 'ALN_RIGHT': '0206'}


def us_sig(strings):
    c = Counter()
    for s in strings:
        for m in re.finditer(r'\{(\w+)(?: ([^}]*))?\}', s):
            name, args = m.group(1), (m.group(2) or '')
            mm = re.match(r'STRVAR_(\d+)$', name)
            if mm:
                k = int(args.split(',')[0]) if args else 0
                c['%02X%02X' % (int(mm.group(1)), k)] += 1
            elif name in US_CMD:
                c[US_CMD[name]] += 1
    return c


def cos(a, b):
    if not a or not b:
        return None
    dot = sum(a[k] * b.get(k, 0) for k in a)
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


# English evidence per v4 bank
ev = {}
for b, ss in v4.items():
    e = set()
    for s in ss:
        if not has_cjk(s):
            n = enorm(s)
            if len(n) >= 4 and re.search('[a-z]{3}', n):
                e.add(n)
        else:
            g = GL.get(norm(s))
            if g:
                n = enorm(g)
                if len(n) >= 3:
                    e.add(n)
    for s in v3en.get(b, []):
        if not has_cjk(s):
            n = enorm(s)
            if len(n) >= 4 and re.search('[a-z]{3}', n):
                e.add(n)
    ev[b] = e

usn = {u: set(n for n in (enorm(s) for s in d['strings']) if len(n) >= 3) for u, d in us.items()}
df = Counter(n for s in usn.values() for n in s)
inv = defaultdict(set)
for u, s in usn.items():
    for n in s:
        inv[n].add(u)
content = defaultdict(float)
for b, e in ev.items():
    for n in e:
        for u in inv.get(n, ()):
            content[(b, u)] += 1.0 / df[n]


def content_norm(b, u):
    c = content.get((b, u), 0.0)
    if not c:
        return 0.0
    denom = min(len(ev[b]), len(usn[u])) or 1
    return min(1.0, c / max(3.0, denom * 0.5))


# entity evidence: species / locations / trainer names mentioned in the text
NAMES = {}
for f in ('species', 'locations'):
    for k, v in json.load(open(os.path.join(WORK, 'glossary', f + '.json'))).items():
        if len(k) >= 2 and re.match(r'^[\u4e00-\u9fff]+$', k):
            NAMES[k] = v['en']
for l in open(os.path.join(OUT, 'tm_v3.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    if r['v3_bank'] == 719 and len(r['zh']) >= 2 and re.match(r'^[\u4e00-\u9fff]+$', r['zh']):
        e = r['en'].replace('{COMPRESSED}', '').strip()
        if re.match(r'^[A-Z][a-z]+$', e):
            NAMES.setdefault(r['zh'], e)
zh_re = re.compile('|'.join(sorted(map(re.escape, NAMES), key=len, reverse=True)))
en_names = sorted({v.lower() for v in NAMES.values() if len(v) >= 4}, key=len, reverse=True)
en_re = re.compile(r'\b(' + '|'.join(map(re.escape, en_names)) + r')\b')
ent4 = {b: {NAMES[m].lower() for s in ss for m in zh_re.findall(s)} for b, ss in v4.items()}
entu = {u: set(en_re.findall(' '.join(d['strings']).lower().replace('é', 'e'))) for u, d in us.items()}
dfe = Counter(n for s in entu.values() for n in s)


def ent_sim(b, u):
    a, c = ent4.get(b, set()), entu.get(u, set())
    if not a or not c:
        return 0.0
    inter = sum(1.0 / dfe[n] for n in a & c)
    tot = sum(1.0 / max(dfe[n], 1) for n in a | c)
    return inter / tot if tot else 0.0


sig4 = {b: var_sig(''.join(ss)) for b, ss in v4.items()}
sigu = {u: var_sig(''.join(d['strings'])) for u, d in us.items()}
US_COUNT = {u: d['count'] for u, d in us.items()}


JP = {int(k): v for k, v in json.load(open(os.path.join(OUT, 'ref', 'jp_a027.json')))['banks'].items()}
XZ = {int(k): v['name'] for k, v in json.load(open(os.path.join(OUT, 'ref', 'vanilla_hgss.json')))['banks'].items()}


def core_sig(t):
    return tuple(sorted((k, v) for k, v in var_sig(t).items() if k not in ('FF00', 'FF01')))


def tag_agree(b, u):
    """Vanilla JP bank b vs US bank u: fraction of same-id strings with identical command multiset
    (only over ids where either side has commands). None if no commands at all."""
    a, c = JP.get(b, []), US_ROM.get(u, [])
    tot = same = 0
    for x, y in zip(a, c):
        sx, sy = core_sig(x), core_sig(y)
        if sx or sy:
            tot += 1
            same += sx == sy
    return (same / tot) if tot >= 2 else None


def map_code_match(b, u):
    jp = XZ.get(b, '')
    uc = (us.get(u, {}).get('map_code') or '')
    if not uc or not re.match(r'^[a-z]+\d', jp or ''):
        return 0.0
    return 1.0 if jp.upper() == uc.upper() else -1.0


def pair(b, u):
    na = len(JP.get(b, v4[b]))      # vanilla JP count (v4 banks may be hack-extended)
    nb = US_COUNT.get(u)
    cs = 0.3 if nb is None else (1.0 if na == nb else math.exp(-2.5 * abs(math.log((na + 1) / (nb + 1)))))
    tc = cos(sig4[b], sigu.get(u, Counter()))
    if tc is None:
        tc = 0.5 if (not sig4[b] and not sigu.get(u)) else 0.0
    cn = content_norm(b, u)
    return cn, tc, cs, ent_sim(b, u)


def kana_bonus(b, u):
    # the Chinese build replaced the Japanese-language banks (e.g. JP Pokédex text) with Chinese
    ss = us.get(u, {}).get('strings', [])
    kana = sum(1 for x in ss if KANA_RE.search(x))
    cjk = sum(1 for x in v4[b] if has_cjk(x))
    return 0.8 if ss and kana > 0.5 * max(len(ss), 1) and cjk > 0.5 * max(len(v4[b]), 1) and len(ss) == len(v4[b]) else 0.0


# US-only localisation banks: ALL-CAPS copies used only by easy_chat.c (JP has one list)
CAPS_VARIANT = {u for u, d in us.items() if d['refs'] == ['easy_chat.c']
                and sum(1 for x in d['strings'] if x and x == x.upper()) > 0.8 * max(1, sum(1 for x in d['strings'] if x))}
A = [b for b in sorted(v4) if b < 814]      # 814-816 are hack-new (see bank_map_v3_v4.json)
MAXOFF = 15                                  # US has 15 more banks than the JP/CN layout
GAP = -0.05                                  # per skipped US bank
cache = {}


def S(b, u):
    key = (b, u)
    if key not in cache:
        if u not in us and u != 729:
            cache[key] = -5.0
        else:
            cn, tc, cs, es = pair(b, u)
            ta = tag_agree(b, u)
            cache[key] = (3.0 * cn + 0.5 * tc + 0.9 * cs + 1.5 * es + kana_bonus(b, u) - 1.0
                          - (0.3 if u in CAPS_VARIANT else 0.0)
                          + (2.0 * ta - 0.6 if ta is not None else 0.0)
                          + 3.0 * map_code_match(b, u))
    return cache[key]


# dp over non-decreasing offset k (v4 bank b -> US bank b+k)
NEG = -1e18
dp = [[NEG] * (MAXOFF + 1) for _ in A]
bk = [[0] * (MAXOFF + 1) for _ in A]
for k in range(MAXOFF + 1):
    dp[0][k] = S(A[0], A[0] + k) + GAP * k
for i in range(1, len(A)):
    best, arg = NEG, 0
    for k in range(MAXOFF + 1):
        if dp[i - 1][k] > best:
            best, arg = dp[i - 1][k], k
        # best over k' <= k, penalise the (k - k') skipped banks
        cand = max(((dp[i - 1][kk] + GAP * (k - kk), kk) for kk in range(k + 1)))
        dp[i][k] = cand[0] + S(A[i], A[i] + k)
        bk[i][k] = cand[1]
k = max(range(MAXOFF + 1), key=lambda k: dp[-1][k])
offs = [0] * len(A)
for i in range(len(A) - 1, -1, -1):
    offs[i] = k
    k = bk[i][k]
matched = {A[i]: A[i] + offs[i] for i in range(len(A))}
used = set(matched.values())
pairs = []
for u in range(829):
    if u not in used:
        pairs.append((None, u))
for b in sorted(v4):
    pairs.append((b, matched.get(b)))
pairs.sort(key=lambda p: (p[1] if p[1] is not None else 10000 + p[0], p[0] is not None))

res = []
for b, u in pairs:
    e = {'v4': b, 'us': u}
    if b is not None and u is not None:
        cn, tc, cs, es = pair(b, u)
        best_u = max(((content_norm(b, x), x) for x in range(max(0, b - 5), b + 50) if x in usn), default=(0, None))
        e.update({'v4_count': len(v4[b]), 'us_count': US_COUNT.get(u), 'us_file': us.get(u, {}).get('file'),
                  'us_maps': us.get(u, {}).get('maps', []),
                  'content': round(cn, 3), 'tag_cos': round(tc, 3), 'count_sim': round(cs, 3), 'entity_sim': round(es, 3),
                  'jp_name': XZ.get(b), 'jp_count': len(JP.get(b, [])),
                  'jp_us_tag_agree': (round(tag_agree(b, u), 3) if tag_agree(b, u) is not None else None),
                  'map_code_match': map_code_match(b, u) > 0})
        ta = tag_agree(b, u)
        if map_code_match(b, u) > 0 or (cn >= 0.5 and best_u[1] == u) or \
                (ta is not None and ta >= 0.8 and len(JP.get(b, [])) == US_COUNT.get(u)):
            conf = 'high'
        elif cn >= 0.2 or es >= 0.3 or (tc >= 0.9 and cs >= 0.8 and sig4[b]):
            conf = 'medium'
        elif cs == 1.0:
            conf = 'low (count only)'
        else:
            conf = 'low (position only)'
        e['confidence'] = conf
    elif b is None:
        e.update({'us_file': us.get(u, {}).get('file'), 'us_count': US_COUNT.get(u), 'confidence': 'us-only'})
    else:
        e.update({'v4_count': len(v4[b]), 'confidence': 'v4-only'})
    res.append(e)

# upgrade position-only guesses that sit between two content anchors with the same offset
anch = [(e['v4'], e['us'] - e['v4']) for e in res if e.get('confidence') in ('high', 'medium')]
for e in res:
    if e['v4'] is None or e['us'] is None or not e['confidence'].startswith('low'):
        continue
    before = [o for b, o in anch if b < e['v4']]
    after = [o for b, o in anch if b > e['v4']]
    if before and after and before[-1] == after[0] == e['us'] - e['v4']:
        e['confidence'] = 'medium (between anchors, same offset)'
summ = Counter(e['confidence'] for e in res)
off = []
prev = None
for e in res:
    if e['v4'] is not None and e['us'] is not None:
        d = e['us'] - e['v4']
        if d != prev:
            off.append([e['v4'], d])
            prev = d
json.dump({'description': 'Guessed US HeartGold (pret/pokeheartgold msg_NNNN.gmm = US a/0/2/7 index) bank per v4 a027 '
                          'bank. Monotone DP over English-content overlap (v4 Latin leftovers, v3 Eng, glossary), '
                          'command-signature cosine and string-count similarity. Use high/medium only for reuse of '
                          'official text; always verify per string.',
           'summary': dict(summ), 'offset_changes_[v4,us-v4]': off, 'map': res},
          open(os.path.join(OUT, 'bank_map_us_v4.json'), 'w'), ensure_ascii=False, indent=1)
print(summ)
print(off)
