"""Score a round on held-out teams: the new build plays the round's held-out seeds and each game is compared with
the old build's game on the same teams (the Spanish qa/aivsai/LOOP.md, "Held-out teams only").

  S=work/advanced-ai/testbench/versus/score_round.py
  .venv/bin/python $S --new-round NAME --rom OLD.nds --sizes 6:6 --scenarios mixed=80,random=40
  .venv/bin/python $S --round NAME --rom OLD.nds --payload P --baseline   # play the old build, its score
  .venv/bin/python $S --round NAME --rom NEW.nds --payload P              # play the new build and compare
  .venv/bin/python $S --round NAME --rom NEW.nds --compare                # compare existing reports only
  .venv/bin/python $S --selftest

Ported from the Spanish workspace's qa/aivsai/score_round.py (dc8577c): the paths are the test bench's (RUNS/aivsai/
for reports, RUNS/aivsai/holdout/ for the held-out runs), the ROM is always --rom, the payload goes to aivsai through
ADVAI_PAYLOAD, and the seed bookkeeping is lib/seeds.py.

The round's seeds and the old build's SHA-1 live in RUNS/aivsai/holdout/seeds.json. --new-round draws the seeds and
stores them without printing them. aivsai gets its seed on stdin, so no process listing shows it, and its runs (logs,
report, work files) are moved into RUNS/aivsai/holdout/ as soon as they finish, so they never sit where analysts read.
The printed score is the win rate with its Wilson 95% interval and a scenario bootstrap 95% interval (BOOT_N
resamples of scenarios, seed BOOT_SEED, both fixed before the RC31_6V6 round). A comparison is refused when the two
builds' games did not hold the same teams."""
import logging
logging.getLogger().addHandler(logging.NullHandler())   # this Python's hashlib logs a harmless blake2 traceback on import
import argparse  # noqa: E402
import collections  # noqa: E402
import datetime  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import payload  # noqa: E402
import seeds as aitune  # noqa: E402  (the Spanish tools/aitune.py's seed bookkeeping, now lib/seeds.py)
from aivsai_report import classify_failures, counted, end_of, fallback_counts, wilson  # noqa: E402

RUNS = os.path.join(tbpaths.RUNS, 'aivsai')       # every AI-vs-AI report (the Spanish qa/aivsai/)
HOLD = os.path.join(RUNS, 'holdout')
SEEDS = os.path.join(HOLD, 'seeds.json')
LEDGER = os.path.join(aitune.TUNE_DIR, 'ledger.jsonl')
AIVSAI = os.path.join(tbpaths.TESTBENCH, 'versus', 'aivsai.py')
AIVSAI_OUT = os.path.join(tbpaths.RUNS, 'aivsai')
KINDS = ('mixed', 'random')
BANNED = {34208, 86603, 71831, 51222, 39253, 74981, 75279, 71405}    # earlier rounds' seeds (RC31_PLAN.md section 2)
SEED_RANGE = (10000, 99999)
BOOT_N, BOOT_SEED = 10000, 31
RUNNER = 'import json, runpy, sys; sys.argv = json.load(sys.stdin); runpy.run_path(sys.argv[0], run_name="__main__")'


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


# --- a new round
def used_seeds():
    """Every seed a new round must not take: any integer in the held-out file, the tuning ledger's seeds, the seed in
    the meta of every report under RUNS/aivsai/ (holdout/ included), the banned list and the training rounds' seeds."""
    used = BANNED | set(aitune.ROUND_SEEDS) | aitune.Ledger(LEDGER).seeds()
    if os.path.exists(SEEDS):
        used |= aitune.holdout_seeds(SEEDS)
    for p in glob.glob(os.path.join(RUNS, '**', '*.json'), recursive=True):
        try:
            with open(p) as f:
                meta = json.load(f).get('meta')
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(meta, dict):
            used |= {m.get('seed') for m in [meta] + list(meta.get('sessions') or []) if isinstance(m, dict)}
    return used


def fresh_seeds(k, used, rng):
    out = []
    while len(out) < k:
        s = rng.randint(*SEED_RANGE)
        if s not in used and s not in out:
            out.append(s)
    return out


