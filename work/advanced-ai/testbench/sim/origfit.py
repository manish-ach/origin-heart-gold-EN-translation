"""The model of the original AI (overlay 11) that origbot.c plays: fitted on the emulator's adv-vs-orig logs, where the
original AI plays the player side (engine side 0).

  .venv/bin/python tools/sim/origfit.py fit [--split team|game] [--train 0|1|all]   # the user-side and foe rows' score
        tables from the train fold -> tools/sim/origmodel.h (with origparams.json's parameters), then make
  .venv/bin/python tools/sim/origfit.py eval [--split team|game] [--train 0|1|all]  # per-decision agreement per fold
  .venv/bin/python tools/sim/origfit.py tune [--split team|game] [--train 0] [--rounds 2]   # the foe-row and switch
        parameters by coordinate search on the train fold's log-likelihood -> origparams.json
  .venv/bin/python tools/sim/origfit.py holdout [--split team|game]   # fit, tune and eval on fold 0, report fold 1
  every command takes --model trainer|random (default trainer) and --obs FILE (turnlog.py's observations; default the
  adv-vs-orig runs' file below). --model random writes origmodel_rand.h and origparams_rand.json, the model origbot.c
  plays for a side whose team is one of aivsai's random teams (POOL_RANDOM), with move-free rows by effect code
  (OrigEff) under the per-move ones, so a move the fit never saw gets the rows of the moves that work alike; its
  parameters' override is ORIG_PARAMS_RAND. Fit it on random-team logs only (turnlog.py --runs DIR).

The folds: a game goes to fold crc32(key) % 2, the key being the original side's team (--split team, the default: the
held-out fold's teams never played the original side in training) or the log's path (--split game). The data come
from `sim validate --orig-dump` over turnlog.py --orig's file (made here when missing or with --refresh).
"""
import argparse
import collections
import json
import math
import os
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import simbuild  # noqa: E402
import simpool  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
VAL = os.path.join(tbpaths.RUNS, 'sim', 'val')
OBS = os.path.join(VAL, 'obs_orig.txt')
OBS_ORIG = OBS
DUMP = os.path.join(VAL, 'orig_dump.jsonl')
EVAL = os.path.join(VAL, 'orig_eval.jsonl')
SIM = simbuild.binary()
MODEL = os.path.join(HERE, 'origmodel.h')
PARAMS = os.path.join(HERE, 'origparams.json')
# per model: the header, the parameters, the C names' prefix, the override variable, min rows for a move-only level
MODELS = {'trainer': ('origmodel.h', 'origparams.json', 'orig', 'ORIG_PARAMS', 1),
          'random': ('origmodel_rand.h', 'origparams_rand.json', 'origr', 'ORIG_PARAMS_RAND', 10)}
KIND = 'trainer'
ANY_EFFECT = 0xFFFF
MIN_EFF = 15                # rows for an effect-code level (the any-effect level from 1; 15 held out best)
MIN_MOVE = 0                # --min-move: rows for a move-only level (0: the model's own)

SELF_TARGETS = {1, 6, 7, 12, 8, 10, 13}     # target types with a row on the user (8, 10, 13: on both sides)
NAMES = ('ko', 'ko_prio', 'immune', 'weak_q', 'se4_bonus', 'se4_p', 'status_fails', 'status_neg', 'self_works',
         'self_fails', 'r5', 'r6', 'r7_se_exit', 'r7_imm', 'r7_res', 'r7_high')    # origbot.c orig_param_name
DEFAULTS = dict(ko=4, ko_prio=2, immune=-10, weak_q=0.8, se4_bonus=2, se4_p=0.2, status_fails=-10, status_neg=0.1,
                self_works=0, self_fails=-10, r5=0.5, r6=1, r7_se_exit=0.9, r7_imm=0.5, r7_res=0.33, r7_high=0.7)
GRID = dict(ko=[1, 2, 3, 4, 6, 10], ko_prio=[0, 1, 2, 4, 6], immune=[-1, -3, -5, -10], weak_q=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0],
            se4_bonus=[0, 1, 2, 3], se4_p=[0, 0.2, 0.5, 0.8, 1.0], status_fails=[-1, -3, -5, -10],
            status_neg=[0, 0.1, 0.2, 0.35, 0.5, 0.7], r5=[0, 0.25, 0.5, 1], r6=[0, 0.5, 1],
            r7_se_exit=[0.9, 0.97, 1.0], r7_imm=[0, 0.05, 0.1, 0.25, 0.5], r7_res=[0, 0.02, 0.05, 0.1, 0.2, 0.33],
            r7_high=[0, 0.1, 0.3, 0.5, 0.7])
