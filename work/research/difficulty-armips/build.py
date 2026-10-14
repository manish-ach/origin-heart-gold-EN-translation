#!/usr/bin/env python3
"""Research-only opt-in build. Invoke from repository root; no downloads."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'work/research/difficulty-armips'
BASE, LIMIT = 0x023DC000, 0x023E0000
ITEM_STUB_BYTES = 336
CLANG = '/usr/bin/clang'
LLD = str(Path.home() / '.rustup/toolchains/stable-aarch64-apple-darwin/lib/rustlib/aarch64-apple-darwin/bin/gcc-ld/ld.lld')
ARMIPS = str(Path.home() / 'Developer/armips/build/armips')
MODULES = ('policy', 'settings', 'growth', 'items', 'options', 'caps', 'runtime')
FLAGS = ['--target=arm-none-eabi', '-mcpu=arm946e-s', '-mthumb', '-Os',
         '-ffreestanding', '-fno-builtin', '-fno-unwind-tables',
         '-fno-asynchronous-unwind-tables', '-fstack-usage', '-Wall', '-Wextra', '-Werror']
# Opt-in development mode (research/dev-tools-mode.md): DIFFICULTY_DEV_TOOLS=1
# records the local tools' pins instead of comparing them. Release is the default.
DEV_ENV = 'DIFFICULTY_DEV_TOOLS'
DEV_LABEL = 'development build, local tools, not a release candidate'


def dev_tools():
    return os.environ.get(DEV_ENV) == '1'


def tool_mode():
    return 'development' if dev_tools() else 'release'


# A development candidate never shares the release candidate's folder.
OUTPUT = ROOT / ('work/build/difficulty-v2/integration-impl-dev' if dev_tools() else
                 'work/build/difficulty-v2/integration-impl')
RECEIPT = OUTPUT / 'receipt.json'


def tool_env(tool):
    """Development only: a current rustup rust-lld loads libLLVM.dylib from the
    toolchain's lib directory, which its rpath does not name."""
    if dev_tools() and str(tool) == LLD:
        return dict(os.environ, DYLD_FALLBACK_LIBRARY_PATH=str(Path(LLD).parents[4]))
    return None


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    p = Path(path)
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}


def run(args, stage, name):
    env = tool_env(args[0])
    result = subprocess.run(list(map(str, args)), cwd=ROOT, text=True, capture_output=True, env=env)
    (stage / (name + '.log')).write_text(result.stdout + result.stderr)
    require(result.returncode == 0, f'{name} failed: {result.stdout}{result.stderr}')
    record = {'argv': list(map(str, args)), 'returncode': result.returncode}
    if env:
        record['env'] = {'DYLD_FALLBACK_LIBRARY_PATH': env['DYLD_FALLBACK_LIBRARY_PATH']}
    return record


def read_elf(path):
    """Read actual linked ELF32, validate every alloc section/symbol/relocation."""
    b = path.read_bytes()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', b)
    require(b[:7] == b'\x7fELF\x01\x01\x01' and h[1:3] == (2, 40), 'not linked ARM ELF32 LE')
    headers = [struct.unpack_from('<10I', b, h[6]+i*h[11]) for i in range(h[12])]
    def content(s):
        return b[s[4]:s[4]+s[5]]
    names = content(headers[h[13]])
    def string(data, off):
        return data[off:data.index(b'\0', off)].decode()
    sections, symbols, details = [], {}, []
    alloc = {}
    for i, s in enumerate(headers):
        name = string(names, s[0])
        require(s[1] not in (4, 9) or not s[5], f'unresolved relocation section {name}')
        if s[2] & 2:
            require(name in ('.text', '.rodata', '.data', '.bss'), f'unexpected alloc section {name}')
            require(BASE <= s[3] <= s[3]+s[5] <= LIMIT, f'ELF section bounds {name}')
            require(s[1] in (1, 8), f'ELF section type {name}')
            alloc[i] = s
            sections.append({'name': name, 'address': s[3], 'size': s[5], 'type': s[1], 'flags': s[2]})
    for s in headers:
        if s[1] != 2:
            continue
        strings = content(headers[s[6]])
        for off in range(s[4], s[4]+s[5], s[9]):
            n, value, size, info, other, idx = struct.unpack_from('<IIIBBH', b, off)
            if not n:
                continue
            name = string(strings, n)
            require(idx != 0, f'undefined ELF symbol {name}')
            typ = info & 15
            if idx in alloc:
                sec = alloc[idx]
                addr = value & ~1 if typ == 2 else value
                if typ == 0 and name.startswith('__'):
                    require(BASE <= addr <= LIMIT and size == 0, f'linker boundary {name}')
                else:
                    require(sec[3] <= addr <= addr+size <= sec[3]+sec[5], f'symbol out of section {name}')
                if typ == 2:
                    require(value & 1 and sec[2] & 4, f'non-Thumb/non-executable function {name}')
                details.append({'name': name, 'value': value, 'size': size, 'type': typ, 'section': idx})
            elif typ in (1, 2):
                raise ValueError(f'nonresident ELF object/function {name}')
            symbols[name] = value
    end = symbols['__c_end']
    require(BASE < end <= LIMIT, 'C extent')
    image = bytearray(end-BASE)
    zeros = []
    last = BASE
    for sec in sorted(sections, key=lambda s: s['address']):
        start, size = sec['address'], sec['size']
        require(start >= last or not size, 'overlapping C sections')
        last = start+size
        raw = next(s for s in headers if s[3] == start and s[5] == size and s[2] & 2)
        if sec['type'] == 8:
            zeros.append([start, start+size])
        else:
            image[start-BASE:start-BASE+size] = content(raw)
    require(symbols['__bss_start'] <= symbols['__bss_end'] == end, 'BSS bounds')
    for start, stop in zeros:
        require(not any(image[start-BASE:stop-BASE]), 'interior BSS not zero')
    return bytes(image), symbols, {'sections': sections, 'symbols': details, 'zero_ranges': zeros,
                                  'initialized_end': symbols['__initialized_end'], 'c_end': end,
                                  'entry': h[4], 'undefined_symbols': [], 'relocations': []}


