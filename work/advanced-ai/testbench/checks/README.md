# checks: pass/fail behaviour checks of an AI build

Each tool here runs an AI build on the emulator and exits 0 when every case passes, 1 when one fails. They are
ports of the Spanish workspace's checks (commit `dc8577c`, by luisvent, reused with their permission); each file's
docstring lists what changed. The `options_*` files belong to the Options row (phase 4) and are described in their
own docstrings.

| Tool | What it checks | Tier | Spanish source |
|---|---|---|---|
| `aimode_check.py` | The three settings (off, all, important) and who the AI serves under each: singles, doubles against two trainers, a multi battle with a partner, a Gym trainer, a story character (14 cases) | quick | `tools/aimode_check.py`, rewritten for flags in RAM |
| `lead_check.py` | The trainer's lead pick (`src/lead.c`): each setting, a keep-lead trainer, the NOLEAD word, doubles and multi (8 cases), and the DS's lead against the simulator's host build on 24 level-80 matchups (`host`) | quick | `tools/lead_check.py` |
| `read_check.py` | Reading the player's committed action: waiting, NOREAD, RUN, the menu's own choices, written actions, the read gate's outcomes, doubles | quick | `tools/read_check.py` |
| `menulock.py` | The player's menu with no selectable move, the banned-move message, recoil; `--advanced` with the `foe_*` cases: the AI's side Struggles or switches and the battle ends | quick (`--advanced foe_pp4 foe_pp4_one foe_pp4_bench foe_pp4_double`) | `qa/ai_research/menulock.py` |
| `fscheck.py` | Foresight: every part of a trusted cell against the turn played, in AI-vs-AI games; `--human` the shipping path with a scripted player | deep | `tools/fscheck.py` (steering checks not ported) |
| `storycheck.py` | Story battles with the AI on against the same scenes with it off: Willy's and Giovanni's lost battles (white-out), the Route 3 scene's two battles; the AI-on run must show the AI deciding | deep | `tools/storycheck.py --ai`'s battle cases |
| `ai_smoke.py` | End to end through our harness (`work/tools/emu_harness.py`): boot, the setting in RAM or through the real Options row (`--options RECEIPT`), four trainer battles (ALL unmarked, KEY marked, KEY unmarked, OFF), who served each | quick | the installer agent's `layout/ai_smoke.py` |
| `itcm_arena.py` | Nothing but the AI touches its memory: no write into its code (the payload's itcm and main regions, compared with `itcm.bin`/`main.bin` at the end), the SDK's ITCM arena never changes, foreign writes into its work RAM listed; field menus, a save, a wild battle, singles and doubles with the Bag and party opened. Without a payload, the phase 0 canary over 0x01FF8FC0-0x02000000 | deep | the installer agent's `layout/itcm_probe.py` |

## What they need

- An AI build and its payload: `--rom ROM --payload PAYLOAD.json` (or `ADVAI_PAYLOAD`). For the Spanish rc44: `--rom work/build/advanced-ai/es/rc44.nds --payload
  work/build/advanced-ai/es/payload/payload.json`. For the English build: the installer's ROM and
  `work/advanced-ai/payload/payload.json`.
- The test saves (`lib/saves.py make`), the project venv (py-desmume 0.0.9), `lib/` and `bench/`, `fuzz/aifuzz.py`
  (the full-battle driver), `versus/aivsai.py` (fscheck), `sim/` (lead_check's host match).
- The marks: `aimode_check.py` and `lead_check.py` refuse to run unless the trainers they rely on are marked as
  expected both in the ROM (header byte 2 of `a/0/5/5`) and in `data/trainer_marks.json`.
- `ai_smoke.py` and `itcm_arena.py` drive our own harness (`work/tools/emu_harness.py`) with the Violet Gym test save
  cut to its 512 KB battery image.

**Fallbacks fail loudly.** The Spanish test saves' Pokémon carry edited stats; after a battle the game leaves current
HP above maximum HP (998/297), the AI's range check rejects that Pokémon (`FB_OPP`) and hands every turn to overlay 11,
which looks like "AI off". The bench-based checks write fresh parties; `storycheck.py`, `ai_smoke.py` and
`itcm_arena.py` cap every party Pokémon's HP at its maximum before each battle. Every check that expects the AI to
serve fails on a fallback code other than the by-design ones (0; 3 doubles; 6 no usable option), and `storycheck.py`
and `fscheck.py` fail when no decision of the AI was seen at all.

The AI setting is written into the save in RAM after every state load (`lib/emu.py set_ai_setting`), so no check
depends on the Options row. Battle messages are read from the ROM's own strings or in both languages, so the same
checks run on the Spanish rc44 and on the English build.

## Run

From the repository root, at most 2 emulators (`--workers 2`):

```
P=--payload work/advanced-ai/payload/payload.json; R=--rom <the English AI build>
.venv/bin/python work/advanced-ai/testbench/checks/aimode_check.py $R $P --workers 2
.venv/bin/python work/advanced-ai/testbench/checks/lead_check.py $R $P --workers 2
.venv/bin/python work/advanced-ai/testbench/checks/read_check.py $R $P
.venv/bin/python work/advanced-ai/testbench/checks/menulock.py $R $P --advanced foe_pp4 foe_pp4_one foe_pp4_bench foe_pp4_double
.venv/bin/python work/advanced-ai/testbench/checks/fscheck.py $R $P --games 8 --workers 2
.venv/bin/python work/advanced-ai/testbench/checks/storycheck.py $R $P
.venv/bin/python work/advanced-ai/testbench/checks/ai_smoke.py $R $P [--options <difficulty receipt>]
.venv/bin/python work/advanced-ai/testbench/checks/itcm_arena.py $R $P
```

Run output (work files, logs, screenshots) goes to `work/build/advanced-ai/runs/<tool>/` (ignored by git).
