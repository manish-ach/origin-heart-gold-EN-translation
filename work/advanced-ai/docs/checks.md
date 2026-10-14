# Checks

How the advanced AI's three test tiers ([testbench/README.md](../testbench/README.md), "Tiers") plug into
`work/tools/check.py` and the release runbook ([RELEASING.md](../../../RELEASING.md)).

| Tier | Runs from | `check.py` steps | Needs | Time |
|---|---|---|---|---|
| Static, no ROM | `check.py` (the fast check) and `--full` | `ai-payload`, `ai-unit` (the unit tests that need no ROM) | Nothing beyond the fast check's own needs | About 4 s |
| Static, all | `check.py --full` | `ai-unit` (every unit test), `ai-static` (the rest of `run.py static`) | The AI build (below); optional: the toolchain, `ADVAI_ES_REPO` | About 22 s + 15 s |
| Quick | `check.py --full --emu` (the part `ai`) | `emu-ai` (`run.py quick`) | The AI build, the test bench's saves, py-desmume | About 20 min with 3 emulators (26 min with 2, beside another agent's deep run) |
| Deep | By hand; RELEASING.md requires it for every release that ships the AI | None | The same as quick | 35–80 min |

Times are from the reference machine on 2026-10-13.

## The steps

**`ai-payload`** (fast and `--full`). `payload/payload.json` records the SHA-256 of every source it was built from
(`builder/build.py`, the layout, `src/`) and of each `.bin`. The step fails when a file differs from its pin, which
catches a source edited without rebuilding the payload. It needs no toolchain and takes milliseconds. The step prints
the rebuild command:

```sh
.venv/bin/python work/advanced-ai/builder/build.py --layout en --out work/advanced-ai/payload
```

**`ai-unit`**. The unit tests in `testbench/unit/`.
- **Fast:** only the classes named in `check.py`'s `AI_UNIT_NO_ROM`. These need no ROM and no toolchain: the installer's
  and the verifier's synthetic ROMs, the toolchain pin, `ids.h` and the trainer-mark lists. `test_check.py` checks that
  each name is still a class in `unit/`.
- **`--full`:** every unit test. This adds the builder's two builds compared with the committed payload, the real-ROM
  installs and refusals, and the Spanish comparisons. A test whose input is missing skips, and the step lists each skip
  reason with its count. A missing toolchain therefore shows as `skipped (1): needs the pinned toolchain: ...`.

**`ai-static`** (`--full`). The command is `testbench/run.py static --only <every static step except unit>` on the AI
build, because `ai-unit` already ran the unit tests. The step runs the bench's claim checks against the ROM data, the
test bench's self-tests, the host-AI and simulator replays of the bench record, and aitune's tests. `run.py static
--list` gives the step names, so a step that the test bench adds later runs here too.

**`emu-ai`** (`--emu`, the part `ai`). The command is `testbench/run.py quick --workers <--emu-jobs>` on the AI build.
It runs after the emulator layer's parts, not beside them, so at most `--emu-jobs` emulators run at once. Every
emulator also takes a slot of the machine-wide pool that the harness and the test bench share
(`testbench/lib/emupool.py`). Before the run, the step checks the test bench's saves (`testbench/lib/saves.py check`).
The quick tier is judged against `testbench/references/en/`: until a reviewed reference is recorded, its bench step
fails.

```sh
.venv/bin/python work/tools/check.py --full --emu                    # the layer's four parts, then ai
.venv/bin/python work/tools/check.py --full --emu-only ai --emu-jobs 2   # only the AI's quick tier
```

## The AI build

`ai-static` and `emu-ai` run on one AI build, which is made once per `check.py` run:

- `--ai-rom ROM`, when given. `builder/verify.py` must accept it as the committed payload installed.
- Otherwise, `builder/install.py` installs the committed payload on the rc8 release
  (`work/build/advanced-ai/base/rc8_release.nds`, from the rc8 release xdelta: [build-contract.md](build-contract.md),
  "Inputs") into `<work-dir>-ai/check_ai.nds`. The default is `work/build/check-ai/`. The install takes about 2 s,
  and the installer writes the same bytes every time.

