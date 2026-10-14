"""luck_stats.py: the numbers behind luck-adjusted results (sim cf luck lines: INDEX REP W|D|L LUCK TURNS HASH).

  luck_stats.py single FILE            one build: plain and adjusted rates, the mean luck (unbiasedness) and the variance ratio
  luck_stats.py paired A B             two builds on the same games: plain and adjusted A - B, their SEs, the variance ratio
  luck_stats.py h2h A1 A2              head to head: A1 has build A on side 1, A2 on side 0 (the same games); A's score
  luck_stats.py spsa LOG [--every N]   an SPSA log: unbiasedness and variance ratio of its pairs, gradient z per constant,
                                       the trajectory and the averaged theta of the second half

SEs are clustered by pairs line (matchup); z of the mean luck tests that the adjustment adds no bias. The variance ratio
(plain over adjusted) is how many plain games one adjusted game is worth for that quantity."""
import json
import math
import sys

RES = {'W': 1.0, 'D': 0.5, 'L': 0.0}


def read(path):
    g = {}
    for line in open(path):
        f = line.split()
        if len(f) == 6:
            g[(int(f[0]), int(f[1]))] = (RES[f[2]], float(f[3]), int(f[4]), f[5])
    return g


def clustered(vals, keys):
    """mean and matchup-clustered SE of vals (keys: the cluster of each value)"""
    n = len(vals)
    m = sum(vals) / n
    by = {}
    for v, k in zip(vals, keys):
        by[k] = by.get(k, 0.0) + v - m
    c = len(by)
    return m, math.sqrt(sum(s * s for s in by.values()) * c / (c - 1)) / n


def var(v):
    m = sum(v) / len(v)
    return sum((x - m) ** 2 for x in v) / (len(v) - 1)


def line(name, vals, keys):
    m, se = clustered(vals, keys)
    return '%-34s %8.4f%%  SE %.4f  (per-game var %.5f)' % (name, 100 * m, 100 * se, var(vals))


def single(path):
    g = read(path)
    ks = sorted(g)
    cl = [k[0] for k in ks]
    raw = [g[k][0] for k in ks]
    luck = [g[k][1] for k in ks]
    adj = [r - l for r, l in zip(raw, luck)]
    ml, sel = clustered(luck, cl)
    _, se_r = clustered(raw, cl)
    _, se_a = clustered(adj, cl)
    print('%s: %d games, %d matchups, %.1f turns per game' % (path, len(ks), len(set(cl)), sum(g[k][2] for k in ks) / len(ks)))
    print(line('  plain result (side 1)', raw, cl))
    print(line('  adjusted result', adj, cl))
    print('  mean luck (adjusted - plain = -luck) %+.4f points, SE %.4f, z %+.2f' % (100 * ml, 100 * sel, ml / sel))
    print('  variance ratio plain/adjusted: per game %.2f; clustered SE^2 %.2f' % (var(raw) / var(adj), (se_r / se_a) ** 2))
    return g


def paired(pa, pb):
    a, b = read(pa), read(pb)
    ks = sorted(set(a) & set(b))
    cl = [k[0] for k in ks]
    dr = [a[k][0] - b[k][0] for k in ks]
    da = [(a[k][0] - a[k][1]) - (b[k][0] - b[k][1]) for k in ks]
    mr, ser = clustered(dr, cl)
    ma, sea = clustered(da, cl)
    same = sum(a[k][3] == b[k][3] for k in ks)
    print('%s - %s: %d games (%.1f%% identical)' % (pa, pb, len(ks), 100 * same / len(ks)))
    print('  plain A - B    %+.4f points  SE %.4f  z %+.2f' % (100 * mr, 100 * ser, mr / ser if ser else 0))
    print('  adjusted A - B %+.4f points  SE %.4f  z %+.2f' % (100 * ma, 100 * sea, ma / sea if sea else 0))
    print('  adjusted - plain %+.4f points' % (100 * (ma - mr)))
    print('  variance ratio of the difference: per game %.2f; clustered SE^2 %.2f' % (var(dr) / var(da), (ser / sea) ** 2))


