"""Trainer AI bench: set-up battle positions with their correct answers, run against the AI in a ROM.

  .venv/bin/python work/advanced-ai/testbench/bench/aibench.py [ID|CATEGORY|batch:N ...] --rom ROM --payload PAYLOAD
                   [--advanced] [--repeats N] [--workers N] [--save NAME] [--compare A B] [--report NAME]
  .venv/bin/python work/advanced-ai/testbench/bench/aibench.py --check --rom ROM   # every scenario's claims, no emulator

Ported from the Spanish workspace's tools/aibench.py (dc8577c). Changes: the AI-build addresses (the slot range, the
NOLEAD/NOREAD/READS words, the debug record) come from the payload (lib/payload.py); the AI setting is written into
the save in RAM after every state load (lib/emu.py set_ai_setting: --advanced sets 0x2C2, else it is cleared), and
into the battery save the pre-battle state is made from (setting_save); the Violet Gym save comes from lib/saves.py; each worker runs a symlink of the ROM, not a
copy; run files go to RUNS/aibench/ and saved runs (--save) to RUNS/aibench/saved/.

Each scenario (tests/ai_scenarios.py) is one decision: both teams (species, level, moves, ability,
item, HP, status), the trainer's items, and the answers graded as best / ok / bad (anything else is
a miss). A run boots from a save state made once per ROM (tests/violet_gym.dsv, the field before
Officer Felix, trainer 71, starts his battle), and:
- when EnemyTrainerSet_Init returns (0x020507C8, in SetupAndStartTrainerBattle), replaces both parties in BattleSetup (+4 player,
  +8 enemy; Party = max, count, 6 x 236-byte Pokémon) with Pokémon built from the ROM's data, and
  the trainer's items and party size (trainer[1] at +0x5C);
- keeps the trainer's party order (the NOLEAD word, tools/ai/engine.h), so the advanced AI does not pick another lead,
  and sets the NOREAD word, so it decides without the player's committed action (the A presses would commit one);
- when the server has loaded the AI's slot overlay (0x02223D14, after SwitchSlotOverlay), writes the
  repeat's seed into the battle RNG ([main]+0x24C, main = [0x02255BAC]), so repeats differ and are
  reproducible;
- takes the AI's decision from the overlay 14 action setters it calls (0x02200960 move,
  0x02200A30 item, 0x022009AC switch, 0x0220091C none) while the slot holds the AI, and stops there.
The setters are the same for any AI in the slot, so the advanced AI runs through the same bench.
Results: RUNS/aibench/<name>.json (--save NAME also writes RUNS/aibench/saved/<NAME>.json to compare).
"""
import argparse
import collections
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import emu  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aidata import TYPES, Data, nature_id, norm  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'aibench')
BASELINES = os.path.join(OUT, 'saved')
DSV_DIR = emu.DSV_DIR
SETTING_ENV = 'ADVAI_AI_SETTING'    # the AI setting to_battle writes after each state load ('off', 'all', 'important')
TRAINER_SET_INIT, AFTER_TRAINER_SET = 0x02072544, 0x020507C8   # its only call is at 0x020507C4
TRAINER_BATTLE = 0x02050768   # SetupAndStartTrainerBattle(task, trainer 1, trainer 2, ...): trainer 2 = 1 makes a
                              # double against one trainer, whose two Pokemon out are its party's first two
FIRST_FOE_ID = 13             # the AI's first Pokemon (client 1, pokeIDs 13-18): its decision is the one graded
AFTER_AI_LOAD = 0x02223D14
SLOT_SWITCH, NOT_AI = 0x02215914, {5, 8, 9, 12}        # the slot range comes from the payload (Layout.slot_range)
MAIN_PTR, RNG = 0x02255BAC, 0x24C
OV11_WRITER = 0x021E4F2C    # overlay 11's decision writer (r1 = AI state): diagnostics for the current AI only
SETTERS = {0x02200960: 'move', 0x02200A30: 'item', 0x022009AC: 'switch', 0x0220091C: 'none'}
STATUS_BITS = {None: 0, 'slp': 3, 'psn': 0x08, 'brn': 0x10, 'frz': 0x20, 'par': 0x40,
               'tox': 0x88}   # this hack needs the poison bit too: 0x80 alone gives no status (measured, round 2)
FAILURES = ('assert', 'null', 'freeze', 'outside', 'clipped')
AI_FLAG, AI_OVERLAY = emu.FLAG_AI, payload.AI_OVERLAY   # build.FLAG_AI / build.AI_OVERLAY
DEBUG_MAGIC = 0x49414441          # tools/ai/advai.c ai_debug, first in overlay 10's bss
DEBUG_SIZE = 248                  # sizeof(Debug): from version 3 one record per side, the trainer's first
DEBUG_SIZE_V4 = 256               # version 4 adds the foe model (strong) and the foe's likely switch-in
# the advanced AI's record of the foe's play (advai.c Read, engine.h READS_AT), the trainer's first: a scenario with
# strong=True starts with a pinned one that says the player plays strongly (magic 0xA5C3, llr 300, s 1000, pinned 1)
STRONG_READ = struct.pack('<IHHhhBB2x', 0, 0xA5C3, 0, 300, 1000, 0, 1)
# a scenario is a set position: the word NOLEAD (src/engine.h) keeps the trainer's party order, which the advanced AI
# would otherwise reorder before the battle (src/lead.c); checks/lead_check.py tests the lead itself.
# And NOREAD makes the trainer's side decide without waiting for the player's committed action (advai.c foe_choice):
# the bench presses A until the AI decides, which would commit the player's first move and grade the AI's answer to
# it; checks/read_check.py tests the reading itself. Both addresses, and READS_AT, come from the payload: other modules
# read them as aibench.NOLEAD_FLAG etc. (module __getattr__ below), this one through layout().
LAZY_WORDS = ('READS_AT', 'NOLEAD_FLAG', 'NOLEAD_MAGIC', 'NOREAD_FLAG', 'NOREAD_MAGIC')
FRAME_LIMIT = 4800     # weather from an ability on entry adds its message and animation before turn 1
NEUTRAL_NATURES = (0, 6, 12, 18, 24)
# Scenarios whose claims rest on a data edit of the Spanish build (its build.data_members) that the hack and our build
# do not have. On a ROM without the edit the scenario is left out of --check and of runs, by name and with the reason.
SPANISH_DATA = {
    'b01_light_ball_ko': ('Pikachu', {'atk': 85, 'spa': 85},
                          'its KO claims need the Spanish build\'s Pikachu (base 60/85/60/110/85/60; the hack has '
                          '40/60/50/110/60/50)'),
}


