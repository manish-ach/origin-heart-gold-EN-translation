"""The lookahead's playouts (lapol.c, battle.c, move.c, damage.c, policy.c) compiled for the DS CPU with
builder/build.py's AI_CFLAGS (minus -Werror), linked with libgcc, and run in unicorn on root battles the host dumped
(sim cf la --dump). Counts Thumb instructions and ideal ARM9E-S cycles per decision the way hostai/thumbcount.py does,
and requires each decision's values and work counts to equal the host's. The simulator's data is the ROM's build's
(sim/simbuild.py: run it for --rom first).

  PY=<python with unicorn> lathumb.py DUMP [DUMP ...] [--rom ROM] [--max N] [--sizes]
"""
import argparse
import collections
import json
import os
import struct
import subprocess
import sys

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from unicorn import UC_ARCH_ARM, UC_HOOK_BLOCK, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(SIM), 'lib'))
import tbpaths  # noqa: E402
import simbuild  # noqa: E402
from thumbcount import BRANCH, cycles_of  # noqa: E402  the same cycle model

IMAGE = 0x02000000
ROOT, JOB, WORKB = 0x02380000, 0x02381000, 0x02382000
DTCM, DTCM_SIZE = 0x027E0000, 0x4000
STOP = 0x0237FF00
ROOT_BYTES = 868        # offsetof(Battle, verbose), the same on both ABIs (layout.h)
SOURCES = [os.path.join(SIM, f + '.c') for f in ('battle', 'move', 'damage', 'policy', 'lapol')] + \
    [os.path.join(HERE, 'ds_libc.c'), os.path.join(HERE, 'ds_entry.c')]
LDS = """SECTIONS {
  . = 0x%08X;
  .text : { KEEP(*(.text.entry)) *(.text .text.*) }
  .rodata : { *(.rodata .rodata.*) }
  .data : { *(.data .data.*) }
  .bss : { *(.bss .bss.* COMMON) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.ARM.attributes) *(.comment) *(.note*) }
}
""" % IMAGE


