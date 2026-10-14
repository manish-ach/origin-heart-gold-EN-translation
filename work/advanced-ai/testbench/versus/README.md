# versus: AI against AI

The advanced AI (the trainer's side) against the hack's own AI (the player's side), whole battles with teams of six,
and the tools around those games. Ported from the Spanish workspace (commit `dc8577c`).

| File | What it is | Spanish file |
|---|---|---|
| `aivsai.py` | The runner: N scenarios, each played twice with the teams swapped; logs and a report | `tools/aivsai.py` |
| `aivsai_report.py` | The report: wins, Wilson interval, sign test, failures, fallbacks | `tools/aivsai_report.py` |
| `aiteams.py` | The ROM's trainer teams and random teams as team specs | `tools/aiteams.py` |
| `aivsai_live.py` | The live window and the log line format | `tools/aivsai_live.py` |
| `aiplay.py` | Play mode: a person against the advanced AI, every battle logged | `tools/aiplay.py` |
| `human_games.py` | The person's games: list, mark analyzed | `qa/aivsai/human_games.py` |
| `score_round.py` | The held-out scorer: rounds of seeds nobody sees, old build against new | `qa/aivsai/score_round.py` |
| `mirror_check.py` | Side-asymmetry check on self-play logs | `qa/aivsai/mirror_check.py` |
| `fix_outcomes.py` | Correct report winners from the logs' end messages | `qa/aivsai/fix_outcomes.py` |
| `test_aiteams.py` | Unit tests of the trainer names (the static tier runs them) | new |

## Run

```
T=work/advanced-ai/testbench
.venv/bin/python $T/versus/aivsai.py 40 --seed 101 --rom ROM --payload PAYLOAD --workers 3   # the deep tier's 80 games
.venv/bin/python $T/versus/aivsai.py 4 --rom ROM --payload PAYLOAD --live                    # one window, every decision
.venv/bin/python $T/versus/aivsai.py 20 --rom ROM --payload PAYLOAD --control                # the hack's AI on both sides
.venv/bin/python $T/versus/aiteams.py --rom ROM [--check]
.venv/bin/python $T/versus/aiplay.py 3 --rom ROM --payload PAYLOAD
.venv/bin/python $T/versus/aivsai_report.py --selftest       # also aivsai_live.py and score_round.py --selftest
```

The 80 games of seed 101 are deterministic: the luck is synced (each selection phase reseeded from the game seed) and
the clock pinned, so the same build gives byte-identical logs. `run.py deep` compares their SHA-256 with
`references/<layout>/aivsai.json`. Games need the Violet Gym save (`lib/saves.py make violet_gym`). Output:
`work/build/advanced-ai/runs/aivsai/` (work files), `runs/aivsai/reports/` (reports, logs under `runs/`), or `--log-dir`.

## Changes from the Spanish tools

- The AI-build addresses (`ADV_CODE`, `ORIG_CODE`, `SELFPLAY_FLAG`, `FS_WORD_AT`, `REPLACED_AT`, the tuning table) come
  from the payload; other modules still read them as `aivsai.ADV_CODE` and so on.
- No speed toggle: the ROM is never changed (`--speed` is gone; the Spanish `--speed fast` left rc44 unchanged anyway),
  and each worker opens a symlink of the ROM.
- The AI setting is written into the save in RAM after every state load, besides the battery save (`--control`
  clears it).
- The teams are drawn from `--rom` (the Spanish tool drew them from its own build).
- Trainer names: our build keeps five long names (ids 17, 59, 632, 666, 745; `work/tools/trainer_display.py`, D-2487)
  in bank 719 as keys like `T00017` and draws the full name from ITCM. `aiteams.full_names` puts back the full name
  the game shows, from the translation workspace the build takes it from (`work/translate/banks/a027/0719.json`);
  none of the five has six Pokémon, so no AI-vs-AI team carries one today.
- The battle's verdict (`OUTCOMES`), a failure's move message and `fix_outcomes.py` read English and Spanish.
- Names come from `lib/names.json` and the failure classification from `lib/failures.py` (both from the Spanish
  `aifuzz.py` and text banks), the seed bookkeeping from `lib/seeds.py` (from `aitune.py`).
- The Spanish `ES_STEER_TEST` 'hard' option (hard mode, for luck steering) is gone with steering; 'mark' stays as
  `ADVAI_STEER_TEST`.
