"""AI vs AI: the advanced AI (the trainer's side) against the original AI (the player's side), teams of six,
played to the end. Plan and data shapes: the Spanish workspace's qa/aivsai_plan.md.

  .venv/bin/python work/advanced-ai/testbench/versus/aivsai.py N --rom ROM --payload PAYLOAD [--live]
             [--teams trainers|mixed|random] [--level L] [--seed S] [--workers W] [--control | --self]
             [--adv-size N] [--orig-size M] [--sizes N:M] [--pick first|random] [--reseed K|A-B,...] [--log-dir DIR]

Ported from the Spanish workspace's tools/aivsai.py (dc8577c). Changes:
- the AI-build addresses (ADV_CODE, ORIG_CODE, SELFPLAY_FLAG, FS_WORD_AT, REPLACED_AT, the tuning table) come from
  the payload (lib/payload.py); other modules still read them as aivsai.ADV_CODE etc.;
- the ROM is never changed: no speed toggle (--speed is gone; the battles run at the ROM's own speed, as fast as the
  emulator goes), and each worker opens a symlink of the ROM;
- the AI setting is written into the save in RAM after every state load (lib/emu.py set_ai_setting), besides the
  battery save; the Violet Gym save comes from lib/saves.py; the teams are drawn from --rom;
- the battle's own verdict is read in English and in Spanish (OUTCOMES), and a failure's move message in both;
- files: RUNS/aivsai/ (work files), RUNS/aivsai/reports/ (reports, battle logs under runs/), or --log-dir.

N scenarios, each two teams of six. Without --live every scenario is played twice with the teams swapped,
on parallel emulators with no window, and a report is written to qa/aivsai/report_<date>.md. With --live
one emulator plays each scenario once in a window at normal speed and the terminal shows every decision.
--control plays the original AI on both sides (a fairness check: it should win about half its games).
--self plays the advanced AI on both sides, to find its mistakes: each side's decisions are logged with its own
weighed options, and its replacements after a faint with the values ai_replace gave the candidates. The win rate
is not progress (that is always measured against the original AI); the sizes then mean trainer side / player side.
--adv-size and --orig-size (or --sizes N:M) cut the advanced side's team to N and the original side's to M
(default 6 each): a handicap for the advanced AI. The sizes stay with the AIs when the teams swap: game 0 is
team A cut to N against team B cut to M, game 1 team B cut to N against team A cut to M. --pick first keeps
each team's first members (the lead stays); --pick random keeps a subset drawn from the scenario's seed.
Every battle's log (and the live view) has each turn's Pokémon with HP, status and stat stages, the weather,
both decisions, and the battle's own messages as the game prints them (misses, crits, items, abilities).

How: the bench's save state just before a trainer battle (tools/aibench.py), both teams written into the
battle setup; the player's side handed to the AI by pointing its two controller-table entries (choose an
action, choose a replacement) at the AI's routines in emulator memory; with the advanced AI switched on
both AIs are in memory (overlay 10 holds overlay 11 byte for byte), and around the player side's AI call
the slot word is set to 11 so the dispatcher sends it to the original AI. No change to the ROM. With --self the
slot word stays 10 and the magic word at SELFPLAY_FLAG makes ai_replace serve the player's side too.

Luck (--rng): the battle RNG is one 32-bit LCG at [main]+0x24C (BattleRandom 0x0222646C), and the AIs' thinking
draws from it too (in a measured 6v6 battle about 1,450 draws inside AI calls against the battle's 80; the advanced
AI's option values do not depend on them). With 'legacy' (the only mode before 2026-10-04) the bench seeds it once
per battle, so two builds whose AIs think differently get different luck from the first turn on, even when they
decide the same. With 'synced' (the default) each selection phase k reseeds it from (game seed, k), and every AI call
(AI_POLL, REPLACE_CALL) runs on its side's own stream, swapped in for the call and out after it: the battle's rolls
depend on the game seed and the actions taken, never on how the AIs think. Two builds then share their luck until
their decisions differ, and after that phase k still starts from the same rolls in both. The advanced AI's foresight
(rc29) predicts the turn's rolls from the battle's word: with 'synced' the call gets that word at FS_WORD_AT (the other
side's thinking draws from its own stream, so the prediction holds); with 'legacy' the AI trusts the live word only once
the other side has answered its choice (overlay 11 draws while it decides). 'synced' also writes the battle setup's
seed (BattleSetup+0x19C, SETUP_SEED) from the game seed: the game makes it from the RTC and the VBlank counter
(0x02050D40), and the pre-battle state's VBlank counter differs by build (boot timing: 2,526 and 2,530 for two builds
that differ only in the main arena's start), and the advanced AI's read draw (RD's rd_draw) is seeded from it (rc34
LAYOUT). The emulator's clock is
pinned too (tools/emu.py), so the same build replays a game line for line. --reseed K (or a list, 0-9) plays each
game once per K with other luck and the same teams, sides and sizes: reseed 0 is the game seed's own luck (every run
before --reseed), any other K draws the luck from a mix of the game seed and K (luck_seed).

Tuning (tools/aitune.py): a build with tools/ai/tune.h has a table of the AI's judgment constants in arm9's ITCM
block (find_tune), one copy per side. A game dict may carry 'tune': {'trainer': [u16 x n], 'player': [u16 x n]};
play() writes both copies after every state load and reads them back (a mismatch is a 'tune ...' failure, and
aitune excludes the game), and its result records the two vectors' ids (tune_id) and the game's 'x_side'.
"""
import logging
logging.getLogger().addHandler(logging.NullHandler())   # this Python's hashlib logs a harmless blake2 traceback on import
import argparse  # noqa: E402
import collections  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import aibench  # noqa: E402
import emu  # noqa: E402
import failures  # noqa: E402
import payload  # noqa: E402
from aidata import Data  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'aivsai')
REPORTS = os.path.join(OUT, 'reports')
# the battle engine picks each client's routines from TABLE[kind][type] (0x022014B8; type byte at client+0:
# 0 the player's menus, 1 an AI); kind 2 chooses an action, kind 4 a replacement after a faint
TABLE = 0x0224AB70
SELECT, REPLACE = TABLE + 2 * 8, TABLE + 4 * 8
HUMAN_SELECT, AI_SELECT, HUMAN_REPLACE, AI_REPLACE = 0x02203655, 0x0220368D, 0x02203F01, 0x02203B61
AI_POLL, AI_POLL_RET = 0x02203736, 0x0220373A       # the client's call into the AI (r4 client, r1 its AI state)
CLIENT_SIDE = 2                                     # byte of the client: 0 the player's, 1 the trainer's
# ORIG_CODE (overlay 11's copy in overlay 10) and ADV_CODE (the AI's code in the slot): Layout.orig_code / adv_code
REPLACE_LR = 0x02203C23                             # the engine's replacement chooser calling the switch setter
                                                    # (r5 its client: the side whose Pokémon fainted, also when both did)
REPLACE_CALL, REPLACE_RET = 0x02203C06, 0x02203C0A  # the client's call into the replacement chooser (r5 its client)
RNG_MODES = ('synced', 'legacy')                    # --rng: see Luck above
MAIN_SLOT = 0x26C
# src/engine.h, in ITCM RAM (which every state load restores, so both are written after each load): SELFPLAY_FLAG, the
# magic that makes ai_replace serve the player's side too, and REPLACED_AT, replace.c's records of each side's last
# replacement; synced luck only: FS_WORD_AT, while an AI call runs on its side's stream, the battle's word it set aside,
# for the advanced AI's foresight (the magic, then the word; cleared when the call returns). Their addresses come from
# the payload (Layout.words): other modules read them as aivsai.SELFPLAY_FLAG etc. (module __getattr__ below).
REPLACED_SIZE, MAX_BENCH = 32, 5        # per side, the trainer's first: seq, n, orig[5], out[5], v[5]
LAZY = {'SELFPLAY_FLAG', 'SELFPLAY_MAGIC', 'FS_WORD_AT', 'FS_WORD_MAGIC', 'REPLACED_AT'}
MODES = ('adv', 'control', 'self')                          # the advanced AI against the original, original x2, advanced x2
FRAME_LIMIT = 108000                                # 30 minutes of game time
# The evolution scene's touch menu (arm9): r1 = 1 for Forget a move! / Keep old moves! (195:1181/1182), 0 for the give-up
# question's. After a won battle a Pokemon that evolves may be offered a move with four known; A would pick Forget
# and then press A on an HM in the summary until the frame limit, so from the first menu to the second the runner
# presses B (keep the old moves) and the next A gives up the move.
EVO_MENU = 0x02073E18
SIDES = ('original', 'advanced')                    # by client side: 0 the player's, 1 the trainer's (with --self too)
# what a turn line shows of each active Pokémon, read from its battle Pokémon (each checked against the game's messages)
SICK = 0x3C            # condition words 8 bytes apart: condition i at +0x3C + 8 i, on while its low 3 bits are set
STATUSES = {1: 'PAR', 2: 'SLP', 3: 'FRZ', 4: 'BRN', 5: 'PSN'}   # the main status: the first of 1-5 that is on
                                                                # (BPP_GetPokeSick 0x02216C64); poison 1, bad poison 0x1E79