def layout():
    """The AI build's addresses (lib/payload.py; --payload or ADVAI_PAYLOAD)."""
    return payload.load()


def __getattr__(name):
    if name in LAZY_WORDS:
        return layout().words[name]
    if name == 'SLOT_RANGE':
        return layout().slot_range
    raise AttributeError(name)


def scenarios():
    import ai_scenarios
    return ai_scenarios.SCENARIOS


def mon_view(d, spec):
    """The scenario's Pokémon as the data module sees it: stats from base stats (IVs and nature as given,
    else IV 31 and a neutral nature; EVs as given), HP from a fraction or a number."""
    level = spec.get('level', 50)
    stats = d.stats(spec['species'], level, spec.get('evs'), spec.get('ivs', 31), spec.get('nature'))
    hp = spec.get('hp', 1.0)
    cur = max(1, int(stats['hp'] * hp)) if isinstance(hp, float) else hp
    return {'species': spec['species'], 'level': level, 'stats': stats, 'cur_hp': cur,
            'types': d.species(spec['species'])['types'], 'ability': spec.get('ability'),
            'status': spec.get('status'), 'moves': spec['moves']}


def build_mon(d, template, spec, seed):
    """236-byte Gen 4 party Pokémon for a scenario spec, built on a valid template."""
    from savetool import Mon
    v = mon_view(d, spec)
    m = Mon(template)
    rng = random.Random(seed)
    pid = rng.randrange(1 << 32)
    natures = (nature_id(spec['nature']),) if spec.get('nature') else NEUTRAL_NATURES
    while pid % 25 not in natures:
        pid = rng.randrange(1 << 32)
    m.pid = pid
    m.head = struct.pack('<I', pid) + m.head[4:]
    sp = d.id('species', spec['species'])
    m.set_species(sp, spec.get('nickname') or d.species_name[sp][:10])
    A, B = m.blocks['A'], m.blocks['B']
    struct.pack_into('<H', A, 2, d.id('item', spec['item']) if spec.get('item') else 0)
    struct.pack_into('<I', A, 8, d.exp_for(sp, v['level']))
    ability = d.id('ability', spec['ability']) if spec.get('ability') else d.species(sp)['abilities'][0]
    A[0x0D] = ability & 0xFF
    if 'friendship' in spec:
        A[0x0C] = spec['friendship']
    evs = spec.get('evs') or {}
    A[0x10:0x16] = bytes(evs.get(s, 0) for s in ('hp', 'atk', 'def', 'spe', 'spa', 'spd'))
    moves = [d.id('move', x) for x in spec['moves']] + [0] * (4 - len(spec['moves']))
    struct.pack_into('<4H', B, 0, *moves)
    B[8:12] = bytes(min(64, d.move(x)['pp']) if x else 0 for x in moves)
    if spec.get('pp'):          # rc36: PP left per move (uxcheck's Struggle case)
        B[8:8 + len(spec['pp'])] = bytes(spec['pp'])
    B[0x0C:0x10] = b'\0\0\0\0'
    struct.pack_into('<I', B, 0x10, (spec.get('ivs', 31) * 0x2108421) & 0x3FFFFFFF | (1 << 31))
    struct.pack_into('<I', B, 0x14, struct.unpack_from('<I', B, 0x14)[0] & ~(0x3F << 25))
    B[0x18] &= 0x01
    B[0x19] &= 0x3F
    struct.pack_into('<H', B, 0x1A, ability)
    st = v['stats']
    m.set_level(v['level'], d.exp_for(sp, v['level']))
    m.set_stats(st['hp'], st['atk'], st['def'], st['spe'], st['spa'], st['spd'])
    m.set_hp(v['cur_hp'])
    m.set_status(STATUS_BITS[spec.get('status')] if spec.get('status') != 'slp' else spec.get('sleep', 3))
    return m.encode()


def action_name(d, kind, r1, r2, enemy, player=None):
    if kind == 'move':
        name = d.move_name.get(r1, str(r1))
        if player is not None:      # doubles: the target, by battle position (even = the player's side)
            name += '>' + (player[r2 >> 1]['species'] if not r2 & 1 and (r2 >> 1) < len(player) else 'ally')
        return name
    if kind == 'item':
        return 'item:' + d.item_name.get(r1, str(r1))
    if kind == 'switch':
        return 'switch:' + (enemy[r2]['species'] if r2 < len(enemy) else str(r2))
    return 'none'


def grade(sc, action):
    """best/ok/bad/miss; names compare normalized (the same move can be 'SolarBeam' or 'Solar Beam')."""
    if action in ('no decision', 'no result'):
        return 'error'
    e = sc['expect']
    key = lambda a: a.split(':')[0] + ':' + norm(a.split(':', 1)[1]) if ':' in a else norm(a)
    move_only = lambda a: norm(a.split('>')[0])
    for g in ('best', 'ok', 'bad'):   # an answer without '>' matches the move at any target
        if any(key(action) == key(a) or ('>' not in a and '>' in action and move_only(action) == move_only(a)) for a in e.get(g, [])):
            return {'best': 'pass', 'ok': 'ok', 'bad': 'blunder'}[g]
    return 'miss'


