"""Full trainer battles with random teams, played to the end: crash safety and win rate of the AI.

  .venv/bin/python work/advanced-ai/testbench/fuzz/aifuzz.py --rom ROM --payload PAYLOAD [--battles N] [--seed S]
                   [--workers N] [--mode both|advanced|current] [--double] [--only SEEDS]
  .venv/bin/python work/advanced-ai/testbench/fuzz/aifuzz.py --report --rom ROM [--double]   # the saved results,
                                                                                   # compared on the seeds both played

Ported from the Spanish workspace's tools/aifuzz.py (dc8577c). Changes: the random teams and the failure sorting moved
to lib/randteams.py and lib/failures.py (the AI-vs-AI report uses them too); the AI setting is written into the save in
RAM after every state load (bench/aibench.py: ADVAI_AI_SETTING 'all' for the advanced mode, 'off' for the current one)
instead of the battery save; addresses come from the payload; results go to RUNS/aifuzz/. --hard (hard mode, flag
0x218, which ran the Spanish luck steering) is not ported: this project has neither. Battle messages are read in
English or Spanish (lib/failures.py USED).

Each battle (seeded, so both AIs get the same teams) boots the bench's save state, writes random teams
into BattleSetup as bench/aibench.py does (the AI: 2-6 Pokemon, sometimes trainer items; the player:
one Pokemon a few levels higher, damaging moves only, so no move opens the party screen), and plays:
the player touches FIGHT and a random move each turn, A advances everything else. With --double the
battle is a double against the one trainer (as the bench's doubles: trainer 2 = trainer 1), the
player has two Pokemon and touches a random foe still standing on the target screen. It records every
AI decision (which overlay made it, the advanced AI's fallback code), each side's Pokemon still able
to fight (read from the battle's party containers), and every assert, NULL allocation, freeze or text
drawn outside its window (text drawn past its window's size but inside its buffer, lib/emu.py's 'clipped' note, is
listed with its text and not counted: it is the ROM's text fit, the same with either AI). A battle fails on any of
those except the inherited end-of-battle assert
(0x020733B2, one per empty party slot, see the Spanish tools/doublecheck.py), on a fallback other than doubles,
or when it does not end. Results: RUNS/aifuzz/<mode>[_double]_<ROM name>.json and a summary comparing the modes.
Exit status 1 when an advanced-mode battle has a problem for review.
"""
import argparse
import collections
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import payload  # noqa: E402
from aidata import Data  # noqa: E402
from failures import MENU_MOVE, USED, classify, problems  # noqa: E402
from randteams import battle_spec  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'aifuzz')
BATTLE_FRAMES = 36000            # 10 minutes of game time
MOVE_BUTTONS = [(64, 53), (192, 53), (64, 109), (192, 109)]
FIGHT_BUTTON = (128, 90)
# doubles target screen: each foe's box (a screenshot pixel that is orange, where to touch it, the columns of
# its name band); a foe that fainted keeps an orange box with no name in it
TARGET_BOXES = [((20, 215), (64, 40), (24, 104)), ((236, 215), (192, 40), (152, 232))]
FOE_BOX, NAME_INK, NAME_ROWS = (232, 96, 48), (64, 64, 64), (214, 226)


def standing_foes(r):
    """Touch points of the target screen's boxes with a foe in them: orange, with its name drawn."""
    im = r.emu.screenshot().convert('RGB')
    out = []
    for px, touch, (x0, x1) in TARGET_BOXES:
        orange = all(abs(a - b) <= 12 for a, b in zip(im.getpixel(px), FOE_BOX))
        ink = sum(1 for y in range(*NAME_ROWS) for x in range(x0, x1) if im.getpixel((x, y)) == NAME_INK)
        if orange and ink >= 20:
            out.append(touch)
    return out


def refused(actions):
    """The game refused the player's move (a Choice lock, a move that cannot be selected) and stays in the
    move menu with that move under the cursor, where A would pick it again forever: the menu set the same
    move twice in a row for the same Pokemon, nothing in between, within a few seconds. B goes back to
    FIGHT, where the next try touches a random move."""
    if len(actions) < 2:
        return False
    a, b = actions[-2], actions[-1]
    return a[5] == b[5] == MENU_MOVE and a[2] == b[2] and a[4] == b[4] and b[0] - a[0] < 400


