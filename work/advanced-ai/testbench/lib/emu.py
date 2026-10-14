"""Headless DeSmuME runner: the emulator every test bench tool drives.

  .venv/bin/python work/advanced-ai/testbench/lib/emu.py ROM SCRIPT [--state IN.dst] [--save-state OUT.dst] [--shots DIR]

Ported from the Spanish workspace's tools/emu.py (dc8577c). Changes:
- no speed toggle: the ROM is never changed; walking uses FPT frames per tile (8, the Spanish 'fast' value, which the
  Spanish tool used for its rc44 test saves and for the hack's own main loop), set per Runner or by ADVAI_FPT;
- no melonDS backend (the Spanish ES_EMU=melon): every tier runs on DeSmuME, which has execution hooks;
- battery saves: DeSmuME reads them from $XDG_CONFIG_HOME/desmume/<ROM file name>.dsv; this module points
  XDG_CONFIG_HOME at the test bench's own folder (RUNS/xdg, or ADVAI_XDG) before DeSmuME starts, so no run reads or
  writes ~/.config/desmume, and DSV_DIR is that folder;
- Runner.set_flag and set_ai_setting write script flags into the save in RAM (the AI settings 0x2C2/0x2C3), as the
  Spanish tools/impactcheck.py set_flag does;
- the emulator pool is lib/emupool.py (shared with our harness).

SCRIPT is a text file (or '-' for stdin) with one command per line:
  wait N                 run N frames with no input
  press KEY [N]          hold KEY (A B X Y L R START SELECT UP DOWN LEFT RIGHT) for 6 frames,
                         then release for 12; repeated N times
  hold KEY FRAMES        hold KEY for FRAMES frames, then release
  touch X Y [FRAMES]     touch the lower screen at (X, Y) for FRAMES (default 6) frames
  walk DIR [N]           walk N tiles (default 1), one tile per hold; timing follows the game's speed
  face DIR               tap DIR to turn toward an NPC or object in the way
  goto X Y               walk until the player stands on tile (X, Y) (up/down first, then sideways)
  until STATE [KEY] [N]  press KEY (default A, 'none' to wait) every 60 frames until the screen shows STATE
                         (yesno, party, field, fight_menu, dexpage); dialogue lengths differ between languages
  shot NAME              save a screenshot (both screens) as DIR/NAME.png
  savestate PATH         save a savestate now
  mark NAME              with --heap: print the low-water marks since the last mark, then reset them
Lines starting with # are comments.

The main loop is watched too: FREEZE is printed (and traced) when it has not run for 30 seconds.
The emulator's real-time clock is the emulated one (Runner.pin_clock), so the same inputs replay the same run, and
every Runner first takes a slot of the machine-wide emulator pool (tools/emupool.py).
Every heap allocation is watched (addresses are for this ROM's ARM9): a NULL result is
printed as it happens, as is every failed game assertion (such as a string that did not fit
its buffer), and --heap prints each heap's size and its smallest largest-free-block
seen at any allocation, i.e. how close each app came to running out. --heap also logs every
heap creation with the parent heap's largest free block at that moment.
"""
import argparse
import ctypes
import datetime
import json
import logging
import os
import sys
import time

import tbpaths

# battery saves: DeSmuME (GLib) reads XDG_CONFIG_HOME once, when the first emulator starts, so it is set before that
XDG = os.environ['XDG_CONFIG_HOME'] = os.environ.get('ADVAI_XDG') or os.path.join(tbpaths.RUNS, 'xdg')
DSV_DIR = os.path.join(XDG, 'desmume')
os.makedirs(DSV_DIR, exist_ok=True)
logging.disable(logging.ERROR)
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')    # no audio device: macOS's coreaudiod took ~2 cores serving muted emulators
from desmume.controls import Keys, keymask  # noqa: E402
from desmume.emulator import DeSmuME  # noqa: E402

logging.disable(logging.NOTSET)
import emupool  # noqa: E402
from text import codes_to_text  # noqa: E402