class Bench:
    """One emulator for a ROM; runs scenarios one after another from the same save state."""

    def __init__(self, rom, state):
        lay = layout()
        self.layout, self.slot_range = lay, lay.slot_range
        self.debug_addr = lay.debug_addr(rom)
        self.r = emu.Runner(rom, os.path.join(OUT, 'shots'))
        self.r.ai_setting = os.environ.get(SETTING_ENV)
        self.mem, self.reg, self.mu = self.r.emu.memory, self.r.emu.memory.register_arm9, self.r.emu.memory.unsigned
        self.state = state
        self.cur = None
        self.r.skip_render = True      # decisions are read from the setters, never from the screen
        self.r.event = self._event
        self.mem.register_exec(TRAINER_SET_INIT, self._setup)
        self.mem.register_exec(TRAINER_BATTLE, self._double)
        self.mem.register_exec(AFTER_TRAINER_SET, self._inject)
        self.mem.register_exec(AFTER_AI_LOAD, self._seed)
        self.mem.register_exec(SLOT_SWITCH, self._slot)
        for addr, kind in SETTERS.items():
            self.mem.register_exec(addr, self._setter(kind))
        self.mem.register_exec(OV11_WRITER, self._diag)

    def _diag(self, a, s):
        c = self.cur
        if c is None or c.get('slot') not in (10, 11):
            return
        st, mu = self.reg.r1, self.mu
        signed = lambda v: v - (1 << 32) if v >> 31 else v
        row = lambda e: [mu.read_short(e + 2), mu.read_long(e + 0x18)] + [signed(mu.read_long(e + 4 + 4 * f)) for f in range(5)]
        rows = [row(st + 0x30 + k * 0x1C) for k in range(4) if mu.read_short(st + 0x30 + k * 0x1C + 2)]
        # overlay 11's draw (0x021E64A0) reads rows[target][move] at +0x30 + 0x70 t + 0x1C k, for k below the move
        # count (+0x1F0) and t below the target count (+0x1F1); byte 0 of a row is its target's pokeID
        n_moves, n_targets = min(4, mu.read_byte(st + 0x1F0)), min(4, mu.read_byte(st + 0x1F1))
        targets = [{'poke': mu.read_byte(st + 0x30 + 0x70 * t),
                    'rows': [row(st + 0x30 + 0x70 * t + 0x1C * k) for k in range(n_moves)]} for t in range(n_targets)]
        c['diag'] = {'moves': rows, 'targets': targets, 'move': signed(mu.read_long(st + 0x380)),
                     'switch': signed(mu.read_long(st + 0x41C)),
                     'switch_skip': mu.read_long(st + 0x418), 'item': signed(mu.read_long(st + 0x3BC)),
                     'item_skip': mu.read_long(st + 0x3B8)}

    def _event(self, **ev):
        if self.cur is not None and ev['ev'] in FAILURES:
            self.cur['failures'].append('%s %s' % (ev['ev'], ev.get('lr') or ev.get('heap') or ''))
        elif self.cur is not None and ev['ev'] in ('goto_fail', 'until_fail'):
            self.cur['notes'].append('%s %s' % (ev['ev'], ev.get('at') or ev.get('state') or ''))

    def _double(self, a, s):
        if self.cur is not None and self.cur.get('double') and self.reg.r2 == 0:
            self.reg.r2 = self.reg.r1

    def _setup(self, a, s):
        if self.cur is not None:
            self.cur['setup'] = self.reg.r0

    def _write(self, addr, data):
        for k in range(0, len(data), 4):
            self.mem.write_long(addr + k, struct.unpack_from('<I', data, k)[0])

    def _inject(self, a, s):
        c = self.cur
        if c is None or 'setup' not in c or c.get('injected'):
            return
        setup = c['setup']
        for side, key in ((0, 'player'), (1, 'enemy'), (3, 'enemy2')):    # client 3: trainer 2, when given
            if key not in c['mons']:
                continue
            party = self.mu.read_long(setup + 4 + 4 * side)
            mons = c['mons'][key]
            self.mem.write_long(party + 4, len(mons))
            for k, raw in enumerate(mons):
                self._write(party + 8 + 236 * k, raw)
            if side == 3:
                self.mem.write_byte(setup + 0x28 + 0x34 * 3 + 3, len(mons))
        trainer = setup + 0x5C
        self.mem.write_byte(trainer + 3, len(c['mons']['enemy']))
        for k in range(4):
            self.mem.write_short(trainer + 4 + 2 * k, c['items'][k] if k < len(c['items']) else 0)
        c['injected'] = True

    def _seed(self, a, s):
        if self.cur is not None and self.cur.get('injected'):
            self.mem.write_long(self.mu.read_long(MAIN_PTR) + RNG, self.cur['seed'])

    def _slot(self, a, s):
        if self.cur is not None:
            self.cur['slot'] = self.reg.r0

    def _setter(self, kind):
        def f(a, s):
            c = self.cur
            if c is None or c.get('slot') in NOT_AI or c.get('slot') is None:
                return
            if not (self.slot_range[0] <= self.reg.r14 < self.slot_range[1]):
                return
            # a move or item names its Pokemon; a switch names the field position (r1), 0 being the first foe's
            who = self.mu.read_long(self.reg.r13) & 0xFF if kind in ('move', 'item') else \
                FIRST_FOE_ID if kind == 'switch' and self.reg.r1 == 0 else None
            c['calls'].append((kind, self.reg.r1, self.reg.r2, who))
            if kind != 'none' and (not c.get('double') or who == FIRST_FOE_ID):
                c['done'] = True
                if c.get('slot') == AI_OVERLAY and self.debug_addr:
                    c['adv'] = self.read_debug()
        return f

    def read_debug(self, side=1):
        """The advanced AI's debug record of a side: 1 the trainer's; 0 the player's, which debug version 3 adds
        after it (before that the same bytes are the AI's working memory, which never holds the magic)."""
        mu, a = self.mu, self.debug_addr
        if side != 1:       # the player's record follows the trainer's, whose size depends on the version
            a += next((n for n in (DEBUG_SIZE_V4, DEBUG_SIZE) if mu.read_long(a + n) == DEBUG_MAGIC and
                       (mu.read_short(a + n + 4) >= 4) == (n == DEBUG_SIZE_V4)), DEBUG_SIZE)
        if mu.read_long(a) != DEBUG_MAGIC or (side != 1 and mu.read_short(a + 4) < 3):
            return {'magic': mu.read_long(a)}
        h = lambda o: mu.read_short(a + o)
        b = lambda o: mu.read_byte(a + o)
        side = lambda sp, hp, st, ty, lv, stt, ab, it, mv: {
            'species': h(sp), 'hp': h(hp), 'maxhp': h(hp + 2), 'stats': [h(st + 2 * i) for i in range(5)],
            'types': [b(ty + i) for i in range(3)], 'level': b(lv), 'status': b(stt), 'ability': h(ab), 'item': h(it),
            'moves': [h(mv + 2 * i) for i in range(4)]}
        n = b(112)
        opts = []
        for i in range(min(n, 16)):
            o = a + 120 + 8 * i
            v = mu.read_long(o + 4)
            opts.append([mu.read_byte(o), mu.read_byte(o + 1), mu.read_short(o + 2), v - (1 << 32) if v >> 31 else v])
        return {'polls': b(6), 'fallback': b(7), 'decisions': mu.read_long(a + 8),
                'me': side(12, 16, 24, 44, 50, 52, 54, 58, 62), 'opp': side(14, 20, 34, 47, 51, 53, 56, 60, 70),
                'd_mo': [h(78 + 2 * i) for i in range(4)], 'd_om': [h(86 + 2 * i) for i in range(4)],
                'f_mo': [h(94 + 2 * i) for i in range(4)], 'f_om': [h(102 + 2 * i) for i in range(4)],
                'weather': b(110), 'nbench': b(111), 'options': opts, 'chosen': b(113), 'trapped': b(114), 'doubles': b(115),
                'sim_unsure': b(116), 'legal': b(117), 'version': h(4),
                # debug version 2 (round 4): why the played option is not the top value, and the lost-position band
                'why': b(118) if h(4) >= 2 else 0, 'lost': b(119) if h(4) >= 2 else 0,
                # debug version 4 (round S1): the foe model (0-1000), the foe's likely switch-in and its case's weight (per-mille)
                'strong': h(248) if h(4) >= 4 else 0, 'sw_species': h(250) if h(4) >= 4 else 0,
                'sw_w': h(252) if h(4) >= 4 else 0,
                # debug version 5 (round S3): what my active's roles are worth at its HP (advai.c role_loss down to 0 HP)
                'role': h(254) if h(4) >= 5 else 0}

    def run(self, mons, items, seed, double=False, strong=False):
        self.cur = {'mons': mons, 'items': items, 'seed': seed, 'calls': [], 'failures': [], 'notes': [], 'done': False,
                    'double': double}
        start = self.r.frames
        to_battle(self.r, self.state)
        w = self.layout.words
        self.mem.write_long(w['NOLEAD_FLAG'], w['NOLEAD_MAGIC'])
        self.mem.write_long(w['NOREAD_FLAG'], w['NOREAD_MAGIC'])
        if strong:
            self._write(w['READS_AT'], STRONG_READ)
        while not self.cur['done'] and self.r.frames - start < FRAME_LIMIT and not self.r.frozen:
            self.r.hold('A', 4, release=4) if (self.r.frames - start) % 40 == 0 else self.r.step(1)
        c, self.cur = self.cur, None
        if not c.get('injected'):
            c['notes'].append('no battle; player at %s; screenshot %s' % (self.r.player_pos(), self.r.shot('no_battle_%d' % os.getpid())))
        final = [x for x in c['calls'] if x[0] != 'none' and (not double or x[3] == FIRST_FOE_ID)]
        return {'call': final[0] if final else (c['calls'][-1] if c['calls'] else None), 'diag': c.get('diag'),
                'adv': c.get('adv'), 'slot': c.get('slot'),
                'injected': bool(c.get('injected')), 'failures': c['failures'], 'notes': c['notes'],
                'frames': self.r.frames - start}


