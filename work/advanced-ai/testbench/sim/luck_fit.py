"""luck_fit.py FEAT [--w W,...]: fit the luck judge's weights on a sim cf luck --feat dump (rc28 self-play games).

The judge is the leaf's logistic model, V = sigmoid(w . f / 1000 + w0), and the result once the battle is over. A game's
luck is the sum over its turns of V(real state) - mean V(replays). Any fixed w keeps result - luck unbiased; the best w
for testing is the one that leaves the least variance. This fits w that way (Adam on Var(result - luck) per game),
starting from the leaf's weights, on three quarters of the matchups, and reports every judge's variance ratio on the
held-out quarter: the leaf's weights, a plain logistic refit on these states, and the variance fit."""
import math
import sys

import numpy as np

LEAF_W = [0.4522, 0.5591, -0.0190, 0.0900, 0.0413, 0.1144, 0.3543, -0.2901, -0.6517, 0.4390, 0.0192, 0.2717, 0.4849,
          0.5559, -0.0472, 0.5119, -0.1638, 0.2365, -0.1650]


def load(path):
    games, cur, turns = {}, None, []
    for line in open(path):
        f = line.split()
        if f[0] == 'T':
            cur = (int(f[1]), int(f[2]))
            turns.append([cur, []])
        elif f[0] == 'E':
            games[(int(f[1]), int(f[2]))] = float(f[3])
        else:
            turns[-1][1].append([float(v) for v in f])
    keys = sorted(games)
    gi = {k: i for i, k in enumerate(keys)}
    turns = [t for t in turns if t[0] in gi and len(t[1]) > 1]
    k = len(turns[0][1]) - 1
    turns = [t for t in turns if len(t[1]) == k + 1]
    X = np.array([t[1] for t in turns])                     # turns x (1 + K) x (1 + 18)
    g = np.array([gi[t[0]] for t in turns])
    R = np.array([games[key] for key in keys])
    lines = np.array([key[0] for key in keys])
    return X, g, R, lines, k


def values(X, w):
    term = X[:, :, 0]
    F = X[:, :, 1:] / 1000.0
    z = F @ w[:-1] + w[-1]
    s = 1 / (1 + np.exp(-z))
    v = np.where(term >= 0, term, s)
    ds = np.where(term >= 0, 0.0, s * (1 - s))              # dV/dz
    return v, ds, F


def luck(X, g, n, w):
    v, ds, F = values(X, w)
    lt = v[:, 0] - v[:, 1:].mean(axis=1)
    L = np.bincount(g, weights=lt, minlength=n)
    # dL/dw per game
    dz = ds[:, :, None] * np.concatenate([F, np.ones(F.shape[:2] + (1,))], axis=2)
    dlt = dz[:, 0, :] - dz[:, 1:, :].mean(axis=1)
    dL = np.zeros((n, len(w)))
    np.add.at(dL, g, dlt)
    return L, dL


def objective(R, L, dL):
    a = R - L
    m = a.mean()
    var = ((a - m) ** 2).mean()
    grad = (-2 * (a - m)[:, None] * (dL - dL.mean(axis=0))).mean(axis=0)
    return var, grad


def logistic_refit(X, g, R, w0):
    """a plain logistic regression of the final result on the real states' features"""
    real = X[:, 0, :]
    keep = real[:, 0] < 0
    F = np.hstack([real[keep, 1:] / 1000.0, np.ones((keep.sum(), 1))])
    y = R[g[keep]]
    keep2 = y != 0.5
    F, y = F[keep2], y[keep2]
    w = np.array(w0, dtype=float)
    for _ in range(40):
        p = 1 / (1 + np.exp(-F @ w))
        grad = F.T @ (p - y) + 1e-3 * w
        H = (F * (p * (1 - p))[:, None]).T @ F + 1e-3 * np.eye(len(w))
        w -= np.linalg.solve(H, grad)
    return w


def report(name, X, g, R, w):
    L, _ = luck(X, g, len(R), np.array(w))
    vr, va = R.var(), (R - L).var()
    print('  %-26s var plain %.4f adjusted %.4f ratio %.3f; mean luck %+.4f (SE %.4f)' % (
        name, vr, va, vr / va, L.mean(), L.std() / math.sqrt(len(L))))
    return vr / va


def main():
    X, g, R, lines, k = load(sys.argv[1])
    n = len(R)
    ml = sorted(set(lines))
    cut = set(ml[int(len(ml) * 0.75):])
    te_game = np.array([l in cut for l in lines])
    tr_idx = np.where(~te_game)[0]
    te_idx = np.where(te_game)[0]

    def subset(idx):
        m = np.zeros(n, bool)
        m[idx] = True
        sel = m[g]
        remap = -np.ones(n, int)
        remap[idx] = np.arange(len(idx))
        return X[sel], remap[g[sel]], R[idx]

    Xtr, gtr, Rtr = subset(tr_idx)
    Xte, gte, Rte = subset(te_idx)
    print('%d games (%d train, %d held out), %d turns, K %d' % (n, len(tr_idx), len(te_idx), len(X), k))
    w = np.array(LEAF_W)
    wl = logistic_refit(Xtr, gtr, Rtr, LEAF_W)
    # Adam on the training games' variance
    m1 = np.zeros_like(w)
    m2 = np.zeros_like(w)
    best = (None, 1e9)
    for it in range(1, 401):
        L, dL = luck(Xtr, gtr, len(Rtr), w)
        var, grad = objective(Rtr, L, dL)
        if var < best[1]:
            best = (w.copy(), var)
        m1 = 0.9 * m1 + 0.1 * grad
        m2 = 0.999 * m2 + 0.001 * grad ** 2
        w = w - 0.05 * (m1 / (1 - 0.9 ** it)) / (np.sqrt(m2 / (1 - 0.999 ** it)) + 1e-8)
        if it % 100 == 0:
            print('    adam %d: train var %.5f' % (it, var))
    wv = best[0]
    print('train:')
    for name, ww in (('leaf weights', LEAF_W), ('logistic refit', wl), ('variance fit', wv)):
        report(name, Xtr, gtr, Rtr, ww)
    print('held out:')
    for name, ww in (('leaf weights', LEAF_W), ('logistic refit', wl), ('variance fit', wv)):
        report(name, Xte, gte, Rte, ww)
    print('LOGISTIC_W=' + ','.join('%.4f' % v for v in wl))
    print('VARFIT_W=' + ','.join('%.4f' % v for v in wv))


if __name__ == '__main__':
    main()
