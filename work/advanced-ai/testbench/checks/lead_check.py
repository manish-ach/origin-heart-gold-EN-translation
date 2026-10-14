"""The trainer's lead at run time (src/lead.c: a trainer the advanced AI serves picks its lead in a single battle).

  .venv/bin/python work/advanced-ai/testbench/checks/lead_check.py --rom ROM --payload PAYLOAD [CASE ...] [--workers N]
                   [--pairs PAIRS] [--sim BIN] [--matchups N] [--seed S]

Ported from the Spanish workspace's tools/lead_check.py (dc8577c). Changes: the setting is written into the save in RAM
after the state loads (bench/aibench.py ADVAI_AI_SETTING: off, all, important) instead of the battery save, so one
save state serves every case; ai_lead's address comes from the payload; the marks are checked in the ROM and in
data/trainer_marks.json; the host match builds the simulator for the ROM with the payload's layout switches
(sim/simbuild.py) and makes the level-80 pairs itself when --pairs is not given; results go to RUNS/lead/.

Every case boots the bench's save state (bench/aibench.py: the Violet Gym save before Officer Felix, trainer 71) with
its setting, sets the battle's trainers as checks/aimode_check.py does, writes the teams into BattleSetup as
the bench does, and stops at the first selection phase (the AI slot load, 0x02223D14), where it reads each client's
party list in both copies of the parties (main+0x54 and main+0x144: the pokeID of each member, in order).
- Settings: Magikarp (Splash), Pikachu (Thunderbolt), Geodude (Rock Throw) against a Gyarados, all level 30, so the
  rule leads with Pikachu. A trainer the setting serves must lead with Pikachu (party slot 1 swapped with slot 0, the
  rest in place); the AI off, an unmarked trainer in the important-only setting, a keep-lead trainer (bit 1),
  the bench's NOLEAD word, and doubles
  and multi battles keep every party's order, the partner's (client 2) included. The player's order never changes.
- Host match (case 'host'): --matchups matchups drawn from the level-80 pool (the simulator gate's pairs) with
  --seed, the trainer teams at level 100 as versus/aivsai.py builds them, the AI on for every trainer. The lead the DS
  sends out must be the one the simulator's host build picks for the same teams (`sim cf lead`, --sim).
A case also fails on any assert, NULL allocation, freeze or text outside its window before the selection phase. Text
drawn past its window's size but inside its buffer (lib/emu.py's 'clipped' note: a text-fit matter of the ROM's
strings, the same with the AI off) is printed with its text, not failed.
Results: RUNS/lead/. Exit status 1 when a case fails.
"""
import argparse
import ctypes
import json
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
import simbuild  # noqa: E402
from aidata import Data  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'lead')
TRAINER_DATA = 'a/0/5/5'        # trainer headers: byte 2 bit 0 = important, bit 1 = keep lead
IMPORTANT_MARK, KEEP_LEAD_MARK = 1, 2
MARKS = os.path.join(tbpaths.ADV, 'data', 'trainer_marks.json')
COPIES = (0x54, 0x144)          # E_POKECON(1), E_POKECON(0): party list of client c at +0x0C + 0x1C c
FIRST_ID = (1, 13, 7, 19)       # each client's first pokeID (overlay 14's table 0x0224D130)
SERVER_START = 0x02223A40       # lead.c: ai_lead calls it once the picks are swapped in
VBLANK = 1120380                # ARM9 cycles per VBlank (dev/aitime.py FRAME)
MARKED, UNMARKED = 253, 5       # Leader Brock, Picnicker Amelia (checks/aimode_check.py)
KEEP = 200                      # Rival Blue at Lavender Town, with his Wartortle beside him (a keep-lead trainer)
LEVEL = 30
ENEMY = [{'species': 'Magikarp', 'level': LEVEL, 'moves': ['Splash'], 'ability': 'Swift Swim'},
         {'species': 'Pikachu', 'level': LEVEL, 'moves': ['Thunderbolt'], 'ability': 'Static'},
         {'species': 'Geodude', 'level': LEVEL, 'moves': ['Rock Throw'], 'ability': 'Sturdy'}]
PLAYER = [{'species': 'Gyarados', 'level': LEVEL, 'moves': ['Waterfall'], 'ability': 'Intimidate'},
          {'species': 'Lapras', 'level': LEVEL, 'moves': ['Surf'], 'ability': 'Water Absorb'}]