def approach(r, start, stop):
    """From the field state: walk up to the gym trainer and press A (4 frames every 40) until stop()."""
    r.run(['goto 15 14'])
    while not stop() and r.frames - start < FRAME_LIMIT and not r.frozen:
        # 4 frames: builds at 30 fps read input every other frame, so a 1-frame press every 40
        # frames always fell on the same phase and, from some save states, was never seen
        r.hold('A', 4, release=4) if (r.frames - start) % 40 == 0 else r.step(1)


def make_state(rom, path):
    """Boot the Violet Gym save into the field, then save the state a few frames before the trainer
    battle starts (SetupAndStartTrainerBattle), so a run skips the walk and the trainer's lines: more
    than half of its frames. Found by playing the approach once, then replaying the same inputs from the
    field and stopping short; if the replay does not land before the battle, the field state is kept
    (PATH.pre marks a pre-battle state). Per ROM: a state made with another build is not valid."""
    r = emu.Runner(rom, os.path.join(OUT, 'shots'))
    r.skip_render = True
    r.run(open(os.path.join(tbpaths.LIB, 'boot.txt')).read().splitlines())
    field = path + '.field'
    r.emu.savestate.save_file(field)
    fired = {}
    r.emu.memory.register_exec(TRAINER_BATTLE, lambda a, s: fired.setdefault('f', r.frames))
    start = r.frames
    approach(r, start, lambda: 'f' in fired)
    pre = path + '.pre'
    if os.path.exists(pre):
        os.remove(pre)
    if 'f' in fired:
        target = fired.pop('f') - start - 24
        r.emu.savestate.load_file(field)
        start = r.frames
        approach(r, start, lambda: 'f' in fired or r.frames - start >= target)
        if 'f' not in fired:
            r.emu.savestate.save_file(path)
            open(pre, 'w').write('%d frames before the battle setup\n' % (target + 24 - (r.frames - start)))
            os.remove(field)
            return
    r.emu.savestate.load_file(field)
    r.emu.savestate.save_file(path)
    os.remove(field)


