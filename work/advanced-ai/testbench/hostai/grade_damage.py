"""Grade damage formulas on the engine's own numbers: every bench record's active pair (d_mo, d_om: the engine
simulation's maximum roll, as the AI read it) against the AI's formula (f_mo, f_om, from the same record) and against
dev/aicalc.py's maximum roll for the same Pokemon, move and field.

  .venv/bin/python work/advanced-ai/testbench/hostai/grade_damage.py --rom ROM [RESULTS.json] [-v] [--sim SIM]

RESULTS defaults to the newest advanced-AI bench run recorded on ROM (replay.bench_runs). --sim also grades the
simulator's C port (sim/damage.c, through `sim damage`; sim/simbuild.py builds it for ROM) on the same numbers.

A pair counts when the engine number is above 1 (1 is the simulation's "no effect"), the decision drew no extra roll
(sim_unsure 0), and both Pokemon are level 50 or as the spec says. This is the bar a C port of aicalc must clear to
replace the AI's formula as the host's stand-in for the engine simulation.
"""
import argparse
import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import aibench  # noqa: E402
import aicalc  # noqa: E402
import replay  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WEATHER = {1: 'rain', 2: 'sun', 3: 'sand', 4: 'snow'}
TERRAIN = {'grassysurge': 'grassy', 'mistysurge': 'misty', 'elecsurge': 'electric', 'psychicsurge': 'psychic'}
STATUS = {'par': 'par', 'brn': 'brn', 'psn': 'psn', 'tox': 'tox', 'slp': 'slp', 'frz': 'frz'}
WEATHER_ID = {None: 0, 'rain': 1, 'sun': 2, 'sand': 3, 'snow': 4, 'harsh': 9, 'heavy': 8}
TERRAIN_ID = {None: 0, 'grassy': 1, 'misty': 2, 'electric': 3, 'psychic': 4}
STAGES = ['atk', 'def', 'spa', 'spd', 'spe', 'acc', 'eva']


def sim_side(rec, mon):
    """One Pokemon of a `sim damage` query: the record's own ids and stats, the stages aicalc gave it."""
    return [rec['species'], rec['level'], rec['hp'], rec['maxhp']] + rec['stats'] + rec['types'] + \
        [rec['ability'], rec['item'], rec['status']] + [mon.boosts.get(k, 0) for k in STAGES]


