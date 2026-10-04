#!/usr/bin/env python3
"""Build work/translate/us_ref.json from a (sparse) clone of pret/pokeheartgold.

Usage: python3 build_us_ref.py PATH_TO_POKEHEARTGOLD_CLONE
Needs files/msgdata/msg/*.gmm, src/, asm/, include/constants/maps.h (or ./maps.h).
Per US bank: gmm file name, map code (suffix), map constant names, row count,
C/asm source files that reference the bank, row ids, and the English strings.
"""
import html, json, os, re, sys
from collections import defaultdict

root = sys.argv[1]
msgdir = os.path.join(root, 'files/msgdata/msg')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'us_ref.json')

maps_h = None
for cand in ('include/constants/maps.h', 'maps.h'):
    p = os.path.join(root, cand)
    if os.path.exists(p):
        maps_h = open(p).read()
code2maps = defaultdict(list)
if maps_h:
    for m in re.finditer(r'#define\s+(MAP_\w+)\s+\d+\s*//\s*MAP_(\w+)', maps_h):
        code2maps[m.group(2)].append(m.group(1)[4:])

refs = defaultdict(set)
for d in ('src', 'asm', 'include'):
    for dp, _, fs in os.walk(os.path.join(root, d)):
        for f in fs:
            if not f.endswith(('.c', '.h', '.s', '.inc')):
                continue
            try:
                t = open(os.path.join(dp, f), errors='ignore').read()
            except OSError:
                continue
            for m in re.finditer(r'NARC_msg_msg_(\d{4})\w*?_bin', t):
                refs[int(m.group(1))].add(f)

row_re = re.compile(r'<row id="([^"]*)" index="(\d+)">.*?<language name="English">(.*?)</language>', re.S)
banks = {}
for f in sorted(os.listdir(msgdir)):
    m = re.match(r'msg_(\d{4})(?:_(\w+))?\.gmm$', f)
    if not m:
        continue
    b = int(m.group(1))
    code = m.group(2)
    t = open(os.path.join(msgdir, f), encoding='utf-8').read()
    rows = [(rid, int(i), html.unescape(s)) for rid, i, s in row_re.findall(t)]
    rows.sort(key=lambda r: r[1])
    n = max([r[1] for r in rows], default=-1) + 1
    strings = [''] * n
    ids = [''] * n
    for rid, i, s in rows:
        strings[i] = s
        ids[i] = rid
    named = [i for i in ids if i and not re.match(r'msg_\d{4}_\d+$', i)]
    banks[b] = {
        'bank': b, 'file': f, 'map_code': code,
        'maps': code2maps.get(code, []) if code else [],
        'count': n,
        'refs': sorted(refs.get(b, [])),
        'named_ids_sample': named[:8],
        'strings': strings,
    }
json.dump({'source': 'pret/pokeheartgold master (US HeartGold IPKE)', 'banks': [banks[k] for k in sorted(banks)]},
          open(out, 'w'), ensure_ascii=False, indent=0)
print(len(banks), 'banks ->', out)