PICK = 1                        # the rule's lead in ENEMY
# case: (setting, trainer 1, trainer 2, partner, NOLEAD, client 1's expected lead slot)
CASES = {
    'all_pick':           ('all', UNMARKED, 0, 0, False, PICK),
    'important_marked':   ('important', MARKED, 0, 0, False, PICK),
    'important_unmarked': ('important', UNMARKED, 0, 0, False, 0),
    'off':                ('off', MARKED, 0, 0, False, 0),
    'nolead':             ('all', UNMARKED, 0, 0, True, 0),
    'all_keep':           ('all', KEEP, 0, 0, False, 0),           # a keep-lead trainer
    'all_double':         ('all', UNMARKED, 6, 0, False, 0),       # two trainers, a double: no pick
    'all_multi':          ('all', UNMARKED, 6, 63, False, 0),      # with Steven as the partner: no pick
}


class LeadBattle(aibench.Bench):
    """A bench battle up to its first selection phase, with the case's trainers, reading the party lists there."""

    def __init__(self, rom, state):
        super().__init__(rom, state)
        self.case = (None, 0, 0)
        # the pick's cost: libdesmume's nds_timer (ARM9 cycles, tools/aitime.py Clock) from ai_lead's entry to its call of
        # the server's start
        self.timer = ctypes.c_uint64.in_dll(self.r.emu.lib, 'nds_timer')
        self.mem.register_exec(self.layout.sym('ai_lead') & ~1, self._lead_in)
        self.mem.register_exec(SERVER_START, self._lead_out)

    def _event(self, **ev):
        if ev['ev'] == 'clipped':           # a text-fit note (lib/emu.py), not the lead's business: kept with its text
            if self.cur is not None:
                self.cur.setdefault('clipped', []).append(ev.get('text'))
            return
        super()._event(**ev)

    def _lead_in(self, a, s):
        if self.cur is not None:
            self.cur['t_in'] = self.timer.value

    def _lead_out(self, a, s):
        if self.cur is not None and 't_in' in self.cur and 'cycles' not in self.cur:
            self.cur['cycles'] = self.timer.value - self.cur['t_in']

    def _double(self, a, s):        # SetupAndStartTrainerBattle(task, trainer 1, trainer 2, partner, ...)
        if self.cur is None:
            return
        t1, t2, partner = self.case
        if t1:
            self.reg.r1 = t1
        self.reg.r2, self.reg.r3 = t2, partner

    def _seed(self, a, s):
        c = self.cur
        if c is None or not c.get('injected') or 'order' in c:
            return
        main = self.mu.read_long(aibench.MAIN_PTR)
        order = {}
        for copy in COPIES:
            for client in range(4):
                party = main + copy + 0x0C + 0x1C * client
                n = self.mu.read_byte(party + 0x18)
                if 0 < n <= 6:
                    order.setdefault(client, []).append(
                        [self.mu.read_byte(self.mu.read_long(party + 4 * i) + 0x14) - FIRST_ID[client] for i in range(n)])
        c['order'] = order
        c['species'] = [self.mu.read_short(self.mu.read_long(main + 0x54 + 0x0C + 0x1C + 4 * i))
                        for i in range(self.mu.read_byte(main + 0x54 + 0x0C + 0x1C + 0x18))]
        c['done'] = True

    def run_case(self, mons, seed, case, nolead):
        self.case = case
        self.cur = {'mons': mons, 'items': [], 'seed': seed, 'calls': [], 'failures': [], 'notes': [], 'done': False,
                    'double': bool(case[1])}
        start = self.r.frames
        aibench.to_battle(self.r, self.state)
        self.mem.write_long(aibench.NOLEAD_FLAG, aibench.NOLEAD_MAGIC if nolead else 0)
        while not self.cur['done'] and self.r.frames - start < aibench.FRAME_LIMIT and not self.r.frozen:
            self.r.hold('A', 4, release=4) if (self.r.frames - start) % 40 == 0 else self.r.step(1)
        c, self.cur = self.cur, None
        return {'injected': bool(c.get('injected')), 'order': c.get('order'), 'species': c.get('species'),
                'failures': c['failures'], 'frames': self.r.frames - start, 'cycles': c.get('cycles'),
                'clipped': sorted(set(c.get('clipped', [])))}


def host_jobs(pairs, n, seed):
    """n lines of the pairs file, drawn with seed: [(line, trainer team, slots, player team, slots)]"""
    lines = [l.split() for l in open(pairs) if l.startswith('pair ')]
    out = []
    for f in random.Random(seed).sample(lines, n):
        t0, n0 = int(f[3]), int(f[4])
        s0 = [int(x) for x in f[5:5 + n0]]
        t1, n1 = int(f[5 + n0]), int(f[6 + n0])
        out.append((' '.join(f), t0, s0, t1, [int(x) for x in f[7 + n0:7 + n0 + n1]]))
    return out


