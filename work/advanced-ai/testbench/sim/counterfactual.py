"""Where the advanced AI loses: win rates per matchup and counterfactual replays of its decisions (sim cf, cf.c).

  .venv/bin/python tools/sim/counterfactual.py pairs [--pool all|80|random] [-o FILE]
  .venv/bin/python tools/sim/counterfactual.py rate --pairs FILE [--reps 200] [--seed 1] [--p0 orig] [--p1 adv]
                                                    [--workers 8] [--per-game] [--sim BIN] -o RATES
  .venv/bin/python tools/sim/counterfactual.py dist RATES [RATES2] [--pool all|80] [--balance SELF_RATES]
  .venv/bin/python tools/sim/counterfactual.py analyze (--rates RATES [--below 0.8] [--above 0] | --pairs FILE)
                                                    [--matchups N] [--reps K] [--all-games] [--p0 orig]
                                                    [--rollout-p0 adv] [--workers 8] [--seed 7] [--screen 48]
                                                    [--confirm 200] [--mc N [--margin 0.05] [--general 1|2]] [--sim BIN] -o OUT
  .venv/bin/python tools/sim/counterfactual.py features OUT.jsonl --seed S -o FEAT.jsonl
  .venv/bin/python tools/sim/counterfactual.py report OUT.jsonl [--features FEAT.jsonl] [--mistake 0.10] [--examples 3]
  .venv/bin/python tools/sim/counterfactual.py compare RATES1 RATES2     (rate --per-game files of two builds)
  .venv/bin/python tools/sim/counterfactual.py h2h RATES_A1 RATES_B1    (a dual binary's two side assignments)

pairs writes every ordered pair of distinct six-Pokemon trainer teams (the trainer side first; --pool 80 keeps
aivsai's level-80 pool; --pool random pairs the extra teams of gen_simdata.py --extra-teams instead). rate plays each pair --reps times with the advanced AI on the trainer side (engine side 1)
against --p0 on the player side, split over --workers processes; a game's luck comes from its teams and rep, so the
split and the build do not change it. dist prints the distribution of the per-matchup win rates (two rate files: the
paired difference). analyze draws --matchups matchups whose rate is in [--above, --below) (or from a pairs file), plays
--reps games of each and replays every decision of the lost ones (--all-games: of every game) with each legal action
(sim cf analyze); with --mc N it plays the same games with the rollout policy instead (sim cf mc: one step of policy
improvement, N replays per action), which bounds what better decisions alone can win. report classifies the lost
games and groups the costly decisions into patterns.
"""
import argparse
import collections
import json
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import simbuild  # noqa: E402
import simpool  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.environ.get('ADVAI_SIM') or simbuild.binary()      # the Chinese ROM's build (simbuild.py) unless --sim


def teams(sim):
    out = simpool.run([sim, 'cf', 'teams'], check=True, capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        idx, trainer, pool, n, name, species = line.split('\t')
        rows.append({'idx': int(idx), 'trainer': int(trainer), 'pool': int(pool), 'n': int(n), 'name': name,
                     'species': species.split(',')})
    return rows


def pair_line(scen, a, b):
    return 'pair %s 0 %d 6 0 1 2 3 4 5 %d 6 0 1 2 3 4 5' % (scen, a, b)


POOLS = {'all': (0, 1), '80': (1,), 'random': (2,)}     # sim.h POOL_OTHER, POOL_80, POOL_RANDOM


def cmd_pairs(a):
    tl = [t for t in teams(a.sim) if t['n'] == 6 and t['pool'] in POOLS[a.pool]]
    lines = [pair_line('m%05d' % k, x['idx'], y['idx'])
             for k, (x, y) in enumerate((x, y) for x in tl for y in tl if x is not y)]
    out = open(a.o, 'w') if a.o else sys.stdout
    out.write('\n'.join(lines) + '\n')
    print('%d teams, %d ordered pairs' % (len(tl), len(lines)), file=sys.stderr)


def run_split(sim, args, pair_lines, workers, out_path, chunks=None):
    """sim cf ARGS over the pairs split into contiguous chunks (default one per worker), at most `workers` processes at
    once; the chunks' stdout concatenated in order into out_path."""
    import concurrent.futures
    tmp = tempfile.mkdtemp(prefix='cf_', dir=os.path.dirname(os.path.abspath(out_path)))
    n = max(1, min(len(pair_lines), chunks or workers))
    size = math.ceil(len(pair_lines) / n)
    parts = [pair_lines[i:i + size] for i in range(0, len(pair_lines), size)]

    def one(k):
        pf = os.path.join(tmp, 'p%04d.txt' % k)
        with open(pf, 'w') as f:
            f.write('\n'.join(parts[k]) + '\n')
        with open(os.path.join(tmp, 'o%04d.txt' % k), 'w') as of:
            return simpool.run([sim, 'cf'] + args + ['--pairs', pf], stdout=of).returncode

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        codes = list(ex.map(one, range(len(parts))))
    with open(out_path, 'w') as out:
        for k in range(len(parts)):
            with open(os.path.join(tmp, 'o%04d.txt' % k)) as f:
                out.write(f.read())
    for name in os.listdir(tmp):
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)
    if any(codes):
        raise SystemExit('a sim cf process failed')


