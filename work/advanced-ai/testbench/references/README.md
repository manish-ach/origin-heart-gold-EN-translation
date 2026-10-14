# references: recorded results

What `run.py` judges a tier against. One folder per payload layout: `en/` for our AI build, `es/` for the Spanish rc44
(the port's validation). The files hold scores, actions, SHA-256 digests and seeds: no ROM bytes, no game text.

| File | Written by | Holds | Pass rule |
|---|---|---|---|
| `bench.json`, `bench_record.json` | `run.py quick --record` | The bench score, fallbacks, decisions not from overlay 10, errors, every scenario's action, the ROM's hashes; the whole saved run (decisions, debug records), which `hostai/replay.py` and `sim/bench_check.py` replay | quick: score at or above it, 0 fallbacks, every decision from overlay 10, 0 errors |
| `aivsai.json` | `run.py deep --record` | `aivsai 40 --seed 101`: wins, counted and played games, the AI's fallbacks, each battle log's SHA-256, the ROM's hashes | deep: no more fallbacks than recorded, and all 80 logs byte-identical; else the advanced AI wins 80-94% of the counted games, and the differing games are printed |
| `aiprops.json` | `run.py quick\|deep --record` | Per tier the seed, positions, checks, violations and sides the AI did not serve | 0 violations, some checks made, no more unserved sides than recorded |

Every reference was recorded with the reference test saves (`lib/saves.py make` from the Spanish repository), and
`--record` refuses other saves. With saves derived from someone's own game (`make --base`) every tier still runs and
prints the saves' source; the AI-vs-AI logs are compared with `aivsai.json` only with the reference saves, and
otherwise the win range alone judges them.

Every judged step reports the AI's fallbacks: an AI that hands its turns back to the hack's AI (overlay 11) without
saying so never passes.

A new reference is recorded only with a reviewer's sign-off: the run's report must name the change that moved the
results (a changed bench action, a differing log). Record with the same command as the tier plus `--record`, on the
reviewed ROM and payload, and commit the changed files with that report.

## Recorded

See `en/RECORDED.md` and `es/RECORDED.md` for the ROM, the payload, the commands, the numbers and the times of each
recorded run.