CONFUSION = 6
STAGES, STAGE_NAMES = 0x240, ('Atk', 'Def', 'SpA', 'SpD', 'Spe', 'Acc', 'Eva')    # 6 = no change
MAIN_FIELD = 0x58      # main+0x58 points to the field state: byte 0 the weather, byte 1 its length in turns, byte 3 turns gone
WEATHERS = {1: 'rain', 2: 'sun', 3: 'sand', 4: 'hail'}
NO_LIMIT = 0xFF
# battle messages: the text printers into these windows (width, height in tiles) while overlay 14 is loaded
MSG_BOX = (27, 4)      # the battle message box
ABILITY_BOX = (15, 5)  # an ability pop-up: printed twice, the ability, then the Pokémon
REPEAT_FRAMES = 20     # the same text again this soon is the same message printed again, not a new one
DAMAGE_CMD = 8         # the battle client command of a hit (its damage is already taken off the HP)
FAINT_CMD = 21         # the battle client command of a faint: it runs after the messages of the hit that caused it
FULL_TEAM = 6
# The battle's own verdict, per language of the ROM: (the player's side won: the message starts with this; the
# player's side is out: the message holds this, unless the bench trainer's name comes before it). The bench save's
# trainer is #71, 'Policía Felix' in the Spanish build, Felix in ours.
OUTCOMES = (('¡Derrotaste a', 'no le quedan Pokémon', '¡A Policía Felix'),       # Spanish rc44
            ('You defeated', 'is out of usable', 'Felix'))                       # English (battle_string 2: 35, 45)
# the tuning table (src/tune.h, g_tune in section .itcm.tune): u32 magic "TUNE", u16 version, u16 n, then
# u16 v[2][n], v[0] the trainer side's (the AI picks its copy by (client & 1) ^ 1). The game copies arm9's autoload
# block to ITCM at boot and never writes the table; every state load restores it, so play() writes it after each.
# Its address is the payload's g_tune; without one, the Spanish scan of the ITCM block at ITCM_BASE.
ITCM_BASE = 0x01FF8000           # arm9's ITCM autoload block
TUNE_MAGIC, TUNE_HEAD, TUNE_MAX = 0x454E5554, 8, 64
TUNE_SIDES = ('trainer', 'player')
TuneTable = collections.namedtuple('TuneTable', 'addr version defaults')   # defaults: the compiled values, v[0]
KEPT_EVENTS = ('turn', 'decision', 'switch')    # what logged_play keeps in the result for game['keep_events']
# test only: ADVAI_STEER_TEST, a comma list; 'mark=0' or 'mark=1' clears or sets the trainer's important mark
# (BattleSetup trainer header byte 2 bit 0, client 1) after the teams are injected. Unset: the battles are as before.
# Child processes inherit it. (The Spanish ES_STEER_TEST also had 'hard', hard mode for its luck steering, which is
# not ported.)
SETUP_MARK = 0x2A + 0x34        # client 1's header byte 2 in the BattleSetup (src/aiselect.s)
SETUP_SEED = 0x19C               # the BattleSetup's battle seed (RTC + VBlank counter, 0x02050D40)


def layout():
    return payload.load()


def __getattr__(name):
    lay = layout()
    if name in LAZY:
        return lay.words[name]
    if name == 'ADV_CODE':
        return lay.adv_code
    if name == 'ORIG_CODE':
        return lay.orig_code
    raise AttributeError(name)


def steer_test():
    """ADVAI_STEER_TEST as {key: value}: {'mark': '0'} for 'mark=0'."""
    spec = os.environ.get('ADVAI_STEER_TEST', '')
    return dict(p.split('=', 1) if '=' in p else (p, '1') for p in spec.split(',') if p)


class TuneError(ValueError):
    """A tuning table whose header or copies do not hold together."""


def tune_in_itcm(itcm):
    """The tuning table in the bytes of an ITCM block loaded at ITCM_BASE: a TuneTable, or None when no 4-aligned
    magic starts a well-formed table (version 1 or more, 1 to TUNE_MAX entries, inside the block). A well-formed
    table whose two copies differ, or two well-formed tables, raise TuneError."""
    magic, found = struct.pack('<I', TUNE_MAGIC), []
    at = itcm.find(magic)
    while at >= 0:
        if at % 4 == 0 and at + TUNE_HEAD <= len(itcm):
            version, n = struct.unpack_from('<HH', itcm, at + 4)
            if version >= 1 and 1 <= n <= TUNE_MAX and at + TUNE_HEAD + 4 * n <= len(itcm):
                v = list(struct.unpack_from('<%dH' % (2 * n), itcm, at + TUNE_HEAD))
                found.append((at, version, v[:n], v[n:]))
        at = itcm.find(magic, at + 1)
    if len(found) > 1:
        raise TuneError('%d tuning tables in the ITCM block (at %s)' % (
            len(found), ', '.join('%08X' % (ITCM_BASE + f[0]) for f in found)))
    if not found:
        return None
    at, version, v0, v1 = found[0]
    if v0 != v1:
        raise TuneError('the tuning table at %08X has two different copies: %s and %s' % (ITCM_BASE + at, v0, v1))
    return TuneTable(ITCM_BASE + at, version, v0)


def find_tune(rom, at=None):
    """The tuning table of the ROM file at `rom`, read from arm9's autoload sections with ndspy: at `at` (default the
    payload's g_tune, when a payload is given), else the Spanish scan of the ITCM block. TuneTable(addr, version,
    defaults), or None for a build without one (TuneError: a broken one)."""
    import ndspy.code
    with open(rom, 'rb') as f:
        off, _, ram, size = struct.unpack_from('<IIII', f.read(0x30), 0x20)
        f.seek(off)
        arm9 = f.read(size)
    sections = [(s.ramAddress, bytes(s.data)) for s in ndspy.code.MainCodeFile(arm9, ram).sections]
    if at is None and os.environ.get(payload.ENV):
        at = layout().tune
    if at is None:
        return tune_in_itcm(next((data for base, data in sections if base == ITCM_BASE), b''))
    base, data = next(((b, d) for b, d in sections if b <= at < b + len(d)), (None, None))
    if base is None:
        raise TuneError('no autoload section holds the tuning table at %08X' % at)
    found = tune_in_itcm(data[at - base:at - base + TUNE_HEAD + 4 * TUNE_MAX])
    if found is None or found.addr != ITCM_BASE:
        raise TuneError('no tuning table at %08X' % at)
    return TuneTable(at, found.version, found.defaults)


def tune_id(values):
    """A tuning vector's short id: the first 8 hex digits of the SHA-1 of its values joined by commas."""
    return hashlib.sha1(','.join(str(v) for v in values).encode()).hexdigest()[:8]


TEXT_CODE = re.compile(r'\\[nrf]|\\[{}\\]|\{[^{}]*\}')    # tools/gen4text.py's codes_to_text escapes and commands


def battle_text(raw):
    """A printed message on one line: line and page breaks and the alternate space as spaces, the other control
    codes (colors, cursor) dropped."""
    def code(m):
        t = m.group(0)
        if t in ('\\n', '\\r', '\\f', '{U:01FB}'):
            return ' '
        return t[1] if t[0] == '\\' else ''
    return ' '.join(TEXT_CODE.sub(code, raw or '').split())


class quiet:
    """Silence the emulator's own C-level prints (device lines, 'Savestate info') on stdout."""

    def __enter__(self):
        sys.stdout.flush()
        self.saved, self.null = os.dup(1), os.open(os.devnull, os.O_WRONLY)
        os.dup2(self.null, 1)

    def __exit__(self, *exc):
        sys.stdout.flush()
        os.dup2(self.saved, 1)
        os.close(self.null)
        os.close(self.saved)


