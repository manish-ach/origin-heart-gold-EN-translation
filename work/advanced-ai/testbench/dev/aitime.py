"""Think time on the emulated DS: what the trainer AIs cost per poll and per decision, how much of each main-loop pass
the battle leaves idle, and whether the AI thinks while the player's menu waits. Findings (Spanish build): the Spanish
workspace's qa/ai_think_time.md.

  .venv/bin/python work/advanced-ai/testbench/dev/aitime.py --rom ROM --payload P --selftest   # the clock's calibration
  .venv/bin/python work/advanced-ai/testbench/dev/aitime.py --rom ROM --payload P battles N [--seed S] [--workers W]
                                                                                            [--count K]
  .venv/bin/python work/advanced-ai/testbench/dev/aitime.py --rom ROM --payload P bench [ID|CATEGORY ...] [--workers W]
  .venv/bin/python work/advanced-ai/testbench/dev/aitime.py --rom ROM --payload P human [CASE ...] [--wait F]
  .venv/bin/python work/advanced-ai/testbench/dev/aitime.py report      # tables from every run saved in RUNS/aitime/

Ported from the Spanish workspace's tools/aitime.py (dc8577c). Changes: the AI's code ranges for --count come from the
payload's regions (the slot code, the itcm and main regions) instead of the Spanish build module's ITCM_NEW, MAIN_AI and
EVENT_TABLE; the steer-table probe (ES_STEER_TABLE) is not ported; the ROM is linked, not copied; at most 2 workers
(the emulator budget); results in RUNS/aitime/.

All runs use a link to --rom prepared as versus/aivsai.py prepares its own: the bench's pre-battle state, the advanced
AI switched on (in the save in RAM), battle scene off, set style, fast text.

The clock. DeSmuME's system time is the libdesmume global nds_timer, in ARM9 cycles (67.027964 MHz). The interpreter
(this build has the JIT off) advances it after every instruction, and the hardware timers are computed from it
(prescaler 1 = one tick per 2 units), so it is the DS's own time at the instruction a hook fires on, with no effect on
the game. --selftest checks it: 1,120,380 units per VBlank (2 x 560,190 timer ticks), a cascaded hardware timer pair
started on the free timers 1 and 2 counting 560,190 per VBlank and half the units between two hooks, and the game's
own OS tick timer (timer 0, prescaler 64) counting 8,753 per VBlank. DeSmuME's own load accounting (nds.idleCycles,
runCycleCollector: the ARM9 cycles spent halted waiting for an interrupt, per VBlank) gives the idle time.

What is recorded, per run, as events [kind, time, ...]:
  beat   a main-loop pass starts (MAIN_LOOP 0x02000D90), with the ARM9's halted cycles so far
  win    the main loop's WaitFrame calls OS_WaitIrq (0x02000F50); wout: it returns (0x02000F54)
  pin    a client's poll into the AI (0x02203736): side, slot word, the deciding Pokemon's pokeID; pout: its return, r0
  rin    the replacement chooser call after a faint (0x02203C06, ai_replace's hook): side; rout: its return
  sim    the engine's damage simulation (0x02223390), which the advanced AI calls from its early polls
  set    an action setter (move/item/switch/none) with its caller; hsel / hrep: the player's select / replacement
         routine (0x02203654 / 0x02203F00); asel / arep: the AI client's (0x0220368C / 0x02203B60); cmd: a battle
         client command (0x0220467E); key: a scripted press of the player's buttons; menu: the FIGHT menu appears or
         goes (scripted-player runs look at every frame of a selection phase)
beat, pin, pout, rin and rout also carry running totals: the cycles in interrupt handlers (DeSmuME's BIOS IRQ stub,
0xFFFF0274 to 0xFFFF0294), E_WAZA's record loads and their cycles (its 4-slot cache missed: 0x0201A2BC), and the halted
cycles, so a poll's CPU leaves out interrupts and halting. DeSmuME's HG/SS overclock hack (busy frames up to 265 lines)
is switched off unless --overclock: the DS always has 263.
With --count K the first K decisions of the advanced AI in each battle also count its instructions: every halfword of
its code (overlay 10 past overlay 11's image, and the appended ITCM code) is hooked, each instruction is decoded once
(capstone), and its cycles are split from the calls it makes outside its code and from interrupts.
"""
import argparse
import ctypes
import json
import os
import shutil
import statistics
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import aivsai  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402

WORK = tbpaths.WORK
OUT = os.path.join(tbpaths.RUNS, 'aitime')
FRAME = 1120380            # nds_timer units (ARM9 cycles) per VBlank: 263 lines x 4,260
ARM9_HZ = 67027964
TICKS_PER_VBLANK = FRAME // 2   # a hardware timer at prescaler 1 (33.513982 MHz)
VBLANK_LINE = 192
# libdesmume's struct NDSSystem (NDSSystem.h, this build's layout, checked by Clock.check): VCount, idleCycles[2],
# runCycleCollector[2][16] (per VBlank: 1,120,380 minus the cycles halted), idleFrameCounter (the ring's next slot)
NDS_VCOUNT, NDS_IDLE0, NDS_RCC, NDS_IFC = 72, 156, 164, 292
WAIT_CALL, WAIT_RET = 0x02000F50, 0x02000F54     # WaitFrame (build.ARM9_PATCHES): blx OS_WaitIrq; the next instruction
VBLANK_COUNTER = 0x021D0094 + 0x2C               # gSystem.vblankCounter, bumped by WaitFrame after each wait
SIM_DAMAGE = 0x02223390
HUMAN_SELECT, AI_SELECT, HUMAN_REPLACE, AI_REPLACE = 0x02203654, 0x0220368C, 0x02203F00, 0x02203B60
TIMER_CNT = 0x04000100     # TMxCNT_L (+0) and TMxCNT_H (+2) per timer, 4 bytes apart
WAZA_LOAD = 0x0201A2BC     # in E_WAZA (WAZADATA_GetParam 0x0201A274), its 4-slot record cache missed: bl NARC load
IRQ_ENTRY, IRQ_EXIT = 0xFFFF0274, 0xFFFF0294   # DeSmuME's BIOS IRQ stub: push, call [DTCM+0x3FFC] (OS_IrqHandler,
                                               # 0x01FF8000), pop, subs pc, lr, #4 (its last instruction)
SIDE_NAMES = ('player', 'trainer')
BRANCHES = {'b', 'beq', 'bne', 'bcs', 'bhs', 'bcc', 'blo', 'bmi', 'bpl', 'bvs', 'bvc', 'bhi', 'bls', 'bge', 'blt', 'bgt',
            'ble'}
JITTER = 64                # cycles: one instruction's cost bounds the jitter of an emulated frame's end
GAP = 400                  # cycles: more than any single instruction with an I-cache and a D-cache miss (about 100)
NO_FIRST_A = 30            # frames between the scripted player's presses
TAP_STEP = 60              # frames between the scripted player's touches
PHASE_GAP = 60             # frames without the player's routine that end a selection phase


class Clock:
    """The emulator's time and idle accounting, read from libdesmume's globals."""

    def __init__(self, lib):
        self.timer = ctypes.c_uint64.in_dll(lib, 'nds_timer')
        self.nds = ctypes.addressof(ctypes.c_char.in_dll(lib, 'nds'))
        self.settings = ctypes.addressof(ctypes.c_char.in_dll(lib, 'CommonSettings'))
        self.ifc = self.idle0 = self.at = None
        self.total, self.epoch = 0, 0

    def i32(self, off):
        return ctypes.c_int32.from_address(self.nds + off).value

    def vcount(self):
        return self.i32(NDS_VCOUNT)

    def halted(self):
        """(epoch, the ARM9's halted cycles so far). Totals compare only within an epoch: a new one starts when the
        time jumps (a state load) or more than 15 VBlanks passed since the last call (the ring holds 16), so callers
        call it at least once per frame."""
        now, ifc, idle0 = self.timer.value, self.i32(NDS_IFC), self.i32(NDS_IDLE0)
        if self.ifc is None or not 0 <= now - self.at <= 15 * FRAME:
            self.ifc, self.idle0, self.at = ifc, idle0, now
            self.epoch += 1
            return self.epoch, self.total
        n = (ifc - self.ifc) & 15
        done = sum(FRAME - self.i32(NDS_RCC + 4 * ((self.ifc + j) & 15)) for j in range(n))
        self.total += done - self.idle0 + idle0
        self.ifc, self.idle0, self.at = ifc, idle0, now
        return self.epoch, self.total

    def timing_settings(self):
        """CommonSettings fields around dispLayers[2][5] (ten true bytes), as this build's TCommonSettings lays them out:
        int num_cores, bool rigorous_timing, gamehacks {bool en; bool overclock; bool stylusjitter}, int StylusPressure
        (50), dispLayers, bool, FAST_ALIGN bool advanced_timing, bool use_jit, u32 jit_max_block_size (12)."""
        raw = ctypes.string_at(self.settings, 0x2000)
        at = raw.find(b'\x01' * 10)
        while at >= 0:
            adv = (at + 10 + 3) & ~3
            jit, block = raw[adv + 1], struct.unpack_from('<I', raw, (adv + 2 + 3) & ~3)[0]
            if raw[adv] in (0, 1) and jit in (0, 1) and block == 12 and struct.unpack_from('<i', raw, at - 4)[0] == 50:
                return {'advanced_timing': raw[adv], 'use_jit': jit, 'jit_max_block_size': block,
                        'num_cores': struct.unpack_from('<i', raw, at - 12)[0], 'rigorous_timing': raw[at - 8],
                        'gamehacks': raw[at - 7], 'overclock_hack': raw[at - 6], 'overclock_at': at - 6}
            at = raw.find(b'\x01' * 10, at + 1)
        return None

    def set_overclock(self, on):
        """DeSmuME's HG/SS game hack (GameHacks::apply, IPK/IPG): at line 262 with the ARM9 still busy it repeats line
        261, up to twice a frame, so busy frames last up to 265 lines. The DS always has 263. Off for measurements."""
        at = self.timing_settings()['overclock_at']
        ctypes.c_uint8.from_address(self.settings + at).value = int(on)


