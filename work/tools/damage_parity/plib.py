"""Parity harness library: hooks on the hack's damage routine (ov14 0x0220876C) and battle-Pokémon readers.
Read-only on the ROM. CN ROM by default (D-1002)."""
import sys, json, datetime, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # work/tools
import emu_harness as E
from save_core import decode_pokemon

def _default_save():
    """$PARITY_SAV, else trainer.sav in this checkout's work/build/memcheck, else in the main checkout's."""
    import os, subprocess
    if os.environ.get('PARITY_SAV'):
        return os.environ['PARITY_SAV']
    here = E.DEF_SAVES / 'trainer.sav'
    if here.exists():
        return str(here)
    common = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=Path(__file__).parent,
                            capture_output=True, text=True).stdout.strip()
    return str((Path(__file__).parent / common).resolve().parent / 'work' / 'build' / 'memcheck' / 'trainer.sav')


SAV = _default_save()
CLOCK = datetime.datetime(2026, 10, 9, 12)

# damage routine 0x0220876C(atk bpp r0, def bpp r1, move param r2, eff r3, [sp] targetRatio, [sp+4] crit, ...)
DMG_ENTRY = 0x0220876C
DMG_POWER = 0x02208848      # r0 = power (after 0x2206598)
DMG_ATK = 0x0220885A        # r0 = attack stat after mods
DMG_DEF = 0x02208868        # r0 = defense stat after mods
DMG_LVL = 0x02208870        # r0 = level
DMG_BASE = 0x02208882       # r0 = base damage
DMG_WEATHER = 0x022088A0    # r0 = weather ratio (fx)
DMG_GLAIVE = 0x022088BA     # r0 = defender has condition 0x2D
DMG_ROLL = 0x022088E4       # r0 = random roll 85..100
DMG_STAB = 0x022088FA       # r0 = STAB ratio
DMG_TYPE = 0x0220890C       # r0 = after type effectiveness
DMG_PREFINAL = 0x02208938   # r4 = damage before final modifiers (u16)
DMG_FINALMOD = 0x02208966   # r4 = final modifier chain
DMG_STORE = 0x02208994      # r6 = final damage


class DamageLog:
    def __init__(self, h, force_crit=None, force_roll=None, max_calls=50):
        self.rows = []
        self.cur = None
        self.force_crit = force_crit
        self.force_roll = force_roll
        h.on_exec(DMG_ENTRY, self.entry)
        for addr, key in ((DMG_POWER, 'power'), (DMG_ATK, 'atk'), (DMG_DEF, 'def'), (DMG_LVL, 'level'),
                          (DMG_BASE, 'base'), (DMG_WEATHER, 'weatherRatio'), (DMG_GLAIVE, 'glaive'),
                          (DMG_STAB, 'stabRatio'), (DMG_TYPE, 'afterType')):
            h.on_exec(addr, lambda h, key=key: self.put(key, h.reg.r0))
        h.on_exec(DMG_ROLL, self.roll)
        h.on_exec(DMG_PREFINAL, lambda h: self.put('preFinal', h.reg.r4))
        h.on_exec(DMG_FINALMOD, lambda h: self.put('finalMod', h.reg.r0))
        h.on_exec(DMG_STORE, self.store)

    def put(self, k, v):
        if self.cur is not None:
            self.cur[k] = v

    def entry(self, h):
        sp = h.reg.sp
        a, d, mp = h.reg.r0, h.reg.r1, h.reg.r2
        if self.force_crit is not None:
            h.w32(sp + 4, 1 if self.force_crit else 0)
        self.cur = dict(frame=h.frame, attacker=bpp(h, a), defender=bpp(h, d), move=h.u16(mp), moveType=h.u8(mp + 8),
                        moveCat=h.u8(mp + 9), eff=h.reg.r3, targetRatio=h.u32(sp), crit=h.u32(sp + 4), lr=hex(h.reg.lr))

    def roll(self, h):
        if self.cur is None:
            return
        if self.force_roll is not None:
            h.reg.r0 = self.force_roll
        self.cur['roll'] = h.reg.r0

    def store(self, h):
        if self.cur is None:
            return
        self.cur['damage'] = h.reg.r6
        self.rows.append(self.cur)
        self.cur = None