def new_round(name, sizes, scenarios, old_sha1, rng=None):
    rounds = json.load(open(SEEDS)) if os.path.exists(SEEDS) else {}
    if name in rounds:
        sys.exit('round %s exists; nothing changed' % name)
    seeds = fresh_seeds(len(KINDS), used_seeds(), rng or random.SystemRandom())
    rounds[name] = dict(zip(KINDS, seeds), sizes=sizes, scenarios=scenarios, old_sha1=old_sha1,
                        created=datetime.datetime.now().isoformat(timespec='seconds'))
    os.makedirs(HOLD, exist_ok=True)
    with open(SEEDS + '.tmp', 'w') as f:
        json.dump(rounds, f, indent=1)
    os.replace(SEEDS + '.tmp', SEEDS)
    print('round %s created: sizes %s, %s scenarios, old build %s' % (
        name, sizes, ' + '.join('%s %d' % kv for kv in scenarios.items()), old_sha1[:8]))


# --- playing
def reports(sha, teams, seed):
    """Held-out reports of one build on one seed, newest first."""
    out = []
    for p in glob.glob(os.path.join(HOLD, 'report_*.json')):
        m = json.load(open(p))['meta']
        if m.get('rom_sha1') == sha and m.get('teams') == teams and m.get('seed') == seed:
            out.append(p)
    return sorted(out, reverse=True)


def play(rom, teams, seed, sizes, n, workers):
    argv = [AIVSAI, str(n), '--teams', teams, '--sizes', sizes, '--pick', 'random', '--seed', str(seed), '--rom', rom,
            '--workers', str(workers)]
    p = subprocess.run([sys.executable, '-c', RUNNER], input=json.dumps(argv), cwd=tbpaths.REPO, capture_output=True, text=True)
    run = report = None
    for line in p.stdout.splitlines():
        if line.startswith('battle logs: '):
            run = os.path.join(tbpaths.REPO, line.split(': ', 1)[1].strip())
        if line.startswith('Report: '):
            report = line.split(': ', 1)[1].strip()
    if not run or not report:
        sys.exit('aivsai did not finish:\n' + (p.stdout + p.stderr)[-2000:].replace(str(seed), '<seed>'))
    dest = os.path.join(HOLD, os.path.basename(run))
    shutil.move(run, dest)
    for f in glob.glob(report[:-3] + '*'):
        shutil.move(f, os.path.join(HOLD, os.path.basename(f)))
    tag = 'aivsai_adv_' + os.path.splitext(os.path.basename(rom))[0]
    os.makedirs(os.path.join(dest, 'work'), exist_ok=True)
    for f in glob.glob(os.path.join(AIVSAI_OUT, 'jobs_%s_*.json' % tag)) + glob.glob(os.path.join(AIVSAI_OUT, 'res_%s_*.json' % tag)):
        shutil.move(f, os.path.join(dest, 'work', os.path.basename(f)))    # the jobs hold the games' teams and seeds
    return os.path.join(HOLD, os.path.basename(report)[:-3] + '.json')


# --- scoring
def load(path):
    return {(r['scenario'], r['game']): r for r in json.load(open(path))['results']}


def tally(games):
    """{kind: results} -> the score's numbers; clusters are each scenario's (wins, counted), per kind."""
    c = collections.Counter()
    clusters, splits, margins, turns = {}, collections.Counter(), collections.Counter(), {'won': [], 'lost': []}
    for kind, rs in games.items():
        scn = collections.defaultdict(lambda: [0, 0])
        for (s, _), r in rs.items():
            if counted(r):
                won = r['winner'] == 'advanced'
                c['won' if won else 'lost'] += 1
                scn[s][0] += won
                scn[s][1] += 1
                turns['won' if won else 'lost'].append(r.get('turns') or 0)
                if not won:
                    margins[min(3, (r.get('left') or {}).get('original') or 0)] += 1
            else:
                end = end_of(r)
                c[{'normal': 'no winner'}.get(end, end)] += 1
                scn[s]      # a scenario with no counted game still counts as one when resampled
        clusters[kind] = [tuple(v) for _, v in sorted(scn.items())]
        splits.update('%d-%d' % (w, n - w) for w, n in clusters[kind] if n == 2)
    return {'won': c['won'], 'lost': c['lost'], 'void': {k: v for k, v in c.items() if k not in ('won', 'lost')},
            'clusters': clusters, 'splits': splits, 'margins': margins, 'turns': turns}


