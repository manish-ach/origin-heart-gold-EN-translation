# sim: the singles battle simulator

A PC simulator of the hack's singles trainer battles, so the advanced AI can be measured over tens of thousands of
games instead of the emulator's ten a minute. It plays with the ROM's own data and the battle rules as the hack's engine
has them where they were measured, and the official rules elsewhere. The advanced AI plays through the host build of
`../hostai/`, unchanged, on either side.

Ported from the Spanish workspace's `tools/sim/` (commit `dc8577c`, by luisvent, reused with their permission). Its
design, measurements and history are in that workspace: `work_es/tools/sim/README.md` (the full command reference,
the turn-level validator, the original AI's model, `sim cf`, luck and lookahead) and `work_es/qa/simulator_feasibility.md`.
This README covers what differs here and how to run it.

## What it needs

- clang and make (Apple clang 17 is enough), macOS (the host build maps a fixed address range).
- A ROM for the data. Default: `work/rom/origin_v4.0.3_cn.nds`, the untouched Chinese hack. Its battle data equals the
  English build's (the games below are identical); the Spanish rc44 differs in two species' base stats.
- The test bench's `lib/` (names, ROM readers, the simulator pool) and `versus/aiteams.py` (the trainer teams).

## Build and run

From the repository root:

```
.venv/bin/python work/advanced-ai/testbench/sim/simbuild.py [--rom ROM] [--layout en]   # make it, print the binary
SIM=work/build/advanced-ai/sim/origin_v4.0.3_cn/sim
$SIM play --games 1000 [--seed S]                  # AI vs AI on the level-80 trainer pool, JSON lines out
$SIM play --p0 orig --p1 adv -v                    # the original AI's model against the AI, turns on stderr
.venv/bin/python work/advanced-ai/testbench/sim/counterfactual.py --sim $SIM pairs --pool 80 -o PAIRS
SIM_READ_SIDE=1 SIM_FS=2 SIM_FS_SIDE=1 .venv/bin/python work/advanced-ai/testbench/sim/counterfactual.py --sim $SIM \
    rate --pairs PAIRS --reps 2 --seed 7201 --p0 orig --p1 adv --workers 4 --per-game -o RATES   # the bot leg
.venv/bin/python work/advanced-ai/testbench/sim/bench_check.py --rom ROM [--layout en]   # static tier: the bridge vs the DS
.venv/bin/python work/advanced-ai/testbench/sim/coverage.py [--rom ROM] [--pool]        # what the teams use that it lacks
make -C work/advanced-ai/testbench/sim ROM=<absolute ROM path> [B=DIR] [AI_DEFS=-DAI_NO_STEER]   # the build alone
```

`--layout en` compiles the AI with the English build's switches (`builder/layouts/en.json` cflags: `-DAI_NO_STEER`,
steering compiled out), in its own build directory. Use it for the English AI build. The simulator never steers unless
`SIM_STEER_K` is set, so both builds play the same games (measured below).

`bench_check.py` rebuilds the bench record's complete first decisions (`hostai/replay.py`'s cases) as simulator
battles, decides them through `bridge.c` with every engine simulation answered by `damage.c`, and grades them with
`replay.py`'s comparison. It exits 0 when every complete case matches the DS (Spanish: 202 of 202), 1 when one differs,
2 when the ROM has no bench record (a skip for the static tier).

