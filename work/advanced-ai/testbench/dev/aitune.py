"""Self-play tuning of the advanced AI's judgment constants: the bench side.

A build with src/tune.h keeps the tunable constants in a table in arm9's ITCM block (g_tune, section .itcm.tune:
magic "TUNE", version, count, then one copy of the values per side, the trainer side's first). versus/aivsai.py writes
a vector into each side's copy after every state load (game 'tune'), so one ROM plays any two settings against each
other. This tool plans the matches, runs them in self-play and scores them.

  .venv/bin/python work/advanced-ai/testbench/dev/aitune.py COMMAND ...
  aitune.py table --rom ROM [--payload P]        # the ROM's table against tune.h
  aitune.py screen --name NAME --rom ROM --payload P [--knobs A,B,..] [--pairs 200] [--design h8|h4] [--max-blocks N]
                   [--dry-run]
  aitune.py confirm --name NAME --set FILE --rom ROM --payload P [--pairs 50] [--dry-run]
  aitune.py export --set FILE --src DIR --out NEWDIR    # the set as the defaults of a copy of DIR, for dev/aibuild.py
  aitune.py accept-sides --rom ROM --payload P   # harness acceptance: each side reads its own copy
  aitune.py accept-aa --rom ROM --payload P [--pairs 20]   # harness acceptance: defaults on both sides, mirror_check
  aitune.py seed [--check N ...] [--reserve LABEL]
  aitune.py --selftest                           # dev/tests/test_aitune.py (no emulator)
Common options: --rom (an AI build: a dev/aibuild.py ROM), --payload (its payload.json; default ADVAI_PAYLOAD),
--tune-h (default src/tune.h), --workers (2), --ledger (RUNS/aivsai/tune/ledger.jsonl), --out-dir (RUNS/aivsai/tune:
reports, candidates, battle logs).

Ported from the Spanish workspace's tools/aitune.py (dc8577c). Changes: the seed bookkeeping (round and held-out
seeds, the ledger) moved to lib/seeds.py, which versus/ shares; paths under RUNS; the ROM and payload are arguments;
the workers default to 2 (the emulator budget); export's next step names dev/aibuild.py.

screen: the mirrored Hadamard screen. Block i plays X = defaults + s*step against Y = defaults - s*step, where
s holds each knob's column in row i of the Sylvester matrix (entry (i, j) = (-1)^popcount(i & j)). h8 puts the
knobs on columns 1, 2, 3, 4, 7 (then 5, 6) and h4 on 1, 2, 3, 0. The columns left free (0, 5 and 6 with five
knobs) carry no constant: they are the checks. Each block draws a fresh seed (SystemRandom), refused when it is
held out, a round seed or already in the ledger. Teams are mixed, six a side at level 100, and each scenario is
played twice with the teams swapped. X plays the trainer side in odd scenarios and the player side in even ones.
Pair score: +1 when X won both games, -1 when Y won both, 0 for a split. The estimate is
E_j = (1/B) sum_i H[i][j] m_i, where m_i is block i's mean pair score; with equal blocks this is the design's
(1/P) sum_i H[i][j] S_i. The "+" win rate is 50% + E_j / 2. A knob is kept in its winning direction when
|E_j| >= 0.12, and only when every check column is within 0.10. Games that did not end normally are excluded,
and more than 3% excluded in one block stops the pass. Every game goes into the ledger as it finishes, so
running the same command again resumes a stopped pass.
ROLL_MARGIN is one knob for both rolls: MY_ROLL = 925 - m and THEIR_ROLL = 925 + m.
"""
import logging
logging.getLogger().addHandler(logging.NullHandler())   # this Python's hashlib logs a harmless blake2 traceback on import
import argparse  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from collections import namedtuple  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aivsai  # noqa: E402
import payload  # noqa: E402
from seeds import HOLDOUT, ROUND_SEEDS, TUNE_DIR, Ledger, fresh_seed, holdout_seeds, refusal  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = tbpaths.WORK
TUNE_H = os.path.join(tbpaths.ADV, 'src', 'tune.h')
MIRROR_CHECK = os.path.join(tbpaths.TESTBENCH, 'versus', 'mirror_check.py')
ROLL_CENTER = 925                                # the 85-100 damage roll's average, per-mille
TEAMS, LEVEL, SIZES = 'mixed', 100, (6, 6)
KEEP, CHECK, MAX_EXCLUDED = 0.12, 0.10, 0.03     # keep rule |E| >= KEEP; checks |E| <= CHECK; excluded share
NULL_VAR = 0.26                                  # pair-score variance under no effect (26% of pairs split)
DESIGNS = {'h8': (8, (1, 2, 3, 4, 7, 5, 6)), 'h4': (4, (1, 2, 3, 0))}    # blocks, knob columns in order
DEFAULT_KNOBS = ('TEMPO', 'WORTH_BASE', 'KO_TEMPO', 'ROLL_MARGIN', 'SWITCH_COST')
WINNER_SIDE = {'advanced': 'trainer', 'original': 'player'}   # aivsai's winner names by side in self-play
SIDES = aivsai.TUNE_SIDES                                     # ('trainer', 'player')
SIDE_TEST = ('SWITCH_COST', 1000)                # accept-sides: the switch options of that side drop by 1000 - default
REPLACE_TEST = 'WORTH_BASE'                      # accept-sides: a constant ai_replace reads (worth), set to its hi
SIDE_TOLERANCE = 2


# --- the registry: tune.h's TUNE_LIST
Entry = namedtuple('Entry', 'name default lo hi step')


class RegistryError(ValueError):
    pass


def _blank_comments(text):
    """text with every C comment turned into spaces (newlines kept), so offsets still match text."""
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)


def _int(tok, what):
    t = re.sub(r'[uUlL]+$', '', tok.strip())
    try:
        return int(t, 0)
    except ValueError:
        raise RegistryError('%s: %r is not an integer literal' % (what, tok.strip())) from None


