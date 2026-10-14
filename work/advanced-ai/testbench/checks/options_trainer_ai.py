#!/usr/bin/env python3
"""TRAINER AI row on Options page 2: native check in the emulator.

Drives the real Options screen (held-L entry, and page 1 then R), changes the row
with the D-pad and touch, applies and cancels, saves with the field menu, and
reloads the saved battery in a second emulator process. The oracle is the pair
of saved flags 0x2C2/0x2C3 read from RAM by the harness (its own SaveData path,
not the page's), plus traces of the hack's SetFlag/ClearFlag calls.

Works on a difficulty build with or without the advanced AI installed: the AI
installer leaves difficulty's resident section unchanged, and the check verifies
that section against --receipt before it trusts the receipt's symbols.

Run from the repository root, one emulator at a time:

  .venv/bin/python work/advanced-ai/testbench/checks/options_trainer_ai.py \\
      --rom work/build/advanced-ai/options/difficulty_dev.nds

The battery (--sav) must Continue into the field with the touch menu available.
The default is made from the Spanish workspace's committed test save:
  git -C <Spanish repo> show dc8577c:work_es/tests/starter.dsv | head -c 524288 \\
      > work/build/advanced-ai/options/field.sav
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'work/tools'))
OUT = ROOT / 'work/build/advanced-ai/options'

FLAG_ON, FLAG_KEY = 0x2C2, 0x2C3
SET_FLAG, CLEAR_FLAG = 0x0204F890, 0x0204F8B8      # Thumb, next to CheckFlag 0x0204F864
ROW3_PREVIEW = 0x0200589C                         # native slot-3 preview the row must never run
RESIDENT, RESIDENT_END = 0x023DC000, 0x023E0000
OFF, KEY, ALL = 0, 1, 2
NAMES = ('OFF', 'KEY', 'ALL')
# page struct (native/options.c): +24 state, +36 focus, +48 mode, +352 ai_stored (bit0 0x2C2,
# bit1 0x2C3), +356 ai_draft.
PAGE_SIZE, STATE, FOCUS, MODE, AI_STORED, AI_DRAFT = 360, 24, 36, 48, 352, 356
# Screen touch points: TRAINER AI row band y 82..101, value bands x 108..159/160..207/208..247.
ROW_Y = 91
VALUE_X = {OFF: 128, KEY: 180, ALL: 220}
APPLY, CANCEL = (149, 180), (200, 180)
OPTIONS_ICON, SAVE_ICON = (123, 113), (123, 73)

# Strings the row draws; each must appear verbatim in options.c and fit its space.
LABELS = {'TRAINER AI': 104, 'OFF': 44, 'KEY': 44, 'ALL': 44,
          'Advanced AI: OFF for no trainers, KEY': 212, 'for important trainers, ALL for all.': 212}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(on, key):
    return OFF if not on else KEY if key else ALL


def label_widths():
    """Font 0 advances from work/tools/font_widths.json (both sets), against the
    space each string has: label x 4..107, values at a 48-pixel pitch, help 212."""
    fonts = json.loads((ROOT / 'work/tools/font_widths.json').read_text())['font_sets']
    source = (ROOT / 'work/research/difficulty-armips/native/options.c').read_text()
    rows = {}
    for text, limit in LABELS.items():
        assert f'"{text}"' in source, f'options.c no longer draws {text!r}'
        widths = {}
        for name, fs in fonts.items():
            f = fs['fonts']['0']
            widths[name] = sum(f['widths'].get(c, f['default_width']) for c in text)
        rows[text] = dict(widths=widths, limit=limit)
        assert max(widths.values()) <= limit, (text, widths, limit)
    return rows


def resident_symbols(rom_path, receipt_path):
    import ndspy.rom
    receipt = json.loads(Path(receipt_path).read_text())
    sections = ndspy.rom.NintendoDSRom.fromFile(rom_path).loadArm9().sections
    resident = next(bytes(s.data) for s in sections if s.ramAddress == RESIDENT)
    expected = receipt['build_artifacts']['resident.bin']
    assert hashlib.sha256(resident).hexdigest() == expected['sha256'], \
        'the ROM does not carry the difficulty resident section this receipt describes'
    page = next(s for s in receipt['build']['symbols'] if s['name'] == 'page')
    assert page['size'] == PAGE_SIZE, ('page layout changed', page['size'])
    return dict(page=page['value'], resident=resident, receipt=receipt)


class Check:
    def __init__(self, h, out, page, result):
        self.h, self.out, self.page, self.result = h, out, page, result
        self.writes, self.previews, self.shots = [], [], []
        h.on_exec(SET_FLAG, self.flag_call(True))
        h.on_exec(CLEAR_FLAG, self.flag_call(False))
        h.on_exec(ROW3_PREVIEW, self.preview)

    def flag_call(self, value):
        def record(h):
            flag = getattr(h.reg, 'r', h.reg)[1] & 0xFFFF   # py-desmume indexes the accessor itself
            if flag in (FLAG_ON, FLAG_KEY):
                self.writes.append(dict(flag=flag, value=value, lr=h.reg.lr & 0xFFFFFFFF, frame=h.frame))
        return record

    def preview(self, h):
        if h.u32(self.page + STATE):
            self.previews.append(dict(frame=h.frame, mode=h.u32(self.page + MODE), lr=h.reg.lr & 0xFFFFFFFF))

    def flags(self):
        return (self.h.get_flag(FLAG_ON), self.h.get_flag(FLAG_KEY))

    def shot(self, name):
        path = self.h.screenshot(name)
        self.shots.append(dict(name=name, path=str(path), sha256=sha256(path)))

    def open(self, page2=True):
        h = self.h
        assert h.in_field() and not h.u32(self.page + STATE), 'Options must open from the field'
        if page2:
            h.hold('L'); h.step(2)
        h.touch(*OPTIONS_ICON, frames=6, after=240)
        if page2:
            h.release('L')
        h.step(60)
        assert h.u32(self.page + STATE), 'Options page did not open'
        assert h.u32(self.page + MODE) == int(page2), 'wrong page'

    def draft(self):
        return self.h.u32(self.page + AI_DRAFT)

    def focus(self):
        return self.h.u32(self.page + FOCUS)

    def to_row(self):
        for _ in range(3):
            self.h.press('DOWN', after=30)
        assert self.focus() == 3, ('focus', self.focus())

    def closed(self):
        self.h.step(240)
        assert self.h.run_until(lambda h: h.in_field() and not h.u32(self.page + STATE), 600, every=10), \
            'Options did not close'

    def expect(self, case, flags, writes, **extra):
        """flags: (0x2C2, 0x2C3) now; writes: the SetFlag/ClearFlag calls since the case began."""
        got = self.flags()
        calls = [(w['flag'], w['value']) for w in self.writes[self.mark:]]
        assert got == flags, (case, 'flags', got, flags)
        assert sorted(calls) == sorted(writes), (case, 'flag calls', calls, writes)
        assert all(RESIDENT <= w['lr'] < RESIDENT_END for w in self.writes[self.mark:]), (case, 'caller')
        self.result['cases'][case] = dict(status='passed', flags=list(got), flag_calls=calls, **extra)

    def begin(self, flags=None):
        if flags is not None:
            for flag, value in zip((FLAG_ON, FLAG_KEY), flags):
                self.h.set_flag(flag, bool(value))
        self.mark = len(self.writes)


def phase_a(args, sym, out, result):
    from emu_harness import Harness
    with Harness(rom=args.rom, sav=args.sav, out=out, verbose=False, emulator='desmume') as h:
        h.boot_to_menu(); h.continue_game()
        assert h.in_field(), 'battery did not continue into the field'
        # GetSaveData's global (0x021106A8+0x20, the row's path) is the harness's SaveData.
        assert h.u32(0x021106C8) == h.save, 'GetSaveData and the harness disagree on SaveData'
        c = Check(h, out, sym['page'], result)
        result['initial_flags'] = list(c.flags())
        c.shot('field')

        # Every stored pair shows its value; B writes nothing.
        for on, key in ((0, 0), (0, 1), (1, 0), (1, 1)):
            c.begin((on, key)); c.open()
            value = decode(on, key)
            assert h.u32(c.page + AI_STORED) == on | key << 1 and c.draft() == value
            c.shot(f'decode-{on}{key}-{NAMES[value].lower()}')
            h.press('B'); c.closed()
            c.expect(f'decode_{on}{key}', (bool(on), bool(key)), [], shown=NAMES[value])

        # D-pad: reach the row, RIGHT/RIGHT/LEFT, DOWN twice to APPLY, A.
        # Confirm without a change turns the stray pair (0x2C2 clear, 0x2C3 set) into canonical OFF.
        c.begin((0, 1)); c.open(); assert c.draft() == OFF
        h.touch(*APPLY); c.closed()
        c.expect('stray_pair_confirm_canonical_off', (False, False), [(FLAG_ON, False), (FLAG_KEY, False)])

        c.begin((0, 0)); c.open(); c.to_row(); c.shot('dpad-focus-trainer-ai')
        for key, value in (('RIGHT', KEY), ('RIGHT', ALL), ('LEFT', KEY)):
            h.press(key, after=30)
            assert c.draft() == value and c.flags() == (False, False), 'draft changed the flags'
            c.shot(f'dpad-{key.lower()}-draft-{NAMES[value].lower()}')
        h.press('DOWN', after=30); h.press('DOWN', after=30)
        assert c.focus() == 5; c.shot('dpad-focus-apply')
        h.press('A'); c.closed(); c.shot('dpad-applied-key')
        c.expect('dpad_apply_key', (True, True), [(FLAG_ON, True), (FLAG_KEY, True)])

        # B cancels a changed draft.
        c.begin(); c.open(); assert c.draft() == KEY
        c.to_row(); h.press('RIGHT', after=30); assert c.draft() == ALL
        c.shot('b-cancel-draft-all'); h.press('B'); c.closed()
        c.expect('b_cancel', (True, True), [])

        # Touch a value, then touch Apply.
        c.begin(); c.open()
        h.touch(VALUE_X[ALL], ROW_Y, after=30)
        assert c.focus() == 3 and c.draft() == ALL; c.shot('touch-draft-all')
        h.touch(*APPLY); c.closed(); c.shot('touch-applied-all')
        c.expect('touch_apply_all', (True, False), [(FLAG_ON, True), (FLAG_KEY, False)])

        # Touch a value, then touch Cancel.
        c.begin(); c.open()
        h.touch(VALUE_X[OFF], ROW_Y, after=30); assert c.draft() == OFF; c.shot('touch-draft-off')
        h.touch(*CANCEL); c.closed()
        c.expect('touch_cancel', (True, False), [])

        # Page 1 entry: R to page 2, change the row, L back, Confirm on page 1.
        c.begin(); c.open(page2=False); h.press('R', after=30)
        assert h.u32(c.page + MODE) == 1
        c.to_row(); h.press('RIGHT', after=30); assert c.draft() == OFF
        h.press('L', after=30); assert h.u32(c.page + MODE) == 0
        c.shot('page1-holding-ai-draft-off'); h.touch(*APPLY); c.closed()
        c.expect('page1_confirm_off', (False, False), [(FLAG_ON, False), (FLAG_KEY, False)])

        # The native slot-3 preview never ran while page 2 was shown.
        assert not [p for p in c.previews if p['mode'] == 1], c.previews
        result['cases']['no_row3_preview_on_page2'] = dict(status='passed', page1_preview_calls=len(c.previews))

        # Save KEY with the field menu, then apply OFF without saving.
        c.begin(); c.open(); h.touch(VALUE_X[KEY], ROW_Y, after=30); h.touch(*APPLY); c.closed()
        c.expect('apply_key_before_save', (True, True), [(FLAG_ON, True), (FLAG_KEY, True)])
        h.touch(*SAVE_ICON, after=120)
        for _ in range(3):
            h.press('A', after=180)
        h.step(1200); c.shot('saved-key')
        saved = out / 'saved-key.sav'
        assert h.emu.backup.export_file(str(saved)), 'battery export failed'
        result['saved_battery'] = dict(path=str(saved), sha256=sha256(saved))
        h.press('B', after=120)
        assert h.run_until(lambda h: h.in_field() and not h.u32(c.page + STATE), 600, every=10)
        c.begin(); c.open(); h.touch(VALUE_X[OFF], ROW_Y, after=30); h.touch(*APPLY); c.closed()
        c.expect('apply_off_unsaved', (False, False), [(FLAG_ON, False), (FLAG_KEY, False)])
        result['shots'] = c.shots
        return saved


def phase_b(args, sym, out, result):
    """A fresh process boots the battery that phase A saved (py-desmume holds one
    emulator per process)."""
    from emu_harness import Harness
    with Harness(rom=args.rom, sav=args.sav, out=out, verbose=False, emulator='desmume') as h:
        h.boot_to_menu(); h.continue_game()
        c = Check(h, out, sym['page'], result)
        c.begin()
        assert c.flags() == (True, True), ('reload lost the saved setting', c.flags())
        c.open(); assert c.draft() == KEY; c.shot('reload-shows-key')
        h.press('B'); c.closed()
        c.expect('save_reload_key', (True, True), [])
        result['shots'] = c.shots


def reload_child(args, receipt, out, saved, result):
    import subprocess
    child = subprocess.run([sys.executable, __file__, '--phase', 'reload', '--rom', args.rom, '--receipt', receipt,
                            '--sav', saved, '--out', out], cwd=ROOT, capture_output=True, text=True, timeout=600)
    (out / 'reload.log').write_text(child.stdout + child.stderr)
    reload = json.loads((out / 'reload-result.json').read_text())
    assert child.returncode == 0 and reload['status'] == 'passed', ('reload phase', child.returncode, reload.get('failure'))
    result['cases'].update(reload['cases'])
    result['shots'] += reload['shots']


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--receipt', type=Path, help='difficulty receipt (default: <rom>.receipt.json beside the ROM)')
    p.add_argument('--sav', type=Path, default=OUT / 'field.sav')
    p.add_argument('--out', type=Path, default=OUT / 'native')
    p.add_argument('--phase', choices=('all', 'reload'), default='all', help='reload: internal, the second process')
    args = p.parse_args()
    args.rom = args.rom.resolve()
    receipt = (args.receipt or args.rom.with_suffix('.receipt.json')).resolve()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    result = dict(status='running', check='options_trainer_ai',
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  rom=dict(path=str(args.rom), sha256=sha256(args.rom)),
                  battery=dict(path=str(args.sav), sha256=sha256(args.sav)),
                  receipt=dict(path=str(receipt), sha256=sha256(receipt)), cases={})
    try:
        result['labels'] = label_widths()
        sym = resident_symbols(args.rom, receipt)
        result['tool_mode'] = sym['receipt'].get('tool_mode', 'release')
        if args.phase == 'reload':
            phase_b(args, sym, out, result)
        else:
            saved = phase_a(args, sym, out, result)
            reload_child(args, receipt, out, saved, result)
        assert sha256(args.sav) == result['battery']['sha256'], 'source battery changed'
        result['status'] = 'passed'
    except BaseException:
        result.update(status='failed', failure=traceback.format_exc())
    finally:
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        name = 'reload-result.json' if args.phase == 'reload' else 'result.json'
        (out / name).write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['status']}: {sum(v['status'] == 'passed' for v in result['cases'].values())} cases; {out / 'result.json'}")
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
