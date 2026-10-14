#!/usr/bin/env python3
"""build - compile and link the advanced trainer AI into a payload.

    .venv/bin/python work/advanced-ai/builder/build.py --layout en [--out DIR] [--work DIR]
    .venv/bin/python work/advanced-ai/builder/build.py --layout es --es-tree DIR [--out DIR] [--work DIR]

Compiles src/advai.c, replace.c and lead.c as one unit, assembles the layout's asm sources, and links them with
src/link.ld into the memory regions of builder/layouts/<layout>.json. Ported from the Spanish translation's
tools/build.py (commit dc8577c: link_ai, resident_sections, slot_spill, largest_first, room_line).

Writes to --out (default work/build/advanced-ai/payload-<layout>/):
  slot.bin      the AI code after overlay 11's image in overlay 10 (never overlay 11's bytes)
  itcm.bin      the resident code of the itcm region
  main.bin      the resident code of the main region
  payload.json  regions, every placed symbol, the hooks and words, sha256 of every source and .bin
  (docs/build-contract.md has the schema.) --work keeps the objects, the ELF and the link map there.

--layout es reproduces the Spanish rc44 bytes (testbench/unit/test_golden.py). Its ITCM block starts with the
Spanish build's other asm sources, which it takes from --es-tree: a `git archive dc8577c work_es/tools/asm` of the
Spanish workspace, never copied here. --layout en is the English payload.

Needs arm-none-eabi-gcc 16.2.0 and GNU binutils 2.47 on PATH; any other version is refused, because another
compiler gives other bytes and the slot has under 3 KB to spare.
"""
import argparse
import collections
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
SRC = AI_DIR / 'src'
LAYOUTS = HERE / 'layouts'
REPO = AI_DIR.parents[1]
BUILD_DIR = REPO / 'work' / 'build' / 'advanced-ai'

ES_COMMIT = 'dc8577c'      # the Spanish workspace's rc44 commit, the source of src/ and of the es layout
GCC_VERSION = '16.2.0'
BINUTILS_VERSION = '2.47'
BINUTILS = ('as', 'ld', 'objcopy', 'objdump', 'readelf')
FORMAT = 1

AI_CFLAGS = ['-mthumb', '-mcpu=arm946e-s', '-Os', '-ffreestanding', '-fno-builtin', '-nostdlib', '-fno-common',
             '-ffunction-sections', '-fdata-sections', '-fno-strict-aliasing', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-parameter']
C_UNIT = ['advai.c', 'replace.c', 'lead.c']     # one translation unit (ai_unit.c includes them in this order)
C_HEADERS = ['engine.h', 'tune.h', 'ids.h']
ITCM_TOP = 0x02000000
SLOT_FIRST = ('.text.entry', '.text.write_action')   # link.ld puts these first in the slot, in this order
ROOM_REGION = {'.itcm': 'itcm_code', '.itcm_ai': 'itcm_code', '.itcm_spill': 'itcm_code', '.text': 'slot_code',
               '.bss': 'slot_bss', '.itcm_bss': 'itcm_bss', '.main': 'main_ai', '.main_spill': 'main_ai'}


class BuildError(Exception):
    pass


def require(cond, msg):
    if not cond:
        raise BuildError(msg)


def run(*args):
    """stdout of a tool, in the C locale so its output parses the same everywhere."""
    env = dict(os.environ, LC_ALL='C', LANG='C')
    proc = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env)
    if proc.returncode:
        raise BuildError('%s failed (%d):\n%s%s' % (Path(str(args[0])).name, proc.returncode, proc.stdout, proc.stderr))
    return proc.stdout


def tool(name):
    return 'arm-none-eabi-' + name


