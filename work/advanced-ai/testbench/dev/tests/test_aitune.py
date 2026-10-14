"""Tests of dev/aitune.py and the tuning additions to versus/aivsai.py that need no emulator.

  .venv/bin/python work/advanced-ai/testbench/dev/aitune.py --selftest
  .venv/bin/python work/advanced-ai/testbench/dev/tests/test_aitune.py

Ported from the Spanish workspace's tests/aitune/test_aitune.py (dc8577c). The ROM tests use the English rc8 release
(work/build/advanced-ai/base/rc8_release.nds, a ROM without the AI and so without the table; the Spanish tests used
its base_s2 build) and skip when it is missing. Scratch files go to RUNS/aitune_test/ and are removed."""
import argparse
import contextlib
import io
import json
import os
import random
import re
import shutil
import struct
import sys
import unittest
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'lib'))
import tbpaths  # noqa: E402
import aitune  # noqa: E402
import aivsai  # noqa: E402
from romio import crc16  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, 'sample_tune.h')
BASE_S2 = os.path.join(tbpaths.BUILD, 'base', 'rc8_release.nds')     # a ROM without the table (the Spanish base_s2)
SCRATCH = os.path.join(tbpaths.RUNS, 'aitune_test')
os.environ.setdefault('ADVAI_TEAMS_ROM', BASE_S2)        # the trainer teams block_games draws from
# the ROM tests read tables by the Spanish scan (aivsai.find_tune), never at an AI build's g_tune: a payload in the
# environment (run.py exports one) would point them at an address these ROMs do not have
os.environ.pop('ADVAI_PAYLOAD', None)
# the design's table (section 4): rows are blocks, columns 0-7; col 1 TEMPO, 2 WORTH_BASE, 3 KO_TEMPO,
# 4 ROLL_MARGIN, 7 SWITCH_COST
DESIGN_H8 = ['++++++++', '+-+-+-+-', '++--++--', '+--++--+', '++++----', '+-+--+-+', '++----++', '+--+-++-']


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def sample():
    return aitune.Registry.load(SAMPLE)


def scratch(name):
    os.makedirs(SCRATCH, exist_ok=True)
    return os.path.join(SCRATCH, name)