class Duel(aibench.Bench):
    """One emulator playing AI-vs-AI battles from the bench's pre-battle state."""

    def __init__(self, rom, state, mode='adv', live=None):
        assert mode in MODES, mode
        with quiet():
            super().__init__(rom, state)
        self.mode, self.live = mode, live            # live: where the events go (the window's log, or a battle's log file)
        lay = self.layout
        self.adv_code, self.orig_code, self.words = lay.adv_code, lay.orig_code, lay.words
        if mode == 'self':
            import aivsai_live
            aivsai_live.use_side_names(True)
        self.window = False                          # a window shows every frame; headless draws one frame in 30
        self.r.skip_render = True
        self.d = Data(rom)
        self.mem.register_exec(AI_POLL, self._poll)
        self.mem.register_exec(AI_POLL_RET, self._poll_ret)
        self.mem.register_exec(REPLACE_CALL, self._replace_call)
        self.mem.register_exec(REPLACE_RET, self._leave_ai)
        self.mem.register_exec(emu.ADD_PRINTER, self._printer)      # in place of the runner's hook, which it calls
        self.mem.register_exec(emu.BATTLE_CMD, self._battle_cmd)
        self.mem.register_exec(EVO_MENU, self._evo_menu)
        self.side, self.restore, self.deciding = None, False, None
        self.turn_gap = 60 if self.r.fpt == 8 else 120    # 2 s of game time: the ROM at 60 or 30 fps (lib/emu.py FPT)
        # tools/aiplay.py: with human set a person plays the player's side (its menus are not handed to the AI, and
        # the runner presses nothing from the battle's start until one side has no Pokémon left: human_control);
        # frame_limit: a person's battle may run longer than an AI game's FRAME_LIMIT
        self.human, self.human_control, self.frame_limit = False, False, FRAME_LIMIT
        self.tune, self.tune_error = None, None      # the ROM's tuning table, for games that carry 'tune'
        try:
            self.tune = find_tune(rom)
        except TuneError as e:
            self.tune_error = str(e)

    def _evo_menu(self, a, s):
        if self.cur is not None:
            self.cur['keep_moves'] = self.reg.r1 == 1

    def _seed(self, a, s):
        """Every selection phase loads the AI's slot overlay. legacy: the game seed once per battle (the bench reseeds
        at every AI load, which would replay the same rolls every turn); synced: phase k's battle and AI streams."""
        c = self.cur
        if c is None or not c.get('injected'):
            return
        if c['rng'] == 'legacy':
            if not c.get('seeded'):
                c['seeded'] = True
                super()._seed(a, s)
            return
        k = c['phase']
        self.mem.write_long(self.mu.read_long(aibench.MAIN_PTR) + aibench.RNG, luck(c['seed'], k, 'battle'))
        c['ai_rng'] = [luck(c['seed'], k, SIDES[side]) for side in (0, 1)]
        c['phase'] = k + 1

    def _enter_ai(self, side):
        """synced: an AI call starts; the battle's RNG state is kept aside and this side's AI stream put in."""
        c = self.cur
        if c is None or c['rng'] != 'synced' or c.get('ai_rng') is None or c.get('held') is not None:
            return
        at = self.mu.read_long(aibench.MAIN_PTR) + aibench.RNG
        c['held'] = (at, self.mu.read_long(at), side)
        self.mem.write_long(self.words['FS_WORD_AT'] + 4, c['held'][1])
        self.mem.write_long(self.words['FS_WORD_AT'], self.words['FS_WORD_MAGIC'])
        self.mem.write_long(at, c['ai_rng'][side])

    def _leave_ai(self, a=None, s=None):
        c = self.cur
        if c is None or c.get('held') is None:
            return
        at, battle, side = c.pop('held')
        c['ai_rng'][side] = self.mu.read_long(at)
        self.mem.write_long(at, battle)
        self.mem.write_long(self.words['FS_WORD_AT'], 0)

    def _replace_call(self, a, s):
        if self.cur is not None and self.in_battle():
            self._enter_ai(self.mu.read_byte(self.reg.r5 + CLIENT_SIDE) & 1)

    # --- routing and attribution
    def _poll(self, a, s):
        c = self.cur
        if c is None or not self.in_battle():
            return          # another overlay's code at this address (seen before a battle when the clock moved)
        self.side = self.mu.read_byte(self.reg.r4 + CLIENT_SIDE) & 1
        bpp = self.mu.read_long(self.reg.r1 + 4)
        self.deciding = bpp if 0x02200000 <= bpp < 0x02400000 else None
        main = self.mu.read_long(aibench.MAIN_PTR)
        if self.mode == 'adv' and self.side == 0 and self.mu.read_long(main + MAIN_SLOT) == aibench.AI_OVERLAY:
            self.mem.write_long(main + MAIN_SLOT, 11)      # this call goes to the original AI's entry
            self.restore = True
        # each turn's selection phase calls the AIs in one burst: a call long after the last one opens a turn
        if self.r.frames - c.get('last_poll', -10 ** 9) > self.turn_gap:
            c['turn'] = c.get('turn', 0) + 1
            if self.live:
                self.report_faints()
                ev = {'kind': 'turn', 'turn': c['turn'], 'adv': self.active_view(1), 'orig': self.active_view(0),
                      'weather': self.weather()}
                if c['double']:         # the second position of each side
                    ev.update(adv2=self.active_view(1, 1), orig2=self.active_view(0, 1))
                self.live(ev)
        c['last_poll'] = self.r.frames
        self._enter_ai(self.side)

    def _diag(self, a, s):
        super()._diag(a, s)
        if self.cur is not None:
            self.cur['diag_side'] = self.side      # the writer runs inside this side's AI call

    def _inject(self, a, s):
        c = self.cur
        fresh = c is not None and 'setup' in c and not c.get('injected')
        super()._inject(a, s)
        if fresh and c['rng'] == 'synced':
            self.mem.write_long(c['setup'] + SETUP_SEED, luck(c['seed'], 0, 'setup'))
        mark = steer_test().get('mark')
        if fresh and mark is not None:
            at = c['setup'] + SETUP_MARK
            self.mem.write_byte(at, (self.mu.read_byte(at) & ~1) | (mark == '1'))
        if fresh and self.mode == 'self':     # the player side's AI would read trainer[0]'s items (BattleSetup + 0x2C)
            for k in range(4):
                self.mem.write_short(c['setup'] + 0x2C + 2 * k, 0)

    def _poll_ret(self, a, s):
        self._leave_ai()
        if self.restore:
            self.mem.write_long(self.mu.read_long(aibench.MAIN_PTR) + MAIN_SLOT, aibench.AI_OVERLAY)
            self.restore = False

    def _setter(self, kind):
        def f(a, s):
            c = self.cur
            if c is None or kind == 'none' or not c.get('injected'):
                return
            lr = self.reg.r14
            if lr == REPLACE_LR:
                side = self.mu.read_byte(self.reg.r5 + CLIENT_SIDE) & 1
                c['replacements'][SIDES[side]] += 1
                rec = self.replaced(side)
                if rec:
                    tally = c['ai_replacements'][SIDES[side]]
                    tally['valued'] += 1
                    tally['changed'] += rec['out'][0] != rec['orig'][0]
                    tally['not_taken'] += rec['out'][0] != self.reg.r2
                if self.live:
                    self.report_faints()
                    party = self.party(side)
                    name = lambda i: self.species_of(party[i]) if party and i < len(party) else '?'  # noqa: E731
                    ev = {'kind': 'switch', 'side': SIDES[side], 'from': name(0) if party else '?', 'to': name(self.reg.r2)}
                    if rec:
                        ev['options'] = [[name(i), v] for i, v in zip(rec['out'], rec['v'])]
                        if rec['orig'][0] != rec['out'][0]:
                            ev['engine'] = name(rec['orig'][0])
                    self.live(ev)
                return
            by = 'advanced' if self.adv_code[0] <= lr < self.adv_code[1] else \
                'original' if self.orig_code[0] <= lr < self.orig_code[1] else None
            if by is None or self.side is None:
                return
            # overlay 10 handing its turn to its own copy of overlay 11 (by design, e.g. no move left with PP: Struggle)
            # is still the advanced AI; only overlay 11 itself in the slot on the advanced side is a routing failure
            if by == 'original' and (self.side == 1 or self.mode == 'self') and self.mode != 'control' and \
                    self.mu.read_long(self.mu.read_long(aibench.MAIN_PTR) + MAIN_SLOT) == aibench.AI_OVERLAY:
                by = 'advanced'
            key = (self.r.frames, self.side, kind, self.reg.r1, self.reg.r2)
            if key == c.get('last_call'):       # the AIs write the same action twice per decision
                return
            c['last_call'] = key
            want = 'original' if self.mode == 'control' or (self.side == 0 and self.mode == 'adv') else 'advanced'
            sd = SIDES[self.side]
            c['decisions'][sd]['right' if by == want else 'wrong'] += 1
            adv = self.read_debug(self.side) if by == 'advanced' and self.debug_addr else {}
            if adv.get('fallback') is not None:
                fb = c['fallbacks'][sd]
                fb[str(adv['fallback'])] = fb.get(str(adv['fallback']), 0) + 1
                c['polls_max'][sd] = max(c['polls_max'][sd], adv.get('polls') or 0)
            if self.live:
                self.live(self.decision_event(kind, by, adv))
        return f

    # --- reading the battle
    def party(self, side):
        main = self.mu.read_long(aibench.MAIN_PTR)
        if not 0x02200000 <= main < 0x02400000:
            return None
        p = main + 0x54 + 0x0C + 0x1C * side
        n = self.mu.read_byte(p + 0x18)
        if n > 6:
            return None
        out = [self.mu.read_long(p + 4 * i) for i in range(n)]
        return out if all(0x02200000 <= b < 0x02400000 for b in out) else None

    def replaced(self, side):
        """ai_replace's record of this side's replacement, when it valued this one (its count moved since the last
        read): {'orig': the engine chooser's order, 'out': the order after ai_replace, 'v': its values}, as party
        indices; None when ai_replace left the order alone (one candidate, the flag off, the player's side
        without --self)."""
        a, mu, c = self.words['REPLACED_AT'] + REPLACED_SIZE * (side ^ 1), self.mu, self.cur
        seq, n = mu.read_byte(a), mu.read_byte(a + 1)
        if seq == c['rep_seq'][side] or not 2 <= n <= MAX_BENCH:
            return None
        c['rep_seq'][side] = seq
        signed = lambda v: v - (1 << 32) if v >> 31 else v  # noqa: E731
        return {'orig': [mu.read_byte(a + 2 + i) for i in range(n)], 'out': [mu.read_byte(a + 7 + i) for i in range(n)],
                'v': [signed(mu.read_long(a + 12 + 4 * i)) for i in range(n)]}

    def set_itcm(self):
        """After a state load: the self-play flag (the magic with --self, else 0) and empty replacement records.
        Returns the flag word as read back."""
        w = self.words
        for k in range(0, 2 * REPLACED_SIZE, 4):
            self.mem.write_long(w['REPLACED_AT'] + k, 0)
        self.mem.write_long(w['SELFPLAY_FLAG'], w['SELFPLAY_MAGIC'] if self.mode == 'self' else 0)
        return self.mu.read_long(w['SELFPLAY_FLAG'])

    def set_tune(self, tune):
        """After a state load (which restores ITCM, so the table holds the ROM's defaults): v[0] from tune['trainer']
        and v[1] from tune['player'] written into the table and read back. Returns what went wrong, or None."""
        t = self.tune
        if t is None:
            return 'the ROM has no tuning table' + (' (%s)' % self.tune_error if self.tune_error else '')
        n = len(t.defaults)
        vecs = [list(tune.get(side) or []) for side in TUNE_SIDES]
        if any(len(v) != n or not all(isinstance(x, int) and 0 <= x <= 0xFFFF for x in v) for v in vecs):
            return 'the vectors are not %d values of 0-65535' % n
        head = (self.mu.read_long(t.addr), self.mu.read_short(t.addr + 4), self.mu.read_short(t.addr + 6))
        if head != (TUNE_MAGIC, t.version, n):
            return 'the header at %08X reads %08X %d %d' % ((t.addr,) + head)
        at = lambda side, k: t.addr + TUNE_HEAD + 2 * (n * side + k)  # noqa: E731
        for side, v in enumerate(vecs):
            for k, x in enumerate(v):
                self.mem.write_short(at(side, k), x)
        back = [[self.mu.read_short(at(side, k)) for k in range(n)] for side in (0, 1)]
        return None if back == vecs else 'read back %s, wrote %s' % (back, vecs)

    def species_of(self, bpp):
        return self.d.species_name.get(self.mu.read_short(bpp), '?') if bpp else '?'

    def active_view(self, side, slot=0):
        party = self.party(side)
        if not party or slot >= len(party):
            return {'species': '?', 'hp': 0, 'maxhp': 0}
        b = party[slot]
        on = lambda i: self.mu.read_long(b + SICK + 8 * i) & 7
        status = next((STATUSES[i] for i in STATUSES if on(i)), None)
        if status == 'PSN' and self.mu.read_long(b + SICK + 8 * 5) >> 3:
            status = 'TOX'
        stages = {name: self.mu.read_byte(b + STAGES + k) - 6 for k, name in enumerate(STAGE_NAMES)}
        return {'species': self.species_of(b), 'hp': self.mu.read_short(b + 0x1E), 'maxhp': self.mu.read_short(b + 0x1C),
                'status': status, 'confused': bool(on(CONFUSION)), 'stages': {k: v for k, v in stages.items() if v}}

    def weather(self):
        """{'kind': 'rain', 'turns_left': 4} (turns_left None: no limit), or None."""
        main = self.mu.read_long(aibench.MAIN_PTR)
        field = self.mu.read_long(main + MAIN_FIELD) if 0x02200000 <= main < 0x02400000 else 0
        if not 0x02000000 <= field < 0x02400000 or self.mu.read_byte(field) not in WEATHERS:
            return None
        length, gone = self.mu.read_byte(field + 1), self.mu.read_byte(field + 3)
        return {'kind': WEATHERS[self.mu.read_byte(field)], 'turns_left': None if length == NO_LIMIT else length - gone}

    def report_faints(self):
        """A faint event for each side with fewer Pokémon able to fight than last reported. Called when the faint
        command starts (after the messages of the hit) and, in case a faint was not seen there, before the next
        turn, replacement or result."""
        c = self.cur
        a = self.alive_counts()
        if c is None or a is None or not sum(a):
            return
        if self.live and c.get('shown'):
            for side in (0, 1):
                if a[side] < c['shown'][side]:
                    self.live({'kind': 'faint', 'side': SIDES[side], 'pokemon': self.active_view(side)['species']})
        c['shown'] = a

    # --- the battle's own messages
    def in_battle(self):
        at, code = emu.BATTLE_CMD_READ
        return bytes(self.mu.read_byte(at + k) for k in range(4)) == code

    def _battle_cmd(self, a, s):
        if self.cur is None or not self.cur.get('injected') or not self.in_battle():
            return
        cmd = self.mu.read_long(self.reg.r4 + 0x2C)
        if cmd == FAINT_CMD:
            self.report_faints()
        elif cmd == DAMAGE_CMD and self.live:
            self.report_hit(self.reg.r4)

    def report_hit(self, client):
        """Damage command: count +0x38, effectiveness +0x3C (1 neutral, 2 super, 3 not very), move +0x40; targets
        at +0x98 every 8 bytes, the pokeID in byte 0 and the damage (already taken off the HP) a u16 at +4."""
        n = min(self.mu.read_long(client + 0x38) & 0xFFFF, 6)
        targets = []
        for i in range(n):
            pid, dmg = self.mu.read_byte(client + 0x98 + 8 * i), self.mu.read_short(client + 0x9C + 8 * i)
            side = 0 if 1 <= pid <= 12 else 1
            name = next((self.species_of(b) for b in self.party(side) or [] if self.mu.read_byte(b + 0x14) == pid), '?')
            targets.append([name, dmg])
        self.live({'kind': 'hit', 'move': self.d.move_name.get(self.mu.read_long(client + 0x40), '?'), 'targets': targets,
                   'eff': self.mu.read_long(client + 0x3C)})

    def _printer(self, a, s):
        self.r._printer(a, s)
        c = self.cur
        if c is None or not c.get('injected') or not self.live:
            return
        win = self.mu.read_long(self.reg.r0 + 4)
        if not 0x02000000 <= win < 0x02400000:
            return              # the health boxes' names: drawn straight into video memory
        box = (self.mu.read_byte(win + 7), self.mu.read_byte(win + 8))
        if box not in (MSG_BOX, ABILITY_BOX) or not self.in_battle():
            return
        text = battle_text(self.r.last_text)
        if not text:
            return
        if box == MSG_BOX:
            self._message({'kind': 'message', 'text': text})
        elif c.get('popup') and c['popup'][0] == win:
            self._message({'kind': 'message', 'ability': c.pop('popup')[1], 'pokemon': text})
        else:
            self.flush_popup()
            c['popup'] = (win, text)

    def flush_popup(self):
        """An ability pop-up whose second print (the Pokémon) never came: the ability alone."""
        if self.cur is not None and self.cur.get('popup'):
            self._message({'kind': 'message', 'ability': self.cur.pop('popup')[1]})

    def _message(self, ev):
        c = self.cur
        if ev.get('text'):
            self.flush_popup()
        text = ev.get('text') or ''
        for won, out, trainer in OUTCOMES:
            if text.startswith(won):                     # the game's own verdict: the player's side won
                c['outcome'] = 'original'
            elif out in text and trainer not in text.split(out, 1)[0]:
                c['outcome'] = 'advanced'                # the player's side is out (a double KO counts as its loss)
        key = (ev.get('text'), ev.get('ability'), ev.get('pokemon'))
        if key == c.get('last_msg') and self.r.frames - c.get('last_msg_frame', 0) < REPEAT_FRAMES:
            return
        c['last_msg'], c['last_msg_frame'] = key, self.r.frames
        self.live(ev)

    def alive_counts(self):
        out = []
        for side in (0, 1):
            party = self.party(side)
            if party is None:
                return None
            out.append(sum(1 for b in party if self.mu.read_short(b + 0x1E) > 0))
        return tuple(out)

    def decision_event(self, kind, by, adv):
        d, r1, r2 = self.d, self.reg.r1, self.reg.r2
        me = self.deciding
        foe = self.party(1 - self.side)
        side = SIDES[self.side] if self.mode == 'self' else \
            'advanced' if (by == 'advanced' or (self.mode == 'control' and self.side == 1)) else 'original'
        ev = {'kind': 'decision', 'side': side,
              'pokemon': self.species_of(me), 'action': kind, 'name': '?', 'target': self.species_of(foe[0]) if foe else None}
        if kind == 'move':
            ev['name'] = d.move_name.get(r1, str(r1))
        elif kind == 'item':
            ev['name'] = d.item_name.get(r1, str(r1))
            ev['target'] = None
        else:
            party = self.party(self.side)
            ev['name'] = self.species_of(party[r2]) if party and r2 < len(party) else str(r2)
            ev['target'] = None
        # a fallback (overlay 11's code decided) leaves the record's last pick in place: its options are not this one's
        fb = adv.get('fallback')
        if fb:
            ev['fallback'] = fb
        if adv.get('why') and not fb:
            ev['why'] = {1: 'surer KO', 2: 'less commitment', 3: 'more damage', 4: 'status move in a lost position'}.get(adv['why'], str(adv['why'])) + \
                (', lost position' if adv.get('lost') else '')
        # debug version 4: the foe model (0-1000) and the foe's likely switch-in with the weight its case got (per-mille);
        # with --self on every decision, 0 too, so a replay (tools/sim/validate.py --ai) can compare it decision by decision
        if not fb and (adv.get('strong') or adv.get('sw_w') or (self.mode == 'self' and adv.get('version', 0) >= 4)):
            ev['foe'] = {'strong': adv.get('strong', 0), 'w': adv.get('sw_w', 0)}
            if adv.get('sw_w'):
                ev['foe']['switch'] = d.species_name.get(adv.get('sw_species'), str(adv.get('sw_species')))
        if adv.get('options') and not fb:
            moves = [self.mu.read_short(me + 0x25A + 0x12 * i) for i in range(4)] if me else [0] * 4
            party = self.party(self.side) or []
            opts = []
            for k, idx, extra, value in adv['options']:
                if k == 0:
                    name = d.move_name.get(moves[idx], '?') if idx < 4 else '?'
                elif k == 1:
                    name = 'switch:' + (self.species_of(party[extra]) if extra < len(party) else '?')
                else:
                    name = 'item:' + d.item_name.get(extra, str(extra))
                opts.append([name, value])
            ev['options'] = sorted(opts, key=lambda o: -o[1])
        elif (by == 'original' or fb) and self.cur.get('diag') and self.cur.get('diag_side') == self.side:
            # the original AI's five sub-scores per move (+4..+0x14 of its move rows); their sum ranks its choice
            ev['scores'] = sorted(([d.move_name.get(row[0], str(row[0])), sum(row[2:])] for row in self.cur['diag']['moves']),
                                  key=lambda x: -x[1])
            # 'scores' is the first target's rows (the player side's own Pokemon); the other targets' rows hold the
            # attacks, logged as 'scores on foe:' (or 'self') with only the rows the draw considers (invalid flag 0)
            ev['target_scores'] = [['self' if (t['poke'] > 12) == (self.side == 1) else 'foe',     # pokeIDs 1-12 the player's
                                    [[d.move_name.get(row[0], str(row[0])), sum(row[2:])] for row in t['rows'] if not row[1]]]
                                   for t in self.cur['diag'].get('targets', [])[1:]]
        return ev

    # --- one battle
    def play(self, game, frame_hook=None):
        d = self.d
        template = aibench.template_mon()
        seed = game['seed']
        # each member built from its place in the full team, so a cut team's members are the same Pokémon
        build = lambda team, base: [aibench.build_mon(d, template, spec, base + 31 * i)
                                    for i, spec in zip(slots_of(team), team['team'])]
        mons = {'player': build(game['orig'], seed), 'enemy': build(game['adv'], seed + 7)}
        r = self.r
        rng = game.get('rng', 'legacy')
        assert rng in RNG_MODES, rng
        self.cur = {'mons': mons, 'items': [], 'seed': luck_seed(seed, game.get('reseed', 0)), 'calls': [], 'failures': [], 'notes': [],
                    'rng': rng, 'phase': 0,
                    'done': False, 'double': bool(game.get('double')), 'fail_detail': [], 'decisions': {s: {'right': 0, 'wrong': 0} for s in SIDES},
                    'replacements': {'original': 0, 'advanced': 0, 'unknown': 0}, 'fallbacks': {s: {} for s in SIDES},
                    'polls_max': {s: 0 for s in SIDES}, 'rep_seq': [0, 0],
                    'ai_replacements': {s: {'valued': 0, 'changed': 0, 'not_taken': 0} for s in SIDES}}
        self.side, self.restore = None, False
        start = r.frames
        with quiet():
            aibench.to_battle(r, self.state)
        flag = self.set_itcm()
        if flag != (self.words['SELFPLAY_MAGIC'] if self.mode == 'self' else 0):
            self.cur['fail_detail'].append({'ev': 'selfplay flag %08X' % flag, 'text': None, 'move_text': None})
        tune = game.get('tune')
        if tune is not None:
            bad = self.set_tune(tune)
            if bad:
                self.cur['fail_detail'].append({'ev': 'tune ' + bad, 'text': None, 'move_text': None})
        patched, last, seen_battle, ended, parties = False, None, False, None, None
        while r.frames - start < self.frame_limit and not r.frozen:
            k = r.frames - start
            if not self.window:
                r.skip_render = k % 30 != 29                  # one picture every 30 frames, for the end check
            if not self.human and not patched and self.mu.read_long(SELECT) == HUMAN_SELECT:
                self.mem.write_long(SELECT, AI_SELECT)
                self.mem.write_long(REPLACE, AI_REPLACE)
                patched = True
            if k % 30 == 0 and self.cur.get('injected'):
                # counted from the first decision on: before it (rc34's VS intro plays after the injection) the main
                # pointer word in overlay 14's bss is stale, and the counts read through it are garbage
                a = self.alive_counts() if any(sum(d.values()) for d in self.cur['decisions'].values()) else None
                if a is not None and sum(a):
                    self.cur.setdefault('shown', a)         # faints are reported by report_faints, in message order
                    last, seen_battle = a, True
                    if parties is None:                     # the party sizes the battle engine itself holds
                        parties = {SIDES[side]: len(self.party(side)) for side in (0, 1)}
                if seen_battle and r.seen(emu.STATES['field']):
                    ended = k
                    break
            self.human_control = self.human and bool(self.cur.get('injected')) and not (last and 0 in last)
            if k % 40 == 0 and not self.human_control:
                r.hold('B' if self.cur.get('keep_moves') else 'A', 4, release=4)   # only advances text: both sides choose through the AI
            else:
                r.step(1)
        self.human_control = False
        if self.live and self.cur.get('injected'):
            self.flush_popup()
            if self.in_battle():                    # after the battle its memory is gone
                self.report_faints()
        c, self.cur = self.cur, None
        turns = c.get('turn', 0)
        if not c.get('injected'):
            end = 'no battle'
        elif r.frozen:
            end = 'frozen'
        elif ended is None:
            end = 'unfinished'
        elif c['decisions']['advanced']['wrong'] or c['decisions']['original']['wrong']:
            end = 'wrong ai'
        else:
            end = 'normal'
        left = {'original': last[0], 'advanced': last[1]} if last else {'original': 0, 'advanced': 0}
        winner = None
        if end in ('normal', 'wrong ai') and last:
            winner = 'advanced' if last[1] > 0 and last[0] == 0 else 'original' if last[0] > 0 and last[1] == 0 else None
        if end in ('normal', 'wrong ai') and c.get('outcome'):
            # the last count can be sampled before a final recoil or Destiny Bond faint: the game's message decides
            winner = c['outcome']
            loser = 'original' if winner == 'advanced' else 'advanced'
            left[loser] = 0
        if self.live:
            self.live({'kind': 'end', 'winner': winner, 'left': left, 'turns': turns, 'end': end})
        out = {'scenario': game['scenario'], 'game': game['game'], 'reseed': game.get('reseed', 0),
               'adv_team': game['adv']['name'], 'orig_team': game['orig']['name'],
               'sizes': game_sizes(game), 'parties': parties,
               'winner': winner, 'end': end, 'turns': turns, 'left': left, 'frames': r.frames - start,
               'decisions': c['decisions'], 'replacements': c['replacements'], 'adv_fallbacks': c['fallbacks']['advanced'],
               'adv_polls_max': c['polls_max']['advanced'], 'fallbacks': c['fallbacks'], 'polls_max': c['polls_max'],
               'ai_replacements': c['ai_replacements'], 'rng': rng, 'failures': [{'ev': f['ev'], 'text': f.get('text'), 'move_text': f.get('move_text')}
                                                             for f in c['fail_detail']]}
        if tune is not None:      # which vector each side played (by id), and which side the tuner's X was
            out['tune'] = {side: tune_id(tune.get(side) or []) for side in TUNE_SIDES}
            out['x_side'] = game.get('x_side')
        return out

    def _event(self, **ev):
        # each failure with the battle message on screen (as tools/aifuzz.py does)
        if self.cur is not None and ev['ev'] in aibench.FAILURES:
            moves = [t for t in self.r.recent_texts if any(m in t for m in failures.USED)]
            self.cur['fail_detail'].append({'ev': '%s %s' % (ev['ev'], ev.get('lr') or ev.get('heap') or ''),
                                            'text': self.r.last_text, 'move_text': moves[-1] if moves else None})
        super()._event(**ev)