def read_pairs(path):
    return [l.rstrip('\n') for l in open(path) if l.startswith('pair ')]


def cmd_rate(a):
    run_split(a.sim, ['rate', '--reps', str(a.reps), '--seed', str(a.seed), '--p0', a.p0, '--p1', a.p1] +
              (['--per-game'] if a.per_game else []), read_pairs(a.pairs), a.workers, a.o, chunks=4 * a.workers)


def read_rates(path):
    """{(team_t, team_p): (wins, draws, losses, turns)}"""
    r = {}
    for line in open(path):
        f = line.split()
        r[(int(f[2]), int(f[3]))] = tuple(int(x) for x in f[4:8])
    return r


def rate_of(v):
    w, d, l, _ = v
    return (w + 0.5 * d) / (w + d + l)


def cmd_dist(a):
    sim_teams = teams(a.sim)
    r = read_rates(a.rates)
    if a.pool == '80':
        r = {k: v for k, v in r.items() if sim_teams[k[0]]['pool'] == 1 and sim_teams[k[1]]['pool'] == 1}
    if a.rates2:
        r2 = read_rates(a.rates2)
        keys = [k for k in r if k in r2]
        d = [rate_of(r[k]) - rate_of(r2[k]) for k in keys]
        g1 = sum(r[k][0] + 0.5 * r[k][1] for k in keys)
        g2 = sum(r2[k][0] + 0.5 * r2[k][1] for k in keys)
        n = sum(sum(r[k][:3]) for k in keys)
        mean = sum(d) / len(d)
        sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (len(d) - 1))
        print('%d matchups, %d games each side: %.4f vs %.4f, difference %+.4f (matchup-clustered SE %.4f)' % (
            len(keys), n, g1 / n, g2 / n, (g1 - g2) / n, sd / math.sqrt(len(d))))
        return
    if a.balance:
        # the teams' balance: the same matchup with the advanced AI on both sides; a matchup the AI loses in self-play
        # with these teams is lost by the teams, not by the decisions
        sb = read_rates(a.balance)
        keys = [k for k in r if k in sb]
        losses = sum(1 - rate_of(r[k]) for k in keys)
        print('%d matchups with a self-play rate; by the trainer team\'s self-play rate (the advanced AI on both sides):'
              % len(keys))
        print('self-play band  matchups  vs the original AI  share of its losses')
        for lo, hi in zip([0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8], [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.01]):
            ks = [k for k in keys if lo <= rate_of(sb[k]) < hi]
            if ks:
                print('[%.2f, %.2f)  %8d  %16.1f%%  %8.1f%%' % (lo, min(hi, 1), len(ks),
                      100 * sum(rate_of(r[k]) for k in ks) / len(ks), 100 * sum(1 - rate_of(r[k]) for k in ks) / losses))
        return
    rates = sorted(rate_of(v) for v in r.values())
    n = len(rates)
    games = sum(sum(v[:3]) for v in r.values())
    wins = sum(v[0] + 0.5 * v[1] for v in r.values())
    reps = games // n
    print('%d matchups, %d games (%d per matchup): the advanced AI wins %.2f%%' % (n, games, reps, 100 * wins / games))
    edges = [0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001]
    print('rate band      matchups  share   losses  share of all losses')
    losses = sum((1 - rate_of(v)) for v in r.values())
    for lo, hi in zip(edges, edges[1:]):
        sel = [x for x in rates if lo <= x < hi]
        lost = sum(1 - x for x in sel)
        print('[%.2f, %.2f)  %8d  %5.1f%%  %7.1f  %5.1f%%' % (lo, min(hi, 1), len(sel), 100 * len(sel) / n, lost * reps,
                                                         100 * lost / losses if losses else 0))
    for t in (0.95, 0.9, 0.8, 0.5):
        sel = [x for x in rates if x < t]
        print('below %.2f: %d matchups (%.1f%%), %.1f%% of all losses; the rest average %.2f%%' % (
            t, len(sel), 100 * len(sel) / n, 100 * sum(1 - x for x in sel) / losses,
            100 * sum(x for x in rates if x >= t) / max(1, n - len(sel))))
    # what the win rate would be if the matchups below a band were raised to it
    for t in (0.8, 0.9, 0.95):
        lifted = sum(max(x, t) for x in rates) / n
        print('every matchup below %.2f raised to %.2f: %.2f%% overall' % (t, t, 100 * lifted))
    # the teams that lose most often, on either side
    by_t = collections.defaultdict(list)
    by_p = collections.defaultdict(list)
    for (tt, tp), v in r.items():
        by_t[tt].append(rate_of(v))
        by_p[tp].append(rate_of(v))
    print('\nthe advanced AI\'s worst teams (its mean rate with the team):')
    for t, xs in sorted(by_t.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[:12]:
        print('  %5.1f%%  %3d %-28s %s' % (100 * sum(xs) / len(xs), t, sim_teams[t]['name'], ','.join(sim_teams[t]['species'])))
    print('the original AI\'s best teams (the advanced AI\'s mean rate against the team):')
    for t, xs in sorted(by_p.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[:12]:
        print('  %5.1f%%  %3d %-28s %s' % (100 * sum(xs) / len(xs), t, sim_teams[t]['name'], ','.join(sim_teams[t]['species'])))


def matchups_of(pairs_path):
    out = []
    for line in read_pairs(pairs_path):
        f = line.split()
        out.append((int(f[3]), int(f[11])))
    return out


def cmd_analyze(a):
    if a.rates:
        r = read_rates(a.rates)
        pool = sorted(k for k, v in r.items() if a.above <= rate_of(v) < a.below)
    else:
        pool = sorted(set(matchups_of(a.pairs)))
    rnd = random.Random(a.seed)
    pick = rnd.sample(pool, min(a.matchups, len(pool)))
    lines = [pair_line('m%05d' % k, tt, tp) for k, (tt, tp) in enumerate(pick)]
    print('%d matchups %s; %d drawn, %d games each' % (
        len(pool), 'with a rate in [%.2f, %.2f)' % (a.above, a.below) if a.rates else 'in the pairs file', len(pick),
        a.reps), file=sys.stderr)
    args = ['analyze', '--reps', str(a.reps), '--seed', str(a.seed), '--p0', a.p0, '--screen', str(a.screen),
            '--confirm', str(a.confirm)]
    if not a.all_games:
        args.append('--lost-only')
    if a.rollout_p0:
        args += ['--rollout-p0', a.rollout_p0]
    if a.mc:
        args = ['mc', '--reps', str(a.reps), '--seed', str(a.seed), '--p0', a.p0, '--n', str(a.mc), '--margin',
                str(a.margin)] + (['--rollout-p0', a.rollout_p0] if a.rollout_p0 else []) + \
            (['--general', str(a.general)] if a.general else [])
    run_split(a.sim, args, lines, a.workers, a.o, chunks=len(lines))


PROTECT = {'Protect', 'Detect', 'KingsShield', 'Spiky Shield', 'BanefulBunkr', 'Obstruct', 'Silk Trap', 'BurnBulwark',
           'Max Guard', 'Endure'}


def cat(opt):
    c = opt['cat']
    if c == 'other':
        name = opt['a'].split(':', 1)[1]
        if name in PROTECT:
            return 'protect'
        if name == 'Substitute':
            return 'substitute'
    return c


def label(d):
    """the decision's pattern: what the AI did, what the replays found better, and the context that matters"""
    o = d['opts']
    c, b = o[d['chosen']], o[d['alt']]
    cc, bc = cat(c), cat(b)
    hp = d['me']['hp']
    ctx = ' (the foe must recharge)' if d.get('fbusy') == 1 else ' (the foe is asleep)' if d['foe']['st'] == 2 else \
        ' (the foe can KO it)' if d['threat'] else \
        ' (the foe can barely hurt it)' if 4 * d.get('fmax', hp) < hp else ''
    if d['kind'] == 'replace':
        return 'replacement: another Pokemon to send in'
    if cc == 'attack' and bc == 'attack':
        if b.get('ko', 0) == 2 and c.get('ko', 0) < 2:
            return 'attack: missed a sure KO'
        if b.get('fx') == 'boost':
            return 'attack: an attack that raises its stats was better' + ctx
        if b.get('fx') == 'pivot':
            return 'attack: U-turn or Volt Switch was better' + ctx
        if c.get('fx') in ('drop', 'recoil', 'recharge') and not b.get('fx'):
            return 'attack: one with a drawback (%s), a plain one was better' % c['fx']
        if b.get('first') and not c.get('first'):
            return 'attack: a priority attack was better' + ctx
        if b.get('acc', 100) > c.get('acc', 100):
            return 'attack: a less accurate attack, a surer one was better'
        if b.get('dmax', 0) > c.get('dmax', 0):
            return 'attack: a weaker attack than one available'
        return 'attack: a stronger attack, a weaker one was better'
    if cc == 'attack' and bc == 'switch':
        return 'stayed in to attack, a switch was better' + ctx
    if cc == 'attack':
        return 'attacked, a %s move was better' % bc + ctx
    if cc == 'switch' and bc == 'switch':
        return 'switched to the wrong Pokemon'
    if cc == 'switch':
        return 'switched out, %s was better' % ('attacking' if bc == 'attack' else 'a %s move' % bc) + ctx
    if bc == 'attack':
        return '%s move instead of attacking' % cc + ctx
    if bc == 'switch':
        return '%s move, a switch was better' % cc + ctx
    return '%s move, a %s move was better' % (cc, bc)


def cmd_features(a):
    """the decision features of an analyze run's games (sim cf features: the same games, no replays), for report
    --features: each switch or send-in option's hit on the foe, the foe's hit on it and which is faster"""
    games = set()
    for line in open(a.file):
        try:
            x = json.loads(line)
        except ValueError:
            continue
        if x['type'] == 'game':
            games.add((x['tt'], x['tp'], x['rep']))
    mts = sorted({(tt, tp) for tt, tp, _ in games})
    reps = 1 + max(r for _, _, r in games)
    tmp = a.o + '.raw'
    run_split(a.sim, ['features', '--reps', str(reps), '--seed', str(a.seed), '--p0', a.p0],
              [pair_line('f%05d' % k, tt, tp) for k, (tt, tp) in enumerate(mts)], a.workers, tmp)
    with open(a.o, 'w') as out:
        for line in open(tmp):
            x = json.loads(line)
            if (x['tt'], x['tp'], x['rep']) in games:
                out.write(line)
    os.remove(tmp)


def switch_why(d, b, c):
    """what sets the better switch or send-in b apart from the chosen action c, from the features"""
    if 'hit' not in b:
        return ''
    if c.get('cat') in ('switch', 'send') and 'took' in c and c['took'][0] >= 100 and c['fast'] <= 0 and b['took'][0] < 100:
        return 'the chosen one falls to the foe before it moves'
    if b['fast'] == 1 and b['hit'][0] >= 100:
        return 'the better one outspeeds and KOs'
    if b['took'][1] <= 33:
        return 'the better one takes a third or less'
    if b['hit'][0] >= 100:
        return 'the better one KOs (slower)'
    if c.get('cat') in ('switch', 'send') and 'took' in c and c['took'][1] > b['took'][1] + 30:
        return 'the better one takes much less'
    return 'other'


def family(name):
    """the pattern's family, for the summary table"""
    if name.startswith('replacement'):
        return 'replacement after a faint or pivot: another Pokemon was better'
    if name.startswith('switched to the wrong'):
        return 'switched, to the wrong Pokemon'
    if name.startswith('switched out'):
        return 'switched out, staying in was better'
    if ', a switch was better' in name:
        return 'stayed in, a switch was better'
    if name.startswith('attacked, a '):
        return 'attacked, a non-damaging move was better'
    if name.startswith('attack: '):
        return 'attacked, another attack was better'
    return 'a non-damaging move, another move was better'


def cmd_report(a):
    decs, games = [], []
    for line in open(a.file):
        try:
            x = json.loads(line)
        except ValueError:          # a run cut short leaves a partial last line
            continue
        (decs if x['type'] == 'dec' else games).append(x)
    done = {(g['m'], g['tt'], g['tp'], g['rep']) for g in games}
    decs = [d for d in decs if (d['m'], d['tt'], d['tp'], d['rep']) in done]
    if a.features:
        feat = {}
        for line in open(a.features):
            x = json.loads(line)
            feat[(x['tt'], x['tp'], x['rep'], x['d'])] = x
        miss = 0
        for d in decs:
            f = feat.get((d['tt'], d['tp'], d['rep'], d['d']))
            if f and [o['a'] for o in f['opts']] == [o['a'] for o in d['opts']]:
                d['opts'] = f['opts']
                d['fbusy'] = f.get('fbusy', 0)
            else:
                miss += 1
        if miss:
            print('warning: %d decisions without matching features' % miss)
    by_game = collections.defaultdict(list)
    for d in decs:
        by_game[(d['m'], d['tt'], d['tp'], d['rep'])].append(d)
    lost = [g for g in games if g['res'] < 1]
    print('%d games analyzed (%d lost, %d draws), %d decisions with a choice, %.1f per game' % (
        len(games), len(lost), sum(g['res'] == 0.5 for g in games), len(decs), len(decs) / max(1, len(games))))

    def cost(d):
        return d['vb'] - d['vc'] if d['vb'] >= 0 and d['vc'] >= 0 else 0.0

    # a lost game's deciding swing: the largest of its decisions' costs (best other action minus the chosen one) and of
    # the drops of the AI's own win probability from one decision to the next (dice and the foe's choices). The game is
    # the matchup's when the AI's chance at its first decision was below --underdog; else the AI's mistake when the
    # largest swing is a decision's cost of --mistake or more; else luck
    cls = collections.Counter()
    sizes = collections.defaultdict(list)
    for g in lost:
        ds = sorted(by_game[(g['m'], g['tt'], g['tp'], g['rep'])], key=lambda d: d['d'])
        vs = [d['vc'] for d in ds if d['vc'] >= 0] + [g['res']]
        drop = max([x - y for x, y in zip(vs, vs[1:])] + [0.0])
        top = max(ds, key=cost) if ds else None
        mis = cost(top) if top is not None else 0.0
        if g['v0'] < a.underdog:
            k = 'matchup'
        elif mis >= a.mistake and mis >= drop:
            g2 = top['vb2'] - top['vc2'] if top['vb2'] >= 0 else None
            k = 'mistake, general' if g2 is not None and g2 >= 0.05 else \
                'mistake, original AI only' if g2 is not None and g2 <= -0.05 else 'mistake, unclear'
        else:
            k = 'luck'
        cls[k] += 1
        sizes[k].append((g['v0'], mis, drop))
    n = max(1, len(lost))
    print('\nlost games by their deciding swing (matchup: first-decision chance below %.2f; mistake: a decision cost '
          '%.2f or more and at least the largest drop; luck: a drop of the AI\'s chance from one decision to the next):'
          % (a.underdog, a.mistake))
    for k in ('matchup', 'mistake, general', 'mistake, unclear', 'mistake, original AI only', 'luck'):
        z = sizes[k]
        if z:
            print('  %-26s %4d  %5.1f%%   mean first-decision chance %.2f, largest cost %.2f, largest drop %.2f' % (
                k, cls[k], 100 * cls[k] / n, sum(x[0] for x in z) / len(z), sum(x[1] for x in z) / len(z),
                sum(x[2] for x in z) / len(z)))
    print('  mean win probability at the first decision of the lost games: %.3f' % (sum(g['v0'] for g in lost) / n))
    withm = sum(1 for g in lost if any(cost(d) >= a.mistake for d in by_game[(g['m'], g['tt'], g['tp'], g['rep'])]))
    wonm = sum(1 for g in games if g['res'] >= 1 and
               any(cost(d) >= a.mistake for d in by_game[(g['m'], g['tt'], g['tp'], g['rep'])]))
    print('  games with a decision that cost %.2f or more: %d of %d lost, %d of %d won' % (
        a.mistake, withm, len(lost), wonm, len(games) - len(lost)))

    th = [0.05, 0.10, 0.20, 0.30]
    print('\ndecisions by the confirmed cost of the AI\'s choice (best other action minus its own):')
    for t in th:
        k = sum(cost(d) >= t for d in decs)
        print('  >= %.2f: %5d (%.2f%% of decisions, %.2f per game)' % (t, k, 100 * k / max(1, len(decs)), k / max(1, len(games))))
    tot = sum(max(0.0, cost(d)) for d in decs if cost(d) >= a.mistake)
    print('  summed cost of the decisions at %.2f or more: %.2f per game (not a gain: the costs overlap, since a better '
          'choice changes the later decisions; analyze --mc measures the gain)' % (a.mistake, tot / max(1, len(games))))

    pats = collections.defaultdict(list)
    for d in decs:
        if cost(d) >= a.mistake:
            pats[label(d)].append(d)
    print('\npatterns among the decisions that cost %.2f or more (cost: mean win probability lost; per game: summed '
          'cost / games; vs adv: the same two actions with the advanced AI as the foe, mean gain; gen/orig/?: the gain '
          'there is +0.05 or more (a general mistake), -0.05 or less (it pays only against the original AI), between)'
          % a.mistake)
    print('%-70s %5s %6s %8s %7s %11s' % ('pattern', 'count', 'cost', 'per game', 'vs adv', 'gen/orig/?'))
    rows = sorted(pats.items(), key=lambda kv: -sum(cost(d) for d in kv[1]))
    allg = []
    for name, ds in rows:
        g2 = [d['vb2'] - d['vc2'] for d in ds if d['vb2'] >= 0]
        allg += g2
        print('%-70s %5d %6.3f %8.4f %7s %11s' % (
            name, len(ds), sum(cost(d) for d in ds) / len(ds), sum(cost(d) for d in ds) / max(1, len(games)),
            '%+.3f' % (sum(g2) / len(g2)) if g2 else '-',
            '%d/%d/%d' % (sum(x >= 0.05 for x in g2), sum(x <= -0.05 for x in g2), sum(-0.05 < x < 0.05 for x in g2))
            if g2 else '-'))
    fams = collections.defaultdict(list)
    for name, ds in rows:
        fams[family(name)] += ds
    print('\nfamilies of patterns (the same columns):')
    for name, ds in sorted(fams.items(), key=lambda kv: -sum(cost(d) for d in kv[1])):
        g2 = [d['vb2'] - d['vc2'] for d in ds if d['vb2'] >= 0]
        print('%-70s %5d %6.3f %8.4f %7s %11s' % (
            name, len(ds), sum(cost(d) for d in ds) / len(ds), sum(cost(d) for d in ds) / max(1, len(games)),
            '%+.3f' % (sum(g2) / len(g2)) if g2 else '-',
            '%d/%d/%d' % (sum(x >= 0.05 for x in g2), sum(x <= -0.05 for x in g2), sum(-0.05 < x < 0.05 for x in g2))
            if g2 else '-'))
    if allg:
        print('all: %d with the generality replays; general %d, original-AI only %d, unclear %d; mean gain vs adv %+.3f' % (
            len(allg), sum(x >= 0.05 for x in allg), sum(x <= -0.05 for x in allg),
            sum(-0.05 < x < 0.05 for x in allg), sum(allg) / len(allg)))
    if a.features:
        print('\nwhat sets the better switch or send-in apart (decisions at %.2f or more whose better action is one):' % a.mistake)
        for name, ds in rows:
            why = collections.Counter(switch_why(d, d['opts'][d['alt']], d['opts'][d['chosen']]) for d in ds
                                      if d['opts'][d['alt']]['cat'] in ('switch', 'send'))
            if why:
                print('  %s: %s' % (name, ', '.join('%s %d' % kv for kv in why.most_common())))
    if a.examples:
        print('\nexamples (largest cost first):')
        for name, ds in rows[:a.top]:
            print('\n' + name)
            for d in sorted(ds, key=cost, reverse=True)[:a.examples]:
                c, b = d['opts'][d['chosen']], d['opts'][d['alt']]
                print('  %s rep %d turn %d: %s %d/%d vs %s %d/%d (alive %d-%d, faster %d, threat %d): %s %.2f -> %s %.2f%s'
                      % (d['m'], d['rep'], d['turn'], d['me']['sp'], d['me']['hp'], d['me']['max'], d['foe']['sp'],
                         d['foe']['hp'], d['foe']['max'], d['alive'][0], d['alive'][1], d['faster'], d['threat'],
                         c['a'], d['vc'], b['a'], d['vb'],
                         '; vs adv %.2f -> %.2f' % (d['vc2'], d['vb2']) if d['vb2'] >= 0 else ''))
                print('    sim cf show --pairs <(echo "pair x 0 %d 6 0 1 2 3 4 5 %d 6 0 1 2 3 4 5") --seed %s --rep %d' % (
                    d['tt'], d['tp'], a.seed if a.seed is not None else 'S', d['rep']))


def read_games(path):
    """{(team_t, team_p, rep): (score of the trainer side 1/0.5/0, final-battle hash)} from a rate --per-game file"""
    g = {}
    for line in open(path):
        f = line.split()
        for rep, x in enumerate(f[8:]):
            g[(int(f[2]), int(f[3]), rep)] = ({'W': 1.0, 'D': 0.5, 'L': 0.0}[x[0]], x[1:])
    return g


def cmd_compare(a):
    """two builds on the same games (rate --per-game, same pairs, reps and seed): the paired difference"""
    g1, g2 = read_games(a.file1), read_games(a.file2)
    keys = [k for k in g1 if k in g2]
    same = sum(g1[k][1] == g2[k][1] for k in keys)
    better = sum(g1[k][0] > g2[k][0] for k in keys)
    worse = sum(g1[k][0] < g2[k][0] for k in keys)
    s1 = sum(g1[k][0] for k in keys)
    s2 = sum(g2[k][0] for k in keys)
    n = len(keys)
    z = (better - worse) / math.sqrt(better + worse) if better + worse else 0.0
    print('%d games: %s %.3f%%, %s %.3f%%; difference %+.3f points' % (
        n, os.path.basename(a.file1), 100 * s1 / n, os.path.basename(a.file2), 100 * s2 / n, 100 * (s1 - s2) / n))
    print('identical games (same final battle) %d (%.2f%%); different result %d: first better %d, second better %d '
          '(sign test z %+.2f)' % (same, 100 * same / n, better + worse, better, worse, z))


def cmd_h2h(a):
    """head to head (a dual binary): file1 = A on the trainer side, B on the player side; file2 = the same games with
    the AIs swapped. A's score per pair of games, and how often the two played alike"""
    g1, g2 = read_games(a.file1), read_games(a.file2)
    keys = [k for k in g1 if k in g2]
    n = len(keys)
    score = sum(g1[k][0] + 1 - g2[k][0] for k in keys)
    same = sum(g1[k][1] == g2[k][1] for k in keys)
    both = sum(g1[k][0] == 1 and g2[k][0] == 0 for k in keys)
    lost = sum(g1[k][0] == 0 and g2[k][0] == 1 for k in keys)
    pairs_score = [g1[k][0] + 1 - g2[k][0] - 1 for k in keys]
    mean = sum(pairs_score) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in pairs_score) / (n - 1))
    print('%d pairs of games (%d games): A scores %.3f%% (SE %.3f, pairs as units)' % (
        n, 2 * n, 100 * score / (2 * n), 100 * sd / math.sqrt(n) / 2))
    print('pairs where both games were identical (the two AIs played alike) %d (%.2f%%); A won both %d, B won both %d' % (
        same, 100 * same / n, both, lost))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sim', default=SIM)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pairs')
    p.add_argument('--pool', choices=('all', '80', 'random'), default='all',
                   help='all: every trainer team; 80: the level-80 pool; random: the extra teams (gen_simdata.py)')
    p.add_argument('-o')
    p = sub.add_parser('rate')
    p.add_argument('--pairs', required=True)
    p.add_argument('--reps', type=int, default=200)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--p0', default='orig')
    p.add_argument('--p1', default='adv')
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--per-game', action='store_true', help='each game\'s result and final-battle hash (compare, h2h)')
    p.add_argument('-o', required=True)
    p = sub.add_parser('dist')
    p.add_argument('rates')
    p.add_argument('rates2', nargs='?')
    p.add_argument('--pool', choices=('all', '80'), default='all')
    p.add_argument('--balance', help='self-play rates of the same matchups (rate --p0 adv)')
    p = sub.add_parser('analyze')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--rates', help='draw from the matchups whose rate is in [--above, --below)')
    g.add_argument('--pairs', help='draw from every matchup of this pairs file')
    p.add_argument('--below', type=float, default=0.8)
    p.add_argument('--above', type=float, default=0.0)
    p.add_argument('--matchups', type=int, default=100)
    p.add_argument('--reps', type=int, default=4)
    p.add_argument('--all-games', action='store_true')
    p.add_argument('--p0', default='orig')
    p.add_argument('--rollout-p0', default='adv', help="side 0's policy in the generality replays ('' for none)")
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--seed', type=int, default=7)
    p.add_argument('--screen', type=int, default=48)
    p.add_argument('--confirm', type=int, default=200)
    p.add_argument('--mc', type=int, default=0, help='play the rollout policy with N replays per action instead (sim cf mc); '
                   'the output is a rate file')
    p.add_argument('--margin', type=float, default=0.05)
    p.add_argument('--general', type=int, default=0, help='with --mc: take an action only if its replays against '
                   '--rollout-p0 are no worse (1) or better (2) than the AI\'s own choice\'s; the replays that pick it '
                   'use --p0')
    p.add_argument('-o', required=True)
    p = sub.add_parser('report')
    p.add_argument('file')
    p.add_argument('--mistake', type=float, default=0.10)
    p.add_argument('--underdog', type=float, default=0.25)
    p.add_argument('--examples', type=int, default=3)
    p.add_argument('--top', type=int, default=8, help='patterns with examples')
    p.add_argument('--seed', type=int, help="the analyze run's --seed, for the example commands")
    p.add_argument('--features', help='the features file of the same run (features)')
    p = sub.add_parser('features')
    p.add_argument('file', help='an analyze output')
    p.add_argument('--seed', type=int, required=True, help="the analyze run's --seed")
    p.add_argument('--p0', default='orig')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('-o', required=True)
    p = sub.add_parser('compare')
    p.add_argument('file1')
    p.add_argument('file2')
    p = sub.add_parser('h2h')
    p.add_argument('file1')
    p.add_argument('file2')
    a = ap.parse_args()
    {'features': cmd_features, 'compare': cmd_compare, 'h2h': cmd_h2h, 'pairs': cmd_pairs, 'rate': cmd_rate, 'dist': cmd_dist, 'analyze': cmd_analyze, 'report': cmd_report}[a.cmd](a)


if __name__ == '__main__':
    main()