KEYS = {k[4:]: getattr(Keys, k) for k in dir(Keys) if k.startswith('KEY_')}
HEAP_INFO = 0x021D050C     # sHeapInfo: handles*, ..., counts* (+0xC), heapIdxs* (+0x10), numHeaps (+0x14)
ALLOC_RESULT = 0x0201B284  # in AllocFromHeapInternal, after NNS_FndAllocFromExpHeapEx: r4 = block, r6 = heap id
CREATE_HEAP = 0x0201B148   # CreateHeapInternal(parent, child, size, align), behind CreateHeap/CreateHeapAtEnd
ASSERT_FAIL = 0x02025B2C   # GF_AssertFail: e.g. a message too long for its String buffer is not copied
SOUND_START = 0x02006B64   # every sequence/SE start passes here; the sequence number is at [sp]
BATTLE_CMD = 0x0220467E    # battle client dispatcher (overlay 14), once per server command: id at r4+0x2C
BATTLE_CMD_READ = (0x02204668, bytes.fromhex('20f036fb'))   # its "bl ReadCommand": overlay 14 is loaded
NARC_PATH = 0x02007838     # NARC id -> path, called whenever a NARC is opened or read
NARC_TABLE_LIT = 0x02007888  # literal holding the NARC path table
MAIN_LOOP = {b'IPKJ': 0x02000D90, b'IPKE': 0x02000E28}   # an instruction the main loop runs once per game frame (Origin builds / vanilla US)
FREEZE_FRAMES = 1800        # no main-loop pass for 30 s = frozen (a full save blocks it for ~18 s)
PLAYER_POS = 0x021D9776     # player's tile x (u16), tile y at +8, while in the field (same in the Chinese ROM)
# screen states for `until` (pixels on the 256x384 screenshot, RGB): same in the Chinese ROM
STATES = {
    'yesno': [((40, 264), (208, 208, 208)), ((128, 222), (8, 176, 112))],   # Yes/No buttons on the green backdrop
    'party': [((228, 368), (16, 88, 208))],                         # party list (EXIT button)
    'field': [((4, 196), (72, 72, 72)), ((164, 196), (72, 72, 72)), ((20, 192), (24, 128, 64))],  # field touch menu
    'fight_menu': [((60, 252), (232, 56, 56)), ((128, 262), (232, 56, 56))],   # battle FIGHT button
    'dexpage': [((16, 0), (248, 184, 56)), ((2, 0), (200, 136, 32))],          # Pokédex registration page banner
    'mainmenu': [((4, 250), (96, 96, 248)), ((4, 370), (96, 96, 248)), ((128, 96), (0, 0, 0))],   # main menu backdrop, top screen off
}
MSGDATA_NEW = 0x0200BA98    # MsgData_New(type, narc id, file id, heap): every message bank opened
GLYPH_COPY = 0x0201E2FC     # CopyGlyphToWindow(window, glyph, width, height, x, y, row-doubling mask): every glyph drawn
ADD_PRINTER = 0x020208D4    # AddTextPrinter(template, ...): template+0 the String, +4 the window it prints into
MSG_TABLE_SET = 0x0200BABC  # in MsgData_New after the whole bank is loaded: r0 = table, r6 = narc id, r7 = bank
MSG_NARC_SET = 0x0200BAD4   # in MsgData_New after the archive is opened: r0 = NARC handle, r6 = narc id
# every message read, by where its bank and index are: (table, index, ...) for a loaded bank,
# (NARC handle, bank, index, ...) for an open archive, (narc id, bank, index, ...)
MSG_READS = {0x0200B5C0: 'table', 0x0200B700: 'table', 0x0200B7B0: 'table',
             0x0200B89C: 'handle', 0x0200B998: 'handle', 0x0200B644: 'id'}
COPY_CODES = 0x02026EB8     # CopyU16ArrayToStringN(dest, codes, n): asserts and copies nothing if n > dest's size
COPY_FROM_READ = {0x0200B78C, 0x0200B940}   # its return addresses in the reads into an existing String (the
                                            # reads that make a new String size it to the message: 0x0200B846, 0x0200BA4A)
