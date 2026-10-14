# fuzz: full trainer battles with random teams

`aifuzz.py` plays full trainer battles to the end with random teams (the trainer: 2-6 Pokémon at level 30-65,
sometimes with items; the player: one Pokémon a few levels higher, or two with `--double`), the player touching a
random move each turn. Each battle is seeded, so the advanced AI and the hack's own AI play the same battles. It records
every AI decision, the advanced AI's fallback codes, and every assert, NULL allocation, freeze or text outside its
window, and sorts them (`lib/failures.py`) into inherited from the Chinese hack, by design, or for review. `FullBattle`
is also the full-battle driver of `checks/aimode_check.py`, `checks/menulock.py` and `dev/animcheck.py`.

Ported from the Spanish workspace's `tools/aifuzz.py` (commit `dc8577c`, by luisvent, reused with their permission).
The random teams and the failure sorting are in `lib/randteams.py` and `lib/failures.py`; `--hard` (hard mode and its
luck steering) is not ported.

## What it needs

An AI build and its payload, the test saves (`lib/saves.py make`), `lib/`, `bench/aibench.py` and `versus/aivsai.py`.

## Run

```
.venv/bin/python work/advanced-ai/testbench/fuzz/aifuzz.py --rom ROM --payload PAYLOAD --battles 50 --double --mode advanced
.venv/bin/python work/advanced-ai/testbench/fuzz/aifuzz.py --rom ROM --payload PAYLOAD --battles 50 --mode both
.venv/bin/python work/advanced-ai/testbench/fuzz/aifuzz.py --report [--double]
```

`--mode both` plays each battle with the advanced AI and with the hack's AI; `--report` compares their win rates on
the seeds both played. The exit status is 1 when an advanced-mode battle has a problem for review. The deep tier runs
the doubles (`--double --mode advanced`). Results: `work/build/advanced-ai/runs/aifuzz/` (ignored by git). At most
2 workers (`--workers`, the emulator budget).