def asm_symbols(path):
    result = {}
    for line in path.read_text().splitlines():
        words = line.split()
        if len(words) == 2:
            try:
                value = int(words[0], 16)
            except ValueError:
                continue
            result[words[1].lower()] = value
    return result


def build(stage):
    commands = []
    for name in MODULES:
        commands.append(run([CLANG, *FLAGS, '-c', SOURCE/'native'/f'{name}.c',
                             '-o', stage/f'{name}.o'], stage, name))
    commands.append(run([LLD, '--no-undefined', '--fatal-warnings', '-T', SOURCE/'native/link.ld',
                         '-Map='+str(stage/'resident.map'), '-o', stage/'resident.elf',
                         *[stage/f'{n}.o' for n in MODULES]], stage, 'link'))
    image, symbols, report = read_elf(stage/'resident.elf')
    (stage/'c-symbols.inc').write_text(''.join(f'.definelabel {n}, 0x{v:08X}\n'
        for n, v in sorted(symbols.items()) if n.startswith('dg_')))
    item_base = BASE+len(image)
    options_base = item_base+ITEM_STUB_BYTES
    runtime_base = options_base+72
    require(runtime_base+176 <= LIMIT, 'combined resident exceeds 16KiB reservation')
    for filename, size in [('options-stubs.bin', 72), ('runtime-stubs.bin', 176)]:
        (stage/filename).write_bytes(bytes(size))
    definitions = ['-definelabel', 'ITEM_STUB_BASE', hex(item_base),
                   '-definelabel', 'DG_ITEMS_PATCH_HOOKS', '1']
    for n in ('dg_bag_item_attr', 'dg_bag_remembered', 'dg_bag_accept', 'dg_bag_commit_item', 'dg_bag_commit_target', 'dg_bag_effect_attr'):
        definitions += ['-definelabel', n, hex(symbols[n])]
    for filename, defs in [('native/items.asm', definitions),
                           ('native/options.asm', ['-definelabel','DG_OPTIONS_STUB_BASE',hex(options_base)]),
                           ('native/runtime.asm', ['-definelabel','DG_RUNTIME_STUB_BASE',hex(runtime_base)]),
                           ('compatibility.asm', [])]:
        # armips -root changes resolution of staged file names, not process cwd.
        name = Path(filename).stem
        staged_source = stage/Path(filename).name
        staged_source.write_bytes((SOURCE/filename).read_bytes())
        commands.append(run([ARMIPS, staged_source, '-root', stage, '-sym', stage/f'{name}.sym', *defs], stage, 'asm-'+name))
    emitted = {}
    for name in ('items', 'options', 'runtime'):
        emitted.update(asm_symbols(stage/f'{name}.sym'))
    spans = [('item_stubs.bin', item_base, ITEM_STUB_BYTES, 'dg_itemstubsstart', 'dg_itemstubsend'),
             ('options-stubs.bin', options_base, 72, 'dg_optionsstubsstart', 'dg_optionsstubsend'),
             ('runtime-stubs.bin', runtime_base, 176, 'dg_runtimestubsstart', 'dg_runtimestubsend')]
    for filename, base, size, start, end in spans:
        raw = (stage/filename).read_bytes()
        require(len(raw) == size and emitted[start] == base and emitted[end] == base+size,
                f'assembled stub extent mismatch {filename}')
        image += raw
    # Autoload copies complete code, materialized interior BSS, then stubs.
    (stage/'resident.bin').write_bytes(image)
    report.update({'reservation': [BASE, LIMIT], 'resident_end': BASE+len(image),
                   'resident_bytes': len(image), 'tail_bss': 0,
                   'stub_spans': [{'file': f, 'start': b, 'end': b+s} for f,b,s,_,_ in spans],
                   'asm_symbols': emitted, 'elf_labels': symbols, 'commands': commands})
    return image, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-difficulty', action='store_true', required=True)
    parser.add_argument('--input', type=Path, required=True, help='compatible completed English ROM (read only)')
    args = parser.parse_args()
    require(Path.cwd().resolve() == ROOT, 'run from repository root')
    import install
    if dev_tools():
        try:
            print(f'{DEV_LABEL.upper()} ({DEV_ENV}=1): tool pins are recorded, not compared.', file=sys.stderr)
        except OSError:
            pass
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='run-', dir=OUTPUT))
    try:
        summary = install.execute(args.input.resolve(), stage)
    except Exception as exc:
        (stage/'FAILED.txt').write_text(str(exc)+'\n')
        outcome = 'RECOVERY REQUIRED' if isinstance(exc, install.PublicationRecoveryRequired) else 'REJECTED'
        print(f'{outcome}: {exc}\nArtifacts: {stage}', file=sys.stderr)
        return 1
    # Publication has committed. A closed output stream cannot turn it into a
    # claimed rejected build or undo the coherent new pair.
    try:
        print(json.dumps(summary, indent=2))
    except OSError:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