The AI build is not the `--full` build. The installer needs an English build with difficulty, and `build.py` makes
the standard build, which has none. So the static and quick tiers check the committed payload on the rc8 release, not
this commit's standard build. A change to the standard build that moves bytes the AI depends on (the hook sites, the
arena words, overlays 10, 11 and 14, the trainer headers) shows up only when the AI is installed on a difficulty build
of that commit. Give that build with `--ai-rom`.

## Skips and failures

| Situation | Result |
|---|---|
| No rc8 release and no `--ai-rom` | `ai-static` and `emu-ai`: SKIP, with a note |
| The test bench's saves are missing or wrong | `emu-ai`: SKIP, with the `saves.py make` command |
| No toolchain, no `ADVAI_ES_REPO`, no Chinese ROM | `ai-unit`: those tests skip; the step passes and lists the reasons |
| `--ai-rom` names a missing file, or a ROM that `verify.py` rejects | FAIL |
| The installer refuses the rc8 release | FAIL |
| py-desmume is missing under `--emu` | FAIL (as for the emulator layer) |
| A tier step fails | FAIL; the step shows the tier's rows and its log |

A missing AI input is never a failure, `--strict-release` included. `check.py --full` checks the standard build,
which holds neither difficulty nor the AI; the release installs both after it (RELEASING.md, step 3), so the standard
gates must not wait on the AI's inputs. The release runs the three tiers on its own AI ROM (below), where a SKIP does
not count as a pass.

## A release that ships the AI

The next release ships the AI in its one xdelta, off by default (D-2506). Its ROM is the standard build, then
difficulty, then the AI, made by `builder/release.py` ([builder/README.md](../builder/README.md)); RELEASING.md,
step 3, gives every command in order. These three run on that ROM:

```sh
ROM=work/build/release-ai/<tag>/origin_hg_v4.0.3_en_ai.nds     # from release.py --out-dir
P=work/advanced-ai/payload/payload.json
.venv/bin/python work/tools/check.py --full --strict-release --ai-rom "$ROM"
.venv/bin/python work/advanced-ai/testbench/run.py quick --rom "$ROM" --payload $P --workers 3 \
    --options-receipt work/build/difficulty-v2/integration-impl/receipt.json
.venv/bin/python work/advanced-ai/testbench/run.py deep --rom "$ROM" --payload $P --workers 3
```

- `check.py` runs `ai-unit` and `ai-static` on the release ROM. A SKIP of either one blocks the release.
- The quick tier runs directly, not as `--emu-only ai`, so that it can take the difficulty receipt. With the receipt it
  also checks the Options row (`checks/options_trainer_ai.py`).
- The deep tier takes 35–80 minutes with 3 emulators. It passes when the 80 AI-vs-AI logs are byte-identical to
  `references/en/aivsai.json`. When logs differ, it passes if the advanced AI wins 80–94% of the counted games, and
  the release notes must then name the change that moved the logs ([testbench/README.md](../testbench/README.md)).

## Output

Everything lands under the ignored `work/build/`:

| Path | What |
|---|---|
| `work/build/check-ai/` (`<work-dir>-ai/`) | The AI build, its install receipt, the `static-*.log` and `quick-*.log` of each run |
| `work/build/advanced-ai/runs/tiers/<tier>_<layout>_<time>/` | The tier's step logs and `summary.txt` (`run.py`) |
| `work/build/advanced-ai/runs/` | The tools' own work files: aibench runs, AI-vs-AI reports, simulator runs |
| `work/build/advanced-ai/{hostai,sim}/<ROM name>[_<layout>]/` | The host-AI and simulator builds for that ROM |
| `work/build/advanced-ai/saves/` | The test bench's saves (`lib/saves.py make`) |

Files that are written into the source tree on purpose, and committed after review:
- `testbench/references/<layout>/`, by `run.py --record`;
- `payload/`, by `builder/build.py --out work/advanced-ai/payload`;
- `src/IDS.md`, by `unit/test_ids.py --write`;
- `lib/names.json`, by `lib/names.py`;
- the simulator's fitted model (`sim/origmodel.h`, `sim/origparams.json`), by `sim/origfit.py`.
