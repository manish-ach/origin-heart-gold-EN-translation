# Advanced trainer AI

An optional, stronger trainer AI for the English build. It is ported from the Spanish translation's advanced AI (release
rc44, Spanish workspace commit `dc8577c`, by luisvent, reused with their permission). Credit line (D-2510): "Advanced
trainer AI: from the Spanish translation by luisvent."

When it serves a trainer, it:
- values every move, switch and item by simulating the turn;
- vetoes moves that cannot work;
- picks its lead;
- reads the player's committed action under a gate.

For any battle it does not support, it hands the turn back to the hack's own AI. It is off by default, and the player
switches it on in Options (D-1575: an optional feature for English players). The next release includes it in its one
xdelta, still off by default (D-2506), after it passes the three test levels on the release ROM.

Everything for the feature lives in this directory. Its tests live in [testbench/](testbench/).

## Getting started

To play against the AI or run its tests, start with the quick-start in
[testbench/README.md](testbench/README.md#play-against-the-ai): set up Python, apply the rc8 patch to your USA ROM,
install the AI, make the test saves from your own save, and play or run a test level. To build a release with the AI,
follow [RELEASING.md](../../RELEASING.md), step 3.

## Status

| Phase | State |
|---|---|
| Plan | Written: [PLAN.md](PLAN.md) |
| 0. Environment and measurements | Done: tools installed, rc8 builds reproduced; ITCM arena unused, heap keeps 77 KB ([docs/memory-layout.md](docs/memory-layout.md)) |
| 1. Faithful extraction | Done: sources vendored (0db9bb3), golden test reproduces rc44 byte for byte (7b12fad) |
| 2. English build of the engine | Done: payload, installer and verifier (review fixes included); AI serves trainers on the English ROM |
| 3. Test bench and runtime verification | Done on rc8: whole bench ported, Spanish results reproduced on rc44, English references recorded (static 9/9, quick all pass, deep: 72/80 vs the hack's AI, 0 fallbacks); one known Spanish property violation awaits a reviewer |
| 4. Options setting | Row built in a development difficulty build; host tests, 14 native cases and the flag scan pass; release-tool build pending |
| 5. Review and merge | Independent review done and its fixes merged; upstream main merged (dc7a1d3): AI ITCM origin fixed at 0x01FF9500, difficulty re-pinned to main, all tiers re-pass with identical decisions; not pushed |
| Release step | `builder/release.py` (difficulty's verified candidate, the AI, the xdelta, `release.json`) with its unit tests; proven end to end with `--allow-development` on main's development difficulty build ([builder/README.md](builder/README.md), "Release"). RELEASING.md, CHANGELOG and credits written. A releasable patch still needs difficulty built with the maintainer's pinned tools, xdelta3 3.2.0 and the three levels on that ROM |

## Layout

| Path | What it holds | Added in |
|---|---|---|
| `README.md` | This overview: status, layout, rules, touch points | plan |
| `PLAN.md` | The port plan: decisions, what comes from the Spanish build, memory layout, phases, risks | plan |
| `docs/` | Research, design notes and test reports | plan |
| `PROVENANCE.md` | Every file taken from the Spanish workspace: its path there, commit, sha256, and the permission | phase 1 |
| `src/` | The AI sources: the Spanish files as taken, then our changes as separate reviewed commits | phase 1 |
| `builder/` | `build.py` (compiles and links the AI, `--layout es` or `en`), `install.py` (writes it into an AI build), `verify.py` (re-reads the result independently), `release.py` (the release patch with the AI and its receipt) | phases 1–2, 5 |
| `payload/` | The reviewed compiler output and its symbols, which normal builds install without a compiler | phase 2 |
| `data/` | The trainer-mark lists (important trainers, keep-lead trainers) and the rule that selects them | phase 2 |
| `testbench/` | Every test and test tool, in three tiers: [testbench/README.md](testbench/README.md) | phases 1–3 |

Every directory gets its own README when it is created: what it holds, what it needs, how to run it.

## Documents

| Document | Contents |
|---|---|
| [PLAN.md](PLAN.md) | The port plan |
| [docs/research-2026-10-13.md](docs/research-2026-10-13.md) | What the Spanish patch's AI is, how it was verified, why it is rebuilt from source, the constraints in this project |
| [docs/checks.md](docs/checks.md) | How the tiers run from check.py (fast, --full, the --emu part ai) and the release runbook: steps, the AI ROM, skips, commands, timings, output paths |
| [builder/README.md](builder/README.md) | The builder, installer, verifier and release step (`release.py`: what it checks, refuses and writes) |
| [docs/build-contract.md](docs/build-contract.md) | The interfaces between builder, installer, test bench and the Options row |
| [docs/memory-layout.md](docs/memory-layout.md) | Where the AI lives in memory and the measurements behind it |
| [testbench/README.md](testbench/README.md) | Test layout, tiers, pass rules, what comes from the Spanish test bench |
| `docs/test-report-*.md` | Test reports (phase 3 onwards) |

Earlier context, outside this directory: `work/notes/es_patch_comparison_20261012.md` compared the Spanish patch with
our rc7 from its bytes alone, before its source was available.

## Rules

- **No game data in git.** Never commit ROMs, saves, extracted files or ROM bytes. Build output and test runs go to the
  ignored `work/build/advanced-ai/`.
- **Provenance.** Every file that comes from the Spanish workspace is listed in `PROVENANCE.md`. A change to such a file
  is its own commit, so the diff from the Spanish original stays readable.
- **Toolchain.**
  - The AI is built with arm-none-eabi-gcc 16.2.0 and binutils 2.47, and the builder refuses other versions.
  - Normal builds install the committed payload and need no compiler.
  - The release repro check recompiles and requires identical bytes.
- **Settings.** Flags 0x2C2 (on) and 0x2C3 (important trainers only), the same as the Spanish build.
- **Scope.** The AI core only. The Spanish battle-experience lines, VS intro, boss aura, luck steering, hard mode and
  NPC are not ported ([PLAN.md](PLAN.md), "Not ported").

## Touch points outside this directory

The feature changes only these files elsewhere. Each change is listed here when it is made.

| File | Change | Phase |
|---|---|---|
| `work/tools/check.py` | Fast: `ai-payload`, `ai-unit` (no-ROM tests); `--full`: all unit tests and `ai-static`; `--emu`: the `ai` part (quick tier); `--ai-rom`. Phase 5: the AI-build skip reason points to the release step | 3, 5 |
| `work/tools/test_check.py` | Tests for the AI steps (`AdvancedAi`) | 3 |
| `RELEASING.md` | Step 3: the release chain (standard build, difficulty in release mode, `builder/release.py`) and the three tiers on the release ROM; steps 4–5: what `README.txt` and `latest.json` need for the AI | 3, 5 |
| `CONTRIBUTING.md` (Checks), `work/notes/toolchain.md` (Checks) | The AI steps in the check documentation; phase 5: toolchain.md's skip reason points to the release step | 3, 5 |
| `.githooks/pre-commit`, `.github/workflows/patches.yml` | Run the fast check for changes under `work/advanced-ai/` | 3 |
| `.gitignore` | No change needed: every output lands under the ignored `work/build/` | 3 |
| `work/research/difficulty-armips/native/options.c`, `settings.c`, `settings.h`; `native/integration_contract.json` (source overrides) | The TRAINER AI row on Options page 2 ([options-trainer-ai.md](../research/difficulty-armips/research/options-trainer-ai.md)) | 4 |
| `work/research/difficulty-armips/tests/`: `drivers/options_check.c`, `support.py`, `native_ui.py`, `native_ui_oracles.py`, `evidence.py`, `test_framework.py` | Host tests for the row; the native UI driver walks six focus positions | 4 |
| `work/research/difficulty-armips/native/runtime.c`, `items.c`; `tests/drivers/runtime_check.c`, `items_check.c` | Difficulty's pointer checks end at 0x023D4000, below the AI's main code | 4 |
| `work/research/difficulty-armips/build.py`, `install.py`, `verify.py`, `tests/run.py`, `tests/test_installer.py`, and the receipt path in every `tests/` driver (`support.RECEIPT`) | Opt-in development tools mode, `DIFFICULTY_DEV_TOOLS=1`, with its own output folder ([dev-tools-mode.md](../research/difficulty-armips/research/dev-tools-mode.md)) | 4 |
| `work/research/difficulty-armips/install.py`, `compatibility.json`, `research/items-revival-pins.json`, `native/integration_contract.json`; `work/notes/main_difficulty_compatibility_20261013.md` | Difficulty re-pinned from the rc8 standard build to main's (trainer full names in ITCM); review in the note | 4 |
| `CHANGELOG.md` | The Unreleased entry: the optional AI for players, `release.py`, the release note and the credit line | 5 |
| `README.md` (Credits), `work/notes/credits_and_sources.md` | The credit line, and the AI's source and permission | 5 |
| `AGENTS.md` | One line pointing to this directory | 5 |
