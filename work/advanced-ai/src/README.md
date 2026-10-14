# AI sources

The advanced trainer AI's source code, taken from the Spanish translation's workspace (commit `dc8577c`, reused with
the author's permission). [PROVENANCE.md](../PROVENANCE.md) lists each file's Spanish path and sha256. Every change
to a taken file is its own commit, so `git log -p <file>` shows how it differs from the Spanish original.

| File | What it is |
|---|---|
| `advai.c` | The AI: snapshot, move/switch/item valuation, battle simulation, vetoes, the read gate, foresight, the fallback to the hack's AI |
| `replace.c` | Which Pokémon to send in after a faint (`ai_replace`) |
| `lead.c` | The trainer's lead pick in singles (`ai_lead`) |
| `engine.h` | Engine addresses, structure offsets and the hack functions the AI calls (Chinese v4.0.3), and the test words at the top of ITCM |
| `tune.h` | The tuned constants (`g_tune`); the game runs the defaults |
| `link.ld` | The section rules. The builder writes the `MEMORY` regions (`ai_layout.ld`) from a layout |
| `aiselect.s` | `ai_serves`, `ai_slot_select`, `ai_entry`, `ai_bag_check`: who the AI serves, loading overlay 10, routing each poll |
| `check_flag.s` | `check_flag`, taken from the Spanish `hardmode.s`: reads a script flag for `aiselect.s` |
| `ids.h` | Move, ability and item ids, frozen from the Spanish generation. [IDS.md](IDS.md) names each one |
| `IDS.md` | A table naming every id in `ids.h` through our glossary and the ROM's names, for review |

## Building

Nothing here is built by hand. `../builder/build.py --layout en` compiles and links these files into the payload
(see [../builder/README.md](../builder/README.md)). It needs arm-none-eabi-gcc 16.2.0 and binutils 2.47.

`advai.c`, `replace.c` and `lead.c` are compiled as one unit (`advai.c` includes neither; the builder writes a unit
file that includes all three). `advai.c` also holds a host build (`HOST_ENGINE_H`) for the PC simulator, which the
test bench uses.

## Changes from the Spanish sources

| Change | Where | Defined by |
|---|---|---|
| `AI_NO_STEER`: `steer_marked` returns 0, so luck steering is off in singles and doubles and flag 0x218 is never read; zeroed storage stands in for `steer.s`'s `steer_stash`, `steer_ledgers` and `steer_dstash` | `advai.c` | `builder/layouts/en.json` only, so the `es` build stays byte-identical to rc44 |