def to_battle(r, state):
    """Load a bench state, then write the runner's AI setting (r.ai_setting: from ADVAI_AI_SETTING in Bench; None
    leaves the save's flags) into the save in RAM; from a field state (no PATH.pre), walk up to the trainer first."""
    r.emu.savestate.load_file(state)
    setting = getattr(r, 'ai_setting', None)
    if setting and not emu.set_ai_setting(r, setting):
        raise RuntimeError('no save in RAM after loading %s: the AI setting cannot be written' % state)
    if not os.path.exists(state + '.pre'):
        r.run(['goto 15 14'])


def worker(rom, state, jobs_path, out_path):
    d = Data(rom)
    template = open(os.path.join(OUT, 'template.bin'), 'rb').read()
    bench = Bench(rom, state)
    results = []
    by_id = {s['id']: s for s in scenarios()}
    for sid, rep in json.load(open(jobs_path)):
        sc = by_id[sid]
        seed = (hash_id(sid) * 7919 + rep * 104729) & 0xFFFFFFFF
        mons = {k: [build_mon(d, template, spec, seed + 31 * i) for i, spec in enumerate(sc[k])] for k in ('player', 'enemy')}
        items = [d.id('item', x) for x in sc.get('items', [])]
        t0 = time.time()
        for attempt in range(3):        # the walk from the save state now and then misses the trainer
            res = bench.run(mons, items, seed, bool(sc.get('double')), bool(sc.get('strong')))
            if res['injected']:
                break
        res['attempts'] = attempt + 1
        call = res['call']
        action = action_name(d, call[0], call[1], call[2], sc['enemy'], sc['player'] if sc.get('double') else None) if call else 'no decision'
        results.append({'id': sid, 'repeat': rep, 'seed': seed, 'action': action, 'grade': grade(sc, action) if call else 'error',
                        'call': call, 'diag': res['diag'], 'adv': res['adv'], 'slot': res['slot'],
                        'snapshot': snapshot_problems(d, sc, res['adv']) if res['adv'] else None,
                        'injected': res['injected'], 'failures': res['failures'],
                        'notes': res['notes'],
                        'frames': res['frames'], 'attempts': res['attempts'], 'seconds': round(time.time() - t0, 1)})
        with open(out_path, 'w') as f:
            json.dump(results, f)


def hash_id(s):
    h = 2166136261
    for ch in s.encode():
        h = (h ^ ch) * 16777619 & 0xFFFFFFFF
    return h


def template_mon():
    """A valid party Pokémon to build on (the Violet Gym save's first one)."""
    from savetool import PARTY, Save
    s = Save(saves.path('violet_gym'))
    off = s.base + PARTY
    return bytes(s.data[off:off + 236])


def data_skips(d):
    """{scenario id: why} of SPANISH_DATA's scenarios this ROM's data cannot hold."""
    return {sid: why for sid, (species, want, why) in SPANISH_DATA.items()
            if any(d.species(species)['base'][k] != v for k, v in want.items())}


def select(names, all_sc):
    """Scenarios by id, category or batch ('batch:3'; batch 0 is the original set)."""
    if not names:
        return all_sc
    return [s for s in all_sc if s['id'] in names or s['cat'] in names or 'batch:%d' % s.get('batch', 0) in names]


def snapshot_problems(d, sc, adv):
    """What the advanced AI read against what the scenario set up: its active Pokemon is the
    scenario's enemy[0], its opponent the player's [0]."""
    out = []
    if 'me' not in adv:
        return ['no debug record (magic %s)' % adv.get('magic')]
    status = {None: 0, 'par': 1, 'slp': 2, 'frz': 3, 'brn': 4, 'psn': 5, 'tox': 5}
    for side, spec in (('me', sc['enemy'][0]), ('opp', sc['player'][0])):
        v, got = mon_view(d, spec), adv[side]
        want = {'species': d.id('species', spec['species']), 'hp': v['cur_hp'], 'maxhp': v['stats']['hp'],
                'stats': [v['stats'][k] for k in ('atk', 'def', 'spa', 'spd', 'spe')], 'level': v['level'],
                'ability': d.id('ability', spec['ability']) if spec.get('ability') else got['ability'],
                'status': status[spec.get('status')],
                'moves': [d.id('move', m) for m in spec['moves']] + [0] * (4 - len(spec['moves']))}
        for k, w in want.items():
            if got[k] != w:
                out.append('%s.%s read %s, set %s' % (side, k, got[k], w))
    return out


def link_rom(rom, path):
    """`path` as a symlink to `rom` (DeSmuME names the battery save after the file it opens, so each worker opens its
    own name; the Spanish tools copied the ROM)."""
    if os.path.lexists(path):
        os.remove(path)
    os.symlink(os.path.abspath(rom), path)
    return path


