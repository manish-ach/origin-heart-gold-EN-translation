# dev: development tools no tier runs

Tools for working on the AI: building a test ROM, running the bench's batches, tuning, timing, damage arithmetic and
the engine probes the Spanish AI work was built on. Ported from the Spanish workspace (commit `dc8577c`, by
luisvent, reused with their permission); each file's docstring lists what changed. Only `tests/test_aitune.py` runs in a
tier (static).

| Tool | What it does | Spanish source |
|---|---|---|
| `aibuild.py` | Compiles `src/` (or `--src`, a copy) with `builder/build.py` and installs it with `builder/install.py` into a copy of the pre-AI English ROM: an AI build in about 10 s, with the `--rom`/`--payload` pair the tools take | `tools/aibuild.py` (it rebuilt overlay 10 of a full Spanish build) |
| `aibatch.py` | One round of the scenario loop: the claim checks, both AIs on a batch, what the advanced AI missed; `--regress` every scenario once | `tools/aibatch.py` |
| `aitune.py`, `tests/` | Self-play tuning of `src/tune.h`'s constants (Hadamard screen, confirm, export, acceptance runs, seeds); `--selftest` runs `tests/test_aitune.py` | `tools/aitune.py`, `tests/aitune/` |
| `aicalc.py` | Damage and speed calculator from the ROM's data, every modifier labelled (measured, official, hack) | `tools/aicalc.py` |
| `aitime.py` | Think time on the emulated DS: cycles per poll and decision, idle time, instruction counts | `tools/aitime.py` |
| `aiprobe.py` | Overlay 11's scores and decisions turn by turn in set-up battles (research) | `qa/ai_research/aiprobe.py` |
| `factprobe.py`, `paraprobe.py` | Engine facts and paralysis measured in short battles (research) | `qa/ai_research/` |
| `effectcheck.py` | Does the hack implement an item or ability? Two battles, with and without it | `qa/ai_research/effectcheck.py` |
| `bpp_dump.py` | Dumps the battle state the AI reads in a bench battle, to map the engine's structures | `qa/ai_research/bpp_dump.py` |
| `animcheck.py` | Move animations in doubles: inherited asserts and heap leaks, against the Chinese ROM | `qa/ai_research/animcheck.py` |

## What they need

An AI build and its payload (`--rom`, `--payload` or `ADVAI_PAYLOAD`) for every tool that runs the emulator; `lib/`,
`bench/` and `versus/`. `aibuild.py` needs arm-none-eabi-gcc 16.2.0 and binutils 2.47 (the builder checks them) and the
pre-AI English ROM (`work/build/advanced-ai/base/rc8_release.nds` by default). At most 2 emulator workers.

## Run

```
.venv/bin/python work/advanced-ai/testbench/dev/aibuild.py --out work/build/advanced-ai/runs/mine.nds [--src DIR]
.venv/bin/python work/advanced-ai/testbench/dev/aitune.py --selftest                  # static tier, ~3 s
.venv/bin/python work/advanced-ai/testbench/dev/aibatch.py 3 --rom ROM --payload P
.venv/bin/python work/advanced-ai/testbench/dev/aicalc.py --rom ROM Mawile "Play Rough" Lucario --a-ability "Huge Power"
.venv/bin/python work/advanced-ai/testbench/dev/aitime.py --rom ROM --payload P battles 4
```

Run output goes to `work/build/advanced-ai/runs/` (ignored by git): `aibuild/`, `aitime/`, `ai_probe/`, `factprobe/`,
`paraprobe/`, `animcheck/`, `aitune_test/`, and the tuning ledger under `aivsai/tune/`.
