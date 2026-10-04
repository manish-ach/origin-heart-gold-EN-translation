#!/usr/bin/env python3
"""seed_us - seed the translation workspace with official US HeartGold text.

For every a027 string whose us_reuse.jsonl verdict is "likely", set
    en = modernise(us_text), status "tm", origin "us"
on workspace entries that are still untranslated (status "todo", en null). Entries with any other
status (draft / reviewed / tm, including the glossary name banks and "copy" strings) are never touched.

Modernisation (STYLE.md rule 2):
  * Gen-4 ALL-CAPS species (BULBASAUR, FARFETCH’D, MR. MIME ...) -> modern mixed case (PokéAPI).
  * ALL-CAPS types (FIRE, FIGHTING ...) -> Fire, Fighting, only in strings that contain lowercase
    letters (so pure-caps UI labels are left alone).
  * POKéMON/POKé BALL/POKéDEX/POKéGEAR/... -> Pokémon/Poké Ball/Pokédex/Pokégear/...;
    TRAINER(S) -> Trainer(s) in mixed-case strings.
  * Gen-4 move/item/ability spellings (DoubleSlap, Faint Attack, Parlyz Heal, Thunderstone,
    Compoundeyes ...) -> current official names, by index: US name banks 0750/0222/0720 vs
    glossary/src PokéAPI CSVs (item ids via item_game_indices generation 4).
  * ASCII apostrophes from PokéAPI names become ’ (the font has no ASCII quotes).

Usage:
    python3 work/translate/scripts/seed_us.py [--dry-run] [--ws work/translate/banks] [--show N]
Re-runnable: already-seeded entries are no longer "todo" and are skipped.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(WORK, 'tools'))
import ws as wsmod  # noqa: E402

SRC = os.path.join(WORK, 'glossary', 'src')
US = os.path.join(WORK, 'extract', 'us', 'a027')
EN = '9'  # PokéAPI local_language_id for English


def _csv_names(fname, idcol):
    out = {}
    with open(os.path.join(SRC, fname), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['local_language_id'] == EN:
                out[int(r[idcol])] = r['name'].replace("'", '’')
    return out


def _us_bank(n):
    d = json.load(open(os.path.join(US, '%04d.json' % n), encoding='utf-8'))
    return {s['id']: s['text'] for s in d['strings']}


def build_tables():
    """Returns (case_sensitive_map_always, map_mixed_only)."""
    always, mixed = {}, {}
    # species: US 0237 id == national dex
    sp = _csv_names('pokemon_species_names.csv', 'pokemon_species_id')
    for i, t in _us_bank(237).items():
        if 1 <= i <= 493 and t and t != sp.get(i):
            always[t] = sp[i]
    # moves: US 0750 id == move id
    mv = _csv_names('move_names.csv', 'move_id')
    for i, t in _us_bank(750).items():
        if 1 <= i <= 467 and t and i in mv and t != mv[i]:
            always[t] = mv[i]
    # abilities: US 0720 id == ability id
    ab = _csv_names('ability_names.csv', 'ability_id')
    for i, t in _us_bank(720).items():
        if 1 <= i <= 123 and t and i in ab and t != ab[i]:
            always[t] = ab[i]
    # items: US 0222 id == Gen 4 game index
    it = _csv_names('item_names.csv', 'item_id')
    g4 = {}
    with open(os.path.join(SRC, 'item_game_indices.csv'), encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['generation_id'] == '4':
                g4[int(r['game_index'])] = int(r['item_id'])
    for i, t in _us_bank(222).items():
        if i in g4 and g4[i] in it and t and t != it[g4[i]] and len(t) > 2:
            if t.lower() == it[g4[i]].lower() and t != t.upper():
                continue           # pure case variant (e.g. 'Thunderstone' vs 'Thunder Stone' is not)
            always[t] = it[g4[i]]
    # types: CAPS -> Title, only in mixed-case strings
    for t in _us_bank(735).values():
        if t and t.isupper():
            mixed[t] = t.capitalize()
    # generic Gen-4 caps terms
    mixed.update({'TRAINERS': 'Trainers', 'TRAINER': 'Trainer'})
    # 'Stick' (-> Leek) is also an ordinary English word; leave it to a human
    always.pop('Stick', None)
    # drop identity / nonsense entries
    always = {k: v for k, v in always.items() if k != v and k.strip('-? ')}
    return always, mixed


def _compile(m):
    if not m:
        return None
    keys = sorted(m, key=len, reverse=True)
    return re.compile(r'(?<![A-Za-zé])(' + '|'.join(re.escape(k) for k in keys) + r')(?![A-Za-zé])')


POKE_RE = re.compile(r'POKé(\s?)([A-Z]+)?')
POKE_SPECIAL = {'PARK': 'Park', 'WALKER': 'walker', 'MON': 'mon', 'DEX': 'dex', 'GEAR': 'gear',
                'ATHLON': 'athlon', 'NAV': 'Nav'}


def _poke(m):
    sp, w = m.group(1), m.group(2)
    if not w:
        return 'Poké' + sp
    if sp:
        return 'Poké' + sp + w.capitalize()          # POKé BALL -> Poké Ball, POKé MART -> Poké Mart
    if w in POKE_SPECIAL:
        return 'Poké' + POKE_SPECIAL[w]
    if w.startswith('MON'):
        return 'Pokémon' + w[3:].lower()
    return 'Poké' + w.lower()


class Moderniser:
    def __init__(self):
        self.always, self.mixed = build_tables()
        self.re_always = _compile(self.always)
        self.re_mixed = _compile(self.mixed)
        self.stats = Counter()

    def __call__(self, text):
        # protect tags
        parts = re.split(r'(\{[^{}]*\})', text)
        visible = ''.join(p for p in parts if not p.startswith('{'))
        has_lower = bool(re.search(r'[a-z]', visible.replace('POKé', '')))
        out = []
        for p in parts:
            if p.startswith('{'):
                out.append(p)
                continue
            q = POKE_RE.sub(_poke, p)
            if self.re_always:
                q = self.re_always.sub(lambda m: self._hit('name', self.always[m.group(1)]), q)
            if has_lower and self.re_mixed:
                q = self.re_mixed.sub(lambda m: self._hit('caps', self.mixed[m.group(1)]), q)
            out.append(q)
        return ''.join(out)

    def _hit(self, kind, v):
        self.stats[kind] += 1
        return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ws', default=os.path.join(WORK, 'translate', 'banks'))
    ap.add_argument('--reuse', default=os.path.join(WORK, 'translate', 'us_reuse.jsonl'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--show', type=int, default=0, help='print N modernised examples')
    a = ap.parse_args(argv)

    mod = Moderniser()
    by_bank = defaultdict(dict)
    for line in open(a.reuse, encoding='utf-8'):
        r = json.loads(line)
        if r.get('verdict') == 'likely' and r.get('us_text') is not None:
            by_bank[r['bank']][r['id']] = r

    # Guard: one US string claimed by several v4 strings with *different* zh (the per-bank best-match
    # fallback of us_reuse can pick the neighbour, e.g. 不是 'No' -> US 'YES'). Keep only claimants at the
    # bank's modal id offset (us_id - id); the others are ambiguous and are not seeded (and are reset
    # if an earlier run seeded them).
    zh_of = {}
    for bank in by_bank:
        ep = os.path.join(WORK, 'extract', 'v4', 'a027', '%04d.json' % bank)
        if os.path.exists(ep):
            for st in json.load(open(ep, encoding='utf-8'))['strings']:
                zh_of[(bank, st['id'])] = st['text']
    claims = defaultdict(list)
    offs = defaultdict(Counter)
    for bank, recs in by_bank.items():
        for i, r in recs.items():
            claims[(r['us_bank'], r['us_id'])].append(r)
            offs[bank][r['us_id'] - i] += 1
    ambiguous = set()
    for rs in claims.values():
        if len({zh_of.get((r['bank'], r['id'])) for r in rs}) > 1:
            for r in rs:
                if r['us_id'] - r['id'] != offs[r['bank']].most_common(1)[0][0]:
                    ambiguous.add((r['bank'], r['id']))

    c = Counter()
    shown = 0
    for bank in sorted(by_bank):
        p = os.path.join(a.ws, 'a027', '%04d.json' % bank)
        if not os.path.exists(p):
            c['missing_bank'] += len(by_bank[bank])
            continue
        b = wsmod.load_json(p)
        changed = False
        for e in b['strings']:
            r = by_bank[bank].get(e['id'])
            if r is None:
                continue
            if (bank, e['id']) in ambiguous:
                if e.get('status') == 'tm' and e.get('origin') == 'us':
                    # pointer only: never copy US text into notes
                    e['notes'] = (e.get('notes') + ' | ' if e.get('notes') else '') + \
                        'seed rejected us [ambiguous US match] (candidate US %04d#%d; text not kept)' % (r['us_bank'], r['us_id'])
                    e['en'], e['status'], e['origin'] = None, 'todo', None
                    changed = True
                    c['reset_ambiguous'] += 1
                else:
                    c['skipped_ambiguous'] += 1
                continue
            if e.get('status') != 'todo' or e.get('en') is not None:
                c['skipped_existing'] += 1
                continue
            if 'seed rejected us' in (e.get('notes') or ''):
                c['skipped_previously_rejected'] += 1
                continue
            us = r['us_text']
            if not us.strip():
                c['skipped_blank_us'] += 1
                continue
            en = mod(us)
            e['en'] = en
            e['status'] = 'tm'
            e['origin'] = 'us'
            note = 'US %04d/%d' % (r['us_bank'], r['us_id'])
            if en != us:
                note += '; modernised from US %04d#%d' % (r['us_bank'], r['us_id'])   # pointer only: never copy US text into notes
                c['modernised'] += 1
                if shown < a.show:
                    print('%d/%d  %s\n      -> %s' % (bank, e['id'], us, en))
                    shown += 1
            e['notes'] = (e.get('notes') + ' | ' if e.get('notes') else '') + note
            changed = True
            c['applied'] += 1
        if changed and not a.dry_run:
            wsmod.save_json(__import__('pathlib').Path(p), b)
    print(json.dumps({'counts': c, 'replacements': mod.stats,
                      'table_sizes': {'names': len(mod.always), 'caps': len(mod.mixed)}}, indent=1))


if __name__ == '__main__':
    main()