def boot(clusters, n=BOOT_N, seed=BOOT_SEED):
    """Scenario bootstrap 95% interval of the win rate: each resample draws as many scenarios of each kind as the
    round has, with replacement (the kinds keep their counts, as the round's design fixes them)."""
    rng = random.Random(seed)
    rates = []
    for _ in range(n):
        w = c = 0
        for scn in clusters.values():
            for sw, sc in rng.choices(scn, k=len(scn)):
                w += sw
                c += sc
        rates.append(w / c if c else 0.0)
    rates.sort()
    return rates[int(0.025 * n)], rates[int(0.975 * n) - 1]


def score_line(label, t):
    n = t['won'] + t['lost']
    void = ', '.join('%d %s' % (v, k) for k, v in sorted(t['void'].items())) or '0'
    if not n:
        return '  %-7s no counted game (not counted: %s)' % (label, void)
    lo, hi = wilson(t['won'], n)
    blo, bhi = boot(t['clusters'])
    return '  %-7s %3d won, %2d lost, not counted %s: %.2f%% (Wilson %.1f-%.1f, scenario bootstrap %.1f-%.1f)' % (
        label, t['won'], t['lost'], void, 100 * t['won'] / n, 100 * lo, 100 * hi, 100 * blo, 100 * bhi)


def median(xs):
    return '%.0f' % statistics.median(xs) if xs else '-'


def loss_line(label, t):
    return '  %-7s scenarios %s; losses by the original AI\'s Pokemon left 1: %d, 2: %d, 3+: %d; median turns won %s, ' \
        'lost %s' % (label, ', '.join('%s %d' % (k, t['splits'][k]) for k in ('2-0', '1-1', '0-2')),
                     t['margins'][1], t['margins'][2], t['margins'][3], median(t['turns']['won']), median(t['turns']['lost']))


def check_line(rs):
    wrong = sum(sum(s.get('wrong', 0) for s in (r.get('decisions') or {}).values()) for r in rs)
    # a failure's text on screen can name the teams' Pokemon and moves: only its event and address are printed
    review = [(i, x.split(' during ')[0]) for i, r in enumerate(rs) for x in classify_failures(r)[1]]
    top = ', '.join('%s x%d' % kc for kc in collections.Counter(x for _, x in review).most_common(5))
    return '  checks  wrong-AI decisions %d, advanced fallbacks %s, advanced polls max %d, median frames %s\n' \
        '  checks  failures needing review %d in %d games%s' % (
            wrong, fallback_counts(rs, 'advanced') or '{}', max([r.get('adv_polls_max') or 0 for r in rs] or [0]),
            median([r.get('frames') or 0 for r in rs]), len(review), len({i for i, _ in review}), ' (%s)' % top if top else '')


def score(games, header):
    """Print a build's score per kind and pooled, then the losses and the run's checks."""
    print(header)
    rows = [(kind, tally({kind: games[kind]})) for kind in games] + [('pooled', tally(games))]
    for label, t in rows:
        print(score_line(label, t))
    for label, t in rows:
        print(loss_line(label, t))
    print(check_line([r for kind in games.values() for r in kind.values()]))


# --- comparing
def team_blocks(results):
    """Per game, the teams at the head of its battle log (None when the log is missing)."""
    out = {}
    for key, r in results.items():
        log = os.path.join(HOLD, *r['log'].split('/')[-2:]) if r.get('log') else None
        if log and os.path.isfile(log):
            lines = open(log, encoding='utf-8').read().split('\n')
            end = next((i for i in range(1, len(lines)) if not lines[i]), len(lines))
            out[key] = '\n'.join(lines[1:end])
        else:
            out[key] = None
    return out


