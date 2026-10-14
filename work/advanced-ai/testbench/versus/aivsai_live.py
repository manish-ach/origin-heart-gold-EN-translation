"""Live mode of the AI-vs-AI bench (the Spanish qa/aivsai_plan.md, "Live mode"): the emulator window at normal speed
and the live events as readable terminal lines; format_event also writes every battle log of a headless run.

  .venv/bin/python work/advanced-ai/testbench/versus/aivsai_live.py --selftest             # a synthetic battle, no window
  .venv/bin/python work/advanced-ai/testbench/versus/aivsai_live.py --window-test ROM [--speed 2]   # ~600 frames

Ported from the Spanish workspace's tools/aivsai_live.py (dc8577c); only the imports and the run folder changed (the
selftest's battle messages stay Spanish: they only test the formatting).

versus/aivsai.py makes one LiveView per run (py-desmume keeps one window per process), calls frame() after every
emulated frame and log() for every live event, all on the main thread: macOS lets SDL open windows and read
their events only there.

The window only shows the game. py-desmume's input call ends by setting the DS keypad to the window's keyboard
state, every call, which would let go of a key the runner holds after one frame; frame() puts the runner's keys
back. Keyboard and mouse events are switched off in SDL, so nothing typed or clicked in the window reaches the
game (in a plain DeSmuME window F1-F10 save or load savestate slots and Esc quits). Closing the window or Ctrl+C
in the terminal stops the run: on a close frame() destroys the window and closed() turns true; on a Ctrl+C the
next frame() raises KeyboardInterrupt.
"""
import argparse
import ctypes
import math
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)

DS_FPS = 59.8261        # the DS's refresh rate: normal speed
MAX_LAG = 0.1           # seconds behind schedule before the schedule restarts from now instead of catching up
AI_SIDE_NAMES = {'advanced': 'ADVANCED', 'original': 'ORIGINAL'}    # the trainer's side and the player's side
SELF_SIDE_NAMES = {'advanced': 'TRAINER', 'original': 'PLAYER'}      # the same, with the advanced AI on both (--self)
SIDE_NAMES = AI_SIDE_NAMES
SIDE_COLORS = {'advanced': '36', 'original': '33'}              # ANSI cyan and yellow
RULE = 72               # width of the battle, turn and end rules
MAX_OPTIONS = 5
BAR_CELLS = 10
NAME_WIDTH = 12
INDENT = ' ' * 12       # under the Pokémon of a side line ('  ADVANCED  Garchomp')
MESSAGE = '  >> '       # before a battle message

# SDL (the copy libdesmume links): the window it opens is titled 'Desmume SDL', 256 x 384, not resizable
SDL_LIB = ('.dylibs', 'libSDL2-2.0.0.dylib')
DESMUME_TITLE, WINDOW_TITLE = b'Desmume SDL', b'Origin HeartGold - AI vs AI'
WINDOWPOS_CENTERED = 0x2FFF0000     # | display index
INPUT_EVENTS = (0x300, 0x301, 0x302, 0x303, 0x400, 0x401, 0x402, 0x403)   # keyboard: down, up, editing, text;
                                                                           # mouse: motion, down, up, wheel


class Rect(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int), ('w', ctypes.c_int), ('h', ctypes.c_int)]