Every other driver keeps the Spanish command line (`run.py`, `validate.py`, `turnlog.py`, `logstats.py`, `parity.py`,
`origfit.py`, `luck_*.py`, `gate.sh`, `la/`); `--sim` defaults to the Chinese ROM's build, or `ADVAI_SIM`. Simulator
processes take slots of `lib/simpool.py` (`ADVAI_SIM_SLOTS`, default 6; this project's budget is 4).

## Output (ignored by git)

| Path | What |
|---|---|
| `work/build/advanced-ai/sim/<ROM name>[_<layout>]/` | the build: `simdata.c` and `sim_ids.h` (from the ROM), objects, `sim`, `extra_teams.json` if any |
| `work/build/advanced-ai/runs/sim/` | `bench_check/`, `val/` (validator input), `run/`, `la/`, `la_ds/` |

The generated data is derived from the ROM: it stays in the build directory and is never committed.

## Validation (2026-10-13)

| Check | Result |
|---|---|
| `sim_ids.h` from `lib/names.json` | identical to the one made with the Spanish workspace's names (rc44) |
| Bot leg on rc44 (pairs80: 25,122 matchups, 2 reps, seed 7201, read and foresight on the trainer side) | **89.875%** (45,157 won, 5,087 lost): exactly the Spanish figure for this AI's read gate on the same seed (`qa/aivsai/rc39_RD2.md`, "new (700/300)" 89.875%) |
| The same on the Chinese ROM's data | 89.792% (45,115-5,129): the two base-stat edits of the Spanish build |
| The same on the English rc8 release's data | 89.792%, every game identical to the Chinese ROM's |
| The same with `-DAI_NO_STEER` (English layout) | every game identical |
| Self-play speed, AI on both sides | 277-287 games/s on one core with the machine loaded (load average 13-23); the Spanish figure is ~425 unloaded |
| Determinism | `play --games 2000 --seed 1` gives the same games on the Chinese and English data (names aside) |
| Bench check on rc44 (`bench_check.py`, the bench's full advanced record `port_rc44_all`) | **202 of 202** complete decisions give the DS's choice, setter call, every option value and the snapshot (the Spanish figure); 12 more cases are unsupported (trainer items, doubles), 0.9 s |
| Damage against the engine (`hostai/grade_damage.py --sim`, the same record) | **1,540 of 1,540** engine numbers exact (the Spanish figure); the AI's own formula 91.2%, `aicalc` 94.7% |
| `sim cf check` (snapshots replay the same games byte for byte), 20 matchups x 2 reps | 0 of 2,027 replays differ blind; 0 differ with reading alone and with foresight alone; **74 of 898 differ with reading and foresight together**, and the unchanged Spanish simulator at dc8577c built on the same data gives the same 74: an inherited gap (the Spanish rc31 K report had 0 of 1,013 with both on, so a later Spanish change left some state out of `sim_ai_state_save`). It affects only `cf analyze` and `cf mc` with both on, not `play` or `rate` |

The bench check (`bench_check.py`) needs a bench record made on the same ROM (`bench/aibench.py --advanced`).

## Changes from the Spanish files

- **Not ported:** the drama observer and its tools (`drama_obs.c`, `drama_trace.h`, `drama_tune.c`, `drama_parity.c`,
  `drama_*.py`: the battle experience, not ported) and `steer_luck.py` (luck steering, not ported). `drama_off.c`
  stands in for the observer with no-op entry points, so `battle.c`, `move.c` and `play.c` keep their hooks unchanged.
- **C sources:** unchanged. `bridge.c` keeps the simulator's own steering knobs (`SIM_STEER_*`, off unless set).
- **Makefiles:** the build directory per ROM outside the tree, `ROM`, `AI_DEFS` (a stamp rebuilds the objects when it
  changes), the AI from `src/` with its frozen `ids.h`; no drama targets.
- **Python:** the test bench imports (`lib/tbpaths.py`); `simbuild.py` (new) is the one place that knows where a ROM's
  build lives; `gen_simdata.py` takes names from `lib/names.json`, weights from the hack's Pokédex bank
  (`work/translate/banks/a027/0800.json`, the `zh` text) and no longer writes `ids.h`; `bench_check.py` and
  `hostai/replay.py` find records by ROM SHA-1 and have exit statuses; run output under `RUNS/sim/`.
- **Spanish-only:** `turnlog.py` parses the battle messages of the Spanish ROM (its patterns and the Spanish names, read
  from the Spanish repository with git). It, and `validate.py`, `origfit.py` and `run.py`'s team matching that use it,
  work on logs of games played on rc44, not yet on the English build's English messages.

## Files

| File | What it holds |
|---|---|
| `simbuild.py` | Where a ROM's build lives, the layouts' switches, the builder's DS flags; makes the simulator |
| `gen_simdata.py` | The generator: `simdata.c` (species, moves, type chart, item tables, the 209 six-Pokémon trainer teams, names, the AI's move records) and `sim_ids.h` |
| `sim.h`, `internal.h` | The data shapes and what `battle.c` and `move.c` share |
| `damage.c` | One hit's damage (the port of `dev/aicalc.py`), with the engine simulation's quirks for the AI |
| `battle.c`, `move.c` | Turn order, switching, entry effects, end of turn, faints; a move from its checks to its last effect |
| `bridge.c`, `ai_sim.c` | The advanced AI as a policy: the battle written into the DS address space it reads, its engine calls answered |
| `policy.c`, `origbot.c`, `origbot.h`, `origmodel*.h`, `origparams*.json`, `origfit.py` | The greedy bot; the model of the hack's original AI and its fitting |
| `play.c`, `bench.c`, `main.c`, `cf.c`, `validate.c`, `protect_check.c` | The commands: `play`, `bench`, `damage`, `cf`, `validate`; the Protect streak check |
| `lapol.c`, `lapol.h`, `leaf.c`, `leaf.h`, `la/` | Lookahead variants and the learned leaf (research) |
| `drama_off.c` | The no-op stand-in for the Spanish drama observer |
| `bench_check.py`, `run.py`, `coverage.py`, `logstats.py`, `validate.py`, `turnlog.py`, `parity.py` | The checks and the log tools |
| `counterfactual.py`, `gate.sh`, `Makefile.dual` | Win rates per matchup, counterfactual replays, a dual binary for head-to-head games of two AI builds |
| `luck_stats.py`, `luck_spsa.py`, `luck_gate.py`, `luck_fit.py` | Luck-adjusted results and SPSA over `src/tune.h` |
