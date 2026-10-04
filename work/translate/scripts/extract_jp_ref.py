#!/usr/bin/env python3
"""Decode the vanilla Japanese HGSS message NARC (a/0/2/7, 814 banks) shipped in
Xzonn/PokemonChineseTranslationRevise original_files/HGSS/data/a/0/2/7 into
work/translate/ref/jp_a027.json ({bank: [strings]}), using work/tools/msgtool.py.
Usage: python3 extract_jp_ref.py PATH_TO_NARC
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(WORK, 'tools'))
import msgtool as M
n = M.Narc.parse(open(sys.argv[1], 'rb').read())
cm = M.Charmap.load([os.path.join(WORK, 'tools/charmap_en.tsv'), os.path.join(WORK, 'tools/charmaps/charmap_zh_xzonn_gen4.tsv')])
out = {}
for i, f in enumerate(n.files):
    j = M.bank_to_json(i, f, cm)
    out[i] = [s['text'] for s in j['strings']]
json.dump({'source': 'vanilla JP HeartGold/SoulSilver a/0/2/7 (via Xzonn original_files)', 'banks': out},
          open(os.path.join(WORK, 'translate/ref/jp_a027.json'), 'w'), ensure_ascii=False)
print(len(out))