def worker(rom, state, jobs_path, out_path):
    d = Data(rom)
    template = aibench.template_mon()
    lb = LeadBattle(rom, state)
    results = []
    for job in json.load(open(jobs_path)):
        seed = aibench.hash_id(job['name'])
        mons = {k: [aibench.build_mon(d, template, spec, seed + 31 * i + (7 if k == 'enemy' else 0))
                    for i, spec in enumerate(job[k])] for k in ('player', 'enemy')}
        for attempt in range(3):        # the walk from the save state now and then misses the trainer
            res = lb.run_case(mons, seed, tuple(job['trainers']), job['nolead'])
            if res['injected']:
                break
        res['name'] = job['name']
        results.append(res)
        with open(out_path, 'w') as f:
            json.dump(results, f)


def make_state(rom, tag):
    """The bench's save state for this ROM (the Violet Gym save, booted on a link to `rom`); the setting is written
    after each load, so one state serves every case."""
    rom_link = aibench.link_rom(rom, os.path.join(OUT, tag + '.nds'))
    state = os.path.join(OUT, tag + '.dst')
    dsv = os.path.join(aibench.DSV_DIR, tag + '.dsv')
    shutil.copy(saves.path('violet_gym'), dsv)
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_link, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in (rom_link, dsv):
        if os.path.lexists(p):
            os.remove(p)
    if not os.path.exists(state):
        sys.exit('no save state made from %s' % rom)
    return state


