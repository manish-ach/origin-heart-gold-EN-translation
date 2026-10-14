# Spanish rc44: the port's validation

The ported tools against the archived Spanish tools (commit `dc8577c`), both on the Spanish rc44 ROM (SHA-1
`5477043f03f3d145176d15dd9f92e4972f9a99f1`), on 2026-10-13. The port used the builder's `--layout es` payload
(`work/build/advanced-ai/es/payload/payload.json`, sha256 `baa69fea…8eb5`). Both ran with 3 emulators on a shared,
heavily loaded machine (load average 25-90), so the times are upper bounds.

| Check | Spanish tool | Port | Same? |
|---|---|---|---|
| `aibench --check` (claims, no emulator) | — | all 365 scenarios check out (364 on our English data: `bench/README.md`) | — |
| `aibench --advanced --repeats 1`, all 365 scenarios | 98.1%, 0 fallbacks, 365 of 365 from overlay 10, polls max 5; 488 s | 98.1%, 0 fallbacks, 365 of 365 from overlay 10, polls max 5; 583 s | every result's seed, action, grade, setter call, debug record (all option values), overlay-11 diagnostics and snapshot identical; report text identical; 3 of 365 runs reached the decision 1 frame earlier or later (same decision and record) |
| `aivsai 40 --seed 101` | 71 of 80 (88.8%), 31 scenarios 2-0, 9 split; 17.9 turns; 0 of 1,431 fallbacks; polls max 8; 0 failures; 22.1 min | the same numbers; 28.2 min | **80 of 80 logs byte-identical** |
| `aiprops --n 20 --seed 1` | 100 runs: 0 violations of 6 invariants (109 checks), 1 note, every side checked; 152 s | the same; 149 s | positions, all 100 runs (decisions, debug records, frames), invariants and notes identical |

The Spanish references these match: `qa/rc44_rerun.md` (aivsai seed 101: 71 of 80, 17.9 turns, 0 fallbacks of 1,431,
polls max 8, logs byte-identical between rc42 and rc43) and `qa/aibench/advanced_all_rc32f_bench.txt` (97.8% on 365 on
rc32; rc44's AI scores 98.1% with the Spanish tool itself).
