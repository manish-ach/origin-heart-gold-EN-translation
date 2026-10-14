"""The turn-level validator: the emulator's logged turns replayed in the simulator and graded (tools/sim/validate.c).

  .venv/bin/python tools/sim/validate.py [--runs GLOB] [--ai] [--show CAT] [--top N] [--json OUT]

Parses the logs (tools/sim/turnlog.py) into tools/sim/build/val/<name>.txt, runs `sim validate` on them and prints:
- coverage: games, turns, hits, random decisions graded, facts compared;
- the findings by category, most frequent first, with their commonest keys (move, ability, item, Pokemon):
  zero:KIND (a random outcome the model gives probability 0), damage (a logged hit outside the 16 rolls),
  order (the log's order impossible in the model), sim_only:WHAT / log_only:WHAT (an effect only one side shows),
  drift:WHAT (the state at a turn's start differs from what the simulator carried over), and the rest;
- the rates: for each kind of random decision and each probability the model uses, the decisions, the outcomes
  observed and expected, and z (observed - expected over the binomial standard error);
- with --ai, the value check: the advanced AI's option values in the replayed states against the logged ones.
--show CAT prints up to --top examples of one category (e.g. --show damage, --show drift:hp).
"""
import argparse
import collections
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import simbuild  # noqa: E402
import simpool  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SIM = os.environ.get('ADVAI_SIM') or simbuild.binary()
VAL = tbpaths.run_dir('sim', 'val')
KEYS = ('move', 'kind', 'what', 'ability', 'item', 'dability', 'ditem', 'mon', 'aname')


def category(d):
    c = d['cat']
    if c in ('drift', 'sim_only', 'log_only'):
        return c + ':' + d['what']
    if c == 'zero':
        return c + ':' + d['kind']
    if c == 'damage':
        return 'damage:' + ('in_range' if d['min'] <= d['logged'] <= d['max'] else 'out_of_range')
    return c


def turn_text(path, turn, n):
    """The log's lines of turns turn-n+1 .. turn, without the option lines."""
    out, keep = [], False
    for line in open(path, encoding='utf-8'):
        if line.startswith('--- Turn '):
            t = int(line.split()[2])
            keep = turn - n < t <= turn
        if keep and not line.startswith('            '):
            out.append('    ' + line.rstrip())
    return '\n'.join(out)


def run(obs, ai, sim=SIM):
    out = simpool.run([sim, 'validate', obs] + (['--ai'] if ai else []), capture_output=True, text=True, check=True)
    games, findings, rates, summary = {}, [], [], None
    for line in out.stdout.splitlines():
        d = json.loads(line)
        if 'game' in d and 'path' in d:
            games[d['game']] = d['path']
        elif 'cat' in d:
            findings.append(d)
        elif 'rate' in d:
            rates.append(d)
        elif d.get('summary'):
            summary = d
    return games, findings, rates, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', default=os.path.join(tbpaths.RUNS, 'aivsai', '*_self*'))
    ap.add_argument('--name', default=None, help='the parsed file name (default from --runs)')
    ap.add_argument('--ai', action='store_true')
    ap.add_argument('--sim', default=SIM, help='the simulator binary (default: simbuild.binary())')
    ap.add_argument('--no-parse', action='store_true', help='reuse the parsed file')
    ap.add_argument('--show', default=None)
    ap.add_argument('--top', type=int, default=12)
    ap.add_argument('--grep', default=None, help='with --show: only findings whose JSON contains this text')
    ap.add_argument('--context', type=int, default=0, help='with --show: print the turn (and N-1 turns before) from the log')
    ap.add_argument('--json', default=None, help='write the counts here (for before/after comparisons)')
    a = ap.parse_args()
    name = a.name or ('all' if '*' in os.path.basename(a.runs) else os.path.basename(a.runs.rstrip('/')))
    obs = os.path.join(VAL, name + '.txt')
    os.makedirs(os.path.dirname(obs), exist_ok=True)
    if not a.no_parse or not os.path.exists(obs):
        subprocess.run([PY, os.path.join(HERE, 'turnlog.py'), '--runs', a.runs, '-o', obs], check=True)
    games, findings, rates, s = run(obs, a.ai, a.sim)
    counts = collections.Counter(category(d) for d in findings)
    if a.show:
        n = 0
        for d in findings:
            if (category(d) == a.show or d['cat'] == a.show) and (not a.grep or a.grep in json.dumps(d, ensure_ascii=False)):
                print(games.get(d['g'], '?'), json.dumps(d, ensure_ascii=False))
                if a.context:
                    print(turn_text(os.path.join(tbpaths.WORK, games.get(d['g'], '')), d['t'], a.context))
                n += 1
                if n >= a.top:
                    break
        return
    dec = sum(v for k, v in s.items() if k.startswith('dec_'))
    zero = sum(v for k, v in s.items() if k.startswith('zero_'))
    print('coverage: %d games, %d turns played (%d games stopped early); %d logged hits checked (%d exact roll, %d KO or '
          'survival clamp, %d outside the rolls, %d hits the log lacks); %d random decisions graded, %d at probability 0' % (
              s['games'], s['turns'], s['stopped'], s['hits'], s['hits_exact'], s['hits_clamp'], s['hits_out'],
              s['hits_unlogged'], dec, zero))
    print('\nfindings by category (count, then the commonest keys):')
    for cat, n in counts.most_common():
        keys = collections.Counter()
        for d in findings:
            if category(d) == cat:
                key = ' '.join('%s=%s' % (k, d[k]) for k in ('move', 'kind', 'ability', 'item', 'aname', 'stat', 'st')
                               if d.get(k) not in (None, '', 'None'))[:90]
                keys[key] += 1
        top = '; '.join('%s (%d)' % (k, v) for k, v in keys.most_common(3))
        print('  %5d  %-26s %s' % (n, cat, top))
    print('\nrates (kind, model p: decisions, observed, expected, z):')
    for r in sorted(rates, key=lambda r: (r['rate'], r['p'])):
        if r['n'] < 5 and r['p'] not in (0, 1):
            continue
        sd = math.sqrt(r['n'] * r['p'] * (1 - r['p'])) if 0 < r['p'] < 1 else 0
        z = (r['yes'] - r['exp']) / sd if sd else 0
        print('  %-12s p=%.4f: %6d decisions, %5d observed (%.3f), %8.1f expected, z %+.1f' % (
            r['rate'], r['p'], r['n'], r['yes'], r['yes'] / r['n'] if r['n'] else 0, r['exp'], z))
    if a.ai and 'value_decisions' in s:
        print('\nvalue check: %d decisions; all shown values exact in %d (%.1f%%); the same top option in %d (%.1f%%); '
              '%d of %d shown values exact; foe model s equal in %d of %d; replacements %d, the same pick in %d' % (
                  s['value_decisions'], s['value_exact'], 100 * s['value_exact'] / max(1, s['value_decisions']),
                  s['value_top_same'], 100 * s['value_top_same'] / max(1, s['value_decisions']), s['value_shown_exact'],
                  s['value_shown'], s['strong_same'], s['strong_n'], s['repl'], s['repl_same']))
    if a.json:
        with open(a.json, 'w') as f:
            json.dump({'summary': s, 'counts': counts, 'rates': rates}, f, indent=1)


if __name__ == '__main__':
    main()
