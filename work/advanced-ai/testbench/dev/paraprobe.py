"""Paralysis, measured in short battles (the Spanish qa/aivsai/paralysis.md): factprobe's battles (versus/aivsai.py's
Duel with set teams, the original AI on both sides, moves forced per turn) with these cases, and a report that reads
their logs.

  .venv/bin/python work/advanced-ai/testbench/dev/paraprobe.py run CASE [CASE ...] --rom ROM --payload P [--workers 2]
  .venv/bin/python work/advanced-ai/testbench/dev/paraprobe.py report
  .venv/bin/python work/advanced-ai/testbench/dev/paraprobe.py trace CASE K ADDR [ADDR ...] --rom ROM --payload P

Ported from the Spanish workspace's qa/ai_research/paraprobe.py (dc8577c) into the test bench: its imports (lib/tbpaths.py),
the ROM and its payload as arguments, the Violet Gym save from lib/saves.py, results under RUNS/paraprobe/. The report reads the battle messages in Spanish or English.

Logs: RUNS/paraprobe/<case>_<k>.log (factprobe's format; the speed cases add DUMP lines, whose battle Pokémon
bytes hold the Speed stat at +0x234). Side 1 is the trainer's, side 0 the player's. Each battle k of a case is seeded
777 + 13 k (one seed per battle: these games carry no 'rng', so the luck is aivsai's legacy mode).
"""
import json
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'lib'))
import tbpaths  # noqa: E402
import payload  # noqa: E402
from factprobe import mon  # noqa: E402

WORK = tbpaths.WORK
OUT = os.path.join(tbpaths.RUNS, 'paraprobe')
STATUS_MOVES = ['Splash', 'Growl', 'Tail Whip', 'Leer']        # 140 PP between them: a long battle where nothing happens
SPLASH = {0: ['Splash'], 1: ['Splash']}


def snorlax(spe, level, status=None):
    """A Snorlax whose Speed is set by its Speed EVs (the speed cases' opponent): spe -> EV at that level."""
    ev = {(50, 73): 180, (50, 77): 212, (100, 110): 56, (100, 114): 72, (100, 159): 252}[(level, spe)]
    return mon('Snorlax', ['Splash'], level=level, status=status, evs={'hp': 0, 'atk': 0, 'def': 0, 'spe': ev, 'spa': 0, 'spd': 0})


def jolteon(status=None, ability='Run Away'):
    return mon('Jolteon', ['Splash'], level=50, status=status, ability=ability)       # Speed 150


# case: battles of (trainer side team, player side team, frame limit, forced moves {side: moves by turn, cycled},
# original AI on both sides); the trainer's Jolteon (Speed 150) against an opponent of set Speed, both using Splash
CASES = {
    # the Speed factor: 1/2 puts paralyzed Jolteon at 75, 1/4 at 37
    'par_spd_ctl': [([jolteon()], [snorlax(159, 100)], 4200, SPLASH, True)],
    'par_spd_73': [([jolteon('par')], [snorlax(73, 50)], 4200, SPLASH, True)],
    'par_spd_77': [([jolteon('par')], [snorlax(77, 50)], 4200, SPLASH, True)],
    # Quick Feet: the official games give a paralyzed holder x1.5 and skip the paralysis drop (225 here); the code read
    # gives x1.5 then x1/2 (112); a burned holder gets x1.5 (225)
    'qf_par_110': [([jolteon('par', 'Quick Feet')], [snorlax(110, 100)], 4200, SPLASH, True)],
    'qf_par_114': [([jolteon('par', 'Quick Feet')], [snorlax(114, 100)], 4200, SPLASH, True)],
    'qf_par_159': [([jolteon('par', 'Quick Feet')], [snorlax(159, 100)], 4200, SPLASH, True)],
    'qf_brn_221': [([jolteon('brn', 'Quick Feet')], [mon('Dugtrio', ['Splash'], level=80)], 4200, SPLASH, True)],
    'qf_brn_226': [([jolteon('brn', 'Quick Feet')], [mon('Starmie', ['Splash'], level=85)], 4200, SPLASH, True)],
    # full paralysis: both sides paralyzed, status moves only, about 100 turns per battle, four seeds
    'par_rate': [([mon('Blissey', STATUS_MOVES, level=100, status='par')], [mon('Snorlax', STATUS_MOVES, level=100, status='par')],
                  30000, {0: STATUS_MOVES, 1: STATUS_MOVES}, True)] * 4,
    # damage: Snorlax's Tackle on a Blissey with Leftovers, the attacker healthy, paralyzed, burned (a known x1/2), and
    # the defender paralyzed
    'par_dmg': [([mon('Snorlax', ['Tackle'], status=st_a)], [mon('Blissey', ['Splash'], level=100, item='Leftovers', status=st_d)],
                 9000, {1: ['Tackle'], 0: ['Splash']}, True) for st_a, st_d in ((None, None), ('par', None), ('brn', None), (None, 'par'))],
    # immunities: the trainer's move every turn on the player's Pokémon (abilities that block are left out: Run Away)
    'im_twave': [([mon('Slowbro', ['Thunder Wave'])], [mon(sp, ['Splash'])], 2400, {1: ['Thunder Wave'], 0: ['Splash']}, True)
                 for sp in ('Snorlax', 'Jolteon', 'Sandslash')],
    'im_nuzzle': [([mon('Pikachu', ['Nuzzle'])], [mon(sp, ['Splash'], level=100)], 2400, {1: ['Nuzzle'], 0: ['Splash']}, True)
                  for sp in ('Snorlax', 'Magnezone', 'Lanturn')],
    'im_bodyslam': [([mon('Snorlax', ['Body Slam'])], [mon('Magnezone', ['Splash'], level=100, item='Leftovers')], 9000,
                     {1: ['Body Slam'], 0: ['Splash']}, True)],
    'im_powder': [([mon('Vileplume', ['Stun Spore'])], [mon(sp, ['Splash'])], 3000, {1: ['Stun Spore'], 0: ['Splash']}, True)
                  for sp in ('Snorlax', 'Venusaur')],
    'im_glare': [([mon('Arbok', ['Glare'])], [mon('Gengar', ['Splash'])], 2400, {1: ['Glare'], 0: ['Splash']}, True)],
}
DUMP_CASES = {c for c in CASES if c.startswith(('par_spd', 'qf_'))}


