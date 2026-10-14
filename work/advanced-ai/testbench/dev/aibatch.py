"""One round of the AI scenario loop: check the claims, run both AIs on a batch, show what the advanced AI missed.

  .venv/bin/python work/advanced-ai/testbench/dev/aibatch.py N --rom ROM --payload PAYLOAD [--repeats 3] [--workers 2]
  .venv/bin/python work/advanced-ai/testbench/dev/aibatch.py --regress --rom ROM --payload PAYLOAD [--workers 2]

Ported from the Spanish workspace's tools/aibatch.py (dc8577c). Changes: the bench is bench/aibench.py, which takes
the ROM and its payload (an AI build, e.g. one dev/aibuild.py made); every saved name ends in _<ROM file name>; the
results and reports go to the bench's saved runs (RUNS/aibench/saved/).

N is a batch (bench/tests/ai_batches/batch_NN.py; 0 = the original set). The batches are written by an author who never
sees the AI (the Spanish tests/ai_batches/AUTHORING.md). A round runs aibench.py --check, then the advanced and the
current AI on the batch side by side (results advanced_bNN_<ROM>.json and current_bNN_<ROM>.json), and prints each
scenario the advanced AI did not pass with its actions, the key, and the options it weighed (kind, index, value from
its debug record), which is what a fix starts from. Writes batch_NN_<ROM>.md. --regress runs all scenarios once
(advanced_all_<ROM>.json) and lists every one that is not a pass.
"""
import argparse
import collections
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import aibench  # noqa: E402
import payload  # noqa: E402
from aidata import Data  # noqa: E402

PY = sys.executable
KINDS = {0: 'move', 1: 'switch', 2: 'item'}


def rom_suffix(rom):
    """'_' + the ROM's file name (aibench tags its work files the same way)."""
    return '_' + os.path.splitext(os.path.basename(rom))[0]


def bench(args):
    """bench/aibench.py with ARGS; the payload comes from ADVAI_PAYLOAD (payload.path_from exported it)."""
    return subprocess.run([PY, aibench.__file__] + args, capture_output=True, text=True)


def load(name):
    return json.load(open(os.path.join(aibench.BASELINES, name + '.json')))['results']


def option_names(d, sc, adv):
    """The advanced AI's weighed options, by name."""
    me = sc['enemy'][0]
    out = []
    for kind, idx, extra, value in adv.get('options', []):
        k = KINDS.get(kind, kind)
        if k == 'move':
            name = me['moves'][idx] if idx < len(me['moves']) else '?'
            if extra and sc.get('double'):
                name += '>%d' % extra
        elif k == 'switch':
            name = 'switch:' + (sc['enemy'][extra]['species'] if extra < len(sc['enemy']) else str(extra))
        else:
            name = 'item:' + d.item_name.get(extra, str(extra))
        out.append('%s=%d' % (name, value))
    return out


def summarize(d, chosen, adv_results, cur_results=None):
    by = collections.defaultdict(list)
    for x in adv_results:
        by[x['id']].append(x)
    cur = collections.defaultdict(list)
    for x in cur_results or []:
        cur[x['id']].append(x)
    points = {'pass': 1.0, 'ok': 0.5}
    lines, misses = [], []
    tot_a = tot_c = 0.0
    for sc in chosen:
        rs = by.get(sc['id'], [])
        sa = sum(points.get(aibench.grade(sc, x['action']), 0) for x in rs) / max(1, len(rs))
        cs = cur.get(sc['id'], [])
        sco = sum(points.get(aibench.grade(sc, x['action']), 0) for x in cs) / max(1, len(cs)) if cs else None
        tot_a += sa
        tot_c += sco or 0
        acts = collections.Counter('%s (%s)' % (x['action'], aibench.grade(sc, x['action'])) for x in rs)
        lines.append('| `%s` | %s | %.0f%% | %s |' % (sc['id'], sc['cat'], 100 * sa, '' if sco is None else '%.0f%%' % (100 * sco)))
        if sa < 1.0:
            adv = next((x['adv'] for x in rs if x.get('adv')), None) or {}
            misses.append('%s [%s] %s\n    took: %s\n    key: best %s ok %s bad %s\n    options: %s\n    fallback %s, failures %s' % (
                sc['id'], sc['cat'], sc['desc'], dict(acts), sc['expect']['best'], sc['expect']['ok'], sc['expect']['bad'],
                ', '.join(option_names(d, sc, adv)), adv.get('fallback'), sorted({f for x in rs for f in x.get('failures', [])})))
    n = max(1, len(chosen))
    head = 'advanced %.1f%%' % (100 * tot_a / n) + ('' if cur_results is None else ', current %.1f%%' % (100 * tot_c / n))
    return head, lines, misses


