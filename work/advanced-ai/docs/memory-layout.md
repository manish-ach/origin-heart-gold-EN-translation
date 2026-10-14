# Memory layout of the advanced AI (phase 0)

Measured 2026-10-13 on the English rc8 release (`work/build/advanced-ai/base/rc8_release.nds`, SHA-1 `a54a6475…`),
the standard build plus difficulty. This answers PLAN.md phase 0: can the AI's resident code go in the ITCM arena
(option A), or must it all go in main RAM (option B)?

**Decision: option A.** Nothing allocates from the ITCM arena or writes to it, and the main arena has 110,228 bytes
that nothing uses after boot. Option A takes 32 KB of them. No game heap gets smaller with either option.

Updated after the merge of `main` (trainer full names, `work/tools/trainer_display.py`): the AI's `itcm` region now
starts at a fixed origin, 0x01FF9500, with headroom above every input's ITCM code. See "The ITCM origin". The ITCM
arena measurement was repeated on main's standard build.

## Final layout

| Region | RAM | Size | What is there | Written by |
|---|---|---|---|---|
| Overlay 10 | 0x021E4DA0–0x021FF8A0 | file 0x12080 + 32,800 B, bss 0xA60 (3,904 B of the slot free) | Overlay 11's image and its 0x20-byte bss, then the slot code from 0x021F6E20 (`adv_entry` first). Loaded into the battle slot in place of overlay 11 | y9 entry 10, ROM file 10 |
| The input's ITCM code | 0x01FF8000 to its end: 0x01FF8FC0 in the rc8 release (the hack's block and text speed), 0x01FF9140 in main's English build (and trainer display; at most 0x01FF9320 in any locale) | – | Kept as the input has it | – |
| Headroom | the input's ITCM end to 0x01FF9500 (1,344 B with rc8, 960 B with main) | – | Empty; nothing writes it | – |
| `itcm` | 0x01FF9500–0x01FFECAC (limit 0x01FFEE00, 340 B free); its bss 0x01FFECAC–0x01FFFDD8 | 22,444 B, bss 0x112C (4,396 B) | Resident AI code: `aiselect.s`, `check_flag`, `ai_replace`, `g_tune`, libgcc, shared AI code | new autoload section 5 |
| `itcm_ram` | 0x01FFEE00–0x01FFFDD8 (limit 0x01FFFF8C, 436 B free) | 4,056 B | The AI's work RAM (`.itcm_bss`), inside the `itcm` section's bss, so every boot zeroes it | autoload section 5's bss |
| Fixed records | 0x01FFFF8C–0x01FFFFFF | 116 B | Foresight word, NOREAD, NOLEAD, Read and Replaced records, SELFPLAY (`engine.h`) | – |
| `main` | 0x023D4000–0x023DA4B8 (limit 0x023DC000, 6,984 B free) | 25,784 B, no bss | Resident AI code: `ai_lead` first, and what no longer fits ITCM | new autoload section 6 |
| Difficulty (unchanged) | 0x023DC000–0x023DE1E0 (rc8; the development build with the TRAINER AI row: –0x023DE660), below 0x023E0000 | 8,672 B (rc8) | Difficulty's resident code | autoload section 4 |

| Word | Before | After | Meaning |
|---|---|---|---|
| arm9 0x020D1A28 | the input's ITCM end (0x01FF8FC0 rc8, 0x01FF9140 main), at most 0x01FF9500 | 0x02000000 | Initial ITCM arena start: the arena is now empty |
| arm9 0x020D1970 | 0x023DC000 (difficulty) | 0x023D4000 | Initial main arena end: the arena now ends below region `main` |