class Recorder:
    """Timing hooks for a Runner-based battle driver (aibench.Bench or aivsai.Duel), as events in self.events."""

    def attach_timing(self, count=0, overclock=False):
        self.clock = Clock(self.r.emu.lib)
        self.clock.set_overclock(overclock)
        self.events, self.count_left = [], count
        self.hsel_seen, self.hrep_seen, self.script = -10 ** 9, -10 ** 9, None
        self.menu_up, self.menu_seen = 0, -10 ** 9
        self.irq = Span(self.mem, self.clock, IRQ_ENTRY, IRQ_EXIT)
        self.wmiss = Span(self.mem, self.clock, WAZA_LOAD, WAZA_LOAD + 4)
        m = self.mem
        m.register_exec(emu.MAIN_LOOP[b'IPKJ'], self._t_beat)
        m.register_exec(WAIT_CALL, lambda a, s: self.battle_on() and self.ev('win'))
        m.register_exec(WAIT_RET, lambda a, s: self.battle_on() and self.ev('wout'))
        m.register_exec(aivsai.AI_POLL, self._poll)
        m.register_exec(aivsai.AI_POLL_RET, self._poll_ret)
        m.register_exec(aivsai.REPLACE_CALL, self._replace_call)
        m.register_exec(aivsai.REPLACE_RET, self._leave_ai)
        m.register_exec(SIM_DAMAGE, self._t_sim)
        m.register_exec(emu.BATTLE_CMD, self._battle_cmd)
        for addr, kind in ((HUMAN_SELECT, 'hsel'), (AI_SELECT, 'asel'), (HUMAN_REPLACE, 'hrep'), (AI_REPLACE, 'arep')):
            m.register_exec(addr, self._routine(kind))
        step = self.r.step

        def timed_step(n=1):
            for _ in range(n):
                if self.script:
                    self.script()
                watch = getattr(self, 'human', False) and self.r.frames - max(self.hsel_seen, self.hrep_seen) <= PHASE_GAP
                if watch:
                    self.r.skip_render = False      # every frame of a selection phase is looked at
                step(1)
                self.clock.halted()         # once per frame keeps the idle ring readable
                if watch and self.battle_on():
                    up = int(self.r.seen(emu.STATES['fight_menu']))
                    if up != self.menu_up:
                        self.ev('menu', up)
                        self.menu_up = up
                        if up:
                            self.menu_seen = self.r.frames
        self.r.step = timed_step
        if count:
            self.counter = Counter(self)

    def ev(self, kind, *rest):
        self.events.append([kind, self.clock.timer.value] + list(rest))

    def ev_irq(self, kind, *rest):
        """An event that also carries the cycles so far in interrupt handlers, E_WAZA's misses and their cycles, and the
        halted cycles (epoch, total)."""
        self.events.append([kind, self.clock.timer.value] + list(rest) + [self.irq.total, self.wmiss.n, self.wmiss.total,
                                                                           *self.clock.halted()])

    def battle_on(self):
        return self.cur is not None and self.cur.get('injected') and aivsai.Duel.in_battle(self)

    def _t_beat(self, a, s):
        self.r._beat(a, s)
        if self.battle_on():
            self.ev_irq('beat', *self.clock.halted(), self.mu.read_long(VBLANK_COUNTER))

    def _routine(self, kind):
        def f(a, s):
            if self.battle_on():
                self.ev(kind)
                if kind == 'hsel':
                    self.hsel_seen = self.r.frames
                elif kind == 'hrep':
                    self.hrep_seen = self.r.frames
        return f

    def _t_sim(self, a, s):
        if self.battle_on():
            self.ev('sim')

    def _poll(self, a, s):
        sup = getattr(super(), '_poll', None)
        if sup:
            sup(a, s)
        if not self.battle_on():
            return
        side = self.mu.read_byte(self.reg.r4 + aivsai.CLIENT_SIDE) & 1
        bpp = self.mu.read_long(self.reg.r1 + 4)
        poke = self.mu.read_byte(bpp + 0x14) if 0x02200000 <= bpp < 0x02400000 else 0
        slot = self.mu.read_long(self.mu.read_long(aibench.MAIN_PTR) + aivsai.MAIN_SLOT)
        self.ev_irq('pin', side, slot, poke)
        if self.count_left and side == 1 and slot == aibench.AI_OVERLAY:
            self.counter.start()

    def _poll_ret(self, a, s):
        sup = getattr(super(), '_poll_ret', None)
        if sup:
            sup(a, s)
        if not self.battle_on():
            return
        ret = self.reg.r0
        if self.count_left and self.counter.on:
            self.ev('count', *self.counter.stop())
            if ret == 1:
                self.count_left -= 1
                if not self.count_left:
                    self.frame_limit = 0        # Duel.play stops at its next frame
        self.ev_irq('pout', ret)

    def _replace_call(self, a, s):
        sup = getattr(super(), '_replace_call', None)
        if sup:
            sup(a, s)
        if self.battle_on():
            self.ev_irq('rin', self.mu.read_byte(self.reg.r5 + aivsai.CLIENT_SIDE) & 1)

    def _leave_ai(self, a=None, s=None):
        sup = getattr(super(), '_leave_ai', None)
        if sup:
            sup(a, s)
        if self.battle_on() and a == aivsai.REPLACE_RET:
            self.ev_irq('rout')

    def _battle_cmd(self, a, s):
        sup = getattr(super(), '_battle_cmd', None)
        if sup:
            sup(a, s)
        if self.battle_on():
            self.ev('cmd', self.mu.read_long(self.reg.r4 + 0x2C))

    def _setter(self, kind):
        inner = super()._setter(kind)

        def f(a, s):
            if self.battle_on():
                self.ev('set', kind, self.reg.r14, self.reg.r1, self.reg.r2)
            inner(a, s)
        return f



class Span:
    """Cycles spent between an entry and an exit instruction (outermost entries only), summed in .total, count in .n:
    the interrupt handlers (BIOS stub entry to its return), or E_WAZA's record loads on a cache miss."""

    def __init__(self, mem, clock, entry, exit_):
        self.timer, self.total, self.n, self.depth, self.t_in = clock.timer, 0, 0, 0, 0
        signed = lambda a: a - (1 << 32) if a >> 31 else a  # noqa: E731  (libdesmume takes the address as a C int)
        mem.register_exec(signed(entry), self._in)
        mem.register_exec(signed(exit_), self._out)

    def _in(self, a, s):
        if not self.depth:
            self.t_in = self.timer.value
        self.depth += 1
        self.n += 1

    def _out(self, a, s):
        if self.depth:
            self.depth -= 1
            if not self.depth:
                self.total += self.timer.value - self.t_in


