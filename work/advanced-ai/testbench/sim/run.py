"""The simulator against the emulator's self-play games: the same matchups, sides, sizes and repeat counts.

  .venv/bin/python work/advanced-ai/testbench/sim/run.py [--rom ROM] [--emu EMU.jsonl] [--reps R] [--seed S]
                                                         [--p0 adv] [--p1 adv]

Reads the emulator's games (tools/sim/logstats.py games; made here when --emu is not given), finds each side's team
among the trainer teams sim/gen_simdata.py exported from ROM (the ROM the emulator ran) (by name, the members' slots and their species and moves),
(gen_simdata.all_teams: the trainer teams, then the extra teams such as aivsai's random ones), writes the matchups
to RUNS/sim/run/pairs.txt, plays each R times (default 1) with that ROM's simulator (simbuild.py), and prints
logstats.py's comparison. The games go to RUNS/sim/run/sim_games.jsonl, the emulator's to RUNS/sim/run/emu_self.jsonl.
"""
import argparse
import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import gen_simdata  # noqa: E402
import simbuild  # noqa: E402
import simpool  # noqa: E402
import turnlog  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BUILD = os.path.join(tbpaths.RUNS, 'sim', 'run')


def find_team(teams, side):
    """The exported team index and the slots of a log's team (side: logstats' team object). A mixed team (aivsai
    --teams mixed) gives -1 and, per member, (its place in the mixed team, source team, source slot)."""
    slots = side['slots'] if side['slots'] is not None else list(range(len(side['mons'])))
    if side['name'].startswith('Mixed '):
        src = turnlog.find_members(teams, side)
        if src is None:
            raise SystemExit('mixed team %r: a member is not among the exported teams' % side['name'])
        return -1, [(k, t, s) for k, (t, s) in zip(slots, src)]
    found = []
    for i, t in enumerate(teams):
        if t['name'] != side['name'] or max(slots) >= len(t['team']):
            continue
        if all(t['team'][s]['species'] == m['species'] and [str(x) for x in t['team'][s]['moves']] == m['moves']
               for s, m in zip(slots, side['mons'])):
            found.append(i)
    if len(found) != 1:
        raise SystemExit('team %r (%s): %d matches among the exported teams' % (
            side['name'], ', '.join(m['species'] for m in side['mons']), len(found)))
    return found[0], slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default=simbuild.DEFAULT_ROM, help='the ROM the emulator games ran on')
    ap.add_argument('--emu', help="the emulator's games (logstats.py games); made from RUNS/aivsai when omitted")
    ap.add_argument('--reps', type=int, default=1)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--p0', help='engine side 0, the player side (default adv; orig with --orig)')
    ap.add_argument('--p1', default='adv')
    ap.add_argument('--orig', action='store_true',
                    help="the emulator's adv-vs-orig games (the original AI on the player side) instead of self-play")
    ap.add_argument('--runs', help='with --orig: only these run directories (comma-separated names)')
    a = ap.parse_args()
    a.p0 = a.p0 or ('orig' if a.orig else 'adv')
    os.makedirs(BUILD, exist_ok=True)
    emu = a.emu or os.path.join(BUILD, 'emu_orig.jsonl' if a.orig else 'emu_self.jsonl')
    if not a.emu:
        subprocess.run([PY, os.path.join(HERE, 'logstats.py'), 'games', '-o', emu] + (['--orig'] if a.orig else []),
                       check=True)
    if a.runs:
        keep = set(a.runs.split(','))
        sub = emu.replace('.jsonl', '_sel.jsonl')
        with open(sub, 'w') as f:
            f.writelines(x for x in open(emu) if json.loads(x)['run'] in keep)
        emu = sub
    teams = gen_simdata.all_teams(a.rom)
    sim = simbuild.build(a.rom)
    lines = []
    for line in open(emu):
        g = json.loads(line)
        if not g['finished']:
            continue
        sides = [find_team(teams, t) for t in g['teams']]
        lines.append('pair %s %d %s' % (g['scenario'], g['game'], ' '.join(
            '%d %d %s' % (i, len(slots), ' '.join(' '.join(map(str, x)) if i < 0 else str(x) for x in slots))
            for i, slots in sides)))
    pairs = os.path.join(BUILD, 'pairs.txt')
    with open(pairs, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    out = os.path.join(BUILD, 'sim_games.jsonl')
    with open(out, 'w') as f:
        simpool.run([sim, 'play', '--pairs', pairs, '--reps', str(a.reps), '--seed', str(a.seed),
                        '--p0', a.p0, '--p1', a.p1], stdout=f, check=True)
    print('%d matchups from %s, %d simulator games -> %s' % (len(lines), emu, len(lines) * a.reps, out))
    subprocess.run([PY, os.path.join(HERE, 'logstats.py'), 'compare', emu, out], check=True)
    agreement(emu, out, len(lines))
    if a.orig:
        win_rates(emu, out, len(lines))


def agreement(emu, out, n):
    """Does the side that won on the emulator win in the simulator? Per emulator game, the share of the simulator's
    replays won by the same side. For scale, the same measure between the emulator's own games of one matchup in one
    orientation (the same teams on the same sides), over the games that have such replays. Then the matchups where the
    two disagree most."""
    games = [json.loads(x) for x in open(emu)]
    games = [g for g in games if g['finished']]
    sim = [json.loads(x) for x in open(out)]
    key = lambda g: json.dumps([[t['name'], [m['species'] for m in t['mons']]] for t in g['teams']])
    won = collections.defaultdict(list)            # emulator game index -> the simulator's winners
    for i, g in enumerate(sim):
        won[i % n].append(g['winner'])
    share = {i: sum(w == games[i]['winner'] for w in won[i]) / len(won[i]) for i in range(n) if games[i]['winner'] is not None}
    print('\nwinner agreement: the simulator gives the emulator\'s winner in %.1f%% of its replays of %d games' %
          (100 * sum(share.values()) / len(share), len(share)))
    groups = collections.defaultdict(list)
    for i in share:
        groups[key(games[i])].append(i)
    rep = [ix for ix in groups.values() if len(ix) > 1]
    emu_pairs = [(games[x]['winner'] == games[y]['winner']) for ix in rep for k, x in enumerate(ix) for y in ix[k + 1:]]
    sim_rep = [share[i] for ix in rep for i in ix]
    if emu_pairs:
        print('  on the %d games whose matchup the emulator replayed: the simulator %.1f%%, the emulator against its own '
              'replays %.1f%% (%d pairs)' % (len(sim_rep), 100 * sum(sim_rep) / len(sim_rep),
                                            100 * sum(emu_pairs) / len(emu_pairs), len(emu_pairs)))
    worst = sorted(groups.values(), key=lambda ix: sum(share[i] for i in ix) / len(ix))[:8]
    print('  largest disagreements (the emulator\'s wins for its winner / games; the simulator\'s share for that side):')
    for ix in worst:
        g = games[ix[0]]
        print('    %-28s vs %-28s emulator %d/%d, simulator %.0f%%  (%s %s g%d)' % (
            g['teams'][0]['name'][:28], g['teams'][1]['name'][:28], sum(games[i]['winner'] == g['winner'] for i in ix),
            len(ix), 100 * sum(share[i] for i in ix) / len(ix), g['run'], g['scenario'], g['game']))


def win_rates(emu, out, n):
    """The trainer side's (the advanced AI's) win rate per emulator run against the simulator's on the same games, with
    a binomial 95% interval for the emulator and the paired difference's z (clustered by game)."""
    games = [g for g in (json.loads(x) for x in open(emu)) if g['finished']]
    sim = [json.loads(x) for x in open(out)]
    share = collections.defaultdict(list)
    for i, g in enumerate(sim):
        share[i % n].append(g['winner'] == 0)
    runs = collections.defaultdict(list)
    for i, g in enumerate(games):
        if g['winner'] is not None:
            runs[g['run']].append((g['winner'] == 0, sum(share[i]) / len(share[i])))
    print('\nthe advanced AI\'s win rate, emulator against simulator, per run (the same games, sizes advanced:original):')
    print('  %-24s %5s %6s %16s %9s %6s' % ('run', 'games', 'sizes', 'emulator', 'simulator', 'z'))
    total = []
    for run in sorted(runs):
        rows = runs[run]
        total += rows
        print('  ' + row(run, rows, games))
    print('  ' + row('all', total, games))


def row(name, rows, games):
    k = len(rows)
    e = sum(x for x, _ in rows) / k
    s = sum(y for _, y in rows) / k
    d = [x - y for x, y in rows]
    md = sum(d) / k
    sd = (sum((x - md) ** 2 for x in d) / max(1, k - 1)) ** 0.5 / k ** 0.5
    sizes = next(('%d:%d' % tuple(g['sizes']) for g in games if g['run'] == name), '')
    return '%-24s %5d %6s %5.1f%% (%2.0f-%2.0f) %8.1f%% %+6.1f' % (
        name, k, sizes, 100 * e, 100 * max(0, e - 1.96 * (e * (1 - e) / k) ** 0.5),
        100 * min(1, e + 1.96 * (e * (1 - e) / k) ** 0.5), 100 * s, (s - e) / sd if sd else 0)


if __name__ == '__main__':
    main()