def viewer_window(scale):
    """Title, size (scale None: 2x when the screen has room, else 1x) and keyboard and mouse events off for
    DeSmuME's window. Returns the scale, or None when that window is not found (it stays as DeSmuME made it)."""
    import desmume
    sdl = ctypes.CDLL(os.path.join(os.path.dirname(desmume.__file__), *SDL_LIB))
    sdl.SDL_GetWindowFromID.restype = ctypes.c_void_p
    sdl.SDL_GetWindowFromID.argtypes = [ctypes.c_uint32]
    sdl.SDL_GetWindowTitle.restype = ctypes.c_char_p
    sdl.SDL_GetWindowTitle.argtypes = [ctypes.c_void_p]
    sdl.SDL_GetWindowDisplayIndex.argtypes = [ctypes.c_void_p]
    sdl.SDL_GetDisplayUsableBounds.argtypes = [ctypes.c_int, ctypes.POINTER(Rect)]
    sdl.SDL_SetWindowTitle.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    sdl.SDL_SetWindowSize.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    sdl.SDL_SetWindowPosition.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    sdl.SDL_EventState.argtypes = [ctypes.c_uint32, ctypes.c_int]
    win = next((w for w in map(sdl.SDL_GetWindowFromID, range(1, 17)) if w and sdl.SDL_GetWindowTitle(w) == DESMUME_TITLE), None)
    if not win:
        return None
    display = max(sdl.SDL_GetWindowDisplayIndex(win), 0)
    if scale is None:
        r = Rect()
        roomy = sdl.SDL_GetDisplayUsableBounds(display, ctypes.byref(r)) == 0 and r.w >= 512 and r.h >= 768 + 64
        scale = 2 if roomy else 1
    sdl.SDL_SetWindowTitle(win, WINDOW_TITLE)
    sdl.SDL_SetWindowSize(win, 256 * scale, 384 * scale)       # the renderer stretches each frame to the window
    sdl.SDL_SetWindowPosition(win, WINDOWPOS_CENTERED | display, WINDOWPOS_CENTERED | display)
    for kind in INPUT_EVENTS:
        sdl.SDL_EventState(kind, 0)                            # SDL_IGNORE
    return scale


class LiveView:
    """The emulator's window at DS_FPS x speed (0 = no limit), and the live events printed."""

    def __init__(self, emu, speed=1.0, scale=None):
        self.emu, self.speed = emu, speed
        self.window = emu.create_sdl_window(auto_pause=False, use_opengl_if_possible=False)
        try:
            self.scale = viewer_window(scale)
        except (OSError, AttributeError):       # no such SDL library or call: DeSmuME's own window still works
            self.scale = None
        self.color = stdout_color()
        self.frames = 0
        self._due, self._closed, self._interrupted = None, False, False
        try:
            # a Ctrl+C that lands in one of the emulator's Python callbacks would be printed and dropped by ctypes,
            # so the handler only takes note and frame() raises it
            self._old_sigint = signal.signal(signal.SIGINT, self._sigint)
        except ValueError:                      # not the main thread
            self._old_sigint = None

    def _sigint(self, signum, frame):
        if self._interrupted:                   # a second Ctrl+C before frame() acted on the first
            raise KeyboardInterrupt
        self._interrupted = True

    def frame(self):
        if self._interrupted:
            self._interrupted = False
            raise KeyboardInterrupt
        if self._closed:
            return
        keys = self.emu.input.keypad_get()
        self.window.process_input()             # ends by setting the DS keypad to the window's (empty) keyboard
        self.emu.input.keypad_update(keys)
        if self.window.has_quit():
            self.close()
            return
        self.window.draw()
        self.frames += 1
        if self.speed > 0:
            self._pace(1 / (DS_FPS * self.speed))

    def _pace(self, period):
        now = time.perf_counter()
        if self._due is None or now - self._due > MAX_LAG:
            self._due = now                     # first frame, or too far behind: no debt carried
        elif self._due > now:
            time.sleep(self._due - now)
        self._due += period

    def closed(self):
        return self._closed

    def close(self):
        if not self._closed:
            self._closed = True
            self.window.destroy()               # SDL_Quit; py-desmume calls it again when the emulator goes, harmlessly
        if self._old_sigint is not None and signal.getsignal(signal.SIGINT) == self._sigint:
            signal.signal(signal.SIGINT, self._old_sigint)
            self._old_sigint = None

    def log(self, event):
        print(format_event(event, self.color), flush=True)


# --- the terminal lines

def use_side_names(self_play):
    """Name the sides by their AI, or by side when the advanced AI plays both (aivsai --self). Once per process:
    each aivsai worker and the live run play one mode."""
    global SIDE_NAMES
    SIDE_NAMES = SELF_SIDE_NAMES if self_play else AI_SIDE_NAMES


def stdout_color():
    return sys.stdout.isatty() and 'NO_COLOR' not in os.environ and os.environ.get('TERM') != 'dumb'


def paint(text, code, color):
    return '\033[%sm%s\033[0m' % (code, text) if color and code else text


