"""ITCM and arena guard: nothing but the advanced AI touches the memory the AI build put it in.

  .venv/bin/python work/advanced-ai/testbench/checks/itcm_arena.py --rom ROM [--payload P] [--part menus|battles|all]
                                                                   [--setting off|all|important] [--json OUT]

Adopted from the installer agent's phase 0 probe (work/build/advanced-ai/layout/itcm_probe.py, which proved that
0x01FF8FC0-0x02000000 is free before the AI went there; docs/memory-layout.md). It boots the Violet Gym test save
(lib/saves.py, cut to its 512 KB battery image) on the ROM in DeSmuME through our harness (work/tools/emu_harness.py,
clock fixed at 2026-01-01 12:00) and plays:
- the field: a walk, the touch menu (Pokedex, party and a summary, Bag, Pokegear, trainer card), Options pages 1 and
  2, a save with overwrite;
- a wild battle, fled;
- a trainer battle in singles (trainer 6; the player's lead at 1 HP, so it faints and the player sends another) and a
  double against two trainers (15 and 6), each with the Bag, a pocket, the party and a summary opened in battle.
Before each trainer battle every party Pokemon's current HP is set to at most its maximum (the Spanish test save's
edited stats leave 998/297 after a battle, which the AI's range check rejects: a silent fallback to overlay 11).

Without --payload (a ROM without the AI): it fills the SDK's ITCM arena, from the end of the ROM's ITCM code (the
hack's block, text speed and, in main's builds, trainer display: 0x01FF8FC0 in the rc8 release, 0x01FF9140 in main)
to 0x02000000, with an address-derived canary and hooks writes there, as the phase 0 probe did. The positive control
is text speed's frame state (from work/patches/text-speed/payload.json), which the game writes every frame. It fails
if a word changes or the hook fires.

With --payload (an AI build): the AI is switched on with --setting (default all) in the save in RAM, and the checks are
the AI's own regions (the payload's itcm and main regions): no code outside the AI ever writes into them, the AI itself
writes only its data objects there (the payload's even-address symbols, e.g. g_fsg and g_tune, each up to the next
symbol), and at the end every other byte still equals the payload's itcm.bin and main.bin; the SDK's ITCM arena (bounds at 0x027FFDA0/0x027FFDC4, sampled
every 30 frames) never changes from its value after boot. Writes into the AI's work RAM (the itcm_ram region) from
code outside the AI are counted and listed, not failed: the engine routines the AI calls may write into its buffers.
Below the AI's itcm origin (from the payload), the ITCM code the AI build kept (the hack's block, text speed, trainer
display) must stay as the ROM has it: the AI's code never writes there, nothing writes the headroom between that code's
end and the origin, and at the end those bytes equal the ROM's ITCM section, except text speed's frame state.
Both modes also track each game heap's smallest spare room and every NULL allocation (memcheck's method), and fail
on a NULL allocation or a battle that does not end.

Results: RUNS/itcm_arena/<ROM name>/ (screenshots, the harness log) and the JSON summary (--json). Exit status 1 on a
failure. One emulator.
"""
import argparse
import datetime
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402

sys.path.insert(0, os.path.join(tbpaths.WORK, 'tools'))
import emu_harness as eh  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'itcm_arena')
ITCM = (0x01FF8000, 0x02000000)
TEXT_SPEED = os.path.join(tbpaths.WORK, 'patches', 'text-speed', 'payload.json')
ARENA_LO, ARENA_HI = 0x027FFDA0, 0x027FFDC4
ARENAS = ('main', 'main_subpriv', 'mainex', 'itcm', 'dtcm', 'shared', 'wram_main', 'wram_sub', 'wram_subpriv')
ALLOC = 0x0201B258           # AllocFromHeapInternal(expHeap, size, align, heapId)
ALLOC_RET = 0x0201B284
FREE_SIG = 0x4652
FLAG_AI, FLAG_AI_IMPORTANT = 0x2C2, 0x2C3
SETTINGS = {'off': (False, False), 'all': (True, False), 'important': (True, True)}
TRAINER_SET_INIT = 0x02072544      # EnemyTrainerSet_Init(BattleSetup *setup, ...)
IN_BATTLE_SUMMARY = (50, 173)      # battle party, a Pokemon's page: SUMMARY (bottom left)
IN_BATTLE_SHIFT = (128, 78)        # the same page: SHIFT
BATTERY = 524288                   # the battery image the harness imports (a .dsv is it plus DeSmuME's footer)


