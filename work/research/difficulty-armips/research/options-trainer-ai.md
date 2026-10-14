# TRAINER AI row on Options page 2

2026-10-13. Phase 4 of the advanced trainer AI port (`work/advanced-ai/PLAN.md`,
decision 4). Page 2 gains a fourth row, TRAINER AI, with three values: OFF,
KEY (important trainers only) and ALL. The row only stores the setting. The AI
that reads it is installed later by `work/advanced-ai/builder/install.py`; the
row works the same with or without it.

## Storage

Two saved event flags, not the Options word (`work/advanced-ai/docs/build-contract.md`, Settings):

| Value | 0x2C2 | 0x2C3 |
|---|---|---|
| OFF | clear | clear |
| ALL | set | clear |
| KEY | set | set |

Reading ignores 0x2C3 when 0x2C2 is clear, so the stray pair (0x2C2 clear,
0x2C3 set) shows OFF. Writing always stores the pair above: OFF clears both, as
the Spanish build's Pokémon Centre NPC did, and Confirm rewrites a stray pair
even when the row was not changed. Codec: `dg_ai_decode` and `dg_ai_encode` in
`native/settings.c`.

The row reads and writes the flags through the hack's own routines, the same
path the AI's selector reads (disassembly of the rc8 standard build):

| Address | Routine | Body |
|---|---|---|
| 0x02001194 | GetSaveData | `ldr r0,=0x021106A8; ldr r0,[r0,#0x20]` |
| 0x0204F858 | Save_VarsFlags_Get | `SaveArray_Get(save, 4)` (0x02027740) |
| 0x0204F864 | CheckFlag(vars, flag) | GetFlagAddr, then tests bit `flag & 7`; returns 0 or 1 |
| 0x0204F890 | SetFlag(vars, flag) | GetFlagAddr, then ORs the bit into the byte |
| 0x0204F8B8 | ClearFlag(vars, flag) | GetFlagAddr, then ANDs the byte with the inverted bit |
| 0x0204F8E4 | GetFlagAddr | `vars + 0x2E0 + flag / 8` for flags below 0x4000; null for flag 0 |

The emulator check hooks SetFlag and ClearFlag. Every write it sees for 0x2C2
or 0x2C3 comes from the difficulty resident code, and the harness reads the
result through its own SaveData global (0x021D11B4), which holds the same
pointer as GetSaveData's.

## Why flags 0x2C2 and 0x2C3 are free

`work/advanced-ai/testbench/checks/options_flags_free.py` (no emulator) gives the
same result on the untouched Chinese ROM, the rc8 English standard build and the
development difficulty build:

- **Scripts** (`a/0/1/2`): 966 files, of which 963 decode as scripts. The
  Chinese ROM has 292,869 reachable instructions; rc8 has 292,930, because its
  fixes add some. No SetFlag, ClearFlag or CheckFlag names 706 or 707. Other
  commands carry 706 or 707 only as plain values: GoTo and movement offsets,
  `CompareVarToValue(0x8005, 706/707)` and `PlayerHasSpecies`.
- **Map objects** (`a/0/3/2`): none of the 6,731 objects uses 706 or 707 as its
  hide flag. A hide flag would count as a writer, because removing the object
  sets it.
- **Vanilla US HeartGold** did use both flags: script 832 sets and clears them,
  and map events 355 has two objects that hide with them. The hack has no such
  uses. The US scan is only for this comparison, because the hack's command
  table decodes less of the US scripts.
- **Code**: the only literal 0x2C2/0x2C3 words in ARM9, ITCM and all overlays
  are three in overlay 14 and one in overlay 77. One (0x0221B39C) feeds a battle
  routine at 0x02229E1C, not a flag routine. No pc-relative load reaches the
  other three, which are table data. Constants that the compiler builds with
  arithmetic are not covered by this search. The setter at 0x0203FC70 and the
  clearer at 0x0203FC88 use flag 0x550 + n, so their flags start at 1360.

Seven commands take their flag from a variable, all in three files. Each is
bounded:

| File (script IDs) | Commands | Variable | Flags |
|---|---|---|---|
| 145 (hidden items, 8000–8799) | SetFlagVar | 0x8006, copied from 0x8002, which the engine sets | 800–1030 |
| 151 (Bug-Catching Contest) | SetFlagVar, ClearFlagVar | 0x8005 or 0x8006 = 627 + a loop counter 0–9 | 627–636 |
| 948 (Trainer House), script 10350 | SetFlagVar, ClearFlagVar | 0x4001 = 653 + a loop counter 0–9; 663 at loop exit | 653–663 |
| 948, scripts 10351–10361 | CheckFlagVar, SetFlagVar | 0x4001 = 2730 + 0x4000, which each script sets to 0–10 | 2730–2740 (or 653–663, below) |

- **Hidden items.** Starting any script 8000–8799 calls 0x0203FCE8 (from
  0x0203F796–0x0203F7A8). It looks up script − 8000 in the 231-row table at
  0x020F7194 and writes 0x8000 = item, 0x8001 = quantity, and 0x8002 = script −
  7200 (0x0203FC98). File 145's single entry copies 0x8002 to 0x8006 and sets
  that flag. The table indices are 0–230, so the flag is 800–1030. All 215
  hidden-item BG events use scripts 8000–8230 and have a table row. No map
  object, coordinate trigger or CallStd starts a script in 8000–8799. If the
  lookup failed, the prep would assert and write nothing; no event reaches that
  path.