def side_tag(side, color):
    return paint(SIDE_NAMES.get(side, str(side).upper() if side else '?').ljust(8), SIDE_COLORS.get(side), color)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def num(v):
    return (str(int(v)) if float(v).is_integer() else '%.1f' % v) if is_num(v) and math.isfinite(v) else str(v)


def weighed(entries):
    """'name=value, ...' best first, at most MAX_OPTIONS, with the rest counted."""
    if not isinstance(entries, (list, tuple)):
        raise TypeError('options and scores are lists of [name, value]')
    pairs = [(str(e[0]), e[1]) if isinstance(e, (list, tuple)) and len(e) >= 2 else (str(e), None) for e in entries]
    pairs.sort(key=lambda p: -p[1] if is_num(p[1]) and not math.isnan(p[1]) else math.inf)
    text = ', '.join('%s=%s' % (n, num(v)) if v is not None else n for n, v in pairs[:MAX_OPTIONS])
    return text + (' (+%d more)' % (len(pairs) - MAX_OPTIONS) if len(pairs) > MAX_OPTIONS else '')


def hp_bar(hp, maxhp):
    """BAR_CELLS cells: full only at full HP, at least one while any HP is left."""
    cells = min(BAR_CELLS - int(hp < maxhp), max(int(hp > 0), round(BAR_CELLS * hp / maxhp)))
    return '█' * cells + '░' * (BAR_CELLS - cells)


def rule(plain, painted, char):
    return painted + ' ' + char * max(3, RULE - len(plain) - 1)


def fmt_battle(ev, color):
    """The battle's rule and both teams; with 'sizes' ({'advanced': 4, 'original': 6}) each team's Pokémon count."""
    n, of = ev.get('n'), ev.get('of')
    title = '%s Battle %s' % ('=' * 3, n if of is None else '%s of %s' % (n, of))
    sizes = ev.get('sizes') if isinstance(ev.get('sizes'), dict) else {}
    count = lambda side: ', %s Pokémon' % sizes[side] if side in sizes else ''  # noqa: E731
    return '\n'.join(['', paint(rule(title, title, '='), '1', color),
                      '  %s  %s (trainer side%s)' % (side_tag('advanced', color), ev.get('adv_team', '?'), count('advanced')),
                      '  %s  %s (player side%s)' % (side_tag('original', color), ev.get('orig_team', '?'), count('original'))])


def mon_state(mon):
    """'TOX confused Atk+2 Spe-1': the main status, confusion and the stat stages that are not 0; '' for none."""
    parts = [str(mon['status'])] if mon.get('status') else []
    parts += ['confused'] if mon.get('confused') else []
    stages = mon.get('stages') if isinstance(mon.get('stages'), dict) else {}
    return ' '.join(parts + ['%s%+d' % (k, v) for k, v in stages.items() if is_num(v) and v])


def mon_line(side, mon, color):
    mon = mon if isinstance(mon, dict) else {}
    hp, maxhp = mon.get('hp'), mon.get('maxhp')
    head = '  %s  %s' % (side_tag(side, color), str(mon.get('species', '?')).ljust(NAME_WIDTH))
    state = mon_state(mon)
    if is_num(hp) and is_num(maxhp) and maxhp > 0:
        return '%s %3d/%-3d %s' % (head, hp, maxhp, hp_bar(hp, maxhp)) + ('  ' + state if state else '')
    return '%s   ?/?' % head + ('  ' + state if state else '')


def weather_text(w):
    """'rain, 4 turns left', or 'sun' when it has no limit."""
    left = w.get('turns_left')
    return str(w.get('kind', '?')) + (', %s turn%s left' % (num(left), '' if left == 1 else 's') if is_num(left) else '')


def fmt_turn(ev, color):
    title = '--- Turn %s' % ev.get('turn', '?')
    if isinstance(ev.get('weather'), dict):
        title += ' (%s)' % weather_text(ev['weather'])
    lines = [rule(title, title, '-'), mon_line('advanced', ev.get('adv'), color)]
    if ev.get('adv2'):
        lines.append(mon_line('advanced', ev['adv2'], color))
    lines.append(mon_line('original', ev.get('orig'), color))
    if ev.get('orig2'):
        lines.append(mon_line('original', ev['orig2'], color))
    return '\n'.join(lines)


