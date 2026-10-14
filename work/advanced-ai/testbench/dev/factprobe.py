"""Engine facts, measured in short battles: tools/aivsai.py's Duel with set teams, the original AI on both sides
unless a case says otherwise, moves forced per turn where a case says so (the move id is replaced at the action
setter).

  .venv/bin/python work/advanced-ai/testbench/dev/factprobe.py CASE [CASE ...] --rom ROM --payload P [--workers 2]
                                                                [--dump] [--heap DIR]

Ported from the Spanish workspace's qa/ai_research/factprobe.py (dc8577c) into the test bench: its imports (lib/tbpaths.py),
the ROM and its payload as arguments, the Violet Gym save from lib/saves.py, results under RUNS/factprobe/. The Spanish results are in its qa/aivsai/ENGINE_FACTS.md.

Each battle writes RUNS/factprobe/<case>_<k>.log: the teams, a line per turn with HP, status and stat stages,
the game's own messages, the advanced AI's debug records when it plays (DEBUG: its simulated damage both ways and
the options it weighed), and with --dump both active battle Pokémon's first 0x340 bytes at every turn (DUMP).

--heap DIR writes all of main RAM (0x02000000-0x023FFFFF) at the first AI poll of turns 1-12 to DIR/<case>_<k>_t<turn>.bin,
and DIR/<case>_<k>.json with each turn's main pointer and battle Pokémon addresses. Round 3 compared these dumps between
a battle with an effect and the same battle without it (Trick Room, Leech Seed, Yawn, terrain, Taunt, Encore, Tailwind,
Substitute, semi-invulnerable turns).
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import payload  # noqa: E402

WORK = tbpaths.WORK
OUT = os.path.join(tbpaths.RUNS, 'factprobe')
EV0 = {'hp': 0, 'atk': 0, 'def': 0, 'spe': 0, 'spa': 0, 'spd': 0}


def mon(species, moves, level=50, ability='Run Away', item=None, hp=None, status=None, evs=None):
    m = {'species': species, 'level': level, 'moves': moves, 'ability': ability, 'item': item, 'evs': evs or EV0}
    if hp is not None:
        m['hp'] = hp
    if status:
        m['status'] = status
    return m


BLISSEY_WALL = mon('Blissey', ['Splash', 'Growl', 'Charm', 'FeatherDance'], level=100)

# case: battles of (trainer side team, player side team, frame limit, forced moves {side: moves by turn, cycled},
# original AI on both sides[, the trainer's items]). Side 1 is the trainer's, side 0 the player's.
CASES = {
    'wp': [([mon('Snorlax', ['Splash'], item='Weak. Policy')], [mon('Machamp', ['Brick Break'])], 2400, None, True)],
    'gale': [([mon('Talonflame', ['Wing Attack'], ability='Gale Wings', hp=0.5)], [mon('Electrode', ['Tackle'], level=100)], 2400, None, True),
             ([mon('Talonflame', ['Wing Attack'], ability='Gale Wings')], [mon('Electrode', ['Tackle'], level=100)], 2400, None, True)],
    'charge': [([mon('Pidgeot', ['Rock Wrecker', 'Sky Attack', 'Hyper Beam'])], [mon('Steelix', ['Splash'], level=100)], 5400,
                {1: ['Rock Wrecker', 'Rock Wrecker', 'Sky Attack', 'Sky Attack', 'Hyper Beam', 'Hyper Beam', 'Rock Wrecker']}, True)],
    'damp': [([mon('Quagsire', ['Water Gun'], ability='Damp', hp=0.5)], [mon('Snorlax', ['Splash'])], 3000, None, True),
             ([mon('Quagsire', ['Water Gun'], ability='Oblivious', hp=0.5)], [mon('Snorlax', ['Splash'])], 3000, None, True)],
    'armor': [([mon('Machamp', ['Tackle'])], [mon('Snorlax', ['Splash'], ability='Battle Armor')], 2400, None, True),
              ([mon('Machamp', ['Tackle'])], [mon('Snorlax', ['Splash'])], 2400, None, True)],
    'mind': [([mon('Poliwrath', ['Mind Reader', 'Lock-On', 'Zap Cannon', 'Inferno'])], [BLISSEY_WALL], 9000,
              {1: ['Mind Reader', 'Zap Cannon', 'Lock-On', 'Inferno']}, True)],
    'mindctl': [([mon('Poliwrath', ['Zap Cannon', 'Inferno', 'DynamicPunch'])], [BLISSEY_WALL], 6000,
                 {1: ['Zap Cannon', 'Inferno', 'DynamicPunch']}, True)],
    'megasol': [([mon('Meganium', ['Solar Beam'], ability='Mega Sol')], [mon('Venusaur', ['Solar Beam'], ability='Overgrow')], 4200, None, True)],
    'megasol_adv': [([mon('Meganium', ['Solar Beam'], ability='Mega Sol'), mon('Snorlax', ['Tackle'])],
                     [mon('Venusaur', ['Solar Beam'], ability='Overgrow')], 4200, None, False)],
    'bright': [([mon('Pidgey', ['Pound', 'Tackle', 'Scratch', 'Wing Attack'], level=5)],
                [mon('Blissey', ['Splash', 'Growl', 'Charm', 'FeatherDance'], level=100, item='BrightPowder')], 40000, None, True)],
    'brightctl': [([mon('Pidgey', ['Pound', 'Tackle', 'Scratch', 'Wing Attack'], level=5)], [BLISSEY_WALL], 15000, None, True)],
    'macho': [([mon('Jolteon', ['Tackle'], item='Macho Brace')], [mon('Talonflame', ['Tackle'])], 2400, None, True),
              ([mon('Jolteon', ['Tackle'])], [mon('Talonflame', ['Tackle'])], 2400, None, True)],
    # the advanced AI (not control) against a foe whose Sp. Atk drops each turn, and against Moody
    'stages': [([mon('Blissey', ['Pound', 'Splash'])], [mon('Exeggutor', ['Leaf Storm'])], 5000, None, False)],
    'tox': [([mon('Suicune', ['Surf'], status='tox')], [mon('Walrein', ['Splash'], level=48)], 3000, None, False)],
    'turns': [([mon('Ambipom', ['Fake Out', 'Aerial Ace'])], [mon('Nidoqueen', ['Protect', 'Splash'], level=60)], 5400,
               {1: ['Aerial Ace', 'Aerial Ace', 'Aerial Ace', 'Fake Out', 'Aerial Ace'], 0: ['Splash', 'Protect', 'Splash', 'Splash', 'Splash']}, True)],
    'recharge': [([mon('Snorlax', ['Hyper Beam', 'Tackle'])], [mon('Steelix', ['Splash'], level=100)], 4200,
                  {1: ['Hyper Beam', 'Tackle', 'Tackle', 'Hyper Beam', 'Tackle']}, True)],
    'moody': [([mon('Blissey', ['Pound', 'Splash'])], [mon('Exeggutor', ['Giga Drain', 'Psychic', 'Energy Ball', 'Leaf Blade'], ability='Moody')], 5000, None, False)],
    'reentry': [([mon('Ambipom', ['U-turn', 'Fake Out']), mon('Smeargle', ['U-turn', 'Fake Out'])], [mon('Snorlax', ['Splash'], level=60)], 4200,
                 {1: ['U-turn', 'U-turn', 'Fake Out', 'Fake Out', 'U-turn', 'Fake Out']}, True)],
    'ironball': [([mon('Jolteon', ['Tackle'], item='Iron Ball')], [mon('Talonflame', ['Tackle'])], 1500, None, True)],
    'anklet': [([mon('Jolteon', ['Tackle'], item='Power Anklet')], [mon('Talonflame', ['Tackle'])], 1500, None, True)],
    'tox88': [([mon('Suicune', ['Surf'], status='tox')], [mon('Walrein', ['Splash'], level=48)], 1800, None, False)],
    'toxfh': [([mon('Suicune', ['Surf', 'Ice Beam'], status='tox', evs={'hp': 252, 'spd': 252})],
               [mon('Walrein', ['Surf', 'Aurora Beam'], level=48)], 1500, None, False, ['Full Heal'])],
    'fly': [([mon('Snorlax', ['Tackle'])], [mon('Pidgeot', ['Fly', 'Outrage'])], 4200, {0: ['Fly', 'Fly', 'Outrage']}, True)],
    'toxmove': [([mon('Suicune', ['Surf'])], [mon('Walrein', ['Toxic', 'Splash'], level=48)], 3000, {0: ['Toxic', 'Splash']}, True)],
    'psn': [([mon('Suicune', ['Surf'], status='psn')], [mon('Walrein', ['Splash'], level=48)], 1800, None, False)],
    # round 3 (--heap): each case's last battle is the control, the same battle with Splash in place of the effect
    'trickroom': [([mon('Slowbro', ['Trick Room', 'Splash'])], [mon('Jolteon', ['Splash', 'Tackle'])], 6000,
                   {1: ['Trick Room'] + ['Splash'] * 11, 0: ['Splash', 'Tackle'] * 6}, True),
                  ([mon('Slowbro', ['Trick Room', 'Splash'])], [mon('Jolteon', ['Splash', 'Tackle'])], 6000,
                   {1: ['Splash'] * 12, 0: ['Splash', 'Tackle'] * 6}, True)],
    'leechseed': [([mon('Venusaur', ['Leech Seed', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200,
                   {1: ['Leech Seed'] + ['Splash'] * 9, 0: ['Splash']}, True),
                  ([mon('Snorlax', ['Splash'])], [mon('Venusaur', ['Leech Seed', 'Splash'])], 4200,
                   {0: ['Leech Seed'] + ['Splash'] * 9, 1: ['Splash']}, True),
                  ([mon('Venusaur', ['Leech Seed', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200,
                   {1: ['Splash'], 0: ['Splash']}, True)],
    'yawn': [([mon('Slowbro', ['Yawn', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200,
              {1: ['Yawn'] + ['Splash'] * 9, 0: ['Splash']}, True),
             ([mon('Slowbro', ['Yawn', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200, {1: ['Splash'], 0: ['Splash']}, True)],
    'terrain': [([mon('Slowbro', [t, 'Splash'])], [mon('Snorlax', ['Splash'])], 5400, {1: [t] + ['Splash'] * 11, 0: ['Splash']}, True)
                for t in ('ElecTerrain', 'GrassTerrain', 'MistyTerrain', 'PsychTerrain')] +
               [([mon('Raikou', ['Splash'], ability='Thunder Roar')], [mon('Snorlax', ['Splash'])], 5400, {1: ['Splash'], 0: ['Splash']}, True),
                ([mon('Tapu Koko', ['Splash'], ability='Elec. Surge')], [mon('Snorlax', ['Splash'])], 5400, {1: ['Splash'], 0: ['Splash']}, True),
                ([mon('Slowbro', ['Splash'])], [mon('Snorlax', ['Splash'])], 5400, {1: ['Splash'], 0: ['Splash']}, True)],
    'taunt': [([mon('Jolteon', ['Taunt', 'Splash'])], [mon('Snorlax', ['Tackle', 'Splash'])], 4200,
               {1: ['Taunt'] + ['Splash'] * 9, 0: ['Tackle']}, True),
              ([mon('Jolteon', ['Taunt', 'Splash'])], [mon('Snorlax', ['Tackle', 'Splash'])], 4200, {1: ['Splash'], 0: ['Tackle']}, True)],
    'encore': [([mon('Slowbro', ['Encore', 'Splash'])], [mon('Snorlax', ['Growl', 'Tackle'])], 4200,
                {1: ['Splash', 'Encore'] + ['Splash'] * 8, 0: ['Growl']}, True),
               ([mon('Slowbro', ['Encore', 'Splash'])], [mon('Snorlax', ['Growl', 'Tackle'])], 4200, {1: ['Splash'], 0: ['Growl']}, True)],
    'tailwind': [([mon('Pidgeot', ['Tailwind', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200,
                  {1: ['Tailwind'] + ['Splash'] * 9, 0: ['Splash']}, True),
                 ([mon('Pidgeot', ['Tailwind', 'Splash'])], [mon('Snorlax', ['Splash'])], 4200, {1: ['Splash'], 0: ['Splash']}, True)],
    'substitute': [([mon('Snorlax', ['Substitute', 'Splash'])], [mon('Pidgey', ['Tackle', 'Splash'], level=10)], 4200,
                    {1: ['Substitute'] + ['Splash'] * 9, 0: ['Splash'] + ['Tackle'] * 9}, True),
                   ([mon('Snorlax', ['Substitute', 'Splash'])], [mon('Pidgey', ['Tackle', 'Splash'], level=10)], 4200,
                    {1: ['Splash'], 0: ['Splash'] + ['Tackle'] * 9}, True)],
    # at turns 2, 5 and 8 the player's Pokémon is up in the air, underground, under water (k=0: Fly, Dig, Dive; Bounce,
    # a one-turn move in this hack, in between) or vanished, vanished, up with the foe (k=1: Phantom Force, Shadow Force,
    # Sky Drop); on the ground at the other turns
    'semi': [([BLISSEY_WALL], [mon('Pidgeot', ['Fly', 'Dig', 'Bounce', 'Dive'])], 6000,
              {1: ['Splash'], 0: ['Fly', 'Fly', 'Bounce', 'Dig', 'Dig', 'Bounce', 'Dive', 'Dive', 'Bounce']}, True),
             ([BLISSEY_WALL], [mon('Gengar', ['Phantom Force', 'Shadow Force', 'Sky Drop', 'Tackle'])], 6000,
              {1: ['Splash'], 0: ['Phantom Force', 'Phantom Force', 'Tackle', 'Shadow Force', 'Shadow Force', 'Tackle',
                                  'Sky Drop', 'Sky Drop', 'Tackle']}, True),
             ([BLISSEY_WALL], [mon('Pidgeot', ['Wing Attack', 'Splash'])], 6000, {1: ['Splash'], 0: ['Wing Attack']}, True)],
}
RAM = (0x02000000, 0x02400000)


def run_one(case, k, rom_path, dump, heapdir=None):
    import aibench
    import aivsai
    from aidata import Data
    adv, orig, frames, force, control = CASES[case][k][:5]
    items = CASES[case][k][5] if len(CASES[case][k]) > 5 else []
    tag = 'factprobe_%s_%d' % (case, k)
    rom, state, save = aivsai.prepare(rom_path, control, tag)
    if case in ('tox88', 'toxfh'):
        aibench.STATUS_BITS['tox'] = 0x88      # the party status bits that give bad poison in this hack
    d = Data(rom)
    debug, dumps, seen, heap_turns = [], [], set(), {}
    if heapdir:
        os.makedirs(heapdir, exist_ok=True)

    class Probe(aivsai.Duel):
        def _inject(self, a, s):
            if self.cur is not None:
                self.cur['items'] = [d.id('item', x) for x in items]
            super()._inject(a, s)

        def _poll(self, a, s):
            super()._poll(a, s)
            c = self.cur
            if heapdir and c is not None and c.get('injected') and c.get('turn', 99) <= 12 and c.get('turn') not in heap_turns:
                import array
                ram = array.array('I', self.mem.read(RAM[0], RAM[1], 4, False))
                with open(os.path.join(heapdir, '%s_%d_t%d.bin' % (case, k, c['turn'])), 'wb') as f:
                    f.write(ram.tobytes())
                heap_turns[c['turn']] = {'frames': self.r.frames, 'side': self.side, 'main': self.mu.read_long(aibench.MAIN_PTR),
                                         'party': [self.party(sd) for sd in (0, 1)]}
                with open(os.path.join(heapdir, '%s_%d.json' % (case, k)), 'w') as f:
                    json.dump(heap_turns, f)
            if not dump or c is None or not c.get('injected') or (c.get('turn'), self.side) in seen:
                return
            seen.add((c.get('turn'), self.side))
            row = []
            for side in (0, 1):
                party = self.party(side)
                if party:
                    row.append(bytes(self.mu.read_byte(party[0] + i) for i in range(0x340)).hex())
            dumps.append((c.get('turn'), self.side, row))

        def _setter(self, kind):
            base = super()._setter(kind)

            def f(a, s):
                c = self.cur
                # the side of the Pokémon the move is set for (its pokeID, the setter's fifth argument: 1-12 the
                # player's), not the side last polled: a charging Pokémon's move is set by the engine without a poll
                who = self.mu.read_long(self.reg.r13) & 0xFF
                side = 0 if 1 <= who <= 12 else 1
                if kind == 'move' and c is not None and c.get('injected') and force and side in force \
                        and self.reg.r14 != aivsai.REPLACE_LR:
                    plan = force[side]
                    self.reg.r1 = d.id('move', plan[(c.get('turn', 1) - 1) % len(plan)])
                if kind != 'none' and c is not None and c.get('injected') and self.side == 1 and not control \
                        and self.adv_code[0] <= self.reg.r14 < self.adv_code[1]:
                    rec = self.read_debug()
                    rec['turn'] = c.get('turn')
                    debug.append(rec)
                base(a, s)
            return f

    aivsai.FRAME_LIMIT = frames                     # Duel reads it when it is made
    duel = Probe(rom, state, 'control' if control else 'adv')
    game = {'scenario': case, 'game': k, 'seed': 777 + 13 * k, 'adv': {'name': 'trainer', 'team': adv},
            'orig': {'name': 'player', 'team': orig}}
    path = os.path.join(OUT, '%s_%d.log' % (case, k))
    res = aivsai.logged_play(duel, game, path)
    with open(path, 'a') as f:
        f.write('RESULT %s\n' % json.dumps({x: res[x] for x in ('end', 'turns', 'left', 'frames')}))
        for t, sd, row in dumps:
            f.write('DUMP turn %s side %s %s\n' % (t, sd, ' | '.join(row)))
        for r in debug:
            f.write('DEBUG turn %s d_mo %s d_om %s me %s/%s status %s opp %s/%s status %s options %s fallback %s\n' % (
                r.get('turn'), r.get('d_mo'), r.get('d_om'), r['me']['hp'], r['me']['maxhp'], r['me']['status'],
                r['opp']['hp'], r['opp']['maxhp'], r['opp']['status'], r.get('options'), r.get('fallback')))
    for p in (rom, os.path.join(aibench.DSV_DIR, '%s.dsv' % tag)):
        if os.path.lexists(p):
            os.remove(p)


def main():
    if sys.argv[1:2] == ['--one']:
        return run_one(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5] == '1', sys.argv[6] if len(sys.argv) > 6 else None)
    import argparse
    ap = argparse.ArgumentParser(description='Engine facts measured in short battles.')
    ap.add_argument('cases', nargs='+', choices=sorted(CASES))
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--dump', action='store_true', help='log the active battle Pokémon\'s bytes every turn')
    ap.add_argument('--heap', metavar='DIR', help='write all of main RAM at every turn\'s first AI poll into DIR')
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the battles
    os.makedirs(OUT, exist_ok=True)
    if a.heap:
        os.makedirs(a.heap, exist_ok=True)
    jobs = [(c, k) for c in a.cases for k in range(len(CASES[c]))]

    def go(job):
        case, k = job
        subprocess.run([sys.executable, __file__, '--one', case, str(k), a.rom, '1' if a.dump else '0'] +
                       ([os.path.abspath(a.heap)] if a.heap else []),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return '%s_%d' % job
    with ThreadPoolExecutor(a.workers) as pool:
        for name in pool.map(go, jobs):
            print('wrote %s' % os.path.relpath(os.path.join(OUT, name + '.log'), WORK), flush=True)


if __name__ == '__main__':
    main()