def run_one(case, k, rom_path, trace=None):
    """factprobe.run_one for this aivsai (Duel takes a mode name), without its heap and debug options. trace: code
    addresses whose calls in the battle are written to the log (TRACE lines: address, r0-r3 and the return address)."""
    import aibench
    import aivsai
    from aidata import Data
    adv, orig, frames, force, control = CASES[case][k]
    dump = case in DUMP_CASES
    tag = 'paraprobe_%s_%d' % (case, k)
    rom, state, save = aivsai.prepare(rom_path, control, tag)
    d = Data(rom)
    dumps, seen = [], set()

    class Probe(aivsai.Duel):
        def _poll(self, a, s):
            super()._poll(a, s)
            c = self.cur
            if not dump or c is None or not c.get('injected') or (c.get('turn'), self.side) in seen:
                return
            seen.add((c.get('turn'), self.side))
            rows = [bytes(self.mu.read_byte(p[0] + i) for i in range(0x340)).hex()
                    for p in (self.party(side) for side in (0, 1)) if p]
            dumps.append((c.get('turn'), self.side, rows))

        def _setter(self, kind):
            base = super()._setter(kind)

            def f(a, s):
                c = self.cur
                who = self.mu.read_long(self.reg.r13) & 0xFF        # the pokeID the move is set for: 1-12 the player's
                side = 0 if 1 <= who <= 12 else 1
                if kind == 'move' and c is not None and c.get('injected') and side in force and self.reg.r14 != aivsai.REPLACE_LR:
                    plan = force[side]
                    self.reg.r1 = d.id('move', plan[(c.get('turn', 1) - 1) % len(plan)])
                base(a, s)
            return f

    aivsai.FRAME_LIMIT = frames                     # Duel reads it when it is made
    duel = Probe(rom, state, 'control' if control else 'adv')
    traced = []
    for at in trace or []:
        def hit(a, s, at=at):
            if duel.cur is not None and duel.cur.get('injected') and duel.in_battle():
                r = duel.reg
                row = (at, r.r0, r.r1, r.r2, r.r3, r.r14 & ~1)
                if row[2:] not in {t[2:] for t in traced if t[0] == at}:
                    traced.append(row)
        duel.mem.register_exec(at, hit)
    game = {'scenario': case, 'game': k, 'seed': 777 + 13 * k, 'adv': {'name': 'trainer', 'team': adv},
            'orig': {'name': 'player', 'team': orig}}
    os.makedirs(OUT, exist_ok=True)
    path = log_path(case, k) if not trace else os.path.join(OUT, 'trace_%s_%d.log' % (case, k))
    res = aivsai.logged_play(duel, game, path)
    with open(path, 'a') as f:
        f.write('RESULT %s\n' % json.dumps({x: res[x] for x in ('end', 'turns', 'left', 'frames')}))
        for t, sd, rows in dumps:
            f.write('DUMP turn %s side %s %s\n' % (t, sd, ' | '.join(rows)))
        for row in traced:
            f.write('TRACE %08X r0 %08X r1 %08X r2 %08X r3 %08X from %08X\n' % row)
    for p in (rom, os.path.join(aibench.DSV_DIR, '%s.dsv' % tag), state, state + '.pre', save):
        if os.path.lexists(p):
            os.remove(p)


