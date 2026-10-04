"""Turn map coordinates into player directions, for writing the quest guide.

The guide must say "four steps east of the Pokémon Center door", not "≈1236,238". This tool lists
what a player can see on a map: doors (with readable room names from places.py), NPCs and signs
(with the first line they say), and item balls; and describes a coordinate relative to the
nearest of them.

    python3 work/tools/docs/landmarks.py list "Celadon City"          # every map in the location
    python3 work/tools/docs/landmarks.py list 380                     # one map (zone id)
    python3 work/tools/docs/landmarks.py near "Celadon City" 1236,238 # describe a spot
    python3 work/tools/docs/landmarks.py near 393 9,13

x grows to the east, z (the second number) grows to the south. One unit is one step.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_docs as G   # noqa: E402
import romdata as R    # noqa: E402

TALK = {44, 45, 46, 47}          # NonNPCMsg / NPCMsg (+Var)
GENDER_MSG = 'GenderMsgBox'


def first_line(ctx, zone, script_no):
    """First message a local script shows (the NPC's or sign's opening line)."""
    z = ctx.zones[zone]
    f = z['scripts_bank']
    d = ctx.S.get(f)
    if not d or not (1 <= script_no <= len(d['entries'])):
        return ''
    bank = z['msg_bank']
    try:
        texts = R.load_bank(bank)
    except Exception:
        return ''
    names = R.cmds()
    pc = d['entries'][script_no - 1]
    for _ in range(80):
        if pc not in d['ins']:
            break
        op, a, n, t = d['ins'][pc]
        nm = names.get(op, ('',))[0]
        if op in (44, 45) or nm in (GENDER_MSG, 'MsgBox', 'ShowMsg') or (nm.lower().endswith('msg') and a):
            s = texts.get(a[0], '')
            s = re.sub(r'\{[^}]*\}', ' ', s)
            return ' '.join(s.split())[:110]
        if op in (2, 27) or (op == 22):
            if op == 22 and t is not None:
                pc = t
                continue
            break
        pc = n
    return ''


def things(ctx, zid):
    """[(x, z, kind, label)] visible on one map."""
    z = ctx.zones[zid]
    ev = ctx.events.get(z['events_bank']) or {}
    out = []
    for w in ev.get('warp', []):
        dest = w['dest']
        lab = ctx.zname(dest) if 0 <= dest < len(ctx.zones) else 'somewhere'
        out.append((w['x'], w['z'], 'door', 'door to ' + lab))
    for o in ev.get('obj', []):
        s = o['script']
        if o['sprite'] == G.ITEM_BALL_SPRITE or 7000 <= s < 8000:
            out.append((o['x'], o['z'], 'item', 'item ball'))
        elif 3000 <= s < 7000:
            out.append((o['x'], o['z'], 'trainer', 'trainer #%d' % (s - 2999 if s < 5000 else s - 4999)))
        elif 0 < s < 1000:
            line = first_line(ctx, zid, s)
            hide = ' (appears/disappears with story flag %d)' % o['flag'] if o['flag'] else ''
            out.append((o['x'], o['z'], 'person', 'person%s: "%s"' % (hide, line) if line else 'person' + hide))
    for b in ev.get('bg', []):
        if 0 < b['script'] < 1000:
            line = first_line(ctx, zid, b['script'])
            out.append((b['x'], b['z'], 'sign', 'sign/object: "%s"' % line if line else 'sign/object'))
        elif 8000 <= b['script'] < 8800:
            out.append((b['x'], b['z'], 'hidden', 'hidden item'))
    return out


def resolve(ctx, where):
    if re.fullmatch(r'\d+', where):
        return [int(where)]
    zs = [z['zone_id'] for z in ctx.zones if ctx._zbase(z) == where]
    if not zs:
        zs = [z['zone_id'] for z in ctx.zones if ctx.zname(z['zone_id']) == where]
    if not zs:
        sys.exit('unknown location %r (use the in-game name, e.g. "Celadon City", or a zone id)' % where)
    return sorted(zs, key=ctx.zrank)


def steps(dx, dz):
    parts = []
    if dz:
        parts.append('%d step%s %s' % (abs(dz), 's' if abs(dz) > 1 else '', 'south' if dz > 0 else 'north'))
    if dx:
        parts.append('%d step%s %s' % (abs(dx), 's' if abs(dx) > 1 else '', 'east' if dx > 0 else 'west'))
    return ' and '.join(parts) or 'right at'


def describe(ctx, zid, x, z, n=4):
    ts = [t for t in things(ctx, zid) if (t[0], t[1]) != (x, z) or t[2] != 'person']
    same = [t for t in things(ctx, zid) if (t[0], t[1]) == (x, z)]
    ts.sort(key=lambda t: (abs(t[0] - x) + abs(t[1] - z), t[2] != 'door'))
    out = []
    for t in same:
        out.append('AT this spot: %s' % t[3])
    for t in ts[:n]:
        out.append('%s of the %s (%d,%d)' % (steps(x - t[0], z - t[1]), t[3], t[0], t[1]))
    return out


def in_bounds(ctx, zid, x, z):
    pts = [(t[0], t[1]) for t in things(ctx, zid)]
    if not pts:
        return False
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - 12 <= x <= max(xs) + 12 and min(zs) - 12 <= z <= max(zs) + 12


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    l = sub.add_parser('list')
    l.add_argument('where')
    nr = sub.add_parser('near')
    nr.add_argument('where')
    nr.add_argument('xz')
    a = ap.parse_args(argv)
    ctx = G.Ctx()
    zs = resolve(ctx, a.where)
    if a.cmd == 'list':
        for zid in zs:
            ts = things(ctx, zid)
            print('== %s (zone %d, %s)' % (ctx.zname(zid), zid, ctx.zones[zid]['map_type']))
            for x, z, kind, lab in sorted(ts, key=lambda t: (t[1], t[0])):
                print('  %5d,%-5d %-7s %s' % (x, z, kind, lab))
        return 0
    x, z = (int(v) for v in a.xz.replace('≈', '').split(','))
    hits = [zid for zid in zs if in_bounds(ctx, zid, x, z)] or zs
    for zid in hits:
        print('== %s (zone %d)' % (ctx.zname(zid), zid))
        for s in describe(ctx, zid, x, z):
            print('  ' + s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
