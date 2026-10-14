"""Lookahead variants against the plain games on the same seeds (sim cf la), by band of the level-80 pool.

  la_run.py sample --rates R -o SAMPLE [--low 200 --mid 1000 --high 400] [--seed 17]
  la_run.py run --sample SAMPLE --name NAME [--foe orig|adv] [--workers 4] -- <sim cf la options>
  la_run.py report NAME [NAME ...] [--foe orig|adv]

A run writes RUNS/sim/la/<foe>/<NAME>.txt (one line per matchup: as sim cf mc prints, plus each game's result) and
<NAME>.stats (one line per decision: scenario, game, turn, actions, turns simulated, playout-policy decisions,
overridden). The plain games are the run named 'plain' (--margin 9: no override). Every gain is paired with them.
"""
import argparse
import concurrent.futures
import math
import os
import random
import statistics
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'lib'))
import tbpaths  # noqa: E402,F401
import simbuild  # noqa: E402
import simpool  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.environ.get('LA_SIM') or simbuild.binary()
OUT = os.path.join(tbpaths.RUNS, 'sim', 'la')
BANDS = (('low', 0.0, 0.20), ('mid', 0.20, 0.95), ('high', 0.95, 1.01))


def pair_line(scen, a, b):
    return 'pair %s 0 %d 6 0 1 2 3 4 5 %d 6 0 1 2 3 4 5' % (scen, a, b)


def read_rates(path):
    r = {}
    for line in open(path):
        f = line.split()
        w, d, l = int(f[4]), int(f[5]), int(f[6])
        r[(int(f[2]), int(f[3]))] = (w + 0.5 * d) / (w + d + l)
    return r


def band_of(rate):
    return next(b for b, lo, hi in BANDS if lo <= rate < hi)


def cmd_sample(a):
    r = read_rates(a.rates)
    excl = set()
    for path in a.exclude or []:
        excl |= {(int(l.split()[3]), int(l.split()[11])) for l in open(path) if l.startswith('pair ')}
    rnd = random.Random(a.seed)
    want = {'low': a.low, 'mid': a.mid, 'high': a.high}
    lines, k = [], 0
    with open(a.o + '.shares', 'w') as f:
        mean = sum(r.values()) / len(r)
        f.write('pool %d 1.0 %.6f\n' % (len(r), mean))
        for b, lo, hi in BANDS:
            pool = sorted(m for m, v in r.items() if lo <= v < hi)
            draw = [m for m in pool if m not in excl]
            f.write('%s %d %.6f %.6f\n' % (b, len(pool), len(pool) / len(r), sum(r[m] for m in pool) / max(1, len(pool))))
            for tt, tp in rnd.sample(draw, min(want[b], len(draw))):
                lines.append(pair_line('%s%05d' % (b[0], k), tt, tp))
                k += 1
    open(a.o, 'w').write('\n'.join(lines) + '\n')
    print(open(a.o + '.shares').read() + '%d matchups drawn' % len(lines))


def cmd_run(a, extra):
    lines = [l.rstrip('\n') for l in open(a.sample) if l.startswith('pair ')]
    d = os.path.join(OUT, a.foe)
    os.makedirs(d, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='la_', dir=d)
    n = a.chunks or 4 * a.workers
    size = math.ceil(len(lines) / n)
    parts = [lines[i:i + size] for i in range(0, len(lines), size)]

    def one(k):
        pf, of, sf = (os.path.join(tmp, '%s%04d.txt' % (x, k)) for x in 'pos')
        open(pf, 'w').write('\n'.join(parts[k]) + '\n')
        if a.mode == 'mc':
            open(sf, 'w').close()
        with open(of, 'w') as o:
            return simpool.run([SIM, 'cf', a.mode, '--pairs', pf, '--reps', str(a.reps), '--seed', str(a.seed),
                                   '--p0', a.foe] + (['--stats', sf] if a.mode == 'la' else []) + extra,
                                  stdout=o).returncode

    with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        codes = list(ex.map(one, range(len(parts))))
    if any(codes):
        raise SystemExit('a sim cf la process failed')
    with open(os.path.join(d, a.name + '.txt'), 'w') as out, open(os.path.join(d, a.name + '.stats'), 'w') as st:
        for k in range(len(parts)):
            out.write(open(os.path.join(tmp, 'o%04d.txt' % k)).read())
            st.write(open(os.path.join(tmp, 's%04d.txt' % k)).read())
    open(os.path.join(d, a.name + '.cmd'), 'w').write(' '.join([a.mode, '--reps', str(a.reps), '--seed', str(a.seed), '--p0',
                                                                  a.foe] + extra) + '\n')
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)


def read_run(path):
    """{scenario: (games 'WDL...', overridden, choices)}"""
    r = {}
    for line in open(path):
        f = line.split()
        games = f[10] if len(f) > 10 else 'W' * int(f[4]) + 'D' * int(f[5]) + 'L' * int(f[6])
        r[f[0]] = (games, int(f[8]), int(f[9]))
    return r