class FullBattle(aibench.Bench):
    def __init__(self, rom, state):
        super().__init__(rom, state)
        self.r.skip_render = False     # the player's touches are chosen from screen pixels

    def _inject(self, a, s):
        # the battle seed from the case seed, as aivsai's synced luck pins it: the game adds the VBlank counter, which
        # differs per ROM build, and the advanced AI's reading draw (rd_draw) seeds from it (qa/aivsai/rc41_DIVERGE.md)
        c = self.cur
        fresh = c is not None and 'setup' in c and not c.get('injected')
        super()._inject(a, s)
        if fresh:
            import aivsai
            self.mem.write_long(c['setup'] + aivsai.SETUP_SEED, aivsai.luck(c['seed'], 0, 'setup'))

    def _seed(self, a, s):
        # once per battle: the bench's reseed at every AI load would replay the same rolls each turn
        if self.cur is not None and self.cur.get('injected') and not self.cur.get('seeded'):
            self.cur['seeded'] = True
            super()._seed(a, s)

    def alive(self):
        """(player, AI) Pokemon able to fight, from the AI's party containers; None outside a battle."""
        main = self.mu.read_long(aibench.MAIN_PTR)
        if not 0x02200000 <= main < 0x02400000:
            return None
        pc = main + 0x54
        out = []
        for client in (0, 1):
            party = pc + 0x0C + 0x1C * client
            n = self.mu.read_byte(party + 0x18)
            if n > 6:
                return None
            k = 0
            for i in range(n):
                b = self.mu.read_long(party + 4 * i)
                if not 0x02200000 <= b < 0x02400000:
                    return None
                k += self.mu.read_short(b + 0x1E) > 0
            out.append(k)
        return tuple(out)

    def play(self, mons, items, seed, policy, double=False):
        import emu
        r = self.r
        self.cur = {'mons': mons, 'items': items, 'seed': seed, 'calls': [], 'failures': [], 'notes': [], 'done': False,
                    'decisions': [], 'double': double, 'actions': [], 'fail_detail': [], 'fallbacks': []}
        start = r.frames
        aibench.to_battle(r, self.state)
        last, seen_battle, ended = None, False, None
        while r.frames - start < BATTLE_FRAMES and not r.frozen:
            k = r.frames - start
            if k % 30 == 0:
                a = self.alive() if self.cur.get('injected') else None
                if a is not None and sum(a):
                    last, seen_battle = a, True
                if seen_battle and r.seen(emu.STATES['field']):
                    ended = r.frames - start
                    break
            if k % 40 == 0:
                if r.seen(emu.STATES['fight_menu']):
                    r.touch(*FIGHT_BUTTON)
                    r.step(50)
                    r.touch(*policy.choice(MOVE_BUTTONS))
                    r.step(40 if double else 20)
                    foes = standing_foes(r) if double else []
                    if foes:
                        r.touch(*policy.choice(foes))
                        r.step(20)
                elif refused(self.cur['actions']):
                    r.hold('B', 4, release=4)
                else:
                    r.hold('A', 4, release=4)
            else:
                r.step(1)
        c, self.cur = self.cur, None
        return {'injected': bool(c.get('injected')), 'failures': c['failures'], 'decisions': c['decisions'],
                'alive': last, 'ended': ended, 'frozen': r.frozen, 'frames': r.frames - start,
                'actions': c['actions'], 'fail_detail': c['fail_detail'], 'fallbacks': c['fallbacks'],
                'clipped': sorted({t for t in c.get('clipped', []) if t})}

    def _event(self, **ev):
        if ev['ev'] == 'clipped':
            # text drawn past its window's size inside its buffer (lib/emu.py's note): a text-fit matter of the ROM's
            # strings, the same with either AI, so it is kept with its text and not counted as the battle's failure
            if self.cur is not None:
                self.cur.setdefault('clipped', []).append(ev.get('text'))
            return
        # each failure with its frame and the text last printed (the battle message on screen: whose move it was)
        if self.cur is not None and ev['ev'] in aibench.FAILURES:
            moves = [t for t in self.r.recent_texts if any(u in t for u in USED)]
            self.cur['fail_detail'].append({'f': self.r.frames, 'ev': '%s %s' % (ev['ev'], ev.get('lr') or ev.get('heap') or ''),
                                            'text': self.r.last_text, 'move_text': moves[-1] if moves else None})
        super()._event(**ev)

    def _setter(self, kind):
        base = super()._setter(kind)

        def f(a, s):
            c = self.cur
            n = len(c['calls']) if c else 0
            if c is not None and 'actions' in c and kind != 'none':
                # every action set in the battle: by the AI (called from the slot overlay), the player's menu or the engine
                lr = self.reg.r14
                by = 'ai' if aibench.SLOT_RANGE[0] <= lr < aibench.SLOT_RANGE[1] and c.get('slot') not in aibench.NOT_AI else '%08X' % lr
                who = self.mu.read_long(self.reg.r13) & 0xFF if kind in ('move', 'item') else None
                c['actions'].append([self.r.frames, kind, self.reg.r1, self.reg.r2, who, by])
            base(a, s)
            if c is not None and 'decisions' in c and len(c['calls']) > n and kind != 'none':
                adv = self.read_debug() if c.get('slot') == aibench.AI_OVERLAY and self.debug_addr else {}
                c['decisions'].append({'kind': kind, 'slot': c.get('slot'), 'fallback': adv.get('fallback'),
                                       'polls': adv.get('polls')})
                if adv.get('fallback'):
                    c['fallbacks'].append(dict(adv, f=self.r.frames))
        return f