def build_image(out, rom):
    gen = simbuild.build_dir(rom)
    flags = [f for f in simbuild.builder_cflags() if f != '-Werror'] + [
        '-DSIM_DS', '-I', os.path.join(HERE, 'include'), '-I', HERE, '-I', SIM, '-I', gen, '-I',
        os.path.join(tbpaths.ADV, 'src')]
    os.makedirs(out, exist_ok=True)
    objs = []
    for src in SOURCES + [os.path.join(gen, 'simdata.c')]:
        obj = os.path.join(out, os.path.basename(src)[:-2] + '.o')
        subprocess.run(['arm-none-eabi-gcc'] + flags + ['-c', src, '-o', obj], check=True)
        objs.append(obj)
    with open(os.path.join(out, 'la.ld'), 'w') as f:
        f.write(LDS)
    libgcc = subprocess.run(['arm-none-eabi-gcc', '-mthumb', '-mcpu=arm946e-s', '-print-libgcc-file-name'],
                            check=True, capture_output=True, text=True).stdout.strip()
    elf, binf = os.path.join(out, 'la.elf'), os.path.join(out, 'la.bin')
    subprocess.run(['arm-none-eabi-ld', '-T', os.path.join(out, 'la.ld'), '--gc-sections', '-e', 'la_entry',
                    '-Map', os.path.join(out, 'la.map'), '-o', elf] + objs + [libgcc], check=True)
    subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', elf, binf], check=True)
    syms = []
    for line in subprocess.run(['arm-none-eabi-nm', '-S', '--defined-only', elf], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 4:
            syms.append((int(p[0], 16), int(p[1], 16), p[2], p[3]))
    return open(binf, 'rb').read(), syms, elf


def sizes(elf, syms, out):
    """code and data by origin: each defined symbol's size from nm -S, grouped by its object file in the map"""
    sec = subprocess.run(['arm-none-eabi-size', '-A', elf], check=True, capture_output=True, text=True).stdout
    owner = {}
    cur = None
    for line in open(os.path.join(out, 'la.map')):
        p = line.split()
        if len(p) >= 1 and p[0].startswith('.') and len(p) == 1:
            cur = p[0]
        elif len(p) >= 3 and p[0].startswith('.') and p[1].startswith('0x'):
            owner[p[0]] = os.path.basename(p[3]) if len(p) >= 4 else '?'
        elif len(p) >= 3 and cur and p[0].startswith('0x') and p[2].endswith('.o'):
            owner[cur] = os.path.basename(p[2])
            cur = None
    agg = collections.Counter()
    for addr, size, kind, name in syms:
        o = owner.get('.text.' + name) or owner.get('.rodata.' + name) or ('libgcc' if name.startswith('__') else '?')
        agg[(o, 'code' if kind in 'tT' else 'data')] += size
    return sec, agg


def read_dumps(paths, limit):
    rows = []
    for path in paths:
        n = 0
        for line in open(path):
            p = line.split()
            if not p or p[0] != 'dec':
                continue
            root = bytes.fromhex(p[4])
            nalt = int(p[5])
            alt = [(int(p[6 + 2 * i]), int(p[7 + 2 * i])) for i in range(nalt)]
            q = 6 + 2 * nalt
            cfg = list(map(int, p[q:q + 7]))
            w = list(map(int, p[q + 7:q + 7 + nalt]))
            turns, calls = int(p[q + 7 + nalt]), int(p[q + 8 + nalt])
            rows.append({'src': os.path.basename(path), 'm': p[1], 'turn': int(p[3]), 'root': root, 'alt': alt,
                         'cfg': cfg, 'w': w, 'turns': turns, 'calls': calls})
            n += 1
            if limit and n >= limit:
                break
    return rows


def run(args):
    out = tbpaths.run_dir('sim', 'la_ds')
    image, syms, elf = build_image(out, args.rom)
    if args.sizes:
        sec, agg = sizes(elf, syms, out)
        print(sec)
        for (o, k), v in sorted(agg.items()):
            print('%-14s %-5s %7d' % (o, k, v))
    funcs = sorted((a & ~1, a + s, n) for a, s, k, n in syms if k in 'tT' and s)
    starts = [f[0] for f in funcs]
    import bisect

    def func_of(addr):
        i = bisect.bisect_right(starts, addr) - 1
        return funcs[i][2] if i >= 0 and addr < funcs[i][1] else '?'
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    entry = next(a for a, s, k, n in syms if n == 'la_entry')
    block_info = {}
    results = []
    for d in read_dumps(args.dumps, args.max):
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.mem_map(0x02000000, 0x400000)
        mu.mem_map(DTCM, DTCM_SIZE)
        mu.mem_write(IMAGE, image)
        mu.mem_write(STOP, b'\xfe\xe7')
        root = d['root'] + b'\0' * (880 - len(d['root']))
        mu.mem_write(ROOT, root)
        job = struct.pack('<5iII', *d['cfg'])
        job += struct.pack('<i', len(d['alt']))
        job += b''.join(struct.pack('<BB', k, i) for k, i in d['alt']) + b'\0' * (2 * (12 - len(d['alt'])))
        job += b'\0' * (4 * 12 + 8)
        mu.mem_write(JOB, job)
        count = {'ins': 0, 'cyc': 0.0, 'minsp': DTCM + DTCM_SIZE}
        per_func = collections.Counter()

        def on_block(uc, addr, size, _):
            info = block_info.get(addr)
            if info is None:
                ins = list(md.disasm(bytes(uc.mem_read(addr, size)), addr))
                cyc = sum(cycles_of(i) for i in ins[:-1])
                last = ins[-1] if ins else None
                cyc_last = 3 if last and last.mnemonic in BRANCH else (cycles_of(last) if last else 0)
                info = (size // 2, cyc + cyc_last, func_of(addr))
                block_info[addr] = info
            n, cyc, fn = info
            count['ins'] += n
            count['cyc'] += cyc
            per_func[fn] += n
            sp = uc.reg_read(UC_ARM_REG_SP)
            if sp < count['minsp']:
                count['minsp'] = sp
        mu.hook_add(UC_HOOK_BLOCK, on_block, begin=IMAGE, end=IMAGE + len(image))
        mu.reg_write(UC_ARM_REG_SP, DTCM + DTCM_SIZE - 0x100)
        mu.reg_write(UC_ARM_REG_LR, STOP | 1)
        mu.reg_write(UC_ARM_REG_R0, ROOT)
        mu.reg_write(UC_ARM_REG_R1, JOB)
        mu.reg_write(UC_ARM_REG_R2, WORKB)
        mu.emu_start(entry | 1, STOP)
        raw = bytes(mu.mem_read(JOB, 28 + 4 + 24 + 48 + 8))
        nalt = len(d['alt'])
        w = list(struct.unpack_from('<%di' % nalt, raw, 56))
        turns, calls = struct.unpack_from('<II', raw, 56 + 48)
        same = w == d['w'] and turns == d['turns'] and calls == d['calls']
        r = {'src': d['src'], 'm': d['m'], 'turn': d['turn'], 'nalt': nalt, 'n': d['cfg'][0], 'depth': d['cfg'][1],
             'eval': d['cfg'][2], 'pol': d['cfg'][3], 'same_as_host': same, 'turns': turns, 'calls': calls,
             'thumb': count['ins'], 'cycles_ideal': int(count['cyc']),
             'stack': DTCM + DTCM_SIZE - 0x100 - count['minsp'],
             'top': per_func.most_common(12)}
        results.append(r)
        print(json.dumps(r))
        sys.stdout.flush()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dumps', nargs='+')
    ap.add_argument('--max', type=int, default=0, help='decisions per dump file')
    ap.add_argument('--sizes', action='store_true')
    ap.add_argument('--rom', default=simbuild.DEFAULT_ROM, help="the simulator data's ROM (simbuild.py)")
    a = ap.parse_args()
    rows = run(a)
    print('%d decisions, %d with the host\'s values and counts' % (len(rows), sum(r['same_as_host'] for r in rows)))


if __name__ == '__main__':
    main()
