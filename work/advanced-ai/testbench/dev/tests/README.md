# dev/tests: the tuning tool's tests

`test_aitune.py` tests `dev/aitune.py` and the tuning additions to `versus/aivsai.py` with no emulator: the `tune.h`
registry (`sample_tune.h` is its fixture), the Hadamard screen's plan and estimates, the seed rules, the ledger, the
command results with the emulators stood in, and the tuning table read from a ROM. It runs in the static tier.

Ported from the Spanish workspace's `tests/aitune/` (commit `dc8577c`). Changes: the ROM without a tuning table is the
English rc8 release (`work/build/advanced-ai/base/rc8_release.nds`; the ROM tests skip without it), the held-out seeds
come from a fixture file (this project has not held out a round yet; `lib/seeds.py` reads a missing file as none), and
scratch files go to `work/build/advanced-ai/runs/aitune_test/`.

```
.venv/bin/python work/advanced-ai/testbench/dev/aitune.py --selftest      # 46 tests, about 3 s
```