def score(c):
    return 1.0 if c == 'W' else 0.5 if c == 'D' else 0.0


def shares(sample):
    s = {}
    for line in open(sample + '.shares'):
        f = line.split()
        s[f[0]] = (int(f[1]), float(f[2]), float(f[3]))
    return s


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0


def summarize(name, foe, sample, keys=None, plain_name='plain'):
    d = os.path.join(OUT, foe)
    plain, var = read_run(os.path.join(d, plain_name + '.txt')), read_run(os.path.join(d, name + '.txt'))
    if keys:
        var = {k: v for k, v in var.items() if k in keys}
    sh = shares(sample)
    rows, pool_gain, pool_var = {}, 0.0, 0.0
    for b, _, _ in BANDS:
        keys = [k for k in var if k[0] == b[0] and k in plain]
        if not keys:
            continue
        diffs, base, new, games, over, cho = [], 0.0, 0.0, 0, 0, 0
        for k in keys:
            gp, gv = plain[k][0], var[k][0]
            diffs.append(sum(score(x) for x in gv) - sum(score(x) for x in gp))
            base += sum(score(x) for x in gp)
            new += sum(score(x) for x in gv)
            games += len(gv)
            over += var[k][1]
            cho += var[k][2]
        per = games / len(keys)
        gain = sum(diffs) / games
        se = statistics.pstdev(diffs) / per / math.sqrt(len(keys)) if len(keys) > 1 else 0
        rows[b] = {'games': games, 'plain': base / games, 'rate': new / games, 'gain': gain, 'se': se,
                   'over': over / max(1, cho), 'share': sh[b][1]}
        pool_gain += sh[b][1] * gain
        pool_var += (sh[b][1] * se) ** 2
    st = [list(map(int, l.split()[3:7])) for l in open(os.path.join(d, name + '.stats'))]
    turns, calls = [x[1] for x in st], [x[2] for x in st]
    return {'name': name, 'bands': rows, 'pool_gain': pool_gain, 'pool_se': math.sqrt(pool_var),
            'pool_base': sh['pool'][2], 'decisions': len(st),
            'turns': (statistics.median(turns) if turns else 0, pct(turns, 0.9), max(turns) if turns else 0),
            'calls': (statistics.median(calls) if calls else 0, pct(calls, 0.9), max(calls) if calls else 0),
            'mean_turns': sum(turns) / max(1, len(turns))}


def cmd_report(a):
    print('%-26s %6s  %-22s %-22s %-22s  %-13s %8s %18s %18s' % ('variant', 'games', 'low: rate gain(SE)', 'mid: rate gain(SE)',
                                                                 'high: rate gain(SE)', 'pool gain(SE)', 'override',
                                                                 'turns med/p90/max', 'calls med/p90/max'))
    keys = {l.split()[1] for l in open(a.keys) if l.startswith('pair ')} if a.keys else None
    for name in a.names:
        s = summarize(name, a.foe, a.sample, keys, a.plain)
        cells, g, ov, oc = [], 0, 0, 0
        for b, _, _ in BANDS:
            r = s['bands'].get(b)
            if r:
                cells.append('%5.1f %+5.1f(%.1f)' % (100 * r['rate'], 100 * r['gain'], 100 * r['se']))
                g += r['games']
                ov += r['over'] * r['games']
                oc += r['games']
            else:
                cells.append('')
        print('%-26s %6d  %-22s %-22s %-22s  %+5.2f(%.2f)   %6.1f%% %18s %18s' % (
            name, g, cells[0], cells[1], cells[2], 100 * s['pool_gain'], 100 * s['pool_se'], 100 * ov / max(1, oc),
            '%d/%d/%d' % s['turns'], '%d/%d/%d' % s['calls']))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('sample')
    p.add_argument('--rates', required=True)
    p.add_argument('-o', required=True)
    p.add_argument('--low', type=int, default=200)
    p.add_argument('--mid', type=int, default=1000)
    p.add_argument('--high', type=int, default=400)
    p.add_argument('--seed', type=int, default=17)
    p.add_argument('--exclude', nargs='*', help='pairs files whose matchups are not drawn')
    p = sub.add_parser('run')
    p.add_argument('--sample', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--foe', default='orig')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--chunks', type=int, default=0)
    p.add_argument('--mode', choices=('la', 'mc'), default='la')
    p.add_argument('--reps', type=int, default=2)
    p.add_argument('--seed', type=int, default=7)
    p = sub.add_parser('report')
    p.add_argument('names', nargs='+')
    p.add_argument('--foe', default='orig')
    p.add_argument('--sample', default=os.path.join(OUT, 'sample.txt'))
    p.add_argument('--keys', help='only the matchups of this pairs file')
    p.add_argument('--plain', default='plain', help='the run of the plain games')
    argv = sys.argv[1:]
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    if a.cmd == 'sample':
        cmd_sample(a)
    elif a.cmd == 'run':
        cmd_run(a, extra)
    else:
        cmd_report(a)


if __name__ == '__main__':
    main()
