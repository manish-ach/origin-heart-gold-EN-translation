"""Play mode: you play battles against the advanced trainer AI, and every battle is logged for later analysis.

  .venv/bin/python work/advanced-ai/testbench/versus/aiplay.py N --rom ROM --payload PAYLOAD
                   [--teams mixed|random|trainers] [--size 4|5|6 | --sizes N:M] [--level L] [--seed S]

Ported from the Spanish workspace's tools/aiplay.py (dc8577c). Changes: the ROM and the payload are arguments, the ROM
plays at its own speed (no speed toggle: the Spanish tool switched its build to 30 fps), the seed bookkeeping comes
from lib/seeds.py, and the logs go to RUNS/aivsai/human/.

N battles in a row, in one window at normal speed. You play the player's side with the
keyboard (the DS buttons) and the mouse (the touch screen); the advanced AI (the NPC flag set: overlay 10) plays
the trainer's side. Every battle you get a fresh random team and the AI a different fresh random team: by default
new teams of the ROM trainers' Pokémon, each with its own moves, item, EVs and nature (aivsai's 'mixed'); 'random'
gives any species any moves, 'trainers' the ROM's own six-Pokémon teams. Both sides get the same size, drawn from
4, 5 and 6 every battle; --size fixes it, --sizes N:M gives you N and the AI M. Level 100 unless --level. The
session seed is printed and logged: --seed S draws the same teams and sizes again (the battles still go their own
way: your choices differ). Your team is printed before each battle; the AI's is only logged.

Logs (for the analysis, the Spanish /aiplay-analyze and qa/aivsai/HUMAN_BRIEF.md; RUNS = work/build/advanced-ai/runs):
  RUNS/aivsai/human/<session>/gNN.log   the AI-vs-AI log format, the player's side named HUMAN: both teams, every turn
                                      with HP, status, stages and weather, every battle message and [hit] line, the
                                      AI's decisions with the options it weighed, your choices, the result
  RUNS/aivsai/human/<session>/session.json   seed, ROM SHA-1, teams, sizes, per game the winner, turns, Pokémon left
  RUNS/aivsai/human/index.jsonl       one line per game played, 'analyzed': false (versus/human_games.py)
Closing the window or Ctrl+C in the terminal ends the session; a battle in progress is logged as abandoned.

How: versus/aivsai.py's Duel with human set (the player's menus are not handed to the AI and the runner presses
nothing while the battle runs), its bench save state and team injection. Your choices are read where the bench reads
the AI's, at overlay 14's action setters, which the player's menus call too (a call from outside both AIs' code is
yours). The window is DeSmuME's SDL window with an event filter that takes every key and mouse event before
DeSmuME sees it: py-desmume 0.0.9's own key handling shifts each key's mask twice (only X reaches the game, as A; Z
arrives as Select, Enter as Up, Right as R), so the keys are mapped here, with py-desmume's default keyboard layout
(DeSmuME's SDL defaults), and the mouse's left button becomes touch-screen presses.

Hidden test modes (no window on screen; logs under RUNS/aiplay_autotest/ unless --out):
  --autotest ai     the original AI plays the player's side through aivsai's controller swap, the window a stub
  --autotest keys   the real play window on SDL's dummy video driver, no frame pacing; a bot sends SDL key events
                    (the X key, so DS A) and one mouse click on the FIGHT button, as a person's keyboard and mouse do
  --autotest input  no battle: every mapped key, keys that must do nothing, the runner's keys outside the person's
                    turns, focus loss and mouse clicks, checked against what the game reads (about 20 s)
"""
import logging
logging.getLogger().addHandler(logging.NullHandler())   # this Python's hashlib logs a harmless blake2 traceback on import
import argparse  # noqa: E402
import ctypes  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import select  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import aibench  # noqa: E402
import aivsai  # noqa: E402
import aivsai_live  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402
import seeds as aitune  # noqa: E402  (the Spanish tools/aitune.py's seed bookkeeping, now lib/seeds.py)
from desmume.controls import Keys, keymask  # noqa: E402

HUMAN_DIR = os.path.join(tbpaths.RUNS, 'aivsai', 'human')
AUTOTEST_DIR = os.path.join(tbpaths.RUNS, 'aiplay_autotest')
SIZES = (4, 5, 6)
FRAME_LIMIT = 4 * 3600 * 60    # emulator frames (60 a second): 4 hours, then the battle counts as unfinished
HUMAN_SIDE_NAMES = {'advanced': 'ADVANCED', 'original': 'HUMAN'}
PICK = 'random'                # which members a smaller team keeps: a subset drawn from the battle's seed
TITLE = b'Origin HeartGold - you vs the advanced AI'

# py-desmume's default keyboard layout (DeSmuME's SDL frontend): the SDL keycodes of libdesmume.dylib's table at file
# offset 0x326290, in its order A, B, Select, Start, Right, Left, Up, Down, R, L, X, Y (then Debug, Boost and Lid,
# left out here: Backspace would close the DS's lid)
KEYMAP = {0x78: Keys.KEY_A, 0x7A: Keys.KEY_B, 0x400000E5: Keys.KEY_SELECT, 0x0D: Keys.KEY_START,
          0x4000004F: Keys.KEY_RIGHT, 0x40000050: Keys.KEY_LEFT, 0x40000052: Keys.KEY_UP, 0x40000051: Keys.KEY_DOWN,
          0x77: Keys.KEY_R, 0x71: Keys.KEY_L, 0x73: Keys.KEY_X, 0x61: Keys.KEY_Y}