ACTIONS = {
    'move': lambda name, target: name + (' on %s' % target if target else ''),
    'switch': lambda name, target: 'switch to %s' % name,
    'item': lambda name, target: 'use %s' % name + (' on %s' % target if target else ''),
}


def fmt_decision(ev, color):
    action, name, target = ev.get('action'), ev.get('name') or '?', ev.get('target')
    if action in ACTIONS:
        what = ACTIONS[action](name, target)
    else:
        what = ' '.join(str(x) for x in (action, ev.get('name')) if x is not None) or '?'
    lines = ['  %s  %s -> %s' % (side_tag(ev.get('side'), color), ev.get('pokemon', '?'), what)]
    if ev.get('options'):
        lines.append(INDENT + 'options: ' + weighed(ev['options']))
    if isinstance(ev.get('foe'), dict):      # the advanced AI's foe model: its strength, and the switch-in it expects
        foe = ev['foe']
        lines.append(INDENT + 'foe model s=%.2f' % (foe.get('strong', 0) / 1000) + (
            ', expects switch to %s (w %.2f)' % (foe.get('switch', '?'), foe['w'] / 1000) if foe.get('w') else ''))
    if ev.get('why'):
        lines.append(INDENT + 'picked by: ' + ev['why'] + ' (not the top value)')
    if ev.get('fallback'):
        lines.append(INDENT + "fallback %s: the original AI's code decided" % ev['fallback'])
    if ev.get('scores'):
        lines.append(INDENT + 'scores:  ' + weighed(ev['scores']))
    for target, rows in ev.get('target_scores') or []:      # the original AI's rows aimed at its other targets
        if rows:
            lines.append(INDENT + 'scores on %s:  ' % target + weighed(rows))
    return '\n'.join(lines)


def fmt_message(ev, color):
    """A battle message as the game printed it; an ability pop-up as '[ability] Pokémon: Ability'."""
    if ev.get('ability'):
        text = '[ability] %s%s' % ('%s: ' % ev['pokemon'] if ev.get('pokemon') else '', ev['ability'])
    else:
        text = str(ev.get('text', ''))
    return paint(MESSAGE + text, '2', color)


def fmt_hit(ev, color):
    """The damage a move did, from the battle's damage command: neutral hits print no message of their own."""
    eff = {2: ', super effective', 3: ', not very effective'}.get(ev.get('eff'), '')
    hits = ', '.join('%s %s' % (t[0], t[1]) for t in ev.get('targets') or [])
    return paint(MESSAGE + '[hit] %s: %s%s' % (ev.get('move', '?'), hits, eff), '2', color)


def fmt_switch(ev, color):
    """A replacement after a faint; with 'options', the values ai_replace gave the candidates ('engine': the
    engine chooser's first, when ai_replace put another first)."""
    old, new = ev.get('from'), ev.get('to', '?')
    line = '  %s  %s' % (side_tag(ev.get('side'), color), '%s out, %s in' % (old, new) if old and old != '?' else '%s in' % new)
    if not ev.get('options'):
        return line
    return line + '\n' + INDENT + 'options: ' + weighed(ev['options']) + (
        " (the engine's pick: %s)" % ev['engine'] if ev.get('engine') else '')


def fmt_faint(ev, color):
    return '  %s  %s fainted' % (side_tag(ev.get('side'), color), ev.get('pokemon', '?'))


def fmt_end(ev, color):
    winner, left, turns, end = ev.get('winner'), ev.get('left') or {}, ev.get('turns'), ev.get('end')
    who = SIDE_NAMES.get(winner, str(winner).upper()) if winner else None
    plain = painted = '=== '
    plain += '%s wins' % who if who else 'No winner'
    painted += '%s wins' % paint(who, '1;' + SIDE_COLORS.get(winner, '0'), color) if who else 'No winner'
    tail = ''.join([' after %s turns' % turns if turns is not None else '',
                    ' (%s)' % end if end and end != 'normal' else ''])
    sides = [s for s in SIDE_NAMES if s in left] + [s for s in left if s not in SIDE_NAMES]
    if sides:
        tail += '; Pokémon left: ' + ', '.join('%s %s' % (SIDE_NAMES.get(s, s), left[s]) for s in sides)
    return rule(plain + tail, painted + tail, '=')