def luck(seed, phase, stream):
    """synced luck: the 32-bit RNG state of one stream ('battle', or an AI side) for selection phase `phase`."""
    return int.from_bytes(hashlib.sha1(b'%d:%d:%s' % (seed, phase, stream.encode())).digest()[:4], 'little')


def luck_seed(seed, reseed=0):
    """The seed a game's luck comes from (synced: every phase's streams; legacy: the battle RNG's start): the game seed
    for reseed 0, else a 32-bit mix of the game seed and the reseed index. The teams are built from the game seed
    alone, so a reseeded game changes only the luck."""
    if not reseed:
        return seed & 0xFFFFFFFF
    return int.from_bytes(hashlib.sha1(b'%d:reseed:%d' % (seed, reseed)).digest()[:4], 'little')


def parse_reseeds(spec):
    """--reseed: 'K', 'A-B' or a comma list of both ('0-4,9') -> the sorted indices."""
    out = set()
    for part in spec.split(','):
        lo, sep, hi = part.strip().partition('-')
        if not lo.isdigit() or (sep and not hi.isdigit()) or int(hi or lo) < int(lo):
            raise ValueError('a reseed is K, A-B or a comma list of them, not %r' % spec)
        out.update(range(int(lo), int(hi or lo) + 1))
    return sorted(out)


