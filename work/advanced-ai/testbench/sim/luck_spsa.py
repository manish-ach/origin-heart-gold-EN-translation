"""luck_spsa.py: SPSA over tools/ai/tune.h's constants, judged head to head, the fishtest way: one iteration is one pair
of games, theta+ against theta- with the sides swapped on the same game seed (sim cf serve), and its signal is the
luck-adjusted score (sim cf luck's judge). Workers play iterations concurrently; theta moves as each result arrives.

  luck_spsa.py --sim SIM --pairs PAIRS --tune TUNE_H --log LOG [--iters N] [--minutes M] [--workers W] [--seed S]
               [--c C] [--a A] [--luck-k K] [--leaf-w W,...] [--signal adj|raw] [--resume]

Coordinates are in steps (tune.h's step per constant). c_k = C / (k + 1)^0.101 and a_k = A / (0.1 N + k + 1)^0.602;
theta+- = theta +- c_k delta (delta random signs), rounded and clipped to tune.h's range; the gradient estimate is
(score+ - score-) / (2 c_k delta), score+ theta+'s score over the pair (0 to 2). LOG gets one tab-separated line per
iteration with everything needed to replay or re-analyze it (luck_stats.py spsa LOG)."""
import argparse
import json
import os
import random
import re
import selectors
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import simpool  # noqa: E402


def read_tune(path):
    rows = re.findall(r'X\((\w+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)', open(path).read())
    return [{'name': n, 'default': int(d), 'lo': int(lo), 'hi': int(hi), 'step': int(st)} for n, d, lo, hi, st in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sim', required=True)
    ap.add_argument('--pairs', required=True)
    ap.add_argument('--tune', required=True)
    ap.add_argument('--log', required=True)
    ap.add_argument('--iters', type=int, default=24000)
    ap.add_argument('--minutes', type=float, default=1e9)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--seed', type=int, default=9311)
    ap.add_argument('--c', type=float, default=1.5)
    ap.add_argument('--a', type=float, default=1.5)
    ap.add_argument('--luck-k', type=int, default=8)
    ap.add_argument('--signal', choices=('adj', 'raw'), default='adj')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--leaf-w', default='', help="the judge's weights for sim cf serve (default: leaf.c's)")
    a = ap.parse_args()
    if simpool.size():
        a.workers = min(a.workers, simpool.size())  # the servers never exit: more would wait forever

    P = read_tune(a.tune)
    n = len(P)
    nlines = sum(1 for l in open(a.pairs) if l.startswith('pair '))
    x = [p['default'] / p['step'] for p in P]
    k0 = 0
    if a.resume and os.path.exists(a.log):
        last = None
        for line in open(a.log):
            if line[0].isdigit():
                last = line
        if last:
            f = last.rstrip('\n').split('\t')
            k0 = int(f[0]) + 1
            x = json.loads(f[-1])
    rnd = random.Random(a.seed * 1000003 + k0)
    big_a = 0.1 * a.iters
    log = open(a.log, 'a')
    if k0 == 0:
        log.write('# ' + json.dumps({'params': P, 'args': vars(a), 'nlines': nlines}) + '\n')
        log.write('k\tworker\tline\trep\tck\tak\tdelta\ttplus\ttminus\tra\tla\trb\tlb\tta\ttb\traw\tadj\tx\n')
        log.flush()

    def theta(xv, sign, ck, delta):
        out = []
        for i, p in enumerate(P):
            v = round((xv[i] + sign * ck * delta[i]) * p['step'])
            out.append(min(p['hi'], max(p['lo'], v)))
        return out

    procs = []
    sel = selectors.DefaultSelector()
    for w in range(a.workers):
        cmd = [a.sim, 'cf', 'serve', '--pairs', a.pairs, '--p0', 'adv', '--p1', 'adv', '--luck-k', str(a.luck_k)] + (['--leaf-w', a.leaf_w] if a.leaf_w else [])
        pr = simpool.popen(cmd, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True, bufsize=1)
        procs.append(pr)
        sel.register(pr.stdout, selectors.EVENT_READ, w)
    pending = {}
    k_next = k0
    done = 0
    t0 = time.time()
    deadline = t0 + 60 * a.minutes

    def send(w):
        nonlocal k_next
        k = k_next
        k_next += 1
        ck = a.c / (k + 1) ** 0.101
        ak = a.a / (big_a + k + 1) ** 0.602
        delta = [rnd.choice((-1, 1)) for _ in range(n)]
        tp, tm = theta(x, 1, ck, delta), theta(x, -1, ck, delta)
        li, rep = rnd.randrange(nlines), rnd.randrange(1 << 20)
        pending[k] = (w, li, rep, ck, ak, delta, tp, tm)
        procs[w].stdin.write('%d %d %d %d %s %s\n' % (k, li, rep, a.seed, ' '.join(map(str, tp)), ' '.join(map(str, tm))))
        procs[w].stdin.flush()

    for w in range(a.workers):
        if k_next < a.iters:
            send(w)
    while pending:
        for key, _ in sel.select():
            w = key.data
            line = procs[w].stdout.readline()
            if not line:
                sys.exit('worker %d ended' % w)
            f = line.split()
            k = int(f[0])
            ra, la, rb, lb = map(float, f[1:5])
            ta, tb = int(f[5]), int(f[6])
            _, li, rep, ck, ak, delta, tp, tm = pending.pop(k)
            raw = 2 * (ra - rb)                       # score+ - score-, score+ = ra + 1 - rb
            adj = 2 * ((ra - la) - (rb - lb))
            d = adj if a.signal == 'adj' else raw
            for i, p in enumerate(P):
                x[i] += ak * d / (2 * ck * delta[i])
                x[i] = min(p['hi'] / p['step'], max(p['lo'] / p['step'], x[i]))
            log.write('%d\t%d\t%d\t%d\t%.5f\t%.6f\t%s\t%s\t%s\t%.1f\t%.6f\t%.1f\t%.6f\t%d\t%d\t%.6f\t%.6f\t%s\n' % (
                k, w, li, rep, ck, ak, ''.join('+' if v > 0 else '-' for v in delta), ','.join(map(str, tp)),
                ','.join(map(str, tm)), ra, la, rb, lb, ta, tb, raw, adj, json.dumps([round(v, 5) for v in x])))
            done += 1
            if done % 200 == 0:
                log.flush()
                el = time.time() - t0
                print('%s k %d, %.2f it/s, theta %s' % (time.strftime('%H:%M:%S'), k, done / el,
                                                         [round(v * p['step']) for v, p in zip(x, P)]), flush=True)
            if k_next < a.iters and time.time() < deadline:
                send(w)
    log.flush()
    for pr in procs:
        pr.stdin.close()
        pr.wait()
    print('done: %d iterations in %.0f s; theta %s' % (done, time.time() - t0,
                                                      [round(v * p['step']) for v, p in zip(x, P)]), flush=True)


if __name__ == '__main__':
    main()