class Registry:
    """tune.h's TUNE_VERSION and TUNE_LIST(X) entries X(NAME, default, lo, hi, step), in table order."""

    def __init__(self, text):
        self.text = text
        t = _blank_comments(text)
        m = re.search(r'^[ \t]*#[ \t]*define[ \t]+TUNE_VERSION[ \t]+(\S+)', t, re.M)
        if not m:
            raise RegistryError('no #define TUNE_VERSION')
        self.version = _int(m.group(1), 'TUNE_VERSION')
        m = re.search(r'^[ \t]*#[ \t]*define[ \t]+TUNE_LIST[ \t]*\([ \t]*(\w+)[ \t]*\)', t, re.M)
        if not m:
            raise RegistryError('no #define TUNE_LIST(X)')
        param, start = re.escape(m.group(1)), m.end()
        end = start
        for line in t[start:].split('\n'):           # the macro runs to the first line without a final backslash
            end += len(line) + 1
            if not line.rstrip().endswith('\\'):
                break
        body = t[start:end]
        calls = re.findall(r'\b%s[ \t]*\(' % param, body)
        found = list(re.finditer(r'\b%s[ \t]*\(\s*(\w+)\s*,([^,()]*),([^,()]*),([^,()]*),([^,()]*)\)' % param, body))
        if len(found) != len(calls):
            raise RegistryError('%d of the %d TUNE_LIST entries are not NAME, default, lo, hi, step with integer '
                                'literals' % (len(calls) - len(found), len(calls)))
        self.entries, self.spans = [], {}
        for f in found:
            name = f.group(1)
            self.entries.append(Entry(name, *(_int(f.group(k), '%s field %d' % (name, k - 1)) for k in range(2, 6))))
            self.spans[name] = (start + f.start(2), start + f.end(2))      # the default, in text
        self.index = {e.name: i for i, e in enumerate(self.entries)}
        if not self.entries:
            raise RegistryError('TUNE_LIST has no entries')
        if len(self.index) != len(self.entries):
            raise RegistryError('a name appears twice in TUNE_LIST')
        if len(self.entries) > aivsai.TUNE_MAX:
            raise RegistryError('%d entries, more than %d' % (len(self.entries), aivsai.TUNE_MAX))
        for e in self.entries:
            if not (0 <= e.lo <= e.default <= e.hi <= 0xFFFF and e.step >= 1):
                raise RegistryError('%s: needs 0 <= lo <= default <= hi <= 65535 and step >= 1, has %d, %d, %d, %d'
                                    % (e.name, e.default, e.lo, e.hi, e.step))
        if {'MY_ROLL', 'THEIR_ROLL'} <= set(self.index) and self.entry('MY_ROLL').hi >= self.entry('THEIR_ROLL').lo:
            raise RegistryError('the ranges of MY_ROLL and THEIR_ROLL meet (the AI compares a roll with MY_ROLL)')

    @classmethod
    def load(cls, path):
        with open(path, encoding='utf-8') as f:
            return cls(f.read())

    @property
    def names(self):
        return [e.name for e in self.entries]

    @property
    def defaults(self):
        return [e.default for e in self.entries]

    def entry(self, name):
        if name not in self.index:
            raise RegistryError('unknown constant %s (tune.h has %s)' % (name, ', '.join(self.names)))
        return self.entries[self.index[name]]

    def knob(self, name):
        """An entry, or ROLL_MARGIN: m with MY_ROLL = 925 - m and THEIR_ROLL = 925 + m (defaults must be symmetric)."""
        if name != 'ROLL_MARGIN':
            return self.entry(name)
        my, th = self.entry('MY_ROLL'), self.entry('THEIR_ROLL')
        m = ROLL_CENTER - my.default
        if th.default != ROLL_CENTER + m:
            raise RegistryError('ROLL_MARGIN needs MY_ROLL and THEIR_ROLL symmetric about %d: they are %d and %d'
                                % (ROLL_CENTER, my.default, th.default))
        return Entry('ROLL_MARGIN', m, max(ROLL_CENTER - my.hi, th.lo - ROLL_CENTER, 1),
                     min(ROLL_CENTER - my.lo, th.hi - ROLL_CENTER), min(my.step, th.step))

    def vector(self, values, check=True):
        """The table's values with `values` ({knob: value}) in place of the defaults. check: every knob inside its
        range (accept-sides passes False for its out-of-range probe). MY_ROLL always stays below THEIR_ROLL."""
        v = list(self.defaults)
        if 'ROLL_MARGIN' in values and {'MY_ROLL', 'THEIR_ROLL'} & set(values):
            raise RegistryError('ROLL_MARGIN sets MY_ROLL and THEIR_ROLL: give one or the others')
        for name, x in values.items():
            if not isinstance(x, int) or isinstance(x, bool):
                raise RegistryError('%s: %r is not an integer' % (name, x))
            k = self.knob(name)
            if check and not k.lo <= x <= k.hi:
                raise RegistryError('%s %d is outside its range %d-%d' % (name, x, k.lo, k.hi))
            if name == 'ROLL_MARGIN':
                v[self.index['MY_ROLL']], v[self.index['THEIR_ROLL']] = ROLL_CENTER - x, ROLL_CENTER + x
            else:
                v[self.index[name]] = x
        bad = [n for n, x in zip(self.names, v) if not 0 <= x <= 0xFFFF]
        if bad:
            raise RegistryError('%s outside 0-65535' % ', '.join(bad))
        if {'MY_ROLL', 'THEIR_ROLL'} <= set(self.index) and v[self.index['MY_ROLL']] >= v[self.index['THEIR_ROLL']]:
            raise RegistryError('MY_ROLL must stay below THEIR_ROLL')
        return v

    def exported(self, values):
        """tune.h's text with `values` as the new defaults (ROLL_MARGIN as its two rolls), nothing else changed."""
        v = self.vector(values)
        text = self.text
        for e, x in sorted(zip(self.entries, v), key=lambda p: -self.spans[p[0].name][0]):   # last first: spans hold
            if x == e.default:
                continue
            a, b = self.spans[e.name]
            old, new = text[a:b], str(x)
            text = text[:a] + (new.rjust(len(old)) if len(new) < len(old) else (' ' if old[:1].isspace() else '') + new) + text[b:]
        out = Registry(text)
        assert out.defaults == v and [e[:1] + e[2:] for e in out.entries] == [e[:1] + e[2:] for e in self.entries]
        return text