SDLK_X = 0x78
CONTROLS = """Controls (in the game window; click it once so it gets the keyboard):
  DS A = X key       DS B = Z key       DS X = S key       DS Y = A key
  DS L = Q key       DS R = W key       Start = Enter      Select = Right Shift
  D-pad = arrow keys                    touch screen = left mouse button on the lower screen
To stop: close the window, or Ctrl+C here. A battle in progress is then logged as abandoned."""
# SDL2 event types and fields (SDL_events.h)
KEYDOWN, KEYUP = 0x300, 0x301
MOUSEMOTION, MOUSEDOWN, MOUSEUP, MOUSEWHEEL = 0x400, 0x401, 0x402, 0x403
FINGER = (0x700, 0x701, 0x702)
WINDOWEVENT, FOCUS_LOST = 0x200, 13
LEFT_BUTTON = 1
EVENT_FILTER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
# moves and items the hack's player menus handle badly (inherited from the Chinese ROM, qa/ai_research/menulock.py)
NO_SELECT = {'Pursuit'}
CHOICE = {'Choice Band', 'Choice Specs', 'Choice Scarf'}


class Stop(Exception):
    """The person ended the session (the window closed, or Ctrl+C)."""


def drop_emulator_prints():
    """Empty C's stdout buffer into /dev/null. DeSmuME's own prints (device lines, 'Savestate info') happen inside
    aivsai.quiet(), but C's stdout was first used there, on /dev/null, so it is fully buffered: they would come out
    in the player's terminal when the buffer fills or the program ends."""
    with aivsai.quiet():
        ctypes.CDLL(None).fflush(None)


def sdl_lib():
    import desmume
    sdl = ctypes.CDLL(os.path.join(os.path.dirname(desmume.__file__), *aivsai_live.SDL_LIB))
    sdl.SDL_GetWindowFromID.restype = ctypes.c_void_p
    sdl.SDL_GetWindowFromID.argtypes = [ctypes.c_uint32]
    sdl.SDL_GetWindowTitle.restype = ctypes.c_char_p
    sdl.SDL_GetWindowTitle.argtypes = [ctypes.c_void_p]
    sdl.SDL_SetWindowTitle.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    sdl.SDL_GetWindowSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    sdl.SDL_EventState.argtypes = [ctypes.c_uint32, ctypes.c_int]
    sdl.SDL_EventState.restype = ctypes.c_uint8
    sdl.SDL_SetEventFilter.argtypes = [EVENT_FILTER, ctypes.c_void_p]
    sdl.SDL_PushEvent.argtypes = [ctypes.c_void_p]
    sdl.SDL_RaiseWindow.argtypes = [ctypes.c_void_p]
    return sdl