def toolchain_versions(gcc_version, binutils_banners):
    """{'gcc': ..., 'binutils': ...} from `gcc -dumpfullversion` and each binutils tool's first --version line, or
    BuildError naming what differs from the pin. A 2.47 release-branch build (2.47.YYYYMMDD) counts as 2.47."""
    gcc_version = gcc_version.strip()
    require(gcc_version == GCC_VERSION,
            'arm-none-eabi-gcc %s found; the AI is built only with %s (the payload must not change bytes)'
            % (gcc_version or '(no version)', GCC_VERSION))
    for name, banner in binutils_banners.items():
        m = re.search(r'\(GNU Binutils[^)]*\) (\d+\.\d+)(\.\d{8})?\s*$', banner.strip())
        require(m and m.group(1) == BINUTILS_VERSION,
                'arm-none-eabi-%s is "%s"; the AI is built only with GNU binutils %s'
                % (name, banner.strip(), BINUTILS_VERSION))
    return {'gcc': GCC_VERSION, 'binutils': BINUTILS_VERSION}


def toolchain():
    """The pinned versions, after checking every tool the build runs."""
    for name in ('gcc',) + BINUTILS:
        require(shutil.which(tool(name)), '%s not found on PATH (needs arm-none-eabi-gcc %s and GNU binutils %s)'
                % (tool(name), GCC_VERSION, BINUTILS_VERSION))
    banners = {name: run(tool(name), '--version').splitlines()[0] for name in BINUTILS}
    return toolchain_versions(run(tool('gcc'), '-dumpfullversion'), banners)


def hexa(n):
    return '0x%08X' % n


def num(s):
    return int(s, 0) if isinstance(s, str) else s


def load_layout(name):
    path = LAYOUTS / ('%s.json' % name)
    require(path.is_file(), 'no layout %s (builder/layouts/ has %s)'
            % (name, ', '.join(sorted(p.stem for p in LAYOUTS.glob('*.json')))))
    layout = json.loads(path.read_text())
    require(layout.get('name') == name, '%s: name is %r' % (path.name, layout.get('name')))
    r = {k: {f: num(v) for f, v in r.items()} for k, r in layout['regions'].items()}
    require(set(r) == {'slot', 'itcm', 'itcm_ram', 'main'}, '%s: regions %s' % (path.name, sorted(r)))
    ov = {k: num(v) if k != 'static_init' else [num(x) for x in v] for k, v in layout['overlay10'].items()}
    require(ov['ram'] + ov['copied_size'] + ov['copied_bss'] == r['slot']['origin'],
            '%s: the slot must start after overlay %d\'s image and bss' % (path.name, ov['copied']))
    require(r['itcm']['origin'] < r['itcm']['limit'] <= r['itcm_ram']['origin'] < r['itcm_ram']['limit'] <= ITCM_TOP,
            '%s: itcm and itcm_ram regions out of order' % path.name)
    layout['regions'], layout['overlay10'], layout['path'] = r, ov, path
    return layout


def source_path(entry, es_tree):
    """The file a layout's asm entry names: {"src": <file in src/>} or {"es": <path in the Spanish archive>}."""
    if 'src' in entry:
        return SRC / entry['src']
    require(es_tree, 'this layout takes %s from the Spanish workspace: pass --es-tree' % entry['es'])
    path = Path(es_tree) / entry['es']
    require(path.is_file(), '%s not found under --es-tree %s' % (entry['es'], es_tree))
    return path


def sources(layout, es_tree):
    """{name in payload.json: path} of every input that decides the bytes."""
    out = {'builder/build.py': HERE / 'build.py', 'builder/layouts/%s.json' % layout['name']: layout['path'],
           'src/link.ld': SRC / 'link.ld'}
    out.update({'src/' + n: SRC / n for n in C_UNIT + C_HEADERS})
    for entry in layout['asm']:
        out['src/' + entry['src'] if 'src' in entry else 'es:' + entry['es']] = source_path(entry, es_tree)
    return dict(sorted(out.items()))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def thumb_bl(src, dst):
    """The 4 bytes of a Thumb BL at `src` to `dst` (+-4 MB)."""
    off = dst - (src + 4)
    require(-0x400000 <= off < 0x400000 and not off & 1, 'BL %08X -> %08X out of range' % (src, dst))
    return struct.pack('<HH', 0xF000 | (off >> 12 & 0x7FF), 0xF800 | (off >> 1 & 0x7FF))


# ---- section analysis, ported from the Spanish build.py ----