def log_name(game):
    """A game's log file: sNNN_gK.log, with _rK for a reseeded game."""
    k = game.get('reseed', 0)
    return '%s_g%d%s.log' % (game['scenario'], game['game'], '_r%d' % k if k else '')


# --- scenarios
def mixed_team(rng, members, name, taken):
    """Six members drawn from the trainer teams' Pokémon (each keeps its own moves, item, EVs and nature), no
    species twice in a team and no member in both teams of a scenario (taken)."""
    team, species = [], set()
    while len(team) < FULL_TEAM:
        i = rng.randrange(len(members))
        if i in taken or members[i]['species'] in species:
            continue
        taken.add(i)
        species.add(members[i]['species'])
        team.append(members[i])
    return {'source': 'mixed', 'name': name, 'team': team}


def draw_scenarios(n, teams, level, seed, min_level=80, rom=None):
    """n scenarios of two distinct teams of six; trainer teams only when all six are at min_level or above in the
    ROM (low-level teams, like level-7 Metapods, stay weak at any level and only add 1-1 splits). 'mixed' builds
    new teams from those teams' Pokémon: the sets are the ROM's, the teams are new, so a run on a new seed is
    held-out data for teams the analysts never saw; 'random' gives any species any four moves."""
    import aiteams
    rng = random.Random(seed)
    rom = rom or os.environ['ADVAI_TEAMS_ROM']  # --rom (the Spanish tool drew from its own build, rom/origin_es.nds)
    pool = [t for t in aiteams.trainer_teams(rom, 6) if min(s['level'] for s in t['team']) >= min_level] \
        if teams in ('trainers', 'mixed') else None
    members = [spec for t in pool for spec in t['team']] if teams == 'mixed' else None
    out = []
    order = []
    for k in range(n):
        if members is not None:
            taken = set()
            a = mixed_team(rng, members, 'Mixed s%03d-A' % (k + 1), taken)
            b = mixed_team(rng, members, 'Mixed s%03d-B' % (k + 1), taken)
        elif pool is not None:
            if len(order) < 2:
                order = list(range(len(pool)))
                rng.shuffle(order)
            a, b = pool[order.pop()], pool[order.pop()]
        else:
            a, b = aiteams.random_team(rng.randrange(1 << 30), 6, level, rom), aiteams.random_team(rng.randrange(1 << 30), 6, level, rom)
        a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
        for t in (a, b):
            for spec in t['team']:
                spec['level'] = level
        out.append({'id': 's%03d' % (k + 1), 'seed': rng.randrange(1 << 31), 'a': a, 'b': b})
    return out


