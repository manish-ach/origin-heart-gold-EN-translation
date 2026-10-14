"""Parity of the advanced AI's logged DS decisions (adv-vs-orig aivsai logs) with the host build's in the same replayed
positions, from `sim validate --ai` with VAL_PARITY=FILE (Spanish qa/aivsai/rc33_A0_PARITY.md).

  .venv/bin/python work/advanced-ai/testbench/sim/parity.py RUN.jsonl [--alt RUN2.jsonl ...] [--val VAL.jsonl] [--roll ROLL.jsonl] [--tsv OUT]

RUN: a VAL_PARITY file (SIM_FS=2 SIM_FS_SIDE=1, the DS's foresight); --alt: the same logs with other foresight luck
(VAL_SEED=k) or none (SIM_FS unset): a disagreement one of them resolves is 'luck'; --val: validate's own output (its
drift findings); --roll: a VAL_ROLL file, which prices each disagreement (host win rate - DS win rate from that
position, the original-AI model as the foe). Classes, in order: bench (a Pokemon fainted on one side only, from the
log's faint lines), benchhp (a benched Pokemon's HP differs from the DS's last shown HP, Regenerator skipped), belch
(the simulator lets Belch be chosen before a Berry is eaten), sleep (validate does not know the DS's sleep counter),
extra (the host chose an option the DS did not have, its list complete), luck, absent (the DS's choice is no option
on the host), drift (validate's drift findings that turn), tie (either side's margin <= 20), values (the rest)."""
import argparse, collections, json, math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401

WORK = tbpaths.WORK

def load(p, alive=None):
    out = {}
    for line in open(p):
        r = json.loads(line)
        r['full'] = r['path'] if os.path.isabs(r['path']) else os.path.normpath(os.path.join(WORK, r['path']))
        out[(os.path.basename(r['path']), r['turn'], r['side'], r['kind'])] = r
    return out

def top(opts):
    return tuple(max(opts, key=lambda o: o[2])[:2]) if opts else None

def val(opts, key):
    for o in opts:
        if tuple(o[:2]) == key:
            return o[2]
    return None

def ds_alive(path, turn, _cache={}):  # noqa: B006  (a per-process memo)
    """[player side, trainer side] Pokemon not fainted at the start of turn `turn`, from the DS log (6 each)."""
    if path not in _cache:
        seen, t, n = {}, 0, [0, 0]
        hdr = open(path).readline()
        import re
        m = re.search(r'ADVANCED (\d+) vs ORIGINAL (\d+)', hdr)
        size = [int(m.group(2)), int(m.group(1))] if m else [6, 6]
        for line in open(path):
            if line.startswith('--- Turn '):
                t = int(line.split()[2]); seen[t] = (size[0] - n[0], size[1] - n[1])
            elif line.rstrip().endswith(' fainted') and line.lstrip().startswith(('ADVANCED', 'ORIGINAL')):
                n[line.lstrip().startswith('ADVANCED')] += 1
        _cache[path] = seen
    return _cache[path].get(turn)

def ds_bench_hp(path, _cache={}):  # noqa: B006  (a per-process memo)
    """{turn: {(side, set): hp}}: each member's HP at the last turn header that showed it active, up to that turn."""
    if path in _cache:
        return _cache[path]
    import re
    teams, side, out, last, t, regen = [[], []], None, {}, {}, 0, set()
    for line in open(path):
        if line.startswith('ADVANCED team'): side = 1; continue
        if line.startswith('ORIGINAL team'): side = 0; continue
        if side is not None and line.startswith('  ') and ' L100 ' in line or (side is not None and re.match(r'  \S.* L\d+ ', line)):
            teams[side].append(line.split(' L')[0].strip())
            if 'Regenerator' in line:
                regen.add((side, len(teams[side]) - 1))
            continue
        if line.startswith('==='): side = None
        if line.startswith('--- Turn '):
            t = int(line.split()[2]); out[t] = dict(last); continue
        m = re.match(r'  (ADVANCED|ORIGINAL)  (.+?)\s+(\d+)/(\d+) ', line)
        if m and t:
            sd = m.group(1) == 'ADVANCED'; nm = m.group(2).strip()
            if teams[sd].count(nm) == 1 and (sd, teams[sd].index(nm)) not in regen:
                last[sd, teams[sd].index(nm)] = int(m.group(3)); out[t][sd, teams[sd].index(nm)] = int(m.group(3))
    _cache[path] = out
    return out

def bench_hp_drift(r):
    """the AI's bench members (side 1) whose host HP differs from the DS's last shown HP by more than 10 HP"""
    if 'party' not in r or 'full' not in r:
        return []
    known = ds_bench_hp(r['full']).get(r['turn'], {})
    bad = []
    for sd in (0, 1):
        for st, hp in r['party'][sd][1:]:
            if (sd, st) in known and hp > 0 and abs(known[sd, st] - hp) > 10:
                bad.append((sd, st, known[sd, st], hp))
    return bad