class Counter:
    """Counts the advanced AI's own instructions while on, from exec hooks on every halfword of its code."""

    def __init__(self, rec):
        from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
        self.md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        self.rec, self.on = rec, False
        self.ranges, self.code = ai_code(rec.rom_path)
        self.info = {}
        timer, reg, irq = rec.clock.timer, rec.reg, rec.irq
        st = self

        def ins(a, s):
            if not st.on:
                return
            t = timer.value
            info = st.info.get(a) or st.decode(a)
            prev = st.prev
            irq_now = irq.total
            if prev is not None:
                dt = t - st.t - (irq_now - st.irq_mark)    # interrupt handlers are counted apart
                pa, pinfo = prev
                kind = pinfo[2]
                if kind == 'branch':                    # taken unless it fell through
                    taken = a != pa + 2
                    st.ideal += 3 if taken else 1
                    st.desmume += 3 if taken and pinfo[3] else 1
                if kind in ('bl2', 'blx_reg') and a == pa + 2:
                    st.out += dt                        # a call outside the AI's code returned
                    st.outs += 1
                    row = st.by_target.get(st.target)
                    if row is None:
                        row = st.by_target[st.target] = [0, 0]
                    row[0] += 1
                    row[1] += dt
                elif dt > GAP:
                    st.gap += dt                        # unexplained: reported, so a missed excursion shows
                else:
                    st.cyc += dt
            if info[2] == 'call_out':
                st.target = info[5]
            elif info[2] == 'blx_reg':
                st.target = reg[info[5]] & ~1
            if not info[0]:
                st.n += 1
                st.ideal += info[1] if info[2] != 'branch' else 0
                st.desmume += info[4] if info[2] != 'branch' else 0
                st.tally[info[2]] = st.tally.get(info[2], 0) + 1
            st.prev, st.t, st.irq_mark = (a, info), t, irq_now
        self._ins = ins                                 # ctypes keeps only the pointer
        for lo, hi in self.ranges:
            rec.mem.register_exec(lo, ins, size=hi - lo)

    def decode(self, a):
        """(BL/BLX second half, ideal cycles, class, conditional, DeSmuME's all-hit cycles) of the instruction at a:
        ideal = hostai/thumbcount.py's cycles_of (ARM9E-S, every access a hit); DeSmuME's from its Thumb handlers
        (thumb_instructions.cpp: loads 3, stores 2, push 3/4, pop 2/5 with pc, ldm 3, stm 2, at least one per register;
        taken branch 3, B 1, BL 1 + 4, BX 3, BLX 4) with a TCM or cache hit costing 1."""
        lo = next(lo for lo, hi in self.ranges if lo <= a < hi)
        op = self.code[lo][a - lo] | self.code[lo][a - lo + 1] << 8
        if op & 0xF800 in (0xF800, 0xE800):
            info = (True, 0, 'bl2', False, 0)
        elif op & 0xF800 == 0xF000:                    # BL/BLX first half: the call's target, from both halves
            op2 = self.code[lo][a - lo + 2] | self.code[lo][a - lo + 3] << 8
            hi = (op & 0x7FF) - (0x800 if op & 0x400 else 0)
            target = (a + 4 + (hi << 12) + ((op2 & 0x7FF) << 1)) & 0xFFFFFFFF
            info = (False, 4, 'call_out', False, 5, target & ~3 if op2 & 0xF800 == 0xE800 else target)
        else:
            ins = next(self.md.disasm(self.code[lo][a - lo:a - lo + 2], a), None)
            m, ops = (ins.mnemonic, ins.op_str) if ins else ('?', '')
            n = ops.count(',') + 1
            if m in ('push', 'pop', 'ldm', 'stm', 'ldmia', 'stmia'):
                pc = 'pc' in ops or 'lr' in ops
                ideal = n + 1 + (2 if 'pc' in ops else 0)
                base = {'push': 4 if pc else 3, 'pop': 5 if pc else 2, 'ldm': 3, 'ldmia': 3, 'stm': 2, 'stmia': 2}[m]
                info = (False, ideal, 'multi', False, max(base, n + (1 if m == 'pop' and pc else 0)))
            elif m.startswith('ldr'):
                info = (False, 1.5, 'load', False, 3)
            elif m.startswith('str'):
                info = (False, 1, 'store', False, 2)
            elif m == 'blx':
                info = (False, 3, 'blx_reg', False, 4, (op >> 3) & 0xF)
            elif m == 'bx':
                info = (False, 3, 'bx', False, 3)
            elif m.startswith('mul'):
                info = (False, 3, 'mul', False, 2)
            elif m in BRANCHES:
                info = (False, 3, 'branch', m != 'b', 1)
            else:
                info = (False, 1, 'alu', False, 1)
        self.info[a] = info
        return info

    def start(self):
        self.on, self.prev, self.t, self.irq_mark = True, None, self.rec.clock.timer.value, self.rec.irq.total
        self.t0 = self.t
        self.n = self.cyc = self.out = self.outs = self.gap = 0
        self.target, self.by_target = None, {}
        self.ideal = self.desmume = 0.0
        self.tally = {}

    def stop(self):
        self.on = False
        return [self.n, self.cyc, self.out, self.outs, round(self.ideal), round(self.desmume), self.tally, self.gap,
                {('%08X' % k if isinstance(k, int) else str(k)): v for k, v in self.by_target.items()}]


def ai_code(rom):
    """([(lo, hi)], {lo: bytes}) of the advanced AI's code in RAM, from the ROM file (the slot holds other overlays
    outside a selection phase) and the payload's regions: overlay 10 past overlay 11's image and bss (the slot region's
    start) to the end of its file, the itcm region's code and the main region's code."""
    import ndspy.code
    import ndspy.rom
    lay = payload.load()
    r = ndspy.rom.NintendoDSRom.fromFile(rom)
    o = r.loadArm9Overlays()[aibench.AI_OVERLAY]
    with open(rom, 'rb') as f:
        off, _, ram, size = struct.unpack_from('<IIII', f.read(0x30), 0x20)
        f.seek(off)
        arm9 = f.read(size)
    sections = [(sec.ramAddress, bytes(sec.data)) for sec in ndspy.code.MainCodeFile(arm9, ram).sections]
    slot = (lay.adv_code[0], o.ramAddress + len(o.data))
    ranges, code = [slot], {slot[0]: bytes(o.data[slot[0] - o.ramAddress:])}
    for name in ('itcm', 'main'):
        reg = lay.regions.get(name) or {}
        lo, n = reg.get('ram'), reg.get('size') or 0
        if lo is None or not n:
            continue
        data = next((d[lo - b:lo - b + n] for b, d in sections if b <= lo < b + len(d)), b'')
        if len(data) != n:
            sys.exit('the %s region %08X+%d is not in an autoload section of %s' % (name, lo, n, rom))
        ranges.append((lo, lo + n))
        code[lo] = data + b'\0\0'
    return ranges, code


class TimedDuel(Recorder, aivsai.Duel):
    """An AI-vs-AI (or scripted player) battle with the timing hooks."""

    def __init__(self, rom, state, mode='adv', count=0, double=False, overclock=False):
        self.rom_path = rom
        super().__init__(rom, state, mode)
        self.double = double
        self.attach_timing(count, overclock)

    def _double(self, a, s):
        if self.cur is not None and self.double and self.reg.r2 == 0:
            self.reg.r2 = self.reg.r1


class TimedBench(Recorder, aibench.Bench):
    def __init__(self, rom, state, overclock=False):
        self.rom_path = rom
        super().__init__(rom, state)
        self.attach_timing(0, overclock)


