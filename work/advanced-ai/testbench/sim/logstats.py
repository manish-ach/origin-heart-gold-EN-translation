"""Aggregate statistics of the emulator's AI-vs-AI self-play games (aivsai --self), so the PC battle simulator's
games (sim/) can be compared with them on the same footing.

  .venv/bin/python work/advanced-ai/testbench/sim/logstats.py games [--runs GLOB] [-o OUT.jsonl]   # one JSON
        object per game of the self-play runs (default RUNS/aivsai/*_self*, read as sNNN_gK.log or sNNN_gK_rK.log for
        a reseed);
        side 0 = TRAINER, 1 = PLAYER
  .venv/bin/python work/advanced-ai/testbench/sim/logstats.py summary FILE.jsonl [FILE2.jsonl ...]   # turns, decisions, move share,
        switches, KOs, winner split, per file and per team sizes, over the finished games
  .venv/bin/python work/advanced-ai/testbench/sim/logstats.py compare EMU.jsonl SIM.jsonl   # the same statistics side by side, the
        largest standardized differences first, and the turns-per-game histograms

games checks every log against its end line (the loser lost its whole team, left = size - faints, the end line's
turns = the last turn header) and reports on stderr each game that disagrees, each unfinished game (kept with
"finished": false, its turns the last turn header and its left size - faints) and each decision line that is not a
move, a switch or an item. Standard errors treat all the games of one matchup (the same two teams in either order:
a scenario's two games and its replays in other runs) as one cluster, since the self-play runs replay a few
matchups many times.
"""
import argparse
import collections
import glob
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
from aicalc import CUT, HEADER  # noqa: E402

WORK = tbpaths.WORK
ROOT = os.path.join(tbpaths.RUNS, 'aivsai')        # the AI-vs-AI runs (versus/aivsai.py)
SIDES = ('TRAINER', 'PLAYER')
# group 4: aivsai --reseed K (the same teams with other luck), None for reseed 0
SCENARIO = re.compile(r'^scenario (s\d+) game (\d+), seed (\d+)(?:, reseed (\d+))?, TRAINER SIDE (\d+) vs PLAYER SIDE (\d+)$')
TEAM = re.compile(r'^(TRAINER|PLAYER) SIDE team: (.*)$')
TURN = re.compile(r'^--- Turn (\d+) ')
END = re.compile(r'^=== (?:(TRAINER|PLAYER) wins|No winner)(?: after (\d+) turns)?(?: \((.+?)\))?'
                 r'(?:; Pokémon left: TRAINER (\d+), PLAYER (\d+))? =*$')
SIDE_LINE = re.compile(r'^  (TRAINER|PLAYER) +(\S.*?)(?:  \[.*\])?$')     # a trailing [k=v] holds unknown event keys
ACTIONS = (('switches', re.compile(r'^switch to \S')), ('items', re.compile(r'^use \S')),
           ('moves', re.compile(r'^\S.* on \S')))                        # aivsai_live.ACTIONS; the rest is 'other'
EVENTS = (('hp', re.compile(r'\s(?:\d+|\?)/(?:\d+|\?)(?:\s|$)')), ('battle', re.compile(r'\((?:trainer|player) side(?:, (\d+) Pokémon)?\)$')),
          ('faints', re.compile(r'^\S.* fainted$')), ('replacements', re.compile(r'^(?:\S.*? out, )?\S.* in$')))
COUNTS = ('moves', 'switches', 'items', 'other', 'faints', 'replacements')


ADV_HEAD = re.compile(r'^(scenario s\d+ game \d+, seed \d+(?:, reseed \d+)?)(?:, ADVANCED (\d+) vs ORIGINAL (\d+))?$')
ADV_WORDS = re.compile(r'\b(ADVANCED|ORIGINAL)\b')


