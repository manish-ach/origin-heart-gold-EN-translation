"""luck_gate.py run|stats: the plain simulator gate (no luck adjustment) of a tuning against the defaults, as RC28 ran it:
the level-80 pool (pairs80, 25,122 matchups), one fresh seed, 8 games per matchup against the original-AI bot (paired
with the defaults' games of the same seed) and 4 per side assignment head to head (tuned against the defaults).

  luck_gate.py run   --sim SIM --pairs PAIRS --tuned V,.. --seed S --out DIR [--workers 3] [--block 500] [--base FILE]
                     [--against V,.. --h2h-only]   (head to head against another tuning instead of the defaults)
  luck_gate.py stats --out DIR --base FILE

The matchups go in blocks, each block's three jobs (bot, h2h with the tuning on side 1, h2h with it on side 0) one after
the other, so the numbers so far always cover the same matchups for both measures. A finished block's file is kept, so
the same command resumes. FILE (--base): the defaults' games against the bot on the same seed, in cf rate --per-game's
format (or omit it to play them too)."""
import argparse
import glob
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import simpool  # noqa: E402

RES = {'W': 1.0, 'D': 0.5, 'L': 0.0}


def jobs(a, nlines):
    out = []
    for lo in range(0, nlines, a.block):
        hi = min(nlines, lo + a.block)
        tag = '%05d' % lo
        other = lambda side: ['--tune-' + side, a.against] if a.against else []
        if not a.h2h_only:
            out.append(('bot', tag, ['--p0', 'orig', '--p1', 'adv', '--reps', '8', '--tune-s1', a.tuned], lo, hi))
        out.append(('h2h1', tag, ['--p0', 'adv', '--p1', 'adv', '--reps', '4', '--tune-s1', a.tuned] + other('s0'), lo, hi))
        out.append(('h2h2', tag, ['--p0', 'adv', '--p1', 'adv', '--reps', '4', '--tune-s0', a.tuned] + other('s1'), lo, hi))
        if not a.base and not a.h2h_only:
            out.append(('base', tag, ['--p0', 'orig', '--p1', 'adv', '--reps', '8'], lo, hi))
    return out


def run(a):
    os.makedirs(a.out, exist_ok=True)
    nlines = sum(1 for l in open(a.pairs) if l.startswith('pair '))
    todo = [j for j in jobs(a, nlines) if not os.path.exists(os.path.join(a.out, '%s_%s.txt' % (j[0], j[1])))]
    running = []
    while todo or running:
        while todo and len(running) < a.workers:
            kind, tag, args, lo, hi = todo.pop(0)
            path = os.path.join(a.out, '%s_%s.txt' % (kind, tag))
            cmd = [a.sim, 'cf', 'luck', '--pairs', a.pairs, '--seed', str(a.seed), '--luck-k', '0',
                   '--lines', '%d:%d' % (lo, hi)] + args
            running.append((simpool.popen(cmd, stdout=open(path + '.tmp', 'w')), path))
        time.sleep(2)
        for pr, path in running[:]:
            if pr.poll() is not None:
                running.remove((pr, path))
                if pr.returncode == 0:
                    os.rename(path + '.tmp', path)
                else:
                    sys.exit('%s failed (%d)' % (path, pr.returncode))


def read_luck(paths):
    g = {}
    for p in paths:
        for line in open(p):
            f = line.split()
            g[(int(f[0]), int(f[1]))] = (RES[f[2]], f[2] + f[5])
    return g


def read_rate(path):
    g = {}
    for li, line in enumerate(open(path)):
        for rep, x in enumerate(line.split()[8:]):
            g[(li, rep)] = (RES[x[0]], x)
    return g


def clustered(vals, keys):
    n = len(vals)
    m = sum(vals) / n
    by = {}
    for v, k in zip(vals, keys):
        by[k] = by.get(k, 0.0) + v - m
    c = len(by)
    return m, math.sqrt(sum(s * s for s in by.values()) * c / (c - 1)) / n


def stats(a):
    tuned = read_luck(sorted(glob.glob(os.path.join(a.out, 'bot_*.txt'))))
    base = read_rate(a.base) if a.base else read_luck(sorted(glob.glob(os.path.join(a.out, 'base_*.txt'))))
    ks = sorted(set(tuned) & set(base))
    if ks:
        cl = [k[0] for k in ks]
        mt, st = clustered([tuned[k][0] for k in ks], cl)
        mb, sb = clustered([base[k][0] for k in ks], cl)
        md, sd = clustered([tuned[k][0] - base[k][0] for k in ks], cl)
        better = sum(tuned[k][0] > base[k][0] for k in ks)
        worse = sum(tuned[k][0] < base[k][0] for k in ks)
        print('against the bot: %d games (%d matchups): tuned %.3f%%, defaults %.3f%%; tuned - defaults %+.3f points '
              '(matchup-clustered SE %.3f, z %+.2f); %d games better, %d worse' % (
                  len(ks), len(set(cl)), 100 * mt, 100 * mb, 100 * md, 100 * sd, md / sd if sd else 0, better, worse))
    h1 = read_luck(sorted(glob.glob(os.path.join(a.out, 'h2h1_*.txt'))))
    h2 = read_luck(sorted(glob.glob(os.path.join(a.out, 'h2h2_*.txt'))))
    ks = sorted(set(h1) & set(h2))
    if ks:
        cl = [k[0] for k in ks]
        sc = [(h1[k][0] + 1 - h2[k][0]) / 2 for k in ks]
        m, se = clustered(sc, cl)
        both = sum(h1[k][0] == 1 and h2[k][0] == 0 for k in ks)
        lost = sum(h1[k][0] == 0 and h2[k][0] == 1 for k in ks)
        print('head to head: %d pairs (%d games, %d matchups): tuned scores %.3f%% (matchup-clustered SE %.3f, z %+.2f '
              'vs 50%%); tuned won both %d, defaults won both %d' % (len(ks), 2 * len(ks), len(set(cl)), 100 * m, 100 * se,
                                                                      (m - 0.5) / se if se else 0, both, lost))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('run', 'stats'))
    ap.add_argument('--sim')
    ap.add_argument('--pairs')
    ap.add_argument('--tuned')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--block', type=int, default=500)
    ap.add_argument('--base')
    ap.add_argument('--against', help='the other tuning head to head (default: the defaults)')
    ap.add_argument('--h2h-only', action='store_true')
    a = ap.parse_args()
    run(a) if a.cmd == 'run' else stats(a)


if __name__ == '__main__':
    main()
