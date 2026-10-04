"""Readable dump of one event-script file, with the English text of every message.

    python3 work/tools/docs/scriptdump.py 783              # Celadon City's map script
    python3 work/tools/docs/scriptdump.py 783 --grep 1179  # only lines mentioning 1179 (with context)
    python3 work/tools/docs/scriptdump.py 798 --bank 498   # force the message bank

Reads the untouched CN ROM through romdata (cached). The message bank is found from the zone
table (work/translate/bank_maps.json) or the std-script table. Labels are byte offsets ("L3103"),
the same numbers the guide's Technical source notes use. CheckFlag + GoToIf [0, …] jumps when the
flag is NOT set; [1, …] when it is (the compare codes are <, =, >, ≤, ≥, ≠ for 0–5).
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import romdata as R   # noqa: E402

MSG_OPS = re.compile(r'msg|message|menuitemadd|yesno', re.I)


def msg_bank(rom, f):
    zones = R.read_json(os.path.join(R.REPO, 'work', 'translate', 'bank_maps.json'))['_zones']
    for z in zones:
        if z['scripts_bank'] == f:
            return z['msg_bank'], [z['zone_id'] for z in zones if z['scripts_bank'] == f]
    for lo, sb, mb in rom.std_mapping():
        if sb == f:
            return mb, []
    return None, []


def dump(f, bank=None):
    rom = R.Rom()
    data = rom['scripts'][f]
    ent, ins = R.disasm(data)
    b, zones = msg_bank(rom, f)
    b = bank if bank is not None else b
    texts = R.load_bank(b) if b is not None else {}
    C = R.cmds()
    targets = {t for (_, _, _, t) in ins.values() if t is not None}
    entry = {e: i + 1 for i, e in enumerate(ent)}
    out = ['# script file %d · message bank %s · zones %s' % (f, b, zones)]
    for pc in sorted(ins):
        op, a, n, t = ins[pc]
        if pc in entry:
            out.append('')
            out.append('== script %d' % entry[pc])
        elif pc in targets:
            out.append('  L%d:' % pc)
        name = C[op][0]
        s = '    %5d %s %s' % (pc, name, a)
        if t is not None:
            s += ' -> L%d' % t
        if MSG_OPS.search(name):
            for x in a:
                if isinstance(x, int) and x in texts:
                    txt = re.sub(r'\{(NEWLINE|SCROLL|CLEAR)\}', ' ', texts[x])
                    s += '  «%s»' % ' '.join(txt.split())[:220]
                    break
        out.append(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file', type=int)
    ap.add_argument('--bank', type=int)
    ap.add_argument('--grep', help='only show lines matching this regex (plus 3 lines of context)')
    a = ap.parse_args(argv)
    lines = dump(a.file, a.bank)
    if a.grep:
        rx = re.compile(a.grep)
        keep = set()
        for i, ln in enumerate(lines):
            if rx.search(ln):
                keep.update(range(max(0, i - 3), min(len(lines), i + 4)))
        lines = [lines[i] if i - 1 in keep or i == min(keep) else '    …\n' + lines[i] for i in sorted(keep)] if keep else []
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