def fmt_other(ev):
    if not isinstance(ev, dict):
        return '  [event] %r' % (ev,)
    return '  [%s] %s' % (ev.get('kind', '?'), ', '.join('%s=%s' % (k, v) for k, v in ev.items() if k != 'kind'))


FORMATS = {'battle': fmt_battle, 'turn': fmt_turn, 'decision': fmt_decision, 'switch': fmt_switch,
           'faint': fmt_faint, 'end': fmt_end, 'message': fmt_message, 'hit': fmt_hit}
KNOWN_KEYS = {'battle': {'n', 'of', 'adv_team', 'orig_team', 'sizes'}, 'turn': {'turn', 'adv', 'orig', 'adv2', 'orig2', 'weather'},
              'message': {'text', 'ability', 'pokemon'}, 'hit': {'move', 'targets', 'eff'},
              'decision': {'side', 'pokemon', 'action', 'name', 'target', 'options', 'scores', 'target_scores', 'why', 'fallback', 'foe'},
              'switch': {'side', 'from', 'to', 'options', 'engine'}, 'faint': {'side', 'pokemon'}, 'end': {'winner', 'left', 'turns', 'end'}}


def format_event(event, color=None):
    """The terminal text of one live event (several lines for some kinds). color None: only when stdout is a
    terminal. Never raises: an unknown kind, or an event this cannot read, prints as '  [kind] key=value, ...'."""
    if color is None:
        color = stdout_color()
    try:
        kind = event.get('kind')
        text = FORMATS[kind](event, color)
        extra = ['%s=%s' % (k, v) for k, v in event.items() if k != 'kind' and k not in KNOWN_KEYS[kind]]
        if not extra:
            return text
        lines = text.split('\n')
        first = next(i for i, line in enumerate(lines) if line)     # keys this does not know go on the first line
        lines[first] += '  [%s]' % ', '.join(extra)
        return '\n'.join(lines)
    except Exception:       # the events come from another module, and a log line must never stop a battle
        return fmt_other(event)


# --- checks