- **Trainer House, pc 382.** This command sets the flag after the battle that
  0x4001 was computed for. 0x4001 is a general-purpose variable that 1,335
  instructions name. Only these scripts can run on the map (zone 499, Frontier
  Access) during that battle:
  - header script 10350 (type 2), which leaves 0x4001 at 653–663;
  - frame-table scripts 3 and 4 of file 746, and the std script 2006 they call,
    which never name 0x4001.

  The flag at pc 382 is therefore 2730–2740, or 653–663 if script 10350 ran
  during the battle.

The check fails if any of these change: a flag command or map object names
706/707; the seven sites change; scripts 145, 151 or 948 differ from the
Chinese hack's; or the hidden-item prep code changes. On vanilla US it fails as
expected.

## Transaction

The row joins the existing draft/apply/cancel transaction (`native/options.c`).

- Opening Options reads the stored pair once into `page.ai_stored` and decodes
  it into `page.ai_draft`.
- Changing the row changes only the draft.
- Confirm (APPLY) writes both flags at exit when the draft's pair differs from
  the stored pair. That includes an unchanged OFF over the stray pair. It
  writes them only after the Options word's own apply has succeeded.
- If the stored pair changed while the page was open, Apply is refused on the page
  (the help shows the existing "Settings changed" message) and again at exit
  (`DG_SETTINGS_STALE`). Nothing is written in either case.
- Back, B and Cancel discard the draft. Confirm on page 1 also commits the
  page-2 draft, as for the other difficulty rows.
- Saving is the player's normal Save. There is no auto-save.

## Layout

Rows keep the native 20-pixel pitch. TRAINER AI is drawn at window y 65, the
native row-3 position, so the native red outline (021E5944, BG0 scroll table
by row) frames it with no change.

The row cannot borrow native slot 3 the way rows 0–2 borrow slots 0–2: the
native renderer 021E53EC runs a preview for slot 3 (0x0200589C calls
0x020C6CA4 with the value and stores it at 0x021CF438). The row is therefore drawn with
the renderer's own steps:

1. Erase the value area: `0x0201E2A4(window, 0x22, 108, 65, 320, 20)`.
2. Print OFF, KEY and ALL at x 108, 156 and 204 (the 48-pixel pitch of native
   rows 0 and 1). The chosen value uses the SELECTED colour.

The emulator check confirms that 0x0200589C never runs while page 2 is shown.

| Input | Effect |
|---|---|
| Up, Down | Six positions, wrapping: the four rows, CANCEL (right button), APPLY (left button, CONFIRM) |
| Left on the row | Previous value, wrapping |
| Right or A on the row | Next value, wrapping |
| Touch y 82–101 | x 108–159 OFF, 160–207 KEY, 208–247 ALL; x 8–107 moves the focus only |

## Text

| Text | Width (font 0) | Space |
|---|---|---|
| `TRAINER AI` | 58 | 104 (x 4–107) |
| `OFF`, `KEY`, `ALL` | 18 each | 44 (48-pixel pitch) |
| `Advanced AI: OFF for no trainers, KEY` | 204 | 212 (help line 1) |
| `for important trainers, ALL for all.` | 192 | 212 (help line 2) |

Widths are from `work/tools/font_widths.json`; both font sets give the same
values. The help needs a comma, so `glyph()` now maps `,` to 0x1AD (charmap.tbl).
The labels follow the plan's OFF / KEY / ALL, which is still marked "labels to confirm".

## Binary layout

`page` gains two words at its end: `ai_stored` (bit0 0x2C2, bit1 0x2C3) at +352
and `ai_draft` at +356.
The struct is now 360 bytes. Earlier offsets that native test drivers read
(+24, +36, +48, +52, +336) are unchanged. With Apple clang 17 the resident
section grows from 8940 to 9824 bytes of the 16 KiB reservation.

## Related change: difficulty's pointer check

The advanced AI places resident code at 0x023D4000–0x023DC000
(`work/advanced-ai/docs/memory-layout.md`). Difficulty's pointer checks treated
everything below 0x023DC000 as data: `dg_runtime_ram` (`native/runtime.c`, also
used by `caps.c`) and `RAM_END` (`native/items.c`). They now end at 0x023D4000,
so a pointer into the AI's code is refused. Neither file has a source pin in
`options-source-pins.json`, so no source override applies. The host drivers
check both edges, and they fail with the old bound restored.

## Tests

- Host: `tests/drivers/options_check.c` (ASan/UBSan) covers:
  - the codec;
  - the four flag pairs with B, touch Cancel and an unchanged Apply, none of
    which writes, except that Apply rewrites the stray pair;
  - the D-pad walk over six positions and the native cursor row;
  - Left, Right and A wrapping;
  - touch band edges;
  - the help text;
  - shared Confirm and B from page 1;
  - flags changed before Apply and at exit, and an Options word changed at
    exit, none of which writes.

  Fourteen scratch mutants of the row are all rejected. They include writing on
  Cancel, the wrong touch band, no stale check, writing after a failed word
  apply, and comparing values instead of pairs.
- Native: `work/advanced-ai/testbench/checks/options_trainer_ai.py`, 14 cases on
  the development build, including the stray pair, and save and reload in a
  second emulator process.
- Static: `work/advanced-ai/testbench/checks/options_flags_free.py` (see above).
- The difficulty suite's native UI driver now walks six focus positions
  (`tests/support.py` `FOCUS_COUNT`, `native_ui.py`, `evidence.py`,
  `native_ui_oracles.py`, `test_framework.py`). That driver needs
  `work/build/memcheck/*.sav` and the save core, so it was not run here.
