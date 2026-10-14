# Unit tests

The static tier's own tests for the advanced AI: builder, golden test, ids, installer, verifier, release and trainer marks. Standard `unittest` files named `test_*.py`, with no emulator.

```sh
.venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit            # all of them
ADVAI_ES_REPO=/path/to/spanish/repo .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit
.venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_golden*.py'
```

Run from the repository root with the worktree's `.venv/bin/python`.

| File | What it checks | Needs (skips without it) |
|---|---|---|
| `test_build.py` | The toolchain pin refuses other versions and writes nothing. The en payload's schema, region limits, symbols, hooks and words. The itcm section's bss covers every `.itcm_bss` variable and stops below 0x01FFFF8C. Steering compiled out (only `ai_serves` calls `check_flag`). No overlay 11 bytes in the payload. Two builds are byte-identical. The committed `payload/` equals a fresh build. The en layout's hook `before` bytes equal the Chinese ROM's, the rc8 release's and main's; the ITCM arena word equals each build's ITCM block end, below the itcm origin. The itcm origin clears `trainer_display.py`'s largest block by 0x100 | Toolchain; the Chinese ROM, rc8 release and main standard build for the ROM checks |
| `test_golden.py` | `build.py --layout es` reproduces rc44's overlay 10 slot code, y9 entry, ITCM code, main-RAM AI code and the five hook BLs byte for byte. The sha256s are recorded in the test | Toolchain; the Spanish repository; `work/build/advanced-ai/es/rc44.nds` for the byte comparison |
| `test_ids.py` | Every id in `src/ids.h` names the right move, ability or item in our text banks. `src/IDS.md` lists exactly those ids. `ids.h` equals a fresh Spanish generation. `test_ids.py --write` rewrites `IDS.md` | The Spanish repository with its `work_es/rom/` ROMs and the toolchain, for the generation check only |
| `test_install.py` | Every refusal on synthetic inputs, the receipt, a real install onto the rc8 release and the refusals on real ROMs (Chinese, rc8 standard, rc44, an already installed ROM) | The rc8 release for the real-ROM cases |
| `test_verify.py` | The verifier catches each kind of wrong byte (hook, word, region, overlay 10, marks) | The rc8 release for its real-ROM case |
| `test_release.py` | `builder/release.py` refuses each input a release must not be built from and writes nothing; `--allow-development` marks the output not releasable; `release.json` chains every hash, and the xdelta, applied on its own, gives the AI ROM and carries build.py's file names. Synthetic: the installer tests' ROM and payload, a synthetic difficulty receipt and verification, random bytes as the USA ROM | xdelta3 on PATH for the two cases that write a patch |
| `test_marks.py` | `data/trainer_marks.json` against the Spanish build's lists and rc44's bits; byte 2 clear in every input; nothing in the hack reads byte 2 | The Spanish repository and the ROMs |

## Inputs

| Input | Where |
|---|---|
| arm-none-eabi-gcc 16.2.0, binutils 2.47 | `PATH` |
| Spanish workspace repository (read only; archived at commit `dc8577c` into a temporary directory) | `ADVAI_ES_REPO=/path/to/spanish/repo` (no default; the tests that need it skip when it is unset) |
| Untouched Chinese ROM | `work/rom/origin_v4.0.3_cn.nds` |
| English rc8 release | `work/build/advanced-ai/base/rc8_release.nds` |
| English standard build from main (trainer full names) | `work/build/advanced-ai/base/main_standard.nds` |
| Spanish rc44 | `work/build/advanced-ai/es/rc44.nds` |

The ROMs and the Spanish archive are read at test time and never copied into the repository. Each test that lacks
an input skips and names it.

Time: about 10 s for `test_build.py` (two builds), 10–20 s each for `test_golden.py` and `test_ids.py`, a few
minutes for `test_install.py`, `test_verify.py` and `test_marks.py` (real-ROM installs and the marks scan).