def same_teams(old, new):
    """The games both builds played on teams proven equal (the logs' team lines and the engine's party sizes); exits
    when any game differs, since a different team pool makes the comparison meaningless."""
    if set(old) != set(new):
        sys.exit('refused: the two runs hold different games (%d and %d)' % (len(old), len(new)))
    ob, nb = team_blocks(old), team_blocks(new)
    bad = [k for k in old if ob[k] is not None and nb[k] is not None and
           (ob[k] != nb[k] or None not in (old[k].get('parties'), new[k].get('parties')) and old[k]['parties'] != new[k]['parties'])]
    if bad:
        sys.exit('refused: %d of %d games held different teams in the two runs (the team pool changed?)' % (len(bad), len(old)))
    return [k for k in old if ob[k] is not None and nb[k] is not None]


def sign_p(gains, losses):
    """Two-sided sign test on the games that changed result."""
    n, k = gains + losses, min(gains, losses)
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def changed(old, new, keys):
    keys = [k for k in keys if counted(old[k]) and counted(new[k])]
    won = lambda r: r['winner'] == 'advanced'  # noqa: E731
    return (len(keys), sum(1 for k in keys if not won(old[k]) and won(new[k])),
            sum(1 for k in keys if won(old[k]) and not won(new[k])))


def main():
    ap = argparse.ArgumentParser()
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument('--round')
    which.add_argument('--new-round', metavar='NAME')
    which.add_argument('--selftest', action='store_true')
    ap.add_argument('--rom', help='the build to play (--new-round: the old build)')
    ap.add_argument('--payload', help='the AI build\'s payload.json for aivsai (default: ADVAI_PAYLOAD)')
    ap.add_argument('--compare', action='store_true', help='do not play; compare the newest existing reports')
    ap.add_argument('--baseline', action='store_true', help='play the OLD build (old_sha1, given as --rom) on the round\'s seeds')
    ap.add_argument('--sizes', default='4:6', help='--new-round: team sizes N:M')
    ap.add_argument('--scenarios', default='mixed=40,random=40', help='--new-round: scenarios per kind')
    ap.add_argument('--workers', type=int, default=int(os.environ.get('ADVAI_EMU_SLOTS') or 9))
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.new_round:
        scenarios = {k: int(v) for k, _, v in (x.partition('=') for x in a.scenarios.split(','))}
        if set(scenarios) != set(KINDS):
            ap.error('--scenarios needs mixed=N,random=M')
        if not a.rom:
            ap.error('--new-round needs --rom (the old build)')
        return new_round(a.new_round, a.sizes, scenarios, sha1(a.rom))
    if not a.rom:
        ap.error('--round needs --rom')
    if not a.compare:
        payload.path_from(a.payload)        # exported for aivsai
    cfg = json.load(open(SEEDS))[a.round]
    sha = sha1(a.rom)
    count = cfg.get('scenarios', {})
    if a.baseline and sha != cfg['old_sha1']:
        sys.exit('--baseline needs the old build %s, got %s' % (cfg['old_sha1'][:8], sha[:8]))
    builds = [sha] if a.baseline else [cfg['old_sha1'], sha]
    found = {}
    for b in builds:                # the old build's reports first, so nothing is played when one is missing
        for teams in KINDS:
            got = reports(b, teams, cfg[teams])
            if not got and b == sha and not a.compare:
                got = [play(a.rom, teams, cfg[teams], cfg['sizes'], count.get(teams, 40), a.workers)]
            if not got:
                sys.exit('no held-out report of %s for %s' % (b[:8], teams))
            found[b, teams] = got[0]
    games = {b: {t: load(found[b, t]) for t in KINDS} for b in builds}
    keys = {t: same_teams(games[builds[0]][t], games[sha][t]) for t in KINDS} if not a.baseline else None
    sizes = cfg['sizes'].replace(':', ' vs ')
    print('Round %s held-out score, advanced %s original (scenario bootstrap: %d resamples, seed %d)' % (
        a.round, sizes, BOOT_N, BOOT_SEED))
    for b in builds:
        secs = sum(json.load(open(found[b, t]))['meta'].get('seconds') or 0 for t in KINDS)
        score(games[b], '%s build %s (%s; %.0f s of play)' % ('old' if b == cfg['old_sha1'] else 'new', b[:8],
              ', '.join(os.path.basename(found[b, t]) for t in KINDS), secs))
    if keys is None:
        return
    g = l = 0
    for t in KINDS:
        n, gains, losses = changed(games[builds[0]][t], games[sha][t], keys[t])
        g, l = g + gains, l + losses
        print('  %-7s changed games of %d counted in both: +%d -%d (sign test p = %.3f)%s' % (
            t, n, gains, losses, sign_p(gains, losses),
            '; %d without a log left out' % (len(games[sha][t]) - len(keys[t])) if len(keys[t]) < len(games[sha][t]) else ''))
    print('  pooled  changed games: +%d -%d (sign test p = %.3f)' % (g, l, sign_p(g, l)))


