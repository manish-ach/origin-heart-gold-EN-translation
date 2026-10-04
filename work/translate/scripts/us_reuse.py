#!/usr/bin/env python3
"""Per-v4-string guess: is this an unmodified vanilla HGSS string whose official US English
(work/extract/us/a027, the user's own ROM) can be reused?

Chain: v4 bank b (0-813) == JP/CN vanilla bank b (same layout) --bank_map_us_v4.json--> US bank u.
Vanilla references (work/translate/ref/): jp_a027.json (JP original, structure) and
vanilla_hgss.json (Xzonn's revised zh_Hans; the hack is based on the older ACG text, so
wording differs even for untouched strings -> used as a similarity signal, not an equality test).

Signals per v4 string (vanilla id j, normally j = id):
  xz      difflib ratio of loose-normalized v4 zh vs vanilla zh[j] (精灵/宝可梦 etc. folded)
  tags    command multiset (without colour/size) equals JP[j]
  pages   {CLEAR}+{SCROLL} count equals JP[j] (the ACG translation kept the JP paging)
  name    whole string is a glossary term whose English equals US[j] (case-insensitive)
  tm      v3 Eng (Shake69) English for this string is close to US[j] (ratio >= 0.7)
Verdict: likely / possible / unlikely / no_us (no US counterpart: hack-new bank or id beyond vanilla).
Output: work/translate/us_reuse.jsonl (one line per v4 a027 CJK string), us_reuse_summary.json
"""
import difflib, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from common import *

v4 = load_narc('v4')
US = load_narc('us')
JP = {int(k): v for k, v in json.load(open(os.path.join(OUT, 'ref', 'jp_a027.json')))['banks'].items()}
XZ = {int(k): v for k, v in json.load(open(os.path.join(OUT, 'ref', 'vanilla_hgss.json')))['banks'].items()}
BMAP = {e['v4']: e for e in json.load(open(os.path.join(OUT, 'bank_map_us_v4.json')))['map'] if e['v4'] is not None}

GL = {}
for f in ('species', 'moves', 'items', 'abilities', 'types', 'natures', 'locations'):
    for k, v in json.load(open(os.path.join(WORK, 'glossary', f + '.json'))).items():
        GL.setdefault(k, v['en'])

tm_en = defaultdict(list)
for l in open(os.path.join(OUT, 'tm_v4_matches.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    if r['narc'] == 'a027' and r['tier'] in ('exact', 'exact_loose'):
        tm_en[(r['bank'], r['id'])] = [c['en'] for c in r['candidates'][:3]]

# Xzonn revised terminology -> ACG-era wording used by the hack (for similarity only)
XZ_FOLD = [('宝可梦', '精灵'), ('使出了', '使用'), ('，', ','), ('……', '⋯⋯'), ('…', '⋯')]


def xnorm(t):
    for a, b in XZ_FOLD:
        t = t.replace(a, b)
    return norm(t, loose=True)


def enorm(s):
    s = TAG_RE.sub(' ', s).lower().replace('é', 'e').replace('’', "'")
    return re.sub(r"[^a-z0-9']+", ' ', s).strip()


def core_sig(t):
    return tuple(sorted((k, v) for k, v in var_sig(t).items() if k not in ('FF00', 'FF01')))


def pages(t):
    return t.count('{CLEAR}') + t.count('{SCROLL}')


def ratio(a, b):
    if not a or not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < 0.4:
        return sm.real_quick_ratio() * 0.5
    return sm.ratio()


fh = open(os.path.join(OUT, 'us_reuse.jsonl'), 'w', encoding='utf-8')
per_bank = {}
tot = Counter()
for b in sorted(v4):
    e = BMAP.get(b, {})
    u = e.get('us')
    jp = JP.get(b, [])
    xz = XZ.get(b, {}).get('zh', [])
    xzn = [xnorm(x) for x in xz]
    usb = US.get(u, []) if u is not None else []
    same_count_jp_us = u is not None and len(jp) == len(usb)
    c = Counter()
    for i, t in enumerate(v4[b]):
        if not has_cjk(t):
            continue
        n = cjk_count(t)
        c['cjk_strings'] += 1
        c['cjk_chars'] += n
        rec = {'bank': b, 'id': i, 'us_bank': u}
        if u is None or not usb:
            verdict, j = 'no_us', None
        else:
            k = xnorm(t)
            j, r = (i, ratio(k, xzn[i])) if i < len(xzn) else (None, 0.0)
            if r < 0.6 and xzn and len(xzn) <= 400:
                # hack may insert/reorder strings: look for the best vanilla string in the bank
                best = max(((ratio(k, x), jj) for jj, x in enumerate(xzn) if x), default=(0.0, None))
                if best[0] >= 0.6 and best[0] > r + 0.1:
                    r, j = best
            if j is None and i < len(jp):
                j = i
            if j is None or j >= len(usb) or not re.search('[A-Za-z]', TAG_RE.sub('', usb[j])) \
                    or KANA_RE.search(usb[j]):
                verdict = 'no_us'      # no counterpart, blank/unused US slot, or a Japanese-language US bank
            else:
                jt = jp[j] if j < len(jp) else ''
                tags_ok = core_sig(t) == core_sig(jt)
                tags_nonempty = bool(core_sig(t))
                pages_ok = pages(t) == pages(jt)
                us_t = usb[j]
                g = GL.get(norm(t))
                name_ok = bool(g) and enorm(g) == enorm(us_t)
                tm_sim = max((ratio(enorm(x), enorm(us_t)) for x in tm_en.get((b, i), [])), default=None)
                if name_ok or r >= 0.8 or (tm_sim is not None and tm_sim >= 0.7) or \
                        (r >= 0.6 and tags_ok and pages_ok):
                    verdict = 'likely'
                elif n > 4 and ((r >= 0.45 and tags_ok) or (tags_ok and tags_nonempty and pages_ok and r >= 0.3)):
                    verdict = 'possible'
                else:
                    verdict = 'unlikely'
                rec.update({'us_id': j, 'xz_ratio': round(r, 3), 'tags_match_jp': tags_ok,
                            'pages_match_jp': pages_ok, 'name_match': name_ok,
                            'tm_us_sim': None if tm_sim is None else round(tm_sim, 3),
                            'jp_us_same_count': same_count_jp_us, 'us_text': us_t})
        rec['verdict'] = verdict
        c[verdict] += 1
        c[verdict + '_chars'] += n
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    per_bank[b] = dict(c)
    tot.update(c)
fh.close()
summary = dict(tot)
for v in ('likely', 'possible', 'unlikely', 'no_us'):
    summary[v + '_pct_strings'] = round(100 * tot[v] / tot['cjk_strings'], 2)
    summary[v + '_pct_chars'] = round(100 * tot[v + '_chars'] / tot['cjk_chars'], 2)
json.dump({'summary': summary, 'per_bank': per_bank}, open(os.path.join(OUT, 'us_reuse_summary.json'), 'w'), indent=1)
print(json.dumps(summary, indent=1))
