# props: property tests of the advanced AI

`aiprops.py`, ported from the Spanish workspace's `tools/aiprops.py` (commit `dc8577c`). Random singles turn-1
positions (1-3 Pokémon a side, trainer sets or random ones, HP, status, weather); the advanced AI runs on each, alone on
one side and in self-play, and six invariants must hold: determinism, mirror (trainer side against player side),
interference (the other side's AI deciding in the same turn), immunity, status (moves that cannot work) and hp (values
on the absolute scale). Every violation comes with its position as a bench scenario and a `--repro` command.

## Run

```
T=work/advanced-ai/testbench
.venv/bin/python $T/props/aiprops.py --rom ROM --payload PAYLOAD --n 100 --seed S --workers 3
.venv/bin/python $T/props/aiprops.py --repro work/build/advanced-ai/runs/aiprops/reports/<rom>_<seed>.json#k
.venv/bin/python $T/props/aiprops.py --report work/build/advanced-ai/runs/aiprops/reports/<rom>_<seed>.json
.venv/bin/python $T/props/aiprops.py --selftest --rom ROM          # the invariants on made-up runs, no emulator
```

`run.py quick` runs 20 positions and `run.py deep` 100, seed 1 (or the seeds in `references/<layout>/aiprops.json`);
both pass with 0 violations. About 3 s per run on one emulator, 4-5 runs per position. It needs the Violet Gym save
(`lib/saves.py make violet_gym`). The pre-battle state is kept per ROM build (its SHA-1) under
`work/build/advanced-ai/runs/aiprops/`; results go to `runs/aiprops/reports/<rom>_<seed>.json` and `.txt`.

## Changes from the Spanish tool

- The AI-build addresses come from the payload (through `aibench` and `aivsai`).
- The ROM is never changed (the Spanish tool switched a copy to 60 fps); each worker opens a symlink of it.
- The AI setting is written into the save in RAM after every state load, besides the battery save.
- The random items come from `lib/randteams.py`; a saved run records its ROM's path for `--repro` and `--report`.