# --- self-test: fake rounds and reports in a temporary folder
def _result(scn, game, winner, log, parties=None, end='normal'):
    return {'scenario': scn, 'game': game, 'winner': winner, 'end': end, 'turns': 30, 'frames': 20000,
            'left': {'advanced': 2 if winner == 'advanced' else 0, 'original': 2 if winner == 'original' else 0},
            'parties': parties or {'advanced': 6, 'original': 6}, 'log': log,
            'decisions': {'advanced': {'right': 9, 'wrong': 0}, 'original': {'right': 9, 'wrong': 0}},
            'fallbacks': {'advanced': {'0': 9}, 'original': {}}, 'adv_polls_max': 3, 'failures': []}


def _fake_run(stamp, sha, teams, seed, winners, team_text=lambda scn, g: 'A team: X %s %d' % (scn, g)):
    run = os.path.join(HOLD, stamp)
    os.makedirs(run, exist_ok=True)
    results = []
    for i, w in enumerate(winners):
        scn, g = 's%03d' % (i // 2 + 1), i % 2
        log = 'qa/aivsai/runs/%s/%s_g%d.log' % (stamp, scn, g)
        with open(os.path.join(run, '%s_g%d.log' % (scn, g)), 'w') as f:
            f.write('scenario %s game %d, seed 1\n%s\n  member line\n\n=== Battle\n' % (scn, g, team_text(scn, g)))
        results.append(_result(scn, g, w, log))
    meta = {'rom_sha1': sha, 'teams': teams, 'seed': seed, 'seconds': 100.0}
    with open(os.path.join(HOLD, 'report_%s.json' % stamp), 'w') as f:
        json.dump({'meta': meta, 'results': results}, f)


def selftest():
    import contextlib
    import io
    global HOLD, SEEDS, LEDGER, RUNS
    saved = HOLD, SEEDS, LEDGER, RUNS
    fails = []

    def check(ok, what):
        print('%s %s' % ('ok  ' if ok else 'FAIL', what))
        if not ok:
            fails.append(what)
    with tempfile.TemporaryDirectory() as tmp:
        RUNS, HOLD = tmp, os.path.join(tmp, 'holdout')
        SEEDS, LEDGER = os.path.join(HOLD, 'seeds.json'), os.path.join(tmp, 'tune', 'ledger.jsonl')
        os.makedirs(HOLD)
        try:
            # a new round: refused seeds are skipped, the seeds are stored and never printed, a rerun changes nothing
            json.dump({'OLD': {'mixed': 11111, 'random': 22222}}, open(SEEDS, 'w'))
            os.makedirs(os.path.dirname(LEDGER))
            open(LEDGER, 'w').write(json.dumps({'kind': 'block', 'seed': 33333}) + '\n')
            json.dump({'meta': {'seed': 44444}}, open(os.path.join(tmp, 'report_x.json'), 'w'))
            json.dump({'meta': {'seed': None, 'sessions': [{'seed': 55555}]}}, open(os.path.join(HOLD, 'report_y.json'), 'w'))

            class Fixed:
                def __init__(self, xs):
                    self.xs = list(xs)

                def randint(self, lo, hi):
                    return self.xs.pop(0)
            used = used_seeds()
            check({11111, 22222, 33333, 44444, 55555, 34208} <= used, 'used seeds: held-out file, ledger, report metas, banned list')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                new_round('R', '6:6', {'mixed': 2, 'random': 1}, 'ab' * 20,
                          Fixed([11111, 33333, 44444, 55555, 34208, 101, 60001, 60001, 70002]))
            stored = json.load(open(SEEDS))['R']
            check((stored['mixed'], stored['random']) == (60001, 70002), 'new round skips refused and repeated seeds')
            check('60001' not in out.getvalue() and '70002' not in out.getvalue() and 'round R created' in out.getvalue(),
                  'new round prints the round, never its seeds')
            before = open(SEEDS).read()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    new_round('R', '6:6', {'mixed': 2, 'random': 1}, 'cd' * 20, Fixed([80001, 80002]))
                check(False, 'an existing round is refused')
            except SystemExit:
                check(open(SEEDS).read() == before, 'an existing round is refused and the file is unchanged')

            # the score: Wilson bounds as aivsai_report's (and the plan's table: 228 of 240 is 91.5-97.1), a
            # reproducible bootstrap
            check(tuple(round(100 * x, 1) for x in wilson(228, 240)) == (91.5, 97.1), 'Wilson 228 of 240 = 91.5-97.1')
            _fake_run('20260101_000000', 'old', 'mixed', 60001, ['advanced'] * 7 + ['original'] + ['advanced', 'original'])
            _fake_run('20260101_010000', 'new', 'mixed', 60001, ['advanced'] * 8 + ['advanced', 'advanced'])
            old = load(reports('old', 'mixed', 60001)[0])
            t = tally({'mixed': old})
            line = score_line('mixed', t)
            lo, hi = wilson(8, 10)
            check('Wilson %.1f-%.1f' % (100 * lo, 100 * hi) in line and '8 won,  2 lost' in line, 'score line: %s' % line.strip())
            check(t['splits'] == {'2-0': 3, '1-1': 2}, 'scenario splits 2-0 3, 1-1 2')
            b1 = boot(t['clusters'])
            check(b1 == boot(t['clusters']) and b1[0] <= 0.8 <= b1[1], 'bootstrap reproducible: %.3f-%.3f' % b1)
            # 40 scenarios won 2-0 or lost 0-2: the games of a scenario agree, so resampling scenarios must give a
            # wider interval than Wilson's on 80 independent games (resampling games would not)
            lo, hi = boot({'mixed': [(2, 2)] * 20 + [(0, 2)] * 20})
            wlo, whi = wilson(40, 80)
            check(hi - lo > 1.3 * (whi - wlo), 'bootstrap resamples scenarios: %.3f-%.3f against Wilson %.3f-%.3f' % (lo, hi, wlo, whi))

            # the comparison: same teams accepted, a changed team refused, a missing log left out
            new = load(reports('new', 'mixed', 60001)[0])
            keys = same_teams(old, new)
            check(len(keys) == 10 and changed(old, new, keys) == (10, 2, 0), 'same teams: 10 games compared, +2 -0')
            os.remove(os.path.join(HOLD, '20260101_010000', 's005_g1.log'))
            check(len(same_teams(old, new)) == 9, 'a game without a log is left out of the comparison')
            _fake_run('20260101_020000', 'other', 'mixed', 60001, ['advanced'] * 10,
                      team_text=lambda scn, g: 'A team: X %s %d' % (scn, g) + (' changed' if scn == 's003' else ''))
            try:
                same_teams(old, load(reports('other', 'mixed', 60001)[0]))
                check(False, 'different teams are refused')
            except SystemExit as e:
                check('2 of 10 games' in str(e), 'different teams are refused: %s' % e)
            sizes = dict(new)
            sizes['s002', 0] = dict(sizes['s002', 0], parties={'advanced': 5, 'original': 6})
            try:
                same_teams(old, sizes)
                check(False, 'different party sizes are refused')
            except SystemExit:
                check(True, 'different party sizes are refused')
        finally:
            HOLD, SEEDS, LEDGER, RUNS = saved
    print('selftest: %s' % ('%d failed' % len(fails) if fails else 'all passed'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