def setting_save(setting, out, options=False):
    """The Violet Gym save with the AI setting's flags (and with options: no move animations, fast text), written to
    `out`; and ADVAI_AI_SETTING, which every state load then writes into the save in RAM (to_battle). The flags go
    into the battery too, as the Spanish tools set them: the pre-battle state is made from this save, and with them
    clear in the battery rc44 reached 3 of 365 bench decisions one frame earlier or later (same decisions)."""
    from savetool import Save
    os.environ[SETTING_ENV] = setting
    sv = Save(saves.path('violet_gym'))
    on, important = emu.AI_SETTINGS[setting]
    sv.set_flag(emu.FLAG_AI, on)
    sv.set_flag(emu.FLAG_AI_IMPORTANT, important)
    if options:
        sv.set_options(battle_scene_off=True, battle_style_set=True, text_speed=2)
    sv.write(out)
    return out


def run_bench(rom, chosen, repeats, workers, tag, advanced=False):
    os.makedirs(OUT, exist_ok=True)
    save = setting_save('all' if advanced else 'off', os.path.join(OUT, 'bench_save_%s.dsv' % tag))
    with open(os.path.join(OUT, 'template.bin'), 'wb') as f:
        f.write(template_mon())
    rom_copy = link_rom(rom, os.path.join(OUT, 'bench_%s.nds' % tag))
    dsv = os.path.join(DSV_DIR, 'bench_%s.dsv' % tag)
    shutil.copy(save, dsv)
    state = os.path.join(OUT, 'bench_%s.dst' % tag)

    def go(k, jobs_k):
        # each worker its own ROM copy, so its own battery save in DSV_DIR
        rom_k, dsv_k = os.path.join(OUT, 'bench_%s_%s.nds' % (tag, k)), os.path.join(DSV_DIR, 'bench_%s_%s.dsv' % (tag, k))
        link_rom(rom, rom_k)
        shutil.copy(save, dsv_k)
        jp, op = os.path.join(OUT, 'jobs_%s_%s.json' % (tag, k)), os.path.join(OUT, 'res_%s_%s.json' % (tag, k))
        json.dump(jobs_k, open(jp, 'w'))
        if os.path.exists(op):
            os.remove(op)
        subprocess.run([sys.executable, __file__, '--worker', rom_k, state, jp, op],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for p in (rom_k, dsv_k):
            os.remove(p)
        return json.load(open(op)) if os.path.exists(op) else []
    probe = [(chosen[0]['id'], 0)]
    for attempt in range(3):            # the state must reach a battle before anything is run from it
        subprocess.run([sys.executable, __file__, '--make-state', rom_copy, state],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # one emulator per process
        if any(x.get('injected') for x in go('probe', probe)):
            break
    else:
        sys.exit('the save state never reaches the trainer battle (see %s/no_battle_*.png)' % tbpaths.rel(os.path.join(OUT, 'shots')))
    jobs = [(s['id'], r) for s in chosen for r in range(repeats)]
    chunks = [jobs[k::workers] for k in range(workers) if jobs[k::workers]]
    with ThreadPoolExecutor(len(chunks)) as pool:
        results = [x for part in pool.map(lambda k: go(k, chunks[k]), range(len(chunks))) for x in part]
    for p in (rom_copy, dsv):
        if os.path.lexists(p):
            os.remove(p)
    done = {(x['id'], x['repeat']) for x in results}
    for sid, rep in jobs:
        if (sid, rep) not in done:
            results.append({'id': sid, 'repeat': rep, 'action': 'no result', 'grade': 'error', 'failures': ['worker died']})
    return results


def report(chosen, results):
    by = {}
    for x in results:
        by.setdefault(x['id'], []).append(x)
    cats, lines = {}, []
    points = {'pass': 1.0, 'ok': 0.5, 'miss': 0.0, 'blunder': 0.0, 'error': 0.0}
    for sc in chosen:
        rs = sorted(by.get(sc['id'], []), key=lambda x: x['repeat'])
        for x in rs:                    # graded now, so a fixed answer key needs no rerun
            x['grade'] = grade(sc, x['action'])
        score = sum(points[x['grade']] for x in rs) / max(1, len(rs))
        c = cats.setdefault(sc['cat'], {'n': 0, 'score': 0.0, 'blunders': 0, 'errors': 0})
        c['n'] += 1
        c['score'] += score
        c['blunders'] += sum(x['grade'] == 'blunder' for x in rs)
        c['errors'] += sum(x['grade'] == 'error' or bool(x.get('failures')) for x in rs)
        acts = {}
        for x in rs:
            acts[x['action']] = acts.get(x['action'], 0) + 1
        lines.append('%-34s %-10s %4.0f%%  %s%s' % (sc['id'], sc['cat'], 100 * score,
                     ', '.join('%s x%d (%s)' % (a, n, next(x['grade'] for x in rs if x['action'] == a)) for a, n in acts.items()),
                     '  FAILURES ' + str(sorted({f for x in rs for f in x.get('failures', [])})) if any(x.get('failures') for x in rs) else ''))
    lines.append('')
    total = sum(c['score'] for c in cats.values())
    for cat, c in sorted(cats.items()):
        lines.append('%-12s %3d scenarios  score %5.1f%%  blunders %d  errors %d' % (
            cat, c['n'], 100 * c['score'] / c['n'], c['blunders'], c['errors']))
    lines.append('TOTAL        %3d scenarios  score %5.1f%%' % (len(chosen), 100 * total / max(1, len(chosen))))
    adv = [x for x in results if x.get('slot') == AI_OVERLAY]
    if adv:
        fb = collections.Counter(x['adv'].get('fallback') for x in adv if x.get('adv'))
        snap = [(x['id'], p) for x in adv for p in (x.get('snapshot') or [])]
        lines.append('advanced AI: %d of %d decisions from overlay %d; fallback codes %s; snapshot mismatches %d%s' % (
            len(adv), len(results), AI_OVERLAY, dict(fb), len(snap), ' e.g. %s' % snap[:6] if snap else ''))
        lines.append('             polls max %d' % max((x['adv'] or {}).get('polls', 0) for x in adv))
    return '\n'.join(lines)


def speed(v):
    return v['stats']['spe'] // (2 if v['status'] == 'par' else 1)


def run_check(d, views, c):
    """One scenario claim against the ROM's data. Refs: e0, e1, ... the AI's Pokémon (e0 active),
    p0, p1, ... the player's."""
    ref = lambda r: views['enemy' if r[0] == 'e' else 'player'][int(r[1:])]
    op = c[0]
    if op == 'eff':
        _, a, mv, df, want = c
        got = d.effectiveness(mv, ref(df))
        assert got == want, '%s vs %s: effectiveness %s, claimed %s' % (mv, ref(df)['species'], got, want)
    elif op in ('ko', 'noko'):
        _, a, mv, df = c
        lo, hi = d.damage(mv, ref(a), ref(df))
        hp = ref(df)['cur_hp']
        if op == 'ko':      # 10% margin: damage() approximates the engine
            assert lo * 0.9 >= hp, '%s does %d-%d to %s at %d HP: not a sure KO' % (mv, lo, hi, ref(df)['species'], hp)
        else:
            assert hi * 1.1 < hp, '%s does %d-%d to %s at %d HP: can KO' % (mv, lo, hi, ref(df)['species'], hp)
    elif op == 'noko_at':
        _, a, mv, df, frac = c
        lo, hi = d.damage(mv, ref(a), ref(df))
        hp = int(ref(df)['stats']['hp'] * frac)
        assert hi * 1.1 < hp, '%s does %d-%d: can KO %s from %d HP' % (mv, lo, hi, ref(df)['species'], hp)
    elif op == 'beats':
        _, a, m1, m2, df = c
        d1, d2 = d.damage(m1, ref(a), ref(df)), d.damage(m2, ref(a), ref(df))
        assert d1[0] > d2[1] * 1.05, '%s %s does not clearly out-damage %s %s' % (m1, d1, m2, d2)
    elif op == 'faster':
        _, x, y = c
        assert speed(ref(x)) > speed(ref(y)), '%s (%d) is not faster than %s (%d)' % (
            ref(x)['species'], speed(ref(x)), ref(y)['species'], speed(ref(y)))
    elif op == 'cls':
        _, mv, want = c
        got = ['status', 'physical', 'special'][d.move(mv)['class']]
        assert got == want, '%s is %s, claimed %s' % (mv, got, want)
    elif op == 'pri':
        _, mv, want = c
        assert d.move(mv)['priority'] == want, '%s priority %d, claimed %d' % (mv, d.move(mv)['priority'], want)
    elif op == 'acc_lt':
        _, mv, want = c
        assert d.move(mv)['accuracy'] < want, '%s accuracy %d, claimed under %d' % (mv, d.move(mv)['accuracy'], want)
    elif op == 'type':
        _, r, t = c
        assert TYPES.index(t) in ref(r)['types'], '%s is not %s' % (ref(r)['species'], t)
    else:
        import ai_checks           # ops the scenario authors added (tests/ai_checks.py)
        if op not in ai_checks.CHECKS:
            raise AssertionError('unknown check %r' % (c,))
        ai_checks.CHECKS[op](d, views, c, ref)


def scores(results):
    """{scenario: (score 0-1, blunders, actions Counter)} regraded with the current answer key."""
    by_sc = {sc['id']: sc for sc in scenarios()}
    points = {'pass': 1.0, 'ok': 0.5, 'miss': 0.0, 'blunder': 0.0, 'error': 0.0}
    out = {}
    for x in results:
        if x['id'] not in by_sc:
            continue
        g = grade(by_sc[x['id']], x['action'])
        sc, bl, acts = out.get(x['id'], (0.0, 0, collections.Counter()))
        acts[x['action']] += 1
        out[x['id']] = (sc + points[g], bl + (g == 'blunder'), acts)
    return {k: (v[0] / sum(v[2].values()), v[1], v[2]) for k, v in out.items()}


def compare(a, b):
    ra = scores(json.load(open(os.path.join(BASELINES, a + '.json')))['results'])
    rb = scores(json.load(open(os.path.join(BASELINES, b + '.json')))['results'])
    chosen = [sc for sc in scenarios() if sc['id'] in ra and sc['id'] in rb]
    cats = collections.OrderedDict()
    for sc in chosen:
        c = cats.setdefault(sc['cat'], [0, 0.0, 0.0, 0, 0])
        c[0] += 1
        c[1] += ra[sc['id']][0]
        c[2] += rb[sc['id']][0]
        c[3] += ra[sc['id']][1]
        c[4] += rb[sc['id']][1]
    lines = ['| Category | Scenarios | %s | %s | Blunders %s | Blunders %s |' % (a, b, a, b), '|---|---|---|---|---|---|']
    tot = [0, 0.0, 0.0, 0, 0]
    for cat, c in cats.items():
        lines.append('| %s | %d | %.1f%% | %.1f%% | %d | %d |' % (cat, c[0], 100 * c[1] / c[0], 100 * c[2] / c[0], c[3], c[4]))
        tot = [t + v for t, v in zip(tot, c)]
    lines.append('| **all** | %d | **%.1f%%** | **%.1f%%** | %d | %d |' % (tot[0], 100 * tot[1] / tot[0], 100 * tot[2] / tot[0], tot[3], tot[4]))
    lines += ['', 'Scenarios where they differ (score, the actions taken):', '']
    for sc in chosen:
        x, y = ra[sc['id']], rb[sc['id']]
        if abs(x[0] - y[0]) > 1e-9:
            fmt = lambda r: ', '.join('%s x%d' % (k, n) for k, n in r[2].most_common())
            lines.append('- `%s` (%s): %s %.0f%% (%s) / %s %.0f%% (%s)' % (sc['id'], sc['desc'], a, 100 * x[0], fmt(x), b, 100 * y[0], fmt(y)))
    return '\n'.join(lines)


def check(rom):
    """Every scenario's checks against the ROM's data, plus names, moves and answers that exist."""
    d = Data(rom)
    problems = []
    ids, situations = set(), {}
    skips = data_skips(d)
    for sc in scenarios():
        sid = sc['id']
        if sid in ids:
            problems.append('%s: duplicate id' % sid)
        ids.add(sid)
        if sid in skips:
            continue
        sig = json.dumps([sc['player'], sc['enemy'], sorted(sc.get('items', [])), bool(sc.get('double'))] +
                         ([True] if sc.get('strong') else []), sort_keys=True)
        if sig in situations:
            problems.append('%s: the same situation as %s' % (sid, situations[sig]))
        situations.setdefault(sig, sid)
        try:
            views = {k: [mon_view(d, m) for m in sc[k]] for k in ('player', 'enemy')}
            for k in ('player', 'enemy'):
                for m in sc[k]:
                    for x in m['moves']:
                        d.id('move', x)
                    for f in ('ability',):
                        if m.get(f):
                            d.id('ability', m[f])
                    if m.get('item'):
                        d.id('item', m['item'])
            moves = {norm(x) for x in sc['enemy'][0]['moves']}
            for g, acts in sc['expect'].items():
                for a in acts:
                    if a.startswith('switch:'):
                        assert any(norm(m['species']) == norm(a[7:]) for m in sc['enemy'][1:]), 'no bench ' + a
                    elif a.startswith('item:'):
                        assert norm(a[5:]) in {norm(x) for x in sc.get('items', [])}, 'trainer has no ' + a
                    else:
                        mv, _, tgt = a.partition('>')
                        assert norm(mv) in moves, '%s answer %r is not a move of the active foe' % (g, a)
                        if tgt:
                            assert sc.get('double') and any(norm(p['species']) == norm(tgt) for p in sc['player'][:2]), \
                                'target %r is not one of the player\'s two Pokemon in a double' % tgt
            for c in sc.get('checks', []):
                run_check(d, views, c)
        except (AssertionError, KeyError) as e:
            problems.append('%s: %s' % (sid, e))
    return problems


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:6])
    if sys.argv[1:2] == ['--make-state']:
        return make_state(*sys.argv[2:4])
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*')
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', help='the AI build\'s payload.json (default: ADVAI_PAYLOAD); not needed for --check, '
                    '--report, --compare')
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--workers', type=int, default=7)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--save')
    ap.add_argument('--advanced', action='store_true', help='set the NPC flag (0x2C2): battles use the advanced AI')
    ap.add_argument('--merge', help='rerun the chosen scenarios and replace their results in qa/aibench/NAME.json')
    ap.add_argument('--report', help='regrade and print qa/aibench/NAME.json without running anything')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'), help='regrade two saved runs and compare them (qa/aibench/A_vs_B.md)')
    a = ap.parse_args()
    skips = data_skips(Data(a.rom))
    for sid, why in sorted(skips.items()):
        print('left out on this ROM: %s (%s)' % (sid, why))
    if a.check:
        problems = check(a.rom)
        print('\n'.join(problems) or 'all %d scenarios check out' % (len(scenarios()) - len(skips)))
        sys.exit(1 if problems else 0)
    problems = check(a.rom)
    if problems:
        print('\n'.join(problems))
        sys.exit('scenario checks failed: fix them first (--check)')
    if a.compare:
        text = compare(*a.compare)
        print(text)
        with open(os.path.join(BASELINES, '%s_vs_%s.md' % tuple(a.compare)), 'w') as f:
            f.write(text + '\n')
        return
    if a.report:
        saved = json.load(open(os.path.join(BASELINES, a.report + '.json')))
        text = report(scenarios(), saved['results'])
        print(text)
        with open(os.path.join(BASELINES, a.report + '.txt'), 'w') as f:
            f.write(text + '\n')
        with open(os.path.join(BASELINES, a.report + '.json'), 'w') as f:
            json.dump(saved, f, indent=1)
        return
    payload.path_from(a.payload)            # exported for the workers
    chosen = [sc for sc in select(a.names, scenarios()) if sc['id'] not in skips]
    # runs on different ROMs at once must not share work files (ROM links, battery saves, results)
    tag = os.path.splitext(os.path.basename(a.rom))[0]
    t0 = time.time()
    tag += '_adv' if a.advanced else ''
    results = run_bench(a.rom, chosen, a.repeats, a.workers, tag, a.advanced)
    if a.merge:
        old = json.load(open(os.path.join(BASELINES, a.merge + '.json')))
        redone = {s['id'] for s in chosen}
        results = [x for x in old['results'] if x['id'] not in redone] + results
        chosen, a.save = scenarios(), a.merge
    text = report(chosen, results)
    print(text)
    print('%d runs in %.0f s' % (len(results), time.time() - t0))
    name = a.save or 'last_%s' % tag
    import hashlib
    saved = {'rom': os.path.basename(a.rom), 'rom_sha1': hashlib.sha1(open(a.rom, 'rb').read()).hexdigest(),
             'repeats': a.repeats, 'advanced': a.advanced, 'results': results}
    with open(os.path.join(OUT, name + '.json'), 'w') as f:
        json.dump(saved, f, indent=1)
    if a.save:
        os.makedirs(BASELINES, exist_ok=True)
        with open(os.path.join(BASELINES, a.save + '.json'), 'w') as f:
            json.dump(saved, f, indent=1)
        with open(os.path.join(BASELINES, a.save + '.txt'), 'w') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main()