def cut_team(team, size, pick, key):
    """The team cut to size members, in the team's own order. pick 'first' keeps the first ones (the lead
    stays); 'random' shuffles the places with random.Random(key) and keeps the first size of that order, so
    one team in one scenario always gives the same subset, and a cut to 4 is part of its cut to 5. 'slots'
    are the kept members' places in the full team; 'full' its size, only when members were left out."""
    n = len(team['team'])
    if size >= n:
        return dict(team, slots=list(range(n)))
    if pick == 'first':
        slots = list(range(size))
    else:
        order = list(range(n))
        random.Random(key).shuffle(order)
        slots = sorted(order[:size])
    return dict(team, team=[team['team'][i] for i in slots], slots=slots, full=n)


def slots_of(team):
    return team.get('slots') or list(range(len(team['team'])))


def game_sizes(game):
    return {'advanced': len(game['adv']['team']), 'original': len(game['orig']['team'])}


def games_of(scenarios, both, sizes=(FULL_TEAM, FULL_TEAM), pick='first'):
    """The games of each scenario: game 0 team A on the advanced side, game 1 the teams swapped. sizes (the
    advanced side's, the original side's) stay with the sides, so each team is cut to N on the advanced side
    and to M on the original side; the subset of a team is drawn from the scenario seed and the team's letter."""
    adv_n, orig_n = sizes
    out = []
    for s in scenarios:
        cut = lambda k, n: cut_team(s[k], n, pick, '%d:%s' % (s['seed'], k))  # noqa: E731
        out.append({'scenario': s['id'], 'game': 0, 'seed': s['seed'], 'adv': cut('a', adv_n), 'orig': cut('b', orig_n)})
        if both:
            out.append({'scenario': s['id'], 'game': 1, 'seed': s['seed'] ^ 0x5A5A5A5A, 'adv': cut('b', adv_n),
                        'orig': cut('a', orig_n)})
    return out


def side_labels(mode):
    """The sides' names in headers: by AI, or by side when the advanced AI plays both (--self)."""
    return ('TRAINER SIDE', 'PLAYER SIDE') if mode == 'self' else ('ADVANCED', 'ORIGINAL')


def sizes_text(sizes, mode='adv'):
    """'ADVANCED 4 vs ORIGINAL 6' ('TRAINER SIDE 4 vs PLAYER SIDE 6' with --self)."""
    a, o = side_labels(mode)
    return '%s %d vs %s %d' % (a, sizes['advanced'], o, sizes['original'])