The autoload table after installation is: ITCM block, DTCM, difficulty, AI `itcm`, AI `main`. The ARM9 start-up code
(crt0 at 0x02000800, autoload loop at 0x02000A1C) copies each section word by word and then zeroes its bss. It does
not clear ITCM otherwise, and a DS keeps ITCM across a soft reset. So the `itcm` section's bss runs from the end of
its code through `.itcm_bss` (0x01FFECAC–0x01FFFDD8): every boot zeroes the AI's work RAM, as C expects of `.bss`
(the Spanish build had no such bss and relied on the emulator's zeroed ITCM and on tags). The bss stops before the
fixed records at 0x01FFFF8C, which the test tools write and which keep their magic words. The installer refuses an
`itcm` bss that would reach them or that would not cover the work RAM, and the smoke test filled the bss range to
0x02000000 with 0xA5 before the first instruction: after boot the bss range was 0 and the records still 0xA5.

### The ITCM origin

Every byte the AI links is at an absolute address: the hooks' BLs, the slot code's BLs into ITCM, the literals for
`g_tune`. So one payload fits one `itcm` origin. The ITCM code before it is not the same in every input:

| Input | ITCM code | ITCM arena start word |
|---|---|---|
| rc8 release | the hack's 0x620-byte block and text speed, to 0x01FF8FC0 | 0x01FF8FC0 |
| main's English build | the same, then trainer display's formatter and names, to 0x01FF9140 | 0x01FF9140 |
| any locale of main | trainer display's names differ in length; the builder's worst case ends at 0x01FF9320 | its end |

The origin is fixed at 0x01FF9500, above the worst case with a margin, so one reviewed payload installs on all of
them. The installer accepts an input whose ITCM code (every autoload section in ITCM) ends at or below the origin and
whose ITCM arena start word equals that end (payload.json: `"before": "itcm_end", "before_max": "0x01FF9500"`). It
refuses any other input and records the end and the headroom in the receipt. The cost is ITCM room: the headroom
pushed about 1.6 KB of code from ITCM to the `main` region, which still has 6,984 B free.

## Main arena

### How the main arena is used

The game builds its heaps once, at boot. `InitHeapSystem` (0x0201AFDC) takes the four root heaps of the table at
arm9 0x020F2EAC from the main arena's low end, with fixed sizes:

| Root heap | Size | Arena |
|---|---|---|
| 0 | 0xD200 (53,760 B) | main |
| 1 | 0x2E600 (189,952 B) | main |
| 2 | 0x10 | main |
| 3 | 0x11D000 (1,167,360 B) | main |

Every other heap the game creates (the field, battle, Bag and summary heaps) is a child of these. So the root heaps'
size does not depend on the arena's end, and moving the end down costs no heap, as long as the arena still holds the
root heaps.

**Static check.** We found every call to the SDK arena functions in ARM9, ITCM, every autoload section and all 120
overlays (Thumb and ARM BL/BLX): `OS_GetArenaLo/Hi` 0x020D1898/0x020D1884, `OS_SetArenaLo/Hi`
0x020D1A4C/0x020D1A38, `OS_GetInitArenaLo/Hi` 0x020D1990/0x020D18AC and `OS_AllocFromArenaLo/Hi`
0x020D1A60/0x020D1ACC. The callers are:

| Caller | What it does |
|---|---|
| `OS_InitArena`, 0x020D1734–0x020D1840 | Sets every arena from the initial-bound literals at boot |
| Heap start-up, 0x0201AA28–0x0201AAE0 and 0x0201B00E–0x0201B076 | Allocates from the main arena's low end (arena 0) |
| 0x0201B082 | `OS_AllocFromArenaHi` on arena 2 (extended main RAM), only for a root heap marked arena 2. The table has none |
| Fatal-error screen 0x02095960 | Resets the main arena to its initial bounds and builds one small heap. It is called on an allocation failure (0x0201B2A6) or an assertion (`GF_AssertFail` 0x02025B3E). It reads the patched end, so it stays below the AI |
| Overlay 40, 0x022240CE | Sets the main arena's start inside an 8 KB block it took from a heap (an SDK OS heap). It does not change the end |

No caller uses arena 3 (ITCM). No code reads the arena table at 0x027FFDA0 except these functions. No literal
between 0x027FFDA0 and 0x027FFDE7 appears in ARM9.

**Measurement.** In DeSmuME, the main arena's bounds were sampled every 30 frames across the scenarios listed under
"Method":

| | Main arena start | Main arena end | Free |
|---|---|---|---|
| rc8 release, from boot to the end of every scenario | 0x023C116C | 0x023DC000 | 110,228 B, never less |
| With the AI installed (`smoke` run) | 0x023C1138 | 0x023D4000 | 77,512 B |

The start moved 0x02264920 → 0x023C116C at boot: the root heaps plus 16,444 bytes of heap tables and start-up
allocations. It did not move again in any scenario. Nothing took memory from the end.

### Option costs

| Option | Main arena given up | Free tail left after boot | Root heaps |
|---|---|---|---|
| A (this layout): 32 KB region `main` | 32,768 B | 77,460 B | unchanged |
| B: everything in main RAM (~24 KB `itcm` + 4 KB work RAM + 24 KB `main`, rounded to 52 KB) | ~53,248 B | ~56,980 B | unchanged |

Both are safe for the main arena. Option A is still better: it keeps more of the arena tail as margin, and the code
that runs on every AI poll executes from ITCM, as it did in every Spanish measurement.

The installer recomputes this. It refuses a layout if the new arena end minus the arena start is smaller than the
root heap table's sum plus the 16,444 bytes measured here. A later fix that enlarges a root heap would trip it.

### Heap headroom

Moving the arena end changes no heap, but these are the smallest spare rooms seen, for reference. Spare room is the
largest free block minus the request, at any allocation, using `memcheck.py`'s method. The heap sizes are the game's
own.

| Heap | Size | Smallest spare, rc8 release | Seen during |
|---|---|---|---|
| 0 (system) | 53,704 | 48,396 | wild battle |
| 3 (application root) | 1,167,304 | 127,188 | trainer card |
| 4 (field) | 802,760 | 132,100 | wild battle |
| 5 (battle) | 720,840 | 258,428 | double trainer battle |
| 6 (Bag) | 270,280 | 57,248 | Bag |
| 19 (summary) | 282,568 | 40,404 | summary from the party |

With the AI on (`smoke` run, 4 trainer battles), the battle heap's smallest spare was 308,128 B. The AI allocated its
4,016-byte decision context there. No allocation failed in any run.

## ITCM arena

ITCM is 0x01FF8000–0x02000000. In the rc8 release, ITCM holds the hack's 0x620-byte block plus text speed's code, up
to 0x01FF8FC0. The SDK's ITCM arena is the rest: 0x01FF8FC0–0x02000000, 28,736 bytes. In main's English build,
trainer display's code and names follow, to 0x01FF9140, and the arena is 0x01FF9140–0x02000000.

**Static check.** The only code that touches the ITCM arena is `OS_InitArena`, which sets its bounds at boot. No
code calls an arena function with arena 3. See the table above.

**Measurement** (rc8 release, 25,500 frames):

1. After boot, all 28,736 bytes of the region were still 0. DeSmuME clears ITCM at power-on, so nothing wrote it
   during boot or Continue.
2. A canary was written over the whole region: a different word at each address, `(addr × 0x9E3779B1) xor
   0xC0DECAFE`. It read back correctly, so emulator writes to ITCM stick.
3. A DeSmuME write hook was set over the whole region. As a positive control, a second hook watched text speed's
   frame state at 0x01FF8F80–0x01FF8FC0, which the game writes every frame.
4. The scenarios under "Method" were run.
5. Results:
   - The region hook fired **0** times. The control hook fired 68,020 times.
   - All 7,184 canary words were unchanged at the end.
   - The ITCM arena's bounds (0x027FFDAC/0x027FFDD0) stayed 0x01FF8FC0/0x02000000 throughout.

The same run on main's standard build (`base/main_standard.nds`, sha256 `96793c39…`; 25,806 frames) with
`testbench/checks/itcm_arena.py`, which now takes the arena from the ROM: the region 0x01FF9140–0x02000000 was 0 after
boot, its hook fired 0 times (control: 69,292), every canary word was unchanged and the arena bounds stayed
0x01FF9140/0x02000000. No allocation failed.

The Spanish build supports this too: it emptied the ITCM arena (start 0x02000000) and passed its full QA. A game
allocation from an empty arena would have returned NULL.

So option A's ITCM part is safe. After installation, the arena is empty (start = end = 0x02000000, measured in the
smoke run). On the AI builds, `itcm_arena.py` (with `--payload`) also checks the ITCM below the origin: across the same
scenarios with the AI on, the AI's code never wrote below 0x01FF9500, nothing wrote the headroom, and the kept ITCM
code (with trainer display on main) still equalled the ROM's at the end, except text speed's frame state.