class PlayView(aivsai_live.LiveView):
    """The game window with the person's keyboard and mouse. While human is set (the runner sets it from
    Duel.human_control) the DS keypad and touch screen follow the keys held and the left mouse button; otherwise the
    runner's own key presses stand, as in aivsai's live view. Every key and mouse event goes to _filter and no
    further, so DeSmuME never sees one (its key masks are wrong in this build, Esc would quit and F1-F10 load or
    save savestate slots)."""

    def __init__(self, emu_, speed=1.0, scale=None):
        super().__init__(emu_, speed, scale)
        self.human = self._was_human = False
        self.held = set()           # DS keys held on the keyboard
        self.pointer = None         # (x, y) on the lower screen while the left button is down there
        self.touching = False
        self.starts = 0             # Enter presses (DS Start) seen: the pause between battles waits for one
        self.sdl = sdl_lib()
        self.win = next((w for w in map(self.sdl.SDL_GetWindowFromID, range(1, 17)) if w and
                         self.sdl.SDL_GetWindowTitle(w) in (aivsai_live.WINDOW_TITLE, aivsai_live.DESMUME_TITLE)), None)
        self._cb = EVENT_FILTER(self._filter)       # kept: SDL holds only the pointer
        self.sdl.SDL_SetEventFilter(self._cb, None)
        for kind in (KEYDOWN, KEYUP, MOUSEMOTION, MOUSEDOWN, MOUSEUP):
            self.sdl.SDL_EventState(kind, 1)        # SDL_ENABLE (the live view ignores them): the filter gets them
        if self.win:
            self.sdl.SDL_SetWindowTitle(self.win, TITLE)
        self.focus()

    def focus(self):
        """The window to the front with the keyboard (after an Enter typed in the terminal)."""
        if self.win and not self._closed:
            self.sdl.SDL_RaiseWindow(self.win)

    def _filter(self, userdata, event):
        try:
            kind = ctypes.c_uint32.from_address(event).value
            if kind in (KEYDOWN, KEYUP):
                key = KEYMAP.get(ctypes.c_int32.from_address(event + 20).value)
                if key and kind == KEYDOWN:
                    self.starts += key == Keys.KEY_START and key not in self.held
                    self.held.add(key)
                elif key:
                    self.held.discard(key)
                return 0
            if kind in (MOUSEMOTION, MOUSEDOWN, MOUSEUP):
                x, y = ctypes.c_int32.from_address(event + 20).value, ctypes.c_int32.from_address(event + 24).value
                if kind == MOUSEMOTION:
                    if ctypes.c_uint32.from_address(event + 16).value & 1 and self.pointer is not None:
                        self.pointer = self.lower_screen(x, y)      # a drag off the lower screen lets go
                elif ctypes.c_uint8.from_address(event + 16).value == LEFT_BUTTON:
                    self.pointer = self.lower_screen(x, y) if kind == MOUSEDOWN else None
                return 0
            if kind == MOUSEWHEEL or kind in FINGER:
                return 0
            if kind == WINDOWEVENT and ctypes.c_uint8.from_address(event + 12).value == FOCUS_LOST:
                self.held.clear()           # a key let go in another window is never seen here
                self.pointer = None
        except Exception:                   # an exception must never cross into SDL's C code
            pass
        return 1

    def lower_screen(self, x, y):
        """Window point -> lower-screen pixel, or None off the lower screen. The renderer stretches the 256 x 384
        picture over the whole window (aivsai_live sizes it to 1x or 2x)."""
        w, h = ctypes.c_int(), ctypes.c_int()
        self.sdl.SDL_GetWindowSize(self.win, ctypes.byref(w), ctypes.byref(h))
        if w.value <= 0 or h.value <= 0:
            return None
        tx, ty = x * 256 // w.value, y * 384 // h.value - 192
        return (tx, ty) if 0 <= tx < 256 and 0 <= ty < 192 else None

    def keypad(self):
        return sum(keymask(k) for k in self.held)

    def _touch(self, point):
        if point is not None:
            self.emu.input.touch_set_pos(*point)
            self.touching = True
        elif self.touching:
            self.emu.input.touch_release()
            self.touching = False

    def _input(self):
        runner_keys = self.emu.input.keypad_get()
        self.window.process_input()                 # window events; keys and mouse end in _filter
        if self.human:
            self.emu.input.keypad_update(self.keypad())
            self._touch(self.pointer)
        else:
            # the person's keys are let go when the battle is decided; until then the runner presses nothing
            self.emu.input.keypad_update(0 if self._was_human else runner_keys)
            self._touch(None)
        self._was_human = self.human

    def frame(self):
        if self._interrupted:
            self._interrupted = False
            raise KeyboardInterrupt
        if self._closed:
            return
        self._input()
        if self.window.has_quit():
            self.close()
            return
        self.window.draw()
        self.frames += 1
        if self.speed > 0:
            self._pace(1 / (aivsai_live.DS_FPS * self.speed))

    def idle(self, seconds=1 / 30):
        """Keep the window alive without running the game (the pause between battles)."""
        if self._interrupted:
            self._interrupted = False
            raise KeyboardInterrupt
        if self._closed:
            return
        self.window.process_input()
        if self.window.has_quit():
            self.close()
            return
        self.window.draw()
        time.sleep(seconds)

    def close(self):
        if not self._closed:
            self.sdl.SDL_SetEventFilter(EVENT_FILTER(0), None)
        super().close()


class StubView:
    """--autotest ai: no window at all (the original AI plays the player's side)."""
    human = False
    starts = 0

    def __init__(self, *a, **k):
        self.frames = 0

    def frame(self):
        self.frames += 1

    def idle(self, seconds=0):
        pass

    def focus(self):
        pass

    def closed(self):
        return False

    def close(self):
        pass


class Play(aivsai.Duel):
    """aivsai's Duel with a person on the player's side: their choices logged from overlay 14's action setters."""

    def __init__(self, rom, state, human=True, trace=False):
        super().__init__(rom, state, 'adv')
        self.human = human
        self.frame_limit = FRAME_LIMIT if human else aivsai.FRAME_LIMIT
        self.trace = trace          # every setter call into the log ([setter] lines): how the menus were verified
        self.choices = 0            # the person's choices in the current battle
        # asserts still reach the battle result (session.json 'failures'), but not the player's terminal: the
        # inherited end-of-battle assert (020733B2) would print after every battle
        self.mem.register_exec(emu.ASSERT_FAIL, lambda a, s: self.r.event(ev='assert', lr='%08X' % (self.reg.r14 - 1)))

    def _setter(self, kind):
        ai = super()._setter(kind)

        def f(a, s):
            ai(a, s)
            if self.human:
                self.human_choice(kind)
        return f

    def human_choice(self, kind):
        """A setter call from neither AI's code nor the AI's replacement chooser is the player's menus: a move, an
        item, a switch (a replacement when the Pokémon on the field has fainted)."""
        c, mu = self.cur, self.mu
        if c is None or not c.get('injected') or not self.in_battle():
            return
        lr, r1, r2 = self.reg.r14, self.reg.r1, self.reg.r2
        if self.trace and self.live:
            self.live({'kind': 'setter', 'call': kind, 'lr': '%08X' % lr, 'r1': r1, 'r2': r2,
                       'sp0': mu.read_long(self.reg.r13) & 0xFF})
        if kind == 'none' or lr == aivsai.REPLACE_LR or aivsai.ADV_CODE[0] <= lr < aivsai.ADV_CODE[1] or \
                aivsai.ORIG_CODE[0] <= lr < aivsai.ORIG_CODE[1]:
            return
        key = (self.r.frames, kind, r1, r2)
        if key == c.get('last_human'):
            return
        c['last_human'] = key
        self.choices += 1
        party, foe = self.party(0) or [], self.party(1) or []
        me = party[0] if party else 0
        ev = {'kind': 'decision', 'side': 'original', 'pokemon': self.species_of(me), 'action': kind, 'target': None}
        if kind == 'move':
            ev['name'] = self.d.move_name.get(r1, str(r1))
            ev['target'] = self.species_of(foe[0]) if foe else None
        elif kind == 'item':
            ev['name'] = self.d.item_name.get(r1, str(r1))
        else:
            ev['name'] = self.species_of(party[r2]) if r2 < len(party) else str(r2)
            if me and mu.read_short(me + 0x1E) == 0:        # its Pokémon fainted: the replacement
                self.report_faints()
                ev = {'kind': 'switch', 'side': 'original', 'from': ev['pokemon'], 'to': ev['name']}
        self.live(ev)