def ds_asleep(path, turn, _cache={}):  # noqa: B006  (a per-process memo)
    """1 when either Pokemon on the field is asleep at turn `turn`'s start in the DS log"""
    if path not in _cache:
        out, t = {}, 0
        for line in open(path):
            if line.startswith('--- Turn '):
                t = int(line.split()[2]); out[t] = 0
            elif t and line.startswith(('  ADVANCED  ', '  ORIGINAL  ')) and '/' in line and line.rstrip().endswith(('SLP',)) or (t and ' SLP' in line and '/' in line and '->' not in line):
                out[t] = 1
        _cache[path] = out
    return _cache[path].get(turn, 0)

def classify(r, alts, drift):
    lt, st = tuple(r['log'][0][:2]), top(r['sim'])
    if r['kind'] == 'r':
        return 'agree' if lt == st else 'repl'
    if lt == st:
        return 'agree'
    if 'alive' in r and 'full' in r and ds_alive(r['full'], r['turn']) not in (None, tuple(r['alive'])):
        return 'bench'                       # a Pokemon fainted on one side and not on the other: a replay drift
    if bench_hp_drift(r):
        return 'benchhp'                     # a benched Pokemon's HP differs between the replay and the DS
    if st == (0, 562) and val(r['log'], st) is None:
        return 'belch'                       # the simulator lets Belch be chosen before a Berry is eaten; the DS does not
    if 'full' in r and ds_asleep(r['full'], r['turn']):
        return 'sleep'                       # the replay's sleep counter is not the DS's (validate draws sleep as a hazard)
    if r.get('more') == 0 and val(r['log'], st) is None:
        return 'extra'                       # the host's choice is an option the DS did not have (its list is complete)
    if any(a and top(a['sim']) == lt for a in alts):
        return 'luck'
    hv = val(r['sim'], lt)
    if hv is None:
        return 'absent'                      # the DS's choice is not an option on the host (veto or legality)
    dgap = r['log'][0][2] - (r['log'][1][2] if len(r['log']) > 1 else r['log'][0][2])
    hgap = max(o[2] for o in r['sim']) - hv
    if drift:
        return 'drift'
    if hgap <= 20 or dgap <= 20:
        return 'tie'
    return 'values'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('--alt', action='append', default=[])
    ap.add_argument('--val')
    ap.add_argument('--tsv')
    ap.add_argument('--roll')
    a = ap.parse_args()
    run = load(a.run)
    alts = [load(p) for p in a.alt]
    drift = collections.defaultdict(set)
    if a.val:
        paths = {}
        for line in open(a.val):
            r = json.loads(line)
            if 'game' in r:
                paths[r['game']] = os.path.basename(r['path'])
            elif r.get('cat') in ('drift', 'maxhp') and 'g' in r:
                drift[paths.get(r['g']), r['t']].add(r.get('what', r['cat']))
    tally = collections.Counter()
    rows = []
    for k, r in run.items():
        c = classify(r, [x.get(k) for x in alts], drift.get((k[0], k[1])))
        tally[r['kind'], c] += 1
        if c != 'agree':
            rows.append((k, c, r))
    nc = sum(v for (kd, c), v in tally.items() if kd == 'c')
    nr = sum(v for (kd, c), v in tally.items() if kd == 'r')
    print('decisions %d: agree %d (%.1f%%)' % (nc, tally['c', 'agree'], 100 * tally['c', 'agree'] / nc))
    for (kd, c), v in sorted(tally.items(), key=lambda x: -x[1]):
        if kd == 'c' and c != 'agree':
            print('  %-8s %4d (%.1f%%)' % (c, v, 100 * v / nc))
    print('replacements %d: agree %d (%.1f%%)' % (nr, tally['r', 'agree'], 100 * tally['r', 'agree'] / max(nr, 1)))
    if a.roll:
        price(run, alts, drift, load(a.roll), nc)
    if a.tsv:
        with open(a.tsv, 'w') as f:
            for k, c, r in sorted(rows):
                f.write('%s\t%d\t%s\t%s\tfoe=%s fs=%s\tlog=%s\tsim=%s\n' % (k[0], k[1], k[3], c, r.get('foe'), r.get('fs'),
                        json.dumps(r['log']), json.dumps(sorted(r['sim'], key=lambda o: -o[2])[:6])))

def price(run, alts, drift, roll, nc):
    """each class's summed delta (host - DS win rate) over the priced disagreements, in games"""
    by = collections.defaultdict(list)
    for k, r in run.items():
        x = roll.get(k)
        if r['kind'] != 'c' or not x or 'roll' not in x:
            continue
        c = classify(r, [y.get(k) for y in alts], drift.get((k[0], k[1])))
        if c != 'agree':
            by[c].append(x['roll'][1] - x['roll'][0])
    print('priced (games, host - DS):')
    for c, ds in sorted(by.items(), key=lambda x: -sum(x[1])):
        n = len(ds); m = sum(ds) / n; sd = math.sqrt(sum((d - m) ** 2 for d in ds) / max(n - 1, 1))
        print('  %-8s n %4d  sum %+6.2f  mean %+.3f (SE %.3f)' % (c, n, sum(ds), m, sd / math.sqrt(n)))


if __name__ == '__main__':
    main()
