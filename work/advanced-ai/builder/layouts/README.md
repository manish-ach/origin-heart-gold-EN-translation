# Layouts

One JSON file per memory layout, read by [../build.py](../build.py) (`--layout <name>`).

| File | What it is |
|---|---|
| `en.json` | The English payload, option A of the plan: the resident code in a new ITCM autoload section at a fixed 0x01FF9500 (past the largest ITCM block any locale can have; see [../README.md](../README.md)), and a new main-RAM section below difficulty's |
| `es.json` | The Spanish rc44 layout, for the golden test only. Its asm sources, defsyms and `event_mons.inc` are the Spanish build's |

## Fields

| Field | Meaning |
|---|---|
| `name` | The layout's name; must match the file name |
| `regions.slot` | `origin`: where the AI code starts in overlay 10, after overlay 11's image and bss. `limit`: overlay 14's start. The slot's bss follows the code and must also end below `limit` |
| `regions.itcm` | Resident code in ITCM: `origin` up to `limit` (the start of the work RAM). `zero_work_ram` (en): the section's bss runs from the end of the code through `.itcm_bss`, so the boot's autoload zeroes the AI's work RAM every time. A DS does not clear ITCM at power-on (an emulator does), and the AI opens its move-data handle `g_narc` only while it is 0 |
| `regions.itcm_ram` | The AI's ITCM work RAM (`.itcm_bss`): `origin` up to `limit`. The limit must equal the `ASSERT` in `src/link.ld`, which keeps the test records at 0x01FFFF8C–0x01FFFFFF free |
| `regions.main` | Resident code in main RAM: `origin` (`ai_lead` first) up to `limit` |
| `overlay10` | Overlay 10's base: its RAM address, the overlay it copies (11), that overlay's size and bss, and its static initialisers. `build.py` checks that the slot starts right after the copy; the installer checks the ROM |
| `asm` | The asm sources, in link order: `{"src": <file in src/>}` or `{"es": <path in the Spanish archive>}` |
| `as_defsyms`, `as_includes` | Symbols and include files for the assembler (the es layout only) |
| `ld_defsyms` | Symbols for the linker (es: the Spanish `steer.s` storage in its main block) |
| `cflags` | Extra compiler flags (en: `-DAI_NO_STEER`) |
| `hooks` | The overlay-14 Thumb BLs: site, the bytes the site must hold (`before`), the target symbol. `build.py` adds the new bytes (`after`) |
| `words` | The arm9 words the installer rewrites (arena bounds), with `before` and `after`. `before` is the 4 bytes the word must hold, or `"itcm_end"`: the word must equal the end of the input's ITCM block (0x01FF8000 + its size) and be at most `before_max`, which `build.py` requires to be the itcm origin |

## The English hooks and words

The five hooks and their `before` bytes are the Spanish build's core hooks. `testbench/unit/test_build.py` checks
the bytes against the untouched Chinese ROM, the English rc8 release and main's standard build; they are equal at all
five sites.

| Word | rc8 value | Payload value | Why |
|---|---|---|---|
| 0x020D1A28, ITCM arena start | the ITCM block's end: 0x01FF8FC0 on rc8 (text speed), 0x01FF9140 on main (trainer full names); at most 0x01FF9500 | 0x02000000 | The AI's ITCM code and work RAM take the rest of ITCM, as in the Spanish build |
| 0x020D1970, main arena high | 0x023DC000 (difficulty) | 0x023D4000 | The AI's main region, 32 KB below difficulty's section |