def log_lines(path):
    """A log's lines in the self-play vocabulary. An adv-vs-orig log (aivsai without --self) names its sides ADVANCED
    (the trainer side) and ORIGINAL (the player side); they become TRAINER and PLAYER, so one reader serves both kinds.
    Logs from before the sizes were printed get them from the team lists."""
    lines = open(path, encoding='utf-8').read().split('\n')
    head = ADV_HEAD.match(lines[0])
    if not head or not any(x.startswith('ADVANCED team:') for x in lines[1:3]):
        return lines
    if head.group(2) is None:
        start = next((i for i, x in enumerate(lines) if x.startswith('=== Battle')), len(lines))
        size, side = [0, 0], None
        for x in lines[1:start]:
            if x.startswith(('ADVANCED team:', 'ORIGINAL team:')):
                side = 0 if x.startswith('ADVANCED') else 1
            elif HEADER.match(x) and side is not None:
                size[side] += 1
        sizes = size
    else:
        sizes = [int(head.group(2)), int(head.group(3))]
    out = ['%s, TRAINER SIDE %d vs PLAYER SIDE %d' % (head.group(1), sizes[0], sizes[1])]
    for x in lines[1:]:
        if x.startswith(('ADVANCED team:', 'ORIGINAL team:')):
            x = ('TRAINER' if x[0] == 'A' else 'PLAYER') + ' SIDE' + x[8:]
        elif x.startswith(('  ADVANCED', '  ORIGINAL', '===')):
            x = ADV_WORDS.sub(lambda m: 'TRAINER' if m.group(1) == 'ADVANCED' else 'PLAYER', x)
        out.append(x)
    return out


def read_log(path):
    """(game or None, problems, unfinished reason or None, unknown decision texts) for one sNNN_gK.log."""
    lines = log_lines(path)
    head = SCENARIO.match(lines[0])
    start = next((i for i, line in enumerate(lines) if line.startswith('=== Battle')), None)
    if not head or start is None:
        return None, ['no scenario line' if not head else 'no battle line'], None, []
    problems, unknown = [], []
    scenario, number, reseed = head.group(1), int(head.group(2)), int(head.group(4) or 0)
    sizes = [int(head.group(5)), int(head.group(6))]
    if os.path.basename(path) != '%s_g%d%s.log' % (scenario, number, '_r%d' % reseed if reseed else ''):
        problems.append('the header says %s game %d%s' % (scenario, number, ' reseed %d' % reseed if reseed else ''))
    teams, side = [None, None], None
    for line in lines[1:start]:
        team, member = TEAM.match(line), HEADER.match(line)
        if team:
            side, name, slots = SIDES.index(team.group(1)), team.group(2).strip(), None
            cut = CUT.match(name)
            if cut:
                name, slots = cut.group(1), [int(x) - 1 for x in cut.group(4).split(',')]
            teams[side] = {'name': name, 'slots': slots, 'mons': []}
        elif member and side is not None:
            sp, lv, ab, it, mv, nat = member.groups()
            teams[side]['mons'].append({'species': sp.strip(), 'level': int(lv), 'ability': None if ab.strip() == 'None' else ab.strip(),
                                        'item': None if it.strip() == '-' else it.strip(),
                                        'moves': [x.strip() for x in mv.split(',')], 'nature': nat})
        elif line.strip():
            problems.append('unread team line %r' % line)
    for k in (0, 1):
        got = len(teams[k]['mons']) if teams[k] else 0
        if got != sizes[k] or (teams[k] and teams[k]['slots'] is not None and len(teams[k]['slots']) != sizes[k]):
            problems.append('%s team: %d members for size %d' % (SIDES[k], got, sizes[k]))

    count = {name: [0, 0] for name in COUNTS}
    turn, first_faint, end = 0, None, None
    for line in lines[start + 1:]:
        if end:
            if line.strip():
                problems.append('text after the end line: %r' % line)
            continue
        if TURN.match(line):
            turn = int(TURN.match(line).group(1))
        elif END.match(line):
            end = END.match(line)
        elif SIDE_LINE.match(line):
            s, text = SIDES.index(SIDE_LINE.match(line).group(1)), SIDE_LINE.match(line).group(2)
            if ' -> ' in text:
                what = text.split(' -> ', 1)[1]
                kind = next((name for name, rx in ACTIONS if rx.search(what)), 'other')
                if kind == 'other':
                    unknown.append(what)
                count[kind][s] += 1
                continue
            kind, m = next(((name, rx.search(text)) for name, rx in EVENTS if rx.search(text)), (None, None))
            if kind in COUNTS:
                count[kind][s] += 1
            if kind == 'faints' and first_faint is None:
                first_faint = turn
            if kind == 'battle' and m.group(1) and int(m.group(1)) != sizes[s]:
                problems.append('%s battle line says %s Pokémon, the header %d' % (SIDES[s], m.group(1), sizes[s]))
            if kind is None:
                problems.append('unread line %r' % line)
        elif line.strip() and not line.startswith(('  >> ', '            ')):
            problems.append('unread line %r' % line)

    faints = count['faints']
    derived = [sizes[k] - faints[k] for k in (0, 1)]
    winner, turns, left, unfinished = None, turn, derived, None
    if end is None:
        unfinished = 'no end line (the log stops in turn %d)' % turn
    else:
        who, said_turns, tag, l0, l1 = end.groups()
        winner = SIDES.index(who) if who else None
        if said_turns:
            turns = int(said_turns)
            if turns != turn:
                problems.append('the end line says %d turns, the last turn header %d' % (turns, turn))
        if l0 is None:
            problems.append('the end line gives no Pokémon left')
        else:
            left = [int(l0), int(l1)]
            for k in (0, 1):
                if left[k] != derived[k]:
                    problems.append('%s: the end line leaves %d, size %d - %d faints = %d' % (SIDES[k], left[k], sizes[k], faints[k], derived[k]))
        if winner is None or tag:
            unfinished = 'end line %r' % end.group(0).rstrip('= ')
            winner = None
        elif faints[1 - winner] != sizes[1 - winner] or left[winner] <= 0:
            problems.append('%s won with %d left; %s lost %d of %d' % (SIDES[winner], left[winner], SIDES[1 - winner],
                                                                     faints[1 - winner], sizes[1 - winner]))
    for k in (0, 1):
        if faints[k] > sizes[k]:
            problems.append('%s: %d faints for %d Pokémon' % (SIDES[k], faints[k], sizes[k]))
    game = {'src': 'emu', 'run': os.path.basename(os.path.dirname(path)), 'scenario': scenario, 'game': number,
            'reseed': reseed, 'seed': int(head.group(3)), 'sizes': sizes, 'teams': teams, 'finished': unfinished is None,
            'winner': winner, 'turns': turns, 'left': left}
    game.update(count)
    game['first_faint_turn'] = first_faint
    return game, problems, unfinished, unknown