EXPAND = 0x0200C738         # StringExpandPlaceholders(format, dest, src): variables filled in, into a fixed dest
# The real-time clock. DeSmuME's RTC reads the host clock, unless a movie is active: then it is the movie's rtcStart
# plus the emulated time (currFrameCounter frames, in whole seconds). movieMode 3 (a finished movie) turns that on and
# changes nothing else: input, touch and savestate loads go as with no movie, only a savestate written in it would
# carry a movie chunk, so saves switch it off for the call. Runner pins the clock at boot and after every state load.
CLOCK = datetime.datetime(2026, 1, 1, 12, 0, 0)     # the clock at boot: noon, the field in daylight
MOVIE_FINISHED, RTC_START = 3, 0xC0                 # libdesmume 0.9.12: MOVIEMODE_FINISHED; MovieData.rtcStart (DateTime)
SAVE_HOLDER = 0x021106A8   # Origin builds: +0x20 the save (GetSaveData), made before the main loop starts
FPT = int(os.environ.get('ADVAI_FPT') or 8)     # frames per tile when walking: 8 at 60 fps, 16 at 30 fps
# ADVAI_TRACE_SAMPLES=1 adds samples to a --trace: 'lcg' (the field LCG word every 8th main-loop pass), 'spawns' (the map
# Pokemon records when they change, without their map object pointer), 'mon' (every personality CreateBoxMon picks, with
# species and level) and 'brng' (the battle RNG word at each selection phase)
SAMPLES = os.environ.get('ADVAI_TRACE_SAMPLES') == '1'
FIELD_LCG = 0x021D0530
SPAWNS, SPAWN_COUNT, SPAWN_SIZE = 0x021CFF68, 6, 0x14
PID_PICKED = 0x0206D182     # in CreateBoxMon, after the personality is picked: pid [sp+0x3C], species [sp+0x2C], level [sp+0x30]
AFTER_AI_LOAD = 0x02223D14  # overlay 14: the server loaded the AI slot (a selection phase); battle RNG [[0x02255BAC]+0x24C]
RTC_WORK = 0x021CFE8C   # Origin builds: the game's copy of the RTC (GF_RTC), refreshed every 11 frames; date at +0x10
                        # (year 0-99, month, day, weekday), time at +0x20 (hour, minute, second), all u32
FLAG_AI, FLAG_AI_IMPORTANT = 0x2C2, 0x2C3          # the AI setting (docs/build-contract.md "Settings")
AI_SETTINGS = {'off': (0, 0), 'all': (1, 0), 'important': (1, 1)}    # (0x2C2, 0x2C3)


def ticks(when):
    """A DeSmuME DateTime: 100 ns units since 0001-01-01."""
    return int((when - datetime.datetime(1, 1, 1)).total_seconds()) * 10 ** 7


