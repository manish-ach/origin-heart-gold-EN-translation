# hostai: the advanced AI built for the PC

The AI's own sources (`../../src/`: `advai.c`, `replace.c`, `lead.c`), compiled unchanged with clang for the host, on a
stand-in of the battle engine. The simulator (`../sim/`) plays through this build, and `replay.py` checks it against the
DS: each recorded bench decision is replayed here and must give the DS's choice, option values and snapshot.

Ported from the Spanish workspace's `tools/hostai/` (commit `dc8577c`, by luisvent, reused with their permission).

## What it needs

- clang and make (Apple clang 17 is enough), macOS: `engine.c` maps the DS address space with `mach_vm_allocate` at a
  fixed address and `replay.c` counts instructions with `proc_pid_rusage`.
- A ROM for the data (`--rom`; default `work/rom/origin_v4.0.3_cn.nds`, the untouched Chinese hack).
- `replay.py` and `grade_damage.py` also need an advanced-AI bench record made on that ROM: a `bench/aibench.py
  --advanced` run's JSON under `work/build/advanced-ai/runs/` or `testbench/references/` whose `rom_sha1` is the ROM's.
- `thumbcount.py` needs arm-none-eabi-gcc and a Python with `unicorn` (not in the project venv).

## Run

From the repository root:

```
.venv/bin/python work/advanced-ai/testbench/hostai/replay.py --rom ROM [--layout en]   # static tier: the bench record
.venv/bin/python work/advanced-ai/testbench/hostai/replay.py --rom ROM --sixes 40       # work per 6v6 first decision
.venv/bin/python work/advanced-ai/testbench/hostai/replay.py --rom ROM --os             # the DS build's -Os instead
.venv/bin/python work/advanced-ai/testbench/hostai/grade_damage.py --rom ROM [--sim SIM]   # damage vs the engine
make -C work/advanced-ai/testbench/hostai ROM=<absolute ROM path> [AI_DEFS=-DAI_NO_STEER]  # the build alone
```

`replay.py` exits 0 when every complete bench case (an empty AI bench and a foe that cannot switch: every engine
simulation is in the record) matches the DS, 1 when one differs, and 2 when the ROM has no bench record (the static
tier counts 2 as a skip). The Spanish build passed 202 of 202. On rc44's full record (`port_rc44_all`, 2026-10-13):
214 complete cases, every choice the DS's, 213 with every option value exact; the one left (`item_cure_sleep`, a
sleeping Snorlax with a Full Heal) is listed in `replay.py`'s `KNOWN_GAPS` with its numbers. 1.7 s with the build
cached.

`--layout en` compiles the AI with the English build's switches (`builder/layouts/en.json` cflags: `-DAI_NO_STEER`,
steering compiled out), as the builder compiles the English payload. Without it the AI is the Spanish default. Use
`--layout en` for the English AI build and no layout for the Spanish rc44.

## Output (ignored by git)

| Path | What |
|---|---|
| `work/build/advanced-ai/hostai/<ROM name>[_<layout>][_os]/` | the build: `hostdata.c` (from the ROM), objects, `replay`, `replay_count` |
| `work/build/advanced-ai/runs/hostai/` | case files (`cases.txt`, `sixes.txt`), `thumb/` |

## Files

| File | What it is | Changed from the Spanish |
|---|---|---|
| `ai_unit.c` | The AI's three sources in one unit, plus the host's reset of its globals and debug access | unchanged |
| `host_engine.h` | Force-included before the AI: redirects `AT()`, `CALL()` and the fixed addresses to the host arena | includes `engine.h` from `src/` through `-I` |
| `host.h` | The case format (`HostCase`) and the host API | unchanged |
| `engine.c` | The stand-in engine: the arena, a battle built from a case, the engine entry points the AI calls | writes sleep's condition word (the turns `advai.c` reads; it took every sleeper for one waking now: 4 bench cases differed) |
| `replay.c` | The driver: each case polled as the battle client polls it, one JSON line per case | unchanged |
| `Makefile` | The build, per ROM, with `AI_DEFS` | build directory outside the tree, `ROM`, `AI_DEFS` |
| `gen_data.py` | `hostdata.c`: the move records, the move getter's parameter map, the type chart | `--rom`/`--out`; no `ids.h` (`src/ids.h` is frozen) |
| `replay.py` | Cases from a bench record, the comparison, work per decision; exit status | record lookup by ROM SHA-1, exit status, `--layout`, `--os` |
| `grade_damage.py` | The engine's damage numbers against the AI's formula, `aicalc` and the simulator's port | record lookup, `--rom` |
| `thumbcount.py` | The DS build's Thumb code run in unicorn, instructions and cycles per decision | the builder's flags, `src/`, `--layout` |