def load_set(path):
    """A candidate set: a JSON object {knob: value}."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict) or not all(isinstance(v, int) and not isinstance(v, bool) for v in data.values()):
        raise SystemExit('%s: expected a JSON object of constant names and integers' % path)
    return data


# --- seeds and the ledger
def hadamard(n):
    """Sylvester's n x n Hadamard matrix: entry (i, j) = (-1)^popcount(i & j)."""
    return [[-1 if bin(i & j).count('1') % 2 else 1 for j in range(n)] for i in range(n)]


def screen_plan(reg, knobs, design):
    """The blocks of a screen: each block's signs, X and Y knob values and full vectors."""
    if design not in DESIGNS:
        raise RegistryError('design %s: one of %s' % (design, ', '.join(DESIGNS)))
    nb, order = DESIGNS[design]
    if len(set(knobs)) != len(knobs) or not 1 <= len(knobs) <= len(order):
        raise RegistryError('%s takes 1 to %d different knobs, got %s' % (design, len(order), ', '.join(knobs)))
    H, ks = hadamard(nb), [reg.knob(k) for k in knobs]
    cols = dict(zip(knobs, order))
    blocks = []
    for i in range(nb):
        signs = [H[i][cols[k.name]] for k in ks]
        xv = {k.name: k.default + s * k.step for k, s in zip(ks, signs)}
        yv = {k.name: k.default - s * k.step for k, s in zip(ks, signs)}
        blocks.append({'block': i, 'signs': signs, 'x_values': xv, 'y_values': yv, 'x': reg.vector(xv), 'y': reg.vector(yv)})
    return {'design': design, 'H': H, 'columns': cols, 'checks': [j for j in range(nb) if j not in cols.values()],
            'knobs': list(knobs), 'blocks': blocks}


def x_side_of(scenario):
    """X plays the trainer side in odd scenarios (s001, s003, ...) and the player side in even ones."""
    return 'trainer' if int(re.match(r's(\d+)', scenario).group(1)) % 2 else 'player'


def block_games(seed, pairs, x, y):
    """A block's games: `pairs` mixed scenarios of six against six at level 100 from `seed`, each played with the
    teams swapped, X on the side x_side_of gives in both games of a pair."""
    games = aivsai.games_of(aivsai.draw_scenarios(pairs, TEAMS, LEVEL, seed), True, SIZES)
    for g in games:
        g['x_side'] = x_side_of(g['scenario'])
        g['tune'] = {'trainer': x, 'player': y} if g['x_side'] == 'trainer' else {'trainer': y, 'player': x}
    return games


def game_record(name, block, game, res, x_id, y_id):
    """A ledger record of one game's result; 'excluded' says why it does not count (None when it does)."""
    want = {'trainer': x_id, 'player': y_id} if game['x_side'] == 'trainer' else {'trainer': y_id, 'player': x_id}
    fails = [f.get('ev') or '' for f in res.get('failures') or []]
    winner = WINNER_SIDE.get(res.get('winner'))
    why = next((f for f in fails if f.startswith('tune ')), None)
    if why is None and res.get('end') != 'normal':
        why = res.get('end') or 'no result'
    if why is None and res.get('tune') != want:
        why = 'tune ids %s, expected %s' % (res.get('tune'), want)
    if why is None and winner is None:
        why = 'no winner'
    return {'kind': 'game', 'name': name, 'block': block, 'scenario': game['scenario'], 'game': game['game'],
            'x_side': game['x_side'], 'x_id': x_id, 'y_id': y_id, 'winner': winner,
            'x_won': None if why else winner == game['x_side'], 'excluded': why, 'end': res.get('end'),
            'turns': res.get('turns'), 'seconds': res.get('seconds'), 'log': res.get('log'), 'failures': fails[:5]}


# --- statistics
def sign_p(plus, minus):
    """Two-sided sign test on the informative pairs."""
    n, k = plus + minus, min(plus, minus)
    return 1.0 if not n else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def block_stats(records):
    """One block's numbers from its game records (the newest per game)."""
    decided = [r for r in records if not r['excluded']]
    side = {s: [r for r in decided if r['x_side'] == s] for s in SIDES}
    pairs = {}
    for r in records:
        pairs.setdefault(r['scenario'], []).append(r)
    scores, unscored = [], 0
    for sc in sorted(pairs):
        p = pairs[sc]
        if len(p) != 2 or any(r['excluded'] for r in p):
            unscored += 1
            continue
        won = sum(r['x_won'] for r in p)
        scores.append(1 if won == 2 else -1 if won == 0 else 0)
    plus, minus = scores.count(1), scores.count(-1)
    return {'games': len(records), 'excluded': len(records) - len(decided), 'decided': len(decided),
            'x_wins': sum(r['x_won'] for r in decided),
            'by_side': {s: (sum(r['x_won'] for r in side[s]), len(side[s])) for s in SIDES},
            'scores': scores, 'plus': plus, 'minus': minus, 'split': scores.count(0), 'unscored': unscored,
            'p': sign_p(plus, minus),
            'reasons': sorted({r['excluded'] for r in records if r['excluded']})}


def estimates(H, block_scores):
    """{column: (E, SE)} for every column of H. E_j = (1/B) sum_i H[i][j] m_i, m_i the mean pair score of block i
    (the design's (1/P) sum_i H[i][j] S_i when all blocks have the same number of pairs). SE from the pooled
    within-block variance of the pair scores (NULL_VAR when there are too few pairs to estimate it)."""
    B = len(H)
    n = [len(s) for s in block_scores]
    if len(block_scores) != B or min(n) == 0:
        return None
    m = [sum(s) / len(s) for s in block_scores]
    P = sum(n)
    ss = sum((x - m[i]) ** 2 for i, s in enumerate(block_scores) for x in s)
    var = ss / (P - B) if P > B else NULL_VAR
    se = math.sqrt(var * sum(1 / k for k in n)) / B
    return {j: (sum(H[i][j] * m[i] for i in range(B)) / B, se) for j in range(B)}


