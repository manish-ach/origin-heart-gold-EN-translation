"""End-of-run report of the AI vs AI bench (the Spanish qa/aivsai_plan.md, "Report mode").

  .venv/bin/python work/advanced-ai/testbench/versus/aivsai_report.py RESULTS.json [...] [--out REPORT.md]
                                                    # rewrite a report from saved results; several runs are combined
  .venv/bin/python work/advanced-ai/testbench/versus/aivsai_report.py --selftest

Ported from the Spanish workspace's tools/aivsai_report.py (dc8577c). Changes: the failure classification and move
names come from lib/failures.py and lib/names.json (the Spanish tool read tools/aifuzz.py and its text banks), the
fallback codes from src/advai.c, the rerun commands name versus/aivsai.py, and the selftest's move messages are
English; the numbers and the report text are unchanged.

summarize(results, meta) turns the runner's battle results (one dict per game, the plan's "Battle result")
and its run metadata into the report's numbers. write_report(results, meta, md_path, json_path) writes the
Markdown report (and, with json_path, the metadata, the numbers and the raw results) and returns a short
terminal summary. A game counts only when it ended normally with a winner; a game with a decision from the
wrong AI is void. Failures are sorted with tools/aifuzz.py's classification: inherited (the Chinese ROM has
them too) or needs review. A control run (the original AI on both sides) and a self-play run (the advanced AI on
both, mode 'self') name the sides by side and test for a side bias. Team sizes (--adv-size, --orig-size, --pick) come from the metadata; a run from
before those options counts as 6 against 6. Runs with different sizes are never combined.
"""
import argparse
import collections
import datetime
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import failures as aifuzz  # noqa: E402  (the Spanish tools/aifuzz.py's classification, now lib/failures.py)

SIDES = ('advanced', 'original')
SIDE_RUNS = ('control', 'self')       # the same AI on both sides: the sides are named by side
ENDS = ('normal', 'unfinished', 'frozen', 'no battle', 'wrong ai')
Z95 = 1.959963984540054
ALPHA = 0.05
FULL_TEAM = 6
SAMPLE_MD = os.path.join(tbpaths.RUNS, 'aivsai', 'selftest', 'aivsai_selftest.md')     # --selftest's sample reports
SAMPLE_CONTROL_MD = os.path.join(tbpaths.RUNS, 'aivsai', 'selftest', 'aivsai_selftest_control.md')
FALLBACK_TEXT = {'FB_NONE': 'none: the advanced AI decided',
                 'FB_MAIN': 'battle data not readable',
                 'FB_ME': 'the deciding Pokémon not readable or fainted',
                 'FB_NOT_SINGLES': 'more than two Pokémon out on a side',
                 'FB_OPP': 'no opponent found',
                 'FB_POLLS': 'too many polls',
                 'FB_NO_OPTION': 'no action it accepts',
                 'FB_SNAPSHOT': 'battle state check failed'}


def advai_constants():
    """Fallback code meanings (the FB_ enum's order) and the poll limit, from src/advai.c."""
    try:
        src = open(os.path.join(tbpaths.ADV, 'src', 'advai.c'), encoding='utf-8').read()
    except OSError:
        return {}, None
    enum = re.search(r'enum\s*\{\s*(FB_NONE[^}]*)\}', src)
    names = [n.strip() for n in enum.group(1).split(',')] if enum else []
    limit = re.search(r'#define\s+POLL_LIMIT\s+(\d+)', src)
    return {str(i): FALLBACK_TEXT.get(n, n) for i, n in enumerate(names)}, int(limit.group(1)) if limit else None