def round_(n, repeats, workers, rom):
    chk = bench(['--check', '--rom', rom])
    print(chk.stdout.strip().splitlines()[-1] if chk.stdout.strip() else chk.stderr[-2000:])
    if chk.returncode or 'check out' not in chk.stdout:
        sys.exit('fix the scenario checks first')
    tag = 'b%02d' % n + rom_suffix(rom)
    half = max(1, workers // 2)
    jobs = [['batch:%d' % n, '--rom', rom, '--advanced', '--repeats', str(repeats), '--workers', str(workers - half),
             '--save', 'advanced_' + tag],
            ['batch:%d' % n, '--rom', rom, '--repeats', str(repeats), '--workers', str(half), '--save', 'current_' + tag]]
    with ThreadPoolExecutor(2) as pool:
        outs = list(pool.map(bench, jobs))
    for o in outs:
        if o.returncode:
            print(o.stdout[-1500:], o.stderr[-1500:])
    d = Data(rom)
    chosen = aibench.select(['batch:%d' % n], aibench.scenarios())
    head, lines, misses = summarize(d, chosen, load('advanced_' + tag), load('current_' + tag))
    health = [l for l in outs[0].stdout.splitlines() if l.startswith(('advanced AI', '      ', 'TOTAL'))]
    md = ['# Batch %d: %d scenarios' % (n, len(chosen)), '', head, ''] + health + ['', '| Scenario | Category | Advanced | Current |',
                                                                              '|---|---|---|---|'] + lines
    if misses:
        md += ['', '## Not passed by the advanced AI', '', '```'] + misses + ['```']
    os.makedirs(aibench.BASELINES, exist_ok=True)
    open(os.path.join(aibench.BASELINES, 'batch_%02d%s.md' % (n, rom_suffix(rom))), 'w').write('\n'.join(md) + '\n')
    print(head)
    print('\n'.join(health))
    print('\n'.join(misses) if misses else 'the advanced AI passed every scenario of the batch')


def regress(workers, rom):
    name = 'advanced_all' + rom_suffix(rom)
    o = bench(['--rom', rom, '--advanced', '--repeats', '1', '--workers', str(workers), '--save', name])
    print('\n'.join(l for l in o.stdout.splitlines() if l.startswith(('TOTAL', 'advanced AI', '      ')) or ' runs in ' in l))
    d = Data(rom)
    head, lines, misses = summarize(d, aibench.scenarios(), load(name))
    print(head)
    print('\n'.join(misses) if misses else 'every scenario passed')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch', nargs='?', type=int)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--workers', type=int, default=2, help='emulator processes (lib/emupool.py caps the machine)')
    ap.add_argument('--regress', action='store_true')
    ap.add_argument('--rom', required=True, help='the AI build to bench (e.g. a dev/aibuild.py ROM)')
    ap.add_argument('--payload', help="its payload.json (default: ADVAI_PAYLOAD)")
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for aibench.py
    if a.regress:
        regress(a.workers, a.rom)
    elif a.batch is not None:
        round_(a.batch, a.repeats, a.workers, a.rom)
    else:
        ap.error('give a batch number or --regress')


if __name__ == '__main__':
    main()