TUNED = ('ko', 'ko_prio', 'weak_q', 'status_neg', 'se4_bonus', 'se4_p', 'immune', 'status_fails', 'r7_imm', 'r7_res',
         'r7_se_exit', 'r7_high', 'r5', 'r6')


def use(kind, obs):
    """Point the module at one model's files and one observation file (its dump and eval files sit next to it)."""
    global KIND, MODEL, PARAMS, OBS, DUMP, EVAL
    KIND = kind
    MODEL, PARAMS = (os.path.join(HERE, f) for f in MODELS[kind][:2])
    if obs:
        stem = os.path.splitext(os.path.abspath(obs))[0]
        OBS, DUMP, EVAL = os.path.abspath(obs), stem + '_dump.jsonl', stem + '_eval.jsonl'


def ensure_data(refresh=False):
    os.makedirs(VAL, exist_ok=True)
    if OBS == OBS_ORIG and (refresh or not os.path.exists(OBS)):
        subprocess.run([PY, os.path.join(HERE, 'turnlog.py'), '--orig', '-o', OBS], check=True)
    simbuild.build()
    if refresh or not os.path.exists(DUMP) or os.path.getmtime(DUMP) < os.path.getmtime(OBS):
        with open(os.devnull, 'w') as null:
            simpool.run([SIM, 'validate', OBS, '--orig-dump', DUMP], stdout=null, check=True)


def folds(split):
    """Game index (the validator's order) -> fold 0 or 1."""
    out, gi, team = {}, -1, {}
    for line in open(OBS):
        w = line.split()
        if not w:
            continue
        if w[0] == 'game':
            gi += 1
            team[gi] = {'path': w[1], 'key': []}
        elif w[0] == 'team' and w[1] == '0':
            team[gi]['key'] = [w[2]] + w[4:]
        elif w[0] == 'member' and w[1] == '0':
            team[gi]['key'] += ['%s:%s' % (w[2], w[3])]
    for g, t in team.items():
        key = t['path'] if split == 'game' else ' '.join(t['key'])
        out[g] = zlib.crc32(key.encode()) % 2
    return out


def load_params():
    p = dict(DEFAULTS)
    if os.path.exists(PARAMS):
        p.update(json.load(open(PARAMS)))
    return p


def dist(c):
    """A Dist initializer (origbot.c): the 24 commonest values and their counts."""
    vals = c.most_common(24)
    return '{ %d, %d, { %s }, { %s } }' % (len(vals), sum(x for _, x in vals), ', '.join(str(v) for v, _ in vals),
                                         ', '.join(str(x) for _, x in vals))