def wilson(k, n, z=Z95):
    """Wilson score interval of k successes in n trials; None when n is 0."""
    if n == 0:
        return None
    p, z2 = k / n, z * z
    d = 1 + z2 / n
    c = (p + z2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def sign_test(k, n):
    """Two-sided exact sign test: the chance of a k-of-n split at least this uneven when each side has 1/2."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def unit(r):
    """What the report counts as one scenario: the scenario, and its reseed index when it has one (aivsai --reseed:
    the same teams with other luck, 's012/r3')."""
    k = r.get('reseed')
    return '%s/r%d' % (r.get('scenario'), k) if k else str(r.get('scenario'))


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(s))]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def team_sizes(meta):
    """{'advanced': N, 'original': M, 'pick': 'first' or 'random'}: the run's team sizes by side. A run from before
    the size options played 6 against 6; the pick only matters when a team was cut."""
    a, o = meta.get('adv_size') or FULL_TEAM, meta.get('orig_size') or FULL_TEAM
    return {'advanced': a, 'original': o, 'pick': meta.get('pick') or 'first' if min(a, o) < FULL_TEAM else 'first'}


def is_cut(sizes):
    return min(sizes['advanced'], sizes['original']) < FULL_TEAM


def sizes_text(sizes, side_run=False):
    """'ADVANCED 4 vs ORIGINAL 6' ('TRAINER SIDE 4 vs PLAYER SIDE 6' in a control or self-play run)."""
    a, o = ('TRAINER SIDE', 'PLAYER SIDE') if side_run else ('ADVANCED', 'ORIGINAL')
    return '%s %d vs %s %d' % (a, sizes['advanced'], o, sizes['original'])


def pick_text(sizes):
    return {'first': 'each team keeps its first members', 'random': 'each team keeps a subset drawn from the scenario '
            'seed, the same in both games'}.get(sizes['pick'], str(sizes['pick']))


def labels(meta):
    if meta.get('mode') in SIDE_RUNS:
        return {'advanced': 'trainer side', 'original': 'player side'}
    return {'advanced': 'advanced AI', 'original': 'original AI'}


def wrong_decisions(r):
    d = r.get('decisions') or {}
    return sum((d.get(s) or {}).get('wrong', 0) for s in SIDES)


def end_of(r):
    """The game's end as the report counts it: any decision from the wrong AI voids the game."""
    return 'wrong ai' if wrong_decisions(r) else r.get('end')


def counted(r):
    return end_of(r) == 'normal' and r.get('winner') in SIDES


def fuzz_ev(ev):
    """aifuzz's event format: the kind, a space, then the address or heap ('freeze ' keeps its space)."""
    kind, _, arg = (' '.join(str(ev or '').split()) or 'unknown').partition(' ')
    return kind + ' ' + arg


def classify_failures(r):
    """(inherited, needs review) failure descriptions of one game, by aifuzz.classify. aifuzz drops the
    inherited end-of-battle assert unless there are too many; here it is listed as inherited."""
    details = [dict(f, ev=fuzz_ev(f.get('ev'))) for f in r.get('failures') or []]
    frozen = r.get('end') == 'frozen' and not any(f['ev'].startswith('freeze') for f in details)
    c = aifuzz.classify({'fail_detail': details, 'failures': [], 'injected': True, 'frozen': frozen, 'ended': 0,
                         'actions': [], 'decisions': []}, False)
    end = [f for f in details if f['ev'].split()[0] == 'assert' and f['ev'].split()[-1] in aifuzz.INHERITED]
    if not any('end-of-battle asserts' in x for x in c['review']):
        c['inherited'] += ['%s (end of battle)' % f['ev'].strip() for f in end]
    return c['inherited'], c['review']


def game_cell(r):
    if r is None:
        return None
    return {'end': end_of(r), 'winner': r.get('winner'), 'turns': r.get('turns'),
            'left': (r.get('left') or {}).get(r.get('winner')) if r.get('winner') in SIDES else None}


def fallback_counts(rs, sd):
    """The advanced AI's fallback codes on a side, summed over the games. A result from before the per-side counts
    has the trainer side's only (adv_fallbacks)."""
    out = collections.Counter()
    for r in rs:
        codes = (r.get('fallbacks') or {}).get(sd) if isinstance(r.get('fallbacks'), dict) else \
            r.get('adv_fallbacks') if sd == 'advanced' else None
        for code, c in (codes or {}).items():
            out[str(code)] += c
    return dict(sorted(out.items(), key=lambda t: natural(t[0])))


def fallback_share(fallbacks):
    total = sum(fallbacks.values())
    return sum(c for code, c in fallbacks.items() if code != '0') / total if total else None


def summarize(results, meta):
    """The report's numbers from the runner's battle results and run metadata (JSON-ready)."""
    mode = meta.get('mode') or 'adv-vs-orig'
    lab, control = labels(meta), mode in SIDE_RUNS        # control: the sides are named by side (control or self)
    warnings = []
    games = {}
    for r in results:
        key = (unit(r), r.get('game'))
        if key in games:
            warnings.append('%s game %s has two results; the last one is used.' % key)
        games[key] = r
    rs = sorted(games.values(), key=lambda r: (natural(unit(r)), r.get('game') or 0))
    sizes = team_sizes(meta)
    for r in rs:
        where = '%s game %s' % (unit(r), r.get('game'))
        played = r.get('sizes')
        if played and {sd: played.get(sd) for sd in SIDES} != {sd: sizes[sd] for sd in SIDES}:
            warnings.append('%s was played %s, but the run says %s.' % (where, sizes_text(played, control),
                                                                      sizes_text(sizes, control)))
        engine = r.get('parties')
        if engine and played and engine != {sd: played.get(sd) for sd in SIDES}:
            warnings.append('%s: the battle engine held parties of %s, not the %s built.' % (
                where, sizes_text(engine, control), sizes_text(played, control)))
        for sd in SIDES:
            if (r.get('left') or {}).get(sd, 0) > (played or sizes)[sd]:
                warnings.append('%s: the %s has %s Pokémon left of %d.' % (where, lab[sd], r['left'][sd], (played or sizes)[sd]))
        if r.get('end') not in ENDS:
            warnings.append('%s has an unknown end %r.' % (where, r.get('end')))
        if r.get('end') != 'wrong ai' and wrong_decisions(r):
            warnings.append('%s is marked %r but %d decisions came from the wrong AI. It is void.'
                            % (where, r.get('end'), wrong_decisions(r)))
        if end_of(r) == 'normal' and r.get('winner') not in SIDES + (None,):
            warnings.append('%s has an unknown winner %r.' % (where, r.get('winner')))
        left = r.get('left') or {}
        if counted(r) and left:
            loser = SIDES[1 - SIDES.index(r['winner'])]
            if not left.get(r['winner']) or left.get(loser):
                warnings.append('%s: the winner (%s) has %s Pokémon left and the loser %s.'
                                % (where, lab[r['winner']], left.get(r['winner']), left.get(loser)))

    ends = collections.Counter(end_of(r) for r in rs)
    won = [r for r in rs if counted(r)]
    wins = sum(1 for r in won if r['winner'] == 'advanced')
    losses = len(won) - wins
    ci = wilson(wins, len(won))

    by_scn = collections.defaultdict(dict)
    for r in rs:
        by_scn[unit(r)][r.get('game')] = r
    score = collections.Counter({'2-0': 0, '1-1': 0, '0-2': 0, 'incomplete': 0})
    rows = []
    for scn in sorted(by_scn, key=natural):
        g = by_scn[scn]
        g0, g1 = g.get(0), g.get(1)
        if set(g) - {0, 1}:
            warnings.append('%s has games other than 0 and 1: %s.' % (scn, sorted(set(g) - {0, 1}, key=str)))
        if g0 and g1 and (g1.get('adv_team'), g1.get('orig_team')) != (g0.get('orig_team'), g0.get('adv_team')):
            warnings.append('%s: game 1 does not swap the teams of game 0.' % scn)
        a = g0.get('adv_team') if g0 else g1.get('orig_team')
        b = g0.get('orig_team') if g0 else g1.get('adv_team')
        if g0 and g1 and counted(g0) and counted(g1):
            k = (g0['winner'] == 'advanced') + (g1['winner'] == 'advanced')
            result = '%d-%d' % (k, 2 - k)
        else:
            result = 'incomplete'
        score[result] += 1
        rows.append({'scenario': scn, 'team_a': a, 'team_b': b, 'games': [game_cell(g0), game_cell(g1)],
                     'result': result})
    missing = max(0, (meta.get('scenarios') or 0) - len(by_scn))
    score['incomplete'] += missing
    k, n = score['2-0'], score['2-0'] + score['0-2']
    p = sign_test(k, n)

    fallbacks = fallback_counts(rs, 'advanced')
    polls = [r.get('adv_polls_max') for r in rs if r.get('adv_polls_max') is not None]
    player_polls = [(r.get('polls_max') or {}).get('original') for r in rs if isinstance(r.get('polls_max'), dict)]

    failures = {'inherited': [], 'review': []}
    for r in rs:
        inherited, review = classify_failures(r)
        for kind, items in (('inherited', inherited), ('review', review)):
            failures[kind] += [{'scenario': str(r.get('scenario')), 'game': r.get('game'), 'failure': x} for x in items]

    def failure_stats(items):
        battles = sorted({(x['scenario'], x['game']) for x in items}, key=lambda t: (natural(t[0]), t[1] or 0))
        return {'count': len(items), 'battles': [list(b) for b in battles], 'items': items}

    seconds = meta.get('seconds')
    s = {
        'mode': mode,
        'labels': lab,
        'sizes': sizes,
        'games': len(rs),
        'planned': 2 * meta['scenarios'] if meta.get('scenarios') else None,
        'ends': {e: ends.get(e, 0) for e in ENDS} | {e: c for e, c in ends.items() if e not in ENDS},
        'no_winner': [[str(r.get('scenario')), r.get('game')] for r in rs if end_of(r) == 'normal' and not counted(r)],
        'void': [{'scenario': str(r.get('scenario')), 'game': r.get('game'),
                  'wrong': {sd: ((r.get('decisions') or {}).get(sd) or {}).get('wrong', 0) for sd in SIDES}}
                 for r in rs if end_of(r) == 'wrong ai'],
        'counted': len(won), 'wins': wins, 'losses': losses,
        'win_rate': wins / len(won) if won else None, 'ci95': list(ci) if ci else None,
        'scenarios': dict(score) | {'total': len(by_scn) + missing, 'missing': missing},
        'sign_test': {'k': k, 'n': n, 'p': p},
        'turns': {'all': mean(r.get('turns') for r in won)}
                 | {sd: mean(r.get('turns') for r in won if r['winner'] == sd) for sd in SIDES},
        'left': {sd: mean((r.get('left') or {}).get(sd) for r in won if r['winner'] == sd) for sd in SIDES},
        'decisions': {sd: {x: sum(((r.get('decisions') or {}).get(sd) or {}).get(x, 0) for r in rs)
                           for x in ('right', 'wrong')} for sd in SIDES},
        'fallbacks': fallbacks,
        'fallback_share': fallback_share(fallbacks),
        'polls_max': max(polls) if polls else None,
        'failures': {kind: failure_stats(items) for kind, items in failures.items()},
        'counted_with_review': len({(x['scenario'], x['game']) for x in failures['review']}
                                   & {(str(r.get('scenario')), r.get('game')) for r in won}),
        'runtime': {'seconds': seconds,
                    'games_per_minute': len(rs) / (seconds / 60) if seconds else None,
                    'game_seconds': mean(r.get('seconds') for r in rs),
                    'game_minutes': (mean(r.get('frames') for r in rs) or 0) / 3600 or None},
        'per_scenario': rows,
        'warnings': warnings,
    }
    if mode == 'self':      # the player side's decisions come from the advanced AI too
        s['player_fallbacks'] = fallback_counts(rs, 'original')
        s['player_fallback_share'] = fallback_share(s['player_fallbacks'])
        s['player_polls_max'] = max((x for x in player_polls if x is not None), default=None)
        s['ai_replacements'] = {sd: {'made': sum((r.get('replacements') or {}).get(sd, 0) for r in rs)} |
                                {k: sum(((r.get('ai_replacements') or {}).get(sd) or {}).get(k, 0) for r in rs)
                                 for k in ('valued', 'changed')} for sd in SIDES}
    s['bias'] = control and bool(won) and (not ci[0] <= 0.5 <= ci[1] or p < ALPHA)
    s['verdict'], s['summary'] = verdict(s, control)
    return s


def pct(x):
    return '-' if x is None else '%.1f%%' % (100 * x)


def num(x, fmt='%.1f'):
    return '-' if x is None else fmt % x


def pval(p):
    return '< 0.0001' if p < 0.0001 else '%.3g' % p


def plural(n, word, many=None):
    return '%d %s' % (n, word if n == 1 else many or word + 's')


def ci_text(s):
    lo, hi = s['ci95']
    return '%s, 95%% range %s to %s' % (pct(s['win_rate']), pct(lo), pct(hi))


def p_sentence(s, control):
    k, n, p = s['sign_test']['k'], s['sign_test']['n'], s['sign_test']['p']
    who = 'side' if control else 'AI'
    if n == 0:
        return 'No scenario was won with both teams by either %s, so the sign test has nothing to test.' % who
    if 2 * k == n:
        return 'The 2-0 and 0-2 scenarios are even (%d each), so they show no difference (p = 1).' % k
    odds = ' (about 1 run in %d)' % round(1 / p) if p < 0.5 else ''
    if_equal = 'If neither side had an advantage' if control else 'If the two AIs were equally strong'
    tail = ('That is below %g, so chance is an unlikely explanation.' if p < ALPHA else
            'That is not below %g, so chance can explain it.') % ALPHA
    return ('%s, a split of %s 2-0 against %d 0-2, or one at least this uneven in either direction, would '
            'happen with probability %s%s. %s'
            % (if_equal, plural(k, 'scenario'), n - k, pval(p), odds, tail))


def verdict(s, control):
    """(one-line verdict, the report's two or three summary sentences)."""
    k, n, p = s['sign_test']['k'], s['sign_test']['n'], s['sign_test']['p']
    nv = len(s['void'])
    void = ((' 1 game is' if nv == 1 else ' %d games are' % nv) + ' void because a decision came from the wrong AI.'
            if nv else '')
    if not s['counted']:
        v = 'No game ended normally with a winner, so this run says nothing about %s.' % (
            'side bias' if control else 'the two AIs')
        return v, v + void
    rate = 'The %s won %d of %d counted games (%s).' % (s['labels']['advanced'], s['wins'], s['counted'], ci_text(s))
    split = 'The %s won %s 2-0 and lost %d 0-2, a split %s (sign test p = %s).' % (
        s['labels']['advanced'], plural(k, 'scenario'), n - k,
        'that chance is unlikely to produce' if p < ALPHA else 'that chance can explain', pval(p))
    if control:
        lo, hi = s['ci95']
        if not lo <= 0.5 <= hi:
            v = 'The trainer side has a bias: it wins %s than chance allows.' % ('more' if lo > 0.5 else 'less')
            more = ('It should win about 50% with the same AI on both sides, and the range does not contain 50%, so '
                    'the side or the setup has a bias. ' +
                    ('A control run (--control) tells a bias of the setup from the advanced AI playing one side '
                     'differently.' if s['mode'] == 'self' else
                     'Any advanced AI run on this setup carries it, because the advanced AI always plays the trainer '
                     'side.'))
        elif p < ALPHA:
            v = 'The setup may have a side bias: the range contains 50% but the sign test does not.'
            more = ('With the same AI on both sides it should win about 50%%, and the range contains 50%%. But the '
                    'scenarios won with both teams lean to the %s (p = %s). Treat the setup as biased until a larger '
                    'control run says otherwise.' % ('trainer side' if 2 * k > n else 'player side', pval(p)))
        else:
            v = 'No side bias: the range contains 50%.'
            more = ('With the same AI on both sides it should win about 50%, and the range contains 50%. The run '
                    'shows no side bias.')
        return v, ' '.join((rate, more)) + void
    if n == 0:
        v = 'The run cannot tell the two AIs apart: no scenario was won 2-0 by either AI.'
        return v, ' '.join((v, rate)) + void
    if p < ALPHA:
        v = ('The advanced AI beats the original AI.' if 2 * k > n else 'The original AI beats the advanced AI.')
        return v, ' '.join((v, split, rate)) + void
    v = 'The run does not show that either AI is stronger.'
    return v, ' '.join((v, split, rate)) + void


def rerun_commands(meta):
    def one(m):
        cmd = 'versus/aivsai.py %s --rom ROM --payload PAYLOAD --seed %s --teams %s --level %s --workers %s' % (
            m.get('scenarios'), m.get('seed'), m.get('teams', 'trainers'), m.get('level', 100), m.get('workers', 9))
        sz = team_sizes(m)
        cmd += ''.join(' --%s-size %d' % (flag, sz[sd]) for flag, sd in (('adv', 'advanced'), ('orig', 'original'))
                       if sz[sd] != FULL_TEAM)
        cmd += ' --pick random' if sz['pick'] == 'random' else ''
        cmd += ' --rng legacy' if m.get('rng', 'legacy') == 'legacy' else ''     # runs before 2026-10-04 have no 'rng'
        return cmd + {'control': ' --control', 'self': ' --self'}.get(m.get('mode'), '')
    return [one(m) for m in meta.get('sessions') or [meta]]


def cell_text(c, control):
    if c is None:
        return 'missing'
    short = {'advanced': 'trainer' if control else 'advanced', 'original': 'player' if control else 'original'}
    if c['end'] == 'normal' and c['winner'] in SIDES:
        return '%s won, %s turns, %s left' % (short[c['winner']], num(c['turns'], '%s'), num(c['left'], '%s'))
    if c['end'] == 'wrong ai':
        return '**void** (wrong AI)'
    if c['end'] == 'normal':
        return 'no winner, %s turns' % num(c['turns'], '%s')
    if c['end'] == 'unfinished':
        return 'unfinished, %s turns' % num(c['turns'], '%s')
    return str(c['end'])


def with_move_names(text):
    """'... (move 304)' -> '... (move 304, Hyper Voice)', the English name from lib/names.json."""
    try:
        names = json.load(open(os.path.join(tbpaths.LIB, 'names.json'), encoding='utf-8'))['move']
    except (OSError, ValueError, KeyError):
        return text
    return re.sub(r'\(move (\d+)\)', lambda m: '(move %s, %s)' % (m.group(1), names[m.group(1)])
                  if m.group(1) in names else m.group(0), text)


def md_escape(x):
    return str(x if x is not None else '?').replace('|', '\\|')


def render_markdown(s, meta):
    control = s['mode'] in SIDE_RUNS         # the sides named by side; s['mode'] tells the original from the advanced AI
    self_play = s['mode'] == 'self'
    lab = s['labels']
    A, O = lab['advanced'], lab['original']
    cap = lambda t: t[0].upper() + t[1:]  # noqa: E731
    sizes = s['sizes']
    cut = is_cut(sizes)
    title = ('# AI vs AI self-play run: advanced AI on both sides' if self_play else
             '# AI vs AI control run: original AI on both sides' if control else
             '# AI vs AI report: advanced AI against original AI')
    L = [title + (', %s' % sizes_text(sizes, control) if cut else ''), '']
    teams = {'trainers': "the hack's six-Pokémon trainer teams",
             'mixed': "new teams of six built from the trainer teams' Pokémon", 'random': 'random teams'}.get(meta.get('teams'),
                                                                                             str(meta.get('teams')))
    seeds = ', '.join(str(m.get('seed')) for m in meta['sessions']) if meta.get('sessions') else meta.get('seed')
    L.append('Run started %s. %s, %s planned, %d results. Teams: %s at level %s. Team sizes: %s%s. Seed %s. '
             'ROM SHA-1 `%s`.' % (
                 meta.get('started', '?'), plural(s['scenarios']['total'], 'scenario'),
                 plural(s['planned'] or 0, 'game'), s['games'], teams, meta.get('level'), sizes_text(sizes, control),
                 ' (%s)' % pick_text(sizes) if cut else '', seeds, meta.get('rom_sha1')))
    L.append('')
    if s['void']:
        where = ', '.join('%s game %s' % (v['scenario'], v['game']) for v in s['void'])
        L.append('> **%d %s VOID: a decision came from the wrong AI.** The routing that sends each side to its AI '
                 'failed in %s. %s not counted. Fix the routing before trusting this run. Void: %s.'
                 % (len(s['void']), 'GAME' if len(s['void']) == 1 else 'GAMES',
                    'that game' if len(s['void']) == 1 else 'those games',
                    'It is' if len(s['void']) == 1 else 'They are', where))
        L.append('')
    if s['warnings']:
        L.append('**Data checks.** The results have problems the runner should fix:')
        L.append('')
        L += ['- ' + w for w in s['warnings']]
        L.append('')

    L += ['## Summary', '', s['summary'], '']

    e = s['ends']
    others = ', '.join('%d %r' % (c, k) for k, c in e.items() if k not in ENDS and c)
    L += ['## Numbers', '',
          '- Games: %d played, %d counted (ended normally with a winner).' % (s['games'], s['counted']),
          '- Not counted: %d unfinished, %d frozen, %d with no battle, %d void (wrong AI), %d ended without a winner%s.'
          % (e['unfinished'], e['frozen'], e['no battle'], e['wrong ai'], len(s['no_winner']),
             ', ' + others if others else '')]
    if s['counted']:
        L.append('- %s: %s, %s. Win rate %s.' % (cap(A), plural(s['wins'], 'win'), plural(s['losses'], 'loss', 'losses'),
                                                 ci_text(s)))
        if control:
            lo, hi = s['ci95']
            L.append('- Expected about 50%%, since both sides run the same AI. The range %s 50%%.'
                     % ('contains' if lo <= 0.5 <= hi else 'does not contain'))
    else:
        L.append('- No counted game, so there is no win rate.')
    sc = s['scenarios']
    L.append('- Scenarios: %d won 2-0, %d split 1-1, %d lost 0-2 by the %s, %d incomplete%s.' % (
        sc['2-0'], sc['1-1'], sc['0-2'], A, sc['incomplete'],
        ' (%d with no result at all)' % sc['missing'] if sc['missing'] else ''))
    L.append('- Sign test on 2-0 against 0-2 scenarios: p = %s. %s' % (pval(s['sign_test']['p']), p_sentence(s, control)))
    L.append('- A 1-1 split means the stronger team won both games: the teams decided, not the %s.'
             % ('sides' if control else 'AIs'))
    L.append('- Average turns of a counted game: %s.' % num(s['turns']['all']))
    L += ['', '| | %s | %s |' % (cap(A), cap(O)), '|---|---|---|',
          '| Games won | %d | %d |' % (s['wins'], s['losses']),
          '| Average turns in its wins | %s | %s |' % (num(s['turns']['advanced']), num(s['turns']['original'])),
          '| Average Pokémon left when it won | %s | %s |' % (num(s['left']['advanced']), num(s['left']['original'])),
          '| Decisions from the right AI | %d | %d |' % (s['decisions']['advanced']['right'],
                                                      s['decisions']['original']['right']),
          '| Decisions from the wrong AI | %d | %d |' % (s['decisions']['advanced']['wrong'],
                                                      s['decisions']['original']['wrong']), '']
    L.append('Decisions are counted at the battle engine\'s action setters, with the AI that made each one. %s'
             % ('Both sides should get every decision from the advanced AI.' if self_play else
                'Both sides should get every decision from the original AI.' if control else
                'Every trainer-side decision should come from the advanced AI and every player-side one from the '
                'original AI.'))
    L.append('')

    if self_play:
        names, limit = advai_constants()
        L += ['### Advanced AI fallbacks', '']
        fb = {'advanced': s['fallbacks'], 'original': s.get('player_fallbacks') or {}}
        codes = sorted(set(fb['advanced']) | set(fb['original']), key=natural)
        if codes:
            L += ['| Code | Meaning | %s | %s |' % (cap(A), cap(O)), '|---|---|---|---|']
            L += ['| %s | %s | %d | %d |' % (code, names.get(code, '?'), fb['advanced'].get(code, 0), fb['original'].get(code, 0))
                  for code in codes]
            L += ['', 'Fell back: %s %s, %s %s. In a fallback the original AI\'s code, which the advanced AI\'s overlay '
                  'contains, made that decision.' % (A, pct(s['fallback_share']), O, pct(s.get('player_fallback_share')))]
        else:
            L.append('No fallback codes were recorded.')
        L.append('The largest poll count of one decision was %s on the %s and %s on the %s%s.' % (
            num(s['polls_max'], '%s'), A, num(s.get('player_polls_max'), '%s'), O,
            ' (the advanced AI gives up after %d)' % limit if limit else ''))
        L.append('')
        L.append('Replacements after a faint: %s. A replacement with one candidate left is not valued.' % replacements_text(s))
        L.append('')
    elif not control:
        names, limit = advai_constants()
        L += ['### Advanced AI fallbacks', '']
        if s['fallbacks']:
            L += ['| Code | Meaning | Decisions |', '|---|---|---|']
            L += ['| %s | %s | %d |' % (code, names.get(code, '?'), c) for code, c in s['fallbacks'].items()]
            total = sum(s['fallbacks'].values())
            L += ['', '%d of %d advanced AI decisions fell back (%s). In a fallback the original AI\'s code, which the '
                  'advanced AI\'s overlay contains, made that decision.' % (
                      total - s['fallbacks'].get('0', 0), total, pct(s['fallback_share']))]
        else:
            L.append('No fallback codes were recorded.')
        if s['polls_max'] is not None:
            L.append('The largest poll count of one decision was %d%s.' % (
                s['polls_max'], ' (the advanced AI gives up after %d)' % limit if limit else ''))
        L.append('')

    L += ['## Scenarios', '',
          'Game 0: the %s plays team A. Game 1: the teams are swapped. "Left" is the winner\'s Pokémon still able '
          'to fight. The score is the %s\'s.' % (A, A), '',
          '| Scenario | Team A | Team B | Game 0 | Game 1 | Score |', '|---|---|---|---|---|---|']
    for row in s['per_scenario']:
        L.append('| %s | %s | %s | %s | %s | %s |' % (
            md_escape(row['scenario']), md_escape(row['team_a']), md_escape(row['team_b']),
            cell_text(row['games'][0], control), cell_text(row['games'][1], control), row['result']))
    if sc['missing']:
        L.append('')
        L.append('%s had no result at all.' % plural(sc['missing'], 'scenario'))
    L.append('')

    f = s['failures']
    L += ['## Failures', '']
    if not f['review']['count'] and not f['inherited']['count']:
        L += ['No assert, freeze or memory failure.', '']
    else:
        L.append('Failures are sorted with the fuzz\'s classification (tools/aifuzz.py). Inherited ones happen in the '
                 'Chinese ROM too. Everything else needs review. A game with failures still counts when it ended '
                 'normally with a winner. %s had a failure that needs review.' % (
                     plural(s['counted_with_review'], 'counted game')))
        L.append('')
        L.append('### Needs review: %s in %s' % (plural(f['review']['count'], 'failure'),
                                                plural(len(f['review']['battles']), 'game')))
        L.append('')
        L += ['- %s game %s: %s' % (x['scenario'], x['game'], with_move_names(x['failure']))
              for x in f['review']['items']] or ['None.']
        L.append('')
        L.append('### Inherited: %s in %s' % (plural(f['inherited']['count'], 'failure'),
                                             plural(len(f['inherited']['battles']), 'game')))
        L.append('')
        groups = collections.defaultdict(list)
        for x in f['inherited']['items']:
            groups[x['failure']].append('%s game %s' % (x['scenario'], x['game']))
        L += ['- %s: %d (%s)' % (with_move_names(k), len(v), ', '.join(sorted(set(v), key=natural)))
              for k, v in groups.items()] or ['None.']
        L.append('')

    rt = s['runtime']
    L += ['## Runtime', '']
    if rt['seconds']:
        L.append('- Wall time %.1f min for %d games: %s games per minute with %s emulators%s.' % (
            rt['seconds'] / 60, s['games'], num(rt['games_per_minute']), meta.get('workers', '?'),
            {'fast': ', the battle ROM at 60 fps', 'normal': ', the battle ROM at 30 fps',
             'rom': ', the battle ROM unchanged'}.get(meta.get('speed'), '')))
    L.append('- Average game: %s s of emulator time, %s min of game time.' % (num(rt['game_seconds']),
                                                                            num(rt['game_minutes'])))
    L.append('')

    L += ['## Method', '']
    level = meta.get('level')
    if self_play:
        L.append('Both sides run the advanced AI, to find its mistakes: each side\'s decisions are logged with its own '
                 'weighed options, and its replacements after a faint with the values it gave the candidates. Each '
                 'scenario is two teams of six and a battle seed, played twice with the teams swapped. Every Pokémon '
                 'on both sides is at level %s. Neither side has bag items. Each side models its opponent as the '
                 'original AI, so this run tests the advanced AI against itself, not its strength: progress is '
                 'measured against the original AI. With the same AI on both sides, the trainer side should win about '
                 'half its games. Every decision is counted at the action setters with the AI that made it, and a '
                 'game with a decision from the wrong AI is void. A game counts only when it ended normally with a '
                 'winner. The 95%% range is a Wilson score interval on the counted games. The sign test compares the '
                 'scenarios the trainer side won with both teams against those it lost with both.' % level)
    elif control:
        L.append('Both sides run the original AI. The trainer side is the side the advanced AI plays in a normal run. '
                 'Each scenario is two teams of six and a battle seed, played twice with the teams swapped. Every '
                 'Pokémon on both sides is at level %s. Neither side has bag items. With the same AI on both sides, '
                 'the trainer side should win about half its games. If it does not, the side or the setup has a bias. '
                 'Every decision is counted at the action setters with the AI that made it, and a game with a '
                 'decision from the wrong AI is void. A game counts only when it ended normally with a winner. The '
                 '95%% range is a Wilson score interval on the counted games. The sign test compares the scenarios '
                 'the trainer side won with both teams against those it lost with both.' % level)
    else:
        L.append('Each scenario is two teams of six and a battle seed. It is played twice, the second time with the '
                 'teams swapped, so each AI plays both teams and a stronger team wins one game for each AI. Every '
                 'Pokémon on both sides is at level %s. Neither side has bag items. The advanced AI always plays the '
                 'trainer side and the original AI the player side. Swapping teams cancels team strength, not side, '
                 'so a control run (`--control`) measures any bias of the side itself. Every decision is counted at '
                 'the battle engine\'s action setters with the AI that made it. A game with a decision from the wrong '
                 'AI is void. A game counts only when it ended normally with a winner. The sign test is the main '
                 'test. It uses only the scenarios one AI won with both teams. The 95%% range is a Wilson score '
                 'interval on the counted games. It treats the games as independent, which two games with the same '
                 'teams are not quite.' % level)
    if cut:
        L.append('')
        L.append('Team sizes: the %s plays %s and the %s %s, in both games of a scenario (%s). The sizes stay '
                 'with the sides when the teams swap, so team strength still cancels out and the difference in '
                 'size stays with the %s.' % (A, plural(sizes['advanced'], 'Pokémon', 'Pokémon'), O,
                                              plural(sizes['original'], 'Pokémon', 'Pokémon'), pick_text(sizes), A))
    L += ['', '## Rerun', '', '```'] + rerun_commands(meta) + ['```', '']
    return '\n'.join(L)


def replacements_text(s):
    rep = s.get('ai_replacements') or {}
    return ', '.join('%s %d made, %d valued by ai_replace (%d not the engine\'s pick)' % (
        s['labels'][sd], rep[sd]['made'], rep[sd]['valued'], rep[sd]['changed']) for sd in SIDES if sd in rep)


def terminal_summary(s, meta, md_path):
    control = s['mode'] in SIDE_RUNS
    lab = s['labels']
    A, O = lab['advanced'], lab['original']
    sc, e, f = s['scenarios'], s['ends'], s['failures']
    out = ['AI vs AI %s: %s, %d games, teams %s, level %s, sizes %s%s, seed %s' % (
        {'control': 'control run (original AI on both sides)', 'self': 'self-play run (advanced AI on both sides)'}.get(
            s['mode'], '(advanced AI vs original AI)'),
        plural(sc['total'], 'scenario'), s['games'], meta.get('teams'), meta.get('level'),
        sizes_text(s['sizes'], control), ' (random members)' if s['sizes']['pick'] == 'random' else '',
        ', '.join(str(m.get('seed')) for m in meta['sessions']) if meta.get('sessions') else meta.get('seed'))]
    if s['void']:
        out.append('VOID: %s had a decision from the wrong AI (%s). The routing failed. Not counted.' % (
            plural(len(s['void']), 'game'), ', '.join('%s g%s' % (v['scenario'], v['game']) for v in s['void'])))
    if s['warnings']:
        out.append('Data checks: %s in the results (see the report).' % plural(len(s['warnings']), 'problem'))
    if s['counted']:
        out.append('Counted %d games: %s won %d, lost %d. Win rate %s' % (s['counted'], A, s['wins'], s['losses'],
                                                                         ci_text(s)))
    else:
        out.append('Counted 0 games.')
    out.append('Scenarios: %d won 2-0, %d split 1-1, %d lost 0-2, %d incomplete. Sign test p = %s' % (
        sc['2-0'], sc['1-1'], sc['0-2'], sc['incomplete'], pval(s['sign_test']['p'])))
    out.append('Verdict: ' + s['verdict'])
    out.append('Not counted: %d unfinished, %d frozen, %d no battle, %d wrong AI, %d without a winner' % (
        e['unfinished'], e['frozen'], e['no battle'], e['wrong ai'], len(s['no_winner'])))
    out.append('Turns %s on average. Pokémon left by the winner: %s %s, %s %s' % (
        num(s['turns']['all']), A, num(s['left']['advanced']), O, num(s['left']['original'])))
    d = s['decisions']
    line = 'Decisions: %s %d right, %d wrong; %s %d right, %d wrong' % (
        A, d['advanced']['right'], d['advanced']['wrong'], O, d['original']['right'], d['original']['wrong'])
    if s['mode'] == 'self':
        fell = lambda fb: '%d of %d' % (sum(fb.values()) - fb.get('0', 0), sum(fb.values()))  # noqa: E731
        line += '. Fallbacks %s %s, %s %s; polls max %s, %s' % (A, fell(s['fallbacks']), O, fell(s.get('player_fallbacks') or {}),
                                                               s['polls_max'], s.get('player_polls_max'))
    elif not control and s['fallbacks']:
        total = sum(s['fallbacks'].values())
        line += '. Fallbacks %d of %d, polls max %s' % (total - s['fallbacks'].get('0', 0), total, s['polls_max'])
    out.append(line)
    if s.get('ai_replacements'):
        out.append('Replacements: ' + replacements_text(s))
    out.append('Failures: %d %s review (%s), %d inherited (%s)' % (
        f['review']['count'], 'needs' if f['review']['count'] == 1 else 'need',
        plural(len(f['review']['battles']), 'game'),
        f['inherited']['count'], plural(len(f['inherited']['battles']), 'game')))
    rt = s['runtime']
    if rt['seconds']:
        out.append('Runtime %.1f min, %s games per minute' % (rt['seconds'] / 60, num(rt['games_per_minute'])))
    out.append('Report: %s' % md_path)
    return '\n'.join(out)


def write_report(results, meta, md_path, json_path=None):
    """Write the Markdown report (and the metadata, numbers and raw results as JSON); return the terminal summary."""
    s = summarize(results, meta)
    for path in (md_path, json_path):
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(md_path, 'w', encoding='utf-8') as fh:
        fh.write(render_markdown(s, meta))
    if json_path:
        with open(json_path, 'w', encoding='utf-8') as fh:
            json.dump({'meta': meta, 'summary': s, 'results': results}, fh, indent=1, ensure_ascii=False)
    return terminal_summary(s, meta, md_path)


def combine(runs):
    """Several saved runs ({'meta', 'results'}) as one: each scenario id gets its run's seed in front."""
    for key in ('mode', 'teams', 'level', 'rom_sha1'):
        if len({json.dumps(r['meta'].get(key)) for r in runs}) > 1:
            raise ValueError('cannot combine runs with a different %s' % key)
    sizes = {json.dumps(team_sizes(r['meta']), sort_keys=True) for r in runs}
    if len(sizes) > 1:
        raise ValueError('cannot combine runs with different team sizes: %s' % ', '.join(
            sorted('%s (%s members)' % (sizes_text(json.loads(x)), json.loads(x)['pick']) for x in sizes)))
    seeds = [r['meta'].get('seed') for r in runs]
    if len(set(map(str, seeds))) < len(seeds):
        raise ValueError('two runs share a seed, so they played the same scenarios')
    results = [dict(x, scenario='%s:%s' % (r['meta'].get('seed'), x.get('scenario'))) for r in runs for x in r['results']]
    metas = [r['meta'] for r in runs]
    meta = dict(metas[0], seed=None, sessions=metas, scenarios=sum(m.get('scenarios') or 0 for m in metas),
                seconds=sum(m.get('seconds') or 0 for m in metas), started=min(str(m.get('started')) for m in metas))
    return results, meta


def main():
    if sys.argv[1:] == ['--selftest']:
        return selftest()
    ap = argparse.ArgumentParser(description='Rewrite an AI vs AI report from saved results (several runs: combined).')
    ap.add_argument('json', nargs='+', help='results JSON written by write_report')
    ap.add_argument('--out', help='Markdown report to write (default: next to the JSON, or qa/aivsai/combined_<date>.md)')
    a = ap.parse_args()
    runs = [json.load(open(p, encoding='utf-8')) for p in a.json]
    if len(runs) == 1:
        results, meta = runs[0]['results'], runs[0]['meta']
        out, js = a.out or os.path.splitext(a.json[0])[0] + '.md', None
    else:
        try:
            results, meta = combine(runs)
        except ValueError as err:
            sys.exit(str(err))
        out = a.out or os.path.join(tbpaths.RUNS, 'aivsai', 'reports', 'combined_%s.md' % datetime.date.today().isoformat())
        js = os.path.splitext(out)[0] + '.json'
    print(write_report(results, meta, out, js))


# ---------------------------------------------------------------------------------------------------------------
# self-test: synthetic results with numbers checked by hand


def _game(scn, g, winner, end='normal', turns=20, left=2, failures=(), wrong=(0, 0), right=10, teams=None,
          fallbacks=None, polls=3, seconds=60.0, frames=21000):
    a, b = teams or ('Team %s-A' % scn, 'Team %s-B' % scn)
    if g == 1:
        a, b = b, a
    lft = {'advanced': 0, 'original': 0}
    if winner:
        lft[winner] = left
    return {'scenario': scn, 'game': g, 'adv_team': a, 'orig_team': b, 'winner': winner, 'end': end, 'turns': turns,
            'left': lft, 'frames': frames, 'seconds': seconds,
            'decisions': {'advanced': {'right': right, 'wrong': wrong[0]}, 'original': {'right': right, 'wrong': wrong[1]}},
            'adv_fallbacks': {'0': right} if fallbacks is None else fallbacks, 'adv_polls_max': polls,
            'failures': list(failures)}


def _meta(n, mode='adv-vs-orig', seed=1234, seconds=600.0):
    return {'rom_sha1': '0' * 40, 'mode': mode, 'teams': 'trainers', 'level': 100, 'seed': seed, 'workers': 9,
            'scenarios': n, 'started': '2026-10-02 17:30', 'seconds': seconds, 'rng': 'synced'}


def _pairs(spec, prefix='s', start=1):
    """Results of whole scenarios from a list of outcomes: '2-0', '1-1' or '0-2' for the advanced/trainer side."""
    out = []
    for i, res in enumerate(spec, start):
        scn = '%s%03d' % (prefix, i)
        w = {'2-0': ('advanced', 'advanced'), '1-1': ('advanced', 'original'), '0-2': ('original', 'original')}[res]
        out += [_game(scn, 0, w[0]), _game(scn, 1, w[1])]
    return out


def selftest():
    import tempfile
    os.makedirs(os.path.dirname(SAMPLE_MD), exist_ok=True)
    name = aifuzz.move_names()                   # the frozen names (no ROM given)
    said = lambda move: 'The Pokémon used %s!' % name[move]  # noqa: E731

    # the helpers, against values worked out by hand
    lo, hi = wilson(7, 10)                       # p = 0.7, z^2/n = 0.38415: (0.89207 -+ 0.34287) / 1.38415
    assert abs(lo - 0.3968) < 5e-4 and abs(hi - 0.8922) < 5e-4, (lo, hi)
    lo, hi = wilson(10, 10)                      # 1.19207 / 1.38415 - 0.19208 / 1.38415 = 0.7225
    assert abs(lo - 0.7225) < 5e-4 and abs(hi - 1) < 1e-12, (lo, hi)
    assert wilson(0, 0) is None
    assert sign_test(3, 4) == 0.625              # 2 * (C(4,0) + C(4,1)) / 16 = 10/16
    assert sign_test(8, 10) == 0.109375          # 2 * (1 + 10 + 45) / 1024 = 112/1024
    assert sign_test(9, 10) == 22 / 1024         # 2 * (1 + 10) / 1024
    assert sign_test(8, 8) == 2 / 256 and sign_test(0, 0) == 1.0 and sign_test(2, 4) == 1.0
    assert fuzz_ev('freeze') == 'freeze ' and fuzz_ev('assert  020056FE') == 'assert 020056FE' and fuzz_ev(None) == 'unknown '

    # A: advanced AI against original AI, every kind of game
    hv = {'ev': 'assert 020056FE', 'text': 'The opposing Pokémon', 'move_text': said(304)}  # Hyper Voice: inherited
    new = {'ev': 'assert 02012345', 'text': 'Something odd happens', 'move_text': None}     # nothing explains it
    end_assert = {'ev': 'assert 020733B2', 'text': None, 'move_text': None}                 # end of battle: inherited
    lt = [{'ev': 'freeze', 'text': None, 'move_text': said(536)},                           # Leaf Tornado's freeze
          {'ev': 'null 5', 'text': None, 'move_text': said(536)}]
    a = [_game('s001', 0, 'advanced', left=3, failures=[hv]), _game('s001', 1, 'advanced'),
         _game('s002', 0, 'advanced', fallbacks={'0': 9, '6': 1}), _game('s002', 1, 'advanced', failures=[new]),
         _game('s003', 0, 'advanced', failures=[end_assert, end_assert]), _game('s003', 1, 'advanced', polls=7),
         _game('s004', 0, 'advanced', left=1), _game('s004', 1, 'original', turns=30, left=1),
         _game('s005', 0, 'original', turns=30, left=1), _game('s005', 1, 'original', turns=30, left=1),
         _game('s006', 0, None, end='unfinished', turns=400), _game('s006', 1, None, end='frozen', failures=lt),
         _game('s007', 0, None, end='wrong ai', wrong=(0, 1)),
         _game('s007', 1, None, end='no battle', turns=0, right=0, fallbacks={}),
         _game('s008', 0, 'advanced', wrong=(2, 0))]                                       # marked normal: void
    s = summarize(a, _meta(9))
    assert (s['games'], s['counted'], s['wins'], s['losses']) == (15, 10, 7, 3), s
    assert abs(s['ci95'][0] - 0.3968) < 5e-4 and abs(s['ci95'][1] - 0.8922) < 5e-4
    assert s['ends'] == {'normal': 10, 'unfinished': 1, 'frozen': 1, 'no battle': 1, 'wrong ai': 2}, s['ends']
    assert [(v['scenario'], v['game']) for v in s['void']] == [('s007', 0), ('s008', 0)]
    assert {k: s['scenarios'][k] for k in ('2-0', '1-1', '0-2', 'incomplete', 'missing', 'total')} == \
        {'2-0': 3, '1-1': 1, '0-2': 1, 'incomplete': 4, 'missing': 1, 'total': 9}, s['scenarios']
    assert s['sign_test'] == {'k': 3, 'n': 4, 'p': 0.625}
    assert s['turns'] == {'all': 23.0, 'advanced': 20.0, 'original': 30.0}, s['turns']     # (7*20 + 3*30) / 10
    assert s['left'] == {'advanced': 2.0, 'original': 1.0}, s['left']                      # (3 + 5*2 + 1) / 7
    assert s['decisions'] == {'advanced': {'right': 140, 'wrong': 2}, 'original': {'right': 140, 'wrong': 1}}
    assert s['fallbacks'] == {'0': 139, '6': 1} and s['polls_max'] == 7
    f = s['failures']
    assert (f['inherited']['count'], f['inherited']['battles']) == (5, [['s001', 0], ['s003', 0], ['s006', 1]]), f
    assert (f['review']['count'], f['review']['battles']) == (1, [['s002', 1]]), f
    assert {x['failure'] for x in f['inherited']['items']} == {
        'assert 020056FE (move 304)', 'assert 020733B2 (end of battle)', 'freeze (move 536)', 'null 5 (move 536)'}
    assert s['counted_with_review'] == 1
    assert s['runtime']['games_per_minute'] == 1.5                                         # 15 games in 10 min
    assert any('s008 game 0' in w and 'void' in w for w in s['warnings']) and len(s['warnings']) == 1, s['warnings']
    assert s['verdict'] == 'The run does not show that either AI is stronger.'
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, 'a.json')
        term = write_report(a, _meta(9), SAMPLE_MD, js)
        md = open(SAMPLE_MD, encoding='utf-8').read()
        back = json.load(open(js, encoding='utf-8'))
        assert back['summary']['wins'] == 7 and len(back['results']) == 15 and back['meta']['seed'] == 1234
        assert md.index('**2 GAMES VOID') < md.index('## Summary') and 'VOID' in term
        assert '- assert 020056FE (move 304, Hyper Voice): 1 (s001 game 0)' in md and '1 needs review' in term
        assert '| s001 | Team s001-A | Team s001-B | advanced won, 20 turns, 3 left |' in md
        assert 'versus/aivsai.py 9 --rom ROM --payload PAYLOAD --seed 1234 --teams trainers --level 100 --workers 9\n' in md
        assert '\u2014' not in md and '\u2014' not in term
        print(term)
        print()

        # B: a clear edge for the advanced AI (9 scenarios 2-0, 1 lost 0-2)
        b = _pairs(['2-0'] * 9 + ['1-1'] * 2 + ['0-2'])
        s = summarize(b, _meta(12))
        assert s['sign_test']['p'] == 22 / 1024 and (s['wins'], s['losses']) == (20, 4)
        assert s['verdict'] == 'The advanced AI beats the original AI.', s['verdict']
        assert summarize(_pairs(['0-2'] * 6), _meta(6))['verdict'] == 'The original AI beats the advanced AI.'

        # C: control run with no bias (5 of 12), plus a frozen game with no failure recorded
        c = _pairs(['2-0'] + ['1-1'] * 3 + ['0-2'] * 2, prefix='c')
        c += [_game('c007', 0, None, end='frozen'), _game('c007', 1, None, end='unfinished')]
        s = summarize(c, _meta(7, mode='control'))
        assert (s['counted'], s['wins'], s['bias']) == (12, 5, False) and s['sign_test']['p'] == 1.0
        assert s['ci95'][0] < 0.5 < s['ci95'][1] and s['labels']['advanced'] == 'trainer side'
        assert s['failures']['review']['items'] == [{'scenario': 'c007', 'game': 0, 'failure': 'freeze'}]
        term_c = write_report(c, _meta(7, mode='control'), SAMPLE_CONTROL_MD)
        md = open(SAMPLE_CONTROL_MD, encoding='utf-8').read()
        assert 'trainer side' in md and 'The range contains 50%.' in md and '--control' in md
        assert 'Advanced AI fallbacks' not in md and '\u2014' not in md
        print(term_c)
        print()

        # D: control run with a side bias (18 of 20; 8 scenarios 2-0, none 0-2)
        s = summarize(_pairs(['2-0'] * 8 + ['1-1'] * 2), _meta(10, mode='control'))
        assert s['bias'] and s['sign_test']['p'] == 2 / 256 and s['ci95'][0] > 0.5
        assert s['verdict'].startswith('The trainer side has a bias'), s['verdict']

        # E: every game unfinished
        e = [_game('s%03d' % i, g, None, end='unfinished', turns=300) for i in range(1, 5) for g in (0, 1)]
        s = summarize(e, _meta(4))
        assert (s['counted'], s['win_rate'], s['ci95'], s['scenarios']['incomplete']) == (0, None, None, 4)
        assert s['verdict'].startswith('No game ended normally')
        assert 'Counted 0 games.' in write_report(e, _meta(4), os.path.join(tmp, 'e.md'))

        # F: no counted game of any kind: void, no battle, frozen, a draw; too many end-of-battle asserts
        F = [_game('s001', 0, None, end='wrong ai', wrong=(1, 0)), _game('s001', 1, None, end='no battle', right=0),
             _game('s002', 0, None, end='frozen', failures=[end_assert] * 6),
             _game('s002', 1, None, end='normal', turns=50)]
        s = summarize(F, _meta(2))
        assert s['counted'] == 0 and len(s['void']) == 1 and s['no_winner'] == [['s002', 1]]
        assert [x['failure'] for x in s['failures']['review']['items']] == ['6 end-of-battle asserts', 'freeze']
        md_path = os.path.join(tmp, 'f.md')
        write_report(F, _meta(2), md_path)
        md = open(md_path, encoding='utf-8').read()
        assert '**1 GAME VOID' in md and 'no winner, 50 turns' in md

        # no results at all (every worker died)
        s = summarize([], _meta(3))
        assert (s['games'], s['counted'], s['scenarios']['incomplete'], s['scenarios']['missing']) == (0, 0, 3, 3)
        write_report([], _meta(3), os.path.join(tmp, 'empty.md'))

        # combining two sessions; the same seed twice is refused
        r1 = {'meta': _meta(3, seed=1), 'results': _pairs(['2-0'] * 3)}
        r2 = {'meta': _meta(2, seed=2), 'results': _pairs(['0-2', '1-1'])}
        results, meta = combine([r1, r2])
        s = summarize(results, meta)
        assert s['scenarios']['total'] == 5 and s['scenarios']['missing'] == 0 and s['games'] == 10
        assert (s['wins'], s['losses']) == (7, 3) and s['runtime']['seconds'] == 1200.0
        assert rerun_commands(meta) == ['versus/aivsai.py 3 --rom ROM --payload PAYLOAD --seed 1 --teams trainers --level 100 --workers 9',
                                        'versus/aivsai.py 2 --rom ROM --payload PAYLOAD --seed 2 --teams trainers --level 100 --workers 9']
        try:
            combine([r1, r1])
            raise AssertionError('combined two runs with the same seed')
        except ValueError:
            pass

        # G: team sizes, the advanced side with 4 against 6
        sized = lambda m, a=4, o=6, pick='first': dict(m, adv_size=a, orig_size=o, pick=pick)  # noqa: E731
        g = _pairs(['2-0', '0-2'])
        for r in g:
            r['sizes'], r['parties'] = {'advanced': 4, 'original': 6}, {'advanced': 4, 'original': 6}
        s = summarize(g, sized(_meta(2)))
        assert s['sizes'] == {'advanced': 4, 'original': 6, 'pick': 'first'} and not s['warnings'], s['warnings']
        assert (s['wins'], s['losses']) == (2, 2)                                            # the numbers as before
        md_path = os.path.join(tmp, 'g.md')
        term = write_report(g, sized(_meta(2)), md_path)
        md = open(md_path, encoding='utf-8').read()
        assert md.startswith('# AI vs AI report: advanced AI against original AI, ADVANCED 4 vs ORIGINAL 6\n'), md[:80]
        assert 'Team sizes: ADVANCED 4 vs ORIGINAL 6 (each team keeps its first members).' in md
        assert 'versus/aivsai.py 2 --rom ROM --payload PAYLOAD --seed 1234 --teams trainers --level 100 --workers 9 --adv-size 4\n' in md
        assert 'sizes ADVANCED 4 vs ORIGINAL 6,' in term and '\u2014' not in md
        assert 'Team sizes: ADVANCED 6 vs ORIGINAL 6.' in open(SAMPLE_MD, encoding='utf-8').read()
        # a game played at other sizes, an engine party that is not the built one, more left than the team had
        g[0]['sizes'] = g[0]['parties'] = {'advanced': 6, 'original': 6}
        g[1]['parties'] = {'advanced': 6, 'original': 6}
        g[2]['left'] = {'advanced': 0, 'original': 7}
        w = summarize(g, sized(_meta(2)))['warnings']
        assert len(w) == 3 and 'played ADVANCED 6 vs ORIGINAL 6, but the run says ADVANCED 4 vs ORIGINAL 6' in w[0], w
        assert 'engine held parties of ADVANCED 6 vs ORIGINAL 6' in w[1] and '7 Pokémon left of 6' in w[2], w
        assert sized(_meta(1), 3, 6, 'random') and 'versus/aivsai.py 1 --rom ROM --payload PAYLOAD --seed 1234 --teams trainers --level 100 --workers 9 ' \
            '--adv-size 3 --pick random' == rerun_commands(sized(_meta(1), 3, 6, 'random'))[0]
        assert rerun_commands(sized(_meta(1), 6, 6, 'random')) == rerun_commands(_meta(1))     # no cut: pick is moot
        old = dict(_meta(1))
        del old['rng']
        assert rerun_commands(old) == ['versus/aivsai.py 1 --rom ROM --payload PAYLOAD --seed 1234 --teams trainers --level 100 --workers 9 --rng legacy']
        # combining: different sizes or picks are refused; a run from before the options is 6 against 6
        for other in (sized(_meta(2, seed=2), 6, 6), sized(_meta(2, seed=2), 4, 6, 'random'), _meta(2, seed=2)):
            try:
                combine([{'meta': sized(_meta(2)), 'results': g}, {'meta': other, 'results': g}])
                raise AssertionError('combined runs with different team sizes')
            except ValueError as err:
                assert 'different team sizes' in str(err), err
        results, meta = combine([r1, {'meta': sized(_meta(2, seed=2), 6, 6), 'results': r2['results']}])
        assert team_sizes(meta) == {'advanced': 6, 'original': 6, 'pick': 'first'} and len(results) == 10

        # H: self-play, the advanced AI on both sides: the sides named by side, fallbacks per side, --self to rerun
        h = _pairs(['2-0', '1-1', '0-2'], prefix='h')
        for r in h:
            r['fallbacks'] = {'advanced': {'0': 9, '6': 1}, 'original': {'0': 10}}
            r['adv_fallbacks'], r['adv_polls_max'] = r['fallbacks']['advanced'], 5
            r['polls_max'] = {'advanced': 5, 'original': 7}
            r['replacements'] = {'advanced': 4, 'original': 5, 'unknown': 0}
            r['ai_replacements'] = {'advanced': {'valued': 3, 'changed': 1, 'not_taken': 0},
                                    'original': {'valued': 4, 'changed': 0, 'not_taken': 0}}
        s = summarize(h, _meta(3, mode='self'))
        assert s['mode'] == 'self' and s['labels'] == {'advanced': 'trainer side', 'original': 'player side'}, s['labels']
        assert s['fallbacks'] == {'0': 54, '6': 6} and s['player_fallbacks'] == {'0': 60}, s['fallbacks']
        assert (s['polls_max'], s['player_polls_max'], s['player_fallback_share']) == (5, 7, 0.0)
        assert (s['wins'], s['losses'], s['bias']) == (3, 3, False) and s['verdict'] == 'No side bias: the range contains 50%.'
        md_path = os.path.join(tmp, 'h.md')
        term = write_report(h, dict(_meta(3, mode='self'), adv_size=4, orig_size=6), md_path)
        md = open(md_path, encoding='utf-8').read()
        assert md.startswith('# AI vs AI self-play run: advanced AI on both sides, TRAINER SIDE 4 vs PLAYER SIDE 6\n'), md[:90]
        assert '| Code | Meaning | Trainer side | Player side |' in md and '| 6 | ' in md and '| 1 | 0 |' not in md
        assert '| h001 | Team h001-A | Team h001-B | trainer won, 20 turns, 2 left |' in md
        assert 'Both sides should get every decision from the advanced AI.' in md and '--adv-size 4 --self\n' in md
        assert 'self-play run (advanced AI on both sides)' in term and 'polls max 5, 7' in term, term
        assert "Replacements: trainer side 24 made, 18 valued by ai_replace (6 not the engine's pick), player side 30 " \
            "made, 24 valued by ai_replace (0 not the engine's pick)" in term, term
        assert "Replacements after a faint: trainer side 24 made" in md
        assert '\u2014' not in md and '\u2014' not in term
        for other in (_meta(2, seed=2), _meta(2, mode='control', seed=2)):
            try:
                combine([{'meta': _meta(3, mode='self'), 'results': h}, {'meta': other, 'results': h}])
                raise AssertionError('combined a self-play run with another mode')
            except ValueError as err:
                assert 'different mode' in str(err), err
    print('selftest passed; sample reports: %s, %s' % (tbpaths.rel(SAMPLE_MD), tbpaths.rel(SAMPLE_CONTROL_MD)))


if __name__ == '__main__':
    main()
