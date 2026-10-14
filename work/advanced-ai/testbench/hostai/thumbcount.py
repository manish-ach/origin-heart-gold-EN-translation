"""The DS build's own Thumb code, run decision by decision in a CPU emulator (unicorn), to count the instructions the
ARM946E-S executes and estimate its cycles: the measurement behind the on-DS think time.

  PY=<python with unicorn> work/advanced-ai/testbench/hostai/thumbcount.py CASES [--rom ROM] [--layout en]
                                                                            [--ids ID,...] [--max N]

CASES is a case file replay.py wrote (RUNS/hostai/cases.txt, sixes.txt). The AI (src/advai.c and replace.c in one
unit) is compiled with builder/build.py's AI_CFLAGS (plus the layout's cflags), the DS build's own flags, and linked
with libgcc at 0x02380000; each case's address space comes from the ROM's host build, `replay --dump` (the host
stand-in's battle, byte for byte), and the engine
entry points are answered here as engine.c answers them. Each decision's debug record must equal the host build's,
so the counted run is the decision under test. unicorn is not in the project venv: run it from a venv that has it.

Cycles: ARM9E-S timings per instruction class (ARM946E-S TRM: data processing 1, load 1 plus a 1-cycle use interlock
counted on half of them, store 1, push/pop and ldm/stm one per register plus 1, taken branch 3, bl 4 for its two
halves, bx/blx 3, mul 3) with every access a TCM or cache hit. Misses to main RAM come on top (see the report).
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from unicorn import UC_ARCH_ARM, UC_HOOK_BLOCK, UC_HOOK_CODE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_SP)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import replay  # noqa: E402
import simbuild  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(tbpaths.ADV, 'src')

LO, HI = 0x01FF8000, 0x02400000
DTCM, DTCM_SIZE = 0x027E0000, 0x4000
IMAGE = 0x02380000
STOP = 0x0237FF00
MAIN_OBJ, BPP_OBJ, BPP_SIZE, PARTY_OBJ, ST_OBJ, PARAM_OBJ = 0x02100000, 0x02110000, 0x400, 0x02106000, 0x02120000, 0x02121000
POKECON1, POKECON0, FIELD0_OBJ, HEAP_LO = 0x02104000, 0x02104100, 0x02105000, 0x02300000
RNG_AFTER_MAX = 0x000F0000
CLIENT_BASE = (1, 13, 7, 19)

LDS = """SECTIONS {
  . = 0x%08X;
  .text : { KEEP(*(.text.entry)) *(.text .text.* .itcm.* .rodata .rodata.* .data .data.*) }
  .bss : { KEEP(*(.bss.debug)) *(.bss .bss.* COMMON .itcm_bss) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.ARM.attributes) *(.comment) *(.note*) }
}
""" % IMAGE


def build_image(out, layout=None):
    """(image bytes, bss start, bss end, symbols) of the AI linked at IMAGE with the DS build's flags."""
    os.makedirs(out, exist_ok=True)
    unit = os.path.join(out, 'ai_unit_ds.c')
    with open(unit, 'w') as f:
        f.write('#include "advai.c"\n#include "replace.c"\nint ai_serves(int client) { return 1; }\n')
    with open(os.path.join(out, 'thumb.ld'), 'w') as f:
        f.write(LDS)
    obj, elf, binf = (os.path.join(out, n) for n in ('ai.o', 'ai.elf', 'ai.bin'))
    subprocess.run(['arm-none-eabi-gcc'] + simbuild.builder_cflags(layout) + ['-I', SRC, '-c', unit, '-o', obj],
                   check=True)
    libgcc = subprocess.run(['arm-none-eabi-gcc', '-mthumb', '-mcpu=arm946e-s', '-print-libgcc-file-name'],
                            check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(['arm-none-eabi-ld', '-T', os.path.join(out, 'thumb.ld'), '-o', elf, obj, libgcc], check=True)
    subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', '-j', '.text', elf, binf], check=True)
    syms = {}
    for line in subprocess.run(['arm-none-eabi-nm', elf], check=True, capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    return open(binf, 'rb').read(), syms


def read_cases(path):
    cases, cur = {}, None
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == 'case':
            cur = {'id': p[1], 'doubles': int(p[2]), 'mons': {}, 'dmg': {}}
            cases[p[1]] = cur
        elif p[0] == 'mon':
            v = list(map(int, p[1:]))
            cur['mons'][(v[0], v[1])] = {'id': v[2], 'hp': v[5], 'moves': v[17:21], 'status': v[25],
                                         'unselectable': v[34], 'trapped': v[35]}
        elif p[0] == 'dmg':
            a, d, m, val = map(int, p[1:])
            cur['dmg'][(a, d, m)] = val
    return cases


class Engine:
    """The engine entry points as tools/hostai/engine.c answers them."""

    def __init__(self, mu, case, waza):
        self.mu, self.c, self.waza = mu, case, waza
        self.heap = HEAP_LO
        self.call = None
        self.sims = self.missing = self.ov11 = 0

    def u32(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def mon(self, b):
        if not BPP_OBJ <= b < BPP_OBJ + 48 * BPP_SIZE:
            return None
        k = (b - BPP_OBJ) // BPP_SIZE % 24
        return self.c['mons'].get((k // 6, k % 6))

    def client_of(self, i):
        return next((c for c in range(4) if CLIENT_BASE[c] <= i <= CLIENT_BASE[c] + 5), 0)

    def actives(self, cl):
        return 0 if cl > 1 else 2 if self.c['doubles'] else 1

    def handlers(self):
        u = self.u32
        nparty = lambda cl: sum(1 for (c, s) in self.c['mons'] if c == cl)

        def party(pc, cl, *_):
            return 0 if cl < 0 or cl > 1 or not nparty(cl) else PARTY_OBJ + 0x200 * (pc == POKECON1) + 0x40 * cl

        def member(p, i, *_):
            return u(p + 4 + 4 * i) if 0 <= i < u(p) else 0

        def pos_of(i, *_):
            c = self.client_of(i)
            s = i - CLIENT_BASE[c]
            return 5 if s >= self.actives(c) else c + 2 * s

        def unselectable(b, move, *_):
            m = self.mon(b)
            return next(((m['unselectable'] >> k) & 1 for k in range(4) if m and m['moves'][k] == move), 0)

        def sim(a, d, move, *_):
            self.sims += 1
            self.mu.mem_write(MAIN_OBJ + 0x24C, struct.pack('<I', RNG_AFTER_MAX))
            if (a, d, move) in self.c['dmg']:
                return self.c['dmg'][(a, d, move)]
            self.missing += 1
            return None      # the host's formula stand-in: taken from the host run (see run())

        def alloc(heap, size, *_):
            a = self.heap
            self.heap = (a + size + 31) & ~31
            return a

        def setter(kind):
            def f(p, r1=0, r2=0, *_):
                self.call = (kind, r1, r2)
                return 0
            return f

        def ov11(*_):
            self.ov11 += 1
            return 1
        return {
            0x02215170: lambda w, *_: POKECON1 if w else POKECON0,
            0x02230934: party,
            0x02215038: lambda p, *_: u(p),
            0x022151A0: member,
            0x022157D4: lambda i, *_: self.client_of(i),
            0x022287C8: lambda cl, *_: self.actives(cl),
            0x02228740: pos_of,
            0x02228838: lambda pos, *_: pos >> 1,
            0x02216C64: lambda b, *_: (self.mon(b) or {'status': 0})['status'],
            0x02216548: lambda b, *_: int(bool(self.mon(b) and self.mon(b)['hp'] > 0)),
            0x0201A274: lambda move, param, *_: self.waza(move, param),
            0x022157A0: lambda *_: FIELD0_OBJ,
            0x0222C304: unselectable,
            0x0222C958: lambda cw, b, *_: (self.mon(b) or {'trapped': 0})['trapped'],
            0x02223390: sim,
            0x0220091C: setter('none'),
            0x02200960: setter('move'),
            0x02200A30: setter('item'),
            0x022009AC: setter('switch'),
            0x021E4DA0: ov11,
            0x0201B2AC: alloc,
            0x0201B33C: lambda *_: 0,
        }


def waza_reader(rom):
    """WAZADATA_GetParam as gen_data.py decodes it."""
    import ndspy.rom
    from aidata import Data
    import gen_data
    d = Data(rom)
    pm = gen_data.param_map(ndspy.rom.NintendoDSRom.fromFile(rom))

    def waza(move, param):
        if not 0 <= move < len(d.moves) or not 0 <= param < len(pm):
            return 0
        r, (k, off, bit) = bytes(d.moves[move]).ljust(40, b'\0'), pm[param]
        if k == gen_data.P_U8:
            return r[off]
        if k == gen_data.P_S8:
            return struct.unpack_from('b', r, off)[0] & 0xFFFFFFFF
        if k == gen_data.P_U16:
            return struct.unpack_from('<H', r, off)[0]
        if k == gen_data.P_LO4:
            return r[off] & 15
        if k == gen_data.P_HI4:
            return r[off] >> 4
        if k == gen_data.P_BIT:
            return (struct.unpack_from('<I', r, off)[0] >> bit) & 1
        return 0
    return waza


BRANCH = {'b', 'beq', 'bne', 'bcs', 'bhs', 'bcc', 'blo', 'bmi', 'bpl', 'bvs', 'bvc', 'bhi', 'bls', 'bge', 'blt', 'bgt',
          'ble'}


def cycles_of(ins):
    """ARM9E-S cycles of one Thumb instruction with every access hitting (taken: branch taken)."""
    m = ins.mnemonic
    if m in ('push', 'pop', 'ldm', 'stm', 'ldmia', 'stmia'):
        n = ins.op_str.count(',') + 1
        return n + 1 + (2 if 'pc' in ins.op_str else 0)
    if m.startswith('ldr'):
        return 1.5
    if m.startswith('str'):
        return 1
    if m == 'bl':
        return 4
    if m in ('bx', 'blx'):
        return 3
    if m.startswith('mul'):
        return 3
    return 1


def run(args):
    cases = read_cases(args.cases)
    ids = args.ids.split(',') if args.ids else list(cases)[:args.max]
    out = tbpaths.run_dir('hostai', 'thumb')
    image, syms = build_image(out, args.layout)
    dump = tempfile.mkdtemp(prefix='hostai_dump_')      # 4 MB per case, removed at the end
    chosen = os.path.join(dump, 'cases.txt')
    with open(chosen, 'w') as f:
        keep = False
        for line in open(args.cases):
            if line.startswith('case '):
                keep = line.split()[1] in ids
            if keep:
                f.write(line)
    host = {}
    p = subprocess.run([os.path.join(replay.build(args.rom, layout=args.layout), 'replay'), '--dump', dump, chosen], check=True,
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        o = json.loads(line)
        host[o['id']] = o
    formula = {cid: {tuple(x[:3]): x[3] for x in host[cid]['stand_in']} for cid in host}
    waza = waza_reader(args.rom)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    lib_lo = min(v for k, v in syms.items() if k.startswith('__aeabi') or k.startswith('__gnu_thumb1') or k.startswith('__divsi3') or k.startswith('__udivsi3'))
    block_info = {}
    rows = []
    for cid in ids:
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.mem_map(LO, HI - LO)
        mu.mem_map(DTCM, DTCM_SIZE)
        mu.mem_write(LO, open(os.path.join(dump, cid + '.bin'), 'rb').read())
        mu.mem_write(IMAGE, image)
        eng = Engine(mu, cases[cid], waza)
        eng.formula = formula.get(cid, {})     # the host stand-in's answers to simulations the case lacks
        handlers = eng.handlers()
        for a in handlers:
            mu.mem_write(a, b'\x70\x47')            # bx lr: the hook below sets r0 first
        mu.mem_write(STOP, b'\xfe\xe7')

        def on_engine(uc, addr, size, _):
            f = handlers[addr]
            regs = [uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            sp = uc.reg_read(UC_ARM_REG_SP)
            regs.append(struct.unpack('<I', uc.mem_read(sp, 4))[0])
            v = f(*regs)
            if v is None:          # a simulation the case lacks: the host's formula stand-in answered it
                v = eng.formula.get(tuple(regs[:3]), 0)
            uc.reg_write(UC_ARM_REG_R0, v & 0xFFFFFFFF)
        for a in handlers:
            mu.hook_add(UC_HOOK_CODE, on_engine, begin=a, end=a)
        count = {'ai': 0, 'lib': 0, 'cyc': 0.0}

        def on_block(uc, addr, size, _):
            info = block_info.get(addr)
            if info is None:
                code = bytes(uc.mem_read(addr, size))
                ins = list(md.disasm(code, addr))
                cyc = sum(cycles_of(i) for i in ins[:-1])
                last = ins[-1] if ins else None
                # the block's last instruction is its branch: taken unless the next block follows it
                cyc_last = cycles_of(last) if last else 0
                if last and last.mnemonic in BRANCH:
                    cyc_last = 3
                info = (size // 2, cyc + cyc_last, addr >= lib_lo)
                block_info[addr] = info
            n, cyc, lib = info
            count['lib' if lib else 'ai'] += n
            count['cyc'] += cyc
        mu.hook_add(UC_HOOK_BLOCK, on_block, begin=IMAGE, end=IMAGE + len(image))
        polls, per_poll = 0, []
        while polls < 64:
            before = count['ai'] + count['lib']
            mu.reg_write(UC_ARM_REG_SP, DTCM + DTCM_SIZE - 0x100)
            mu.reg_write(UC_ARM_REG_LR, STOP | 1)
            mu.reg_write(UC_ARM_REG_R0, PARAM_OBJ)
            mu.reg_write(UC_ARM_REG_R1, ST_OBJ)
            mu.reg_write(UC_ARM_REG_R2, 1)
            mu.emu_start(syms['adv_entry'] | 1, STOP)
            polls += 1
            per_poll.append(count['ai'] + count['lib'] - before)
            if mu.reg_read(UC_ARM_REG_R0) == 1:
                break
        dbg = bytes(mu.mem_read(syms['ai_debug'], 256)).hex()
        same = dbg == host[cid]['debug']
        rows.append({'id': cid, 'same_debug_as_host': same, 'polls': polls, 'thumb': count['ai'] + count['lib'],
                     'thumb_lib': count['lib'], 'cycles_ideal': int(count['cyc']), 'per_poll': per_poll,
                     'host_arm64': host[cid]['ins'], 'host_poll_ins': host[cid]['poll_ins'], 'sims': eng.sims,
                     'call': eng.call})
        print(json.dumps(rows[-1]))
        sys.stdout.flush()
    shutil.rmtree(dump)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cases')
    ap.add_argument('--ids')
    ap.add_argument('--max', type=int, default=20)
    ap.add_argument('--rom', default=replay.DEFAULT_ROM)
    ap.add_argument('--layout', help="a builder layout's switches (en: the English build's)")
    a = ap.parse_args()
    rows = run(a)
    same = sum(r['same_debug_as_host'] for r in rows)
    print('\n%d decisions, %d with the same debug record as the host build' % (len(rows), same))


if __name__ == '__main__':
    main()
