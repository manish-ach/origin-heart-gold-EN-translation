# Main difficulty input compatibility review — 2026-10-13

Difficulty's installer pinned the rc8 standard build. Main after rc8 (commit
425c1ee, merged into `feature/advanced-ai` as dc7a1d3) builds a different
standard ROM, which the installer refused. This review attributes every
difference that touches difficulty's guarded inputs, then re-pins difficulty to
main's standard build. The model is
`work/notes/rc8_difficulty_compatibility_20261013.md`.

| Build | Path | SHA-256 | SHA-1 |
|---|---|---|---|
| rc8 standard (old pin) | `work/build/advanced-ai/base/rc8_standard.nds` | `f23e2263…4d492d` | `5e09a688…` |
| main standard (new pin) | `work/build/advanced-ai/base/main_standard.nds`, same bytes as this worktree's `work/build/origin_hg_v4.0.3_en_wip.nds` | `96793c39…6ded3c3c` | `cc57552d…` |

Each figure below can be reproduced by comparing the two ROMs with
`install.sections()`.

## Result

**Unchanged:**
- all 46 hook and edit sites (24 compatibility edits plus the hooks), each
  still holding its `before` bytes;
- the 18 dependency ranges;
- the 3 item-frame ranges, the 10 item-ownership ranges and the revival pins;
- overlays 9, 14 and 50 byte for byte (`OV_PINS` and the overlay 50
  whole-file guard still match);
- every other overlay, the overlay table and every overlay's RAM address,
  sizes, static initialisers and compression flag;
- ARM7 and its overlay table, DTCM and the banner;
- ARM9's size and BSS bounds (0x021106A0, 0x021E4980);
- the main arena words: 0x020D1A1C = 0x02264920 and 0x020D1970 = 0x023E0000.

**Changed:**
- ARM9 at 4 spans;
- ITCM, which keeps all 4,032 rc8 bytes and grows to 4,416;
- 5 of 551 files: `a/0/2/7` (text), `a/0/6/8`, `battle/string/battle_string.narc`,
  `data/clothes1/a068.narc` and `data/clothes2/a068.narc`.

No difficulty guard covers any of these files. The item archive `a/0/1/7` and
the trainer archive `a/0/5/5` are unchanged.

## Changed spans and their source

ARM9 (4 spans):

| Address | Bytes | Change | Nearest difficulty guard |
|---|---|---|---|
| 0x02000BA0, 0x02000BA4 | 2 + 2 | Autoload table start and end (ITCM is longer) | dependency "native held-key reference" 0x020021D8, 5,682 bytes away |
| 0x0202703C | 8 | Trainer-display trampoline `ldr r3,=0x01FF8FC1; bx r3`, replacing `f8b50c1c0090201c` | dependency "String copy" 0x02026EB8–0x02026F1C, 288 bytes away |
| 0x020D1A28 | 2 | ITCM arena start 0x01FF8FC0 → 0x01FF9140 | edit "reserve resident memory below ARM7" 0x020D1970, 180 bytes away |

ITCM: 0x01FF8000–0x01FF8FC0 is byte-identical to rc8. The new range
0x01FF8FC0–0x01FF9140 holds the trainer-display payload, D-2487 and
`work/tools/trainer_display.py`. It is 372 bytes; the sha256 of those bytes
equals `payload_sha256` in `work/build/build_report.json`, and the rest is zero
padding.

## Analysis of the code changes

**Trainer display.** In rc8, 0x0202703C is the entry of the String routine
that appends a String: `push {r3-r7,lr}`, then a call to the String check at
0x02027024. Main overwrites its first 8 bytes with a jump to the ITCM formatter.
The formatter:
- acts only when the source String holds 5 units that equal one of the five
  packed trainer keys (IDs 17, 59, 632, 666, 745);
- in that case, appends the full name if it fits the destination;
- otherwise replays the overwritten prologue and resumes at 0x02027045;
- calls nothing, and reads only the two Strings and its own table.