def verdict(plan, reg, block_scores):
    """The screen's pooled result: rows per column, whether the checks pass, the kept knobs and the candidate."""
    est = estimates(plan['H'], block_scores)
    if est is None:
        return None
    by_col = {c: k for k, c in plan['columns'].items()}
    checks_ok = all(abs(est[c][0]) <= CHECK for c in plan['checks'])
    rows, kept, cand = [], {}, {}
    for j in range(len(plan['H'])):
        e, se = est[j]
        k = by_col.get(j)
        if k is None:
            note = 'check: %s (|E| <= %.2f)' % ('ok' if abs(e) <= CHECK else 'FAILED', CHECK)
        elif abs(e) >= KEEP and checks_ok:
            knob = reg.knob(k)
            sign = 1 if e > 0 else -1
            kept[k], cand[k] = sign, knob.default + sign * knob.step
            note = 'keep %s: %d -> %d' % ('+' if sign > 0 else '-', knob.default, cand[k])
        elif abs(e) >= KEEP:
            note = 'would keep %s, but a check failed' % ('+' if e > 0 else '-')
        else:
            note = 'no clear edge'
        rows.append({'column': j, 'knob': k, 'E': e, 'se': se, 'z': e / se if se else 0.0, 'plus_rate': 0.5 + e / 2, 'note': note})
    return {'rows': rows, 'checks_ok': checks_ok, 'kept': kept, 'candidate': cand,
            'pairs': sum(len(s) for s in block_scores)}


# --- running
def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Emulators:
    """aivsai's self-play machinery on one ROM: one pre-battle state per invocation, games on parallel workers."""

    def __init__(self, rom, workers):
        self.rom, self.workers, self.ready = rom, workers, None
        self.tag = 'aitune_' + os.path.splitext(os.path.basename(rom))[0]

    def run(self, games, log_dir, on_result):
        if self.ready is None:
            print('preparing the battle state for %s ...' % os.path.relpath(self.rom, WORK), flush=True)
            self.ready = aivsai.prepare(self.rom, False, self.tag)
        rom, state, save = self.ready
        os.makedirs(log_dir, exist_ok=True)
        return aivsai.run_parallel(games, rom, state, save, min(self.workers, len(games)), 'self', self.tag, log_dir,
                                   on_result)

    def close(self):
        if self.ready is not None:
            for p in (self.ready[0], os.path.join(aivsai.aibench.DSV_DIR, '%s.dsv' % self.tag)):
                if os.path.lexists(p):
                    os.remove(p)


def check_rom(rom, reg, dry_run=False):
    """The ROM's table must exist and match tune.h (names by count, version, defaults). Returns (sha1, table)."""
    if not os.path.exists(rom):
        if dry_run:
            print('note: %s does not exist (dry run goes on)' % rom)
            return None, None
        raise SystemExit('%s does not exist' % rom)
    try:
        t = aivsai.find_tune(rom)
    except aivsai.TuneError as e:
        raise SystemExit('%s: %s' % (rom, e)) from e
    problem = None
    if t is None:
        problem = '%s has no tuning table (a ROM without the advanced AI)' % os.path.relpath(rom, WORK)
    elif t.version != reg.version or t.defaults != reg.defaults:
        problem = '%s does not match tune.h: ROM version %d, defaults %s; tune.h version %d, defaults %s' % (
            os.path.relpath(rom, WORK), t.version, t.defaults, reg.version, reg.defaults)
    if problem and not dry_run:
        raise SystemExit(problem)
    if problem:
        print('note: ' + problem + ' (dry run goes on)')
    return sha1_file(rom), t


def describe(values):
    return ', '.join('%s %d' % (k, v) + (' (rolls %d/%d)' % (ROLL_CENTER - v, ROLL_CENTER + v) if k == 'ROLL_MARGIN' else '')
                     for k, v in values.items()) or 'defaults'


def block_lines(spec, b, rec, st, total):
    signs = ' '.join('+' if s > 0 else '-' for s in b['signs']) if b.get('signs') else None
    out = ['block %d of %d, seed %d: X %s vs Y %s%s' % (b['block'] + 1, total, rec['seed'], rec['x_id'], rec['y_id'],
                                                       ' (signs %s)' % signs if signs else ''),
           '  X: %s' % describe(b['x_values']), '  Y: %s' % describe(b['y_values'])]
    if st is None:
        return out
    pct = lambda a, n: '%.1f%%' % (100.0 * a / n) if n else '-'  # noqa: E731
    out.append('  games %d, excluded %d (%s)%s; X won %d of %d decided (%s): %d of %d as trainer side, %d of %d as player side'
               % (st['games'], st['excluded'], pct(st['excluded'], st['games']),
                  ' [%s]' % '; '.join(st['reasons']) if st['reasons'] else '', st['x_wins'], st['decided'],
                  pct(st['x_wins'], st['decided']), st['by_side']['trainer'][0], st['by_side']['trainer'][1],
                  st['by_side']['player'][0], st['by_side']['player'][1]))
    out.append('  pairs %d: X won both %d, Y won both %d, split %d, unscored %d; sign test p = %.3f'
               % (len(st['scores']) + st['unscored'], st['plus'], st['minus'], st['split'], st['unscored'], st['p']))
    return out