def prepare(rom, control, tag):
    """ROM link, battery save with fast text and no animations, pre-battle state; the advanced AI on (off for a control
    run) in the battery and through the AI setting every state load writes (aibench.setting_save)."""
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(aibench.OUT, exist_ok=True)
    with open(os.path.join(aibench.OUT, 'template.bin'), 'wb') as f:
        f.write(aibench.template_mon())
    save = aibench.setting_save('off' if control else 'all', os.path.join(OUT, '%s.dsv' % tag), options=True)
    rom_copy, state = aibench.link_rom(rom, os.path.join(OUT, '%s.nds' % tag)), os.path.join(OUT, '%s.dst' % tag)
    shutil.copy(save, os.path.join(aibench.DSV_DIR, '%s.dsv' % tag))
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return rom_copy, state, save


def team_lines(side, team):
    """The team at the head of a battle log: what the analysts need to judge the decisions."""
    out = ['%s team: %s' % (side, team['name']) + (' (%d of %d: members %s)' % (
        len(team['team']), team['full'], ', '.join(str(i + 1) for i in team['slots'])) if team.get('full') else '')]
    for m in team['team']:
        item = m.get('item')
        out.append('  %-12s L%-3s %-14s @ %-14s %s%s' % (m['species'], m.get('level'), m.get('ability'), item if item is not None else '-',
                                                    ', '.join(m['moves']), '  (%s)' % m['nature'] if m.get('nature') else ''))
    return out


def logged_play(duel, game, path, n=None, of=None):
    """One battle with every event written to path (plain text, as the live log). With game['keep_events'] the
    result also has the turn, decision and replacement events ('events', full option lists: the log shows five)."""
    import aivsai_live
    kept = [] if game.get('keep_events') else None
    with open(path, 'w') as f:
        k = game.get('reseed', 0)
        f.write('scenario %s game %d, seed %d%s, %s\n' % (game['scenario'], game['game'], game['seed'],
                                                         ', reseed %d' % k if k else '', sizes_text(game_sizes(game), duel.mode)))
        a, o = side_labels(duel.mode)
        f.write('\n'.join(team_lines(a, game['adv']) + team_lines(o, game['orig'])) + '\n')
        sink = duel.live

        def log(ev):
            if kept is not None and ev.get('kind') in KEPT_EVENTS:
                kept.append(ev)
            f.write(aivsai_live.format_event(ev, color=False) + '\n')
            f.flush()
            if sink:
                sink(ev)
        duel.live = log
        try:
            log({'kind': 'battle', 'n': n or 1, 'of': of or 1, 'adv_team': game['adv']['name'], 'orig_team': game['orig']['name'],
                 'sizes': game_sizes(game)})
            res = duel.play(game)
        finally:
            duel.live = sink
    res['log'] = tbpaths.rel(path)
    if kept is not None:
        res['events'] = kept
    return res


def worker(rom, state, jobs_path, out_path, mode, log_dir):
    duel = Duel(rom, state, mode)
    results = []
    for game in json.load(open(jobs_path)):
        t0 = time.time()
        res = logged_play(duel, game, os.path.join(log_dir, log_name(game)))
        res['seconds'] = round(time.time() - t0, 1)
        results.append(res)
        with open(out_path, 'w') as f:
            json.dump(results, f)