def orig_runs():
    """The adv-vs-orig run directories (the original AI on the player side): sizes like _4v6r allowed, never self-play,
    live windows or the held-out runs."""
    root = ROOT
    return sorted(os.path.join(root, d) for d in os.listdir(root) if re.match(r'^\d{8}_\d{6}(_\dv\dr?)?$', d))


def cmd_games(args):
    pattern = args.runs if os.path.isabs(args.runs) else os.path.join(WORK, args.runs)
    runs = orig_runs() if args.orig else sorted(d for d in glob.glob(pattern) if os.path.isdir(d))
    if any('holdout' in d.split(os.sep) for d in runs):
        sys.exit('refused: the glob reaches a holdout directory')
    paths = [p for d in runs for p in sorted(glob.glob(os.path.join(d, 's*_g*.log')))]
    if not paths:
        sys.exit('no sNNN_gK.log under %s' % pattern)
    out = open(args.o, 'w', encoding='utf-8') if args.o else sys.stdout
    bad, unfinished, unknown, finished = [], [], collections.Counter(), 0
    for path in paths:
        game, problems, why, forms = read_log(path)
        where = os.path.join(os.path.basename(os.path.dirname(path)), os.path.basename(path))
        bad += ['%s: %s' % (where, p) for p in problems]
        unknown.update(forms)
        if why:
            unfinished.append('%s: %s' % (where, why))
        if game:
            finished += game['finished']
            out.write(json.dumps(game, ensure_ascii=False) + '\n')
    if args.o:
        out.close()
    report = ['%d games from %d runs: %d finished, %d unfinished' % (len(paths), len(runs), finished, len(unfinished))]
    report += ['unfinished (kept, "finished": false):'] + ['  ' + x for x in unfinished] if unfinished else []
    report += ['decision forms not read as a move, switch or item: %d' % sum(unknown.values())]
    report += ['  %5d  %s' % (n, form) for form, n in unknown.most_common()]
    report += ['consistency problems: %d in %d games' % (len(bad), len({x.split(': ', 1)[0] for x in bad}))]
    report += ['  ' + x for x in bad]
    print('\n'.join(report), file=sys.stderr)


