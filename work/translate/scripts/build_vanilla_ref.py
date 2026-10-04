#!/usr/bin/env python3
"""Build work/translate/ref/vanilla_hgss.json from a clone of
github.com/Xzonn/PokemonChineseTranslationRevise (texts/ are CC BY-NC-SA 3.0; local reference only).

Per JP/CN bank index (same 814-bank layout as v3/v4 banks 0-813):
  name (Japanese dev gmm name, e.g. 'bag', 't07r0401'), game (HGSS/DP/Pt source file),
  zh  = vanilla Simplified Chinese (Xzonn's revision of the ACG translation), converted to our tag format,
  ja  = Japanese original, same conversion.
Usage: python3 build_vanilla_ref.py PATH_TO_CLONE
"""
import json, os, re, sys

root = sys.argv[1]
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ref')
os.makedirs(out_dir, exist_ok=True)


def conv(t):
    t = t.replace('\\f\n', '{CLEAR}').replace('\\r\n', '{SCROLL}')
    t = t.replace('\\f', '{CLEAR}').replace('\\r', '{SCROLL}').replace('\n', '{NEWLINE}')

    def var(m):
        parts = m.group(1).split(',')
        cmd = parts[0]
        args = [str(int(p, 16)) for p in parts[1:]]
        return '{VAR:%s%s}' % (cmd, (':' + ','.join(args)) if args else '')
    return re.sub(r'\[([0-9A-F]{4}(?:,[0-9A-F]{4})*)\]', var, t)


banks = {}
for line in open(os.path.join(root, 'texts/HGSS/messages_list.txt'), encoding='utf-8'):
    idx, game, fname = line.rstrip('\n').split('\t')
    name = fname[:-4]
    p = os.path.join(root, 'texts', game, 'zh_Hans', name + '.json')
    if not os.path.exists(p):
        continue
    rows = sorted(json.load(open(p, encoding='utf-8')), key=lambda r: r['index'])
    n = max((r['index'] for r in rows), default=-1) + 1
    zh, ja = [''] * n, [''] * n
    for r in rows:
        zh[r['index']] = conv(r.get('translation') or '')
        ja[r['index']] = conv(r.get('original') or '')
    banks[int(idx)] = {'bank': int(idx), 'name': name, 'game': game, 'count': n, 'zh': zh, 'ja': ja}

json.dump({'source': 'Xzonn/PokemonChineseTranslationRevise texts (CC BY-NC-SA 3.0), JP/CN HGSS a/0/2/7 layout',
           'banks': banks}, open(os.path.join(out_dir, 'vanilla_hgss.json'), 'w'), ensure_ascii=False)
print(len(banks), 'banks')