def reached_sections(obj, root, resident=False):
    """The sections of the object file `obj` that its function `root` reaches through relocations, root's own first;
    `resident`: stop on a .data or .bss, which are in the battle slot."""
    dump = run(tool('objdump'), '-t', '-r', obj)
    section_of, relocs, cur = {}, collections.defaultdict(list), None
    for line in dump.splitlines():
        m = re.match(r'[0-9a-f]{8} .{7} (\S+)\t[0-9a-f]{8} (.+)$', line)
        if m:
            section_of[m.group(2)] = m.group(1)
            continue
        m = re.match(r'RELOCATION RECORDS FOR \[(.+)\]:$', line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r'[0-9a-f]{8} R_ARM_\S+\s+(\S+?)(?:[+-]0x[0-9a-f]+)?$', line)
        if m and cur:
            relocs[cur].append(m.group(1))
    out = [section_of[root]]
    todo = list(out)
    while todo:
        for sym in relocs[todo.pop()]:
            sec = section_of.get(sym)
            # *UND*: the asm sources and libgcc, in ITCM; .itcm.*: already in ITCM (the tuning table, .itcm.tune)
            if sec in (None, '*UND*', '.itcm_bss') or sec.startswith('.itcm.') or sec in out:
                continue
            if resident and not sec.startswith(('.text', '.rodata', '.main.text')):
                raise BuildError('%s reaches %s (%s), which is in the battle slot when it runs' % (root, sym, sec))
            out.append(sec)
            todo.append(sec)
    return out


def resident_sections(obj):
    """(ITCM, main RAM): the sections of `obj` that ai_replace or ai_lead reaches. ai_replace runs while the battle
    slot holds another overlay, and ai_lead before the battle loads one, so all of them must be resident. Those
    ai_replace and the selection AI (adv_entry) both run go to ITCM, after ai_replace's own; the rest go to main RAM
    (ai_lead's own first, link.ld). A section the source already names .main.* stays in main RAM."""
    itcm = reached_sections(obj, 'ai_replace', resident=True)
    selection = set(reached_sections(obj, 'adv_entry'))
    fast = [s for i, s in enumerate(itcm) if (not i or s in selection) and not s.startswith('.main.')]
    main = [s for s in itcm[1:] if s not in selection and not s.startswith('.main.')]
    return fast, main + [s for s in reached_sections(obj, 'ai_lead', resident=True) if s not in fast and s not in main
                         and not s.startswith('.main.')]


def map_entries(path):
    """[(output section, input section, size, object file's base name)] of every input section in the ld map file
    at `path`, in placement order (empty sections left out); ld's padding is input section '*fill*' of object ''."""
    out, cur, pending, started = [], None, None, False
    for line in Path(path).read_text().splitlines():
        if line.startswith('Linker script and memory map'):
            started = True
            continue
        if not started:
            continue
        m = re.match(r'(\.\S+)(\s+0x[0-9a-f]+\s+0x[0-9a-f]+.*)?$', line)
        if m:                                   # an output section starts at column 0
            cur, pending = m.group(1), None
            continue
        m = re.match(r' \*fill\*\s+0x[0-9a-f]+\s+0x([0-9a-f]+)', line)
        if m and cur:
            out.append((cur, '*fill*', int(m.group(1), 16), ''))
            continue
        m = re.match(r' (\.\S+)$', line)
        if m:                                   # a long input section name, its address and size on the next line
            pending = m.group(1)
            continue
        m = re.match(r' (\.\S+)\s+0x[0-9a-f]+\s+0x([0-9a-f]+)\s+(\S.*)$', line)
        if m:
            name, size, f = m.group(1), int(m.group(2), 16), m.group(3)
        else:
            m = re.match(r'\s+0x[0-9a-f]+\s+0x([0-9a-f]+)\s+(\S.*)$', line)
            if not (m and pending):
                pending = None
                continue
            name, size, f = pending, int(m.group(1), 16), m.group(2)
        pending = None
        if size:
            out.append((cur, name, size, os.path.basename(f)))
    return out


def map_sections(path, obj):
    """[(output section, input section, size)] of the object file named `obj` in the ld map file at `path`."""
    return [(o, n, size) for o, n, size, f in map_entries(path) if f == obj]