def fit(split, train, params=None):
    """The rows' score distributions from the train fold's logged factor sums. User-side rows: per move, the move with
    its 'works' flag, and those with the HP quarter and the first turn out. Foe rows (logs from 2026-10-05 on): per
    origbot.c foe_key level, the kind with KO and strongest, and the kind alone. A level is kept from 30 rows, the
    coarsest from 1."""
    ensure_data()
    fd = folds(split)
    levels = collections.defaultdict(collections.Counter)
    foe = collections.defaultdict(collections.Counter)
    effs = collections.defaultdict(collections.Counter)
    n_foe = 0
    for line in open(DUMP):
        d = json.loads(line)
        if d['t'] != 'dec' or (train != 'all' and fd[d['game']] != int(train)):
            continue
        sc = dict((m, v) for m, v in d['scores'])
        fsc = dict((m, v) for m, v in d['foe_scores'])
        hp4 = min(4, d['me']['hp'] * 4 // max(1, d['me']['maxhp']))
        fresh = d['me']['fresh']
        n_foe += bool(fsc)
        for m in d['moves']:
            if not m['move'] or not m['legal']:
                continue
            if m['target'] in SELF_TARGETS and m['move'] in sc:
                v = sc[m['move']]
                levels[(m['move'], m['works'], hp4, fresh)][v] += 1
                levels[(m['move'], m['works'], -1, -1)][v] += 1
                levels[(m['move'], -1, -1, -1)][v] += 1
                effs[(0, m['works'], m['effect'])][v] += 1
                effs[(0, m['works'], ANY_EFFECT)][v] += 1
            # a status move with a row on the user too draws its user-side value in origbot.c, so its foe row is not fitted
            if m['move'] in fsc and not (m['cls'] == 0 and m['target'] in SELF_TARGETS):
                k, v = m['fkey'], fsc[m['move']]
                foe[tuple(k)][v] += 1
                foe[(k[0], k[1], k[2], -1, -1)][v] += 1
                foe[(k[0], -1, -1, -1, -1)][v] += 1
                if m['cls'] == 0:
                    effs[(1, int(m['works'] != 0), m['effect'])][v] += 1
                    effs[(1, int(m['works'] != 0), ANY_EFFECT)][v] += 1
    _, _, pre, _, min_move = MODELS[KIND]
    min_move = MIN_MOVE or min_move
    rows = ['    { %d, %d, %d, %d, %s },' % (key + (dist(levels[key]),)) for key in sorted(levels)
            if sum(levels[key].values()) >= (30 if key[1] >= 0 else min_move)]
    eff_rows = ['    { %d, %d, %d, %s },' % (key + (dist(effs[key]),)) for key in sorted(effs)
                if sum(effs[key].values()) >= (1 if key[2] == ANY_EFFECT else MIN_EFF)] if KIND == 'random' else []
    foe_rows = ['    { { %d, %d, %d, %d, %d }, %s },' % (key + (dist(foe[key]),)) for key in sorted(foe)
                if sum(foe[key].values()) >= (30 if key[1] >= 0 else 1)]
    p = params or load_params()
    with open(MODEL, 'w') as f:
        if KIND == 'trainer':
            f.write('/* generated by tools/sim/origfit.py fit --split %s --train %s; do not edit */\n' % (split, train))
        else:
            f.write('/* generated by tools/sim/origfit.py fit --model random --obs %s --split %s --train %s; do not edit */\n' % (
                os.path.basename(OBS), split, train))
        f.write('static const double %s_param_default[ORIG_NP] = { %s };\n' % (pre, ', '.join(repr(float(p[k])) for k in NAMES)))
        f.write('static const OrigSelf %s_self[] = {\n%s\n};\n' % (pre, '\n'.join(rows)))
        f.write('static const int %s_nself = %d;\n' % (pre, len(rows)))
        f.write('/* the foe rows, from %d decisions with them logged */\n' % n_foe)
        f.write('static const OrigFoe %s_foe[] = {\n%s\n};\n' % (pre, '\n'.join(foe_rows) or '    { { -2, -2, -2, -2, -2 }, { 1, 1, { 0 }, { 1 } } },'))
        f.write('static const int %s_nfoe = %d;\n' % (pre, len(foe_rows)))
        if KIND == 'random':
            f.write('/* the move-free rows: side (0 user, 1 foe), works, effect code (%d any) */\n' % ANY_EFFECT)
            f.write('static const OrigEff %s_eff[] = {\n%s\n};\n' % (pre, '\n'.join(eff_rows) or '    { 0, -2, 0, { 1, 1, { 0 }, { 1 } } },'))
            f.write('static const int %s_neff = %d;\n' % (pre, len(eff_rows)))
    simbuild.build()
    return len(rows), len(foe_rows), n_foe


def run_eval(params=None):
    env = dict(os.environ)
    if params:
        env[MODELS[KIND][3]] = ','.join('%s=%s' % (k, v) for k, v in params.items())
    with open(os.devnull, 'w') as null:
        simpool.run([SIM, 'validate', OBS, '--orig-eval', EVAL], stdout=null, check=True, env=env)
    return [json.loads(x) for x in open(EVAL)]


def score(rows, fd, fold):
    """Per-decision agreement of one fold: top-1 for every decision, for the logged moves and the logged switches,
    the predicted switches' precision, the mean probability of the logged choice and its log-likelihood; top-1 of the
    replacements with a choice."""
    c = collections.Counter()
    ll = 0.0
    for e in rows:
        if fold is not None and fd[e['g']] != fold:
            continue
        if e['kind'] == 'r':
            if e['n'] > 1:
                c['repl'] += 1
                c['repl_ok'] += e['pick'] == e['logged']
            continue
        p, lg = e['p'], e['logged']
        if lg < 0 or lg > 10:
            continue
        top = max(range(11), key=lambda i: p[i])
        c['n'] += 1
        c['ok'] += top == lg
        c['p'] += p[lg]
        ll += math.log(max(p[lg], 1e-3))
        k = 'sw' if lg >= 5 else 'mv'
        c[k] += 1
        c[k + '_ok'] += top == lg
        c[k + '_kind'] += (top >= 5) == (lg >= 5)
        c['pred_sw'] += top >= 5
        c['pred_sw_ok'] += top >= 5 and lg >= 5
    c['ll'] = ll
    return c


def report(c, name):
    f = lambda a, b: 100.0 * c[a] / c[b] if c[b] else 0.0  # noqa: E731
    print('  %-14s decisions %6d  top-1 %5.1f%%  moves %5.1f%% (%d)  switches %5.1f%% (%d; switch-or-not %5.1f%%, '
          'predicted %d, %5.1f%% right)  mean p %.3f  ll/dec %.3f  replacements %5.1f%% (%d)' % (
              name, c['n'], f('ok', 'n'), f('mv_ok', 'mv'), c['mv'], f('sw_ok', 'sw'), c['sw'], f('sw_kind', 'sw'),
              c['pred_sw'], f('pred_sw_ok', 'pred_sw'), c['p'] / max(1, c['n']), c['ll'] / max(1, c['n']),
              f('repl_ok', 'repl'), c['repl']))


def cmd_eval(a):
    ensure_data()
    fd = folds(a.split)
    rows = run_eval()
    print('original-AI model against the logged decisions (split by %s, trained on %s):' % (a.split, a.train))
    for fold in (0, 1):
        tag = 'train' if a.train == 'all' or int(a.train) == fold else 'held out'
        report(score(rows, fd, fold), 'fold %d (%s)' % (fold, tag))
    report(score(rows, fd, None), 'all')


def tune(split, train, rounds):
    ensure_data()
    fd = folds(split)
    p = load_params()
    best = score(run_eval(p), fd, None if train == 'all' else int(train))['ll']
    print('start ll %.1f' % best)
    for r in range(rounds):
        for name in TUNED:
            for v in GRID[name]:
                if v == p[name]:
                    continue
                q = dict(p, **{name: v})
                ll = score(run_eval(q), fd, None if train == 'all' else int(train))['ll']
                if ll > best + 1e-6:
                    best, p = ll, q
            print('round %d %-12s -> %s  ll %.1f' % (r + 1, name, p[name], best))
    json.dump({k: p[k] for k in NAMES}, open(PARAMS, 'w'), indent=1)
    print('wrote', PARAMS)
    return p


def main():
    global MIN_EFF, MIN_MOVE
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('fit', 'eval', 'tune', 'holdout'))
    ap.add_argument('--split', choices=('team', 'game'), default='team')
    ap.add_argument('--train', default='all', help="0, 1 or all")
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--refresh', action='store_true', help='rebuild the observations and the dump')
    ap.add_argument('--model', choices=sorted(MODELS), default='trainer')
    ap.add_argument('--min-eff', type=int, default=MIN_EFF, help='rows for an effect-code level (random model)')
    ap.add_argument('--min-move', type=int, default=0, help='rows for a move-only level (0: 1 trainer, 10 random)')
    ap.add_argument('--obs', help="turnlog.py's observation file (default: the adv-vs-orig runs' file)")
    a = ap.parse_args()
    use(a.model, a.obs)
    MIN_EFF, MIN_MOVE = a.min_eff, a.min_move
    if a.refresh:
        ensure_data(True)
    if a.cmd == 'fit':
        print('%d user-side and %d foe-row table rows (%d decisions with foe rows) -> %s' % (fit(a.split, a.train) + (MODEL,)))
    elif a.cmd == 'eval':
        cmd_eval(a)
    elif a.cmd == 'tune':
        fit(a.split, a.train)
        tune(a.split, a.train, a.rounds)
        fit(a.split, a.train)
    else:
        a.train = '0'
        fit(a.split, '0')
        tune(a.split, '0', a.rounds)
        fit(a.split, '0')
        cmd_eval(a)


if __name__ == '__main__':
    main()