def worker(rom, state, jobs_path, out_path, double):
    double = double == '1'
    d = Data(rom)
    template = open(os.path.join(aibench.OUT, 'template.bin'), 'rb').read()
    fb = FullBattle(rom, state)
    results = []
    for seed in json.load(open(jobs_path)):
        spec = battle_spec(d, seed, double)
        mons = {k: [aibench.build_mon(d, template, m, seed * 7 + i) for i, m in enumerate(spec[k])] for k in ('player', 'enemy')}
        t0 = time.time()
        res = fb.play(mons, [d.id('item', x) for x in spec['items']], seed & 0xFFFFFFFF, random.Random(seed * 31 + 1), double)
        res.update({'seed': seed, 'seconds': round(time.time() - t0, 1), 'enemy': len(spec['enemy'])})
        results.append(res)
        with open(out_path, 'w') as f:
            json.dump(results, f)


def run_mode(rom, seeds, workers, advanced, double=False):
    import shutil

    import saves
    tag = ('fuzz_adv' if advanced else 'fuzz_cur') + ('_dbl' if double else '')
    tag += '_' + os.path.splitext(os.path.basename(rom))[0]
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(aibench.OUT, exist_ok=True)
    with open(os.path.join(aibench.OUT, 'template.bin'), 'wb') as f:
        f.write(aibench.template_mon())
    os.environ[aibench.SETTING_ENV] = 'all' if advanced else 'off'     # written after each state load (to_battle)
    save = saves.path('violet_gym')
    rom_copy, state = aibench.link_rom(rom, os.path.join(OUT, '%s.nds' % tag)), os.path.join(OUT, '%s.dst' % tag)
    dsv = os.path.join(aibench.DSV_DIR, '%s.dsv' % tag)
    shutil.copy(save, dsv)
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chunks = [seeds[k::workers] for k in range(workers) if seeds[k::workers]]

    def go(k):
        rom_k, dsv_k = os.path.join(OUT, '%s_%d.nds' % (tag, k)), os.path.join(aibench.DSV_DIR, '%s_%d.dsv' % (tag, k))
        aibench.link_rom(rom, rom_k)
        shutil.copy(save, dsv_k)
        jp, op = os.path.join(OUT, 'jobs_%s_%d.json' % (tag, k)), os.path.join(OUT, 'res_%s_%d.json' % (tag, k))
        json.dump(chunks[k], open(jp, 'w'))
        if os.path.exists(op):
            os.remove(op)
        subprocess.run([sys.executable, __file__, '--worker', rom_k, state, jp, op, '1' if double else '0'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for p in (rom_k, dsv_k):
            os.remove(p)
        return json.load(open(op)) if os.path.exists(op) else []
    with ThreadPoolExecutor(len(chunks)) as pool:
        results = [x for part in pool.map(go, range(len(chunks))) for x in part]
    for p in (rom_copy, dsv):
        if os.path.lexists(p):
            os.remove(p)
    done = {x['seed'] for x in results}
    results += [{'seed': s, 'injected': False, 'failures': ['worker died'], 'decisions': [], 'alive': None, 'ended': None,
                 'frozen': False} for s in seeds if s not in done]
    return results


def summary(name, results, advanced):
    lines = []
    wins = sum(1 for x in results if x['alive'] and x['alive'][0] == 0 and x['alive'][1] > 0)
    losses = sum(1 for x in results if x['alive'] and x['alive'][1] == 0)
    bad = [(x['seed'], problems(x, advanced)) for x in results if problems(x, advanced)]
    decisions = sum(len(x['decisions']) for x in results)
    kinds = collections.Counter(dd['kind'] for x in results for dd in x['decisions'])
    lines.append('%s: %d battles, the AI won %d and lost %d (%d undecided); %d AI decisions %s; %d battles with problems'
                 % (name, len(results), wins, losses, len(results) - wins - losses, decisions, dict(kinds), len(bad)))
    cls = [classify(x, advanced) for x in results]
    lines.append('   not the AI: %d battles with inherited move-animation failures, %d stuck at the player\'s refused menu, '
                 '%d still playing at the frame limit; by design: %d Struggle fallbacks, %d fallbacks with only vetoed legal moves'
                 % (sum(1 for c in cls if c['inherited']), sum(c['stuck'] for c in cls), sum(c['slow'] for c in cls),
                    sum(c['struggle'] for c in cls), sum(c['locked'] for c in cls)))
    if advanced:
        polls = [dd['polls'] for x in results for dd in x['decisions'] if dd.get('polls') is not None]
        codes = collections.Counter(dd['fallback'] for x in results for dd in x['decisions'] if dd['slot'] == aibench.AI_OVERLAY)
        lines.append('   advanced AI: fallback codes %s; polls max %s' % (dict(codes), max(polls) if polls else None))
    for seed, p in bad[:20]:
        lines.append('   seed %d: %s' % (seed, '; '.join(p)))
    clipped = sorted({t for x in results for t in x.get('clipped', [])})
    if clipped:
        lines.append('   text drawn past its window (clipped; a text-fit note, not counted): %s' % ' | '.join(
            repr(t) for t in clipped[:8]))
    return lines, wins, len(bad)


def outcome(x):
    if not x['alive'] or x['ended'] is None:
        return 'undecided'
    return 'loss' if x['alive'][1] == 0 else 'win' if x['alive'][0] == 0 else 'undecided'


def report(double, rom):
    """Win rates of the two AIs on the battles both played (same seeds: the same teams and the same seeded random player)."""
    suffix = ('_double' if double else '') + '_' + os.path.splitext(os.path.basename(rom))[0]
    res = {}
    for name in ('advanced', 'current'):
        path = os.path.join(OUT, name + suffix + '.json')
        if not os.path.exists(path):
            sys.exit('no %s' % path)
        res[name] = {x['seed']: x for x in json.load(open(path))}
    shared = sorted(set(res['advanced']) & set(res['current']))
    pairs = collections.Counter((outcome(res['advanced'][k]), outcome(res['current'][k])) for k in shared)
    lines = ['%s battles: %d played by both AIs (same teams, same seeded random player)' % ('double' if double else 'single', len(shared))]
    for name in ('advanced', 'current'):
        o = collections.Counter(outcome(res[name][k]) for k in shared)
        lines.append('   %-8s won %d (%.1f%%), lost %d, undecided %d; all its runs: %d battles, %d with problems'
                     % (name, o['win'], 100 * o['win'] / max(1, len(shared)), o['loss'], o['undecided'], len(res[name]),
                        sum(1 for x in res[name].values() if problems(x, name == 'advanced'))))
    lines.append('   only the advanced AI won: %d; only the current AI won: %d; both won: %d; neither: %d'
                 % (sum(n for (a, c), n in pairs.items() if a == 'win' and c != 'win'),
                    sum(n for (a, c), n in pairs.items() if c == 'win' and a != 'win'),
                    pairs[('win', 'win')], sum(n for (a, c), n in pairs.items() if a != 'win' and c != 'win')))
    return lines


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:7])
    ap = argparse.ArgumentParser()
    ap.add_argument('--battles', type=int, default=50)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--workers', type=int, default=2, help='emulator processes (lib/emupool.py caps the machine)')
    ap.add_argument('--rom', help='the AI build to fuzz (not needed for --report)')
    ap.add_argument('--payload', help="the AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--mode', choices=('both', 'advanced', 'current'), default='both')
    ap.add_argument('--double', action='store_true', help='double battles against one trainer')
    ap.add_argument('--report', action='store_true', help='compare the saved results of the two modes')
    ap.add_argument('--only', help='comma-separated seeds to replay (as printed in the summary) instead of --battles/--seed')
    a = ap.parse_args()
    if a.report:
        if not a.rom:
            ap.error('--rom is required')
        print('\n'.join(report(a.double, a.rom)))
        return
    if not a.rom:
        ap.error('--rom is required')
    payload.path_from(a.payload)            # exported for the workers
    seeds = [int(x) for x in a.only.split(',')] if a.only else [a.seed * 100003 + k for k in range(a.battles)]
    failed = 0
    modes = [('advanced', True), ('current', False)] if a.mode == 'both' else [(a.mode, a.mode == 'advanced')]
    for name, adv in modes:
        t0 = time.time()
        res = run_mode(a.rom, seeds, a.workers, adv, a.double)
        with open(os.path.join(OUT, '%s%s%s_%s.json' % (name, '_double' if a.double else '', '_only' if a.only else '',
                                                        os.path.splitext(os.path.basename(a.rom))[0])), 'w') as f:
            json.dump(res, f)
        lines, wins, nbad = summary(name, res, adv)
        print('\n'.join(lines))
        print('   (%.0f s)' % (time.time() - t0))
        failed += nbad if adv else 0
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