def slot_spill(sections, room, first=SLOT_FIRST):
    """Which of the AI's slot sections go to ITCM so the rest fits the `room` bytes of the slot. `sections`: [(name,
    size, alignment)] in the object file's order, which link.ld keeps after `first`. The pick is the set with the
    fewest bytes (a subset sum over sizes rounded up to their alignment) whose removal leaves a placement, simulated
    as ld lays it out, that fits; the estimate is raised by what the simulation finds over and the sum redone. Any
    section may move except `first` and .data. Returns the names, [] when everything fits."""
    info = {n: (size, align) for n, size, align in sections}

    def est(n):
        return -(-info[n][0] // info[n][1]) * info[n][1]

    def placed(keep):           # the slot's .text size with only `keep`, as link.ld lays it out
        pos = 0
        for n in [n for n in first if n in keep] + [n for n, _, _ in sections if n in keep and n not in first]:
            pos = -(-pos // info[n][1]) * info[n][1] + info[n][0]
        return -(-pos // 32) * 32
    if placed(info) <= room:
        return []
    movable = [n for n, _, _ in sections if n not in first and not n.startswith('.data')]
    need = sum(est(n) for n in info) - room
    while True:
        cap = need + max(est(n) for n in movable)
        parent = {0: None}      # reachable total -> (previous total, section index), the first way found
        for i, n in enumerate(movable):
            for t in sorted(parent, reverse=True):
                if t + est(n) <= cap and t + est(n) not in parent:
                    parent[t + est(n)] = (t, i)
        best = min((t for t in parent if t >= need), default=None)
        if best is None:
            raise BuildError('the AI code does not fit its room (%d bytes too many)' % need)
        names = []
        while parent[best]:
            best, i = parent[best]
            names.append(movable[i])
        over = placed(set(info) - set(names)) - room
        if over <= 0:
            return names
        need += over


def largest_first(sections, room):
    """Which of the ITCM sections `sections` ([(name, size, alignment)] in the object file's order) go to main RAM so
    the rest, laid out as ld lays it out, fits the `room` bytes of ITCM: the largest first. Moving a few large
    sections keeps the many small ones the race calls most in ITCM (Spanish rc28: 0.27% slower decisions on the DS,
    against 1.6-1.8% for the fewest bytes)."""
    def placed(gone):
        pos = 0
        for n, size, align in sections:
            if n not in gone:
                pos = -(-pos // align) * align + size
        return pos
    names = []
    for n, _, _ in sorted(sections, key=lambda h: -h[1]):
        if placed(names) <= room:
            break
        names.append(n)
    return names


# ---- the link ----

def link_ai(layout, es_tree, d):
    """Compile, place and link the AI in the directory `d`: the port of the Spanish link_ai. Returns
    (slot, itcm, main, symbols, room)."""
    r = layout['regions']
    itcm_at, itcm_ram, slot_at, main_at = (r['itcm']['origin'], r['itcm_ram']['origin'], r['slot']['origin'],
                                           r['main']['origin'])
    slot_end, main_room = r['slot']['limit'], r['main']['limit'] - r['main']['origin']
    for name, text in layout.get('as_includes', {}).items():
        (d / name).write_text('\n'.join(text) + '\n')
    as_defs = [x for k, v in layout.get('as_defsyms', {}).items() for x in ('--defsym', '%s=%s' % (k, v))]
    objs = []
    for entry in layout['asm']:               # *.s.o: link.ld puts them first in ITCM, in this order
        f = source_path(entry, es_tree)
        objs.append(d / (f.name + '.o'))
        run(tool('as'), '-I', d, *as_defs, '-o', objs[-1], f)
    unit, ai, elf, mapfile = d / 'ai_unit.c', d / 'ai.o', d / 'ai.elf', d / 'ai.map'
    unit.write_text(''.join('#include "%s"\n' % n for n in C_UNIT))
    run(tool('gcc'), *AI_CFLAGS, *layout.get('cflags', []), '-I', d, '-I', SRC, '-c', unit, '-o', ai)
    itcm, main = resident_sections(ai)
    run(tool('objcopy'), *['--rename-section=%s=.itcm%s' % (s, s) for s in itcm],
        *['--rename-section=%s=.main%s' % (s, s) for s in main], ai)
    libgcc = run(tool('gcc'), '-mthumb', '-mcpu=arm946e-s', '-print-libgcc-file-name').strip()
    ld_defs = [x for k, v in layout.get('ld_defsyms', {}).items() for x in ('--defsym', '%s=%s' % (k, v))]

    def link(slot):
        (d / 'ai_layout.ld').write_text(
            'MEMORY\n{\n    ITCM (rwx) : ORIGIN = 0x%08X, LENGTH = 0x%X\n    ITCM_RAM (rw) : ORIGIN = 0x%08X, LENGTH = 0x%X\n'
            '    SLOT (rwx) : ORIGIN = 0x%08X, LENGTH = 0x%X\n    MAIN (rwx) : ORIGIN = 0x%08X, LENGTH = 0x%X\n}\n'
            % (itcm_at, r['itcm']['limit'] - itcm_at, itcm_ram, ITCM_TOP - itcm_ram, slot_at, slot, main_at,
               main_room))
        run(tool('ld'), '-L', d, '-T', SRC / 'link.ld', '--gc-sections', '--enable-non-contiguous-regions',
            '--no-warn-rwx-segments', '-e', 'adv_entry', '-o', elf, *ld_defs, '-Map', mapfile, *objs, ai, libgcc)
        return elf_symbols(elf)

    def stubs(*outs):       # bytes of the interworking stubs ld adds (the picks do not see them) in those sections
        return sum(size for out, n, size in map_sections(mapfile, 'linker stubs') if out in outs)

    def obj_sections():     # [(name, size, alignment)] of ai.o
        return [(m.group(1), int(m.group(2), 16), 1 << int(m.group(3))) for m in
                re.finditer(r'^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+[0-9a-f]+\s+[0-9a-f]+\s+2\*\*(\d+)',
                            run(tool('objdump'), '-h', ai), re.M)]

    def elf_sections():     # {name: (address, size)} of the linked ELF
        return {m.group(1): (int(m.group(3), 16), int(m.group(2), 16)) for m in
                re.finditer(r'^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)', run(tool('objdump'), '-h', elf), re.M)}

    syms = link(slot_end - slot_at)
    slot_len = slot_end - slot_at - (syms['__bss_end'] - syms['__bss_start'])   # room for the bss after the code
    placed = {n for out, n, size in map_sections(mapfile, 'ai.o') if out in ('.text', '.itcm_spill', '.main_spill')}
    moved = slot_spill([h for h in obj_sections() if h[0] in placed],
                       slot_len - stubs('.text', '.itcm_spill', '.main_spill'))
    if moved:
        run(tool('objcopy'), *['--rename-section=%s=.itcm.spill%s' % (n, n) for n in moved], ai)
    syms = link(slot_len)
    spill = [n for out, n, size in map_sections(mapfile, 'ai.o') if out in ('.itcm_spill', '.main_spill')]
    require(not spill, 'slot_spill misjudged the slot: %s spilled' % spill)
    # ITCM's own pick: of the sections renamed .itcm.* above, the largest go to main RAM until the rest fits ITCM;
    # link.ld's fallback to main RAM must then stay unused. Moving a section can add an interworking stub in ITCM, and
    # a pick that fits by the estimate can still spill a few bytes: then pick again with less room.
    itcm_ai = ['.itcm' + s for s in itcm[1:]] + ['.itcm.spill' + n for n in moved]
    sections = [h for h in obj_sections() if h[0] in itcm_ai]
    room = r['itcm']['limit'] - elf_sections()['.itcm_ai'][0] - stubs('.itcm_ai', '.main')
    pristine = ai.read_bytes()

    def strays():
        return [n for out, n, size in map_sections(mapfile, 'ai.o') if out == '.main' and n.startswith('.itcm')]
    to_main = []
    for margin in range(0, 1025, 64):
        to_main = largest_first(sections, room - margin)
        if not to_main and not strays():
            break
        ai.write_bytes(pristine)
        if to_main:
            run(tool('objcopy'), *['--rename-section=%s=.main%s' % (n, n[len('.itcm'):]) for n in to_main], ai)
        try:
            syms = link(slot_len)
            if not strays() or margin >= 1024:
                break
        except BuildError:
            if margin >= 1024:
                raise
    require(not strays(), 'the ITCM pick misjudged ITCM: %s went to main RAM' % strays())
    heads = elf_sections()
    entries = map_entries(mapfile)
    run(tool('objcopy'), '-O', 'binary', '-j', '.itcm', '-j', '.itcm_ai', '-j', '.itcm_spill', elf, d / 'itcm.bin')
    run(tool('objcopy'), '-O', 'binary', '-j', '.text', elf, d / 'slot.bin')
    run(tool('objcopy'), '-O', 'binary', '-j', '.main', elf, d / 'main.bin')
    code, slot, main_code = ((d / n).read_bytes() for n in ('itcm.bin', 'slot.bin', 'main.bin'))

    extra = sorted(n for n in set(heads) - set(ROOM_REGION) if not n.startswith('.debug'))
    require(not extra, 'unexpected sections %s' % extra)
    require(heads['.itcm'][0] == itcm_at, '.itcm starts at %08X, not %08X' % (heads['.itcm'][0], itcm_at))
    require(heads['.text'][0] == slot_at == syms['adv_entry'] & ~1,
            'adv_entry must be first in the slot (aiselect.s jumps to %08X)' % slot_at)
    require(not main_code or heads['.main'][0] == main_at, '.main does not start at %08X' % main_at)
    require(slot_at + len(slot) == syms['__bss_start'] == syms['ai_debug'], 'the bss must start where the file ends')
    require(syms['__bss_end'] <= slot_end, 'overlay 10 ends at %08X, past %08X' % (syms['__bss_end'], slot_end))
    code, main_code = code + bytes(-len(code) % 4), main_code + bytes(-len(main_code) % 4)
    require(itcm_at + len(code) <= r['itcm']['limit'], 'ITCM code ends at %08X, past %08X'
            % (itcm_at + len(code), r['itcm']['limit']))
    require(main_at + len(main_code) <= r['main']['limit'], 'main RAM code ends at %08X, past %08X'
            % (main_at + len(main_code), r['main']['limit']))
    itcm_bss_at, itcm_bss = heads.get('.itcm_bss', (itcm_ram, 0))
    itcm_bss_end = int(re.search(r'ASSERT\(ADDR\(\.itcm_bss\) \+ SIZEOF\(\.itcm_bss\) <= (0x[0-9A-Fa-f]+)',
                                 (SRC / 'link.ld').read_text()).group(1), 16)
    require(itcm_bss_end == r['itcm_ram']['limit'], 'link.ld keeps .itcm_bss below %08X, the layout below %08X'
            % (itcm_bss_end, r['itcm_ram']['limit']))
    room = {
        'regions': {
            'slot_code': {'used': len(slot), 'free': slot_end - syms['__bss_end']},   # free: shared with slot_bss
            'slot_bss': {'used': syms['__bss_end'] - syms['__bss_start'], 'free': slot_end - syms['__bss_end']},
            'itcm_code': {'used': len(code), 'free': r['itcm']['limit'] - itcm_at - len(code)},
            'itcm_bss': {'start': itcm_bss_at, 'used': itcm_bss, 'free': itcm_bss_end - itcm_bss_at - itcm_bss,
                         'end': itcm_bss_end},
            'main_ai': {'used': len(main_code), 'free': main_room - len(main_code)}},
        'moved': {'slot_spill': moved, 'largest_first': to_main},
        'sections': [{'name': n, 'object': f, 'output': o, 'region': ROOM_REGION[o], 'size': size}
                     for o, n, size, f in entries if o in ROOM_REGION]}
    for o, (_, size) in heads.items():      # the map leaves out an output section's last alignment padding
        if o in ROOM_REGION:
            tail = size - sum(x['size'] for x in room['sections'] if x['output'] == o)
            require(0 <= tail < 32, 'the link map misses %d bytes of %s' % (tail, o))
    return slot, code, main_code, syms, room


def elf_symbols(elf):
    """{name: address} of every symbol the link placed (functions and objects, global and static, and the linker
    script's labels), Thumb functions with bit 0 set. Left out: mapping symbols ($t, $d), absolute ones, and ld's
    interworking veneers (__<function>_from_thumb, one per region that calls the function)."""
    out = {}
    for line in run(tool('readelf'), '-sW', elf).splitlines():
        f = line.split()
        if (len(f) < 8 or not f[0].endswith(':') or f[6] in ('UND', 'ABS', 'Ndx') or f[7].startswith('$')
                or re.match(r'__.+_from_(thumb|arm)$', f[7])):
            continue
        kind, bind, name, value = f[3], f[4], f[7], int(f[1], 16)
        if kind in ('FUNC', 'OBJECT') or (kind == 'NOTYPE' and bind == 'GLOBAL'):
            if out.get(name, value) != value:
                raise BuildError('two symbols named %s (%08X, %08X)' % (name, out[name], value))
            out[name] = value
    return out


def room_line(room):
    """One line of the AI's room: used and free bytes per region."""
    r = room['regions']
    return ('AI room: slot code %d + bss %d (%d free), ITCM code %d (%d free), .itcm_bss %d (%d free below %08X), '
            'main RAM AI code %d (%d free)' % (r['slot_code']['used'], r['slot_bss']['used'], r['slot_code']['free'],
                                               r['itcm_code']['used'], r['itcm_code']['free'], r['itcm_bss']['used'],
                                               r['itcm_bss']['free'], r['itcm_bss']['end'], r['main_ai']['used'],
                                               r['main_ai']['free']))


def build(layout_name, out, es_tree=None, work=None):
    """Build the layout into the directory `out` (payload.json and the three .bin files). Returns the payload."""
    layout = load_layout(layout_name)
    versions = toolchain()
    srcs = sources(layout, es_tree)
    if work:
        d = Path(work)
        d.mkdir(parents=True, exist_ok=True)
        slot, itcm, main, syms, room = link_ai(layout, es_tree, d.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='advai-') as t:
            slot, itcm, main, syms, room = link_ai(layout, es_tree, Path(t))
    r, ov = layout['regions'], layout['overlay10']
    bins = {'slot.bin': slot, 'itcm.bin': itcm, 'main.bin': main}
    itcm_bss = 0
    if r['itcm'].get('zero_work_ram'):
        # the itcm section's bss runs from the end of its code through .itcm_bss, so the boot's autoload zeroes the
        # AI's work RAM on every boot (a DS leaves ITCM as it was; an emulator zeroes it at power-on). The test
        # records from the itcm_ram limit up stay outside it.
        w = room['regions']['itcm_bss']
        itcm_bss = w['start'] + w['used'] - (r['itcm']['origin'] + len(itcm))
        require(itcm_bss >= 0 and not itcm_bss % 4 and w['start'] + w['used'] <= r['itcm_ram']['limit'],
                'the itcm section\'s bss (%08X+%X) must end on a word at or below %08X'
                % (r['itcm']['origin'] + len(itcm), itcm_bss, r['itcm_ram']['limit']))
    hooks = []
    for h in layout['hooks']:
        require(h['target'] in syms, 'hook target %s is not a symbol of the link' % h['target'])
        at, dst = num(h['address']), syms[h['target']]
        require(dst & 1, 'hook target %s is not a Thumb function' % h['target'])
        hooks.append(dict(h, after=thumb_bl(at, dst & ~1).hex()))
    for w in layout['words']:
        # `before` is the 4 bytes the word must hold, or "itcm_end": it must equal the end of the input's ITCM block
        # (which differs per locale) and be at most `before_max`, the itcm region's origin
        require(re.fullmatch(r'[0-9a-f]{8}', w['before']) or (
                w['before'] == 'itcm_end' and num(w.get('before_max', '0')) == r['itcm']['origin']),
                'word %s: before must be 8 hex digits, or itcm_end with before_max %s' % (w['address'],
                                                                                          hexa(r['itcm']['origin'])))
    payload = {
        'format': FORMAT,
        'layout': layout['name'],
        'toolchain': versions,
        'sources': {n: sha256(p.read_bytes()) for n, p in srcs.items()},
        'regions': {
            'slot': {'ram': hexa(r['slot']['origin']), 'file': 'slot.bin', 'size': len(slot),
                     'bss': syms['__bss_end'] - syms['__bss_start'], 'limit': hexa(r['slot']['limit'])},
            'itcm': {'ram': hexa(r['itcm']['origin']), 'file': 'itcm.bin', 'size': len(itcm), 'bss': itcm_bss,
                     'limit': hexa(r['itcm']['limit'])},
            'itcm_ram': {'ram': hexa(r['itcm_ram']['origin']), 'size': room['regions']['itcm_bss']['used'],
                         'limit': hexa(r['itcm_ram']['limit'])},
            'main': {'ram': hexa(r['main']['origin']), 'file': 'main.bin', 'size': len(main), 'bss': 0,
                     'limit': hexa(r['main']['limit'])},
        },
        'overlay10': {'base_from': 'overlay %d of the input ROM' % ov['copied'], 'ram': hexa(ov['ram']),
                      'copied': {'overlay': ov['copied'], 'size': '0x%X' % ov['copied_size'],
                                 'bss': '0x%X' % ov['copied_bss']},
                      'bss': '0x%X' % (syms['__bss_end'] - syms['__bss_start']),
                      'static_init': [hexa(x) for x in ov['static_init']]},
        'symbols': {n: hexa(a) for n, a in sorted(syms.items(), key=lambda s: (s[1], s[0]))},
        'hooks': hooks,
        'words': layout['words'],
        'room': {'regions': room['regions'], 'moved': room['moved']},
        'files': {n: sha256(b) for n, b in bins.items()},
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for n, b in bins.items():
        write_atomic(out / n, b)
    write_atomic(out / 'payload.json', (json.dumps(payload, indent=1) + '\n').encode())
    return payload, room


def write_atomic(path, data):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def es_archive(repo, dest, paths=('work_es/tools/asm',), commit=ES_COMMIT):
    """Extract `paths` of the Spanish workspace repository `repo` at `commit` into the directory `dest` (git
    archive, never its working tree). Returns `dest`."""
    proc = subprocess.run(['git', '-C', str(repo), 'archive', commit, *paths], capture_output=True)
    if proc.returncode:
        raise BuildError('git archive %s in %s failed: %s' % (commit, repo, proc.stderr.decode(errors='replace')))
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(dest, filter='data')
    return Path(dest)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--layout', required=True, help='a layout in builder/layouts/ (es or en)')
    ap.add_argument('--out', help='output directory (default work/build/advanced-ai/payload-<layout>/)')
    es = ap.add_mutually_exclusive_group()
    es.add_argument('--es-tree', help='root of a `git archive %s work_es/tools/asm` of the Spanish workspace '
                                      '(the es layout only)' % ES_COMMIT)
    es.add_argument('--es-repo', help='the Spanish workspace repository: archive its asm sources at %s into a '
                                      'temporary directory (the es layout only)' % ES_COMMIT)
    ap.add_argument('--work', help='keep the objects, the ELF and the link map in this directory')
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else BUILD_DIR / ('payload-' + args.layout)
    try:
        with tempfile.TemporaryDirectory(prefix='advai-es-') as t:
            es_tree = es_archive(args.es_repo, t) if args.es_repo else args.es_tree
            payload, room = build(args.layout, out, es_tree, args.work)
    except BuildError as e:
        sys.exit('build.py: %s' % e)
    print(room_line(room))
    moved = room['moved']
    if moved['slot_spill'] or moved['largest_first']:
        size = {x['name']: x['size'] for x in room['sections']}
        print('moved: slot to ITCM %s; ITCM to main RAM %d bytes: %s' % (
            moved['slot_spill'] or 'none', sum(size.get('.main' + n[len('.itcm'):], 0) for n in moved['largest_first']),
            ', '.join(moved['largest_first']) or 'none'))
    print('wrote %s (%s)' % (out, ', '.join('%s %s' % (n, s[:12]) for n, s in payload['files'].items())))


if __name__ == '__main__':
    main()
