"""Side-asymmetry check on self-play runs: a pair's two games start from mirror-image positions (game 0 has team A on
the trainer side, game 1 on the player side), so each team's turn-1 option values must be equal in both games. Any
difference means some input to the AI depends on the side it plays.

  .venv/bin/python work/advanced-ai/testbench/versus/mirror_check.py RUNS/aivsai/reports/runs/<run>_self [--min 5]

Ported unchanged from the Spanish workspace's qa/aivsai/mirror_check.py (dc8577c) (it reads only the logs' side names
and option lines, which are the same in every language)."""
import argparse
import glob
import os
import re

OPT = re.compile(r'^\s+options: (.*)$')
DEC = re.compile(r'^  (TRAINER|PLAYER)\s+(.+?) -> ')


def turn1(path):
    """{side: (active, {option: value})} for the first decision of each side on turn 1."""
    out, side, lines = {}, None, open(path, encoding='utf-8').read().split('--- Turn 2 ')[0].splitlines()
    for line in lines:
        m = DEC.match(line)
        if m:
            side, active = m.group(1), m.group(2).strip()
            continue
        o = OPT.match(line)
        if o and side and side not in out:
            vals = {}
            for part in o.group(1).split(', '):
                k, _, v = part.rpartition('=')
                v = v.split(' ')[0]
                if k and re.fullmatch(r'-?\d+', v):
                    vals[k.strip()] = int(v)
            out[side] = (active, vals)
            side = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('--min', type=int, default=5, help='report differences of at least this many points')
    a = ap.parse_args()
    pairs = sorted({os.path.basename(p)[:4] for p in glob.glob(os.path.join(a.run, 's*_g0.log'))})
    checked = diff = 0
    for sc in pairs:
        g0, g1 = os.path.join(a.run, sc + '_g0.log'), os.path.join(a.run, sc + '_g1.log')
        if not os.path.exists(g1):
            continue
        t0, t1 = turn1(g0), turn1(g1)
        for team, s0, s1 in (('A', 'TRAINER', 'PLAYER'), ('B', 'PLAYER', 'TRAINER')):
            if s0 not in t0 or s1 not in t1 or t0[s0][0] != t1[s1][0]:
                continue
            v0, v1 = t0[s0][1], t1[s1][1]
            common = sorted(set(v0) & set(v1))
            checked += 1
            bad = [(k, v0[k], v1[k]) for k in common if abs(v0[k] - v1[k]) >= a.min]
            if bad:
                diff += 1
                print('%s team %s %s (%s in g0, %s in g1): %s' % (sc, team, t0[s0][0], s0.lower(), s1.lower(),
                      ', '.join('%s %d vs %d' % b for b in bad)))
    print('%d mirrored turn-1 decisions checked, %d differ by %d+ points' % (checked, diff, a.min))


if __name__ == '__main__':
    main()