def run_pass(spec, ledger, runner, out_dir, replay_excluded=False, max_blocks=None, dry_run=False, log=print):
    """Play (or resume) a pass: spec has 'name', 'identity' (what makes it the same pass), 'pairs' per block,
    and 'blocks' ([{block, x, y, signs, x_values, y_values}]). Returns {'status': 'done' | 'partial' |
    'stopped', 'stats': {block: stats}, 'lines': report lines}."""
    name, held = spec['name'], holdout_seeds()
    lines = []

    def say(*ls):
        for line in ls:
            lines.append(line)
            log(line)
    plan = ledger.plan(name)
    if plan is not None:
        old = {k: v for k, v in plan.items() if k not in ('kind', 'name', 'time')}
        if old != spec['identity']:
            diff = sorted(k for k in set(old) | set(spec['identity']) if old.get(k) != spec['identity'].get(k))
            raise SystemExit('the ledger has a different pass named %s (differs in %s): pick a new --name'
                             % (name, ', '.join(diff)))
    elif not dry_run:
        ledger.append(dict(spec['identity'], kind='plan', name=name))
    say('%s: %s, %d block(s) of %d pairs (%d games each)%s' % (
        name, spec['identity']['mode'], len(spec['blocks']), spec['pairs'], 2 * spec['pairs'],
        ', resumed from the ledger' if plan is not None else ''))
    stats, played, status = {}, 0, 'done'
    for b in spec['blocks']:
        rec = ledger.blocks(name).get(b['block'])
        if rec is not None:
            if rec['x'] != b['x'] or rec['y'] != b['y']:
                raise SystemExit('block %d of %s has other vectors in the ledger' % (b['block'], name))
            why = refusal(rec['seed'], held, set())
            if why:
                raise SystemExit('block %d of %s: its seed %d is now %s' % (b['block'], name, rec['seed'], why))
        if dry_run:
            seed = rec['seed'] if rec else fresh_seed(held, ledger.seeds())
            fake = {'seed': seed, 'x_id': aivsai.tune_id(b['x']), 'y_id': aivsai.tune_id(b['y'])}
            done = sum(1 for k in ledger.games(name) if k[0] == b['block'])
            say(*block_lines(spec, b, fake, None, len(spec['blocks'])))
            say('  vectors (table order): X %s, Y %s' % (b['x'], b['y']))
            say('  %s; %d of %d games in the ledger' % ('seed from the ledger' if rec else 'fresh seed (not reserved: a real run draws its own)',
                                                         done, 2 * spec['pairs']))
            status = 'dry run'
            continue
        if rec is None:
            if max_blocks is not None and played >= max_blocks:
                status = 'partial'
                break
            seed = fresh_seed(held, ledger.seeds())
            rec = ledger.append({'kind': 'block', 'name': name, 'block': b['block'], 'seed': seed, 'signs': b.get('signs'),
                                 'x': b['x'], 'y': b['y'], 'x_id': aivsai.tune_id(b['x']), 'y_id': aivsai.tune_id(b['y'])})
        games = block_games(rec['seed'], spec['pairs'], b['x'], b['y'])
        prev = ledger.games(name)
        todo = [g for g in games if (b['block'], g['scenario'], g['game']) not in prev or
                (replay_excluded and prev[(b['block'], g['scenario'], g['game'])]['excluded'])]
        if todo:
            if max_blocks is not None and played >= max_blocks:
                status = 'partial'
                break
            played += 1
            by_key = {(g['scenario'], g['game']): g for g in todo}

            def on_result(res, b=b, rec=rec):
                g = by_key.get((res.get('scenario'), res.get('game')))
                if g is not None:
                    ledger.append(game_record(name, b['block'], g, res, rec['x_id'], rec['y_id']))
            log('block %d of %d: %d game(s) to play' % (b['block'] + 1, len(spec['blocks']), len(todo)))
            runner.run(todo, os.path.join(out_dir, 'runs', name, 'b%d' % b['block']), on_result)
        prev = ledger.games(name)
        recs = [prev[k] for k in ((b['block'], g['scenario'], g['game']) for g in games) if k in prev]
        st = stats[b['block']] = block_stats(recs)
        say(*block_lines(spec, b, rec, st, len(spec['blocks'])))
        if len(recs) < len(games):
            say('  %d game(s) have no result: the run was cut short; run the same command again to resume'
                % (len(games) - len(recs)))
            status = 'partial'
            break
        if st['excluded'] > MAX_EXCLUDED * st['games']:
            say('  STOP: %d of %d games excluded, more than %d%%. Fix the cause, then resume with --replay-excluded.'
                % (st['excluded'], st['games'], round(100 * MAX_EXCLUDED)))
            status = 'stopped'
            break
        write_report(out_dir, name, lines)
    if not dry_run:
        write_report(out_dir, name, lines)
    return {'status': status, 'stats': stats, 'lines': lines}


def write_report(out_dir, name, lines):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, '%s.md' % name), 'w', encoding='utf-8') as f:
        f.write('# aitune %s\n\n```\n%s\n```\n' % (name, '\n'.join(lines)))


def verdict_lines(plan, v):
    out = ['', 'Pooled over %d blocks, %d scored pairs:' % (len(plan['H']), v['pairs']),
           '  col  constant        E_j     SE      z   "+" wins  verdict']
    for r in v['rows']:
        out.append('  %-4d %-13s %+7.3f %6.3f %+6.1f   %5.1f%%   %s' % (r['column'], r['knob'] or '(check)', r['E'], r['se'],
                                                                     r['z'], 100 * r['plus_rate'], r['note']))
    if not v['checks_ok']:
        out.append('A check column is outside %.2f: a harness problem or a three-constant interaction. Nothing is kept.' % CHECK)
    elif not v['kept']:
        out.append('Nothing kept: no knob reaches |E_j| >= %.2f.' % KEEP)
    return out


# --- commands
def identity(mode, reg, sha, **extra):
    return dict(mode=mode, rom_sha1=sha, tune_version=reg.version, names=reg.names, defaults=reg.defaults,
                teams=TEAMS, level=LEVEL, sizes=list(SIZES), **extra)