def run_jobs(tag, mode, jobs, rom, state):
    tag = '%s_%s' % (os.path.splitext(os.path.basename(rom))[0], tag)     # runs on two ROMs at once stay apart
    rom_k, dsv_k = os.path.join(OUT, 'job_%s.nds' % tag), os.path.join(aibench.DSV_DIR, 'job_%s.dsv' % tag)
    aibench.link_rom(rom, rom_k)
    shutil.copy(saves.path('violet_gym'), dsv_k)
    jp, op = os.path.join(OUT, 'jobs_%s.json' % tag), os.path.join(OUT, 'res_%s.json' % tag)
    json.dump(jobs, open(jp, 'w'))
    if os.path.exists(op):
        os.remove(op)
    subprocess.run([sys.executable, __file__, '--worker', rom_k, state, jp, op],
                   env=dict(os.environ, **{aibench.SETTING_ENV: mode}), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in (rom_k, dsv_k):
        if os.path.lexists(p):
            os.remove(p)
    return json.load(open(op)) if os.path.exists(op) else []


def swapped(n, k):
    """A party of n in its own order with slot k leading (lead.c swaps k and 0)."""
    o = list(range(n))
    o[0], o[k] = o[k], o[0]
    return o


def problems(res, expect, sizes):
    """expect: {client: lead slot}; sizes: {client: party size}. Both copies must hold the same order."""
    if not res or not res.get('injected') or not res.get('order'):
        return ['no battle' if not res or not res.get('injected') else 'no selection phase reached']
    out = []
    order = {int(k): v for k, v in res['order'].items()}
    for client, n in sizes.items():
        want = swapped(n, expect.get(client, 0))
        got = order.get(client)
        if not got or any(o != want for o in got):
            out.append('client %d: party order %s (copies E_POKECON(1), E_POKECON(0)), want %s' % (client, got, want))
    if res['failures']:
        out.append('failures: %s' % res['failures'])
    return out


def cost(cycles):
    return 'not run' if cycles is None else '%.2f M cycles (%.1f VBlanks)' % (cycles / 1e6, cycles / VBLANK)


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:6])
    ap = argparse.ArgumentParser()
    ap.add_argument('cases', nargs='*')
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="the AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--workers', type=int, default=2, help='emulator processes (lib/emupool.py caps the machine)')
    ap.add_argument('--sim', help="the simulator (default: the ROM's build with the payload's layout, sim/simbuild.py)")
    ap.add_argument('--pairs', default=None, help='the level-80 pool as a pairs file (default: made here with '
                    'sim/counterfactual.py pairs --pool 80)')
    ap.add_argument('--matchups', type=int, default=24)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    import aiteams
    lay = payload.load(a.payload)          # exported for the workers
    from romio import read_narc
    marks = {k: f[2] for k, f in enumerate(read_narc(a.rom, TRAINER_DATA)[0].files)}
    listed = json.load(open(MARKS))
    if marks[MARKED] & 3 != IMPORTANT_MARK or marks[UNMARKED] & 3 or marks[KEEP] & KEEP_LEAD_MARK == 0:
        sys.exit('trainers %d, %d and %d are not marked in the ROM as this check expects' % (MARKED, UNMARKED, KEEP))
    if MARKED not in listed['important'] or MARKED in listed['keep_lead'] or UNMARKED in listed['important'] or \
            UNMARKED in listed['keep_lead'] or KEEP not in listed['keep_lead']:
        sys.exit('trainers %d, %d and %d are not listed in %s as this check expects' % (MARKED, UNMARKED, KEEP,
                                                                                         tbpaths.rel(MARKS)))
    os.makedirs(OUT, exist_ok=True)
    cases = a.cases or list(CASES) + ['host']
    t0 = time.time()
    state = make_state(a.rom, 'lead_' + os.path.splitext(os.path.basename(a.rom))[0])
    groups = []                 # (tag, mode, jobs)
    for c in cases:
        if c in CASES:
            mode, t1, t2, partner, nolead = CASES[c][:5]
            groups.append((c, mode, [{'name': c, 'trainers': [t1, t2, partner], 'nolead': nolead,
                                      'player': PLAYER[:2 if t2 else 1], 'enemy': ENEMY}]))
    host = []
    if 'host' in cases:
        a.sim = a.sim or simbuild.build(a.rom, None if lay.name == 'es' else lay.name)
        if not a.pairs:
            a.pairs = os.path.join(OUT, 'pairs80_%s.txt' % os.path.splitext(os.path.basename(a.rom))[0])
            subprocess.run([sys.executable, os.path.join(tbpaths.TESTBENCH, 'sim', 'counterfactual.py'), '--sim', a.sim,
                            'pairs', '--pool', '80', '-o', a.pairs], check=True, stderr=subprocess.DEVNULL)
        teams = aiteams.trainer_teams(a.rom, 6)
        host = host_jobs(a.pairs, a.matchups, a.seed)

        def specs(t, slots):
            return [dict(teams[t]['team'][s], level=100) for s in slots]
        jobs = [{'name': 'host%02d' % i, 'trainers': [UNMARKED, 0, 0], 'nolead': False,
                 'enemy': specs(t0_, s0), 'player': specs(t1_, s1)} for i, (line, t0_, s0, t1_, s1) in enumerate(host)]
        for k in range(a.workers):
            if jobs[k::a.workers]:
                groups.append(('host%d' % k, 'all', jobs[k::a.workers]))
    with ThreadPoolExecutor(a.workers) as pool:
        out = {r['name']: r for part in pool.map(lambda g: run_jobs(*g, a.rom, state), groups) for r in part}
    failed = total = 0
    for c in [c for c in cases if c in CASES]:
        mode, t1, t2, partner, nolead, lead = CASES[c]
        sizes = {0: len(PLAYER[:2 if t2 else 1]), 1: len(ENEMY)}
        res = out.get(c)
        if res and res.get('order'):
            sizes.update({int(k): len(v[0]) for k, v in res['order'].items() if int(k) > 1})
        bad = problems(res, {1: lead}, sizes)
        total += 1
        failed += bool(bad)
        print('%-19s %-6s client 1 leads with slot %s (want %d); ai_lead %s' % (c, 'FAILED' if bad else 'ok',
              (res or {}).get('order', {}).get('1', [[None]])[0][0], lead, cost((res or {}).get('cycles'))))
        for p in bad:
            print('    ' + p)
    if host:
        hp = os.path.join(OUT, 'host_pairs_%s.txt' % os.path.splitext(os.path.basename(a.rom))[0])
        with open(hp, 'w') as f:
            f.write(''.join(line + '\n' for line, *_ in host))
        sim = subprocess.run([a.sim, 'cf', 'lead', '--pairs', hp, '--p0', 'orig',
                              '--p1', 'adv'], check=True, capture_output=True, text=True).stdout.split('\n')
        picks = [int(l.split()[3]) for l in sim if l.startswith('lead ')]
        changed = 0
        for i, (line, t0_, s0, t1_, s1) in enumerate(host):
            res = out.get('host%02d' % i)
            bad = problems(res, {1: picks[i]}, {0: len(s1), 1: len(s0)})
            total += 1
            failed += bool(bad)
            changed += picks[i] > 0
            print('%-19s %-6s %s vs %s: the simulator leads with slot %d, the DS with %s; ai_lead %s' % (
                'host%02d' % i, 'FAILED' if bad else 'ok', teams[t0_]['name'], teams[t1_]['name'], picks[i],
                (res or {}).get('order', {}).get('1', [[None]])[0][0], cost((res or {}).get('cycles'))))
            for p in bad:
                print('    ' + p)
        print('host match: %d of %d matchups lead with another Pokemon than slot 0' % (changed, len(host)))
    clipped = sorted({t for r in out.values() for t in r.get('clipped', []) if t})
    if clipped:
        print('text drawn past its window (clipped; not failed): %s' % ' | '.join(repr(t) for t in clipped[:8]))
    print('lead_check: %d of %d case(s) failed (%.0f s)' % (failed, total, time.time() - t0))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