def rom_itcm(rom_path, ai_origin=None):
    """(the ROM's ITCM code from 0x01FF8000, its end): every autoload section in ITCM but the AI's own itcm section."""
    import ndspy.rom
    secs = [s for s in ndspy.rom.NintendoDSRom.fromFile(rom_path).loadArm9().sections[1:]
            if ITCM[0] <= s.ramAddress < ITCM[1] and s.ramAddress != ai_origin]
    end = max(s.ramAddress + len(s.data) + s.bssSize for s in secs)
    image = bytearray(end - ITCM[0])
    for s in secs:
        image[s.ramAddress - ITCM[0]:s.ramAddress - ITCM[0] + len(s.data)] = s.data
    return bytes(image), end


def text_speed_state():
    """[lo, hi) of text speed's frame state: its state symbol to its payload's end (written every frame)."""
    with open(TEXT_SPEED) as f:
        t = json.load(f)
    return t['symbols']['text_speed_state'] & ~1, t['base'] + len(bytes.fromhex(t['code']))


def canary(addr):
    return (addr * 0x9E3779B1 ^ 0xC0DECAFE) & 0xFFFFFFFF


def battery(name, out_dir):
    """A test save as the harness takes it: the .dsv's first 512 KB."""
    path = os.path.join(out_dir, name + '.sav')
    with open(saves.path(name), 'rb') as f:
        data = f.read(BATTERY)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def _party_ext_crypt(raw):
    """Gen 4 party extension (0x88-0xEB) XOR stream from the PID (the game's LCRNG)."""
    pid = struct.unpack_from('<I', raw, 0)[0]
    x, out = pid, bytearray(raw)
    for off in range(0x88, 0xEC, 2):
        x = (x * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        v = struct.unpack_from('<H', raw, off)[0] ^ (x >> 16)
        struct.pack_into('<H', out, off, v)
    return bytes(out)


def set_lead_hp(h, hp):
    a = h.array(eh.ARR_PARTY) + 8
    raw = h.read(a, 236)
    plain = bytearray(_party_ext_crypt(raw))
    struct.pack_into('<H', plain, 0x8E, hp)
    h.write(a, _party_ext_crypt(bytes(plain)))


def fix_party_hp(h):
    """Every party Pokemon's current HP at most its maximum (the Spanish test save's edited stats leave 998/297 after a
    battle, which the AI's range check rejects: FB_OPP, every turn to overlay 11). [(slot, was, max)] of those fixed."""
    base = h.array(eh.ARR_PARTY)
    fixed = []
    for k in range(min(6, h.u32(base + 4))):
        a = base + 8 + 236 * k
        plain = bytearray(_party_ext_crypt(h.read(a, 236)))
        cur, mx = struct.unpack_from('<HH', plain, 0x8E)
        if cur > mx:
            struct.pack_into('<H', plain, 0x8E, mx)
            h.write(a, _party_ext_crypt(bytes(plain)))
            fixed.append((k, cur, mx))
    return fixed


def drive_battle(h, shot, tag, max_frames=24000):
    """Fight with move 1 (first target) until the field is back. Between menus: B through messages; every fourth pass
    sends party slot 2 or 3 if a forced switch is pending (touch the slot, then SHIFT)."""
    start, turns, last_menu, n = h.frame, 0, -1000, 0
    while h.frame - start < max_frames:
        if h.in_field():
            h.step(60)
            return ('field', turns, h.frame - start)
        if h.on_screen('battle_menu') and h.frame - last_menu > 30:
            h.touch(*eh.BATTLE_BUTTONS['fight'], frames=10, after=50)
            h.touch(*eh.MOVE_BUTTONS[0], frames=10, after=60)
            if tag == 'double':
                h.touch(64, 40, frames=10, after=60)       # target: the foe on the left
            turns += 1
            last_menu = h.frame
            continue
        n += 1
        if n % 40 == 0:
            shot(f'24_{tag}_{h.frame}')
        if n % 4 == 0:              # a pending forced switch: cursor right (party slot 2), open it, SHIFT
            h.press('RIGHT', after=30)
            h.press('A', after=60)
            h.press('A', after=60)
        else:
            h.press('B', after=40)
    shot(f'24_{tag}_timeout')
    return ('timeout', turns, h.frame - start)


class Probe:
    """Arena samples, heap spare room and NULL allocations (memcheck's method)."""

    stage = 'boot'

    def __init__(self, h):
        self.h = h
        self.arena_samples = {}
        self.minspare = {}
        self.heap_sizes = {}
        self.fails = []
        self._pending = None

    def arenas(self):
        return {n: (self.h.u32(ARENA_LO + 4 * i), self.h.u32(ARENA_HI + 4 * i)) for i, n in enumerate(ARENAS)}

    def sample(self, h):
        if h.frame % 30:
            return
        for n, v in self.arenas().items():
            seen = self.arena_samples.setdefault(n, [])
            if not seen or seen[-1][1] != v:
                seen.append((h.frame, v, self.stage))

    def largest_free(self, heap):
        u32 = self.h.u32
        p, big, n = u32(heap + 0x24), 0, 0
        while p and n < 4096:
            if not 0x02000000 <= p < 0x02400000 or self.h.u16(p) != FREE_SIG:
                return None
            big = max(big, u32(p + 4))
            p = u32(p + 12)
            n += 1
        return big

    def on_alloc(self, h):
        r = h.reg
        heap, req, align, hid = r.r0 & 0xFFFFFFFF, r.r1 & 0xFFFFFFFF, r.r2 & 0xFFFFFFFF, r.r3 & 0xFF
        self._pending = (hid, req)
        if not heap:
            return
        big = self.largest_free(heap)
        if big is None:
            return
        mag = (1 << 32) - align if align >> 31 else align
        spare = big - req - 0x10 - (mag - 4 if mag > 4 else 0)
        cur = self.minspare.get(hid)
        if cur is None or spare < cur[0]:
            self.minspare[hid] = (spare, req, h.frame, self.stage)
        if hid not in self.heap_sizes:
            self.heap_sizes[hid] = h.u32(heap + 0x1C) - h.u32(heap + 0x18)

    def on_ret(self, h):
        if self._pending and h.reg.r4 & 0xFFFFFFFF == 0:
            self.fails.append((*self._pending, h.frame, self.stage))
        self._pending = None


def ai_ranges(lay):
    """{name: (lo, hi)} of the AI's code and work RAM from the payload's regions."""
    out = {'slot': lay.adv_code}
    for name in ('itcm', 'main', 'itcm_ram'):
        reg = lay.regions.get(name) or {}
        if reg.get('ram') is not None and reg.get('size'):
            out[name] = (reg['ram'], reg['ram'] + reg['size'])
    return out


def data_extents(lay, ranges):
    """[(lo, hi)] of the AI's data objects inside its code regions: each even-address symbol up to the next symbol."""
    addrs = sorted(set(lay.symbols.values()))
    out = []
    for name, (lo, hi) in ranges.items():
        if name not in ('itcm', 'main'):
            continue
        for k, v in enumerate(addrs):
            if lo <= v < hi and not v & 1:
                nxt = next((x & ~1 for x in addrs[k + 1:] if x & ~1 > v), hi)
                out.append((v, min(nxt, hi)))
    return out


def payload_bytes(lay, name):
    reg = lay.regions[name]
    with open(os.path.join(os.path.dirname(lay.path), reg['file']), 'rb') as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', help='an AI build\'s payload.json: check the AI\'s regions (default: ADVAI_PAYLOAD; '
                    'none: the canary over the ITCM arena, from the ROM\'s ITCM code end to 0x02000000)')
    ap.add_argument('--setting', choices=sorted(SETTINGS), default='all', help='the AI setting in RAM (AI builds)')
    ap.add_argument('--part', choices=('menus', 'battles', 'all'), default='all')
    ap.add_argument('--json')
    a = ap.parse_args()
    lay = payload.load(a.payload) if (a.payload or os.environ.get(payload.ENV)) else None
    tag = os.path.splitext(os.path.basename(a.rom))[0]
    out = Path(OUT) / tag
    out.mkdir(parents=True, exist_ok=True)
    sav = battery('violet_gym', str(out))
    ranges = ai_ranges(lay) if lay else {}
    code = [(n, r) for n, r in ranges.items() if n in ('itcm', 'main')]
    origin = lay.regions['itcm']['ram'] if lay else None
    itcm_image, itcm_end = rom_itcm(a.rom, origin)
    CONTROL = text_speed_state()
    REGION = (itcm_end, ITCM[1])
    if not ITCM[0] <= CONTROL[0] < CONTROL[1] <= itcm_end:
        sys.exit('text speed\'s frame state %08X-%08X is not in the ROM\'s ITCM code' % CONTROL)
    if lay and itcm_end > origin:
        sys.exit('the ROM\'s ITCM code ends at %08X, past the AI\'s itcm origin %08X' % (itcm_end, origin))
    with eh.Harness(rom=Path(a.rom).resolve(), sav=Path(sav).resolve(), out=out,
                    rtc=datetime.datetime(2026, 1, 1, 12, 0, 0)) as h:
        p = Probe(h)
        h.on_frame(p.sample)
        h.boot_to_menu()
        h.continue_game()
        res = {'rom': str(a.rom), 'mode': 'ai build' if lay else 'canary', 'problems': []}
        writes, foreign, control = [], [], [0]
        below = {'ai': [], 'headroom': [], 'other': []}
        if lay:
            on, important = SETTINGS[a.setting]
            h.set_flag(FLAG_AI, on)
            h.set_flag(FLAG_AI_IMPORTANT, important)
            res['setting'] = (h.get_flag(FLAG_AI), h.get_flag(FLAG_AI_IMPORTANT))
            ai_code = [r for n, r in ranges.items() if n != 'itcm_ram']
            data = data_extents(lay, ranges)

            def on_code(addr, sz):
                pc = h.reg.pc & 0xFFFFFFFE
                own = any(c0 <= pc < c1 for c0, c1 in ai_code)
                if own and any(d0 <= addr < d1 for d0, d1 in data):
                    return                  # the AI writing its own data object
                if len(writes) < 64:
                    writes.append((hex(addr), sz, hex(pc), h.frame, p.stage, 'the AI' if own else 'foreign'))
            for _, (lo, hi) in code:
                h.emu.memory.register_write(lo, on_code, hi - lo)
            if 'itcm_ram' in ranges:
                lo, hi = ranges['itcm_ram']

                def on_ram(addr, sz):
                    pc = h.reg.pc & 0xFFFFFFFE
                    if not any(c0 <= pc < c1 for c0, c1 in ai_code):
                        foreign.append((hex(addr), sz, hex(pc), h.frame, p.stage))
                h.emu.memory.register_write(lo, on_ram, hi - lo)

            # below the origin: the ITCM code the build kept, then the headroom up to the origin
            def on_below(addr, sz):
                pc = h.reg.pc & 0xFFFFFFFE
                kind = ('ai' if any(c0 <= pc < c1 for c0, c1 in ai_code) else 'headroom' if addr >= itcm_end
                        else None if CONTROL[0] <= addr < CONTROL[1] else 'other')
                if kind and len(below[kind]) < 32:
                    below[kind].append((hex(addr), sz, hex(pc), h.frame, p.stage))
            h.emu.memory.register_write(ITCM[0], on_below, origin - ITCM[0])
            res['itcm_below_origin'] = {'code_end': hex(itcm_end), 'origin': hex(origin),
                                        'headroom': origin - itcm_end, 'text_speed_state': [hex(x) for x in CONTROL]}
        else:
            size = REGION[1] - REGION[0]
            res['boot_nonzero_bytes'] = sum(1 for b in h.read(REGION[0], size) if b)
            for addr in range(REGION[0], REGION[1], 4):
                h.w32(addr, canary(addr))
            want = b''.join(struct.pack('<I', canary(x)) for x in range(*REGION, 4))
            res['canary_readback_ok'] = h.read(REGION[0], size) == want

            def on_region(addr, sz):
                if len(writes) < 64:
                    writes.append((hex(addr), sz, hex(h.reg.pc & 0xFFFFFFFF), h.frame, p.stage))

            def on_control(addr, sz):
                control[0] += 1
            h.emu.memory.register_write(REGION[0], on_region, size)
            h.emu.memory.register_write(CONTROL[0], on_control, CONTROL[1] - CONTROL[0])
        arena_boot = p.arenas()['itcm']
        h.on_exec(ALLOC, p.on_alloc)
        h.on_exec(ALLOC_RET, p.on_ret)
        shots, log = [], []

        def shot(name):
            shots.append(str(h.screenshot(name)))

        def stage(name):
            p.stage = name
            h.log('stage', name, 'code or region writes', len(writes), 'foreign work-RAM writes', len(foreign))

        h.press('B', after=60)
        shot('00_field')
        if a.part in ('menus', 'all'):
            stage('walk')
            for d in ('LEFT', 'RIGHT', 'DOWN', 'UP'):
                h.walk(d, 1)
            for name, back in (('pokedex', 3), ('pokemon', 2), ('bag', 2), ('pokegear', 2), ('card', 3)):
                stage(name)
                h.touch(*eh.FIELD_MENU[name], frames=12, after=300)
                h.step(120)
                shot(f'02_{name}')
                if name == 'pokemon':
                    h.press('A', after=60)        # first Pokemon: submenu, first entry Summary
                    h.press('A', after=200)
                    h.press('RIGHT', after=60)
                    h.press('RIGHT', after=60)
                    shot('02_summary_p3')
                    h.press('B', after=200)
                for _ in range(back):
                    h.press('B', after=120)
                h.step(120)
            stage('options')
            h.touch(*eh.FIELD_MENU['options'], frames=12, after=300)
            h.step(120)
            h.press('R', after=120)
            shot('04_options_p2')
            h.press('L', after=120)
            h.press('B', after=200)
            h.press('B', after=120)
            stage('save')
            h.touch(*eh.FIELD_MENU['save'], frames=12, after=300)
            h.step(60)
            h.press('A', after=120)       # Yes
            h.press('A', after=60)        # Yes, overwrite
            h.step(1500)
            shot('05_saved')
            h.press('B', after=120)
            h.press('B', after=120)
        if a.part in ('battles', 'all'):
            h.press('B', after=60)
            stage('wild')
            h.run_script(program=eh.script_bytes(('LockAll',), ('WildBattle', 16, 3, 0), ('ReleaseAll',), ('End',)))
            h.step(400)
            log.append(('wild fled', h.flee()))
            for name, t1, t2, weak in (('single', 6, 0, True), ('double', 15, 6, False)):
                stage(name)
                log.append((name, 'hp fixed', fix_party_hp(h)))
                if weak:
                    set_lead_hp(h, 1)      # the lead faints on the foe's first hit: a forced switch
                h.run_script(program=eh.script_bytes(('LockAll',), ('TrainerBattle', t1, t2, 0, 0),
                                                      ('ReleaseAll',), ('End',)))
                log.append((name, 'menu', h.wait_screen('battle_menu', 3000)))
                stage(name + '_bag')
                h.touch(*eh.BATTLE_BUTTONS['bag'], frames=10, after=180)
                h.touch(*eh.BAG_SLOTS[0], frames=10, after=150)
                shot(f'21_{name}_bag_pocket')
                for _ in range(4):
                    if h.on_screen('battle_menu'):
                        break
                    h.press('B', after=120)
                stage(name + '_party')
                h.wait_screen('battle_menu', 600)
                h.touch(*eh.BATTLE_BUTTONS['pokemon'], frames=10, after=180)
                h.touch(*eh.PARTY_SLOTS[0], frames=10, after=150)
                h.touch(*IN_BATTLE_SUMMARY, frames=10, after=250)
                shot(f'22_{name}_summary')
                for _ in range(5):
                    if h.on_screen('battle_menu'):
                        break
                    h.press('B', after=120)
                stage(name + '_fight')
                fight = drive_battle(h, shot, name)
                log.append((name, fight))
                if fight[0] != 'field':
                    res['problems'].append('the %s battle did not end (%s)' % (name, fight[0]))
                for _ in range(3):
                    h.press('B', after=60)
        stage('end')
        h.step(60)
        if lay:
            for n, (lo, hi) in code:
                ram, want = h.read(lo, hi - lo), payload_bytes(lay, n)
                diff = [lo + i for i in range(hi - lo) if ram[i] != want[i]
                        and not any(d0 <= lo + i < d1 for d0, d1 in data)]
                if diff:
                    res['problems'].append('the AI\'s %s code differs from the payload\'s %s at the end (%d bytes from '
                                           '%08X)' % (n, lay.regions[n]['file'], len(diff), diff[0]))
            if writes:
                res['problems'].append('%d write(s) into the AI\'s code: %s' % (len(writes), writes[:4]))
            if below['ai']:
                res['problems'].append('the AI wrote below its itcm origin: %s' % below['ai'][:4])
            if below['headroom'] or any(h.read(itcm_end, origin - itcm_end)):
                res['problems'].append('the headroom %08X-%08X was written: %s' % (itcm_end, origin, below['headroom'][:4]))
            kept = h.read(ITCM[0], itcm_end - ITCM[0])
            diff = [ITCM[0] + i for i in range(len(kept)) if kept[i] != itcm_image[i]
                    and not CONTROL[0] <= ITCM[0] + i < CONTROL[1]]
            if diff:
                res['problems'].append('the ITCM code below the origin differs from the ROM\'s at the end (%d bytes '
                                       'from %08X)' % (len(diff), diff[0]))
            res['itcm_below_origin'].update(other_writes=below['other'][:16], ai_writes=below['ai'][:16],
                                            headroom_writes=below['headroom'][:16], bytes_changed=len(diff))
        else:
            back = h.read(REGION[0], REGION[1] - REGION[0])
            diff = [REGION[0] + i for i in range(0, len(back), 4) if back[i:i + 4] != want[i:i + 4]]
            res.update(canary_words_changed=len(diff), first_changed=[hex(x) for x in diff[:16]],
                       control_write_hook_hits=control[0])
            if diff or writes:
                res['problems'].append('the region was written: %d canary words changed, %d hook hits %s' % (
                    len(diff), len(writes), writes[:4]))
            if not control[0]:
                res['problems'].append('the positive control (text speed\'s frame state) saw no write: the hooks '
                                       'are not working')
        itcm_seen = [v for _, v, _ in p.arena_samples.get('itcm', [])]
        if any(v != arena_boot for v in itcm_seen):
            res['problems'].append('the ITCM arena changed: %s' % [[hex(x) for x in v] for v in itcm_seen[:6]])
        if p.fails:
            res['problems'].append('NULL allocations: %s' % p.fails[:6])
        res.update({'frames': h.frame, 'itcm_arena_after_boot': [hex(x) for x in arena_boot],
                    'code_write_hits': writes, 'foreign_work_ram_writes': len(foreign),
                    'foreign_work_ram_first': foreign[:16],
                    'arena_samples': {n: [(f, [hex(v[0]), hex(v[1])], st) for f, v, st in s]
                                      for n, s in p.arena_samples.items()},
                    'heap_sizes': {str(k): v for k, v in sorted(p.heap_sizes.items())},
                    'heap_min_spare': {str(k): v for k, v in sorted(p.minspare.items())},
                    'alloc_fails': p.fails, 'log': log, 'shots': shots})
    res['ok'] = not res['problems']
    text = json.dumps(res, indent=1, default=str)
    if a.json:
        Path(a.json).write_text(text + '\n')
    print('itcm_arena (%s, %s): %s' % (tag, res['mode'], 'PASS' if res['ok'] else 'FAIL'))
    for line in res['problems']:
        print('  ' + line)
    print('  foreign writes into the AI\'s work RAM: %d; heap minimum spare: %s' % (
        len(foreign), {k: v[0] for k, v in sorted(p.minspare.items())}))
    sys.exit(0 if res['ok'] else 1)


if __name__ == '__main__':
    main()
