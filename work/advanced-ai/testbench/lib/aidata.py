"""The hack's battle data, read from a ROM, for the AI bench (bench/aibench.py), its scenarios and every other tool.

  .venv/bin/python work/advanced-ai/testbench/lib/aidata.py --rom ROM NAME ...   # look up species, moves, abilities, items

Ported from the Spanish workspace's tools/aidata.py (dc8577c). Changes: the names come from lib/names.json (lib/names.py:
the Spanish workspace's frozen English names by ROM id) instead of its text/en bank and glossary files; the ROM is an
argument.

Everything comes from the ROM under test, because the hack changes the official data (Blastoise is
Water/Steel, Charizard has 90 Attack, Thunderbolt has 90 power, Fairy is type 9):
- species `a/0/0/2` (52 bytes): base HP, Atk, Def, Spe, SpA, SpD at 0-5, types at 6-7, growth rate at
  0x13, abilities u16 at 0x16/0x18, hidden ability at 0x1A;
- moves `extra/new_move_data.narc` (Gen 5 format, 40 bytes): type 0, quality 1, class 2 (0 status,
  1 physical, 2 special), power 3, accuracy 4 (101 never misses), PP 5, priority 6 (signed), hits 7
  (min low nibble, max high nibble; 0 one hit), status u16 8, status chance 10, crit stage 14, flinch
  chance 15, effect u16 16, recoil 18 (signed % of the damage: negative recoil, positive drain), heal %
  19, target 20, stat changes 21-29 (three stat ids 1 Atk 2 Def 3 SpA 4 SpD 5 Spe 6 Acc 7 Eva, three
  signed stages, three chances; 0 on a status move means always), flags u32 32 (bit 0 contact, 7 punch,
  8 sound, 29 bite, 30 ball/bomb);
- evolutions `a/0/3/4` (60 bytes, ten (method, parameter, species) u16 triples; method 0 = none);
- the engine's type chart: overlay 14 at 0x0224DA40, 18 x 18 bytes, attacker row, defender column,
  0 / 2 / 4 / 8 = immune / half / neutral / double; Fairy is index 9;
- names from lib/names.json (frozen, by ROM id; never the ROM's own text, which is Spanish on rc44).
damage() is the Gen 5 formula without items or most abilities, for checking that a scenario's
answer holds with margin (the bench never uses it to grade the AI).
"""
import json
import os
import re
import struct

import ndspy.narc
import ndspy.rom

NAMES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'names.json')

TYPES = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel', 'Fairy',
         'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark']
TYPE_CHART = (14, 0x0224DA40)
# the Protect handler's table (event 0x2F at 0x0223D400): after a move with one of these 13 ids the streak byte (+0x2DD)
# counts on; after any other move the handler sets it to 0 first (DS traces T4c, qa/aivsai/rc33_PR.md)
STREAK_TABLE = (14, 0x022514FC, 13)
STREAK_EFFECTS = {111, 116, 278, 306, 355, 361, 376, 383, 441, 451}    # Protect's kin, Endure, Wide/Quick Guard, Mat Block
# Relations every Gen 6+ chart has; a misplaced or wrong chart fails here.
CHART_FACTS = [('Normal', 'Ghost', 0), ('Ghost', 'Normal', 0), ('Electric', 'Ground', 0), ('Ground', 'Flying', 0),
               ('Psychic', 'Dark', 0), ('Dragon', 'Fairy', 0), ('Poison', 'Steel', 0), ('Fighting', 'Ghost', 0),
               ('Fire', 'Grass', 2), ('Water', 'Fire', 2), ('Fairy', 'Dragon', 2), ('Ice', 'Dragon', 2),
               ('Normal', 'Rock', 0.5), ('Fire', 'Water', 0.5), ('Steel', 'Steel', 0.5), ('Normal', 'Normal', 1)]
STATS = ['hp', 'atk', 'def', 'spe', 'spa', 'spd']
# bank 33's order; nature n raises STATS[1 + n // 5] by 10% and lowers STATS[1 + n % 5] (arm9 table at 0x020FE869)
NATURES = ['Hardy', 'Lonely', 'Brave', 'Adamant', 'Naughty', 'Bold', 'Docile', 'Relaxed', 'Impish', 'Lax', 'Timid',
           'Hasty', 'Serious', 'Jolly', 'Naive', 'Modest', 'Mild', 'Quiet', 'Bashful', 'Rash', 'Calm', 'Gentle', 'Sassy',
           'Careful', 'Quirky']