# --- the session's battles
def fresh_seed():
    rng, held = random.SystemRandom(), aitune.holdout_seeds()     # the scorer's seeds: never drawn or accepted here
    while True:
        s = rng.randrange(1 << 31)
        if s not in held:
            return s


def draw_games(n, teams, level, seed, sizes=None):
    """n battles: aivsai's scenarios (two distinct teams each), team A for the AI and team B for the person, cut
    with aivsai's cut_team. sizes (person, AI) fixed, or None: one size from SIZES per battle for both sides, drawn
    from the session seed."""
    scenarios = aivsai.draw_scenarios(n, teams, level, seed)
    rng = random.Random('aiplay sizes %d' % seed)
    games = []
    for k, s in enumerate(scenarios):
        human_n, ai_n = sizes or (rng.choice(SIZES),) * 2
        g = aivsai.games_of([s], False, (ai_n, human_n), PICK)[0]
        g['scenario'] = 'g%02d' % (k + 1)
        games.append(g)
    return games


def mon_text(m):
    """One team member for the terminal: species, item, ability, moves, nature, with the inherited menu bugs."""
    moves = ', '.join(mv + (' (cannot be selected: inherited bug)' if mv in NO_SELECT else '') for mv in m['moves'])
    item = m.get('item') or '-'
    note = '  (once its locked move is out of PP the menu takes no move: switch it out)' if item in CHOICE else ''
    return '  %-12s @ %-14s %-15s %-8s %s%s' % (m['species'], item, m.get('ability') or '-', m.get('nature') or '-', moves, note)


def header_lines(stamp, game, n, of, seed, a, rom_sha1, mode):
    side = 'ORIGINAL' if mode == 'autotest-ai' else 'HUMAN'
    sizes = aivsai.game_sizes(game)
    return (['aiplay session %s, game %d of %d (%s), session seed %d, battle seed %d, teams %s, level %d, %s %d vs ADVANCED %d, '
             'ROM %s (SHA-1 %s), mode %s' % (stamp, n, of, game['scenario'], seed, game['seed'], a.teams, a.level, side,
                                              sizes['original'], sizes['advanced'], os.path.basename(a.rom), rom_sha1, mode)] +
            aivsai.team_lines('ADVANCED', game['adv']) + aivsai.team_lines(side, game['orig']))


