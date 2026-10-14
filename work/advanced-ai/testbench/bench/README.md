# bench: graded AI decisions

The trainer AI bench: set-up turn-1 positions, each with its answers graded best / ok / bad, run against the AI in a
ROM. Ported from the Spanish workspace (commit `dc8577c`): `tools/aibench.py`, `tests/ai_scenarios.py`,
`tests/ai_checks.py`, `tests/ai_helpers.py` and `tests/ai_batches/` (all files, `AUTHORING.md` included).

| File | What it is |
|---|---|
| `aibench.py` | The runner, the grader and the claim checks (`--check`) |
| `tests/ai_scenarios.py` | The original 114 scenarios; loads `tests/ai_batches/batch_NN.py` (batches 01-06: 251 more) |
| `tests/ai_checks.py` | The claim-check ops the scenario authors added |
| `tests/ai_helpers.py` | `mon` and `S`, the scenario helpers |
| `tests/ai_batches/` | The batches; `batch_04a.py` etc. are imported by their batch, `draft_*.py` load only with `AI_BATCH_DRAFT` |

## Run

```
T=work/advanced-ai/testbench
.venv/bin/python $T/bench/aibench.py --check --rom ROM                                  # static tier: claims, no emulator
.venv/bin/python $T/bench/aibench.py --rom ROM --payload PAYLOAD --advanced --repeats 1 --workers 3 --save NAME
.venv/bin/python $T/bench/aibench.py --report NAME --rom ROM                            # regrade a saved run
.venv/bin/python $T/bench/aibench.py --compare A B --rom ROM                             # two saved runs side by side
```

Without `--advanced` the AI setting is cleared and the hack's own AI (overlay 11) decides. The tier runner
(`run.py quick`) runs all scenarios once with `--advanced` and compares the score with `references/<layout>/bench.json`.

It needs the Violet Gym save (`lib/saves.py make violet_gym`). A run takes about 7 s per scenario per worker; the
pre-battle state is made once per run. Output: `work/build/advanced-ai/runs/aibench/` (`saved/NAME.json` and `.txt`
with `--save`).

## Changes from the Spanish tool

- The AI-build addresses (the slot range, the `NOLEAD`/`NOREAD`/`READS_AT` words, the debug record) come from the
  payload (`lib/payload.py`).
- The AI setting is written into the save in RAM after every state load (`ADVAI_AI_SETTING`, set from `--advanced`),
  and, as the Spanish tool did, into the battery save the pre-battle state is made from (`setting_save`).
- Each worker opens a symlink of the ROM, not a copy.
- `SPANISH_DATA`: `b01_light_ball_ko` rests on the Spanish build's Pikachu (base stats 60/85/60/110/85/60, a data edit
  of that build); the hack and our build keep 40/60/50/110/60/50, so on our ROM its KO claim is false and the scenario
  is left out by name (364 scenarios). On the Spanish rc44 all 365 run.
- `tests/ai_checks.py` reads the hold effects from the ROM under test (the Spanish one read its own build), and two
  batch files lost unused imports (ruff).