class Player:
    """The scripted player: once the select (or replacement) routine has run for `wait` frames in a phase, press A
    every NO_FIRST_A frames until the routine stops running, then wait for the next phase. `phases` limits how many
    phases it plays; after that it presses nothing. In a phase of `taps` ({phase: [lower-screen points]}) it first
    touches those points, TAP_STEP frames apart (held 6 frames each), then goes on with A."""
    POKEMON = (221, 165)    # the battle menu's POKEMON button (BAG is at (35, 165))
    SHIFT = (128, 108)      # SHIFT (CAMBIAR in Spanish) in the chosen Pokemon's menu (versus/aiplay.py KeyBot)

    def __init__(self, rec, wait, phases=99, replace=True, taps=None):
        self.rec, self.wait, self.phases, self.replace = rec, wait, phases, replace
        self.since, self.last_press, self.played = None, -10 ** 9, 0
        self.taps, self.tap_at = {int(k): v for k, v in (taps or {}).items()}, None    # the job's JSON keys are strings

    @classmethod
    def switch_to(cls, slot):
        """The touches that switch to party slot `slot`: POKEMON, its panel (two columns of three), CAMBIAR."""
        return [cls.POKEMON, (64 + 128 * (slot % 2), 28 + 48 * (slot // 2)), cls.SHIFT]

    def tapping(self, f):
        """True while this phase's touches are under way (one each TAP_STEP frames)."""
        rec, points = self.rec, self.taps.get(self.played, [])
        k = f - self.tap_at
        if k // TAP_STEP < len(points) and k % TAP_STEP == 0:
            rec.ev('key', 'touch')
            rec.r.emu.input.touch_set_pos(*points[k // TAP_STEP])
        elif k % TAP_STEP == 6:
            rec.r.emu.input.touch_release()
        return k < len(points) * TAP_STEP

    def __call__(self):
        rec, f = self.rec, self.rec.r.frames
        if f - self.last_press == 4:
            rec.r.emu.input.keypad_rm_key(emu.keymask(emu.KEYS['A']))
        # an AI poll can stall the main loop for several VBlanks, so a phase ends only after a longer gap
        active = f - rec.hsel_seen <= PHASE_GAP or (self.replace and f - rec.hrep_seen <= PHASE_GAP)
        if not active:
            if self.since is not None:
                self.played += 1
            self.since, self.tap_at = None, None
            return
        if self.since is None:
            self.since = f
        if self.played >= self.phases:
            return
        recent = f - rec.hsel_seen <= 2 or (self.replace and f - rec.hrep_seen <= 2)
        # a selection waits from the moment the FIGHT menu is on screen, a replacement from its routine's start
        start = rec.menu_seen if rec.hsel_seen > rec.hrep_seen else self.since
        if self.tap_at is None and self.played in self.taps and start >= self.since and f - start >= self.wait:
            self.tap_at = f
        if self.tap_at is not None and self.tapping(f):
            return
        if recent and start >= self.since and f - start >= self.wait and f - self.last_press >= NO_FIRST_A:
            self.last_press = f
            rec.ev('key', 'A')
            rec.r.emu.input.keypad_add_key(emu.keymask(emu.KEYS['A']))


# ---------------------------------------------------------------- runs

def prepare(rom, original=False):
    """The prepared ROM copy, pre-battle state and save (aivsai.prepare under this tool's own tag); original: the
    advanced AI's flag clear, so trainers use overlay 11."""
    tag = 'aitime_' + os.path.splitext(os.path.basename(rom))[0] + ('_orig' if original else '')
    aivsai.hold_tag(tag)
    rom_copy, state, save = aivsai.prepare(rom, original, tag)
    return tag, rom_copy, state, save


def parallel(kind, jobs, rom, workers, options):
    """Run jobs on `workers` processes (each its own ROM copy and battery save); their results in order."""
    os.makedirs(OUT, exist_ok=True)
    tag, rom_copy, state, save = prepare(rom, options.get('original', False))
    chunks = [jobs[k::workers] for k in range(workers) if jobs[k::workers]]

    def go(k):
        rom_k, dsv_k = os.path.join(OUT, '%s_%d.nds' % (tag, k)), os.path.join(aibench.DSV_DIR, '%s_%d.dsv' % (tag, k))
        aibench.link_rom(rom, rom_k)
        shutil.copy(save, dsv_k)
        jp, op = os.path.join(OUT, 'jobs_%s_%d.json' % (tag, k)), os.path.join(OUT, 'res_%s_%d.json' % (tag, k))
        json.dump(chunks[k], open(jp, 'w'))
        if os.path.exists(op):
            os.remove(op)
        log = open(os.path.join(OUT, 'worker_%s_%d.log' % (tag, k)), 'w')
        subprocess.run([sys.executable, __file__, '--worker', kind, rom_k, state, jp, op, json.dumps(options)],
                       stdout=log, stderr=subprocess.STDOUT)
        for p in (rom_k, dsv_k):
            if os.path.lexists(p):
                os.remove(p)
        try:
            return json.load(open(op))
        except (OSError, ValueError):
            return []
    with ThreadPoolExecutor(len(chunks)) as pool:
        return [x for part in pool.map(go, range(len(chunks))) for x in part]


def worker(kind, rom, state, jobs_path, out_path, options):
    jobs, results, opt = json.load(open(jobs_path)), [], json.loads(options)
    count, overclock = opt.get('count', 0), opt.get('overclock', False)
    if kind == 'bench':
        from aidata import Data
        d = Data(rom)
        template = aibench.template_mon()
        by_id = {s['id']: s for s in aibench.scenarios()}
        bench = TimedBench(rom, state, overclock)
        for sid in jobs:
            sc = by_id[sid]
            seed = aibench.hash_id(sid) * 7919 & 0xFFFFFFFF
            mons = {k: [aibench.build_mon(d, template, spec, seed + 31 * i) for i, spec in enumerate(sc[k])]
                    for k in ('player', 'enemy')}
            items = [d.id('item', x) for x in sc.get('items', [])]
            bench.events = []
            res = bench.run(mons, items, seed, bool(sc.get('double')), bool(sc.get('strong')))
            results.append({'id': sid, 'cat': sc['cat'], 'double': bool(sc.get('double')), 'nbench': len(sc['enemy']) - 1,
                            'slot': res['slot'], 'call': res['call'], 'injected': res['injected'],
                            'polls_dbg': (res['adv'] or {}).get('polls'), 'fallback': (res['adv'] or {}).get('fallback'),
                            'events': bench.events})
            json.dump(results, open(out_path, 'w'))
        return
    duel = TimedDuel(rom, state, 'adv', count=count if kind == 'battles' else 0, overclock=overclock)  # one per process
    for job in jobs:
        duel.double = bool(job.get('double'))
        duel.hsel_seen = duel.hrep_seen = duel.menu_seen = -10 ** 9
        duel.menu_up = 0
        duel.events, duel.count_left = [], count if kind == 'battles' else 0
        duel.frame_limit = job.get('frame_limit', aivsai.FRAME_LIMIT)
        duel.human = kind == 'human'
        duel.script = Player(duel, job['wait'], job.get('phases', 99), taps=job.get('taps')) if duel.human else None
        t0 = time.time()
        with aivsai.quiet():
            res = duel.play(job['game'])
        results.append({'job': {k: v for k, v in job.items() if k != 'game'}, 'scenario': job['game']['scenario'],
                        'game': job['game']['game'], 'adv_team': res['adv_team'], 'orig_team': res['orig_team'],
                        'end': res['end'], 'winner': res['winner'], 'turns': res['turns'], 'frames': res['frames'],
                        'fallbacks': res['fallbacks'], 'seconds': round(time.time() - t0, 1), 'events': duel.events})
        json.dump(results, open(out_path, 'w'))


def save_run(name, meta, results):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + '.json')
    json.dump({'meta': meta, 'results': results}, open(path, 'w'))
    print('saved', os.path.relpath(path, WORK))
    return path


def meta_of(rom, **kw):
    import hashlib
    return dict(rom=os.path.basename(rom), rom_sha1=hashlib.sha1(open(rom, 'rb').read()).hexdigest(),
                date=time.strftime('%Y-%m-%d %H:%M'), **kw)


def run_battles(a):
    games = aivsai.games_of(aivsai.draw_scenarios(a.n, 'trainers', 100, a.seed), both=True)
    games = games[:a.n]
    for g in games:
        g['rng'] = 'synced'
    jobs = [{'game': g, 'frame_limit': a.frames} for g in games]
    t0 = time.time()
    res = parallel('battles', jobs, a.rom, a.workers, {'count': a.count, 'overclock': a.overclock})
    print('%d battles in %.0f s' % (len(res), time.time() - t0))
    return save_run('battles_s%d_n%d%s%s' % (a.seed, a.n, '_count%d' % a.count if a.count else '', '_oc' if a.overclock else ''),
                    meta_of(a.rom, kind='battles', seed=a.seed, n=a.n, count=a.count, overclock=a.overclock), res)


def run_bench(a):
    chosen = aibench.select(a.names, aibench.scenarios())
    if a.per_group:         # the first K scenarios of each kind: doubles, singles with 0, 1, 2, 3+ on the bench
        groups = {}
        for sc in chosen:
            groups.setdefault((bool(sc.get('double')), min(len(sc['enemy']) - 1, 3)), []).append(sc)
        chosen = [sc for g in sorted(groups) for sc in groups[g][:a.per_group]]
    t0 = time.time()
    res = parallel('bench', [s['id'] for s in chosen], a.rom, a.workers, {'overclock': a.overclock})
    print('%d bench runs in %.0f s' % (len(res), time.time() - t0))
    return save_run('bench_' + ('_'.join(a.names) if a.names else 'all') + ('_g%d' % a.per_group if a.per_group else '') +
                    ('_oc' if a.overclock else ''),
                    meta_of(a.rom, kind='bench', names=a.names, overclock=a.overclock), res)


def faint_team(name, lead, rest=(('Pidgey', 'Tackle'), ('Rattata', 'Tackle'))):
    species, level, moves = lead
    team = [{'species': species, 'level': level, 'moves': moves, 'nature': 'Hardy'}]
    team += [{'species': s, 'level': 50, 'moves': [m], 'nature': 'Hardy'} for s, m in rest]
    return {'name': name, 'team': team}


def human_cases(seed, wait):
    six = aivsai.games_of(aivsai.draw_scenarios(2, 'trainers', 100, seed), both=False)
    for g in six:
        g['rng'] = 'synced'
    weak, strong = ('Magikarp', 5, ['Splash']), ('Mewtwo', 100, ['Psychic'])

    def custom(sid, adv, orig):
        return {'scenario': sid, 'game': 0, 'seed': seed, 'rng': 'synced', 'adv': adv, 'orig': orig}
    return {
        # the player waits `wait` frames at every menu, three turns
        'singles': {'game': six[0], 'wait': wait, 'phases': 3, 'frame_limit': 3 * wait + 2400},
        # the player answers as soon as the menu is up: what the AI adds when there is nothing to overlap with
        'fast': {'game': six[0], 'wait': 0, 'phases': 3, 'frame_limit': 2400},
        # switching to its second Pokemon in the first phase, a second after the menu is up (it takes no touch before):
        # the AI facing a known switch (tools/ai foe_choice)
        'switch': {'game': six[0], 'wait': 60, 'phases': 3, 'frame_limit': 2400, 'taps': {0: Player.switch_to(1)}},
        'doubles': {'game': six[1], 'wait': wait, 'phases': 2, 'frame_limit': 2 * wait + 2400, 'double': True},
        # the player's Mewtwo knocks out the AI's lead: the AI chooses its replacement (ai_replace)
        'ai_faint': {'game': custom('ai_faint', faint_team('AI lead falls', weak), faint_team('Player', strong)),
                     'wait': 60, 'phases': 2, 'frame_limit': 2400},
        # the AI's Mewtwo knocks out the player's lead: the player's party screen waits
        'player_faint': {'game': custom('player_faint', faint_team('AI', strong), faint_team('Player lead falls', weak)),
                         'wait': 60, 'phases': 1, 'frame_limit': 2400},
        # Explosion: both leads fall in one turn, both sides choose a replacement
        'both_faint': {'game': custom('both_faint', faint_team('AI lead falls', weak),
                                      faint_team('Player explodes', ('Golem', 100, ['Explosion']))),
                       'wait': 60, 'phases': 1, 'frame_limit': 2400},
    }


def run_human(a):
    cases = human_cases(a.seed, a.wait)
    names = a.cases or list(cases)
    jobs = [dict(cases[n], case=n) for n in names]
    t0 = time.time()
    res = parallel('human', jobs, a.rom, min(a.workers, len(jobs)), {'overclock': a.overclock, 'original': a.original})
    print('%d human runs in %.0f s' % (len(res), time.time() - t0))
    return save_run('human_w%d_%s%s%s' % (a.wait, '_'.join(names) if a.cases else 'all', '_orig' if a.original else '',
                                          '_oc' if a.overclock else ''),
                    meta_of(a.rom, kind='human', seed=a.seed, wait=a.wait, cases=names, overclock=a.overclock,
                            ai='original' if a.original else 'advanced'), res)


# ---------------------------------------------------------------- calibration

def selftest(rom):
    """The clock against the DS's own timers and VBlanks, and DeSmuME's idle accounting against the hooked waits."""
    tag, rom_copy, state, save = prepare(rom)
    r = emu.Runner(rom_copy, os.path.join(OUT, 'shots'))
    r.skip_render = True
    clock = Clock(r.emu.lib)
    mu, mem = r.emu.memory.unsigned, r.emu.memory
    events, lines_at_wake = [], []
    ev = lambda *e: events.append([e[0], clock.timer.value] + list(e[1:]))  # noqa: E731
    irq = Span(mem, clock, IRQ_ENTRY, IRQ_EXIT)
    mem.register_exec(emu.MAIN_LOOP[b'IPKJ'], lambda a, s: ev('beat', *clock.halted(), mu.read_long(VBLANK_COUNTER),
                                                              irq.total))
    mem.register_exec(WAIT_CALL, lambda a, s: ev('win'))
    mem.register_exec(WAIT_RET, lambda a, s: (ev('wout'), lines_at_wake.append(clock.vcount())))
    r.emu.savestate.load_file(state)
    problems, lines = [], []

    def check(ok, text):
        lines.append(('ok   ' if ok else 'FAIL ') + text)
        if not ok:
            problems.append(text)
    settings = clock.timing_settings()
    check(settings is not None and settings['use_jit'] == 0 and settings['advanced_timing'] == 1,
          'DeSmuME settings %s: interpreter (no JIT), advanced bus timing (caches, waits) on' % settings)
    for hack in (True, False):
        clock.set_overclock(hack)
        lens = []
        for f in range(60):
            t = clock.timer.value
            r.step(1)
            lens.append((clock.timer.value - t + FRAME // 526) // (FRAME // 263))
        lines.append('     overclock hack %s: frame lengths in lines %s' % (
            'on (DeSmuME default for HG/SS)' if hack else 'off', dict(sorted(collections_counter(lens).items()))))
    check(clock.timing_settings()['overclock_hack'] == 0, 'overclock hack off for the measurements')
    del events[:]
    cnt = [mu.read_short(TIMER_CNT + 4 * k + 2) for k in range(4)]
    check(cnt[1] & 0x80 == 0 and cnt[2] & 0x80 == 0, 'timers 1 and 2 free (TMxCNT_H %s)' % ['%04X' % c for c in cnt])
    # a cascade on the free timers: timer 1 prescaler 1 (33.513982 MHz), timer 2 counting its overflows
    for k, ctl in ((1, 0), (2, 0)):
        mem.write_short(TIMER_CNT + 4 * k + 2, ctl)
        mem.write_short(TIMER_CNT + 4 * k, 0)
    mem.write_short(TIMER_CNT + 4 * 2 + 2, 0x84)
    mem.write_short(TIMER_CNT + 4 * 1 + 2, 0x80)
    hw = lambda: mu.read_short(TIMER_CNT + 4) | mu.read_short(TIMER_CNT + 8) << 16  # noqa: E731
    tick0 = lambda: mu.read_short(TIMER_CNT)  # noqa: E731
    rows = []
    for f in range(301):
        if f:
            r.step(1)
            clock.halted()
        rows.append((clock.timer.value, hw(), tick0(), clock.i32(NDS_IFC)))
    dts = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    dhw = [(b[1] - a[1]) & 0xFFFFFFFF for a, b in zip(rows, rows[1:])]
    d0 = [(b[2] - a[2]) & 0xFFFF for a, b in zip(rows, rows[1:])]
    difc = [(b[3] - a[3]) & 15 for a, b in zip(rows, rows[1:])]
    # one emulated frame ends after the instruction that crosses its last line, so single frames jitter by that
    # instruction's cycles; the total over 300 frames does not
    check(max(abs(x - FRAME) for x in dts) <= JITTER, 'nds_timer per emulated frame: %d-%d (want %d = 2 x %d, within the '
          'last instruction\'s %d)' % (min(dts), max(dts), FRAME, TICKS_PER_VBLANK, JITTER))
    total_hw, total_t = (rows[-1][1] - rows[0][1]) & 0xFFFFFFFF, rows[-1][0] - rows[0][0]
    check(abs(total_t - 300 * FRAME) <= JITTER, 'over 300 frames nds_timer advanced %d = 300 x %d %+d' % (
        total_t, FRAME, total_t - 300 * FRAME))
    check(max(abs(x - TICKS_PER_VBLANK) for x in dhw) <= JITTER // 2,
          'hardware timers 1+2 (prescaler 1, cascaded) per frame: %d-%d (want %d)' % (min(dhw), max(dhw), TICKS_PER_VBLANK))
    check(abs(total_hw * 2 - total_t) <= 2, 'over 300 frames: hardware %d ticks x 2 = %d, nds_timer %d' % (
        total_hw, total_hw * 2, total_t))
    check(max(abs(x - FRAME / 2 / 64) for x in d0) <= 1, 'the game\'s OS tick timer 0 (prescaler 64) per VBlank: %d-%d '
          '(want %.2f)' % (min(d0), max(d0), FRAME / 2 / 64))
    check(set(difc) == {1}, 'DeSmuME idle ring advances one slot per VBlank (%s)' % sorted(set(difc)))
    vb_rate = ARM9_HZ / FRAME
    check(abs(vb_rate - 59.8261) < 0.001, 'VBlank rate %.4f Hz from 67,027,964 / 1,120,380' % vb_rate)
    # main-loop passes (the field before the bench's battle): two VBlanks each at 30 fps, two waits each, and the
    # halted cycles inside the waits (the rest of a wait is the interrupt handlers that end it)
    passes = [p for p in passes_of(events) if p['halted'] is not None][1:]
    beats = beats_of(events)
    lens = sorted({p['vblanks'] for p in passes})
    check(lens == [2], 'main-loop passes last %s VBlanks (want 2 at 30 fps; %d passes)' % (lens, len(passes)))
    vbc = sorted({b[4] - a[4] for a, b in zip(beats, beats[1:])})
    check(vbc == [2], 'gSystem.vblankCounter +2 per pass: %s' % vbc)
    check(set(lines_at_wake) <= {VBLANK_LINE, VBLANK_LINE + 1}, 'every WaitFrame returns at line %s (VBlank starts at '
          'line %d)' % (sorted(set(lines_at_wake)), VBLANK_LINE))
    bad = [p for p in passes if not 0 < p['halted'] <= p['waited']]
    check(not bad, 'halted cycles within the time in WaitFrame in every pass (%d passes, %d not)' % (len(passes), len(bad)))
    busy = [p['t1'] - p['t0'] - p['halted'] for p in passes]
    in_waits = [p['waited'] - p['halted'] for p in passes]
    irqs = [p['irq'] for p in passes]
    check(all(0 < p['irq'] <= p['t1'] - p['t0'] - p['halted'] for p in passes),
          'interrupt handler cycles (BIOS stub entry to return) within the busy cycles of every pass')
    lines.append('     field passes: busy median %d cycles (%.1f%% of a pass), halted median %d; interrupt handlers median '
                 '%d per pass (%d per frame), and the time in WaitFrame not halted median %d' % (
                     statistics.median(busy), 100 * statistics.median(busy) / (2 * FRAME),
                     statistics.median(p['halted'] for p in passes), statistics.median(irqs),
                     round(irq.n / max(1, len(passes) * 2 + 2)), statistics.median(in_waits)))
    print('\n'.join(lines))
    sys.exit(1 if problems else 0)


# ---------------------------------------------------------------- analysis

def polls_of(events):
    """Every AI poll: dict(side, slot, poke, t0, t1, ret, sims, count)."""
    out, cur = [], None
    for e in events:
        k = e[0]
        if k == 'pin':
            cur = {'side': e[2], 'slot': e[3], 'poke': e[4], 't0': e[1], 'sims': 0, 'irq0': e[5] if len(e) > 5 else None,
                   'w0': e[6:8] if len(e) > 7 else None, 'h0': e[8:10] if len(e) > 9 else None}
        elif k == 'sim' and cur is not None:
            cur['sims'] += 1
        elif k == 'count' and cur is not None:
            cur['count'] = e[2:]
        elif k == 'pout' and cur is not None:
            cur['t1'], cur['ret'] = e[1], e[2]
            cur['cyc'] = cur['t1'] - cur['t0']
            cur['irq'] = e[3] - cur['irq0'] if len(e) > 3 and cur['irq0'] is not None else None
            cur['cpu'] = cur['cyc'] - (cur['irq'] or 0)      # the poll without the interrupts inside it
            if cur['w0'] is not None and len(e) > 5:
                cur['wmiss'], cur['wmiss_cyc'] = e[4] - cur['w0'][0], e[5] - cur['w0'][1]
            if cur['h0'] is not None and len(e) > 7 and e[6] == cur['h0'][0]:
                cur['halted'] = e[7] - cur['h0'][1]           # the ARM9 halted inside the poll (waiting for an IRQ)
                cur['cpu'] -= cur['halted']
            out.append(cur)
            cur = None
    return out


def decisions_of(polls):
    """Polls grouped into decisions: a side's consecutive polls for one Pokemon, ending with the poll that returns 1."""
    open_, out = {}, []
    for p in polls:
        key = (p['side'], p['poke'])
        open_.setdefault(key, []).append(p)
        if p['ret'] == 1:
            ps = open_.pop(key)
            adv = p['side'] == 1 and p['slot'] == aibench.AI_OVERLAY
            out.append({'side': p['side'], 'ai': 'advanced' if adv else 'original', 'polls': ps,
                        'cyc': sum(x['cyc'] for x in ps), 'last': ps[-1]['cyc'], 'first': ps[0]['cyc'],
                        'mid': [x['cyc'] for x in ps[1:-1]], 'span': ps[-1]['t1'] - ps[0]['t0'],
                        'cpu': sum(x['cpu'] for x in ps), 'last_cpu': ps[-1]['cpu'], 'first_cpu': ps[0]['cpu'],
                        'mid_cpu': [x['cpu'] for x in ps[1:-1]],
                        'sims': sum(x['sims'] for x in ps), 't0': ps[0]['t0'], 't1': ps[-1]['t1']})
    return out


def beats_of(events):
    return [e for e in events if e[0] == 'beat']


def passes_of(events):
    """Main-loop passes: dict(t0, t1, vblanks, halted (None if unknown), waited)."""
    bs = beats_of(events)
    waits, pend = [], None
    for e in events:
        if e[0] == 'win':
            pend = e[1]
        elif e[0] == 'wout' and pend is not None:
            waits.append((pend, e[1]))
            pend = None
    out, wi = [], 0
    for a, b in zip(bs, bs[1:]):
        w = 0
        while wi < len(waits) and waits[wi][1] <= b[1]:
            if waits[wi][0] >= a[1]:
                w += waits[wi][1] - waits[wi][0]
            wi += 1
        halted = b[3] - a[3] if a[2] == b[2] else None
        irq = b[5] - a[5] if len(a) > 5 and len(b) > 5 else None
        out.append({'t0': a[1], 't1': b[1], 'vblanks': round((b[1] - a[1]) / FRAME), 'halted': halted, 'waited': w,
                    'irq': irq})
    return out


def pass_at(passes, t):
    for p in passes:
        if p['t0'] <= t < p['t1']:
            return p
    return None


def stats(xs, scale=1.0, fmt='%.0f'):
    xs = sorted(x * scale for x in xs)
    if not xs:
        return ['-'] * 5
    p90 = xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]
    return [str(len(xs)), fmt % statistics.median(xs), fmt % p90, fmt % xs[-1], fmt % xs[0]]


def mc(x):
    return x / 1e6


def ms(x):
    return 1000.0 * x / ARM9_HZ


def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def load_runs(kind):
    runs = []
    for name in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
        if name.endswith('.json') and name.startswith(kind + '_'):
            runs.append((name, json.load(open(os.path.join(OUT, name)))))
    return runs


def dist_row(label, xs):
    """label | n | median | p90 | max, as Mcycles and ms, and VBlanks."""
    if not xs:
        return [label, 0, '-', '-', '-', '-']
    s = sorted(xs)
    n = len(s)
    med, p90, mx = statistics.median(s), s[min(n - 1, int(round(0.9 * (n - 1))))], s[-1]
    f = lambda x: '%.2f M / %.1f ms / %.2f VB' % (mc(x), ms(x), x / FRAME)  # noqa: E731
    return [label, n, f(med), f(p90), f(mx)]


def report_battles(lines):
    for name, run in load_runs('battles'):
        res = run['results']
        decs, polls, reps = [], [], []
        for g in res:
            ev = g['events']
            ps = polls_of(ev)
            polls += ps
            ds = decisions_of(ps)
            pa = passes_of(ev)
            for d in ds:
                d['pass'] = pass_at(pa, d['polls'][-1]['t0'])
            decs += ds
            rin = None
            for e in ev:
                if e[0] == 'rin':
                    rin = e
                elif e[0] == 'rout' and rin is not None:
                    irq = e[2] - rin[3] if len(e) > 2 and len(rin) > 3 else 0
                    reps.append((rin[2], e[1] - rin[1] - irq))
                    rin = None
        adv = [d for d in decs if d['ai'] == 'advanced']
        orig = [d for d in decs if d['ai'] == 'original']
        lines.append('\n### %s (%s, %d battles)\n' % (name, run['meta']['rom'], len(res)))
        lines.append('Ends: %s. Decisions: advanced %d, original %d.\n' % (
            ', '.join('%s %d' % (k, sum(1 for g in res if g['end'] == k)) for k in sorted({g['end'] for g in res})),
            len(adv), len(orig)))
        head = ['measured', 'n', 'median', 'p90', 'max']
        rows = [dist_row('advanced: whole decision, CPU (all polls, no interrupts)', [d['cpu'] for d in adv]),
                dist_row('advanced: whole decision, time inside its polls', [d['cyc'] for d in adv]),
                dist_row('advanced: decide() poll, CPU', [d['last_cpu'] for d in adv]),
                dist_row('advanced: decide() poll, time', [d['last'] for d in adv]),
                dist_row('advanced: first poll (snapshot), CPU', [d['first_cpu'] for d in adv]),
                dist_row('advanced: each engine-simulation poll, CPU', [x for d in adv for x in d['mid_cpu']]),
                dist_row('advanced: first poll to answer (wall)', [d['span'] for d in adv]),
                dist_row('original: whole decision, CPU', [d['cpu'] for d in orig]),
                dist_row('original: largest poll, CPU', [max(p['cpu'] for p in d['polls']) for d in orig]),
                dist_row('original: first poll to answer (wall)', [d['span'] for d in orig]),
                dist_row('replacement chooser, trainer side (ai_replace), CPU', [c for s, c in reps if s == 1]),
                dist_row('replacement chooser, player side (engine), CPU', [c for s, c in reps if s == 0])]
        lines.append(table(head, rows))
        irq_share = [p['irq'] / p['cyc'] for d in adv for p in d['polls'] if p.get('irq') is not None and p['cyc'] > FRAME]
        if irq_share:
            lines.append('\nInterrupt handlers take a median %.1f%% of the time inside polls longer than a VBlank.' % (
                100 * statistics.median(irq_share)))
        halt_share = [p['halted'] / p['cyc'] for d in adv for p in d['polls'] if p.get('halted') is not None and p['cyc'] > FRAME]
        if halt_share:
            lines.append('The ARM9 is halted (waiting for an interrupt) a median %.1f%% (p90 %.1f%%) of the time inside those '
                         'polls; CPU figures leave out both.' % (100 * statistics.median(halt_share),
                                                                 100 * sorted(halt_share)[int(0.9 * (len(halt_share) - 1))]))
        six = [d for d in adv if len(d['polls']) >= 8]
        if six:
            lines.append('\nAdvanced decisions with 8 or more polls (a full bench, the foe with others left): %d.\n' % len(six))
            lines.append(table(head, [dist_row('decide() poll, CPU, 8+ polls', [d['last_cpu'] for d in six]),
                                      dist_row('whole decision, CPU, 8+ polls', [d['cpu'] for d in six])]))
        first = [ds_ for ds_ in (next((d for d in decisions_of(polls_of(g['events'])) if d['ai'] == 'advanced'), None)
                                 for g in res) if ds_]
        if first:
            lines.append('\nThe first advanced decision of each battle (turn 1, 6v6 at full HP, as hostai measured):\n')
            lines.append(table(head, [dist_row('decide() poll, CPU', [d['last_cpu'] for d in first]),
                                      dist_row('whole decision, CPU', [d['cpu'] for d in first])]))
        np_ = [len(d['polls']) for d in adv]
        lines.append('\nPolls per advanced decision: %s. Per original decision: %s.' % (
            dict(sorted(collections_counter(np_).items())), dict(sorted(collections_counter([len(d['polls']) for d in orig]).items()))))
        wm = [(sum(p.get('wmiss', 0) for p in d['polls']), sum(p.get('wmiss_cyc', 0) for p in d['polls'])) for d in adv
              if all('wmiss' in p for p in d['polls'])]
        if wm:
            lines.append('E_WAZA record loads (its 4-slot cache missed) per advanced decision: median %d, max %d; their cycles '
                         'median %.2f M per decision, %.0f per load (a file read from the cartridge through FS).' % (
                             statistics.median(n for n, _ in wm), max(n for n, _ in wm), mc(statistics.median(c for _, c in wm)),
                             sum(c for _, c in wm) / max(1, sum(n for n, _ in wm))))
        sims = [p['sims'] for d in adv for p in d['polls'][1:-1]]
        simc = [p['cyc'] / p['sims'] for d in adv for p in d['polls'][1:-1] if p['sims']]
        if sims:
            lines.append('Engine simulations per simulation poll: median %d, max %d; cycles per simulation (poll / sims) '
                         'median %.0f.' % (statistics.median(sims), max(sims), statistics.median(simc)))
        ov = [d['pass']['vblanks'] for d in adv if d.get('pass')]
        lines.append('VBlanks of the main-loop pass that holds the decide() poll (2 = no overrun): %s.' % (
            dict(sorted(collections_counter(ov).items()))))
        ovo = [p['vblanks'] for g in res for p in passes_of(g['events'])]
        lines.append('All passes in these battles: %s.' % dict(sorted(collections_counter(ovo).items())))
        cnt = [(d, d['polls'][-1].get('count')) for d in adv if d['polls'][-1].get('count')]
        if cnt:
            report_count(lines, cnt, adv)


def collections_counter(xs):
    import collections
    return collections.Counter(xs)


def engine_names():
    """{address: name} of the engine entry points the AI calls (src/engine.h's CALL macros)."""
    import re
    text = open(os.path.join(tbpaths.ADV, 'src', 'engine.h')).read()
    names = {int(m.group(2), 16): m.group(1) for m in re.finditer(r'#define\s+(E_\w+)\(.*?CALL\(0x([0-9A-Fa-f]{8})', text)}
    names.update({int(m.group(2), 16): m.group(1) for m in re.finditer(r'#define\s+(\w+)\s+0x(0[0-9A-Fa-f]{7})\b', text)})
    return names


def report_count(lines, cnt, adv):
    lines.append('\n#### Instruction count of the decide() poll (--count)\n')
    rows = []
    agg = {'n': 0, 'cyc': 0, 'ideal': 0, 'desmume': 0, 'out': 0, 'total': 0, 'gap': 0}
    tally = {}
    for d, c in cnt:
        n, cyc, out, outs, ideal, desm, t, gap = c[:8]
        for k, v in (('n', n), ('cyc', cyc), ('ideal', ideal), ('desmume', desm), ('out', out), ('total', d['last']),
                     ('gap', gap)):
            agg[k] += v
        for k, v in t.items():
            tally[k] = tally.get(k, 0) + v
        rows.append([len(rows) + 1, '%.2f M' % mc(n), '%.2f M' % mc(ideal), '%.2f M' % mc(desm), '%.2f M' % mc(cyc),
                     '%.2f M (%d)' % (mc(out), outs), '%.2f M' % mc(d['last']), '%.2f' % (cyc / n if n else 0),
                     '%.2f' % (cyc / ideal if ideal else 0)])
    lines.append(table(['decision', 'Thumb instructions', 'ideal cycles (all hits)', 'DeSmuME all-hit model',
                        'emulated cycles in AI code', 'outside AI code (calls)', 'whole poll', 'CPI emulated',
                        'emulated / ideal'], rows))
    lines.append('\nAll counted decide() polls: %.2f M instructions, CPI ideal %.2f, DeSmuME all-hit %.2f, emulated %.2f; '
                 'emulated / ideal %.2f; emulated / DeSmuME all-hit %.2f (the rest is cache-miss and main-RAM waits); '
                 'outside the AI code %.1f%% of the poll. Unexplained gaps over %d cycles inside the AI code: %d cycles.' % (
                     mc(agg['n']), agg['ideal'] / agg['n'], agg['desmume'] / agg['n'], agg['cyc'] / agg['n'],
                     agg['cyc'] / agg['ideal'], agg['cyc'] / agg['desmume'], 100 * agg['out'] / agg['total'], GAP,
                     agg['gap']))
    lines.append('Instruction classes: %s.' % ', '.join('%s %.1f%%' % (k, 100 * v / agg['n']) for k, v in
                                                         sorted(tally.items(), key=lambda kv: -kv[1]) if k != 'bl2'))
    names = engine_names()
    kinds = {'snapshot (first poll)': [], 'engine-simulation polls': [], 'decide() poll': []}
    for d in adv:
        ps = [p for p in d['polls'] if p.get('count')]
        if len(ps) != len(d['polls']):
            continue
        kinds['snapshot (first poll)'].append(ps[0])
        kinds['engine-simulation polls'] += ps[1:-1]
        kinds['decide() poll'].append(ps[-1])
    lines.append('\nWhere each counted poll spends its cycles (per poll, medians over %d decisions; calls by target; '
                 'irq = interrupt handlers):\n' % len(kinds['decide() poll']))
    rows = []
    for kind, ps in kinds.items():
        if not ps:
            continue
        per = {}
        for p in ps:
            for k, (calls, cyc) in (p['count'][8] if len(p['count']) > 8 else {}).items():
                row = per.setdefault(k, [0, 0])
                row[0] += calls
                row[1] += cyc
        top = sorted(per.items(), key=lambda kv: -kv[1][1])[:5]
        label = lambda k: names.get(int(k, 16), k) if k not in ('irq', 'None') else k  # noqa: E731
        rows.append([kind, len(ps), '%.2f M' % mc(statistics.median(p['cyc'] for p in ps)),
                     '%.0f k' % (statistics.median(p['count'][1] for p in ps) / 1e3),
                     '%.0f k' % (statistics.median(p['count'][0] for p in ps) / 1e3),
                     '; '.join('%s %.0f calls, %.0f k cyc each' % (label(k), v[0] / len(ps), v[1] / max(1, v[0]) / 1e3)
                               for k, v in top)])
    lines.append(table(['poll', 'n', 'whole poll (median)', 'in AI code', 'AI instructions', 'top calls outside, per poll'],
                       rows))


def report_bench(lines):
    for name, run in load_runs('bench'):
        res = [x for x in run['results'] if x['injected']]
        groups = {}
        for x in res:
            ds = [d for d in decisions_of(polls_of(x['events'])) if d['ai'] == 'advanced']
            if not ds:
                continue
            d = ds[0]
            g = 'doubles' if x['double'] else 'singles, %d on the bench' % min(x['nbench'], 3)
            groups.setdefault(g, []).append(d)
        lines.append('\n### %s (%d runs)\n' % (name, len(res)))
        rows = []
        for g in sorted(groups):
            ds = groups[g]
            rows.append(dist_row(g + ': whole decision, CPU', [d['cpu'] for d in ds]))
            rows.append(dist_row(g + ': decide() poll, CPU', [d['last_cpu'] for d in ds]))
        lines.append(table(['measured', 'n', 'median', 'p90', 'max'], rows))


def phases_of(events):
    """Selection (or replacement) phases of a scripted-player run: from the first select or replacement routine (the
    player's or the AI client's) after more than 60 VBlanks without one, to the first battle command after the
    player's answer."""
    out, cur, last_sel = [], None, -10 ** 18
    for e in events:
        k, t = e[0], e[1]
        if k in ('hsel', 'asel', 'hrep', 'arep'):
            if t - last_sel > PHASE_GAP * FRAME:
                cur = {'t0': t, 'routines': {}, 'pin': [], 'pout': [], 'keys': [], 'set': [], 'cmd': None, 'menu_on': None,
                       'beats': [], 'rin': [], 'rout': []}
                out.append(cur)
            last_sel = t
            cur['routines'].setdefault(k, []).append(t)
        elif cur is None:
            continue
        elif k == 'pin':
            cur['pin'].append((t, e[2], e[3]))
        elif k == 'pout':
            cur['pout'].append((t, e[2]))
        elif k == 'rin':
            cur['rin'].append((t, e[2]))
        elif k == 'rout':
            cur['rout'].append(t)
        elif k == 'key':
            cur['keys'].append(t)
        elif k == 'beat':
            cur['beats'].append(t)
        elif k == 'menu' and e[2] == 1 and cur['menu_on'] is None:
            cur['menu_on'] = t
        elif k == 'set' and e[2] != 'none' and not aivsai.ORIG_CODE[0] <= e[3] < aivsai.ADV_CODE[1] \
                and e[3] != aivsai.REPLACE_LR:
            cur['set'].append((t, e[2], e[3]))
        elif k == 'cmd' and cur['cmd'] is None and cur['set']:
            cur['cmd'] = t
    return out


def report_human(lines):
    for name, run in load_runs('human'):
        lines.append('\n### %s (%s AI; the player waits %s VBlanks once the menu is up)\n' % (
            name, run['meta'].get('ai', 'advanced'), run['meta'].get('wait')))
        for x in run['results']:
            ev = x['events']
            lines.append('\n**%s** (%s vs %s, end %s, %d frames)\n' % (x['job'].get('case'), x['adv_team'], x['orig_team'],
                                                                       x['end'], x['frames']))
            rows = []
            ps_all = passes_of(ev)
            for i, p in enumerate(phases_of(ev)):
                t0 = p['t0']
                vb = lambda t: '%.1f' % ((t - t0) / FRAME) if t is not None else '-'  # noqa: E731
                ai = [q for q in p['pin'] if q[1] == 1]
                ai_done = next((t for t, r in p['pout'] if r == 1), None)
                menu = p['menu_on']
                passes_to_menu = sum(1 for b in p['beats'] if menu is not None and b <= menu)
                setup = [q for q in ps_all if menu is not None and t0 <= q['t1'] <= menu + FRAME and q['halted'] is not None]
                ai_cyc = sum(q[1] - q[0] for q in zip([x[0] for x in p['pin']], [x[0] for x in p['pout']])
                             if menu is None or q[0] < menu)
                rows.append([i + 1, ', '.join(sorted(p['routines'])), vb(menu), passes_to_menu if menu else '-',
                             '%.1f M' % mc(sum(q['halted'] for q in setup)) if setup else '-', '%.1f M' % mc(ai_cyc),
                             vb(ai[0][0]) if ai else '-', vb(ai_done), len(ai),
                             sum(1 for q in ai if menu is not None and q[0] >= menu),
                             vb(p['rin'][0][0]) + ' (%s)' % SIDE_NAMES[p['rin'][0][1]] if p['rin'] else '-',
                             vb(p['keys'][0]) if p['keys'] else '-', vb(p['set'][0][0]) if p['set'] else '-',
                             vb(p['cmd'])])
            lines.append(table(['phase', 'routines', 'FIGHT menu on screen', 'passes until then',
                                'halted until then', 'AI poll cycles until then', 'AI first poll',
                                'AI answer', 'AI polls', 'AI polls after the menu is up', 'replacement chooser',
                                'first key', 'player answer', 'next battle command'], rows))
            ps = passes_of(ev)
            hs = sorted(e[1] for e in ev if e[0] == 'hsel')
            busy_marks = sorted(e[1] for e in ev if e[0] in ('pin', 'rin', 'key'))
            import bisect
            menu = []
            for p in ps:
                if p['halted'] is None:
                    continue
                i = bisect.bisect_left(hs, p['t0'])
                j = bisect.bisect_left(busy_marks, p['t0'])
                if i < len(hs) and hs[i] < p['t1'] and not (j < len(busy_marks) and busy_marks[j] < p['t1']):
                    menu.append(p)
            if menu:
                busy = [p['t1'] - p['t0'] - p['halted'] for p in menu]
                irq = [p['irq'] for p in menu if p.get('irq') is not None]
                lines.append('\nPasses with the player\'s select routine running and no AI poll or key: %d; VBlanks per '
                             'pass %s; busy cycles %s, of them interrupt handlers %s; halted cycles %s (n, median, p90, '
                             'max, min).' % (len(menu), dict(sorted(collections_counter([p['vblanks'] for p in menu]).items())),
                                             stats(busy), stats(irq), stats([p['halted'] for p in menu])))


def report():
    lines = ['# Report from tests/run/aitime (aitime.py report)', '',
             'Cycles are ARM9 cycles (67.027964 MHz). VB = VBlank periods (16.715 ms); a main-loop pass is 2 VB at 30 fps.']
    report_battles(lines)
    report_bench(lines)
    report_human(lines)
    text = '\n'.join(lines)
    print(text)
    return text


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:])
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--rom', help='an AI build (not needed for report)')
    ap.add_argument('--payload', help="its payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--overclock', action='store_true', help="keep DeSmuME's HG/SS overclock hack (busy frames up to 265 lines)")
    sub = ap.add_subparsers(dest='cmd')
    b = sub.add_parser('battles')
    b.add_argument('n', type=int)
    b.add_argument('--seed', type=int, default=20261005)
    b.add_argument('--workers', type=int, default=2)
    b.add_argument('--count', type=int, default=0)
    b.add_argument('--frames', type=int, default=aivsai.FRAME_LIMIT)
    c = sub.add_parser('bench')
    c.add_argument('names', nargs='*')
    c.add_argument('--workers', type=int, default=2)
    c.add_argument('--per-group', type=int, default=0)
    h = sub.add_parser('human')
    h.add_argument('cases', nargs='*')
    h.add_argument('--wait', type=int, default=300)
    h.add_argument('--seed', type=int, default=20261005)
    h.add_argument('--workers', type=int, default=2)
    h.add_argument('--original', action='store_true', help='trainers use the original AI (overlay 11)')
    sub.add_parser('report')
    a = ap.parse_args()
    if a.cmd != 'report':
        if not a.rom:
            ap.error('--rom is required')
        payload.path_from(a.payload)        # exported for the workers
    if a.selftest:
        return selftest(a.rom)
    if getattr(a, 'workers', 1) > 2:
        sys.exit('at most 2 workers (the emulator budget)')
    if a.cmd == 'battles':
        run_battles(a)
    elif a.cmd == 'bench':
        run_bench(a)
    elif a.cmd == 'human':
        run_human(a)
    elif a.cmd == 'report':
        report()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
