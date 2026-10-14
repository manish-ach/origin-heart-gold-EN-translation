"""DS time per decision: cycles per simulated turn from lathumb.py's counts (per playout class: policy, depth, leaf),
times each variant's simulated turns per decision (its .stats). 67.03 MHz, every access hitting (ideal).

  ds_cost.py classes THUMB.jsonl ...            cycles and instructions per turn, per class
  ds_cost.py variants THUMB.jsonl ... -- FOE:NAME:POL:DEPTH:EVAL ...
"""
import collections, json, os, statistics, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'lib'))
from tbpaths import RUNS  # noqa: E402
HZ = 67.03e6
POL = {'greedy': 0, 'gswitch': 1, 'gko': 2, 'gsw2': 3}
EVAL = {'hp': 0, 'count': 1, 'mix': 2, 'race': 3}


def classes(paths):
    acc = collections.defaultdict(lambda: {'cyc': 0, 'ins': 0, 'turns': 0, 'calls': 0, 'n': 0, 'same': 0, 'stack': 0,
                                           'per_turn': [], 'fn': collections.Counter()})
    for p in paths:
        for line in open(p):
            if not line.startswith('{'):
                continue
            r = json.loads(line)
            key = (r['pol'], r['depth'], r['eval'] if r['depth'] else 0)
            a = acc[key]
            a['cyc'] += r['cycles_ideal']; a['ins'] += r['thumb']; a['turns'] += r['turns']; a['calls'] += r['calls']
            a['n'] += 1; a['same'] += r['same_as_host']; a['stack'] = max(a['stack'], r['stack'])
            a['per_turn'].append(r['cycles_ideal'] / max(1, r['turns']))
            for fn, k in r['top']:
                a['fn'][fn] += k
    return acc


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def main():
    argv = sys.argv[1:]
    mode = argv.pop(0)
    specs = []
    if '--' in argv:
        i = argv.index('--')
        argv, specs = argv[:i], argv[i + 1:]
    acc = classes(argv)
    if mode == 'classes':
        print('pol depth eval  decisions same  ins/turn  cyc/turn  CPI  per-turn cycles p10/med/p90  calls/turn  stack')
        for k in sorted(acc):
            a = acc[k]
            pt = a['per_turn']
            print('%s %d %d  %3d %3d  %8.0f  %8.0f  %.2f  %7.0f/%7.0f/%7.0f  %.2f  %d' % (
                ['greedy', 'gswitch', 'gko', 'gsw2'][k[0]], k[1], k[2], a['n'], a['same'], a['ins'] / a['turns'], a['cyc'] / a['turns'],
                a['cyc'] / a['ins'], pct(pt, 0.1), statistics.median(pt), pct(pt, 0.9), a['calls'] / a['turns'], a['stack']))
            print('      top functions (share of the counted top-12 per decision):',
                  ', '.join('%s %.0f%%' % (f, 100 * c / a['ins']) for f, c in a['fn'].most_common(8)))
        return
    print('variant                    class          cyc/turn  ms per decision med/p90/max   (turns med/p90/max)')
    for s in specs:
        foe, name, pol, depth, ev = s.split(':')
        key = (POL[pol], int(depth), EVAL[ev] if int(depth) else 0)
        a = acc[key]
        cpt = a['cyc'] / a['turns']
        turns = [int(l.split()[4]) for l in open(os.path.join(RUNS, 'sim', 'la', foe, name + '.stats'))]
        ms = [t * cpt / HZ * 1000 for t in turns]
        print('%-26s %-14s %8.0f  %7.0f/%7.0f/%7.0f   (%d/%d/%d)' % (
            name, '%s d%s %s' % (pol, depth, ev if int(depth) else '-'), cpt, statistics.median(ms), pct(ms, 0.9), max(ms),
            statistics.median(turns), pct(turns, 0.9), max(turns)))


if __name__ == '__main__':
    main()
