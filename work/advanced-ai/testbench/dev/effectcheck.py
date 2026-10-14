"""Does the hack implement an item or ability? One AI-vs-AI turn, measured in the emulator.

  .venv/bin/python work/advanced-ai/testbench/dev/effectcheck.py --rom ROM --payload P [CASE ...]
                                                                  (one emulator per case; cases below)

Ported from the Spanish workspace's qa/ai_research/effectcheck.py (dc8577c) into the test bench: its imports
(lib/tbpaths.py), the ROM and its payload as arguments (the Spanish tool always read its own build).

Each case plays the same battle twice with the same battle seed, with and without the effect, both sides
knowing one move (versus/aivsai.py's Duel, the original AI on both sides), and reports the HP each side lost
and which side was hit first. A difference between the two runs is the effect; none means the hack does
not implement it. Found this way: Rocky Helmet 324 inert / 590 works, Soul Dew inert.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import payload  # noqa: E402

EV0 = {'hp': 0, 'atk': 0, 'def': 0, 'spe': 0, 'spa': 0, 'spd': 0}


def mon(species, move, level=50, ability='Run Away', item=None):
    return {'species': species, 'level': level, 'moves': [move], 'ability': ability, 'item': item, 'evs': EV0}


# case: (trainer side, player side) with the effect, then without it
CASES = {
    'bulletproof': ((mon('Gengar', 'Sludge Bomb'), mon('Snorlax', 'Splash', ability='Bulletproof')),
                    (mon('Gengar', 'Sludge Bomb'), mon('Snorlax', 'Splash'))),
    'lagging_tail': ((mon('Jolteon', 'Tackle', item='Lagging Tail'), mon('Snorlax', 'Tackle')),
                     (mon('Jolteon', 'Tackle'), mon('Snorlax', 'Tackle'))),
    'power_herb': ((mon('Venusaur', 'Solar Beam', item='Power Herb'), mon('Snorlax', 'Splash')),
                   (mon('Venusaur', 'Solar Beam'), mon('Snorlax', 'Splash'))),
    'light_ball': ((mon('Pikachu', 'Thunderbolt', item='Light Ball'), mon('Snorlax', 'Splash')),
                   (mon('Pikachu', 'Thunderbolt'), mon('Snorlax', 'Splash'))),
    'thick_club': ((mon('Marowak', 'Earthquake', item='Thick Club'), mon('Snorlax', 'Splash')),
                   (mon('Marowak', 'Earthquake'), mon('Snorlax', 'Splash'))),
    'focus_sash': ((mon('Mewtwo', 'Psystrike', level=100), mon('Pichu', 'Splash', level=20, item='Focus Sash')),
                   (mon('Mewtwo', 'Psystrike', level=100), mon('Pichu', 'Splash', level=20))),
    'sitrus_berry': ((mon('Machamp', 'Tackle'), mon('Snorlax', 'Splash', item='Sitrus Berry')),
                     (mon('Machamp', 'Tackle'), mon('Snorlax', 'Splash'))),
}


def one(case, k, rom_path):
    import aivsai
    adv, orig = CASES[case][k]
    rom, state, save = aivsai.prepare(rom_path, True, 'effect_%s_%d' % (case, k))
    duel = aivsai.Duel(rom, state, 'control')
    trace = []
    alive = duel.alive_counts

    def watch():
        a = alive()
        if a and duel.cur and duel.cur.get('injected'):
            trace.append((duel.r.frames, duel.active_view(1), duel.active_view(0)))
        return a
    duel.alive_counts = watch
    aivsai.FRAME_LIMIT = 4500
    duel.play({'scenario': case, 'game': k, 'seed': 777, 'adv': {'name': 'a', 'team': [adv]}, 'orig': {'name': 'o', 'team': [orig]}})
    first = {}
    for f, t, p in trace:
        if t['hp'] < t['maxhp'] and 'trainer' not in first:
            first['trainer'] = f
        if p['hp'] < p['maxhp'] and 'player' not in first:
            first['player'] = f
    turn1 = [x for x in trace if x[1]['hp'] < x[1]['maxhp'] or x[2]['hp'] < x[2]['maxhp']]
    t1 = turn1[0] if turn1 else (None, {}, {})
    end = trace[-1] if trace else (None, {}, {})
    print('%s %s: first hit on %s; after the first hit: trainer %s/%s, player %s/%s; at the end: trainer %s/%s, player %s/%s' % (
        case, 'with' if k == 0 else 'without', min(first, key=first.get) if first else 'nobody',
        t1[1].get('hp'), t1[1].get('maxhp'), t1[2].get('hp'), t1[2].get('maxhp'),
        end[1].get('hp'), end[1].get('maxhp'), end[2].get('hp'), end[2].get('maxhp')), flush=True)


def main():
    if sys.argv[1:2] == ['--one']:
        return one(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cases', nargs='*', help='default: %s' % ', '.join(CASES))
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the battles
    for case in a.cases or list(CASES):
        for k in (0, 1):
            subprocess.run([sys.executable, __file__, '--one', case, str(k), os.path.abspath(a.rom)],
                           stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
