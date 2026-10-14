"""Replay the trainer AI bench's recorded decisions through the host build of the advanced AI and compare.

  .venv/bin/python work/advanced-ai/testbench/hostai/replay.py --rom ROM [RESULTS.json] [--reps N] [--only ID,...]
                                          [--all] [--os] [-v] [--sixes N [--seed S]] [--json OUT]

RESULTS defaults to the newest advanced-AI bench run recorded on ROM (bench_runs: its rom_sha1, under RUNS/aibench/
or testbench/references/). The host build is ROM's (the Makefile's B: work/build/advanced-ai/hostai/<ROM name>; --os
the DS build's -Os in <ROM name>_os; --layout en the English build's switches, sim/simbuild.py). Exit status: 0 when every complete case gives the DS's choice, setter call,
option values and snapshot and no 6v6 decision crashed, 1 otherwise, 2 when the ROM has no bench record and no
--sixes was asked (the static tier counts that as a skip). A case in KNOWN_GAPS (option values the stand-in engine
does not reproduce, for a stated reason) fails only if its chosen action differs too.

Each bench result (bench/aibench.py) holds the AI's debug record: both Pokemon on the field as the AI read them, the
engine's damage between them (d_mo, d_om), its option values and its choice. With the scenario spec
(bench/: the scenarios and their batches) for the parties and the trainer's items, that is the decision's whole input
when the AI's bench is empty and the foe has nothing else able to fight (2 polls): every engine simulation the AI
runs is one of the recorded pairs. Those cases are 'complete'. --all also runs the others (doubles, a foe that can
switch, my bench): their extra simulations are missing from the record, so the host answers them with 0 and they are
reported apart; the stand-in answers them with the AI's own formula (host_formula_ai). --sixes N measures work on
N 6v6 first decisions between the ROM's trainer teams, which have no record to compare with.

Prints per-field mismatches, the pass criteria, and the host's time, retired instructions and work per decision.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402

import aibench  # noqa: E402
import simbuild  # noqa: E402
from aidata import Data  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = simbuild.DEFAULT_ROM
OUT = os.path.join(tbpaths.BUILD, 'hostai')
NO_RECORD = 2
# complete cases whose option values the host's stand-in engine does not reproduce, for a known reason: they still
# print as DIFF, and fail the run only if the chosen action differs too
KNOWN_GAPS = {
    'item_cure_sleep': 'the sleeping Snorlax\'s move values are 604 lower on the DS (-1454/-1459 against -850/-855) with '
                       'a Full Heal in the bag; the choice (Full Heal) is the same. The simulator cannot check it '
                       '(trainer items are unsupported there). Seen on rc44\'s record, 2026-10-13',
}


def build_dir(rom, small=False, layout=None):
    """The host build's directory for a ROM's data (the Makefile's B); small: the DS build's -Os; layout: a builder
    layout's switches (sim/simbuild.py layout_defs)."""
    return os.path.join(OUT, simbuild.tag(rom, layout) + ('_os' if small else ''))


def build(rom, small=False, layout=None):
    """Make the host build for a ROM's data; its directory."""
    b = build_dir(rom, small, layout)
    subprocess.run(['make', '-s', '-C', HERE, 'ROM=' + os.path.abspath(rom), 'B=' + b,
                    'AI_DEFS=' + ' '.join(simbuild.layout_defs(layout))] + (['OPT=-Os'] if small else []), check=True)
    return b


def rom_sha1(rom):
    import hashlib
    h = hashlib.sha1()
    with open(rom, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def bench_runs(sha1):
    """The advanced-AI bench runs (bench/aibench.py's saved runs under RUNS/aibench/, and run.py's bench_record.json
    under testbench/references/) recorded on the ROM with this SHA-1, newest first."""
    import glob
    runs = []
    for p in glob.glob(os.path.join(tbpaths.RUNS, 'aibench', '**', '*.json'), recursive=True) + \
            glob.glob(os.path.join(tbpaths.TESTBENCH, 'references', '**', '*.json'), recursive=True):
        try:
            meta = json.load(open(p))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(meta, dict) and meta.get('advanced') and meta.get('rom_sha1') == sha1:
            runs.append(p)
    return sorted(runs, key=os.path.getmtime, reverse=True)
SICK = {None: 0, 'par': 1, 'slp': 2, 'frz': 3, 'brn': 4, 'psn': 5, 'tox': 5}     # engine.h S_*
BPP_STATS = ('atk', 'def', 'spa', 'spd', 'spe')
CLIENT_BASE = (1, 13)
# What abilities do as their Pokemon come out, before the first decision, that the record does not show (ROM names):
# the extreme weathers (the record's weather byte maps them onto rain and sun), the terrains (engine.h TERRAIN_*), and
# Intimidate's and Download's stages
EXTREME = {'primrdialsea': 8, 'desolateland': 9, 'deltastream': 7}
TERRAIN = {'grassysurge': 1, 'mistysurge': 2, 'elecsurge': 3, 'psychicsurge': 4}
WEATHER = {'drizzle': 1, 'drought': 2, 'sandstream': 3, 'snowwarning': 4}
TRAPS = ('shadowtag', 'arenatrap', 'magnetpull')
INTIMIDATE_IMMUNE = ('clearbody', 'hypercutter', 'whitesmoke', 'fullmetalbody', 'innerfocus', 'oblivious', 'owntempo',
                     'scrappy')
SNAP = ('me', 'opp', 'd_mo', 'd_om', 'f_mo', 'f_om', 'weather', 'nbench', 'trapped', 'doubles', 'legal', 'why', 'lost',
        'strong', 'sw_species', 'sw_w', 'role', 'polls', 'fallback')


def kind(r):
    a = r['adv']
    if a['doubles']:
        return 'doubles'
    if a['nbench']:
        return 'bench'
    return 'complete' if a['polls'] == 2 else 'foe_switch'


class Builder:
    def __init__(self, d):
        self.d = d
        self.ab = {}
        for name in list(EXTREME) + list(TERRAIN) + list(INTIMIDATE_IMMUNE) + list(WEATHER) + list(TRAPS) + \
                ['intimidate', 'download', 'defiant', 'competitive', 'contrary', 'simple', 'levitate']:
            try:
                self.ab[d.id('ability', name)] = name
            except KeyError:
                pass

    def entry(self, me, opp, a, notes):
        """The weather byte and terrain the two Pokemon's abilities leave at the first decision, and the stages their
        Intimidate and Download give (applied to the Pokemon)."""
        names = [self.ab.get(m['ability'], '') for m in (me, opp)]
        raw = next((EXTREME[n] for n in names if n in EXTREME), a['weather'])
        terrains = [TERRAIN[n] for n in names if n in TERRAIN]
        if len(terrains) > 1:
            notes.append('two terrains: the faster one is overwritten, not modeled')
        for x, y, nx, ny in ((me, opp, names[0], names[1]), (opp, me, names[1], names[0])):
            if nx == 'intimidate' and ny not in INTIMIDATE_IMMUNE:
                step = {'contrary': 1, 'simple': -2}.get(ny, -1)
                y['stages'][0] = max(0, min(12, y['stages'][0] + step + 2 * (ny == 'defiant')))
                y['stages'][2] += 2 * (ny == 'competitive')
                notes.append('Intimidate on %d' % y['id'])
            if nx == 'download':
                k = 0 if y['stats'][1] < y['stats'][3] else 2
                x['stages'][k] += 1
                notes.append('Download on %d' % x['id'])
        return raw, terrains[-1] if terrains else 0

    def pp(self, move):
        return min(64, self.d.move(move)['pp']) if move else 0

    def types(self, species):
        r = self.d.personal[species]
        return [r[6], r[7], 18]

    def line(self, client, slot, m):
        v = [client, slot, m['id'], m['species'], m['level'], m['hp'], m['maxhp']] + m['stats'] + m['types'] + \
            [m['ability'], m['item']] + m['moves'] + m['pp'] + [m['status'], m['toxic']] + m['stages'] + \
            [m['unselectable'], m['trapped']] + [0] * 5
        return 'mon ' + ' '.join(str(x) for x in v)

    def from_spec(self, spec, mid):
        d, v = self.d, aibench.mon_view(self.d, spec)
        sp = d.id('species', spec['species'])
        moves = [d.id('move', x) for x in spec['moves']] + [0] * (4 - len(spec['moves']))
        return {'id': mid, 'species': sp, 'level': v['level'], 'hp': v['cur_hp'], 'maxhp': v['stats']['hp'],
                'stats': [v['stats'][s] for s in BPP_STATS], 'types': self.types(sp),
                'ability': d.id('ability', spec['ability']) if spec.get('ability') else d.species(sp)['abilities'][0],
                'item': d.id('item', spec['item']) if spec.get('item') else 0, 'moves': moves,
                'pp': [self.pp(x) for x in moves], 'status': SICK[spec.get('status')] if v['cur_hp'] else 0,
                'toxic': int(spec.get('status') == 'tox'), 'stages': [6] * 7, 'unselectable': 0, 'trapped': 0}

    def from_record(self, rec, spec, mid):
        m = self.from_spec(spec, mid)
        m.update({k: rec[k] for k in ('species', 'hp', 'maxhp', 'stats', 'types', 'level', 'status', 'ability', 'item',
                                      'moves')})
        m['pp'] = [self.pp(x) for x in rec['moves']]
        return m

    def case(self, r, spec):
        """The case file block for a bench result, and the case's own notes (what it had to infer)."""
        d, a = self.d, r['adv']
        notes = []
        party = {0: [], 1: []}
        for client, key, rec in ((0, 'player', a['opp']), (1, 'enemy', a['me'])):
            for slot, s in enumerate(spec[key][:6]):
                mid = CLIENT_BASE[client] + slot
                party[client].append(self.from_record(rec, s, mid) if slot == 0 else self.from_spec(s, mid))
        me, opp = party[1][0], party[0][0]
        for i in range(4):
            if me['moves'][i] and me['pp'][i] and not (a['legal'] >> i) & 1:
                me['unselectable'] |= 1 << i
        me['trapped'] = a['trapped']
        raw, terrain = self.entry(me, opp, a, notes)
        if raw != a['weather']:
            notes.append('weather byte %d' % raw)
        if terrain:
            notes.append('terrain %d' % terrain)
        items = [d.id('item', x) for x in spec.get('items', [])][:4]
        items += [0] * (4 - len(items))
        head = 'case %s %d %d %d %d %s %d %d' % (r['id'], a['doubles'], raw, terrain, r.get('seed', 0) & 0xFFFFFFFF,
                                              ' '.join(map(str, items)), len(party[0]), len(party[1]))
        lines = [head] + [self.line(c, s, m) for c in (0, 1) for s, m in enumerate(party[c])]
        for i in range(4):
            if me['moves'][i]:
                lines.append('dmg %d %d %d %d' % (me['id'], opp['id'], me['moves'][i], a['d_mo'][i]))
            if opp['moves'][i]:
                lines.append('dmg %d %d %d %d' % (opp['id'], me['id'], opp['moves'][i], a['d_om'][i]))
        return '\n'.join(lines + ['end']), notes


    def traps(self, x, y):
        """x's ability keeps y in (official rules; Ghost types escape)"""
        n, ny = self.ab.get(x['ability']), self.ab.get(y['ability'])
        if 7 in y['types'][:2]:
            return 0
        if n == 'shadowtag':
            return int(ny != 'shadowtag')
        if n == 'arenatrap':
            return int(2 not in y['types'][:2] and ny != 'levitate')
        return int(n == 'magnetpull' and 8 in y['types'][:2])

    def case_specs(self, cid, player, enemy, level=None):
        """A battle's first decision with no record behind it (work measurements): both parties from specs, the
        weather and terrain their leads' abilities set (the slower lead's last), trapping by ability, and every engine
        simulation left to the stand-in."""
        notes = []
        party = {}
        for client, team in ((0, player), (1, enemy)):
            party[client] = [self.from_spec(dict(s, level=level or s.get('level', 50)), CLIENT_BASE[client] + k)
                             for k, s in enumerate(team[:6])]
        me, opp = party[1][0], party[0][0]
        weather = 0
        for m in sorted((me, opp), key=lambda m: -m['stats'][4]):
            weather = WEATHER.get(self.ab.get(m['ability']), weather)
        raw, terrain = self.entry(me, opp, {'weather': weather}, notes)
        me['trapped'], opp['trapped'] = self.traps(opp, me), self.traps(me, opp)
        head = 'case %s 0 %d %d 0 0 0 0 0 %d %d' % (cid, raw, terrain, len(party[0]), len(party[1]))
        return '\n'.join([head] + [self.line(c, s, m) for c in (0, 1) for s, m in enumerate(party[c])] + ['end']), notes


class Mem:
    def __init__(self, b):
        self.b = b + bytes(512)

    def read_byte(self, a):
        return self.b[a]

    def read_short(self, a):
        return int.from_bytes(self.b[a:a + 2], 'little')

    def read_long(self, a):
        return int.from_bytes(self.b[a:a + 4], 'little')


def decode_debug(hexstr):
    """The host's debug record through the bench's own decoder (aibench.Bench.read_debug)."""
    fake = types.SimpleNamespace(mu=Mem(bytes.fromhex(hexstr)), debug_addr=0)
    return aibench.Bench.read_debug(fake, 1)


CALL_KIND = {'m': 'move', 'i': 'item', 's': 'switch', 'n': 'none', '-': None}


def compare(r, out):
    """(field mismatches, option mismatches, chosen ok, the largest option value difference)"""
    want, got = r['adv'], decode_debug(out['debug'])
    snap = [(k, want[k], got.get(k)) for k in SNAP if want.get(k) != got.get(k)]
    wo, go = want['options'], got.get('options', [])
    opt = []
    vdiff = 0
    for i in range(max(len(wo), len(go))):
        w = wo[i] if i < len(wo) else None
        g = go[i] if i < len(go) else None
        if w != g:
            opt.append((i, w, g))
        if w and g and w[:3] == g[:3]:
            vdiff = max(vdiff, abs(w[3] - g[3]))
        elif w != g:
            vdiff = None if vdiff is None else float('inf')
    call = [CALL_KIND[out['call'][0]]] + out['call'][1:]
    want_call = list(r['call']) if r.get('call') else None
    pick = lambda o, c: (o[c][:3] if c < len(o) else None)
    chosen_ok = pick(wo, want['chosen']) == pick(go, got.get('chosen', 99)) and call == want_call and out['ret'] == 1 \
        and not out['ov11']
    return snap, opt, chosen_ok, vdiff, call


def run(binary, cases_path, reps):
    p = subprocess.run([binary, '--reps', str(reps), cases_path], capture_output=True, text=True)
    if p.returncode:
        sys.exit('%s failed (%d): %s' % (binary, p.returncode, p.stderr[-2000:]))
    return {o['id']: o for o in map(json.loads, p.stdout.splitlines())}


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def work_report(label, rows, reps):
    def dist(name, v, fmt='%d'):
        print(('  %-28s median ' + fmt + ', p90 ' + fmt + ', max ' + fmt + ', mean ' + fmt) %
              (name, statistics.median(v), pct(v, 0.9), max(v), statistics.mean(v)))
    print('\n%s (%d), per decision, fastest of %d runs:' % (label, len(rows), reps))
    dist('host time (us)', [x['ns'] / 1000 for x in rows], '%.1f')
    dist('arm64 instructions', [x['ins'] for x in rows])
    dist('  of which the decide() poll', [x['poll_ins'][-1] for x in rows])
    dist('polls', [x['polls'] for x in rows])
    dist('engine simulations', [x['sims'] for x in rows])
    for k in rows[0]['counts']:
        dist('calls of ' + k, [x['counts'][k] for x in rows])
    v = [x['ins'] / x['counts']['race_core'] for x in rows if x['counts']['race_core']]
    print('  arm64 instructions per race_core call (whole decision): median %d' % statistics.median(v))


def run_sixes(d, b, n, seed, reps, bdir, rom, work):
    """Work per decision at the first turn of n 6v6 battles between the ROM's trainer teams (versus/aiteams.py) at
    level 100, as versus/aivsai.py plays them; the stand-in answers every engine simulation."""
    import random
    import aiteams
    teams = aiteams.trainer_teams(rom, 6)
    rng = random.Random(seed)
    blocks = []
    for k in range(n):
        x, y = rng.sample(teams, 2)
        blocks.append(b.case_specs('six%03d_%d_%d' % (k, x['trainer'], y['trainer']), x['team'], y['team'], 100)[0])
    path = os.path.join(work, 'sixes.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(blocks) + '\n')
    timed = run(os.path.join(bdir, 'replay'), path, reps)
    counted = run(os.path.join(bdir, 'replay_count'), path, 1)
    rows = [dict(o, counts=counted[i]['counts']) for i, o in timed.items()]
    bad = [o['id'] for o in rows if o['ret'] != 1 or o['ov11'] or decode_debug(o['debug'])['fallback']]
    print('\n6v6 trainer teams: %d decisions, %d fell back to overlay 11' % (len(rows), len(bad)))
    work_report('6v6 first decisions', rows, reps)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('results', nargs='?', help='default: the newest bench record on ROM (bench_runs)')
    ap.add_argument('--rom', default=DEFAULT_ROM)
    ap.add_argument('--reps', type=int, default=20)
    ap.add_argument('--only')
    ap.add_argument('--all', action='store_true', help='also the cases whose input the record lacks')
    ap.add_argument('--json', help='write the per-case comparison here')
    ap.add_argument('--sixes', type=int, default=0, help='also measure work on N 6v6 first decisions (trainer teams)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--os', action='store_true', help="the DS build's optimization level (-Os) instead of -O2")
    ap.add_argument('--layout', help="a builder layout whose switches the AI compiles with (en: the English build's)")
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    bdir = build(a.rom, a.os, a.layout)
    work = tbpaths.run_dir('hostai')
    d = Data(a.rom)
    b = Builder(d)
    if not a.results:
        runs = bench_runs(rom_sha1(a.rom))
        a.results = runs[0] if runs else None
    if not a.results and not a.sixes:
        print('no advanced bench run on %s (SHA-1 %s); make one with bench/aibench.py --advanced --rom %s'
              % (a.rom, rom_sha1(a.rom), a.rom))
        sys.exit(NO_RECORD)
    rows, failed, ncomplete = [], [], 0
    if a.results:
        rows, failed = replay_records(a, d, b, bdir, work)
        ncomplete = sum(x['kind'] == 'complete' for x in rows)
    if a.sixes:
        rows += run_sixes(d, b, a.sixes, a.seed, a.reps, bdir, a.rom, work)
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(rows, f, indent=1, default=str)
    if a.results:
        print('%s: %d of %d complete cases differ from the DS%s' % (
            'FAIL' if failed else 'PASS', len(failed), ncomplete, (': ' + ', '.join(failed[:10])) if failed else ''))
    sys.exit(1 if failed else 0)


def replay_records(a, d, b, bdir, work):
    """The bench record's decisions through the host build: (rows, ids of the complete cases that differ)."""
    saved = json.load(open(a.results))
    print('records %s (ROM SHA-1 %s)' % (tbpaths.rel(a.results), saved.get('rom_sha1')))
    specs = {s['id']: s for s in aibench.scenarios()}
    results = [r for r in saved['results'] if r.get('adv') and r['adv'].get('options')]
    if a.only:
        results = [r for r in results if r['id'] in a.only.split(',')]
    elif not a.all:
        results = [r for r in results if kind(r) == 'complete']
    blocks, notes = [], {}
    for r in results:
        text, notes[r['id']] = b.case(r, specs[r['id']])
        blocks.append(text)
    cases_path = os.path.join(work, 'cases.txt')
    with open(cases_path, 'w') as f:
        f.write('\n'.join(blocks) + '\n')
    timed = run(os.path.join(bdir, 'replay'), cases_path, a.reps)
    counted = run(os.path.join(bdir, 'replay_count'), cases_path, 1)
    rows = []
    for r in results:
        out = timed[r['id']]
        snap, opt, chosen_ok, vdiff, call = compare(r, out)
        rows.append({'id': r['id'], 'kind': kind(r), 'chosen_ok': chosen_ok, 'values_ok': not opt, 'vdiff': vdiff,
                     'snap': snap, 'opt': opt, 'call': call, 'want_call': r.get('call'), 'notes': notes[r['id']],
                     'ns': out['ns'], 'ins': out['ins'], 'poll_ins': out['poll_ins'], 'sims': out['sims'],
                     'missing': out['missing'], 'counts': counted[r['id']]['counts'], 'polls': out['polls'],
                     'nopt': len(r['adv']['options'])})
    by = {}
    for x in rows:
        by.setdefault(x['kind'], []).append(x)
    for k, xs in sorted(by.items()):
        nc = sum(x['chosen_ok'] for x in xs)
        nv = sum(x['values_ok'] for x in xs)
        ns = sum(not x['snap'] for x in xs)
        print('%-10s %3d cases: chosen same %d (%.1f%%), all option values exact %d (%.1f%%), snapshot exact %d' %
              (k, len(xs), nc, 100 * nc / len(xs), nv, 100 * nv / len(xs), ns))
    for x in rows:
        if x['chosen_ok'] and x['values_ok'] and not x['snap'] and not a.v:
            continue
        print('\n%s [%s] chosen %s, values %s, missing sims %d %s' % (x['id'], x['kind'], 'same' if x['chosen_ok'] else 'DIFF',
              'same' if x['values_ok'] else 'DIFF (max %s)' % x['vdiff'], x['missing'], '; '.join(x['notes'])))
        for k, w, g in x['snap']:
            print('   snapshot %-8s DS %s host %s' % (k, w, g))
        for i, w, g in x['opt']:
            print('   option %d DS %s host %s' % (i, w, g))
        if not x['chosen_ok']:
            print('   call DS %s host %s' % (x['want_call'], x['call']))

    if by.get('complete'):
        work_report('complete bench cases', by['complete'], a.reps)
    failed = [x['id'] for x in rows if x['kind'] == 'complete' and not (x['chosen_ok'] and x['values_ok'] and not x['snap'])
              and not (x['id'] in KNOWN_GAPS and x['chosen_ok'] and not x['snap'])]
    for x in rows:
        if x['kind'] == 'complete' and x['id'] in KNOWN_GAPS and not x['values_ok']:
            print('known gap %s: %s' % (x['id'], KNOWN_GAPS[x['id']]))
    return rows, failed


if __name__ == '__main__':
    main()