def h2h(p1, p2):
    a, b = read(p1), read(p2)
    ks = sorted(set(a) & set(b))
    cl = [k[0] for k in ks]
    sr = [(a[k][0] + 1 - b[k][0]) / 2 for k in ks]
    sa = [((a[k][0] - a[k][1]) + 1 - (b[k][0] - b[k][1])) / 2 for k in ks]
    mr, ser = clustered(sr, cl)
    ma, sea = clustered(sa, cl)
    both = sum(a[k][0] == 1 and b[k][0] == 0 for k in ks)
    lost = sum(a[k][0] == 0 and b[k][0] == 1 for k in ks)
    same = sum(a[k][3] == b[k][3] for k in ks)
    print('h2h %s / %s: %d pairs (%d games), identical pairs %.2f%%' % (p1, p2, len(ks), 2 * len(ks), 100 * same / len(ks)))
    print('  plain: A scores %.4f%%  SE %.4f  z %+.2f vs 50%%; A won both %d, B won both %d' % (
        100 * mr, 100 * ser, (mr - 0.5) / ser, both, lost))
    print('  adjusted: A scores %.4f%%  SE %.4f  z %+.2f vs 50%%' % (100 * ma, 100 * sea, (ma - 0.5) / sea))
    print('  variance ratio of the pair score: per pair %.2f; clustered SE^2 %.2f' % (var(sr) / var(sa), (ser / sea) ** 2))


def spsa(path, every=1000):
    head, rows = None, []
    for l in open(path):
        if l.startswith('# '):
            head = json.loads(l[2:])
        elif l[0].isdigit():
            rows.append(l.rstrip('\n').split('\t'))
    P = head['params']
    n = len(P)
    rows.sort(key=lambda f: int(f[0]))
    raw = [float(f[15]) for f in rows]
    adj = [float(f[16]) for f in rows]
    lines = [int(f[2]) for f in rows]
    print('%s: %d iterations (%d games)' % (path, len(rows), 2 * len(rows)))
    dif = [adj[i] - raw[i] for i in range(len(rows))]
    m, se = clustered(dif, lines)
    print('  pairs: plain diff mean %+.4f, adjusted %+.4f; adjusted - plain %+.4f (SE %.4f, z %+.2f)' % (
        sum(raw) / len(raw), sum(adj) / len(adj), m, se, m / se))
    la = [float(f[10]) for f in rows] + [float(f[12]) for f in rows]
    ml, sel = clustered(la, lines + lines)
    print('  mean luck per game (side 1, both games of every pair): %+.4f points, SE %.4f, z %+.2f (%d games)' % (
        100 * ml, 100 * sel, ml / sel, len(la)))
    same = sum(r == 0 and float(f[9]) == float(f[11]) for r, f in zip(raw, rows))
    print('  variance ratio of score+ - score- (plain/adjusted): %.2f; pairs with equal plain results %.1f%%' % (
        var(raw) / var(adj), 100 * same / len(rows)))
    half = len(rows) // 2
    print('  gradient estimates (score difference per step, both halves; z of the second half):')
    for i, p in enumerate(P):
        gs = [adj[j] / (2 * float(rows[j][4]) * (1 if rows[j][6][i] == '+' else -1)) for j in range(len(rows))]
        g1, g2 = gs[:half], gs[half:]
        m1, m2 = sum(g1) / len(g1), sum(g2) / len(g2)
        se2 = math.sqrt(var(g2) / len(g2))
        print('    %-14s %+.4f  %+.4f  z %+.2f' % (p['name'], m1, m2, m2 / se2))
    xs = [json.loads(f[17]) for f in rows]
    print('  trajectory (theta, rounded):')
    print('    %7s ' % 'k' + ' '.join('%12s' % p['name'][:12] for p in P))
    print('    %7s ' % 'default' + ' '.join('%12d' % p['default'] for p in P))
    for j in list(range(every - 1, len(rows), every)) + ([len(rows) - 1] if len(rows) % every else []):
        print('    %7d ' % (j + 1) + ' '.join('%12d' % round(xs[j][i] * p['step']) for i, p in enumerate(P)))
    avg = [sum(x[i] for x in xs[half:]) / (len(xs) - half) * P[i]['step'] for i in range(n)]
    print('    %7s ' % 'avg2nd' + ' '.join('%12d' % round(v) for v in avg))
    print('TUNED=' + ','.join(str(min(p['hi'], max(p['lo'], round(v)))) for v, p in zip(avg, P)))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'single':
        single(sys.argv[2])
    elif cmd == 'paired':
        paired(sys.argv[2], sys.argv[3])
    elif cmd == 'h2h':
        h2h(sys.argv[2], sys.argv[3])
    elif cmd == 'spsa':
        spsa(sys.argv[2], int(sys.argv[4]) if len(sys.argv) > 4 else 1000)