def bpp(h, a):
    return dict(addr=hex(a), species=h.u16(a), hp=h.u16(a + 0x1c), hp2=h.u16(a + 0x1e),
                stats=[h.u16(a + o) for o in (0x22C, 0x22E, 0x230, 0x232, 0x234)],
                stages=[struct.unpack('b', bytes([h.u8(a + 0x240 + i)]))[0] for i in range(7)],
                raw=h.read(a, 0x2A0).hex())


def party_mon(h, slot):
    a = h.array(E.ARR_PARTY) + 8 + 236 * slot
    m = decode_pokemon(h.read(a, 236))
    return {k: v for k, v in m.items() if isinstance(v, (int, str, bool, type(None), list, dict))}


def setup_attacker(h, species, level, moves, item=0, form=0, status=None, slot_to=0, ability=None):
    mon = h.generate_pokemon(species, level=level, item=item, form=form)
    fields = E.moveset(moves, [30] * len(moves))
    if ability is not None:
        fields['ability'] = ability
    if status is not None:
        fields['status'] = status
    h.edit_party_mon(h.generated_slot, **fields)
    h.swap_party(slot_to, h.generated_slot)
    return party_mon(h, slot_to)


def wild_mon_info(h, pid):
    cps = E.pid_copies(h, pid)
    if not cps:
        return None
    m = decode_pokemon(h.read(cps[0], 236))
    return {k: v for k, v in m.items() if isinstance(v, (int, str, bool, type(None), list, dict))}


def dump(obj, path):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=1, default=str)


def wild_battle2(h, species, level, item=None, moves=None, pp=None, form=None, ability=None):
    """emu_harness.wild_battle plus an ability edit of every RAM copy."""
    log = E.WildLog(h)
    h.run_script(program=E.script_bytes(("LockAll",), ("WildBattle", species, level, 0), ("ReleaseAll",), ("End",)))
    if not h.run_until(lambda h: log.rows, 900):
        raise RuntimeError("no wild Pokemon built")
    row = log.rows[0]
    fields = {k: v for k, v in (("item", item), ("form", form), ("ability", ability)) if v is not None}
    if moves is not None:
        fields.update(E.moveset(moves, pp or [30] * len(moves)))
    cps = E.pid_copies(h, row["pid"])
    for a in cps:
        h.write(a, E.encode_pokemon(h.read(a, 136), **fields))
    for addr in (E.WILD_FINALIZE, E.WILD_FINALIZE_SETFORM, E.WILD_FINALIZE_AFTER_SET, E.WILD_FINALIZE_RESTORE,
                 E.WILD_FINALIZE_END):
        h.on_exec(addr, None)
    return {"pid": row["pid"], "copies": [hex(a) for a in cps]}


TARGET_TL, TARGET_TR, TARGET_BL, TARGET_BR = (64, 40), (192, 40), (64, 104), (192, 104)


def choose(h, slot, target=None, shots=None, tag='c'):
    if not h.wait_screen("battle_menu", 1500):
        raise RuntimeError("battle command menu not found")
    h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=60)
    h.touch(*E.MOVE_BUTTONS[slot], frames=10, after=60)
    if shots is not None:
        shots.append(h.screenshot(f'{tag}_after_move_{h.frame}'))
    if target is not None:
        for pt in (target if isinstance(target[0], (list, tuple)) else [target]):
            h.touch(*pt, frames=10, after=40)


def finish_turn(h, max_frames=3000):
    for i in range(0, max_frames, 15):
        h.step(15)
        if h.in_field():
            h.step(60)
            return "field"
        if h.on_screen("battle_menu"):
            return "menu"
        if i % 60 == 45:
            h.press("B", after=0)
    h.screenshot("turn_stuck")
    raise RuntimeError("turn did not finish")