SAMPLE = [
    {'kind': 'battle', 'n': 1, 'of': 2, 'adv_team': 'Leader Falkner', 'orig_team': 'Elite Four Karen'},
    {'kind': 'turn', 'turn': 1, 'adv': {'species': 'Garchomp', 'hp': 183, 'maxhp': 183},
     'orig': {'species': 'Starmie', 'hp': 160, 'maxhp': 160}},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Garchomp', 'action': 'move', 'name': 'Earthquake', 'target': 'Starmie',
     'options': [['Dragon Claw', 980], ['Earthquake', 1240], ['switch:Scizor', 650], ['Stone Edge', 870],
                 ['Swords Dance', 410.5], ['item:Full Restore', -20], ['switch:Lucario', 300]]},
    {'kind': 'decision', 'side': 'original', 'pokemon': 'Starmie', 'action': 'move', 'name': 'Surf', 'target': 'Garchomp',
     'scores': [['Surf', 120], ['Psychic', 100], ['Recover', 90], ['Thunderbolt', 100]],
     'target_scores': [['foe', [['Surf', 3], ['Psychic', -1]]], ['self', []]]},
    {'kind': 'turn', 'turn': 2, 'adv': {'species': 'Garchomp', 'hp': 120, 'maxhp': 183},
     'orig': {'species': 'Starmie', 'hp': 1, 'maxhp': 160}},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Garchomp', 'action': 'move', 'name': 'Swords Dance', 'target': None},
    {'kind': 'decision', 'side': 'original', 'pokemon': 'Starmie', 'action': 'move', 'name': 'Recover', 'target': None,
     'scores': []},
    {'kind': 'faint', 'side': 'original', 'pokemon': 'Starmie'},
    {'kind': 'switch', 'side': 'original', 'from': 'Starmie', 'to': 'Scizor'},
    {'kind': 'turn', 'turn': 3, 'adv': {'species': 'Garchomp', 'hp': 120, 'maxhp': 183},
     'orig': {'species': 'Scizor', 'hp': 0, 'maxhp': 150}},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Garchomp', 'action': 'switch', 'name': 'Infernape', 'target': None,
     'options': [['Earthquake', 400], ['switch:Infernape', 1500]]},
    {'kind': 'switch', 'side': 'advanced', 'from': 'Garchomp', 'to': 'Infernape'},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Infernape', 'action': 'item', 'name': 'Full Restore', 'target': None,
     'options': [['item:Full Restore', 900], ['Close Combat', 850]], 'debug': 0},
    {'kind': 'faint', 'side': 'original', 'pokemon': 'Scizor'},
    {'kind': 'end', 'winner': 'advanced', 'left': {'advanced': 2, 'original': 0}, 'turns': 23, 'end': 'normal'},
    {'kind': 'battle', 'n': 2, 'of': 2, 'adv_team': 'Elite Four Karen', 'orig_team': 'Leader Falkner'},
    {'kind': 'turn', 'turn': 1, 'adv': {'species': '?', 'hp': 0, 'maxhp': 0}, 'orig': {'species': 'Pidgeot', 'hp': 205, 'maxhp': 205}},
    {'kind': 'end', 'winner': None, 'left': {'original': 3, 'advanced': 3}, 'turns': 140, 'end': 'unfinished'},
    {'kind': 'summary', 'battles': 2, 'advanced': 1},
    {'kind': 'decision', 'side': 'advanced', 'options': 'not a list of pairs', 'pokemon': None},
    'not an event',
    {'kind': 'turn', 'turn': 5, 'weather': {'kind': 'rain', 'turns_left': 4},
     'adv': {'species': 'Garchomp', 'hp': 120, 'maxhp': 183, 'status': 'TOX', 'confused': True, 'stages': {'Atk': 2, 'Spe': -1}},
     'orig': {'species': 'Starmie', 'hp': 160, 'maxhp': 160, 'status': None, 'confused': False, 'stages': {}}},
    {'kind': 'message', 'text': '¡Ho-Oh esquivó el ataque!'},
    {'kind': 'message', 'ability': 'Sequía', 'pokemon': 'Ninetales'},
    {'kind': 'turn', 'turn': 6, 'weather': {'kind': 'sun', 'turns_left': None},
     'adv': {'species': 'Garchomp', 'hp': 120, 'maxhp': 183, 'status': 'PAR', 'stages': {}}, 'orig': {'species': 'Starmie', 'hp': 0, 'maxhp': 0}},
    {'kind': 'battle', 'n': 3, 'of': 3, 'adv_team': 'Leader Falkner', 'orig_team': 'Elite Four Karen',
     'sizes': {'advanced': 4, 'original': 6}},
    {'kind': 'end', 'winner': 'original', 'left': {'advanced': 0, 'original': 3}, 'turns': 31, 'end': 'normal'},
    {'kind': 'switch', 'side': 'original', 'from': 'Starmie', 'to': 'Scizor',
     'options': [['Lucario', 640], ['Scizor', 812], ['Gengar', -120]], 'engine': 'Lucario'},
    {'kind': 'decision', 'side': 'original', 'pokemon': 'Scizor', 'action': 'move', 'name': 'Struggle', 'target': 'Garchomp',
     'fallback': 6, 'scores': [['Struggle', 100]]},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Alakazam', 'action': 'move', 'name': 'Focus Blast', 'target': 'Tyranitar',
     'options': [['Focus Blast', 420], ['Psychic', 300]], 'foe': {'strong': 600, 'w': 350, 'switch': 'Umbreon'}},
    {'kind': 'decision', 'side': 'advanced', 'pokemon': 'Alakazam', 'action': 'move', 'name': 'Psychic', 'target': 'Machamp',
     'foe': {'strong': 250, 'w': 0}},
]
SELF_SAMPLE = [     # aivsai --self: the same events, the sides named by side
    {'kind': 'decision', 'side': 'original', 'pokemon': 'Starmie', 'action': 'move', 'name': 'Surf', 'target': 'Garchomp',
     'options': [['Surf', 300], ['Recover', 120]], 'why': 'surer KO'},
    {'kind': 'end', 'winner': 'advanced', 'left': {'advanced': 2, 'original': 0}, 'turns': 23, 'end': 'normal'},
]


