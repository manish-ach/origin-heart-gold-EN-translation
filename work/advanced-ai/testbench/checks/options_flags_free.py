#!/usr/bin/env python3
"""Static check: nothing in a ROM's scripts or map objects uses event flags 0x2C2/0x2C3.

The TRAINER AI row stores its setting in flags 706 (0x2C2) and 707 (0x2C3). This
check re-proves, for any ROM built from the hack (the Chinese ROM, an English
build, an AI build), that the game itself never sets, clears or tests them:

1. No reachable SetFlag/ClearFlag/CheckFlag in a/0/1/2 names 706 or 707.
2. No map object in a/0/3/2 uses 706 or 707 as its hide flag (removing such an
   object would set the flag).
3. The commands that take their flag from a variable are exactly the seven
   reviewed sites, and scripts 145, 151 and 948 decode to the same instructions
   as the untouched Chinese hack, where research/options-trainer-ai.md bounds
   their flags to 800-1030, 627-636, and 653-663 or 2730-2740.
4. The hidden-item path that feeds script 145 is unchanged: the prep code bytes
   match the Chinese hack and the table indices give flags 800-1030 only.

No emulator. Run from the repository root:

  .venv/bin/python work/advanced-ai/testbench/checks/options_flags_free.py --rom work/build/advanced-ai/options/difficulty_dev.nds
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'work/tools'))
CN = ROOT / 'work/rom/origin_v4.0.3_cn.nds'
FLAGS = {706, 707}
IMMEDIATE = {30, 31, 32}                      # SetFlag, ClearFlag, CheckFlag
FROM_VAR = {33: 'SetFlagVar', 34: 'ClearFlagVar', 35: 'CheckFlagVar'}
REVIEWED = Counter({(145, 'SetFlagVar', 0x8006): 1, (151, 'SetFlagVar', 0x8005): 1, (151, 'ClearFlagVar', 0x8006): 1,
                    (948, 'SetFlagVar', 0x4001): 2, (948, 'ClearFlagVar', 0x4001): 1, (948, 'CheckFlagVar', 0x4001): 1})
HIDDEN_TABLE, HIDDEN_ROWS = 0x020F7194, 231   # {u16 item, u8 qty, u8, u16, u16 index}; flag = 800 + index
PREP = (0x0203F764, 0x0203FD50)               # script start (8000-8799 -> prep) through the prep and its pool


def load(path):
    import ndspy.narc
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(path)
    scripts = [bytes(f) for f in ndspy.narc.NARC(rom.getFileByName('a/0/1/2')).files]
    events = [bytes(f) for f in ndspy.narc.NARC(rom.getFileByName('a/0/3/2')).files]
    return scripts, events, bytes(rom.loadArm9().sections[0].data)


def decoded(scripts):
    from docs import romdata as R
    out = {}
    for i, data in enumerate(scripts):
        try:
            entries, ins = R.disasm(data)
        except Exception:
            continue
        if entries:
            out[i] = ins
    return out


def check(path):
    from docs import romdata as R
    scripts, events, main = load(path)
    code = decoded(scripts)
    immediate = [(f, pc) for f, ins in code.items() for pc, (op, a, _, _) in ins.items() if op in IMMEDIATE and a[0] in FLAGS]
    from_var = Counter((f, FROM_VAR[op], a[0]) for f, ins in code.items() for op, a, _, _ in ins.values() if op in FROM_VAR)
    objects = [(i, o['id']) for i, e in enumerate(events) for o in R.parse_events(e)['obj'] if o['flag'] in FLAGS]
    index = [struct.unpack_from('<H', main, HIDDEN_TABLE - 0x02000000 + 8 * r + 6)[0] for r in range(HIDDEN_ROWS)]
    return dict(scripts=len(scripts), decoded=len(code), instructions=sum(map(len, code.values())),
                objects=sum(len(R.parse_events(e)['obj']) for e in events),
                immediate_hits=immediate, object_hits=objects, from_var=sorted(from_var.items()),
                hidden_flags=[800 + min(index), 800 + max(index)], code=code, main=main)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--out', type=Path, default=ROOT / 'work/build/advanced-ai/options/flags-free.json')
    args = p.parse_args()
    target, reference = check(args.rom), check(CN)
    failures = []
    if target['immediate_hits']:
        failures.append(f"flag commands name 706/707: {target['immediate_hits']}")
    if target['object_hits']:
        failures.append(f"map objects hide with 706/707: {target['object_hits']}")
    if Counter(dict((k, v) for k, v in target['from_var'])) != REVIEWED:
        failures.append(f"flag-from-variable sites changed: {target['from_var']}")
    for f in (145, 151, 948):
        if target['code'].get(f) != reference['code'].get(f):
            failures.append(f'script {f} differs from the Chinese hack: re-review its flag bounds')
    start, end = (a - 0x02000000 for a in PREP)
    if target['main'][start:end] != reference['main'][start:end]:
        failures.append('hidden-item prep code differs from the Chinese hack')
    first, last = target['hidden_flags']
    if first <= max(FLAGS) and last >= min(FLAGS):
        failures.append(f"hidden-item flags {target['hidden_flags']} include 706/707")
    report = {k: v for k, v in target.items() if k not in ('code', 'main')}
    report.update(rom=str(args.rom.resolve()), status='failed' if failures else 'passed', failures=failures)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=list) + '\n')
    print(f"{report['status']}: {report['decoded']}/{report['scripts']} script files, {report['instructions']} instructions, "
          f"{report['objects']} map objects; hidden-item flags {report['hidden_flags']}; {args.out}")
    for line in failures:
        print('  ' + line)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