PHYSICAL, SPECIAL, STATUS = 1, 2, 0
# Abilities that make a holder immune to a move type (checked by the scenarios that use them).
TYPE_IMMUNE_ABILITIES = {'Levitate': 'Ground', 'Flash Fire': 'Fire', 'Water Absorb': 'Water', 'Volt Absorb': 'Electric',
                         'Lightningrod': 'Electric', 'Motor Drive': 'Electric', 'Storm Drain': 'Water',
                         'Sap Sipper': 'Grass', 'Dry Skin': 'Water'}
GROWTH = {0: lambda n: n ** 3,
          1: lambda n: (n ** 3 * (100 - n) // 50 if n <= 50 else n ** 3 * (150 - n) // 100 if n <= 68 else
                        n ** 3 * ((1911 - 10 * n) // 3) // 500 if n <= 98 else n ** 3 * (160 - n) // 100),
          2: lambda n: (n ** 3 * (24 + (n + 1) // 3) // 50 if n <= 15 else n ** 3 * (14 + n) // 50 if n <= 36 else
                        n ** 3 * (32 + n // 2) // 50),
          3: lambda n: 6 * n ** 3 // 5 - 15 * n ** 2 + 100 * n - 140, 4: lambda n: 4 * n ** 3 // 5,
          5: lambda n: 5 * n ** 3 // 4}


def norm(name):
    return re.sub(r'[^a-z0-9]', '', name.lower().replace('é', 'e'))


def nature_id(name):
    return [norm(n) for n in NATURES].index(norm(name))


class Data:
    def __init__(self, rom_path):
        self.rom_path = rom_path
        rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
        self.personal = ndspy.narc.NARC(rom.getFileByName('a/0/0/2')).files
        self.moves = ndspy.narc.NARC(rom.getFileByName('extra/new_move_data.narc')).files
        self.evolutions = ndspy.narc.NARC(rom.getFileByName('a/0/3/4')).files
        ov = rom.loadArm9Overlays()[TYPE_CHART[0]]
        code = rom.files[ov.fileID]
        o = TYPE_CHART[1] - ov.ramAddress
        self.chart = [list(code[o + 18 * a:o + 18 * a + 18]) for a in range(18)]
        o = STREAK_TABLE[1] - ov.ramAddress
        self.streak_moves = list(struct.unpack_from('<%dH' % STREAK_TABLE[2], code, o))
        for a, d, m in CHART_FACTS:
            got = self.type_mult(TYPES.index(a), [TYPES.index(d)])
            assert got == m, 'type chart: %s vs %s is %s, expected %s' % (a, d, got, m)
        with open(NAMES, encoding='utf-8') as f:
            names = json.load(f)
        species = names['species']
        self.names = {'species': {}, 'move': {}, 'ability': {}, 'item': {}}
        self.species_name = {}
        for i, s in enumerate(species):
            if s and i < len(self.personal):
                self.names['species'].setdefault(norm(s), i)
                self.species_name[i] = s
        self.move_name, self.ability_name, self.item_name = {}, {}, {}
        for kind, out in (('move', self.move_name), ('ability', self.ability_name), ('item', self.item_name)):
            for k, en in names[kind].items():
                if en and int(k):
                    if kind == 'item':
                        # the hack re-added some items under their old names (Rocky Helmet 324/590, Eviolite 110/584,
                        # Weakness Policy 111/600, Air Balloon 252/576): the later id is the one the battle engine
                        # handles (a holder of 324 took Tackles with no Rocky Helmet damage, 590 dealt a sixth each hit)
                        self.names[kind][norm(en)] = max(int(k), self.names[kind].get(norm(en), 0))
                    else:
                        self.names[kind].setdefault(norm(en), int(k))
                    out[int(k)] = en

    def id(self, kind, name):
        if isinstance(name, int):
            return name
        key = norm(name)
        if key not in self.names[kind]:
            near = [n for n in self.names[kind] if n.startswith(key[:4])][:8]
            raise KeyError('unknown %s %r (close: %s)' % (kind, name, near))
        return self.names[kind][key]

    def species(self, sp):
        r = self.personal[self.id('species', sp)]
        return {'base': dict(zip(STATS, r[0:6])), 'types': sorted({r[6], r[7]}), 'growth': r[0x13],
                'abilities': [struct.unpack_from('<H', r, o)[0] for o in (0x16, 0x18, 0x1A)]}

    def move(self, mv):
        r = self.moves[self.id('move', mv)]
        return {'id': self.id('move', mv), 'type': r[0], 'quality': r[1], 'class': r[2], 'power': r[3],
                'accuracy': r[4], 'pp': r[5], 'priority': struct.unpack_from('b', r, 6)[0],
                'status': struct.unpack_from('<H', r, 8)[0], 'chance': r[10], 'effect': struct.unpack_from('<H', r, 16)[0],
                'target': r[20], 'flags': struct.unpack_from('<I', r, 32)[0],
                'hits': (r[7] & 0xF, r[7] >> 4) if r[7] else (1, 1), 'crit_stage': r[14], 'flinch': r[15],
                'recoil': struct.unpack_from('b', r, 18)[0], 'heal': r[19],
                'stat_changes': [(r[21 + k], struct.unpack_from('b', r, 24 + k)[0], r[27 + k]) for k in range(3) if r[21 + k]]}

    def evolves(self, sp):
        """True when the species has an evolution (what Eviolite asks)."""
        r = self.evolutions[self.id('species', sp)]
        return any(struct.unpack_from('<H', r, 6 * k)[0] for k in range(len(r) // 6))

    def type_mult(self, atk_type, def_types):
        m = 1.0
        for t in set(def_types):
            m *= self.chart[atk_type][t] / 4
        return m

    def effectiveness(self, mv, defender):
        """Type multiplier of a move against a defender dict (species, ability); 0 for ability immunities."""
        m = self.move(mv)
        if m['class'] == STATUS:
            return None
        ability = defender.get('ability')
        if ability and TYPE_IMMUNE_ABILITIES.get(ability) == TYPES[m['type']]:
            return 0.0
        return self.type_mult(m['type'], defender.get('types') or self.species(defender['species'])['types'])

    def stats(self, sp, level, evs=None, ivs=31, nature=None):
        base = self.species(sp)['base']
        evs = evs or {}
        n = nature_id(nature) if nature else 0
        out = {}
        for k, s in enumerate(STATS):
            core = (2 * base[s] + ivs + evs.get(s, 0) // 4) * level // 100
            out[s] = (1 if base[s] == 1 else core + level + 10) if s == 'hp' else core + 5   # Shedinja: 1 HP
            if k and n // 5 != n % 5 and k - 1 in (n // 5, n % 5):
                out[s] = out[s] * (110 if k - 1 == n // 5 else 90) // 100
        return out

    def exp_for(self, sp, level):
        return GROWTH[self.species(sp)['growth']](level)

    def damage(self, mv, attacker, defender, weather=None):
        """(min, max) damage of a non-crit hit: attacker/defender dicts with species, level, stats,
        optional types, ability, status; weather 'rain' or 'sun'."""
        m = self.move(mv)
        if m['class'] == STATUS or not m['power']:
            return (0, 0)
        eff = self.effectiveness(mv, defender)
        a_types = attacker.get('types') or self.species(attacker['species'])['types']
        if m['class'] == PHYSICAL:
            a, d = attacker['stats']['atk'], defender['stats']['def']
        else:
            a, d = attacker['stats']['spa'], defender['stats']['spd']
        base = (2 * attacker['level'] // 5 + 2) * m['power'] * a // d // 50 + 2
        if weather == 'rain':
            base = base * {10: 0.5, 11: 1.5}.get(m['type'], 1)
        if weather == 'sun':
            base = base * {10: 1.5, 11: 0.5}.get(m['type'], 1)
        out = []
        for roll in (85, 100):
            v = int(base * roll / 100)
            if m['type'] in a_types:
                v = int(v * (2 if attacker.get('ability') == 'Adaptability' else 1.5))
            v = int(v * eff)
            if attacker.get('status') == 'brn' and m['class'] == PHYSICAL and attacker.get('ability') != 'Guts':
                v //= 2
            out.append(max(1, v) if eff else 0)
        return tuple(out)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='+')
    ap.add_argument('--rom', required=True)
    a = ap.parse_args()
    d = Data(a.rom)
    for n in a.names:
        for kind in ('species', 'move', 'ability', 'item'):
            try:
                i = d.id(kind, n)
            except KeyError:
                continue
            if kind == 'species':
                s = d.species(i)
                print('species %d %s: %s, base %s, abilities %s' % (i, d.species_name[i], '/'.join(TYPES[t] for t in s['types']),
                      s['base'], [d.ability_name.get(x, x) for x in s['abilities']]))
            elif kind == 'move':
                m = d.move(i)
                print('move %d %s: %s %s power %d acc %d pri %d status %d chance %d effect %d target %d' % (
                    i, d.move_name[i], TYPES[m['type']], ['status', 'physical', 'special'][m['class']], m['power'],
                    m['accuracy'], m['priority'], m['status'], m['chance'], m['effect'], m['target']))
            else:
                print('%s %d %s' % (kind, i, n))


if __name__ == '__main__':
    main()