def run(cases, rom, workers):
    os.makedirs(OUT, exist_ok=True)
    jobs = [(c, k) for c in cases for k in range(len(CASES[c]))]

    def go(job):
        case, k = job
        r = subprocess.run([sys.executable, __file__, '--one', case, str(k), rom], capture_output=True, text=True)
        return '%s_%d%s' % (case, k, '' if r.returncode == 0 else ' FAILED: ' + r.stderr.strip()[-400:])
    with ThreadPoolExecutor(workers) as pool:
        for name in pool.map(go, jobs):
            print('done %s' % name, flush=True)


# --- report
TURN = re.compile(r'^--- Turn (\d+) ')
# Spanish or English battle messages: group 2 the foe's species, group 3 the player's
USED = re.compile(r'^  >> (?:¡(El (.+) enemigo|(.+?)) usó |(?:(The foe’s (.+))|(.+?)) used )')
STUCK = re.compile(r'^  >> (?:¡(El (.+) enemigo|(.+?)) está paralizado! ¡No se puede mover!|'
                   r'(?:(The foe’s (.+))|(.+?)) is paralyzed! It can’t move!)')
HIT = re.compile(r'^  >> \[hit\] (\S.*): (\S+) (\d+)$')


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 1.0)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - h, c + h)


def turns(path):
    """[(turn, [(side, 'move'|'stuck')...], [lines])] from a log; side 1 the trainer's (messages say 'enemigo' or
    'The foe's')."""
    out, cur = [], None
    for line in open(path, encoding='utf-8'):
        m = TURN.match(line)
        if m:
            cur = (int(m.group(1)), [], [])
            out.append(cur)
            continue
        if cur is None:
            continue
        cur[2].append(line.rstrip('\n'))
        for rx, what in ((USED, 'move'), (STUCK, 'stuck')):
            m = rx.match(line)
            if m:
                cur[1].append((1 if m.group(2) or m.group(5) else 0, what))
    return out


def speeds(path):
    """The Speed stat (+0x234) of each side's active battle Pokémon at its first DUMP line: {side: Speed}."""
    for line in open(path, encoding='utf-8'):
        if line.startswith('DUMP '):
            rows = line.split(' ', 5)[5].split(' | ')
            return {side: int.from_bytes(bytes.fromhex(r)[0x234:0x236], 'little') for side, r in enumerate(rows)}
    return {}


def log_path(case, k):
    return os.path.join(OUT, '%s_%d.log' % (case, k))