def load(path):
    return [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]


def chosen(g, k):
    return g['moves'][k] + g['switches'][k] + g['items'][k]


METRICS = (     # name, the game's (numerator, denominator), or None to leave the game out; value = sum / sum
    ('turns per game', lambda g: (g['turns'], 1)),
    ('decisions per game', lambda g: (chosen(g, 0) + chosen(g, 1) + sum(g['other']), 1)),
    ('move share, side 0', lambda g: (g['moves'][0], chosen(g, 0))),
    ('move share, side 1', lambda g: (g['moves'][1], chosen(g, 1))),
    ('move share, pooled', lambda g: (sum(g['moves']), chosen(g, 0) + chosen(g, 1))),
    ('switches per game, side 0', lambda g: (g['switches'][0], 1)),
    ('switches per game, side 1', lambda g: (g['switches'][1], 1)),
    ('items per game', lambda g: (sum(g['items']), 1)),
    ('replacements per game', lambda g: (sum(g['replacements']), 1)),
    ('faints per game', lambda g: (sum(g['faints']), 1)),
    ('side 0 win share', lambda g: (g['winner'] == 0, 1)),
    ("winner's Pokémon left", lambda g: None if g['winner'] is None else (g['left'][g['winner']], 1)),
    ('first faint turn', lambda g: None if g['first_faint_turn'] is None else (g['first_faint_turn'], 1)),
)


def matchup(g):
    return tuple(sorted(json.dumps(t, sort_keys=True) for t in g['teams']))


def estimate(games, fn):
    """(value, standard error) of sum(num) / sum(den), the error from the matchups as clusters (ratio estimator)."""
    clusters = collections.defaultdict(lambda: [0, 0])
    for g in games:
        v = fn(g)
        if v is not None:
            c = clusters[matchup(g)]
            c[0] += v[0]
            c[1] += v[1]
    n, num, den = len(clusters), sum(c[0] for c in clusters.values()), sum(c[1] for c in clusters.values())
    if not den:
        return math.nan, math.nan
    r = num / den
    se = math.sqrt(sum((a - r * b) ** 2 for a, b in clusters.values()) / (n * (n - 1))) / (den / n) if n > 1 else math.nan
    return r, se


def spread(games):
    """Counts and the turns distribution: (name, value) rows with no standard error."""
    done = [g for g in games if g['finished']]
    turns = sorted(g['turns'] for g in done)
    cuts = statistics.quantiles(turns, n=10, method='inclusive') if len(turns) > 1 else [math.nan] * 9
    return [('finished games', len(done)), ('unfinished games', len(games) - len(done)),
            ('matchups (team pairs)', len({matchup(g) for g in done})),
            ('turns sd', statistics.stdev(turns) if len(turns) > 1 else math.nan),
            ('turns median', float(statistics.median(turns)) if turns else math.nan), ('turns p10', cuts[0]), ('turns p90', cuts[8])]


def groups(games):
    by = collections.defaultdict(list)
    for g in games:
        by['%dv%d' % tuple(g['sizes'])].append(g)
    keys = sorted(by, key=lambda k: [-int(x) for x in k.split('v')])
    return [(k, by[k]) for k in keys] + ([('all', games)] if len(keys) > 1 else [])


def fmt(name, v):
    if isinstance(v, float) and math.isnan(v):
        return '-'
    if isinstance(v, int):
        return str(v)
    return '%.1f%%' % (100 * v) if 'share' in name else '%.2f' % v