def calc_mon(calc, spec, rec):
    m = calc.mon(spec['species'], level=spec.get('level', 50), ability=spec.get('ability'), item=spec.get('item'),
                 nature=spec.get('nature') or 'Hardy', evs=spec.get('evs'), ivs=spec.get('ivs', 31),
                 status=STATUS.get(spec.get('status')), hp=rec['hp'])
    m.stats = dict(m.stats, atk=rec['stats'][0], **{'def': rec['stats'][1]}, spa=rec['stats'][2], spd=rec['stats'][3],
                   spe=rec['stats'][4], hp=rec['maxhp'])
    m.hp = rec['hp']
    m.types = sorted(set(t for t in rec['types'] if t < 18))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('results', nargs='?', help='default: the newest bench record on ROM')
    ap.add_argument('--rom', default=replay.DEFAULT_ROM)
    ap.add_argument('-v', action='store_true')
    ap.add_argument('--sim', help='the simulator binary: grade its damage port too')
    a = ap.parse_args()
    if not a.results:
        runs = replay.bench_runs(replay.rom_sha1(a.rom))
        if not runs:
            print('no advanced bench run on %s; make one with bench/aibench.py --advanced --rom %s' % (a.rom, a.rom))
            sys.exit(replay.NO_RECORD)
        a.results = runs[0]
    calc = aicalc.Calc(a.rom)
    specs = {s['id']: s for s in aibench.scenarios()}
    res = [r for r in json.load(open(a.results))['results'] if r.get('adv') and not r['adv']['doubles']]
    n = ai_ok = calc_ok = 0
    calc_within = 0
    misses = collections.Counter()
    queries = []            # (engine number, query, label) for --sim
    for r in res:
        adv, spec = r['adv'], specs[r['id']]
        if adv['sim_unsure']:
            continue
        me, opp = calc_mon(calc, spec['enemy'][0], adv['me']), calc_mon(calc, spec['player'][0], adv['opp'])
        intim = [(x, y) for x, y in ((me, opp), (opp, me)) if x.ab == 'intimidate' and y.ab not in
                 ('clearbody', 'hypercutter', 'whitesmoke', 'innerfocus', 'oblivious', 'owntempo', 'scrappy')]
        for x, y in intim:
            y.boosts['atk'] = y.boosts.get('atk', 0) - 1
        for x, y in ((me, opp), (opp, me)):       # Download: +1 Attack against the lower Defense, else +1 Sp. Atk
            if x.ab == 'download':
                k = 'atk' if y.stats['def'] < y.stats['spd'] else 'spa'
                x.boosts[k] = x.boosts.get(k, 0) + 1
        names = {me.ab, opp.ab}
        weather = 'harsh' if 'desolateland' in names else 'heavy' if 'primrdialsea' in names else WEATHER.get(adv['weather'])
        terrain = next((TERRAIN[x] for x in names if x in TERRAIN), None)
        field = aicalc.Field(weather=weather, terrain=terrain)
        for att, dfn, moves, eng, form, ra, rd in ((me, opp, adv['me']['moves'], adv['d_mo'], adv['f_mo'], adv['me'], adv['opp']),
                                                   (opp, me, adv['opp']['moves'], adv['d_om'], adv['f_om'], adv['opp'], adv['me'])):
            for k in range(4):
                if not moves[k] or eng[k] <= 1:
                    continue
                queries.append((eng[k], 'q %d %d %d %s %s' % (moves[k], WEATHER_ID[weather], TERRAIN_ID[terrain],
                                                             ' '.join(map(str, sim_side(ra, att))),
                                                             ' '.join(map(str, sim_side(rd, dfn)))),
                                '%-34s %-14s' % (r['id'], calc.d.move_name.get(moves[k]))))
                try:
                    hi = calc.damage(att, moves[k], dfn, field).hi
                except Exception as e:      # a move aicalc does not model
                    hi = -1
                    misses['error %s' % type(e).__name__] += 1
                n += 1
                ai_ok += form[k] == eng[k]
                calc_ok += hi == eng[k]
                calc_within += hi > 0 and abs(hi - eng[k]) <= max(1, eng[k] // 100)
                if hi != eng[k]:
                    misses[calc.d.move_name.get(moves[k], moves[k])] += 1
                    if a.v:
                        print('%-34s %-14s engine %4d  aicalc %4d  AI formula %4d' % (
                            r['id'], calc.d.move_name.get(moves[k]), eng[k], hi, form[k]))
    print('%d engine numbers above 1 (single battles, no extra roll)' % n)
    print('  AI formula (f_mo/f_om) exact: %d (%.1f%%)' % (ai_ok, 100 * ai_ok / n))
    print('  aicalc max roll        exact: %d (%.1f%%), within 1%%: %d (%.1f%%)' %
          (calc_ok, 100 * calc_ok / n, calc_within, 100 * calc_within / n))
    print('  aicalc misses by move: %s' % ', '.join('%s %d' % kv for kv in misses.most_common(12)))
    if a.sim:
        out = subprocess.run([a.sim, 'damage'], input='\n'.join(q for _, q, _ in queries) + '\n', capture_output=True,
                             text=True, check=True).stdout.split()
        assert len(out) == len(queries), (len(out), len(queries))
        ok = within = 0
        sim_miss = collections.Counter()
        for (eng, _, label), v in zip(queries, map(int, out)):
            ok += v == eng
            within += abs(v - eng) <= max(1, eng // 100)
            if v != eng:
                sim_miss[label.split()[-1]] += 1
                if a.v:
                    print('sim %s engine %4d  sim %4d' % (label, eng, v))
        print('  sim (tools/sim) max roll exact: %d (%.1f%%), within 1%%: %d (%.1f%%)' %
              (ok, 100 * ok / n, within, 100 * within / n))
        print('  sim misses by move: %s' % ', '.join('%s %d' % kv for kv in sim_miss.most_common(12)))


if __name__ == '__main__':
    main()
