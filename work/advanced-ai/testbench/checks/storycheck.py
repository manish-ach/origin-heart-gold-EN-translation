"""Story battles with the advanced AI on: each scene played with the AI off (the control) and on, from the same save.

  .venv/bin/python work/advanced-ai/testbench/checks/storycheck.py --rom ROM --payload P [CASE ...]
                                                                   [--setting all|important]

Ported from the Spanish workspace's tools/storycheck.py (dc8577c), its trainer-battle cases run with --ai. The
Spanish tool checked its own field script fixes (the white-out after a lost scripted battle, the Route 3 scene) with
the AI's setting written into the battery save; this check asks one question of each scene: does the advanced AI
change how it ends? Each case writes a battery save at its story point (from the Spanish party_nostatus test save,
lib/saves.py), boots it (lib/boot.txt), writes the AI setting into the save in RAM (lib/emu.py set_ai_setting: 'off'
for the control, then --setting), plays the scene and reads the trace and the save block in RAM. The map a save starts
on is empty (savetool.Save.place), so a case either takes a door into the scene's map (a map entered by a door loads
its own people) or writes the one person it needs into the saved map objects.

  willy_loss     Rock Tunnel (map 342): lose to Youngster Willy (script file 129 entry 18) with a level-5 lead at
                 1 HP and the other five fainted. The scene ends by whiting out home (Mom's 38:40).
  giovanni_loss  Mt. Silver (map 65): lose Giovanni's double battle (file 844 entry 3, trigger (23, 139) with var
                 0x40A2 = 8) with two level-5 Pokemon at 1 HP. The test's ROM copy turns the house TV (map 63, file
                 842 @0x2BA) into a Warp to (24, 139), so the player arrives at the terrain's height. Whites out home.
  route3_actors  Route 3 (map 11) from the Pokemon Center door (map 511): the coord scene of file 175 (1149, 119-123)
                 with var 0x4086 = 0 and flag 0x517 still set, a level-100 lead: two trainer battles, one a full team.
                 The scene runs to its end (var 0x4086 = 1).

When a trainer battle starts (SetupAndStartTrainerBattle), every party Pokemon's current HP is set to at most its
maximum: the Spanish test save's edited stats leave 998/297 after a battle, which the AI's range check rejects
(FB_OPP), so it would hand every turn to overlay 11 and the AI-on run would test nothing. The AI-on run must show the
advanced AI deciding (an action setter called from its slot code with overlay 10 loaded) and no fallback code other
than 0 (3 doubles, 6 no usable option: by design) in the trainer side's debug record (the payload's ai_debug).

A case passes when the AI-on run meets the case's end, the AI served it, and it has no assert (other than the
inherited ones), NULL allocation, freeze or text outside its window that the control does not have. A case whose control fails too is
reported as INHERITED (the build without the AI ends that way: the Spanish build had fixes for these scenes that this
project may lack) and passes when the AI-on run fails the same way. Results: RUNS/storycheck/<ROM name>/. Exit status 1 when a
case fails.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'storycheck')
DEX_MAGIC, DEX_AT = 0xBEEFCAFE, 0x13A8          # the general save block in RAM is found by the Pokedex magic
VAR_4086 = 0x118C - 0x2E0 + 2 * (0x4086 - 0x4000)   # Route 3's scene: 0 pending, 1 done (savetool.VARS)
# 'clipped' (text drawn past its window's size inside its buffer, lib/emu.py) is the ROM's text fit, the same with the
# AI on or off: kept apart as a note
FAILURES = ('assert', 'null', 'freeze', 'outside', 'goto_fail', 'until_fail')
# the boot assert every build has; 0203FA28: WildBattle's level read as a variable (the Chinese too); 021F54D4: the
# house's field screens (the Chinese too); 0206143C: the letter scene's movements (the Chinese too)
INHERITED = {'0200B1BC', '0203FA28', '021F54D4', '0206143C'}
HOME = (38, 40)                                 # Mom after a white-out
TRAINER_BATTLE = 0x02050768                     # SetupAndStartTrainerBattle
MAIN_PTR, SLOT_AT = 0x02255BAC, 0x26C           # the battle's main struct; its slot overlay id
SETTERS = (0x02200960, 0x02200A30, 0x022009AC, 0x0220091C)    # move, item, switch, none
DEBUG_MAGIC = 0x49414441                        # advai.c Debug: magic u32, version u16, polls u8, fallback u8
PARTY, PARTY_COUNT, MON_SIZE = 0x98, 0x94, 236  # in the general save block (lib/savetool.py)
# the TV's script (PlaySE, LockAll, NPCMsg, ...) -> Warp map 65 (24, 139) facing left, ReleaseAll, End
TV_WARP = (842, 0x2BA, '4900dc0560002d002332003500610002', 'b0004100000018008b00020061000200')
CASES = {
    'willy_loss': {'place': (342, 43, 97, 'down'), 'person': (17, 317, 18, 43, 98), 'walk': ['face DOWN']},
    'giovanni_loss': {'able': 2, 'walk': ['goto 6 4', 'face UP', 'press A', 'wait 200', 'face LEFT', 'walk LEFT 1']},
    'route3_actors': {'place': (511, 8, 18, 'down'),     # out of the door, so map 11 loads its own objects
                      'walk': ['walk DOWN 1', 'wait 120', 'walk DOWN 1', 'goto 1167 120'] + ['walk LEFT 1'] * 18},
}


def block(r):
    m = r.emu.memory.unsigned
    for at in range(0x02200000, 0x02300000, 4):
        if m.read_long(at + DEX_AT) == DEX_MAGIC and m.read_long(at + 0x90) == 6:   # the party header: not a code literal
            return at
    return None


def legal_hp(r):
    """Every party Pokemon's current HP at most its maximum, in the save block in RAM: [(slot, was, max)] fixed."""
    import struct as st

    from savetool import Mon
    at = block(r)
    if at is None:
        return None
    m = r.emu.memory.unsigned
    fixed = []
    for k in range(min(6, m.read_long(at + PARTY_COUNT))):
        a = at + PARTY + MON_SIZE * k
        mon = Mon(bytes(m.read_byte(a + i) for i in range(MON_SIZE)))
        mon.party = bytearray(mon.party)
        cur, mx = st.unpack_from('<HH', mon.party, 6)
        if cur > mx:
            st.pack_into('<H', mon.party, 6, mx)
            data = mon.encode()
            for i in range(0, MON_SIZE, 4):
                r.emu.memory.write_long(a + i, st.unpack_from('<I', data, i)[0])
            fixed.append((k, cur, mx))
    return fixed