def report():
    print('Speed cases (trainer side = side 1 = Jolteon):')
    for case in sorted(c for c in DUMP_CASES):
        p = log_path(case, 0)
        if not os.path.exists(p):
            continue
        sp = speeds(p)
        first = {0: 0, 1: 0}
        stuck = 0
        for t, acts, _ in turns(p):
            if len(acts) >= 2 and acts[0][0] != acts[1][0]:
                first[acts[0][0]] += 1
            stuck += sum(1 for s, w in acts if w == 'stuck')
        print('  %-12s Speed trainer %s player %s: trainer first %d turns, player first %d turns (full paralysis %d)' % (
            case, sp.get(1), sp.get(0), first[1], first[0], stuck))
    print('Full paralysis (par_rate, both sides paralyzed):')
    tot = {0: [0, 0], 1: [0, 0]}
    after = {True: [0, 0], False: [0, 0]}          # this side's roll by its previous roll: [stuck, rolls]
    for k in range(len(CASES['par_rate'])):
        p = log_path('par_rate', k)
        if not os.path.exists(p):
            continue
        prev = {}
        for t, acts, _ in turns(p):
            for side, what in acts:
                tot[side][0] += what == 'stuck'
                tot[side][1] += 1
                if side in prev:
                    after[prev[side]][0] += what == 'stuck'
                    after[prev[side]][1] += 1
                prev[side] = what == 'stuck'
    allk, alln = tot[0][0] + tot[1][0], tot[0][1] + tot[1][1]
    for side in (1, 0):
        lo, hi = wilson(*tot[side])
        print('  side %d: %d of %d turns lost (%.1f%%, 95%% CI %.1f-%.1f%%)' % (side, tot[side][0], tot[side][1],
                                                                            100 * tot[side][0] / max(1, tot[side][1]), 100 * lo, 100 * hi))
    lo, hi = wilson(allk, alln)
    print('  both: %d of %d (%.1f%%, 95%% CI %.1f-%.1f%%)' % (allk, alln, 100 * allk / max(1, alln), 100 * lo, 100 * hi))
    for prev in (True, False):
        k, n = after[prev]
        lo, hi = wilson(k, n)
        print('  after a %s turn: %d of %d lost (%.1f%%, CI %.1f-%.1f%%)' % ('lost' if prev else 'normal', k, n,
                                                                            100 * k / max(1, n), 100 * lo, 100 * hi))
    pool = [allk, alln]             # every battle with a side paralyzed from turn 1, that side's turns
    for case, k, side in [(c, 0, 1) for c in sorted(DUMP_CASES) if CASES[c][0][0][0].get('status') == 'par'] + \
            [('par_dmg', 1, 1), ('par_dmg', 3, 0)]:
        if os.path.exists(log_path(case, k)):
            for t, acts, _ in turns(log_path(case, k)):
                for sd, what in acts:
                    if sd == side:
                        pool[0] += what == 'stuck'
                        pool[1] += 1
    lo, hi = wilson(*pool)
    print('  pooled with the speed and damage battles: %d of %d (%.1f%%, 95%% CI %.1f-%.1f%%)' % (
        pool[0], pool[1], 100 * pool[0] / max(1, pool[1]), 100 * lo, 100 * hi))
    print('Damage (par_dmg: Snorlax Tackle on Blissey; crits left out):')
    for k, label in enumerate(('healthy', 'attacker paralyzed', 'attacker burned', 'defender paralyzed')):
        p = log_path('par_dmg', k)
        if not os.path.exists(p):
            continue
        dmg, crits, stuck = [], 0, 0
        for t, acts, lines in turns(p):
            stuck += sum(1 for s, w in acts if w == 'stuck')
            crit = any('golpe crítico' in x for x in lines)
            for x in lines:
                m = HIT.match(x)
                if m:
                    if crit:
                        crits += 1
                    else:
                        dmg.append(int(m.group(3)))
        print('  %-19s %2d hits: min %s max %s mean %.1f; crits %d, full paralysis %d' % (
            label, len(dmg), min(dmg or [0]), max(dmg or [0]), sum(dmg) / max(1, len(dmg)), crits, stuck))
    print('Immunities (the trainer\'s move every turn on the player\'s Pokémon):')
    skip = ('usó', ' used ', 'Pero no pasó nada', 'But nothing happened', '[hit]')
    for case in ('im_twave', 'im_nuzzle', 'im_bodyslam', 'im_powder', 'im_glare'):
        for k in range(len(CASES[case])):
            p = log_path(case, k)
            if not os.path.exists(p):
                continue
            target = CASES[case][k][1][0]['species']
            msgs, para_turn, uses, hits, n = [], None, 0, 0, 0
            for t, acts, lines in turns(p):
                n = t
                uses += sum(1 for s, w in acts if s == 1 and w == 'move')
                hits += sum(1 for x in lines if x.startswith('  >> [hit]'))
                for x in lines:
                    if para_turn is None and re.match(r'^  ORIGINAL  \S+ +\d+/\d+ .* PAR', x):
                        para_turn = t
                    if x.startswith('  >> ') and not any(w in x for w in skip) and x[5:] not in msgs:
                        msgs.append(x[5:])
            print('  %s_%d on %s: %d turns, the move used %d times (%d hits), paralyzed from turn %s; messages: %s' % (
                case, k, target, n, uses, hits, para_turn, ' | '.join(msgs)))


def main():
    if sys.argv[1:2] == ['--one']:
        return run_one(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    import argparse
    ap = argparse.ArgumentParser(description='Paralysis measured in short battles.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('cases', nargs='+', choices=sorted(CASES))
    r.add_argument('--rom', required=True)
    r.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    r.add_argument('--workers', type=int, default=2)
    t = sub.add_parser('trace', help='one battle; unique calls to each code address')
    t.add_argument('case', choices=sorted(CASES))
    t.add_argument('k', type=int)
    t.add_argument('addrs', nargs='+')
    t.add_argument('--rom', required=True)
    t.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    sub.add_parser('report')
    a = ap.parse_args()
    if a.cmd in ('run', 'trace'):
        payload.path_from(a.payload)        # exported for the battles
    if a.cmd == 'trace':
        return run_one(a.case, a.k, os.path.abspath(a.rom), [int(x, 16) for x in a.addrs])
    if a.cmd == 'run':
        run(a.cases, os.path.abspath(a.rom), a.workers)
    else:
        report()


if __name__ == '__main__':
    main()
