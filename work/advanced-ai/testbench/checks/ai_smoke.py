"""End-to-end smoke test of an AI build: boot, choose the setting, fight trainer battles, check who served them.

  .venv/bin/python work/advanced-ai/testbench/checks/ai_smoke.py --rom ROM [--payload P] [--options RECEIPT] [--json OUT]

Adopted from the installer agent's smoke test (work/build/advanced-ai/layout/ai_smoke.py, docs/memory-layout.md
"Smoke test with the AI installed"). It boots the Violet Gym test save (lib/saves.py, cut to its 512 KB battery
image) in DeSmuME through our harness (work/tools/emu_harness.py, clock fixed at 2026-01-01 12:00), continues into
the field and starts each case's trainer battle by script from there:

  all_unmarked        0x2C2 set, 0x2C3 clear, trainer 6 (unmarked)    -> slot overlay 10, adv_entry serves client 1
  important_marked    0x2C2 and 0x2C3 set, trainer 1 (marked)         -> overlay 10, adv_entry
  important_unmarked  0x2C2 and 0x2C3 set, trainer 15 (unmarked)      -> overlay 11 only
  off                 both clear, trainer 1                           -> overlay 11 only

The setting is written into the save in RAM, or with --options set through the real Options row (L + OPTIONS for
page 2, touch the TRAINER AI value, Confirm; RECEIPT is the difficulty build's receipt, which names the page's
struct). The player fights with its first move until the field is back. Before each battle every party Pokemon's
current HP is set to at most its maximum: the Spanish test save's edited stats leave 998/297 after a battle, which the
AI's range check rejects (FB_OPP), so every turn would go to overlay 11 and look like "AI off".

Recorded per case: the overlays SwitchSlotOverlay loads, the slot overlay at [main]+0x26C when adv_entry runs, the
calls of ai_slot_select, ai_entry, adv_entry, ai_replace, ai_lead and ai_resume, the action setters called from the
AI's slot code with overlay 10 loaded (the advanced AI deciding), and the trainer side's debug record's fallback code
at every setter call while overlay 10 is loaded. A case fails when the battle does not end, the flags are not the
case's, the slot loads or adv_entry calls are not the setting's, a served case has no action from the AI's code, or
a served case shows a fallback code other than 0 (FB_NONE; src/advai.c FB_*): a fallback where the AI should serve
fails loudly. Also reported: each heap's smallest spare room and every NULL allocation (a failure).

Addresses come from the payload (adv_entry, ai_debug, the slot range and the other symbols). Results:
RUNS/ai_smoke/<ROM name>/ and the JSON summary (--json). Exit status 1 on a failure. One emulator.
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import itcm_arena as ia  # noqa: E402
import payload  # noqa: E402

eh = ia.eh                                  # work/tools/emu_harness.py

OUT = os.path.join(tbpaths.RUNS, 'ai_smoke')
MAIN_PTR, SLOT_AT = 0x02255BAC, 0x26C
SWITCH_SLOT = 0x02215914
SETTERS = {0x02200960: 'move', 0x02200A30: 'item', 0x022009AC: 'switch', 0x0220091C: 'none'}
DEBUG_MAGIC, DEBUG_STRIDE = 0x49414441, 256     # advai.c Debug: magic, version u16, polls u8, fallback u8; 256 B a side
# (case, 0x2C2, 0x2C3, trainer, the slot overlays it must load, adv_entry must serve)
CASES = [('all_unmarked', True, False, 6, {10}, True), ('important_marked', True, True, 1, {10}, True),
         ('important_unmarked', True, True, 15, {11}, False), ('off', False, False, 1, {11}, False)]
OPTIONS_ICON, APPLY, ROW_Y = (123, 113), (149, 180), 91     # checks/options_trainer_ai.py
VALUE_X = {0: 128, 1: 180, 2: 220}                          # OFF, KEY, ALL
PAGE_STATE, PAGE_MODE, PAGE_DRAFT = 24, 48, 356


def set_via_options(h, page, on, important):
    """Options from the field menu with L held (page 2), touch the TRAINER AI value, touch Confirm."""
    value = 0 if not on else 1 if important else 2
    h.hold('L')
    h.step(2)
    h.touch(*OPTIONS_ICON, frames=6, after=240)
    h.release('L')
    h.step(60)
    assert h.u32(page + PAGE_STATE) and h.u32(page + PAGE_MODE) == 1, 'Options page 2 did not open'
    h.touch(VALUE_X[value], ROW_Y, after=30)
    assert h.u32(page + PAGE_DRAFT) == value, ('draft', h.u32(page + PAGE_DRAFT), value)
    h.screenshot(f'options_{value}')
    h.touch(*APPLY)
    h.step(240)
    assert h.run_until(lambda hh: hh.in_field() and not hh.u32(page + PAGE_STATE), 600, every=10), 'Options open'
    return value


def judge(c, flags, on, important, fight, menu, want_slots, want_adv):
    """What differs from the case's setting."""
    out = []
    if not menu or fight[0] != 'field':
        out.append('the battle %s' % ('never reached its menu' if not menu else 'did not end (%s)' % fight[0]))
    if flags != (on, important):
        out.append('flags 0x2C2/0x2C3 %s, the case wants %s' % (flags, (on, important)))
    slots = set(c.get('slot_loads', [])) & {10, 11}
    if slots != want_slots:
        out.append('slot overlays %s, the case wants %s' % (sorted(slots), sorted(want_slots)))
    if bool(c.get('adv_entry')) != want_adv:
        out.append('adv_entry ran %d times' % c.get('adv_entry', 0))
    if bool(c.get('adv_actions')) != want_adv:
        out.append('%d actions from the AI\'s code' % len(c.get('adv_actions', [])))
    bad = sorted(set(c.get('fallbacks', [])) - {0})
    if want_adv and bad:
        out.append('the advanced AI fell back (codes %s, FB_* in src/advai.c) where it should serve' % bad)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="its payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--options', help='a difficulty receipt: set the setting through the Options row')
    ap.add_argument('--json')
    a = ap.parse_args()
    lay = payload.load(a.payload)
    page = None
    if a.options:
        page = next(x['value'] for x in json.loads(Path(a.options).read_text())['build']['symbols']
                    if x['name'] == 'page')
        page = page if isinstance(page, int) else int(page, 0)
    sym = {k: v & ~1 for k, v in lay.symbols.items()}
    lo, hi = lay.adv_code
    dbg = lay.debug_addr(a.rom)
    tag = os.path.splitext(os.path.basename(a.rom))[0] + ('_options' if page else '')
    out = Path(OUT) / tag
    out.mkdir(parents=True, exist_ok=True)
    sav = ia.battery('violet_gym', str(out))
    res = {'rom': a.rom, 'payload': tbpaths.rel(lay.path), 'via': 'options row' if page else 'flags in RAM', 'cases': []}
    with eh.Harness(rom=Path(a.rom).resolve(), sav=Path(sav).resolve(), out=out,
                    rtc=datetime.datetime(2026, 1, 1, 12, 0, 0)) as h:
        p = ia.Probe(h)
        h.boot_to_menu()
        h.continue_game()
        h.on_exec(ia.ALLOC, p.on_alloc)
        h.on_exec(ia.ALLOC_RET, p.on_ret)
        cur = {}

        def slot_now():
            m = h.u32(MAIN_PTR)
            return h.u32(m + SLOT_AT) if 0x02000000 <= m < 0x02400000 else None

        def count(name):
            def f(hh):
                cur[name] = cur.get(name, 0) + 1
            return f
        for name in ('ai_slot_select', 'ai_entry', 'ai_replace', 'ai_lead', 'ai_resume'):
            if name in sym:
                h.on_exec(sym[name], count(name))

        def adv(hh):
            cur['adv_entry'] = cur.get('adv_entry', 0) + 1
            cur.setdefault('slot_at_adv_entry', set()).add(slot_now())
            cur.setdefault('adv_clients', set()).add(hh.reg.r2 & 0xFF)
        h.on_exec(sym['adv_entry'], adv)
        h.on_exec(SWITCH_SLOT, lambda hh: cur.setdefault('slot_loads', set()).add(hh.reg.r0 & 0xFFFFFFFF))

        def setter(kind):
            def f(hh):
                lr = hh.reg.r14 & 0xFFFFFFFF
                if slot_now() != 10:
                    return
                if lo <= lr < hi:
                    cur.setdefault('adv_actions', []).append(kind)
                if dbg and h.u32(dbg) == DEBUG_MAGIC:       # the trainer side's record: its fallback code
                    cur.setdefault('fallbacks', []).append(h.u8(dbg + 7))
            return f
        for addr, kind in SETTERS.items():
            h.on_exec(addr, setter(kind))
        h.press('B', after=60)
        for name, on, important, trainer, want_slots, want_adv in CASES:
            cur.clear()
            fixed = ia.fix_party_hp(h)
            if page is None:
                h.set_flag(ia.FLAG_AI, on)
                h.set_flag(ia.FLAG_AI_IMPORTANT, important)
            else:
                set_via_options(h, page, on, important)
            flags = (h.get_flag(ia.FLAG_AI), h.get_flag(ia.FLAG_AI_IMPORTANT))
            p.stage = name
            h.run_script(program=eh.script_bytes(('LockAll',), ('TrainerBattle', trainer, 0, 0, 0),
                                                  ('ReleaseAll',), ('End',)))
            menu = h.wait_screen('battle_menu', 3000)
            h.screenshot(f'{name}_menu')
            fight = ia.drive_battle(h, lambda n: h.screenshot(n), name)
            h.screenshot(f'{name}_after')
            for _ in range(3):
                h.press('B', after=60)
            c = {k: sorted(v) if isinstance(v, set) else v for k, v in cur.items()}
            problems = judge(c, flags, on, important, fight, menu, want_slots, want_adv)
            res['cases'].append({'case': name, 'flags': flags, 'trainer': trainer, 'fight': fight, 'hp_fixed': fixed,
                                 'problems': problems, 'ok': not problems,
                                 **{k: v for k, v in c.items() if k != 'fallbacks'},
                                 'fallback_codes': sorted(set(c.get('fallbacks', [])))})
            h.log(name, 'ok' if not problems else 'FAIL', problems)
        res['heap_min_spare'] = {str(k): v for k, v in sorted(p.minspare.items())}
        res['alloc_fails'] = p.fails
    res['ok'] = all(c['ok'] for c in res['cases']) and not p.fails
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str) + '\n')
    for c in res['cases']:
        print('%-19s %-6s flags %s, trainer %d, slots %s, adv_entry %s (clients %s), AI actions %d, fallback codes %s, '
              'battle %s%s' % (c['case'], 'ok' if c['ok'] else 'FAILED', c['flags'], c['trainer'], c.get('slot_loads'),
                               c.get('adv_entry', 0), c.get('adv_clients'), len(c.get('adv_actions', [])),
                               c['fallback_codes'], c['fight'][0], '' if c['ok'] else ': ' + '; '.join(c['problems'])))
    if p.fails:
        print('NULL allocations: %s' % p.fails[:6])
    print('ai_smoke (%s, %s): %s' % (os.path.basename(a.rom), res['via'], 'PASS' if res['ok'] else 'FAIL'))
    sys.exit(0 if res['ok'] else 1)


if __name__ == '__main__':
    main()