def selftest():
    for ev in SAMPLE:
        print(format_event(ev))
    text = [format_event(ev, color=False) for ev in SAMPLE]
    lines = [t.split('\n') for t in text]
    assert lines[2] == ['  ADVANCED  Garchomp -> Earthquake on Starmie',
                        INDENT + 'options: Earthquake=1240, Dragon Claw=980, Stone Edge=870, switch:Scizor=650, '
                                 'Swords Dance=410.5 (+2 more)'], lines[2]
    assert lines[3][1:] == [INDENT + 'scores:  Surf=120, Psychic=100, Thunderbolt=100, Recover=90',
                            INDENT + 'scores on foe:  Surf=3, Psychic=-1'], lines[3]          # no line for no valid row
    assert lines[1][1] == '  ADVANCED  Garchomp     183/183 ' + '█' * 10, lines[1]
    assert lines[4][1:] == ['  ADVANCED  Garchomp     120/183 ' + '█' * 7 + '░' * 3,
                            '  ORIGINAL  Starmie        1/160 █' + '░' * 9], lines[4]
    assert lines[9][2].endswith('  0/150 ' + '░' * 10), lines[9]
    assert lines[5] == ['  ADVANCED  Garchomp -> Swords Dance'], lines[5]                  # no options
    assert lines[6] == ['  ORIGINAL  Starmie -> Recover'], lines[6]                         # empty scores
    assert text[8] == '  ORIGINAL  Starmie out, Scizor in', text[8]                         # replacement after a faint
    assert lines[10] == ['  ADVANCED  Garchomp -> switch to Infernape',
                         INDENT + 'options: switch:Infernape=1500, Earthquake=400'], lines[10]
    assert lines[12][0] == '  ADVANCED  Infernape -> use Full Restore  [debug=0]', lines[12]
    assert text[14] == '=== ADVANCED wins after 23 turns; Pokémon left: ADVANCED 2, ORIGINAL 0 ===', text[14]
    assert text[0].split('\n')[1] == '=== Battle 1 of 2 ' + '=' * (RULE - 18), text[0]
    assert text[16].split('\n')[1] == '  ADVANCED  ?              ?/?', text[16]
    assert text[17].startswith('=== No winner after 140 turns (unfinished); Pokémon left: ADVANCED 3, ORIGINAL 3 ='), text[17]
    assert text[18] == '  [summary] battles=2, advanced=1', text[18]
    assert text[19].startswith('  [decision] '), text[19]
    assert text[20] == "  [event] 'not an event'", text[20]
    colored = format_event(SAMPLE[2], color=True)
    assert '\033[36mADVANCED\033[0m' in colored and '\033[33m' in format_event(SAMPLE[3], color=True), colored
    assert lines[21] == ['--- Turn 5 (rain, 4 turns left) ' + '-' * (RULE - 32),
                         '  ADVANCED  Garchomp     120/183 ' + '█' * 7 + '░' * 3 + '  TOX confused Atk+2 Spe-1',
                         '  ORIGINAL  Starmie      160/160 ' + '█' * 10], lines[21]
    assert text[22] == '  >> ¡Ho-Oh esquivó el ataque!', text[22]
    assert text[23] == '  >> [ability] Ninetales: Sequía', text[23]
    assert lines[24][0].startswith('--- Turn 6 (sun) -') and lines[24][1].endswith('  PAR'), lines[24]
    assert lines[24][2] == '  ORIGINAL  Starmie        ?/?', lines[24]
    assert format_event(SAMPLE[22], color=True) == '\033[2m  >> ¡Ho-Oh esquivó el ataque!\033[0m'
    assert lines[25][2:] == ['  ADVANCED  Leader Falkner (trainer side, 4 Pokémon)',
                             '  ORIGINAL  Elite Four Karen (player side, 6 Pokémon)'], lines[25]
    assert lines[0][2] == '  ADVANCED  Leader Falkner (trainer side)', lines[0]                # no sizes: as before
    assert text[26] == '=== ORIGINAL wins after 31 turns; Pokémon left: ADVANCED 0, ORIGINAL 3 ===', text[26]
    assert lines[27] == ['  ORIGINAL  Starmie out, Scizor in',
                         INDENT + "options: Scizor=812, Lucario=640, Gengar=-120 (the engine's pick: Lucario)"], lines[27]
    assert lines[28] == ['  ORIGINAL  Scizor -> Struggle on Garchomp', INDENT + "fallback 6: the original AI's code decided",
                         INDENT + 'scores:  Struggle=100'], lines[28]
    assert lines[29] == ['  ADVANCED  Alakazam -> Focus Blast on Tyranitar', INDENT + 'options: Focus Blast=420, Psychic=300',
                         INDENT + 'foe model s=0.60, expects switch to Umbreon (w 0.35)'], lines[29]
    assert lines[30] == ['  ADVANCED  Alakazam -> Psychic on Machamp', INDENT + 'foe model s=0.25'], lines[30]   # no switch case
    assert not any('\033' in t for t in text)
    use_side_names(True)
    try:
        self_text = [format_event(ev, color=False) for ev in SELF_SAMPLE]
    finally:
        use_side_names(False)
    assert self_text[0].split('\n') == ['  PLAYER    Starmie -> Surf on Garchomp', INDENT + 'options: Surf=300, Recover=120',
                                        INDENT + 'picked by: surer KO (not the top value)'], self_text[0]
    assert self_text[1].startswith('=== TRAINER wins after 23 turns; Pokémon left: TRAINER 2, PLAYER 0 ==='), self_text[1]
    assert format_event(SELF_SAMPLE[1], color=False).startswith('=== ADVANCED wins')        # names back by AI
    print('\nselftest: %d events formatted, all checks passed' % (len(SAMPLE) + len(SELF_SAMPLE)))