def worker_results(path):
    """A worker's results so far ([] while the file is missing or half written)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def run_parallel(games, rom, state, save, workers, mode, tag, log_dir, on_result=None):
    """The games on parallel emulators; their results sorted by scenario and game. on_result (optional) is called
    with each result as soon as its worker has written it (one call at a time; a game whose worker died gets its
    'worker died' result at the end), so a caller can record finished games while the others play."""
    chunks = [games[k::workers] for k in range(workers) if games[k::workers]]
    lock = threading.Lock()

    def go(k):
        rom_k, dsv_k = os.path.join(OUT, '%s_%d.nds' % (tag, k)), os.path.join(aibench.DSV_DIR, '%s_%d.dsv' % (tag, k))
        aibench.link_rom(rom, rom_k)
        shutil.copy(save, dsv_k)
        jp, op = os.path.join(OUT, 'jobs_%s_%d.json' % (tag, k)), os.path.join(OUT, 'res_%s_%d.json' % (tag, k))
        json.dump(chunks[k], open(jp, 'w'))
        if os.path.exists(op):
            os.remove(op)
        cmd = [sys.executable, __file__, '--worker', rom_k, state, jp, op, mode, log_dir]
        if on_result is None:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc, seen = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), 0
            while True:
                done = proc.poll() is not None
                part = worker_results(op)
                with lock:
                    for res in part[seen:]:
                        on_result(res)
                seen = max(seen, len(part))
                if done:
                    break
                time.sleep(2)
        for p in (rom_k, dsv_k):
            os.remove(p)
        return worker_results(op)
    with ThreadPoolExecutor(len(chunks)) as pool:
        results = [x for part in pool.map(go, range(len(chunks))) for x in part]
    key = lambda x: (x['scenario'], x['game'], x.get('reseed', 0))  # noqa: E731
    done = {key(x) for x in results}
    for g in games:
        if key(g) not in done:
            results.append({'scenario': g['scenario'], 'game': g['game'], 'reseed': g.get('reseed', 0),
                            'adv_team': g['adv']['name'], 'orig_team': g['orig']['name'],
                            'sizes': game_sizes(g), 'parties': None, 'winner': None, 'end': 'no battle', 'turns': 0, 'left': {'advanced': 0, 'original': 0}, 'frames': 0,
                            'seconds': 0, 'decisions': {s: {'right': 0, 'wrong': 0} for s in SIDES}, 'adv_fallbacks': {},
                            'adv_polls_max': 0, 'fallbacks': {s: {} for s in SIDES}, 'polls_max': {s: 0 for s in SIDES},
                            'failures': [{'ev': 'worker died', 'text': None, 'move_text': None}]})
            if on_result is not None:
                on_result(results[-1])
    return sorted(results, key=key)


def run_live(games, rom, state, mode, log_path, log_dir):
    """Battles one after another in a window; every event printed and written to log_path. Started without a
    terminal (stdout not a TTY), a Terminal window follows the log so the decisions are always visible."""
    import aivsai_live
    duel = Duel(rom, state, mode, live=None)
    duel.window = True
    view = aivsai_live.LiveView(duel.r.emu)
    log_file = open(log_path, 'w')

    def log(ev):
        view.log(ev)
        log_file.write(aivsai_live.format_event(ev, color=False) + '\n')
        log_file.flush()
    if not sys.stdout.isatty() and sys.platform == 'darwin':
        subprocess.run(['osascript', '-e', 'tell application "Terminal" to do script "tail -n +1 -f %s"' % log_path,
                        '-e', 'tell application "Terminal" to activate'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    duel.live = log
    duel.r.skip_render = False
    step = duel.r.step

    def paced(n=1):
        for _ in range(n):
            step(1)
            view.frame()
            if view.closed():
                raise KeyboardInterrupt
    duel.r.step = paced
    results = []
    try:
        for i, game in enumerate(games):
            a, o = side_labels(mode)
            for line in team_lines(a, game['adv']) + team_lines(o, game['orig']):
                print(line, flush=True)
                log_file.write(line + '\n')
            t0 = time.time()
            res = logged_play(duel, game, os.path.join(log_dir, log_name(game)), i + 1, len(games))
            res['seconds'] = round(time.time() - t0, 1)
            results.append(res)
    except KeyboardInterrupt:
        print('\nstopped')
        log_file.write('stopped\n')
    finally:
        view.close()
        log_file.close()
    return results


def hold_tag(tag):
    """Claim the run's work files (ROM copies, states, job and result files named by `tag`, which comes from the ROM
    file name): a second run on the same ROM file at the same time would overwrite them and kill the first run's
    workers (it happened on 2026-10-04). The claim is released when this process exits."""
    import atexit
    os.makedirs(OUT, exist_ok=True)
    lock = os.path.join(OUT, tag + '.lock')
    try:
        pid = int(open(lock).read().strip() or 0)
        os.kill(pid, 0)
        if pid != os.getpid():
            sys.exit('another aivsai run (pid %d) is using the work files of %s; copy the ROM under another file name '
                     'to run both at once' % (pid, tag))
    except (OSError, ValueError):
        pass
    with open(lock, 'w') as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(lock) and open(lock).read().strip() == str(os.getpid()) and os.remove(lock))


def only_ids(only):
    """The scenario ids of --only ('s12,s025' -> {'s012', 's025'})."""
    return {'s%03d' % int(x.strip().lstrip('sS')) for x in only.split(',') if x.strip()}


def only_count(n, only):
    """How many scenarios to draw so that every --only id is among them (the draw is sequential)."""
    return max([n] + [int(i[1:]) for i in only_ids(only)]) if only else n


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:8])
    ap = argparse.ArgumentParser(description='The advanced AI against the original AI, teams of six, played to the end.')
    ap.add_argument('scenarios', nargs='?', type=int, default=20, help='how many scenarios (pairs of teams)')
    ap.add_argument('--live', action='store_true', help='one emulator in a window at normal speed, decisions printed')
    ap.add_argument('--teams', choices=('trainers', 'mixed', 'random'), default='trainers',
                    help='trainers: the ROM\'s teams; mixed: new teams of the ROM trainers\' Pokémon; random: any species, any moves')
    ap.add_argument('--level', type=int, default=100, help='every Pokémon at this level (default 100)')
    ap.add_argument('--min-level', type=int, default=80, help='trainer teams whose six are all at least this level in the ROM')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--workers', type=int, default=9)
    who = ap.add_mutually_exclusive_group()
    who.add_argument('--control', action='store_true', help='the original AI on both sides')
    who.add_argument('--self', dest='self_play', action='store_true',
                     help='the advanced AI on both sides (self-play: both sides\' options logged; not a progress measure)')
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', help='the AI build\'s payload.json (default: ADVAI_PAYLOAD)')
    ap.add_argument('--log-dir', help='the battle logs\' folder (default: a new RUNS/aivsai/reports/runs/<time>...)')
    size = lambda v: int(v) if v.isdigit() and 1 <= int(v) <= FULL_TEAM else ap.error('a team size is 1 to 6, not %r' % v)  # noqa: E731
    ap.add_argument('--adv-size', type=size, default=None, help='Pokémon on the advanced AI\'s side (1-6, default 6; '
                    'with --self the trainer side)')
    ap.add_argument('--orig-size', type=size, default=None, help='Pokémon on the original AI\'s side (1-6, default 6; '
                    'with --self the player side)')
    ap.add_argument('--sizes', metavar='N:M', help='both sizes at once: --sizes 4:6 is --adv-size 4 --orig-size 6')
    ap.add_argument('--only', metavar='sNNN,...', help='replay only these scenarios of the seed (the draw is the same as '
                    'without --only, so s012 is the same teams as in the full run)')
    ap.add_argument('--rng', choices=RNG_MODES, default='synced',
                    help='synced (default): luck from the game seed per selection phase, the AIs\' thinking on streams '
                         'of their own, so two builds share their luck until their decisions differ; legacy: one '
                         'stream per battle shared with the AIs\' thinking (runs before 2026-10-04)')
    ap.add_argument('--reseed', default='0', metavar='K|A-B,...',
                    help='play each game once per reseed index with other luck and the same teams, sides and sizes '
                         '(default 0: the game seed\'s own luck, as every run before); logs sNNN_gK_rK.log')
    ap.add_argument('--double', action='store_true', help='double battles against the one trainer (the bench\'s trick: '
                    'trainer 2 = trainer 1), each side\'s first two out; files and reports end in _dbl')
    ap.add_argument('--pick', choices=('first', 'random'), default='first',
                    help='which members a smaller team keeps: its first ones (default, the lead stays) or a subset '
                         'drawn from the scenario seed, the same in both games')
    ap.add_argument('--steer-test', metavar='SPEC', help=argparse.SUPPRESS)   # ADVAI_STEER_TEST, test only
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the workers
    os.environ['ADVAI_TEAMS_ROM'] = os.path.abspath(a.rom)
    if a.steer_test is not None:
        os.environ['ADVAI_STEER_TEST'] = a.steer_test
    mode = 'control' if a.control else 'self' if a.self_play else 'adv'
    if a.sizes is not None:
        if a.adv_size is not None or a.orig_size is not None:
            ap.error('--sizes replaces --adv-size and --orig-size: give one or the other')
        n, _, m = a.sizes.partition(':')
        a.adv_size, a.orig_size = size(n), size(m)
    sizes = (a.adv_size or FULL_TEAM, a.orig_size or FULL_TEAM)
    cut = sizes != (FULL_TEAM, FULL_TEAM)
    speed = 'rom'                           # the ROM's own speed: never changed (the Spanish --speed toggled it)
    seed = a.seed if a.seed is not None else random.randrange(1 << 31)
    scenarios = draw_scenarios(only_count(a.scenarios, a.only), a.teams, a.level, seed, a.min_level)
    if a.only:
        scenarios = [sc for sc in scenarios if sc['id'] in only_ids(a.only)]
    try:
        reseeds = parse_reseeds(a.reseed)
    except ValueError as e:
        ap.error(str(e))
    games = [dict(g, rng=a.rng, reseed=k, double=a.double) for k in reseeds for g in games_of(scenarios, not a.live, sizes, a.pick)]
    # runs on different ROMs at once must not share work files (ROM copies, battery saves, states)
    tag = 'aivsai_%s%s%s_%s' % (mode, '_dbl' if a.double else '', '_live' if a.live else '',
                              os.path.splitext(os.path.basename(a.rom))[0])
    # a handicap run's files and reports say so in their names: _4v6, and r when the members are drawn at random
    label = ('_%dv%d%s' % (sizes + ('r' if a.pick == 'random' else '',)) if cut else '') + ('_dbl' if a.double else '')
    print('%d scenario(s)%s, %d battle(s), teams %s, level %d, seed %d, %s speed, %s luck%s, sizes %s%s' % (
        len(scenarios), ' x %d reseeds' % len(reseeds) if reseeds != [0] else '', len(games), a.teams, a.level, seed, speed, a.rng,
        {'control': ', control run', 'self': ', self-play (the advanced AI on both sides)'}.get(mode, ''),
        sizes_text({'advanced': sizes[0], 'original': sizes[1]}, mode),
        (' (%s members kept)' % ('first' if a.pick == 'first' else 'seeded random')) if cut else ''), flush=True)
    hold_tag(tag)
    if a.live:      # a person watches: never wait for a slot of the emulator pool (tools/emupool.py)
        os.environ.setdefault('ADVAI_EMU_SLOTS', '0')
    rom, state, save = prepare(a.rom, a.control, tag)
    t0 = time.time()
    started = datetime.datetime.now()
    os.makedirs(REPORTS, exist_ok=True)
    suffix = {'control': '_control', 'self': '_self'}.get(mode, '')
    log_dir = a.log_dir or os.path.join(REPORTS, 'runs', started.strftime('%Y%m%d_%H%M%S') + suffix + label +
                                        ('_live' if a.live else ''))
    os.makedirs(log_dir, exist_ok=True)
    print('battle logs: %s' % tbpaths.rel(log_dir), flush=True)
    if a.live:
        live_log = os.path.join(REPORTS, 'live_%s%s%s.log' % (started.strftime('%Y%m%d_%H%M%S'), suffix, label))
        print('decisions are also written to %s' % live_log, flush=True)
        results = run_live(games, rom, state, mode, live_log, log_dir)
    else:
        results = run_parallel(games, rom, state, save, min(a.workers, len(games)), mode, tag, log_dir)
    meta = {'rom_sha1': hashlib.sha1(open(a.rom, 'rb').read()).hexdigest(), 'mode': {'adv': 'adv-vs-orig'}.get(mode, mode),
            'teams': a.teams, 'level': a.level, 'seed': seed, 'workers': 1 if a.live else a.workers,
            'scenarios': len(scenarios) * len(reseeds),      # the report counts each reseeded scenario as one
            'started': started.strftime('%Y-%m-%d %H:%M'), 'seconds': round(time.time() - t0, 1), 'live': a.live,
            'speed': speed, 'adv_size': sizes[0], 'orig_size': sizes[1], 'pick': a.pick if cut else 'first', 'rng': a.rng,
            'double': a.double}
    if reseeds != [0]:
        meta['reseeds'] = reseeds
    for p in (rom, os.path.join(aibench.DSV_DIR, '%s.dsv' % tag)):
        if os.path.lexists(p):
            os.remove(p)
    os.makedirs(REPORTS, exist_ok=True)
    stamp = started.strftime('%Y%m%d_%H%M')
    import aivsai_report
    failures.use_rom(a.rom)                 # the move names the ROM's battle messages print
    name = 'report_%s%s%s%s' % (stamp, suffix, label, '_live' if a.live else '')
    print(aivsai_report.write_report(results, meta, os.path.join(REPORTS, name + '.md'), os.path.join(REPORTS, name + '.json')))


if __name__ == '__main__':
    main()