def watch_ai(r, ai):
    """Record into `ai` the advanced AI's actions (a setter called from its slot code with overlay 10 loaded) and the
    trainer side's fallback codes, from the payload's addresses."""
    lay = payload.load()
    lo, hi = lay.adv_code
    dbg = lay.debug
    m = r.emu.memory.unsigned
    reg = r.emu.memory.register_arm9

    def setter(a, s):
        main = m.read_long(MAIN_PTR)
        if not 0x02000000 <= main < 0x02400000 or m.read_long(main + SLOT_AT) != 10:
            return
        if lo <= reg.r14 < hi:
            ai['actions'] += 1
        if dbg and m.read_long(dbg) == DEBUG_MAGIC:
            ai['fallbacks'].add(m.read_byte(dbg + 7))
    for addr in SETTERS:
        r.emu.memory.register_exec(addr, setter)


def poke_script(path, member, at, was, now):
    """Replace bytes inside one a/0/1/2 member of the ROM file at path (same size: nothing moves)."""
    import ndspy.rom
    fid = ndspy.rom.NintendoDSRom.fromFile(path).filenames.idOf('a/0/1/2')
    with open(path, 'r+b') as f:
        raw = f.read()
        start = struct.unpack_from('<I', raw, struct.unpack_from('<I', raw, 0x48)[0] + 8 * fid)[0]
        btnf = start + 0x10 + struct.unpack_from('<I', raw, start + 0x14)[0]
        gmif = btnf + struct.unpack_from('<I', raw, btnf + 4)[0]
        pos = gmif + 8 + struct.unpack_from('<I', raw, start + 0x1C + 8 * member)[0] + at
        assert raw[pos:pos + len(was) // 2].hex() == was, 'member %d is not as expected at 0x%X' % (member, at)
        f.seek(pos)
        f.write(bytes.fromhex(now))


def worker(case, rom, out_dir, setting):
    tag = '%s_%s' % (case, setting)
    trace = os.path.join(out_dir, tag + '.jsonl')
    r = emu.Runner(rom, os.path.join(out_dir, tag), trace=trace)
    r.run(open(os.path.join(tbpaths.LIB, 'boot.txt')).read().splitlines())
    res = {'case': case, 'setting_wanted': setting, 'setting_written': emu.set_ai_setting(r, setting)}
    res['setting'] = emu.ai_setting(r)
    hp_fixed, ai = [], {'actions': 0, 'fallbacks': set()}
    r.emu.memory.register_exec(TRAINER_BATTLE, lambda a, s: hp_fixed.append(legal_hp(r)))
    if setting != 'off':
        watch_ai(r, ai)
    r.run(['press B', 'wait 40'] + CASES[case]['walk'])
    res['at'] = list(r.player_pos())
    r.shot('at')
    at = block(r)
    if case.endswith('_loss'):
        r.until('fight_menu', 'A', 6000)
        r.shot('battle')
        for _ in range(150):                    # FIGHT, the lead faints, the loss, then whatever follows
            r.run(['wait 54', 'press A'])
            if r.frozen or any(key[1:] == HOME for key in r.msg_read):
                break
        r.shot('after')
    else:
        for k in range(600):                    # the scene, its two battles (one a full team) and the lines
            r.run(['wait 30', 'press A'])
            if k % 40 == 10:
                r.shot('scene%02d' % (k // 40))
            if at is not None and r.emu.memory.unsigned.read_short(at + VAR_4086) == 1:
                break
        res['var_4086'] = r.emu.memory.unsigned.read_short(at + VAR_4086) if at is not None else None
    res['end'] = list(r.player_pos())
    res.update(hp_fixed=hp_fixed, ai_actions=ai['actions'], ai_fallbacks=sorted(ai['fallbacks']))
    r.trace.close()
    events = [json.loads(line) for line in open(trace)]
    res['failures'] = sorted({'%s %s' % (e['ev'], e.get('lr') or e.get('text') or e.get('heap') or '') for e in events
                              if e['ev'] in FAILURES and not (e['ev'] == 'assert' and e.get('lr') in INHERITED)})
    res['reads'] = sorted({(e['bank'], e['index']) for e in events if e['ev'] == 'read'})
    res['clipped'] = sorted({e.get('text') or '' for e in events if e['ev'] == 'clipped'})
    with open(os.path.join(out_dir, tag + '.json'), 'w') as f:
        json.dump(res, f, indent=1)


def make_save(case, rom):
    from savetool import OBJECT_SIZE, OBJECTS, VARS, Save, gen4_slow_exp
    s = Save(saves.path('party_nostatus'))
    spec = CASES[case]
    if case.endswith('_loss'):                  # a party that loses at once: level 5 at 1 HP, the rest fainted
        for k in range(6):
            m = s.mon(k)
            if k < spec.get('able', 1):
                m.set_level(5, gen4_slow_exp(5))
                m.set_stats(1, 5, 5, 5, 5, 5)
            else:
                m.set_hp(0)
            s.set_mon(k, m)
    if case == 'route3_actors':
        s.set_flag(0x517)                      # the scene's objects still hidden
        s.put('<H', VARS + 2 * (0x4086 - 0x4000), 0)
        m = s.mon(0)                           # wins the scene's two battles (a battle recomputes the 999s)
        m.set_level(100, 1059860)
        m.set_stats(999, 999, 999, 999, 999, 999)
        s.set_mon(0, m)
        s.set_options(battle_style_set=True)   # no "switch Pokemon?" question, which A would answer Yes
    elif case == 'giovanni_loss':
        s.put('<H', VARS + 2 * (0x40A2 - 0x4000), 8)
        s.set_flag(0x556)                      # the scripts keep it set; clear, it shows people on the path
    slot = s.base + OBJECTS + OBJECT_SIZE
    template = bytes(s.data[slot:slot + OBJECT_SIZE])   # a saved person to copy, before place() switches it off
    if 'place' in spec:
        s.place(*spec['place'], rom)
    if 'person' in spec:
        obj, sprite, script, x, y = spec['person']
        w = bytearray(template)
        w[0x08], w[0x09] = obj, 14             # object id, movement: stands facing up
        w[0x0A:0x0F] = bytes(5)                # no wander range; facing up
        struct.pack_into('<HHHHH', w, 0x10, spec['place'][0], sprite, 0, 0, script)   # map, sprite, kind, flag, script
        struct.pack_into('<6h', w, 0x20, x, 0, y, x, 0, y)
        s.data[slot:slot + OBJECT_SIZE] = w
    return s


def run(case, rom, setting):
    name = 'story%d_%s_%s' % (os.getpid(), case, setting)
    rom_k, dsv_k = os.path.join(OUT, name + '.nds'), os.path.join(emu.DSV_DIR, name + '.dsv')
    if case == 'giovanni_loss':
        shutil.copy(rom, rom_k)                 # a copy: the TV warp is written into it
        poke_script(rom_k, *TV_WARP)
    else:
        if os.path.lexists(rom_k):
            os.remove(rom_k)
        os.symlink(os.path.abspath(rom), rom_k)
    os.makedirs(emu.DSV_DIR, exist_ok=True)
    make_save(case, rom).write(dsv_k)
    out_dir = os.path.join(OUT, os.path.splitext(os.path.basename(rom))[0])
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, '%s_%s.json' % (case, setting))
    if os.path.exists(p):
        os.remove(p)
    subprocess.run([sys.executable, __file__, '--worker', case, rom_k, out_dir, setting], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    for f in (rom_k, dsv_k):
        if os.path.lexists(f):
            os.remove(f)
    return json.load(open(p)) if os.path.exists(p) else None


def ending(case, res):
    """What differs from the scene's end (empty: it ended as it should)."""
    if res is None:
        return ['no result (the worker died)']
    out = ['failures: %s' % res['failures']] if res['failures'] else []
    if res.get('setting') != res.get('setting_wanted'):
        out.append('the save in RAM held setting %r, not %r' % (res.get('setting'), res.get('setting_wanted')))
    if case.endswith('_loss'):
        if HOME not in set(map(tuple, res['reads'])):
            out.append("no white-out: Mom's 38:40 was never shown (the player ended at %s)" % res['end'])
    elif res.get('var_4086') != 1:
        out.append('the scene did not finish: var 0x4086 = %s (want 1)' % res.get('var_4086'))
    return out


def served(res):
    """What shows that the advanced AI did not serve an AI-on run (empty: it did)."""
    if res is None:
        return []
    out = []
    if not res.get('ai_actions'):
        out.append('the advanced AI made no decision (no action from its slot code): the scene tested nothing')
    loud = sorted(set(res.get('ai_fallbacks', [])) - {0, 3, 6})
    if loud:
        out.append('the advanced AI fell back (codes %s, FB_* in src/advai.c)' % loud)
    return out


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:6])
    ap = argparse.ArgumentParser()
    ap.add_argument('cases', nargs='*', help='default: %s' % ', '.join(CASES))
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="its payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--setting', choices=('all', 'important'), default='all', help='the AI-on run\'s setting')
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the workers
    os.makedirs(OUT, exist_ok=True)
    cases = a.cases or list(CASES)
    unknown = [c for c in cases if c not in CASES]
    if unknown:
        sys.exit('unknown cases %s (known: %s)' % (unknown, ', '.join(CASES)))
    failed = 0
    for c in cases:
        off, on = run(c, a.rom, 'off'), run(c, a.rom, a.setting)
        p_off, p_on, not_served = ending(c, off), ending(c, on), served(on)
        if not_served:
            verdict = 'FAILED'              # the AI-on run tested nothing (or fell back)
        elif not p_on:
            verdict = 'ok'
        elif p_off and on and off and sorted(p_on) == sorted(p_off):
            verdict = 'INHERITED'           # the build ends this scene the same way without the AI
        else:
            verdict = 'FAILED'
        failed += verdict == 'FAILED'
        print('%-14s %-9s AI on (%s): ended at %s%s, AI actions %s, fallback codes %s; AI off: ended at %s%s' % (
            c, verdict, a.setting, (on or {}).get('end'), '' if not p_on else ' [%s]' % '; '.join(p_on),
            (on or {}).get('ai_actions'), (on or {}).get('ai_fallbacks'), (off or {}).get('end'),
            '' if not p_off else ' [%s]' % '; '.join(p_off)))
        for p in not_served:
            print('    ' + p)
    print('storycheck (%s, AI %s): %d of %d case(s) failed' % (os.path.basename(a.rom), a.setting, failed, len(cases)))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