class Runner:
    def __init__(self, rom, shots, heap_marks=False, trace=None, fpt=None):
        emupool.acquire()
        self.emu = DeSmuME()
        # DeSmuME's dummy sound core: the sound hardware is still emulated (the game reads it), the output is not mixed
        self.emu.lib['_Z19SPU_ChangeSoundCoreii'](0, 0)
        self.emu.open(rom)
        self.pin_clock(CLOCK)
        states, save_file, load_file = self.emu.savestate, self.emu.savestate.save_file, self.emu.savestate.load_file

        def save_state(path):
            mode = ctypes.c_int.in_dll(self.emu.lib, 'movieMode')
            pinned, mode.value = mode.value, 0
            try:
                save_file(path)
            finally:
                mode.value = pinned

        def load_state(path):
            load_file(path)
            self.pin_clock(self.game_clock() or CLOCK)
        states.save_file, states.load_file = save_state, load_state
        self.shots = shots
        self.frames = 0
        self.heap_min = {}
        self.heap_marks = heap_marks  # walking the free list on every allocation is slow
        self.emu.memory.register_exec(ALLOC_RESULT, self._alloc)
        self.emu.memory.register_exec(ASSERT_FAIL, self._assert)
        with open(rom, 'rb') as f:
            data = bytearray(f.read())
        self.emu.memory.register_exec(MAIN_LOOP.get(bytes(data[0xC:0x10]), MAIN_LOOP[b'IPKJ']), self._beat)
        self.origin = bytes(data[0xC:0x10]) == b'IPKJ'      # an Origin build (Chinese, English or Spanish)
        self.printing, self.outside = {}, 0   # window -> text last printed into it
        self.last_text, self.recent_texts = None, []
        self.skip_render = False
        self.emu.memory.register_exec(GLYPH_COPY, self._glyph)
        self.emu.memory.register_exec(ADD_PRINTER, self._printer)
        self.fpt = fpt or FPT                                     # frames per tile when walking (60 or 30 fps)
        self.last_beat, self.frozen = 0, False
        self.trace = open(trace, 'w') if trace else None
        if self.trace:
            self.emu.memory.register_exec(SOUND_START, self._sound)
            self.emu.memory.register_exec(BATTLE_CMD, self._battle_cmd)
            self.emu.memory.register_exec(NARC_PATH, self._narc)
            self.emu.memory.register_exec(MSGDATA_NEW, self._msg)
            self.msg_src, self.msg_read = {}, set()     # table/NARC handle -> (narc id, bank); reads logged
            self.emu.memory.register_exec(MSG_TABLE_SET, self._msg_src)
            self.emu.memory.register_exec(MSG_NARC_SET, self._msg_src)
            for address in MSG_READS:
                self.emu.memory.register_exec(address, self._msg_read)
            self.last_read, self.buffers = None, set()
            self.emu.memory.register_exec(COPY_CODES, self._copy)
            self.emu.memory.register_exec(EXPAND, self._expand)
        if heap_marks:
            self.emu.memory.register_exec(CREATE_HEAP, self._create)
        self.beats, self.spawns = 0, None
        if self.trace and SAMPLES:
            self.emu.memory.register_exec(PID_PICKED, self._pid)
            self.emu.memory.register_exec(AFTER_AI_LOAD, self._brng)
        os.makedirs(shots, exist_ok=True)

    def pin_clock(self, when):
        """The RTC from now on: `when`, then the emulated time since this call."""
        lib = self.emu.lib
        data = ctypes.addressof(ctypes.c_char.in_dll(lib, 'currMovieData'))
        ctypes.c_int64.from_address(data + RTC_START).value = ticks(when)
        ctypes.c_int.in_dll(lib, 'currFrameCounter').value = 0
        ctypes.c_int.in_dll(lib, 'movieMode').value = MOVIE_FINISHED
        now = lib['_Z10rtcGetTimev']
        now.restype = ctypes.c_int64
        if now() != ticks(when):
            raise RuntimeError('the RTC did not take the pinned time: this libdesmume lays out its movie data differently')

    def _flag_byte(self, flag):
        """The address of a script flag's byte in the save in RAM, or None before the save exists."""
        m = self.emu.memory.unsigned
        save = m.read_long(SAVE_HOLDER + 0x20)
        if not 0x02000000 <= save < 0x02400000:
            return None
        vars_flags = save + 0x10 + m.read_long(save + 0x2E01C + 4 * 16)     # SaveArray_Get(save, 4)
        return vars_flags + 0x2E0 + (flag >> 3)

    def flag(self, flag):
        """A script flag of the save in RAM (0 before the save exists), read as CheckFlag reads it."""
        at = self._flag_byte(flag)
        return 0 if at is None else self.emu.memory.unsigned.read_byte(at) >> (flag & 7) & 1

    def set_flag(self, flag, on=True):
        """Set or clear a script flag of the save in RAM, as SetFlag/ClearFlag do. False before the save exists."""
        at = self._flag_byte(flag)
        if at is None:
            return False
        v = self.emu.memory.unsigned.read_byte(at)
        self.emu.memory.write_byte(at, v | 1 << (flag & 7) if on else v & ~(1 << (flag & 7)) & 0xFF)
        return True

    def game_clock(self):
        """The date and time an Origin build last read from the RTC (a savestate keeps it), or None."""
        if not self.origin:
            return None
        m = self.emu.memory.unsigned
        (y, mo, d), (h, mi, s) = [[m.read_long(RTC_WORK + at + 4 * k) for k in range(3)] for at in (0x10, 0x20)]
        try:
            return datetime.datetime(2000 + y, mo, d, h, mi, s)
        except ValueError:
            return None

    def heap(self, hid):
        """(size, largest free block) of heap `hid`, or None if it does not exist."""
        m = self.emu.memory.unsigned
        if hid >= m.read_short(HEAP_INFO + 0x14):
            return None
        idx = m.read_byte(m.read_long(HEAP_INFO + 0x10) + hid)
        h = m.read_long(m.read_long(HEAP_INFO) + 4 * idx)
        if not h:
            return None
        largest, blk, n = 0, m.read_long(h + 0x24), 0  # NNS expanded heap free list
        while blk and n < 4096:
            largest = max(largest, m.read_long(blk + 4))
            blk, n = m.read_long(blk + 12), n + 1
        return m.read_long(h + 0x1C) - m.read_long(h + 0x18), largest

    def _alloc(self, address, size):
        r = self.emu.memory.register_arm9
        hid = r.r6 & 0xFF
        if r.r4 == 0:
            print('NULL allocation from heap %d at frame %d' % (hid, self.frames))
            self.event(ev='null', heap=hid)
        if not self.heap_marks:
            return
        info = self.heap(hid)
        if info and (hid not in self.heap_min or info[1] < self.heap_min[hid][1]):
            self.heap_min[hid] = info

    def event(self, **ev):
        if self.trace:
            ev['f'] = self.frames
            self.trace.write(json.dumps(ev) + '\n')

    def _sound(self, address, size):
        m, r = self.emu.memory.unsigned, self.emu.memory.register_arm9
        self.event(ev='sound', seq=m.read_short(r.sp))

    def _battle_cmd(self, address, size):
        """A battle client command starts ('battle_cmd', with its first three arguments): difftest lets the
        commands that play the sounds the build adds (tools/asm/battlesound.s, battlefix.s) account for them."""
        m = self.emu.memory.unsigned
        at, code = BATTLE_CMD_READ
        if bytes(m.read_byte(at + k) for k in range(4)) == code:
            client = self.emu.memory.register_arm9.r4
            self.event(ev='battle_cmd', cmd=m.read_long(client + 0x2C),
                       args=[m.read_long(client + 0x38 + 4 * k) for k in range(3)])

    def _narc(self, address, size):
        m, r = self.emu.memory.unsigned, self.emu.memory.register_arm9
        path = '?'
        table = m.read_long(NARC_TABLE_LIT)
        if 0x2000000 <= table < 0x2400000:
            p = m.read_long(table + 4 * r.r0)
            if 0x2000000 <= p < 0x2400000:
                chars = []
                while len(chars) < 64 and m.read_byte(p + len(chars)):
                    chars.append(m.read_byte(p + len(chars)))
                path = bytes(chars).decode('latin1')
        self.event(ev='narc', path=path)

    def _msg(self, address, size):
        r = self.emu.memory.register_arm9
        self.event(ev='msg', narc=r.r1, bank=r.r2)

    def _msg_src(self, address, size):
        r = self.emu.memory.register_arm9
        self.msg_src[r.r0] = (r.r6, r.r7) if address == MSG_TABLE_SET else (r.r6, None)

    def _msg_read(self, address, size):
        """Log the first read of each message ('read' event: narc id, bank, index) for tools/textcensus.py."""
        r = self.emu.memory.register_arm9
        how = MSG_READS[address]
        if how == 'table':
            narc, bank = self.msg_src.get(r.r0, (None, None))
            index = r.r1
        elif how == 'handle':
            narc, bank, index = self.msg_src.get(r.r0, (None,))[0], r.r1, r.r2
        else:
            narc, bank, index = r.r0, r.r1, r.r2
        key = (narc, bank, index & 0xFFFF)
        self.last_read = key if bank is not None else None
        if bank is not None and key not in self.msg_read:
            self.msg_read.add(key)
            self.event(ev='read', narc=narc, bank=bank, index=index & 0xFFFF)

    def _string_text(self, string):
        m = self.emu.memory.unsigned
        n = min(m.read_short(string + 2), 600)
        try:
            return codes_to_text([m.read_short(string + 8 + 2 * k) for k in range(n)])
        except Exception:
            return None

    def _copy(self, address, size):
        """A message read into an existing String: log its bank and the String's size once ('into')."""
        r, m = self.emu.memory.register_arm9, self.emu.memory.unsigned
        if r.lr - 1 not in COPY_FROM_READ or self.last_read is None:
            return
        key = ('into',) + self.last_read + (m.read_short(r.r0),)
        if key not in self.buffers:
            self.buffers.add(key)
            self.event(ev='into', narc=key[1], bank=key[2], index=key[3], max=key[4])

    def _expand(self, address, size):
        """Variables expanded into a fixed String: log its size and the message as read ('expand')."""
        r, m = self.emu.memory.register_arm9, self.emu.memory.unsigned
        text = self._string_text(r.r2)
        key = ('expand', m.read_short(r.r1), text)
        if text is not None and key not in self.buffers:
            self.buffers.add(key)
            self.event(ev='expand', max=key[1], text=text[:600])

    def _printer(self, address, size):
        """AddTextPrinter: remember the text printed into each window; with --trace, log a 'print' event
        (window size, start x/y, font, text) for tools/textcensus.py."""
        m = self.emu.memory.unsigned
        template = self.emu.memory.register_arm9.r0
        string, window = m.read_long(template), m.read_long(template + 4)
        codes = []
        if 0x02000000 <= string < 0x02400000:
            n = min(m.read_short(string + 2), 400)     # String: u16 max, u16 length, u32 magic, codes
            codes = [m.read_short(string + 8 + 2 * k) for k in range(n)]
        try:
            text = codes_to_text([c for c in codes if c != 0xFFFF])
        except Exception:
            text = ' '.join('%04X' % c for c in codes[:40])
        self.printing[window] = text
        self.last_text = text
        self.recent_texts = (self.recent_texts + [text])[-8:]
        if self.trace and 0x02000000 <= window < 0x02400000:
            self.event(ev='print', win=[m.read_byte(window + 7) * 8, m.read_byte(window + 8) * 8],
                       at=[m.read_byte(template + 0xA), m.read_byte(template + 0xB)], font=m.read_byte(template + 9),
                       text=text[:300])

    def _glyph(self, address, size):
        """Text drawing guard. The glyph copy writes every non-zero pixel of the glyph's first 8 or 16 rows
        and columns from (x, y), each source row twice when its bit is set in the row-doubling mask
        ({SIZE 200} passes 0xFFFC), and it clips only the block size to the window, not the rows the
        doubling adds. A byte written past the pixel buffer's heap allocation corrupts memory (the 547:7
        freeze): an 'outside' failure. Pixels past the window's declared size but inside the allocation
        are only drawn where they should not be: a 'clipped' note."""
        m, r = self.emu.memory.unsigned, self.emu.memory.register_arm9
        win = r.r0
        wt, ht = m.read_byte(win + 7), m.read_byte(win + 8)
        if not wt or not ht:
            return
        winw, winh = wt * 8, ht * 8
        buf = m.read_long(win + 0xC)
        bpp8 = m.read_short(win + 0xA) >> 15
        tile, row = (64, 8) if bpp8 else (32, 4)
        # heap block: NNS head ('UD', attribute, size) then the game's 16-byte header, then the buffer
        alloc = m.read_long(buf - 28) - 16 if m.read_short(buf - 32) == 0x5544 else wt * ht * tile
        srcw, srch = r.r2 & 0xFFFF, r.r3 & 0xFFFF
        x, y, mask = m.read_short(r.sp), m.read_short(r.sp + 4), m.read_short(r.sp + 8)
        if winh - y <= 0 or winw - x <= 0:
            return              # the copy returns without drawing (0x0201F46C)
        rows = 16 if min(srch, winh - y) > 8 else 8
        cols = 16 if min(srcw, winw - x) > 8 else 8
        glyph = b''.join(m.read_long(r.r1 + 4 * k).to_bytes(4, 'little') for k in range(32))
        right = bottom = last = -1
        for py in range(rows):
            ink = [px for px in range(cols)
                   if (lambda b: b >> 4 if px & 1 else b & 15)(glyph[((py >> 3) * 2 + (px >> 3)) * 32 + (py & 7) * 4 + ((px & 7) >> 1)])]
            if not ink:
                continue
            first = y + py + bin(mask & ((1 << py) - 1)).count('1')
            for oy in (first, first + 1) if mask >> py & 1 else (first,):
                ox = x + ink[-1]
                off = ((oy >> 3) * wt + (ox >> 3)) * tile + (oy & 7) * row + ((ox & 7) if bpp8 else (ox & 7) >> 1)
                right, bottom, last = max(right, ox), max(bottom, oy), max(last, off)
        if last < 0:
            return
        if last >= alloc:
            self.outside += 1
            print('OUTSIDE: glyph at (%d, %d) writes byte %d of a %d-byte buffer (%dx%d window) at frame %d: %r'
                  % (x, y, last, alloc, winw, winh, self.frames, self.printing.get(win, '?')[:70]))
            self.event(ev='outside', win=[winw, winh], at=[x, y], reach=[right, bottom], byte=last, alloc=alloc,
                       mask=mask, text=self.printing.get(win, '?')[:120])
        elif bottom >= winh or right >= winw:
            self.event(ev='clipped', win=[winw, winh], at=[x, y], reach=[right, bottom], mask=mask,
                       text=self.printing.get(win, '?')[:120])

    def _assert(self, address, size):
        lr = self.emu.memory.register_arm9.lr - 1
        print('ASSERT failed at frame %d, called from %08X' % (self.frames, lr))
        self.event(ev='assert', lr='%08X' % lr)

    def _create(self, address, size):
        r = self.emu.memory.register_arm9
        parent = self.heap(r.r0)
        print('frame %d: create heap %d (%d bytes) from heap %d, which has %s bytes in its largest free block'
              % (self.frames, r.r1, r.r2, r.r0, parent[1] if parent else '?'))
        self.event(ev='heap', heap=r.r1, size=r.r2, parent=r.r0, parent_free=parent[1] if parent else None)

    def print_heap(self, label):
        for hid, (size, low) in sorted(self.heap_min.items()):
            print('%s heap %2d: %7d bytes, smallest largest-free-block %d' % (label, hid, size, low))

    def step(self, n=1):
        for _ in range(n):
            if self.skip_render:        # no picture this frame (tools that never look at the screen run faster)
                self.emu.skip_next_frame()
            self.emu.cycle(with_joystick=False)
            self.frames += 1
            if not self.frozen and self.frames - self.last_beat > FREEZE_FRAMES:
                self.frozen = True
                print('FREEZE: no main-loop pass since frame %d (now %d)' % (self.last_beat, self.frames))
                self.event(ev='freeze', since=self.last_beat)

    def _pid(self, address, size):
        m, sp = self.emu.memory.unsigned, self.emu.memory.register_arm9.sp
        self.event(ev='mon', pid='%08X' % m.read_long(sp + 0x3C), species=m.read_long(sp + 0x2C) & 0xFFFF,
                   level=m.read_long(sp + 0x30) & 0xFF)

    def _brng(self, address, size):
        m = self.emu.memory.unsigned
        at, code = BATTLE_CMD_READ
        if bytes(m.read_byte(at + k) for k in range(4)) == code:
            self.event(ev='brng', v='%08X' % m.read_long(m.read_long(0x02255BAC) + 0x24C))

    def _samples(self):
        m = self.emu.memory.unsigned
        self.event(ev='lcg', v='%08X' % m.read_long(FIELD_LCG))
        recs = [bytes(m.read_byte(SPAWNS + SPAWN_SIZE * i + k) for k in range(0x10)).hex() for i in range(SPAWN_COUNT)]
        if recs != self.spawns:
            self.spawns = recs
            self.event(ev='spawns', recs=recs)

    def _beat(self, address, size):
        self.last_beat = self.frames
        self.beats += 1
        if self.trace and SAMPLES and self.beats % 8 == 0:
            self._samples()
        if self.frozen:
            self.frozen = False
            print('main loop resumed at frame %d' % self.frames)
            self.event(ev='resume')

    def hold(self, key, frames, release=12):
        self.emu.input.keypad_add_key(keymask(KEYS[key]))
        self.step(frames)
        self.emu.input.keypad_rm_key(keymask(KEYS[key]))
        self.step(release)

    def seen(self, checks):
        im = self.emu.screenshot().convert('RGB')
        return all(all(abs(a - b) <= 12 for a, b in zip(im.getpixel(p), c)) for p, c in checks)

    def until(self, state, key='A', limit=3000, every=60):
        start = self.frames
        while self.frames - start < limit:
            for _ in range(every // 4):
                self.step(4)
                if self.seen(STATES[state]):
                    return
            if key != 'none':
                self.hold(key.upper(), 6, release=0)
        print('until %s: not reached in %d frames' % (state, limit))
        self.event(ev='until_fail', state=state)

    def player_pos(self):
        m = self.emu.memory.unsigned
        return m.read_short(PLAYER_POS), m.read_short(PLAYER_POS + 8)

    def goto(self, tx, ty, tries=40):
        for _ in range(tries):
            x, y = self.player_pos()
            if (x, y) == (tx, ty):
                return
            if y == 0xFFFF:                    # between maps (door transition)
                self.step(30)
                continue
            key = ('DOWN' if ty > y else 'UP') if y != ty else ('RIGHT' if tx > x else 'LEFT')
            self.hold(key, self.fpt, release=40)
        print('goto %d %d: stuck at %s' % (tx, ty, self.player_pos()))
        self.event(ev='goto_fail', target=[tx, ty], at=list(self.player_pos()))

    def touch(self, x, y, frames=6):
        self.emu.input.touch_set_pos(x, y)
        self.step(frames)
        self.emu.input.touch_release()
        self.step(12)

    def shot(self, name):
        path = os.path.join(self.shots, name + '.png')
        self.emu.screenshot().save(path)
        return path

    def run(self, lines):
        for raw in lines:
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            op, *args = line.split()
            if op == 'wait':
                self.step(int(args[0]))
            elif op == 'press':
                for _ in range(int(args[1]) if len(args) > 1 else 1):
                    self.hold(args[0].upper(), 6)
            elif op == 'hold':
                self.hold(args[0].upper(), int(args[1]))
            elif op == 'walk':                 # walk DIR N: N tiles, one at a time (frames scale with the ROM's speed)
                for _ in range(int(args[1]) if len(args) > 1 else 1):
                    self.hold(args[0].upper(), self.fpt, release=40)
            elif op == 'until':                # until STATE [KEY] [LIMIT]: press KEY (A; 'none' = just wait) until STATE
                self.until(args[0], args[1] if len(args) > 1 else 'A', int(args[2]) if len(args) > 2 else 3000)
            elif op == 'goto':                 # goto X Y: walk (up/down first, then sideways) until on tile (X, Y)
                self.goto(int(args[0]), int(args[1]))
            elif op == 'face':                 # face DIR: turn toward something that blocks the way
                self.hold(args[0].upper(), self.fpt // 4, release=20)
            elif op == 'touch':
                self.touch(int(args[0]), int(args[1]), int(args[2]) if len(args) > 2 else 6)
            elif op == 'shot':
                print('shot', self.shot(args[0]))
            elif op == 'savestate':
                self.emu.savestate.save_file(args[0])
            elif op == 'mark':
                self.print_heap(args[0])
                for hid, (size, low) in sorted(self.heap_min.items()):
                    self.event(ev='heapmin', heap=hid, size=size, low=low)
                self.event(ev='mark', label=args[0])
                self.heap_min = {}
            else:
                raise ValueError('unknown command: ' + line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('script')
    ap.add_argument('--state')
    ap.add_argument('--save-state')
    ap.add_argument('--shots', default='shots')
    ap.add_argument('--heap', action='store_true', help='print per-heap low-water marks')
    ap.add_argument('--trace', help='write sound starts, NARC loads, asserts, NULL allocations and heap events as JSON lines (compare runs with difftest.py)')
    ap.add_argument('--ai', choices=sorted(AI_SETTINGS), help='after --state: set the AI setting flags in RAM')
    a = ap.parse_args()
    r = Runner(a.rom, a.shots, a.heap, a.trace)
    if a.state:
        r.emu.savestate.load_file(a.state)
    if a.ai and not set_ai_setting(r, a.ai):
        sys.exit('--ai: no save in RAM yet (give a --state from the field)')
    lines = sys.stdin.read().splitlines() if a.script == '-' else open(a.script).read().splitlines()
    t = time.time()
    r.run(lines)
    if a.save_state:
        r.emu.savestate.save_file(a.save_state)
    print('%d frames in %.1fs' % (r.frames, time.time() - t))
    if a.heap:
        r.print_heap('end')


def set_ai_setting(r, setting):
    """The advanced AI's setting in the save in RAM: 'off' (0x2C2 clear), 'all' (0x2C2 set, 0x2C3 clear) or 'important'
    (both set). Call it after every state load: a state load restores the save in RAM. False before the save exists."""
    on, important = AI_SETTINGS[setting]
    return r.set_flag(FLAG_AI, on) and r.set_flag(FLAG_AI_IMPORTANT, important)


def ai_setting(r):
    """The setting the save in RAM holds ('off', 'all' or 'important'); 'off' before the save exists."""
    on, important = r.flag(FLAG_AI), r.flag(FLAG_AI_IMPORTANT)
    return 'off' if not on else 'important' if important else 'all'


if __name__ == '__main__':
    main()