def window_test(rom, speed, frames, scale):
    from desmume.controls import Keys, keymask

    from emu import Runner
    r = Runner(rom, os.path.join(tbpaths.RUNS, 'aivsai_live'))
    view = LiveView(r.emu, speed, scale)
    print('window: %s; speed %g (%s)' % ('%dx' % view.scale if view.scale else "DeSmuME's own",
                                       speed, 'no limit' if speed <= 0 else '%.1f frames per second' % (DS_FPS * speed)), flush=True)
    key_a, half, held = keymask(Keys.KEY_A), frames // 2, None
    emulating, shown, t0 = 0.0, 0, None
    try:
        for i in range(frames):
            if i == half:
                r.emu.input.keypad_add_key(key_a)       # as Runner.hold does
            t = time.perf_counter()
            r.step(1)
            emulating += time.perf_counter() - t
            view.frame()
            if i == half:
                held = bool(r.emu.input.keypad_get() & key_a)
                r.emu.input.keypad_rm_key(key_a)
            if view.closed():
                print('window closed at frame %d' % (i + 1))
                break
            shown = i + 1
            t0 = t0 or time.perf_counter()
            t1 = time.perf_counter()
    except KeyboardInterrupt:
        print('stopped (Ctrl+C)')
    finally:
        view.close()
    if shown > 1:
        print('%d frames in %.2f s: %.1f frames per second' % (shown, t1 - t0, (shown - 1) / (t1 - t0)))
        budget = ' (a frame lasts %.1f ms at this speed)' % (1000 / (DS_FPS * speed)) if speed > 0 else ''
        print('emulation %.1f ms per frame%s' % (1000 * emulating / shown, budget))
    if held is not None:
        print("a key the runner holds survives frame(): %s" % ('yes' if held else 'NO'))
    r.step(60)
    print('the emulator ran 60 more frames after the window closed (frame %d)' % r.frames)
    return 0 if held is not False else 1


def main():
    ap = argparse.ArgumentParser(description='Live mode of the AI-vs-AI bench: the window and the terminal log.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest', action='store_true', help='print a synthetic battle and check the lines (no window)')
    g.add_argument('--window-test', metavar='ROM', help='open the window on ROM, run --frames frames, print the frame rate')
    ap.add_argument('--speed', type=float, default=1.0, help='times the DS frame rate (0 = no limit)')
    ap.add_argument('--frames', type=int, default=600)
    ap.add_argument('--scale', type=int, help='window scale (default: 2 when the screen has room, else 1)')
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    return window_test(a.window_test, a.speed, a.frames, a.scale)


if __name__ == '__main__':
    sys.exit(main())