## Overlay 10 and the battle slot

Overlay 10 replaces overlay 11 in the battle slot. The slot is the range of overlay 8, 0x021E4DA0–0x022007E0, and it
ends where overlay 14, the battle engine, starts. The new overlay 10, bss included, ends at 0x021FF8A0, so 3,904
bytes of the slot stay free.

Overlay 17 (the field Bag, 0x021F86E0–0x022007C0) overlaps the new overlay 10 but not overlay 11. It also overlaps
overlay 8, so it is never in RAM during a battle. The in-battle Bag uses its own slot overlay, and `ai_bag_check` and
`ai_resume` handle that. The installer and the verifier both enforce this rule: overlay 10 must lie inside overlay
8's range, and every overlay it overlaps must also overlap overlay 8.

## Method

The probe and smoke scripts are local tools in the ignored `work/build/advanced-ai/layout/`. They are not
committed.

| Script | What it does |
|---|---|
| `itcm_probe.py` | Canary, write hooks, arena sampling, heap spare room, and read watchpoints on trainer header byte 2 |
| `ai_smoke.py` | The AI smoke test: flags set in RAM, or set through the Options row with `--options` |
| `scan_calls.py` | Finds every BL/BLX to a list of addresses |

**Emulator.** DeSmuME through py-desmume 0.0.9 and `work/tools/emu_harness.py`, with the clock fixed at
2026-01-01 12:00.

