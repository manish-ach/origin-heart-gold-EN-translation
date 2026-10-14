"""What the simulator covers of the trainer pool: every move, ability and item the six-Pokemon trainer teams use,
weighted by how many sets use it, against the simulator's C sources.

  .venv/bin/python work/advanced-ai/testbench/sim/coverage.py [--rom ROM] [--pool | --random [FILE]] [--all]

- A move is covered when its quality is one the engine runs from the move data (damage, status, stat changes,
  recovery, drain; sim/move.c) and its effect code is not in KNOWN_SPECIAL, or when move.c / damage.c name its
  effect code or its move id. The rest is listed: code the simulator does not have yet.
- An ability or item is covered when the C sources name its constant (A_..., I_...) or, for items, the generated
  boost and resist tables hold it; the rest does nothing in the simulator.
--pool: only the level-80 teams aivsai draws from (default: all 209). --random: the extra teams instead
(gen_simdata.py's extra_teams.json in the ROM's build directory, or FILE), plus the share of lib/randteams.py's drawable moves that are not covered
(the random generator draws them uniformly). --all: list the covered ones too.
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import aicalc  # noqa: E402
import aiteams  # noqa: E402
import simbuild  # noqa: E402
from gen_simdata import MIN_LEVEL, extra_path, extra_teams, ident  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

SOURCES = ['move.c', 'damage.c', 'battle.c']
GENERIC = {0, 1, 2, 3, 4, 5, 6, 7, 8}       # Q_DAMAGE .. Q_DRAIN: the data drives them
# effect codes of generic-quality moves whose behavior the move data does not express (by the moves that carry them)
KNOWN_SPECIAL = {
    105: 'Thief, Covet (steal the item)', 119: 'Fury Cutter (power grows)', 122: 'Present (random power or heal)',
    128: 'Pursuit (doubles on a switch)', 135: 'Hidden Power (type from IVs)', 159: 'Uproar (no sleep)',
    223: 'Feint (breaks Protect)', 224: 'Bug Bite (eats the berry)', 246: 'Last Resort (needs the other moves)',
    287: 'Smack Down (grounds)', 302: 'Echoed Voice (power grows)', 341: 'Fell Stinger (+3 Atk on a KO)',
    384: 'Anchor Shot (traps)', 392: 'Throat Chop (no sound moves)', 393: 'Pollen Puff (heals an ally)',
    456: 'Glaive Rush (double damage taken)', 458: 'Salt Cure (residual damage)', 466: 'Rage Fist (power grows)',
}


def handled():
    text = ''.join(open(os.path.join(HERE, f)).read() for f in SOURCES)
    codes = {int(n) for n in re.findall(r'\bE_[A-Z_]+ = (\d+)', text)}
    codes |= {int(n) for n in re.findall(r'case (\d+):', text)}
    names = set(re.findall(r'\b([AIM]_[A-Z0-9_]+)\b', text))
    return codes, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default=simbuild.DEFAULT_ROM)
    ap.add_argument('--pool', action='store_true')
    ap.add_argument('--random', nargs='?', const='')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    d = aiteams.data(a.rom)
    codes, names = handled()
    if a.random is not None:
        teams = extra_teams(a.random or extra_path(a.rom))
        drawable(d, codes, names)
    else:
        teams = [t for t in aiteams.trainer_teams(a.rom, 6) if not a.pool or min(s['level'] for s in t['team']) >= MIN_LEVEL]
    boost_resist = {d.id('item', n) for n in list(aicalc.TYPE_ITEMS) + list(aicalc.RESIST_BERRIES)}
    moves, abilities, items = collections.Counter(), collections.Counter(), collections.Counter()
    for t in teams:
        for s in t['team']:
            abilities[d.id('ability', s['ability'])] += 1
            if s['item']:
                items[d.id('item', s['item'])] += 1
            for m in s['moves']:
                moves[d.id('move', m)] += 1
    print('%d teams, %d sets: %d moves, %d abilities, %d items' % (
        len(teams), sum(len(t['team']) for t in teams), len(moves), len(abilities), len(items)))

    rows = []
    for mv, n in moves.items():
        r = d.move(mv)
        rows.append((move_ok(d, mv, codes, names), n, d.move_name[mv], r['quality'], r['effect'],
                     KNOWN_SPECIAL.get(r['effect'], '')))
    show('moves', rows, a.all, lambda x: '%s (quality %d, effect %d)%s' % (x[2], x[3], x[4], ': ' + x[5] if x[5] else ''))

    rows = [('A_' + ident(d.ability_name[ab]) in names, n, d.ability_name[ab]) for ab, n in abilities.items()]
    show('abilities', rows, a.all, lambda x: x[2])
    rows = [('I_' + ident(d.item_name[it]) in names or it in boost_resist, n, '%s (%d)' % (d.item_name[it], it))
            for it, n in items.items()]
    show('items', rows, a.all, lambda x: x[2])


def move_ok(d, mv, codes, names):
    r = d.move(mv)
    special = r['effect'] in KNOWN_SPECIAL
    return 'M_' + ident(d.move_name[mv]) in names or (r['quality'] in GENERIC and not special) or \
        (r['effect'] in codes and not special)


def drawable(d, codes, names):
    """randteams.random_team's move pool after aiteams.random_team's bans: how much of it the simulator lacks."""
    import randteams
    banned = randteams.PLAYER_NO | {aiteams.LEAF_TORNADO}
    pool = [m for m in range(1, randteams.MAX_MOVE) if m in d.move_name and d.move_name[m] != 'Struggle'
            and d.move_name[m] not in banned]
    miss = [m for m in pool if not move_ok(d, m, codes, names)]
    dmg = sum(1 for m in miss if d.move(m)['class'] and d.move(m)['power'])
    print('drawable moves: %d of %d not covered (%.1f%%; %d damaging, %d other); a team of 24 draws has none with '
          'probability %.3f' % (len(miss), len(pool), 100 * len(miss) / len(pool), dmg, len(miss) - dmg,
                                (1 - len(miss) / len(pool)) ** 24))


def show(kind, rows, everything, fmt):
    ok = [x for x in rows if x[0]]
    uses = sum(x[1] for x in rows)
    print('\n%s: %d of %d covered (%d of %d uses, %.1f%%)' % (
        kind, len(ok), len(rows), sum(x[1] for x in ok), uses, 100 * sum(x[1] for x in ok) / max(uses, 1)))
    print('  not covered: ' + ', '.join('%s %d' % (fmt(x), x[1]) for x in sorted(rows, key=lambda x: -x[1]) if not x[0]))
    if everything:
        print('  covered: ' + ', '.join('%s %d' % (fmt(x), x[1]) for x in sorted(ok, key=lambda x: -x[1])))


if __name__ == '__main__':
    main()
