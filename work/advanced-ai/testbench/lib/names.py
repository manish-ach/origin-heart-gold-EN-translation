"""The test bench's frozen English names of species, moves, abilities and items, keyed by ROM id (lib/names.json).

  .venv/bin/python work/advanced-ai/testbench/lib/names.py make [--es-repo DIR]   # regenerate names.json
  .venv/bin/python work/advanced-ai/testbench/lib/names.py check [--es-repo DIR]  # names.json equals a fresh make
(the Spanish workspace repository: --es-repo, or ADVAI_ES_REPO)

Every test bench tool names things through this one table (lib/aidata.py), never through a ROM's text banks: the
Spanish rc44 ROM prints Spanish names and ours prints modern English ones, so ROM text cannot be the key. The
scenarios, the simulator's S_/M_/A_/I_ constants (sim/gen_simdata.py: ident(norm(name))), aicalc's keys and the
AI-vs-AI logs all use these names, so the logs of the same games are byte-identical on both ROMs' tool runs.

Source (orchestrator decision, 2026-10-13): the Spanish workspace at commit dc8577c (luisvent, reused with his
permission), project-authored ROM-style English names (12-character spellings such as 'WellBakedBdy'):
- species: work_es/text/en/0232.json 'strings' (index = ROM species id);
- moves, abilities, items: work_es/glossary/names_{moves,abilities,items}.json, each id's 'en';
- trainer classes and natures: work_es/text/en/0720.json and 0033.json 'strings' (versus/aiteams.py names a team
  'Class Name' with the class from here and the name from the ROM's bank 719, as the Spanish tool did).
Our own work/glossary is not used: its ids are PokéAPI ids (items differ from ROM ids) and some spellings differ.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'names.json')
ES_REPO = os.environ.get('ADVAI_ES_REPO')     # the Spanish workspace repository (or --es-repo)
ES_COMMIT = 'dc8577c'
SOURCES = {'species': 'work_es/text/en/0232.json', 'move': 'work_es/glossary/names_moves.json',
           'ability': 'work_es/glossary/names_abilities.json', 'item': 'work_es/glossary/names_items.json',
           'trainer_class': 'work_es/text/en/0720.json', 'nature': 'work_es/text/en/0033.json'}


def git_show(repo, path):
    return subprocess.run(['git', '-C', repo, 'show', '%s:%s' % (ES_COMMIT, path)], check=True,
                          capture_output=True).stdout


def build(repo):
    """The names table from the Spanish workspace's commit: {'source', 'species', 'trainer_class', 'nature': [name by
    id], 'move', 'ability', 'item': {id: name}}."""
    bank = lambda kind: json.loads(git_show(repo, SOURCES[kind]))['strings']  # noqa: E731
    out = {'source': {'repository': 'Spanish workspace (Origin HeartGold ES)', 'commit': ES_COMMIT, 'files': SOURCES},
           'species': bank('species'), 'trainer_class': bank('trainer_class'), 'nature': bank('nature')}
    for kind in ('move', 'ability', 'item'):
        table = json.loads(git_show(repo, SOURCES[kind]))
        out[kind] = {k: v['en'] for k, v in table.items() if v.get('en')}     # the file's order: first wins
    return out


def dump(table):
    return json.dumps(table, ensure_ascii=False, indent=1) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=('make', 'check'))
    ap.add_argument('--es-repo', default=ES_REPO, help='the Spanish workspace repository (default: ADVAI_ES_REPO)')
    a = ap.parse_args()
    if not a.es_repo:
        ap.error('give --es-repo DIR or set ADVAI_ES_REPO to the Spanish workspace repository')
    text = dump(build(a.es_repo))
    if a.action == 'make':
        with open(OUT, 'w', encoding='utf-8') as f:
            f.write(text)
        print('wrote %s' % OUT)
        return
    same = os.path.exists(OUT) and open(OUT, encoding='utf-8').read() == text
    print('names.json %s the Spanish workspace at %s' % ('equals' if same else 'DIFFERS FROM', ES_COMMIT))
    sys.exit(0 if same else 1)


if __name__ == '__main__':
    main()