**Save.** The Spanish workspace's `tests/violet_gym.dsv` (commit `dc8577c`), cut to its first 512 KB. It loads on the
English ROM: Violet City, a level 50–100 party. No English battery save existed locally. The harness's
`work/build/memcheck/` saves are not on this machine.

**Scenarios** (one run, 25,500 frames):

- Field:
  - walk;
  - the touch menu: Pokédex, party, summary (two pages), Bag, Pokégear, trainer card;
  - Options page 1 and page 2 (difficulty's);
  - save with overwrite.
- Wild battle (`WildBattle` Pidgey level 3), fled.
- Trainer battle, singles (trainer 6). The player's lead was set to 1 HP, so it fainted and the player had to send
  another Pokémon. The trainer's first Pokémon fainted and the trainer sent its replacement. The Bag, a pocket, the
  party and a summary were opened in battle.
- Trainer battle, doubles against two trainers (15 and 6), with the same in-battle screens.

## Smoke test with the AI installed

With the payload of commit `8362032` (origin 0x01FF9500), `install.py` gave two AI builds (ignored, under
`work/build/advanced-ai/layout/rom/`, each with its receipt):

| AI build | Input | sha256 |
|---|---|---|
| `rc8_ai.nds` | the rc8 release (ITCM end 0x01FF8FC0) | `9b62fe11…f586cb38a` |
| `main_dev_ai.nds` | `options/difficulty_dev_main.nds`: main's build with difficulty in development mode and the TRAINER AI row (ITCM end 0x01FF9140) | `849ab3c3…0100e7d0` |

Each boots to the title screen and continues into the field. On `rc8_ai.nds`, with the flags set in RAM:

| Case | Flags 0x2C2 / 0x2C3 | Trainer | Slot overlays loaded | `adv_entry` polls | Actions written from the slot code | Fallback |
|---|---|---|---|---|---|---|
| ALL | set / clear | 6 (unmarked) | 8, 10 | 205, client 1 | none, move (×2) | 0 |
| KEY | set / set | 1 (important) | 8, 10 | 434, client 1 | none, move (×4) | 0 |
| KEY | set / set | 15 (unmarked) | 8, 11 | 0 | – | – |
| OFF | clear / clear | 1 | 8, 11 | 0 | – | – |

- "Slot overlays loaded" are the overlay IDs passed to `SwitchSlotOverlay`.
- In the served cases, the slot held overlay 10 (`[main]+0x26C`) every time `adv_entry` ran.
- An action counts as the advanced AI's when an action setter (0x0220091C/0x02200960/0x022009AC/0x02200A30) is
  called with a return address in 0x021F6E20–0x022007E0 while overlay 10 is loaded.
- Fallback is `ai_debug.fallback`.
- `ai_lead` and `ai_replace` ran in every battle; their hooks always run and ask `ai_serves`.

The same four cases also pass on `main_dev_ai.nds`, with the setting chosen through the real Options screen: L +
OPTIONS, page 2, touch the value, Confirm. With KEY, trainer 1 led with Ditto instead of its first Pokémon, Bulbasaur,
which shows `ai_lead` picking the lead. On both builds, `itcm_arena.py --payload` passed with the AI on: no write into
the AI's code from outside it, none from outside it into its work RAM, nothing below the origin touched.

One test artefact: the Spanish bench save's Pokémon have edited stats. After the first battle, the game recomputes
the lead's maximum HP, and its current HP is left above it (998/297). The AI's range check then rejects that Pokémon
(`FB_OPP`) and hands every turn to overlay 11. `ai_smoke.py` sets current HP to maximum HP before each battle. The
test bench needs English pre-battle saves with legal Pokémon.

## Risks and open points

- **No real hardware.** Neither project has run the AI on a DS. The boot now zeroes the AI's ITCM work RAM (the
  `itcm` bss), which a soft reset on hardware would otherwise leave as it was; the fixed test records above it are
  not zeroed and rely on their magic words.
- **Distance between ITCM and main RAM.** ITCM (0x01FF8FC0) and region `main` (0x023D4000) are about 3.9 MB apart,
  close to the ±4 MB reach of a Thumb BL. The current link needs no long-branch stubs, and the builder must keep it
  that way. All five hooks are well within reach: the largest offset is about 2.2 MB.
- **Shared ITCM top.** If text speed ever grows its ITCM block past 0x01FF8FC0, the AI's `itcm` region moves with it.
  The installer refuses an overlap: the block's end must not pass `itcm`'s start, and the arena word must equal
  `before`.