Effect on difficulty:
- None of the 84 native addresses in difficulty's C and ASM sources lies in the
  trampoline, the String routine 0x02027024–0x020270C0, the arena word, the
  autoload table or the new ITCM range. The nearest are the String routines
  0x02026865 (allocate), 0x02026891 (free) and 0x02026EB9 (copy characters),
  which are unchanged.
- Native routines that difficulty calls may append Strings internally, for
  example loading the Confirm and Quit labels (0x0200BB0D). Their results
  change only for the five packed trainer keys, which the Options page never
  uses.

**ITCM growth.** All five difficulty ITCM edits lie in the unchanged prefix,
each still holding its rc8 bytes:
- 0x01FF8766 print_task;
- 0x01FF8A1E load_rows;
- 0x01FF8AC4 commit_speed;
- 0x01FF8AF8 exit_free;
- 0x01FF8C2E pass_end.

The TEXT SPEED payload (`itcm_contract`, 0x01FF8620, 2,460 bytes) is
unchanged. So are its callers that difficulty uses (0x01FF8A0D, 0x01FF8B35).
The new code does not reference any of them.

**Arena word.** 0x020D1A28 is the ITCM arena start. Difficulty does not edit
it; its installer only checks it as a layout guard. Difficulty's main-RAM
reservation (0x023DC000–0x023E0000, via 0x020D1970) is unaffected.

**Install outcome.** A development build of difficulty on main (sha256
`5cdbe793…`) writes exactly the same bytes as the same sources on rc8 (sha256
`8ba9489c…`):
- the same resident autoload payload;
- the same ARM9, ITCM and overlay 9/14/50 deltas, apart from autoload
  bookkeeping;
- the same three changed files.

`verify.py` passes. The 53 negative checks reject as before.

## Pins revised (only after this review)

- `install.py`:
  - `INPUT_SHA` f23e2263 → 96793c39;
  - ITCM arena extent check 0x01FF8FC0 → 0x01FF9140;
  - autoload sizes `(4032,0)` → `(4416,0)`;
  - the receipt's `input_selection` label.
- `compatibility.json`:
  - `full_input_guards.en.arm9` 4b55c2e7 → 90ac2b2e;
  - `full_input_guards.en.itcm` 4032 bytes, b52c94de → 4416 bytes, e738fb11;
  - `roms.en` path and sha256 → main;
  - `itcm_contract.unaltered_extent_end` 0x01ff8fc0 → 0x01ff9140. Difficulty
    still alters only the 5 mask bytes in that extent.
- `research/items-revival-pins.json`: `inputs.en` path and sha256 → main.
- `native/integration_contract.json` `source_overrides`, each keeping the old pin
  in its history:
  - `compatibility.json` 842cfa16 → 2fa020c4;
  - `work/tools/text_speed_patch.py` 833852ba → bdc5a9ee. Main's `verify()`
    takes an optional `native_tail` so the trainer-display payload may follow
    TEXT SPEED in ITCM. TEXT SPEED's sources and payload are unchanged, and
    difficulty does not call `verify()`.

`OV_PINS`, the overlay 50 guard, the item, binding and revival ranges, the
hook and edit `before` bytes, and the dependency hashes are unchanged. No hook
guard, overlap check, memory limit, source or tool check, or logical-preservation
check was disabled.

## One accepted input per version

The installer still accepts exactly one standard build: main's. The rc8 standard
build is now refused with "completed-English full ROM guard", in both modes. To
rebuild rc8, use the `v1.0.0-rc8` tag, whose sources pin f23e2263.

## Not established

- Static compatibility and a development build only. The 79 required native
  difficulty cases (`tests/required_native.json`) have not been run on main's
  input (0/79).
- No release-tool build was made; this machine's tools differ from the pins
  (`research/dev-tools-mode.md`).
- Native evidence on the development build: `options_trainer_ai.py` 14/14 and
  `options_flags_free.py` pass.
- The advanced AI's planned ITCM region starts at 0x01FF8FC0
  (`work/advanced-ai/docs/memory-layout.md`, option A), where main now places
  the trainer-display payload. That is for the AI layout to resolve, not for
  difficulty.