def played(duel, game, path, header, n, of):
    """One battle, every event written to path. Returns (aivsai's battle result, why the session stops): None to go
    on; the reason when the person stopped the battle (end 'abandoned') or the tool failed in it (end 'error', the
    traceback in the log and on stderr); the result is then partial."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(header) + '\n')

        def log(ev):
            f.write(aivsai_live.format_event(ev, color=False) + '\n')
            f.flush()
        duel.live = log
        duel.choices = 0
        t0 = time.time()
        try:
            log({'kind': 'battle', 'n': n, 'of': of, 'adv_team': game['adv']['name'], 'orig_team': game['orig']['name'],
                 'sizes': aivsai.game_sizes(game)})
            res, stopped = duel.play(game), None
        except (Stop, KeyboardInterrupt) as e:
            stopped = str(e) if isinstance(e, Stop) else 'Ctrl+C'
            res = abandoned(duel, game)
            log({'kind': 'end', 'winner': None, 'left': res['left'], 'turns': res['turns'], 'end': 'abandoned'})
            f.write('stopped by the player (%s)\n' % stopped)
        except Exception as e:              # a bug here must not lose the game: logged, then the session stops
            import traceback
            stopped = 'error: %s: %s' % (type(e).__name__, e)
            res = abandoned(duel, game, 'error')
            log({'kind': 'end', 'winner': None, 'left': res['left'], 'turns': res['turns'], 'end': 'error'})
            f.write(traceback.format_exc())
            traceback.print_exc()
        finally:
            duel.live = None
            duel.human_control = False
            drop_emulator_prints()
        res['seconds'] = round(time.time() - t0, 1)
    return res, stopped


def abandoned(duel, game, end='abandoned'):
    """What a battle that was stopped got to: turns, Pokémon left (read while the battle's memory is there)."""
    c, duel.cur = duel.cur or {}, None
    left = None
    if c.get('injected') and duel.in_battle():
        a = duel.alive_counts()
        left = {'original': a[0], 'advanced': a[1]} if a else None
    return {'scenario': game['scenario'], 'game': 0, 'adv_team': game['adv']['name'], 'orig_team': game['orig']['name'],
            'sizes': aivsai.game_sizes(game), 'parties': None, 'winner': None, 'end': end, 'turns': c.get('turn', 0),
            'left': left or {'original': 0, 'advanced': 0}, 'frames': 0,
            'decisions': c.get('decisions', {}), 'adv_fallbacks': c.get('fallbacks', {}).get('advanced', {}),
            'ai_replacements': c.get('ai_replacements', {}),
            'failures': [{'ev': f['ev'], 'text': f.get('text'), 'move_text': f.get('move_text')} for f in c.get('fail_detail', [])]}


WINNER = {'advanced': 'ai', 'original': 'human'}


def game_record(game, res, choices, log_rel):
    left = res.get('left') or {}
    return {'game': game['scenario'], 'log': log_rel, 'battle_seed': game['seed'],
            'sizes': {'human': len(game['orig']['team']), 'ai': len(game['adv']['team'])},
            'winner': WINNER.get(res.get('winner')), 'end': res['end'], 'turns': res.get('turns', 0),
            'left': {'human': left.get('original', 0), 'ai': left.get('advanced', 0)},
            'human_choices': choices, 'ai_decisions': (res.get('decisions') or {}).get('advanced'),
            'ai_fallbacks': res.get('adv_fallbacks'), 'ai_replacements': (res.get('ai_replacements') or {}).get('advanced'),
            'parties': res.get('parties'), 'failures': res.get('failures', []), 'seconds': res.get('seconds'),
            'teams': {'human': game['orig'], 'ai': game['adv']}}


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def index_line(session, rec, mode):
    return {'id': '%s/%s' % (session['session'], rec['game']), 'session': session['session'], 'game': rec['game'],
            'log': rec['log'], 'date': session['started'], 'mode': mode, 'rom_sha1': session['rom_sha1'],
            'teams': session['teams'], 'level': session['level'], 'sizes': rec['sizes'], 'winner': rec['winner'],
            'end': rec['end'], 'turns': rec['turns'], 'left': rec['left'], 'finished': rec['end'] not in ('abandoned', 'error'),
            'analyzed': False}


def result_text(rec):
    if rec['end'] in ('abandoned', 'error'):
        return 'Stopped%s after %d turns (logged as %s).' % (' by an error' if rec['end'] == 'error' else '', rec['turns'], rec['end'])
    who = {'human': 'You won', 'ai': 'The advanced AI won'}.get(rec['winner'], 'No winner')
    tail = '' if rec['end'] == 'normal' else ' (%s)' % rec['end']
    return '%s after %d turns%s. Pokémon left: you %d, AI %d.' % (who, rec['turns'], tail, rec['left']['human'], rec['left']['ai'])


def wait_for_start(view, n, of):
    """Between battles: Enter in the terminal or in the game window starts the next one; q + Enter in the terminal,
    a closed window or Ctrl+C stops. Without a terminal (tests) it goes on at once."""
    if not sys.stdin.isatty():
        return
    print('Press Enter to start battle %d of %d (here or in the game window), or q then Enter to stop.' % (n, of), flush=True)
    starts = view.starts
    while True:
        view.idle()
        if view.closed():
            raise Stop('window closed')
        if view.starts != starts:
            return
        if select.select([sys.stdin], [], [], 0)[0]:
            typed = sys.stdin.readline()
            if not typed or typed.strip().lower().startswith('q'):      # q, or the end of input (Ctrl+D)
                raise Stop('stopped between battles')
            view.focus()
            return


# --- the --autotest keys bot: what a person's keyboard and mouse send, as SDL events
class KeyBot:
    """While the person has control, every 40 frames for 4 frames: the X key (DS A); or, while its Pokémon on the
    field has fainted (the party screen asks for a replacement, its cursor on the fainted one), a left click on the
    first able Pokémon's panel and then on CAMBIAR (Shift), in turn. Once, when the battle's FIGHT button first
    shows, a left click on it, recording whether the click opened the move menu."""
    FIGHT = (128, 70)       # lower-screen pixel inside the FIGHT button (emu.STATES['fight_menu'] checks (128, 262))
    SHIFT = (128, 108)      # CAMBIAR in the chosen Pokémon's menu (screenshot of the battle's party screen)

    @staticmethod
    def panel(i):
        """The middle of party member i's panel on the battle's party screen: two columns of three."""
        return 64 + 128 * (i % 2), 28 + 48 * (i // 2)

    def __init__(self, view, duel):
        self.view, self.duel, self.k = view, duel, 0
        self.ev = ctypes.create_string_buffer(56)
        self.clicked, self.click_result = None, None
        self.down = None            # what is held now: ('key', sym) or ('click', point)

    def push(self, kind, fields):
        """An SDL event of this type with fields {offset: (ctypes type, value)}, from window 1."""
        ctypes.memset(self.ev, 0, 56)
        ctypes.c_uint32.from_buffer(self.ev, 0).value = kind
        ctypes.c_uint32.from_buffer(self.ev, 8).value = 1
        for off, (ctype, v) in fields.items():
            ctype.from_buffer(self.ev, off).value = v
        self.view.sdl.SDL_PushEvent(self.ev)

    def key(self, down, sym=SDLK_X):
        self.push(KEYDOWN if down else KEYUP, {12: (ctypes.c_uint8, int(down)), 20: (ctypes.c_int32, sym)})

    def click(self, down, point):
        w, h = ctypes.c_int(), ctypes.c_int()
        self.view.sdl.SDL_GetWindowSize(self.view.win, ctypes.byref(w), ctypes.byref(h))
        x, y = (point[0] * w.value + w.value // 2) // 256, ((point[1] + 192) * h.value + h.value // 2) // 384
        self.push(MOUSEDOWN if down else MOUSEUP, {16: (ctypes.c_uint8, LEFT_BUTTON), 17: (ctypes.c_uint8, int(down)),
                                                   20: (ctypes.c_int32, x), 24: (ctypes.c_int32, y)})

    def __call__(self):
        if not self.duel.human_control:
            self.k = 0
            return
        self.k += 1
        r = self.duel.r
        if self.click_result is None:
            if self.clicked is None and self.k % 10 == 0 and r.seen(emu.STATES['fight_menu']):
                self.clicked = self.k
                self.click(True, self.FIGHT)
                return
            if self.clicked is not None:
                if self.k == self.clicked + 6:
                    self.click(False, self.FIGHT)
                elif self.k == self.clicked + 60:
                    self.click_result = not r.seen(emu.STATES['fight_menu'])     # the move menu replaced it
                return
        if self.k % 40 == 0:
            hp = [self.duel.mu.read_short(b + 0x1E) for b in self.duel.party(0) or []]
            able = next((i for i, v in enumerate(hp) if v), None)
            if hp and not hp[0] and able is not None:
                self.down = ('click', self.panel(able) if self.k // 40 % 2 else self.SHIFT)
                self.click(True, self.down[1])
            else:
                self.down = ('key', SDLK_X)
                self.key(True)
        elif self.k % 40 == 4 and self.down:
            (self.click if self.down[0] == 'click' else self.key)(False, self.down[1])
            self.down = None


# --- --autotest input: the window's input path, with no battle
G_SYSTEM, TOUCH_X, TOUCH_Y, TOUCH_HELD = 0x021D0094, 0x60, 0x62, 0x66   # gSystem's touch fields (found with touch_set_pos)
KEY_INPUT = 0x04000130          # REG_KEYINPUT as the ARM9 reads it: A B Select Start Right Left Up Down R L, 0 = held
DROPPED = {'F1': 0x4000003A, 'Escape': 0x1B, 'Backspace': 0x08, 'P': 0x70, 'O': 0x6F, 'F11': 0x40000044}


def input_test(rom):
    """PlayView on SDL's dummy video driver, fed SDL events as a keyboard and mouse send them: the DS buttons the
    game reads, keys that must do nothing, the runner's keys outside the person's turns, focus loss, and mouse
    clicks as touches (the game's own touch fields) at 2x and 1x. Returns the number of failed checks."""
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.makedirs(AUTOTEST_DIR, exist_ok=True)
    copy = aibench.link_rom(rom, os.path.join(AUTOTEST_DIR, 'aiplay_input.nds'))   # its own battery save name
    with aivsai.quiet():
        r = emu.Runner(copy, os.path.join(AUTOTEST_DIR, 'shots'))
    r.skip_render = True
    r.step(400)                     # past the boot logos: the game samples the touch screen every frame
    view = PlayView(r.emu, 0, 2)
    bot = KeyBot(view, None)
    mu, fails = r.emu.memory.unsigned, []

    def frames(n=3):
        for _ in range(n):
            r.step(1)
            view.frame()

    def pad():
        """The DS buttons held, as keymask bits: the ARM9's register for A to L, the emulator's keypad for X and Y."""
        return (~mu.read_short(KEY_INPUT) & 0x3FF) | (r.emu.input.keypad_get() & 0xC00)

    def check(name, ok, got=''):
        print('  %-58s %s%s' % (name, 'ok' if ok else 'FAIL', '' if ok else '  (%s)' % got))
        if not ok:
            fails.append(name)
    names = {v: k for k, v in vars(Keys).items() if k.startswith('KEY_')}
    try:
        view.human = True
        for sym, key in KEYMAP.items():
            bot.key(True, sym)
            frames()
            down = pad()
            bot.key(False, sym)
            frames()
            check('key %#x -> DS %s' % (sym, names[key][4:]), down == keymask(key) and pad() == 0, 'held %#05x, then %#05x' % (down, pad()))
        for name, sym in DROPPED.items():
            bot.key(True, sym)
            frames()
            got = pad()
            bot.key(False, sym)
            frames()
            check('key %s does nothing' % name, got == 0 and pad() == 0 and not view.closed(), 'held %#05x' % got)
        bot.key(True)
        frames()
        bot.push(WINDOWEVENT, {12: (ctypes.c_uint8, FOCUS_LOST)})
        frames()
        check('focus lost lets go of the keys held', pad() == 0, '%#05x' % pad())
        bot.key(False)
        bot.key(True)
        frames()
        view.human = False
        frames()
        check('the end of the person\'s control lets go of their keys', pad() == 0, '%#05x' % pad())
        bot.key(False)
        r.emu.input.keypad_add_key(keymask(Keys.KEY_A))         # the runner holds A, as Runner.hold does
        bot.key(True, 0x7A)
        frames()
        check('outside the person\'s control: the runner\'s A stays, Z is ignored', pad() == keymask(Keys.KEY_A), '%#05x' % pad())
        bot.key(False, 0x7A)
        r.emu.input.keypad_rm_key(keymask(Keys.KEY_A))
        frames()
        view.human = True
        for size in (2, 1):
            view.sdl.SDL_SetWindowSize.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
            view.sdl.SDL_SetWindowSize(view.win, 256 * size, 384 * size)
            for point in ((10, 10), (128, 96), (250, 185)):
                bot.click(True, point)
                frames(4)
                got = tuple(mu.read_short(G_SYSTEM + o) for o in (TOUCH_X, TOUCH_Y, TOUCH_HELD))
                bot.click(False, point)
                frames(4)
                held = mu.read_short(G_SYSTEM + TOUCH_HELD)
                check('%dx window: click on lower screen %s -> touch' % (size, point),
                      abs(got[0] - point[0] - 1) <= 1 and abs(got[1] - point[1] - 1) <= 1 and got[2] == 1 and held == 0,
                      'game read x %d y %d held %d, then held %d' % (got + (held,)))
            bot.click(True, (128, -96))                         # the upper screen
            frames(4)
            got = mu.read_short(G_SYSTEM + TOUCH_HELD)
            bot.click(False, (128, -96))
            frames(4)
            check('%dx window: a click on the upper screen touches nothing' % size, got == 0, 'held %d' % got)
    finally:
        view.close()
        for p in (copy, os.path.join(aibench.DSV_DIR, 'aiplay_input.dsv')):
            if os.path.lexists(p):
                os.remove(p)
    drop_emulator_prints()
    print('input test: %d checks failed' % len(fails) if fails else 'input test: all checks passed')
    return len(fails)


def main():
    os.environ.setdefault('ADVAI_EMU_SLOTS', '0')  # a person plays: never wait for a slot of the emulator pool (emupool.py)
    ap = argparse.ArgumentParser(description='Play battles against the advanced trainer AI; every battle is logged '
                                             'for analysis (RUNS/aivsai/human/).')
    ap.add_argument('battles', nargs='?', type=int, default=1, help='how many battles to play in a row (default 1)')
    ap.add_argument('--teams', choices=('mixed', 'random', 'trainers'), default='mixed',
                    help="mixed (default): new teams of the ROM trainers' Pokémon, each with its own moves, item, EVs and "
                         "nature; random: any species, any moves; trainers: the ROM's own teams")
    size = lambda v: int(v) if v.isdigit() and 1 <= int(v) <= aivsai.FULL_TEAM else ap.error('a team size is 1 to 6, not %r' % v)  # noqa: E731
    ap.add_argument('--size', type=size, help='both teams this size every battle (default: 4, 5 or 6, drawn per battle)')
    ap.add_argument('--sizes', metavar='N:M', help='your team N Pokémon, the AI\'s M')
    ap.add_argument('--level', type=int, default=100, help='every Pokémon at this level (default 100)')
    ap.add_argument('--seed', type=int, help='replay a session: the same teams and sizes')
    ap.add_argument('--rom', required=True, help='the ROM to play (an AI build)')
    ap.add_argument('--payload', help='the AI build\'s payload.json (default: ADVAI_PAYLOAD)')
    ap.add_argument('--out', help=argparse.SUPPRESS)          # the logs' root (default RUNS/aivsai/human)
    ap.add_argument('--autotest', choices=('ai', 'keys', 'input'), help=argparse.SUPPRESS)
    ap.add_argument('--trace', action='store_true', help=argparse.SUPPRESS)   # [setter] lines in the logs
    a = ap.parse_args()
    payload.path_from(a.payload)
    os.environ['ADVAI_TEAMS_ROM'] = os.path.abspath(a.rom)
    if a.size and a.sizes:
        ap.error('give --size or --sizes, not both')
    sizes = None
    if a.size:
        sizes = (a.size, a.size)
    elif a.sizes:
        n, _, m = a.sizes.partition(':')
        sizes = (size(n), size(m))
    if a.seed in aitune.holdout_seeds():
        ap.error('seed %d is held out for the AI loop: pick another' % a.seed)
    if a.battles < 1:
        ap.error('play at least one battle')
    if a.autotest == 'input':
        return 1 if input_test(a.rom) else 0
    seed = a.seed if a.seed is not None else fresh_seed()
    mode = 'autotest-' + a.autotest if a.autotest else 'human'
    if a.autotest == 'keys':
        os.environ['SDL_VIDEODRIVER'] = 'dummy'     # SDL's window with no screen: nothing pops up
    root = os.path.abspath(a.out or (AUTOTEST_DIR if a.autotest else HUMAN_DIR))
    started = datetime.datetime.now()
    stamp = started.strftime('%Y%m%d_%H%M%S')
    session_dir = os.path.join(root, stamp)
    while os.path.exists(session_dir):
        session_dir += 'b'
    stamp = os.path.basename(session_dir)
    games = draw_games(a.battles, a.teams, a.level, seed, sizes)
    rom_sha1 = hashlib.sha1(open(a.rom, 'rb').read()).hexdigest()
    aivsai_live.SIDE_NAMES = aivsai_live.AI_SIDE_NAMES if a.autotest == 'ai' else HUMAN_SIDE_NAMES
    print('Play mode: %d battle(s) against the advanced AI, teams %s, level %d, %s; session seed %d (--seed %d replays the '
          'teams)' % (len(games), a.teams, a.level, 'sizes %d (you) vs %d (AI)' % sizes if sizes else 'sizes 4 to 6 per battle',
                      seed, seed), flush=True)
    print('Logs: %s' % tbpaths.rel(session_dir), flush=True)
    if not a.autotest:
        print(CONTROLS, flush=True)
    print('Preparing the emulator...', flush=True)
    tag = 'aiplay' if not a.autotest else 'aiplay_autotest_' + a.autotest
    try:
        rom_copy, state, save = aivsai.prepare(a.rom, False, tag)
    except KeyboardInterrupt:
        print('\nstopped before the first battle; nothing was logged')
        return 1
    duel = Play(rom_copy, state, human=a.autotest != 'ai', trace=a.trace)
    if a.autotest:
        duel.frame_limit = aivsai.FRAME_LIMIT       # a test battle that runs 30 minutes of game time has gone wrong
    drop_emulator_prints()
    if a.autotest == 'ai':
        view = StubView()
    else:
        view = PlayView(duel.r.emu, 0 if a.autotest else 1.0, 2 if a.autotest else None)
        duel.window = True
        duel.r.skip_render = False
    bot = KeyBot(view, duel) if a.autotest == 'keys' else None
    step = duel.r.step

    def paced(n=1):
        for _ in range(n):
            step(1)
            view.human = duel.human_control
            view.frame()
            if view.closed():
                raise Stop('window closed')
            if bot:
                bot()
    duel.r.step = paced
    session = {'session': stamp, 'started': started.strftime('%Y-%m-%d %H:%M'), 'mode': mode, 'seed': seed,
               'rom': tbpaths.rel(os.path.abspath(a.rom)), 'rom_sha1': rom_sha1, 'teams': a.teams, 'level': a.level,
               'sizes': {'human': sizes[0], 'ai': sizes[1]} if sizes else 'per battle from %s' % list(SIZES),
               'battles': len(games), 'games': [], 'results': {'human': 0, 'ai': 0, 'none': 0}}
    os.makedirs(session_dir)
    session_json = os.path.join(session_dir, 'session.json')
    write_json(session_json, session)
    index = os.path.join(root, 'index.jsonl')
    stopped = None
    try:
        for i, game in enumerate(games):
            print('\nBattle %d of %d: you %d vs the advanced AI %d. Your team:' % (
                i + 1, len(games), len(game['orig']['team']), len(game['adv']['team'])), flush=True)
            for m in game['orig']['team']:
                print(mon_text(m), flush=True)
            wait_for_start(view, i + 1, len(games))
            path = os.path.join(session_dir, '%s.log' % game['scenario'])
            header = header_lines(stamp, game, i + 1, len(games), seed, a, rom_sha1, mode)
            res, stopped = played(duel, game, path, header, i + 1, len(games))
            rec = game_record(game, res, duel.choices, tbpaths.rel(path))
            session['games'].append(rec)
            session['results'][rec['winner'] or 'none'] += 1
            write_json(session_json, session)
            with open(index, 'a', encoding='utf-8') as f:
                f.write(json.dumps(index_line(session, rec, mode), ensure_ascii=False) + '\n')
            print(result_text(rec), flush=True)
            if stopped:
                break
    except (Stop, KeyboardInterrupt) as e:
        stopped = str(e) if isinstance(e, Stop) else 'Ctrl+C'
    finally:
        view.close()
        drop_emulator_prints()
        for p in (rom_copy, os.path.join(aibench.DSV_DIR, '%s.dsv' % tag)):
            if os.path.lexists(p):
                os.remove(p)
    res = session['results']
    print('\nSession over%s: %d battle(s) played; you won %d, the AI won %d%s.' % (
        ' (%s)' % stopped if stopped else '', len(session['games']), res['human'], res['ai'],
        ', %d without a winner' % res['none'] if res['none'] else ''))
    print('Logs: %s (index: %s)' % (tbpaths.rel(session_dir), tbpaths.rel(index)))
    if bot:
        print('autotest keys: FIGHT click opened the move menu: %s' % bot.click_result)
    if not a.autotest:
        print('When you are done playing, the logs are ready for analysis (versus/human_games.py list).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
