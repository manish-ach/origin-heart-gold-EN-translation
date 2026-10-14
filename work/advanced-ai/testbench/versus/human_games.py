"""The person's battles against the advanced AI (versus/aiplay.py), for their analysis.

  .venv/bin/python work/advanced-ai/testbench/versus/human_games.py list [--all] [--batch N] [--json] [--index PATH]
  .venv/bin/python work/advanced-ai/testbench/versus/human_games.py mark-analyzed ID ... [--findings PATH] [--index PATH]
  .venv/bin/python work/advanced-ai/testbench/versus/human_games.py mark-analyzed --listed [--findings PATH] [--index PATH]

Ported from the Spanish workspace's qa/aivsai/human_games.py (dc8577c); only the paths changed.

list prints the games of RUNS/aivsai/human/index.jsonl that are not analyzed yet, oldest first, one per line: the
id, who won, turns, sizes (you vs the AI), Pokémon left, how it ended, and the log (relative to the repository). A game
with no turn played (no battle, or stopped before the first turn) is left out. A game the person stopped
('abandoned') is listed: its turns are still evidence. --all lists every game, analyzed or not. --batch N groups
the listed games N to a batch, in order, for the analysts. --json prints the same as JSON.

mark-analyzed sets 'analyzed': true, the date and --findings (the folder or file of the analysis) on the given
ids; --listed marks exactly the games list (without --all) shows. Marking a game twice changes nothing more.
Standard library only.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)

INDEX = os.path.join(tbpaths.RUNS, 'aivsai', 'human', 'index.jsonl')


def load(path):
    games = []
    if not os.path.exists(path):
        return games
    with open(path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                games.append(json.loads(line))
            except ValueError:
                print('warning: %s line %d is not JSON: left as it is' % (path, n), file=sys.stderr)
                games.append({'_raw': line.rstrip('\n')})
    return games


def save(path, games):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for g in games:
            f.write((g['_raw'] if '_raw' in g else json.dumps(g, ensure_ascii=False)) + '\n')
    os.replace(tmp, path)


def listed(games, everything=False):
    return [g for g in games if '_raw' not in g and (everything or (not g.get('analyzed') and g.get('turns', 0) > 0))]


def line(g):
    who = {'human': 'you won', 'ai': 'AI won'}.get(g.get('winner'), 'no winner')
    sizes, left = g.get('sizes') or {}, g.get('left') or {}
    return '%-22s %-9s %3s turns  %sv%s  left %s-%s  %-9s %s%s' % (
        g['id'], who, g.get('turns', 0), sizes.get('human', '?'), sizes.get('ai', '?'), left.get('human', '?'),
        left.get('ai', '?'), g.get('end', '?'), g.get('log', '?'), '  (analyzed)' if g.get('analyzed') else '')


def main():
    ap = argparse.ArgumentParser(description='List or mark the person\'s games against the advanced AI.')
    ap.add_argument('--index', default=INDEX, help='the index file (default RUNS/aivsai/human/index.jsonl)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    ls = sub.add_parser('list', help='the games not analyzed yet')
    ls.add_argument('--all', action='store_true', help='every game, analyzed or not')
    ls.add_argument('--batch', type=int, help='group the games N to a batch')
    ls.add_argument('--json', action='store_true')
    mk = sub.add_parser('mark-analyzed', help='mark games as analyzed')
    mk.add_argument('ids', nargs='*')
    mk.add_argument('--listed', action='store_true', help='every game list shows now')
    mk.add_argument('--findings', help='where the analysis is (recorded with each game)')
    a = ap.parse_args()
    games = load(a.index)
    if a.cmd == 'list':
        out = listed(games, a.all)
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return 0
        if not out:
            print('no games to analyze' if not a.all else 'no games yet', '(%s)' % tbpaths.rel(a.index))
            return 0
        if a.batch:
            for k in range(0, len(out), a.batch):
                print('batch %d:' % (k // a.batch + 1))
                for g in out[k:k + a.batch]:
                    print('  ' + line(g))
        else:
            for g in out:
                print(line(g))
        print('%d game(s)' % len(out))
        return 0
    if a.listed == bool(a.ids):
        ap.error('give game ids or --listed (not both)')
    want = {g['id'] for g in listed(games)} if a.listed else set(a.ids)
    known = {g.get('id') for g in games}
    unknown = sorted(want - known)
    if unknown:
        sys.exit('not in %s: %s' % (tbpaths.rel(a.index), ', '.join(unknown)))
    today, marked = datetime.date.today().isoformat(), 0
    for g in games:
        if g.get('id') in want and not g.get('analyzed'):
            g['analyzed'], g['analyzed_on'] = True, today
            if a.findings:
                g['findings'] = a.findings
            marked += 1
    save(a.index, games)
    print('marked %d game(s) analyzed (%d already were)' % (marked, len(want) - marked))
    return 0


if __name__ == '__main__':
    sys.exit(main())