def cmd_screen(a, reg, ledger, runner):
    knobs = [k.strip() for k in a.knobs.split(',') if k.strip()]
    plan = screen_plan(reg, knobs, a.design)
    nb = len(plan['blocks'])
    if a.pairs % nb:
        raise SystemExit('--pairs %d does not split into %d equal blocks' % (a.pairs, nb))
    sha, _ = check_rom(a.rom, reg, a.dry_run)
    spec = {'name': a.name, 'pairs': a.pairs // nb, 'blocks': plan['blocks'],
            'identity': identity('screen', reg, sha, design=a.design, knobs=knobs, columns=plan['columns'],
                                 pairs_per_block=a.pairs // nb)}
    print('knobs on columns: %s; check columns: %s' % (
        ', '.join('%s %d (%d, step %d)' % (k, c, reg.knob(k).default, reg.knob(k).step) for k, c in plan['columns'].items()),
        ', '.join(map(str, plan['checks'])) or 'none'))
    res = run_pass(spec, ledger, runner, a.out_dir, a.replay_excluded, a.max_blocks, a.dry_run)
    if res['status'] != 'done':
        print('pass %s: %s' % (a.name, res['status']))
        return 2 if res['status'] == 'stopped' else 0
    v = verdict(plan, reg, [res['stats'][i]['scores'] for i in range(nb)])
    if v is None:
        lines = ['', 'A block has no scored pair: no estimate.']
    else:
        lines = verdict_lines(plan, v)
        if v['checks_ok'] and v['candidate']:
            path = os.path.join(a.out_dir, '%s_candidate.json' % a.name)
            with open(path, 'w') as f:
                json.dump(v['candidate'], f, indent=1)
            lines += ['Candidate (the kept knobs one step in their winning direction): %s' % os.path.relpath(path, WORK),
                      'Next: dev/aitune.py confirm --name %s_confirm --set %s' % (a.name, os.path.relpath(path, WORK))]
        ledger.append({'kind': 'result', 'name': a.name, 'rows': v['rows'], 'checks_ok': v['checks_ok'],
                       'candidate': v['candidate']})
    for line in lines:
        print(line)
    write_report(a.out_dir, a.name, res['lines'] + lines)
    return 0


def cmd_confirm(a, reg, ledger, runner):
    values = load_set(a.set)
    x = reg.vector(values)
    sha, _ = check_rom(a.rom, reg, a.dry_run)
    spec = {'name': a.name, 'pairs': a.pairs,
            'blocks': [{'block': 0, 'signs': None, 'x_values': values, 'y_values': {}, 'x': x, 'y': reg.defaults}],
            'identity': identity('confirm', reg, sha, set=values, pairs_per_block=a.pairs)}
    res = run_pass(spec, ledger, runner, a.out_dir, a.replay_excluded, None, a.dry_run)
    if res['status'] != 'done':
        print('confirmation %s: %s' % (a.name, res['status']))
        return 2 if res['status'] == 'stopped' else 0
    st = res['stats'][0]
    ok = 2 * st['x_wins'] >= st['decided'] > 0
    line = 'Confirmation: the candidate won %d of %d decided games against the defaults: %s (needs half).' % (
        st['x_wins'], st['decided'], 'PASS' if ok else 'FAIL')
    print(line)
    ledger.append({'kind': 'result', 'name': a.name, 'x_wins': st['x_wins'], 'decided': st['decided'], 'pass': ok})
    write_report(a.out_dir, a.name, res['lines'] + [line])
    return 0 if ok else 1


def cmd_accept_aa(a, reg, ledger, runner):
    sha, _ = check_rom(a.rom, reg, a.dry_run)
    name = a.name or 'accept_aa_%s' % (sha or 'nosha')[:8]
    d = reg.defaults
    spec = {'name': name, 'pairs': a.pairs,
            'blocks': [{'block': 0, 'signs': None, 'x_values': {}, 'y_values': {}, 'x': d, 'y': d}],
            'identity': identity('accept-aa', reg, sha, pairs_per_block=a.pairs)}
    res = run_pass(spec, ledger, runner, a.out_dir, a.replay_excluded, None, a.dry_run)
    if res['status'] != 'done':
        print('A/A %s: %s' % (name, res['status']))
        return 2 if res['status'] == 'stopped' else 0
    log_dir = os.path.join(a.out_dir, 'runs', name, 'b0')
    out = subprocess.run([sys.executable, MIRROR_CHECK, log_dir], capture_output=True, text=True).stdout
    print(out.rstrip())
    m = re.search(r'(\d+) mirrored turn-1 decisions checked, (\d+) differ', out)
    ok = bool(m) and int(m.group(1)) > 0 and int(m.group(2)) == 0
    line = 'A/A: %s (mirror_check: %s)' % ('PASS' if ok else 'FAIL', m.group(0) if m else 'no summary line')
    print(line)
    ledger.append({'kind': 'result', 'name': name, 'mirror': out.strip().splitlines()[-1:] if out else [], 'pass': ok})
    write_report(a.out_dir, name, res['lines'] + [out.rstrip(), line])
    return 0 if ok else 1


# accept-sides: one scenario, game 0, five times on the same teams and seed
def side_runs(reg):
    """(label, trainer vector, player vector, the side with the probe or None, the probe's constant)."""
    d = reg.defaults
    sc = reg.vector({SIDE_TEST[0]: SIDE_TEST[1]}, check=False)
    wb = reg.vector({REPLACE_TEST: reg.entry(REPLACE_TEST).hi}, check=False)
    return [('defaults', d, d, None, None),
            ('switch_cost_player', d, sc, 'player', SIDE_TEST[0]), ('switch_cost_trainer', sc, d, 'trainer', SIDE_TEST[0]),
            ('worth_base_player', d, wb, 'player', REPLACE_TEST), ('worth_base_trainer', wb, d, 'trainer', REPLACE_TEST)]


def _side(ev):
    return WINNER_SIDE.get(ev.get('side'), ev.get('side'))


def turn1_options(events):
    """{side: {option: value}} of each side's first decision on turn 1 (None for a decision without options)."""
    out, turn = {}, 0
    for ev in events:
        if ev.get('kind') == 'turn':
            turn = ev.get('turn')
            if turn and turn > 1:
                break
        elif ev.get('kind') == 'decision' and turn == 1 and _side(ev) not in out:
            out[_side(ev)] = {o[0]: o[1] for o in ev['options']} if ev.get('options') else None
    return out


def first_replacement(events, side):
    """(history before it, {candidate: value}) of the side's first replacement that ai_replace valued, or None.
    The history is every decision and replacement before it, without option values."""
    hist = []
    for ev in events:
        if ev.get('kind') == 'switch' and _side(ev) == side and ev.get('options'):
            return tuple(hist), {o[0]: o[1] for o in ev['options']}
        if ev.get('kind') == 'decision':
            hist.append(('d', _side(ev), ev.get('pokemon'), ev.get('action'), ev.get('name'), ev.get('target')))
        elif ev.get('kind') == 'switch':
            hist.append(('s', _side(ev), ev.get('from'), ev.get('to')))
    return None


def side_check(runs, events, delta, tol=SIDE_TOLERANCE):
    """runs: side_runs(); events: {label: that game's events}. Returns [(status, text)], status PASS, FAIL or SKIP."""
    out, base = [], events.get('defaults')
    if base is None:
        return [('FAIL', 'the defaults game has no events')]
    b1 = turn1_options(base)
    for label, _, _, yside, const in runs[1:]:
        ev = events.get(label)
        if ev is None:
            out.append(('FAIL', '%s: no events (the game did not run)' % label))
            continue
        xside = 'trainer' if yside == 'player' else 'player'
        r1 = turn1_options(ev)
        bx, rx, by, ry = b1.get(xside), r1.get(xside), b1.get(yside), r1.get(yside)
        if bx is None or rx is None:
            out.append(('SKIP', '%s: turn 1 of the %s side (X) has no options to compare' % (label, xside)))
        else:
            out.append(('PASS' if bx == rx else 'FAIL', '%s: turn 1, X (%s side) options %s' % (
                label, xside, 'unchanged' if bx == rx else 'changed: %s vs %s' % (bx, rx))))
        if by is None or ry is None:
            out.append(('SKIP', '%s: turn 1 of the %s side (Y) has no options to compare' % (label, yside)))
        elif const == SIDE_TEST[0]:
            sw = sorted(k for k in by if k.startswith('switch:'))
            if not sw:
                out.append(('SKIP', '%s: Y (%s side) has no switch option on turn 1' % (label, yside)))
            else:
                bad = [(k, by[k], ry.get(k)) for k in sw if ry.get(k) is None or abs(by[k] - delta - ry[k]) > tol]
                out.append(('FAIL' if bad else 'PASS', '%s: turn 1, Y (%s side) switch options %s' % (
                    label, yside, 'all %d lower by %d' % (len(sw), delta) if not bad else
                    'not %d lower: %s' % (delta, ', '.join('%s %s -> %s' % b for b in bad)))))
        else:
            out.append(('PASS' if by != ry else 'FAIL', '%s: turn 1, Y (%s side) options %s' % (
                label, yside, 'changed' if by != ry else 'unchanged (the %s probe did not reach it)' % const)))
        for side, role in ((xside, 'X'), (yside, 'Y')):
            if role == 'Y' and const != REPLACE_TEST:
                continue        # ai_replace does not read SWITCH_COST: only X's values are compared there
            br, rr = first_replacement(base, side), first_replacement(ev, side)
            if br is None or rr is None:
                out.append(('SKIP', '%s: no valued replacement of the %s side in both games' % (label, side)))
            elif br[0] != rr[0]:
                out.append(('SKIP', '%s: the games went apart before the %s side\'s first replacement' % (label, side)))
            elif role == 'X':
                out.append(('PASS' if br[1] == rr[1] else 'FAIL', '%s: ai_replace, X (%s side) values %s' % (
                    label, side, 'unchanged' if br[1] == rr[1] else 'changed: %s vs %s' % (br[1], rr[1]))))
            else:
                out.append(('PASS' if br[1] != rr[1] else 'FAIL', '%s: ai_replace, Y (%s side) values %s' % (
                    label, side, 'changed' if br[1] != rr[1] else 'unchanged')))
    return out


def side_verdict(checks):
    """FAIL on any failure; INCOMPLETE when a turn-1 check was skipped or no Y-side ai_replace check ran."""
    if any(s == 'FAIL' for s, _ in checks):
        return 'FAIL'
    if any(s == 'SKIP' and 'turn 1' in t for s, t in checks) or \
            not any(s == 'PASS' and 'ai_replace, Y' in t for s, t in checks):
        return 'INCOMPLETE'
    return 'PASS'


def cmd_accept_sides(a, reg, ledger, runner):
    sha, _ = check_rom(a.rom, reg, a.dry_run)
    runs = side_runs(reg)
    delta = SIDE_TEST[1] - reg.entry(SIDE_TEST[0]).default
    held = holdout_seeds()
    name = 'accept_sides_%s_%s' % ((sha or 'nosha')[:8], datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    seed = fresh_seed(held, ledger.seeds())
    print('%s: %d runs of one scenario (seed %d)%s' % (name, len(runs), seed, ', dry run' if a.dry_run else ''))
    for label, t, p, side, const in runs:
        print('  %-20s trainer %s, player %s' % (label, aivsai.tune_id(t), aivsai.tune_id(p)))
    if a.dry_run:
        return 0
    ledger.append({'kind': 'block', 'name': name, 'block': 0, 'seed': seed, 'mode': 'accept-sides', 'rom_sha1': sha})
    g0 = aivsai.games_of(aivsai.draw_scenarios(1, TEAMS, LEVEL, seed), False, SIZES)[0]
    games = []
    for label, t, p, side, const in runs:
        g = dict(g0, scenario='%s_%s' % (g0['scenario'], label), tune={'trainer': t, 'player': p}, keep_events=True)
        g['x_side'] = None if side is None else ('trainer' if side == 'player' else 'player')
        games.append(g)
    results = runner.run(games, os.path.join(a.out_dir, 'runs', name), None)
    events, bad = {}, []
    for res in results:
        label = res['scenario'].split('_', 1)[1]
        fails = [f['ev'] for f in res.get('failures') or [] if (f.get('ev') or '').startswith('tune ')]
        print('  %-20s end %s, %s turns, winner %s' % (label, res.get('end'), res.get('turns'),
                                                       WINNER_SIDE.get(res.get('winner'), '-')))
        if fails or res.get('events') is None:
            bad.append('%s: %s' % (label, '; '.join(fails) or 'no events (%s)' % res.get('end')))
        else:
            events[label] = res['events']
    checks = side_check(runs, events, delta)
    for s, t in checks:
        print('  %-4s %s' % (s, t))
    for b in bad:
        print('  game problem: ' + b)
    v = 'FAIL' if bad else side_verdict(checks)
    print('Side routing: %s%s' % (v, ' (run it again: a new seed gives another scenario)' if v == 'INCOMPLETE' else ''))
    ledger.append({'kind': 'result', 'name': name, 'verdict': v, 'checks': checks})
    return {'PASS': 0, 'INCOMPLETE': 3}.get(v, 1)


def cmd_table(a, reg):
    try:
        t = aivsai.find_tune(a.rom)
    except aivsai.TuneError as e:
        print('%s: %s' % (a.rom, e))
        return 1
    if t is None:
        print('%s has no tuning table (a ROM without the advanced AI)' % a.rom)
        return 1
    print('%s: table at %08X, version %d, %d entries' % (a.rom, t.addr, t.version, len(t.defaults)))
    ok = True
    if reg is None:
        print('  (no tune.h to compare with)')
        print('  defaults: %s' % t.defaults)
        return 0
    if t.version != reg.version or len(t.defaults) != len(reg.entries):
        print('  tune.h: version %d, %d entries' % (reg.version, len(reg.entries)))
        ok = False
    for i, e in enumerate(reg.entries):
        rv = t.defaults[i] if i < len(t.defaults) else None
        print('  %-14s ROM %-6s tune.h %-6d %s' % (e.name, rv, e.default, '' if rv == e.default else '<- differs'))
        ok &= rv == e.default
    return 0 if ok else 1


def cmd_seed(a, ledger):
    held, used = holdout_seeds(), ledger.seeds()
    if a.check:
        bad = 0
        for s in a.check:
            why = refusal(s, held, used)
            print('%d: %s' % (s, 'refused, ' + why if why else 'allowed'))
            bad += why is not None
        return 1 if bad else 0
    seed = fresh_seed(held, used)
    if a.reserve:
        ledger.append({'kind': 'seed', 'seed': seed, 'label': a.reserve})
        print('%d (reserved in the ledger as %s)' % (seed, a.reserve))
    else:
        print('%d (not reserved)' % seed)
    return 0


def cmd_export(a):
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    if os.path.exists(out):
        raise SystemExit('%s exists: --out must be a new directory' % a.out)
    reg = Registry.load(os.path.join(src, 'tune.h'))
    values = load_set(a.set)
    text = reg.exported(values)
    shutil.copytree(src, out)
    with open(os.path.join(out, 'tune.h'), 'w', encoding='utf-8') as f:
        f.write(text)
    new = Registry(text)
    for e, d in zip(reg.entries, new.defaults):
        if d != e.default:
            print('  %-14s %d -> %d' % (e.name, e.default, d))
    print('wrote %s/tune.h; build it with:\n  .venv/bin/python work/advanced-ai/testbench/dev/aibuild.py --src %s '
          '--out %s.nds' % (a.out, a.out, os.path.join(tbpaths.RUNS, 'aibuild', os.path.basename(out))))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--selftest']:
        return subprocess.run([sys.executable, os.path.join(HERE, 'tests', 'test_aitune.py')] + argv[1:]).returncode
    ap = argparse.ArgumentParser(description='Self-play tuning of the advanced AI (the bench side).')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, run=True, rom=True):
        if rom:
            p.add_argument('--rom', required=True, help='an AI build')
        p.add_argument('--payload', help="its payload.json (default: ADVAI_PAYLOAD)")
        p.add_argument('--tune-h', default=TUNE_H)
        p.add_argument('--ledger', default=os.path.join(TUNE_DIR, 'ledger.jsonl'))
        p.add_argument('--out-dir', default=TUNE_DIR)
        if run:
            p.add_argument('--workers', type=int, default=2, help='emulator processes (lib/emupool.py caps the machine)')
            p.add_argument('--dry-run', action='store_true', help='print the plan (blocks, vectors, seeds); no emulator')
            p.add_argument('--replay-excluded', action='store_true', help='play again the games the ledger has as excluded')
        return p
    p = common(sub.add_parser('screen', help='the mirrored Hadamard screen'))
    p.add_argument('--name', required=True, help='the pass name (the same name resumes it)')
    p.add_argument('--knobs', default=','.join(DEFAULT_KNOBS))
    p.add_argument('--pairs', type=int, default=200, help='pairs in all (split equally into the blocks)')
    p.add_argument('--design', choices=sorted(DESIGNS), default='h8')
    p.add_argument('--max-blocks', type=int, default=None, help='play at most N blocks in this run')
    p = common(sub.add_parser('confirm', help='a candidate set against the defaults'))
    p.add_argument('--name', required=True)
    p.add_argument('--set', required=True, help='JSON {knob: value}')
    p.add_argument('--pairs', type=int, default=50)
    p = common(sub.add_parser('accept-aa', help='harness acceptance: defaults on both sides, then mirror_check'))
    p.add_argument('--name', default=None)
    p.add_argument('--pairs', type=int, default=20)
    common(sub.add_parser('accept-sides', help='harness acceptance: each side reads its own copy'))
    common(sub.add_parser('table', help="the ROM's tuning table against tune.h"), run=False)
    p = common(sub.add_parser('seed', help='a fresh allowed seed, or why seeds are refused'), run=False, rom=False)
    p.add_argument('--check', type=int, nargs='+')
    p.add_argument('--reserve', metavar='LABEL', help='record the drawn seed in the ledger')
    p = sub.add_parser('export', help='a candidate set as the defaults of a source copy')
    p.add_argument('--set', required=True)
    p.add_argument('--src', required=True, help='the AI sources with tune.h (for example work/advanced-ai/src)')
    p.add_argument('--out', required=True, help='a new directory: a copy of --src with the new defaults')
    a = ap.parse_args(argv)
    if a.cmd == 'export':
        return cmd_export(a)
    ledger = Ledger(a.ledger)
    if a.cmd == 'seed':
        return cmd_seed(a, ledger)
    if a.payload or os.environ.get(payload.ENV):
        payload.path_from(a.payload)    # exported for the workers; find_tune reads g_tune from it
    if getattr(a, 'rom', None):
        os.environ['ADVAI_TEAMS_ROM'] = os.path.abspath(a.rom)     # the trainer teams the scenarios draw from
    reg = Registry.load(a.tune_h) if os.path.exists(a.tune_h) else None
    if a.cmd == 'table':
        return cmd_table(a, reg)
    if reg is None:
        raise SystemExit('%s does not exist (--tune-h names another)' % a.tune_h)
    runner = Emulators(os.path.abspath(a.rom), a.workers)
    try:
        return {'screen': cmd_screen, 'confirm': cmd_confirm, 'accept-aa': cmd_accept_aa,
                'accept-sides': cmd_accept_sides}[a.cmd](a, reg, ledger, runner)
    finally:
        runner.close()


if __name__ == '__main__':
    sys.exit(main())