def cmd_summary(args):
    for path in args.files:
        games = load(path)
        cols = groups(games)
        print('%s (%d games)' % (path, len(games)))
        print('  %-28s' % '' + ''.join('%20s' % k for k, _ in cols))
        spreads = [dict(spread(gs)) for _, gs in cols]
        for name in spreads[0]:
            print('  %-28s' % name + ''.join('%20s' % fmt(name, s[name]) for s in spreads))
        for name, fn in METRICS:
            cells = []
            for _, gs in cols:
                v, se = estimate([g for g in gs if g['finished']], fn)
                cells.append('%s ±%s' % (fmt(name, v), fmt(name, se)))
            print('  %-28s' % name + ''.join('%20s' % c for c in cells))
        print()


def cmd_compare(args):
    a_all, b_all = load(args.a), load(args.b)
    la, lb = (os.path.splitext(os.path.basename(p))[0][:12] for p in (args.a, args.b))
    b_groups = dict(groups(b_all))
    for key, a in groups(a_all):
        if key not in b_groups:
            continue
        b = b_groups[key]
        fa, fb = [g for g in a if g['finished']], [g for g in b if g['finished']]
        print('%s: %s %d games, %s %d games (finished); z = (B - A) / SE, * at |z| >= 1.96' % (key, la, len(fa), lb, len(fb)))
        print('  %-28s %12s %12s %10s %8s %7s' % ('', la, lb, 'B - A', 'SE', 'z'))
        rows = []
        for name, fn in METRICS:
            (va, sa), (vb, sb) = estimate(fa, fn), estimate(fb, fn)
            se = math.hypot(sa, sb)
            z = (vb - va) / se if se else math.nan
            rows.append((name, va, vb, vb - va, se, z))
        rows.sort(key=lambda r: -abs(r[5]) if not math.isnan(r[5]) else math.inf)
        for name, va, vb, d, se, z in rows:
            print('  %-28s %12s %12s %10s %8s %7s' % (name, fmt(name, va), fmt(name, vb), fmt(name, d), fmt(name, se),
                                                    '-' if math.isnan(z) else '%+.2f%s' % (z, '*' if abs(z) >= 1.96 else '')))
        for (name, va), (_, vb) in zip(spread(a), spread(b)):
            print('  %-28s %12s %12s %10s' % (name, fmt(name, va), fmt(name, vb), fmt(name, vb - va)))
        print('\n  turns per game, finished games\n  %7s %-50s%s' % ('turns', la, lb))
        top = (int(statistics.quantiles([g['turns'] for g in fa + fb], n=100, method='inclusive')[98]) - 1) // 5
        bucket = lambda t: min((t - 1) // 5, top + 1)       # noqa: E731  the last bucket holds the longest 1%
        ca, cb = collections.Counter(bucket(g['turns']) for g in fa), collections.Counter(bucket(g['turns']) for g in fb)
        for k in range(min(ca | cb), max(ca | cb) + 1):
            pa, pb = 100 * ca[k] / max(len(fa), 1), 100 * cb[k] / max(len(fb), 1)
            label = '%d-%d' % (5 * k + 1, 5 * k + 5) if k <= top else '%d+' % (5 * k + 1)
            print('  %7s %5d %5.1f%% %-36s %5d %5.1f%% %s' % (label, ca[k], pa, '#' * round(pa), cb[k], pb, '#' * round(pb)))
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('games')
    p.add_argument('--runs', default=os.path.join(ROOT, '*_self*'))
    p.add_argument('--orig', action='store_true', help='the adv-vs-orig runs instead (logstats.orig_runs)')
    p.add_argument('-o')
    p = sub.add_parser('summary')
    p.add_argument('files', nargs='+')
    p = sub.add_parser('compare')
    p.add_argument('a')
    p.add_argument('b')
    args = ap.parse_args()
    {'games': cmd_games, 'summary': cmd_summary, 'compare': cmd_compare}[args.cmd](args)


if __name__ == '__main__':
    main()