def make_tune_rom(src, dst, values, version=1, second=None):
    """A copy of the ROM `src` with a tuning table appended to arm9's ITCM block (as build.replace_itcm writes
    ITCM code): both copies `values`, or `second` as the player side's copy. Returns the table's address."""
    import ndspy.code
    with open(src, 'rb') as f:
        rom = bytearray(f.read())
    a9_off, _, a9_ram, a9_size = struct.unpack_from('<IIII', rom, 0x20)
    footer = bytes(rom[a9_off + a9_size:a9_off + a9_size + 12])
    main = ndspy.code.MainCodeFile(bytes(rom[a9_off:a9_off + a9_size]), a9_ram)
    itcm = next(s for s in main.sections if s.ramAddress == aivsai.ITCM_BASE)
    pad = -len(itcm.data) % 4
    addr = aivsai.ITCM_BASE + len(itcm.data) + pad
    table = struct.pack('<IHH', aivsai.TUNE_MAGIC, version, len(values)) + \
        struct.pack('<%dH' % (2 * len(values)), *(list(values) + list(second or values)))
    itcm.data = bytes(itcm.data) + b'\0' * pad + table
    arm9 = main.save(compress=False)
    fat_off, fat_size = struct.unpack_from('<II', rom, 0x48)
    starts = [s for s, e in (struct.unpack_from('<II', rom, fat_off + 8 * i) for i in range(fat_size // 8)) if e > s]
    starts += [struct.unpack_from('<I', rom, o)[0] for o in (0x30, 0x40, 0x48, 0x50, 0x68)]
    limit = min(s for s in starts if s > a9_off)
    assert a9_off + len(arm9) + 12 <= limit, 'no room after arm9'
    rom[a9_off:limit] = arm9 + footer + b'\xFF' * (limit - a9_off - len(arm9) - 12)
    struct.pack_into('<I', rom, 0x2C, len(arm9))
    struct.pack_into('<H', rom, 0x6C, crc16(rom[0x4000:0x8000]))
    struct.pack_into('<H', rom, 0x15E, crc16(rom[:0x15E]))
    with open(dst, 'wb') as f:
        f.write(rom)
    return addr


class TestRegistry(unittest.TestCase):
    def test_sample(self):
        r = sample()
        self.assertEqual(r.version, 1)
        self.assertEqual(r.names, ['TEMPO', 'WORTH_BASE', 'MY_ROLL', 'THEIR_ROLL', 'SWITCH_COST', 'KO_TEMPO',
                                   'DAMAGE_CREDIT', 'ROLE_W', 'LAST_BONUS'])
        self.assertEqual(r.defaults, [100, 250, 890, 960, 60, 120, 90, 1000, 500])
        self.assertEqual(r.entry('ROLE_W'), aitune.Entry('ROLE_W', 1000, 0, 2000, 400))
        self.assertEqual(r.knob('ROLL_MARGIN'), aitune.Entry('ROLL_MARGIN', 35, 1, 75, 20))

    def test_vector(self):
        r = sample()
        v = r.vector({'ROLL_MARGIN': 55, 'TEMPO': 140})
        self.assertEqual(v[:4], [140, 250, 870, 980])
        with self.assertRaisesRegex(aitune.RegistryError, 'outside its range'):
            r.vector({'TEMPO': 240})
        self.assertEqual(r.vector({'SWITCH_COST': 1000}, check=False)[4], 1000)    # accept-sides' probe
        with self.assertRaisesRegex(aitune.RegistryError, 'give one'):
            r.vector({'ROLL_MARGIN': 20, 'MY_ROLL': 900})
        with self.assertRaisesRegex(aitune.RegistryError, 'below THEIR_ROLL'):
            r.vector({'MY_ROLL': 970}, check=False)
        with self.assertRaisesRegex(aitune.RegistryError, 'unknown constant'):
            r.vector({'NOPE': 1})

    def bad(self, edit, msg):
        text = read(SAMPLE)
        with self.assertRaisesRegex(aitune.RegistryError, msg):
            aitune.Registry(edit(text))

    def test_errors(self):
        self.bad(lambda t: t.replace('X(WORTH_BASE,', 'X(TEMPO,'), 'twice')
        self.bad(lambda t: t.replace('100,  40,  200', '300,  40,  200'), 'lo <= default <= hi')
        self.bad(lambda t: t.replace('890, 850', '(925 - 35), 850'), 'not NAME, default')
        self.bad(lambda t: t.replace('926, 1000', '900, 1000'), 'meet')
        self.bad(lambda t: t.replace('#define TUNE_LIST(X)', '#define TUNE_LIZT(X)'), 'no #define TUNE_LIST')
        self.bad(lambda t: t.replace('1500, 200)', '70000, 200)'), 'lo <= default <= hi')
        self.bad(lambda t: t.replace('#define TUNE_VERSION 1', ''), 'TUNE_VERSION')

    def test_comments_and_macro_end(self):
        # an X( in a comment or after the macro's last line is not an entry
        text = read(SAMPLE).replace('#define TUNE_ENUM', '/* X(FAKE, 1, 0, 2, 1) */\n#define X_AFTER(X) X(FAKE2, 1, 0, 2, 1)\n#define TUNE_ENUM')
        self.assertEqual(len(aitune.Registry(text).entries), 9)

    def test_symmetric_rolls_needed(self):
        r = aitune.Registry(read(SAMPLE).replace('960, 926', '961, 926'))
        with self.assertRaisesRegex(aitune.RegistryError, 'symmetric'):
            r.knob('ROLL_MARGIN')

    def test_export(self):
        r = sample()
        text = r.exported({'TEMPO': 140, 'ROLL_MARGIN': 55, 'ROLE_W': 600})
        new = aitune.Registry(text)
        self.assertEqual(new.defaults, [140, 250, 870, 980, 60, 120, 90, 600, 500])
        self.assertEqual([(e.name, e.lo, e.hi, e.step) for e in new.entries], [(e.name, e.lo, e.hi, e.step) for e in r.entries])
        self.assertIn('    X(TEMPO,          140,  40,  200,  40) \\\n', text)      # alignment kept
        self.assertIn('    X(ROLE_W,         600,   0, 2000, 400) \\\n', text)
        self.assertEqual(text.count('\n'), r.text.count('\n'))
        with self.assertRaises(aitune.RegistryError):
            r.exported({'TEMPO': 20})

    def test_export_command(self):
        src, out, cand = scratch('src'), scratch('src_tuned'), scratch('cand.json')
        for p in (src, out):
            shutil.rmtree(p, ignore_errors=True)
        os.makedirs(src)
        shutil.copy(SAMPLE, os.path.join(src, 'tune.h'))
        write(os.path.join(src, 'advai.c'), '/* stand-in */\n')
        write(cand, json.dumps({'WORTH_BASE': 350}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aitune.main(['export', '--set', cand, '--src', src, '--out', out]), 0)
        self.assertEqual(aitune.Registry.load(os.path.join(out, 'tune.h')).defaults[1], 350)
        self.assertEqual(aitune.Registry.load(os.path.join(src, 'tune.h')).defaults[1], 250)    # the source untouched
        self.assertTrue(os.path.exists(os.path.join(out, 'advai.c')))
        with self.assertRaisesRegex(SystemExit, 'exists'):
            aitune.main(['export', '--set', cand, '--src', src, '--out', out])
        shutil.rmtree(src)
        shutil.rmtree(out)
        os.remove(cand)


class TestPlan(unittest.TestCase):
    def test_hadamard_is_the_design_table(self):
        H = aitune.hadamard(8)
        self.assertEqual([''.join('+' if x > 0 else '-' for x in row) for row in H], DESIGN_H8)
        for a in range(8):
            for b in range(8):
                self.assertEqual(sum(H[i][a] * H[i][b] for i in range(8)), 8 if a == b else 0)

    def test_screen_plan(self):
        p = aitune.screen_plan(sample(), aitune.DEFAULT_KNOBS, 'h8')
        self.assertEqual(p['columns'], {'TEMPO': 1, 'WORTH_BASE': 2, 'KO_TEMPO': 3, 'ROLL_MARGIN': 4, 'SWITCH_COST': 7})
        self.assertEqual(p['checks'], [0, 5, 6])
        b0, b1 = p['blocks'][0], p['blocks'][1]
        # block 0: everything up against everything down, the design's pass 1 steps
        self.assertEqual(b0['x_values'], {'TEMPO': 140, 'WORTH_BASE': 350, 'KO_TEMPO': 168, 'ROLL_MARGIN': 55, 'SWITCH_COST': 84})
        self.assertEqual(b0['y_values'], {'TEMPO': 60, 'WORTH_BASE': 150, 'KO_TEMPO': 72, 'ROLL_MARGIN': 15, 'SWITCH_COST': 36})
        self.assertEqual(b0['x'], [140, 350, 870, 980, 84, 168, 90, 1000, 500])
        self.assertEqual(b0['y'], [60, 150, 910, 940, 36, 72, 90, 1000, 500])
        self.assertEqual(b1['signs'], [-1, 1, -1, 1, -1])                       # row 1: + - + - + - + -
        for b in p['blocks']:
            for k, c in p['columns'].items():
                self.assertEqual(b['signs'][list(p['columns']).index(k)], aitune.hadamard(8)[b['block']][c])
            d = sample().defaults
            self.assertEqual([x + y for x, y in zip(b['x'], b['y'])], [2 * v for v in d])   # mirror images

    def test_h4_and_limits(self):
        p = aitune.screen_plan(sample(), ['TEMPO', 'WORTH_BASE', 'KO_TEMPO', 'SWITCH_COST'], 'h4')
        self.assertEqual(p['columns']['SWITCH_COST'], 0)          # the fourth knob on the all-plus column
        self.assertEqual(p['checks'], [])
        with self.assertRaises(aitune.RegistryError):
            aitune.screen_plan(sample(), ['TEMPO'] * 2, 'h8')
        with self.assertRaises(aitune.RegistryError):
            aitune.screen_plan(sample(), ['TEMPO', 'WORTH_BASE', 'KO_TEMPO', 'SWITCH_COST', 'ROLE_W'], 'h4')
        r = aitune.Registry(read(SAMPLE).replace('X(TEMPO,          100,  40,  200,  40)', 'X(TEMPO, 180, 40, 200, 40)'))
        with self.assertRaisesRegex(aitune.RegistryError, 'TEMPO 220 is outside'):
            aitune.screen_plan(r, aitune.DEFAULT_KNOBS, 'h8')      # a step past the range bound stops the knob

    def test_block_games(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s' % BASE_S2)
        x, y = [1] * 9, [2] * 9
        games = aitune.block_games(12345, 3, x, y)
        self.assertEqual([(g['scenario'], g['game'], g['x_side']) for g in games],
                         [('s001', 0, 'trainer'), ('s001', 1, 'trainer'), ('s002', 0, 'player'), ('s002', 1, 'player'),
                          ('s003', 0, 'trainer'), ('s003', 1, 'trainer')])
        self.assertEqual(games[0]['tune'], {'trainer': x, 'player': y})
        self.assertEqual(games[2]['tune'], {'trainer': y, 'player': x})
        self.assertEqual(games[0]['adv']['name'], games[1]['orig']['name'])   # a pair: the teams swapped
        self.assertTrue(all(len(g['adv']['team']) == 6 and g['adv']['team'][0]['level'] == 100 for g in games))
        self.assertEqual(json.loads(json.dumps(games)), games)                # the worker reads them as JSON


def simulate(plan, pairs, rng, effect):
    """Pair scores per block. effect(signs by knob) is the strength f of a setting; X wins a game with
    probability 0.85 or 0.15 (its team the stronger one or not) plus (f(X) - f(Y)) / 2."""
    out = []
    for b in plan['blocks']:
        sx = dict(zip(plan['knobs'], b['signs']))
        d = (effect(sx) - effect({k: -s for k, s in sx.items()})) / 2
        scores = []
        for _ in range(pairs):
            won = sum(rng.random() < min(1.0, max(0.0, base + d)) for base in (0.85, 0.15))
            scores.append(1 if won == 2 else -1 if won == 0 else 0)
        out.append(scores)
    return out


class TestEstimates(unittest.TestCase):
    def setUp(self):
        self.reg = sample()
        self.plan = aitune.screen_plan(self.reg, aitune.DEFAULT_KNOBS, 'h8')

    def test_formula(self):
        rng = random.Random(1)
        scores = [[rng.choice((-1, 0, 0, 0, 1)) for _ in range(25)] for _ in range(8)]
        est = aitune.estimates(self.plan['H'], scores)
        for j in range(8):    # the design's E_j = (1/200) sum_i H[i][j] S_i with equal blocks
            self.assertAlmostEqual(est[j][0], sum(self.plan['H'][i][j] * sum(scores[i]) for i in range(8)) / 200)
        self.assertAlmostEqual(aitune.estimates(self.plan['H'], [[1, -1, 0, 0] * 25] * 8)[0][1], (0.5 * 100 / 99 / 800) ** 0.5)

    def test_injected_effect_large_sample(self):
        # per-game shifts up to 0.15, so 0.85 + shift never clips at 1
        effect = lambda s: 0.08 * s['TEMPO'] - 0.07 * s['SWITCH_COST'] + 0.08 * s['TEMPO'] * s['WORTH_BASE']  # noqa: E731
        scores = simulate(self.plan, 4000, random.Random(7), effect)
        est = aitune.estimates(self.plan['H'], scores)
        want = {1: 0.16, 7: -0.14}               # E = 2 * the per-game shift; the two-knob term cancels (mirrored)
        for j in range(8):
            self.assertAlmostEqual(est[j][0], want.get(j, 0.0), delta=0.015, msg='column %d' % j)
        v = aitune.verdict(self.plan, self.reg, scores)
        self.assertTrue(v['checks_ok'])
        self.assertEqual(v['kept'], {'TEMPO': 1, 'SWITCH_COST': -1})
        self.assertEqual(v['candidate'], {'TEMPO': 140, 'SWITCH_COST': 36})
        self.assertAlmostEqual(v['rows'][1]['plus_rate'], 0.58, delta=0.01)

    def test_keep_rates_at_design_size(self):
        """25 pairs per block: a real 60/40 edge is kept nearly always, 55/45 about 29%, no effect almost never."""
        rng, runs = random.Random(11), 300
        kept = {k: 0 for k in aitune.DEFAULT_KNOBS}
        for _ in range(runs):
            v = aitune.verdict(self.plan, self.reg, simulate(self.plan, 25, rng, lambda s: 0.10 * s['TEMPO'] + 0.05 * s['KO_TEMPO']))
            for k in v['kept']:
                kept[k] += 1
        self.assertGreaterEqual(kept['TEMPO'] / runs, 0.93)
        self.assertTrue(0.12 <= kept['KO_TEMPO'] / runs <= 0.45, kept['KO_TEMPO'])
        self.assertLessEqual(kept['WORTH_BASE'] + kept['ROLL_MARGIN'] + kept['SWITCH_COST'], 6)

    def test_three_knob_aliases(self):
        # TEMPO x WORTH_BASE x ROLL_MARGIN (1^2^4 = 7) lands on SWITCH_COST's column
        scores = simulate(self.plan, 4000, random.Random(3), lambda s: 0.1 * s['TEMPO'] * s['WORTH_BASE'] * s['ROLL_MARGIN'])
        est = aitune.estimates(self.plan['H'], scores)
        self.assertAlmostEqual(est[7][0], 0.2, delta=0.015)
        self.assertTrue(all(abs(est[j][0]) < 0.015 for j in range(7)))
        # TEMPO x WORTH_BASE x KO_TEMPO (1^2^3 = 0) lands on the bias check: the pass keeps nothing
        scores = simulate(self.plan, 4000, random.Random(4),
                          lambda s: 0.1 * s['TEMPO'] * s['WORTH_BASE'] * s['KO_TEMPO'] + 0.1 * s['TEMPO'])
        v = aitune.verdict(self.plan, self.reg, scores)
        self.assertFalse(v['checks_ok'])
        self.assertEqual(v['kept'], {})
        self.assertIn('FAILED', v['rows'][0]['note'])
        self.assertIn('check failed', v['rows'][1]['note'])

    def test_unequal_blocks_and_empty(self):
        scores = [[1, 0, -1, 0]] * 7 + [[1, 1, 1]]
        est = aitune.estimates(self.plan['H'], scores)
        self.assertAlmostEqual(est[0][0], (0 * 7 + 1) / 8)
        self.assertIsNone(aitune.estimates(self.plan['H'], [[1]] * 7 + [[]]))

    def test_sign_test(self):
        self.assertEqual(aitune.sign_p(0, 0), 1.0)
        self.assertAlmostEqual(aitune.sign_p(9, 1), 22 / 1024)


HELD = (34208, 86603, 71831, 51222)      # four of the Spanish held-out seeds (its qa/aivsai/holdout/seeds.json)


@contextlib.contextmanager
def held_out():
    """aitune with a held-out file of HELD in place of RUNS/aivsai/holdout/seeds.json (which this project's runs
    have not written yet)."""
    import seeds
    p = scratch('holdout_seeds.json')
    write(p, json.dumps({'S1': {'trainers': list(HELD[:2])}, 'S2': {'mixed': list(HELD[2:])}}))
    saved = aitune.holdout_seeds
    aitune.holdout_seeds = lambda path=p: seeds.holdout_seeds(path)
    try:
        yield p
    finally:
        aitune.holdout_seeds = saved
        os.remove(p)


class TestSeeds(unittest.TestCase):
    def test_holdout_file(self):
        with held_out():
            held = aitune.holdout_seeds()
        for s in (34208, 86603, 71831, 51222):
            self.assertIn(s, held)
            self.assertIn('held out', aitune.refusal(s, held, set()))
        for s in aitune.ROUND_SEEDS:
            self.assertEqual(aitune.refusal(s, held, set()), 'a round seed')
        self.assertEqual(aitune.refusal(777, held, {777}), 'already in the ledger')
        self.assertIsNone(aitune.refusal(778, held, {777}))

    def test_fresh_seed_skips_refused(self):
        class Scripted:
            def __init__(self, seq):
                self.seq = list(seq)

            def randrange(self, n):
                return self.seq.pop(0)
        self.assertEqual(aitune.fresh_seed({34208}, {777}, Scripted([34208, 101, 777, 999])), 999)
        with self.assertRaises(RuntimeError):
            aitune.fresh_seed({1}, set(), Scripted([1] * 5), tries=5)
        s = aitune.fresh_seed(aitune.holdout_seeds(), set())
        self.assertTrue(0 <= s < 1 << 31)

    def test_missing_or_empty_holdout_refuses(self):
        # lib/seeds.py: a missing file holds no seed (no round has been held out here yet); an empty one still raises
        self.assertEqual(aitune.holdout_seeds(scratch('no_such_seeds.json')), set())
        p = scratch('empty_seeds.json')
        write(p, json.dumps({'S9': {'sizes': '4:6'}}))
        with self.assertRaises(ValueError):
            aitune.holdout_seeds(p)
        write(p, json.dumps({'S9': {'mixed': [5, 6], 'nested': {'random': 7}}}))
        self.assertEqual(aitune.holdout_seeds(p), {5, 6, 7})
        os.remove(p)


def fake_result(game, winner_side, end='normal', failures=(), ids=True):
    return {'scenario': game['scenario'], 'game': game['game'], 'end': end, 'turns': 20, 'seconds': 0.1, 'log': None,
            'winner': {'trainer': 'advanced', 'player': 'original'}.get(winner_side), 'x_side': game['x_side'],
            'tune': {s: aivsai.tune_id(game['tune'][s]) for s in aitune.SIDES} if ids else None,
            'failures': [{'ev': f} for f in failures]}


def x_wins(game):
    """A fixed outcome per game, the same whatever the seed: X wins in most pairs of scenario s001."""
    return (int(game['scenario'][1:]) * 7 + game['game'] * 3) % 4 != 0


class FakeRunner:
    """Stands in for the emulators: results come from outcome(game), and the run can die after n games."""

    def __init__(self, outcome=None, die_after=None, end=None):
        self.outcome, self.die_after, self.end, self.calls, self.played = outcome or x_wins, die_after, end or (lambda g: 'normal'), [], 0

    def run(self, games, log_dir, on_result):
        self.calls.append([(g['scenario'], g['game']) for g in games])
        out = []
        for g in games:
            if self.die_after is not None and self.played >= self.die_after:
                raise KeyboardInterrupt
            won = self.outcome(g)
            res = fake_result(g, g['x_side'] if won else ('player' if g['x_side'] == 'trainer' else 'trainer'), self.end(g))
            self.played += 1
            out.append(res)
            if on_result:
                on_result(res)
        return out


class TestPass(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s (block_games draws its teams)' % BASE_S2)
        self.reg = sample()
        self.plan = aitune.screen_plan(self.reg, aitune.DEFAULT_KNOBS, 'h8')
        self.path = scratch('ledger_%s.jsonl' % self._testMethodName)
        if os.path.exists(self.path):
            os.remove(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        shutil.rmtree(scratch('out'), ignore_errors=True)

    def spec(self, pairs=3, blocks=None, **extra):
        return {'name': 'p', 'pairs': pairs, 'blocks': (blocks or self.plan['blocks'])[:2],
                'identity': aitune.identity('screen', self.reg, 'f' * 40, design='h8', knobs=list(aitune.DEFAULT_KNOBS),
                                            columns=self.plan['columns'], pairs_per_block=pairs, **extra)}

    def run_pass(self, runner, **kw):
        return aitune.run_pass(self.spec(), aitune.Ledger(self.path), runner, scratch('out'), log=lambda line: None, **kw)

    def test_full_then_resume_after_a_crash(self):
        full = FakeRunner()
        res = self.run_pass(full)
        self.assertEqual(res['status'], 'done')
        self.assertEqual(sum(len(c) for c in full.calls), 12)
        os.remove(self.path)
        with self.assertRaises(KeyboardInterrupt):
            self.run_pass(FakeRunner(die_after=7))          # block 0 done, block 1 cut after one game
        led = aitune.Ledger(self.path)
        seeds = {b: r['seed'] for b, r in led.blocks('p').items()}
        self.assertEqual(len(led.games('p')), 7)
        again = FakeRunner()
        res2 = self.run_pass(again)
        self.assertEqual(again.calls, [[('s001', 1), ('s002', 0), ('s002', 1), ('s003', 0), ('s003', 1)]])
        led = aitune.Ledger(self.path)
        self.assertEqual({b: r['seed'] for b, r in led.blocks('p').items()}, seeds)    # the same seeds
        self.assertEqual(res2['stats'], res['stats'])
        self.assertEqual(len(led.games('p')), 12)
        again2 = FakeRunner()
        self.run_pass(again2)                               # a finished pass plays nothing
        self.assertEqual(again2.calls, [])

    def test_ledger_records(self):
        self.run_pass(FakeRunner())
        led = aitune.Ledger(self.path)
        plan = led.plan('p')
        self.assertEqual(plan['knobs'], list(aitune.DEFAULT_KNOBS))
        b0 = led.blocks('p')[0]
        self.assertEqual((b0['x'], b0['y']), (self.plan['blocks'][0]['x'], self.plan['blocks'][0]['y']))
        self.assertEqual(b0['x_id'], aivsai.tune_id(b0['x']))
        g = led.games('p')[(0, 's002', 1)]
        self.assertEqual((g['x_side'], g['excluded']), ('player', None))
        self.assertEqual(g['x_won'], x_wins({'scenario': 's002', 'game': 1}))
        self.assertTrue(led.seeds() >= {b0['seed']})

    def test_seeds_are_fresh_and_never_held_out(self):
        led = aitune.Ledger(self.path)
        led.append({'kind': 'block', 'name': 'old', 'block': 0, 'seed': 424242})
        self.run_pass(FakeRunner())
        seeds = [r['seed'] for b, r in sorted(aitune.Ledger(self.path).blocks('p').items())]
        held = aitune.holdout_seeds()
        self.assertEqual(len(set(seeds)), 2)
        self.assertTrue(all(aitune.refusal(s, held, {424242}) is None for s in seeds))

    def test_other_plan_same_name_refused(self):
        self.run_pass(FakeRunner())
        spec = self.spec(pairs=4)
        with self.assertRaisesRegex(SystemExit, 'different pass'):
            aitune.run_pass(spec, aitune.Ledger(self.path), FakeRunner(), scratch('out'), log=lambda line: None)

    def test_max_blocks(self):
        r1 = FakeRunner()
        self.assertEqual(self.run_pass(r1, max_blocks=1)['status'], 'partial')
        self.assertEqual(list(aitune.Ledger(self.path).blocks('p')), [0])    # block 1's seed not drawn yet
        r2 = FakeRunner()
        self.assertEqual(self.run_pass(r2, max_blocks=1)['status'], 'done')
        self.assertEqual(len(r2.calls), 1)

    def test_exclusions_stop_the_pass(self):
        frozen = {('s001', 1), ('s003', 0)}
        r = FakeRunner(end=lambda g: 'frozen' if (g['scenario'], g['game']) in frozen else 'normal')
        res = self.run_pass(r)
        self.assertEqual(res['status'], 'stopped')
        st = res['stats'][0]
        self.assertEqual((st['excluded'], st['unscored'], len(st['scores'])), (2, 2, 1))
        self.assertEqual(list(aitune.Ledger(self.path).blocks('p')), [0])
        self.assertEqual(self.run_pass(FakeRunner())['status'], 'stopped')                  # resumed: still stopped
        r2 = FakeRunner()
        self.assertEqual(self.run_pass(r2, replay_excluded=True)['status'], 'done')
        self.assertEqual(r2.calls[0], sorted(frozen))

    def test_game_record_exclusions(self):
        g = {'scenario': 's001', 'game': 0, 'x_side': 'trainer', 'tune': {'trainer': [1], 'player': [2]}}
        xi, yi = aivsai.tune_id([1]), aivsai.tune_id([2])
        rec = lambda res: aitune.game_record('p', 0, g, res, xi, yi)  # noqa: E731
        self.assertEqual(rec(fake_result(g, 'trainer'))['x_won'], True)
        self.assertIsNone(rec(fake_result(g, 'trainer'))['excluded'])
        self.assertTrue(rec(fake_result(g, 'trainer', failures=['tune read back [[1]], wrote [[2]]']))['excluded'].startswith('tune '))
        self.assertIn('tune ids', rec(fake_result(g, 'trainer', ids=False))['excluded'])
        self.assertEqual(rec(fake_result(g, 'trainer', end='unfinished'))['excluded'], 'unfinished')
        self.assertEqual(rec(fake_result(g, None))['excluded'], 'no winner')
        swapped = dict(g, x_side='player')
        self.assertIn('tune ids', aitune.game_record('p', 0, swapped, fake_result(g, 'trainer'), xi, yi)['excluded'])

    def test_dry_run_writes_nothing(self):
        lines = []
        r = FakeRunner()
        res = aitune.run_pass(self.spec(), aitune.Ledger(self.path), r, scratch('out'), dry_run=True, log=lines.append)
        self.assertEqual(res['status'], 'dry run')
        self.assertEqual(r.calls, [])
        self.assertFalse(os.path.exists(self.path))
        text = '\n'.join(lines)
        self.assertIn('block 1 of 2, seed ', text)
        self.assertIn('X: TEMPO 140, WORTH_BASE 350, KO_TEMPO 168, ROLL_MARGIN 55 (rolls 870/980), SWITCH_COST 84', text)
        self.assertIn(aivsai.tune_id(self.plan['blocks'][1]['y']), text)
        self.assertIn('fresh seed (not reserved', text)
        self.assertIn('vectors (table order): X [140, 350, 870, 980, 84, 168, 90, 1000, 500], Y [60, 150, 910, 940, 36, 72, 90, 1000, 500]', text)

    def test_cut_ledger_line(self):
        write(self.path, json.dumps({'kind': 'seed', 'seed': 5}) + '\n{"kind": "game", "na')
        with contextlib.redirect_stderr(io.StringIO()):
            led = aitune.Ledger(self.path)
            led.append({'kind': 'seed', 'seed': 6})
            self.assertEqual(aitune.Ledger(self.path).seeds(), {5, 6})


class TestCommands(unittest.TestCase):
    def test_screen_dry_run_on_a_rom_without_table(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s' % BASE_S2)
        led = scratch('cmd_ledger.jsonl')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = aitune.main(['screen', '--name', 'dry', '--dry-run', '--rom', BASE_S2, '--tune-h', SAMPLE,
                              '--ledger', led, '--out-dir', scratch('out')])
        text = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn('has no tuning table', text)
        self.assertIn('block 8 of 8', text)
        self.assertIn('check columns: 0, 5, 6', text)
        self.assertFalse(os.path.exists(led))
        with self.assertRaisesRegex(SystemExit, 'has no tuning table'):    # a real run refuses that ROM
            with contextlib.redirect_stdout(io.StringIO()):
                aitune.main(['screen', '--name', 'dry', '--rom', BASE_S2, '--tune-h', SAMPLE, '--ledger', led,
                             '--out-dir', scratch('out')])
        shutil.rmtree(scratch('out'), ignore_errors=True)

    def test_seed_command(self):
        led = scratch('seed_ledger.jsonl')
        if os.path.exists(led):
            os.remove(led)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), held_out():
            self.assertEqual(aitune.main(['seed', '--check', '34208', '505', '12', '--ledger', led]), 1)
            self.assertEqual(aitune.main(['seed', '--reserve', 'final eval', '--ledger', led]), 0)
        self.assertIn('34208: refused, held out', out.getvalue())
        self.assertIn('505: refused, a round seed', out.getvalue())
        self.assertIn('12: allowed', out.getvalue())
        self.assertEqual(len(aitune.Ledger(led).seeds()), 1)
        os.remove(led)


class TestFindTune(unittest.TestCase):
    def blob(self, n=3, v0=(1, 2, 3), v1=None, at=12, version=1):
        b = bytearray(at) + struct.pack('<IHH', aivsai.TUNE_MAGIC, version, n) + struct.pack('<%dH' % (2 * n), *(list(v0) + list(v1 or v0)))
        return bytes(b) + bytes(8)

    def test_synthetic_blocks(self):
        t = aivsai.tune_in_itcm(self.blob())
        self.assertEqual(t, aivsai.TuneTable(aivsai.ITCM_BASE + 12, 1, [1, 2, 3]))
        self.assertIsNone(aivsai.tune_in_itcm(b'\0' * 64))
        self.assertIsNone(aivsai.tune_in_itcm(self.blob(at=13)))                 # not 4-aligned
        self.assertIsNone(aivsai.tune_in_itcm(self.blob(version=0)))
        self.assertIsNone(aivsai.tune_in_itcm(self.blob(n=40, v0=[0] * 40)[:-100]))   # runs past the block
        with self.assertRaisesRegex(aivsai.TuneError, 'two different copies'):
            aivsai.tune_in_itcm(self.blob(v1=(1, 2, 4)))
        with self.assertRaisesRegex(aivsai.TuneError, '2 tuning tables'):
            aivsai.tune_in_itcm(self.blob() + self.blob(at=0))

    def test_rom_without_table(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s' % BASE_S2)
        self.assertIsNone(aivsai.find_tune(BASE_S2))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = aitune.main(['table', '--rom', BASE_S2, '--tune-h', SAMPLE])
        self.assertEqual(rc, 1)
        self.assertIn('has no tuning table', out.getvalue())

    def test_rom_with_table(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s' % BASE_S2)
        rom = scratch('tune_fake.nds')
        try:
            d = sample().defaults
            addr = make_tune_rom(BASE_S2, rom, d)
            self.assertEqual(aivsai.find_tune(rom), aivsai.TuneTable(addr, 1, d))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(aitune.main(['table', '--rom', rom, '--tune-h', SAMPLE]), 0)
            self.assertIn('table at %08X, version 1, 9 entries' % addr, out.getvalue())
            make_tune_rom(BASE_S2, rom, d[:-1] + [501])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(aitune.main(['table', '--rom', rom, '--tune-h', SAMPLE]), 1)
                with self.assertRaisesRegex(SystemExit, 'does not match tune.h'):
                    aitune.check_rom(rom, sample())
            make_tune_rom(BASE_S2, rom, d, second=d[:-1] + [501])
            with self.assertRaises(aivsai.TuneError):
                aivsai.find_tune(rom)
        finally:
            if os.path.exists(rom):
                os.remove(rom)


class SidesRunner:
    """accept-sides' games with the events side_events gives (the label is in the scenario name)."""

    def __init__(self, routed):
        self.routed = routed

    def run(self, games, log_dir, on_result):
        runs = aitune.side_runs(sample())
        return [dict(fake_result(g, 'trainer'), events=side_events(runs, g['scenario'].split('_', 1)[1], self.routed))
                for g in games]


class LogRunner(FakeRunner):
    """FakeRunner that also writes turn 1 of each game as a battle log, in the lines mirror_check reads; skew moves
    the player side's options in game 1 (a side asymmetry)."""

    def __init__(self, skew=0):
        super().__init__()
        self.skew = skew

    def run(self, games, log_dir, on_result):
        os.makedirs(log_dir, exist_ok=True)
        for g in games:
            a, b = ('Dragonite', 'Nidoking') if g['game'] == 0 else ('Nidoking', 'Dragonite')   # trainer, player
            opt = {'Dragonite': 'Outrage=500, switch:Cloyster=-136', 'Nidoking': 'Ice Beam=482, switch:Muk=-1179'}
            p_opt = opt[b] if g['game'] == 0 else re.sub(r'=(-?\d+)', lambda m: '=%d' % (int(m.group(1)) + self.skew), opt[b], count=1)
            write(os.path.join(log_dir, '%s_g%d.log' % (g['scenario'], g['game'])),
                  '--- Turn 1 ----\n  TRAINER   %s -> x on y\n            options: %s\n  PLAYER    %s -> x on y\n'
                  '            options: %s\n--- Turn 2 ----\n' % (a, opt[a], b, p_opt))
        return super().run(games, log_dir, on_result)


class TestCommandResults(unittest.TestCase):
    """The commands' verdicts and exit codes with the emulators and the ROM check stood in."""

    def setUp(self):
        if not os.path.exists(BASE_S2):
            self.skipTest('no %s (block_games draws its teams)' % BASE_S2)
        self.check_rom = aitune.check_rom
        aitune.check_rom = lambda rom, reg, dry_run=False: ('f' * 40, None)
        self.led, self.out = scratch('results_ledger.jsonl'), scratch('results_out')
        self.cleanup()

    def tearDown(self):
        aitune.check_rom = self.check_rom
        self.cleanup()

    def cleanup(self):
        for p in (self.led, scratch('cand.json')):
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(self.out, ignore_errors=True)

    def args(self, **kw):
        return argparse.Namespace(rom='x.nds', out_dir=self.out, replay_excluded=False, dry_run=False, max_blocks=None, **kw)

    def call(self, cmd, runner, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = cmd(self.args(**kw), sample(), aitune.Ledger(self.led), runner)
        return rc, out.getvalue()

    def test_screen_to_candidate(self):
        # X wins both games of a pair exactly when its TEMPO is the higher one: E(TEMPO) = 1, the rest 0
        tempo_up = lambda g: g['tune'][g['x_side']][0] > 100  # noqa: E731
        rc, out = self.call(aitune.cmd_screen, FakeRunner(outcome=tempo_up), name='s', knobs=','.join(aitune.DEFAULT_KNOBS),
                            design='h8', pairs=16)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r'1    TEMPO\s+\+1\.000 .*keep \+: 100 -> 140')
        self.assertRegex(out, r'0    \(check\)\s+\+0\.000 .*check: ok')
        self.assertEqual(json.loads(read(os.path.join(self.out, 's_candidate.json'))), {'TEMPO': 140})
        self.assertIn('keep +: 100 -> 140', read(os.path.join(self.out, 's.md')))
        self.assertTrue(aitune.Ledger(self.led).records[-1]['kind'] == 'result')

    def test_confirm(self):
        cand = scratch('cand.json')
        write(cand, json.dumps({'TEMPO': 140}))
        self.assertEqual(self.call(aitune.cmd_confirm, FakeRunner(outcome=lambda g: g['game'] == 0), name='c', set=cand, pairs=4)[0], 0)
        rc, out = self.call(aitune.cmd_confirm, FakeRunner(outcome=lambda g: g['scenario'] == 's001' and g['game'] == 0),
                            name='c2', set=cand, pairs=4)
        self.assertEqual(rc, 1)
        self.assertIn('won 1 of 8 decided games against the defaults: FAIL', out)

    def test_accept_sides(self):
        rc, out = self.call(aitune.cmd_accept_sides, SidesRunner(True))
        self.assertEqual(rc, 0, out)
        self.assertIn('Side routing: PASS', out)
        rc, out = self.call(aitune.cmd_accept_sides, SidesRunner(False))
        self.assertEqual(rc, 1)
        self.assertIn('Side routing: FAIL', out)

    def test_accept_aa(self):
        rc, out = self.call(aitune.cmd_accept_aa, LogRunner(), name='aa', pairs=3)
        self.assertEqual(rc, 0, out)
        self.assertIn('A/A: PASS (mirror_check: 6 mirrored turn-1 decisions checked, 0 differ', out)
        rc, out = self.call(aitune.cmd_accept_aa, LogRunner(skew=9), name='aa2', pairs=3)
        self.assertEqual(rc, 1)
        self.assertIn('A/A: FAIL', out)


class FakeMemory:
    """The two emulator memory views set_tune uses, over a byte array at `base`."""

    def __init__(self, base, data, drop=False):
        self.base, self.data, self.drop = base, bytearray(data), drop

    def write_short(self, a, v):
        if not self.drop:
            struct.pack_into('<H', self.data, a - self.base, v)

    def read_short(self, a):
        return struct.unpack_from('<H', self.data, a - self.base)[0]

    def read_long(self, a):
        return struct.unpack_from('<I', self.data, a - self.base)[0]


class TestSetTune(unittest.TestCase):
    def duel(self, drop=False, magic=aivsai.TUNE_MAGIC, table=True):
        base = aivsai.ITCM_BASE + 0x100
        data = struct.pack('<IHH', magic, 1, 3) + struct.pack('<6H', 1, 2, 3, 1, 2, 3)
        d = object.__new__(aivsai.Duel)
        d.mem = d.mu = FakeMemory(base, data, drop)
        d.tune, d.tune_error = (aivsai.TuneTable(base, 1, [1, 2, 3]) if table else None), None
        return d

    def test_write_and_read_back(self):
        d = self.duel()
        self.assertIsNone(d.set_tune({'trainer': [10, 20, 30], 'player': [40, 50, 60]}))
        self.assertEqual(struct.unpack_from('<6H', d.mem.data, 8), (10, 20, 30, 40, 50, 60))   # v[0] the trainer's

    def test_failures(self):
        self.assertIn('read back', self.duel(drop=True).set_tune({'trainer': [10, 20, 30], 'player': [1, 2, 3]}))
        self.assertIn('header', self.duel(magic=0).set_tune({'trainer': [1, 2, 3], 'player': [1, 2, 3]}))
        self.assertIn('no tuning table', self.duel(table=False).set_tune({'trainer': [1, 2, 3], 'player': [1, 2, 3]}))
        self.assertIn('not 3 values', self.duel().set_tune({'trainer': [1, 2], 'player': [1, 2, 3]}))
        self.assertIn('not 3 values', self.duel().set_tune({'trainer': [1, 2, 70000], 'player': [1, 2, 3]}))

    def test_ids(self):
        self.assertEqual(aivsai.tune_id([100, 250]), aivsai.tune_id([100, 250]))
        self.assertNotEqual(aivsai.tune_id([100, 250]), aivsai.tune_id([100, 251]))
        self.assertEqual(len(aivsai.tune_id([1])), 8)


def events(t_opts, p_opts, replacements=(), turns=None):
    """A game's kept events: turn 1 with each side's options, then decisions and replacements."""
    evs = [{'kind': 'turn', 'turn': 1},
           {'kind': 'decision', 'side': 'original', 'pokemon': 'Nidoking', 'action': 'move', 'name': 'Ice Beam', 'target': 'Dragonite',
            'options': [[k, v] for k, v in p_opts.items()]},
           {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Dragonite', 'action': 'move', 'name': 'Outrage', 'target': 'Nidoking',
            'options': [[k, v] for k, v in t_opts.items()]}]
    for side, opts, hist in replacements:
        evs += [{'kind': 'turn', 'turn': 2}, {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Dragonite', 'action': 'move',
                                              'name': hist, 'target': 'Nidoking'},
                {'kind': 'switch', 'side': side, 'from': 'Nidoking', 'to': 'Muk', 'options': [[k, v] for k, v in opts.items()]}]
    return evs


def side_events(runs, label, routed=True, delta=1000 - 60):
    """A run's events when each side reads its own copy (routed) or both read the defaults (the AI ignores it)."""
    T = {'Outrage': 500, 'switch:Cloyster': -136, 'switch:Dusclops': -370}
    P = {'Ice Beam': 482, 'switch:Muk': -1179, 'switch:Exploud': -1260}
    REP = {'Muk': 300, 'Exploud': 120}
    lower = lambda opts: {k: v - delta if k.startswith('switch:') else v for k, v in opts.items()}  # noqa: E731
    more = lambda opts, d: {k: v + d for k, v in opts.items()}  # noqa: E731
    side, const = next((r[3], r[4]) for r in runs if r[0] == label)
    t, p, rt, rp = dict(T), dict(P), dict(REP), dict(REP)
    if routed and const == 'SWITCH_COST':
        t, p = (lower(t), p) if side == 'trainer' else (t, lower(p))
    if routed and const == 'WORTH_BASE':
        t, p, rt, rp = (more(t, 37), p, more(rt, 11), rp) if side == 'trainer' else (t, more(p, 37), rt, more(rp, 11))
    return events(t, p, [('original', rp, 'Outrage'), ('advanced', rt, 'Outrage')])


class TestSideCheck(unittest.TestCase):
    def setUp(self):
        self.runs = aitune.side_runs(sample())
        self.delta = 1000 - 60

    def game(self, label, routed=True):
        return side_events(self.runs, label, routed, self.delta)

    def test_routed_passes(self):
        evs = {r[0]: self.game(r[0]) for r in self.runs}
        checks = aitune.side_check(self.runs, evs, self.delta)
        self.assertEqual([s for s, _ in checks if s != 'PASS'], [], checks)
        self.assertEqual(aitune.side_verdict(checks), 'PASS')

    def test_unrouted_fails(self):
        """A ROM whose AI ignores the table: Y's options do not move, so the check fails."""
        evs = {r[0]: self.game(r[0], routed=False) for r in self.runs}
        checks = aitune.side_check(self.runs, evs, self.delta)
        self.assertEqual(aitune.side_verdict(checks), 'FAIL')
        self.assertTrue(any(s == 'FAIL' and 'switch options not 940 lower' in t for s, t in checks))

    def test_x_side_moved_fails(self):
        evs = {r[0]: self.game(r[0]) for r in self.runs}
        evs['switch_cost_player'] = self.game('switch_cost_trainer')    # the probe read by the wrong side
        checks = aitune.side_check(self.runs, evs, self.delta)
        self.assertEqual(aitune.side_verdict(checks), 'FAIL')

    def test_diverged_games_are_skipped(self):
        evs = {r[0]: self.game(r[0]) for r in self.runs}
        for label in ('worth_base_player', 'worth_base_trainer'):
            g = evs[label]
            for ev in g:
                if ev.get('kind') == 'decision' and ev.get('name') == 'Outrage' and not ev.get('options'):
                    ev['name'] = 'Fire Punch'
        checks = aitune.side_check(self.runs, evs, self.delta)
        self.assertTrue(any(s == 'SKIP' and 'went apart' in t for s, t in checks))
        self.assertEqual(aitune.side_verdict(checks), 'INCOMPLETE')

    def test_tolerance(self):
        evs = {r[0]: self.game(r[0]) for r in self.runs}
        g = evs['switch_cost_player']
        g[1]['options'][1][1] += 2                                       # 2 points of integer rounding pass
        self.assertEqual(aitune.side_verdict(aitune.side_check(self.runs, evs, self.delta)), 'PASS')
        g[1]['options'][1][1] += 1
        self.assertEqual(aitune.side_verdict(aitune.side_check(self.runs, evs, self.delta)), 'FAIL')


if __name__ == '__main__':
    # aiteams and aidata leave files open; warnings='' keeps unittest from resetting this filter to 'default'
    warnings.filterwarnings('ignore', category=ResourceWarning)
    try:
        unittest.main(verbosity=1, warnings='')
    finally:
        if os.path.isdir(SCRATCH) and not os.listdir(SCRATCH):
            os.rmdir(SCRATCH)
