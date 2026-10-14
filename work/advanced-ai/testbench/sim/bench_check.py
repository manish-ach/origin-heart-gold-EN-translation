"""The simulator's bridge to the advanced AI against the DS: the trainer AI bench's complete recorded first decisions
(hostai/replay.py's complete cases) rebuilt as simulator battles and decided through sim/bridge.c, with every
engine simulation answered by sim/damage.c instead of the record. Graded with replay.py's own comparison: the
same choice and setter call, every option value, the snapshot fields.

  .venv/bin/python work/advanced-ai/testbench/sim/bench_check.py --rom ROM [--layout en] [RESULTS.json] [--all] [-v]

RESULTS defaults to the newest advanced-AI bench run (bench/aibench.py --advanced) recorded on that ROM (its
rom_sha1) under RUNS/aibench/ or testbench/references/; with none it says so and exits 2 (the static tier counts that
as a skip).
The simulator is that ROM's build (simbuild.py), so its data comes from the same ROM; its AI must be the ROM's
(src/ for an AI build of this project, the same sources for the Spanish rc44).

Cases the simulator cannot express (trainer items, doubles, a move the engine refused) are counted apart. Exit 0 when
every complete case gives the DS's choice, setter call, option values and snapshot (the Spanish bar: 202 of 202), 1
when one differs, 2 when the ROM has no bench record.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import aibench  # noqa: E402
import replay  # noqa: E402
import simbuild  # noqa: E402
import simpool  # noqa: E402
from aidata import Data  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('results', nargs='?')
    ap.add_argument('--rom', default=simbuild.DEFAULT_ROM)
    ap.add_argument('--layout', help="a builder layout whose switches the AI compiles with (en: the English build's)")
    ap.add_argument('--all', action='store_true', help='every record, not only the complete ones')
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    sha1 = replay.rom_sha1(a.rom)
    saved = json.load(open(a.results)) if a.results else None
    if saved is None:
        runs = replay.bench_runs(sha1)
        if not runs:
            print('no advanced bench run on %s (SHA-1 %s); make one with bench/aibench.py --advanced --rom %s'
                  % (a.rom, sha1, a.rom))
            sys.exit(replay.NO_RECORD)
        a.results, saved = runs[0], json.load(open(runs[0]))
    if saved.get('rom_sha1') != sha1:
        sys.exit('%s was recorded on a ROM with SHA-1 %s, not %s (%s)' % (a.results, saved.get('rom_sha1'), sha1, a.rom))
    print('records %s, ROM %s (SHA-1 %s)' % (a.results, a.rom, sha1))
    sim = simbuild.build(a.rom, a.layout)
    d = Data(a.rom)
    specs = {s['id']: s for s in aibench.scenarios()}
    work = tbpaths.run_dir('sim', 'bench_check')
    results = [r for r in saved['results'] if r.get('adv') and r['adv'].get('options')]
    if not a.all:
        results = [r for r in results if replay.kind(r) == 'complete']
    b = replay.Builder(d)
    path = os.path.join(work, 'bench_cases_%s.txt' % sha1[:8])
    with open(path, 'w') as f:
        f.write('\n'.join(b.case(r, specs[r['id']])[0] for r in results) + '\n')
    p = simpool.run([sim, 'bench', path], capture_output=True, text=True, check=True)
    outs = {o['id']: o for o in map(json.loads, p.stdout.splitlines())}
    tally = collections.Counter()
    failed = []
    for r in results:
        out = outs[r['id']]
        group = 'unsupported' if out['unsupported'] else replay.kind(r)
        snap, opt, chosen_ok, vdiff, call = replay.compare(r, out)
        tally[group, 'cases'] += 1
        tally[group, 'chosen'] += chosen_ok
        tally[group, 'values'] += not opt
        tally[group, 'snap'] += not snap
        if group == 'complete' and (not chosen_ok or opt or snap):
            failed.append(r['id'])
        if (not chosen_ok or opt or snap) and (a.v or group != 'unsupported'):
            print('%s [%s] chosen %s, values %s' % (r['id'], group, 'same' if chosen_ok else 'DIFF',
                                                    'same' if not opt else 'DIFF (max %s)' % vdiff))
            for k, w, g in snap:
                print('   snapshot %-8s DS %s sim %s' % (k, w, g))
            for i, w, g in opt[:4]:
                print('   option %d DS %s sim %s' % (i, w, g))
            if not chosen_ok:
                print('   call DS %s sim %s' % (r.get('call'), call))
    for group in sorted({g for g, _ in tally}):
        n = tally[group, 'cases']
        print('%-12s %3d cases: chosen same %d (%.1f%%), all option values exact %d (%.1f%%), snapshot exact %d' % (
            group, n, tally[group, 'chosen'], 100 * tally[group, 'chosen'] / n, tally[group, 'values'],
            100 * tally[group, 'values'] / n, tally[group, 'snap']))
    print('%s: %d of %d complete cases differ from the DS%s' % ('FAIL' if failed else 'PASS', len(failed),
                                                               tally['complete', 'cases'],
                                                               (': ' + ', '.join(failed[:10])) if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
