"""src/ids.h, the move, ability and item ids the AI names, frozen from the Spanish build's generation.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_ids*.py'
    .venv/bin/python work/advanced-ai/testbench/unit/test_ids.py --write      rewrite src/IDS.md

Checks:
- every MV_/AB_/IT_ name in ids.h is our name for its id: the English of that id in our text banks (0739 moves,
  0711 abilities, 0219 items), or the glossary's full name for the bank's Chinese. The Spanish generator resolved
  the names to ids the same way, through its own English banks;
- src/IDS.md lists exactly ids.h's ids and lists (its names are for the reader; `--write` refreshes them);
- ids.h equals a fresh Spanish generation: `ai_ids_header()` of the Spanish build.py at commit dc8577c, archived with
  `git archive` into a temporary directory. Importing that build.py links the Spanish AI, so it needs the Spanish
  workspace repository, named by ADVAI_ES_REPO=/path/to/spanish/repo (no default), with its ROMs
  work_es/rom/origin_en.nds and origin_cn.nds (linked into the archive), and the pinned toolchain. It skips without
  them.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[2]
REPO = AI_DIR.parents[1]
IDS_H = AI_DIR / 'src' / 'ids.h'
IDS_MD = AI_DIR / 'src' / 'IDS.md'
BANKS = REPO / 'work' / 'translate' / 'banks' / 'a027'
GLOSSARY = REPO / 'work' / 'glossary'
ES_REPO = Path(os.environ['ADVAI_ES_REPO']) if os.environ.get('ADVAI_ES_REPO') else None
ES_COMMIT = 'dc8577c'
ES_ROMS = ('origin_en.nds', 'origin_cn.nds')
# prefix -> (title, text bank of its names, glossary file)
KINDS = {'MV': ('Moves', '0739', 'moves'), 'AB': ('Abilities', '0711', 'abilities'), 'IT': ('Items', '0219', 'items')}
LISTS = {'IS_BALL_MOVE': 'Ball and bomb moves (Bulletproof blocks them; flag bit 30 of the move record)',
         'IS_STREAK_MOVE': 'Moves after which the engine\'s Protect handler keeps the streak'}


def header_lines(text):
    """ids.h without its leading comment."""
    lines = text.splitlines()
    end = next(i for i, line in enumerate(lines) if line.rstrip().endswith('*/'))
    return lines[end + 1:]


def parse_ids(text):
    """([(prefix, name, id)] in file order, {list macro: [ids]}) of ids.h."""
    defines, lists = [], {}
    for line in header_lines(text):
        m = re.match(r'#define (MV|AB|IT)_(\w+) (\d+)$', line)
        if m:
            defines.append((m.group(1), m.group(2), int(m.group(3))))
            continue
        m = re.match(r'#define (IS_\w+)\(id\) \((.*)\)$', line)
        if m:
            lists[m.group(1)] = [int(x) for x in re.findall(r'\(id\) == (\d+)', m.group(2))]
            continue
        raise AssertionError('unexpected line in ids.h: %r' % line)
    return defines, lists


def bank(number):
    return {s['id']: s for s in json.loads((BANKS / ('%s.json' % number)).read_text())['strings']}


def glossary(name):
    return {zh: v['en'] for zh, v in json.loads((GLOSSARY / ('%s.json' % name)).read_text()).items() if v.get('en')}


def norm(name):
    return re.sub(r'[^A-Z0-9]', '', (name or '').upper().replace('É', 'E'))


def names():
    """{prefix: {id: (Chinese, our English, full name or '')}} from the text banks; the full name is the glossary's
    for the Chinese, else the one a short bank name notes ("abbreviated from ...")."""
    out = {}
    for prefix, (_, number, gloss) in KINDS.items():
        full = glossary(gloss)
        out[prefix] = {}
        for i, s in bank(number).items():
            m = re.search(r'abbreviated from (.+?)\s*$', s.get('notes') or '')
            out[prefix][i] = (s['zh'], s['en'], full.get(s['zh']) or (m.group(1) if m else ''))
    return out


def ids_table():
    """The text of src/IDS.md."""
    defines, lists = parse_ids(IDS_H.read_text())
    named = names()
    out = ['# AI ids', '',
           'Every id in [ids.h](ids.h), named through our text banks: the Chinese is the ROM\'s text, the English our',
           'translation of it (bank 0739 moves, 0711 abilities, 0219 items), and "Full name" the glossary\'s name where',
           'the bank uses a short one. `testbench/unit/test_ids.py` checks that every define names its id and that this',
           'table lists exactly the ids in ids.h; `test_ids.py --write` rewrites it. Do not edit by hand.', '']
    for prefix, (title, number, _) in KINDS.items():
        by_name = {}
        for i, (_, en, _) in named[prefix].items():
            by_name.setdefault(norm(en), []).append(i)
        out += ['## %s' % title, '', '| Define | Id | Chinese | English | Full name | Note |', '|---|---|---|---|---|---|']
        for p, name, i in defines:
            if p != prefix:
                continue
            zh, en, full = named[prefix][i]
            same = [j for j in by_name[norm(en)] if j != i]
            note = 'same name as id %s' % ', '.join(map(str, same)) if same else ''
            out.append('| `%s_%s` | %d | %s | %s | %s | %s |' % (prefix, name, i, zh, en, full if full != en else '',
                                                                 note))
        out.append('')
    for macro, title in LISTS.items():
        out += ['## %s' % title, '', '`%s`:' % macro, '', '| Id | Chinese | English |', '|---|---|---|']
        out += ['| %d | %s | %s |' % (i, named['MV'][i][0], named['MV'][i][1]) for i in lists[macro]]
        out.append('')
    return '\n'.join(out)


class IdsHeader(unittest.TestCase):
    def test_names_match_their_ids(self):
        defines, _ = parse_ids(IDS_H.read_text())
        named = names()
        self.assertEqual(len(defines), 366)
        for prefix, name, i in defines:
            with self.subTest(define='%s_%s' % (prefix, name)):
                zh, en, full = named[prefix][i]
                self.assertIn(norm(name), {norm(en), norm(full)}, 'id %d is %s / %s / %s' % (i, zh, en, full))

    def test_ids_md_lists_the_header(self):
        defines, lists = parse_ids(IDS_H.read_text())
        md = IDS_MD.read_text()
        rows = [(m.group(1), m.group(2), int(m.group(3))) for m in
                re.finditer(r'^\| `(MV|AB|IT)_(\w+)` \| (\d+) \|', md, re.M)]
        self.assertEqual(sorted(rows), sorted(defines), 'src/IDS.md is stale: run test_ids.py --write')
        for macro in LISTS:
            part = md.split('`%s`:' % macro)[1].split('\n## ')[0]
            self.assertEqual([int(x) for x in re.findall(r'^\| (\d+) \|', part, re.M)], lists[macro], macro)


class SpanishGeneration(unittest.TestCase):
    def test_equals_spanish_generation(self):
        if not ES_REPO:
            self.skipTest('ADVAI_ES_REPO is not set: point it at the Spanish workspace repository')
        roms = [ES_REPO / 'work_es' / 'rom' / n for n in ES_ROMS]
        if not (ES_REPO / '.git').exists() or not all(p.is_file() for p in roms):
            self.skipTest('needs the Spanish workspace repository with work_es/rom/%s at %s (set ADVAI_ES_REPO)'
                          % (' and '.join(ES_ROMS), ES_REPO))
        if subprocess.run(['arm-none-eabi-gcc', '-dumpfullversion'], capture_output=True, text=True).stdout.strip() \
                != '16.2.0':
            self.skipTest('needs arm-none-eabi-gcc 16.2.0 (importing the Spanish build.py links its AI)')
        with tempfile.TemporaryDirectory() as t:
            spec = importlib.util.spec_from_file_location('advai_build', AI_DIR / 'builder' / 'build.py')
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            builder.es_archive(ES_REPO, t, ('work_es/tools', 'work_es/text', 'work_es/glossary'), ES_COMMIT)
            (Path(t) / 'work_es' / 'rom').mkdir()
            for p in roms:
                (Path(t) / 'work_es' / 'rom' / p.name).symlink_to(p)
            tools = Path(t) / 'work_es' / 'tools'
            proc = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); '
                                   'import build; sys.stdout.write(build.ai_ids_header())', str(tools)],
                                  capture_output=True, text=True, cwd=t)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        generated = proc.stdout.splitlines()
        self.assertTrue(generated[0].startswith('/* Generated by tools/build.py'), generated[0])
        self.assertEqual(header_lines(IDS_H.read_text()), generated[1:])


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        IDS_MD.write_text(ids_table())
        print('wrote %s' % IDS_MD)
    else:
        unittest.main()
