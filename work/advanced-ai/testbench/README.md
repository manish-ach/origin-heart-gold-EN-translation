# Advanced AI test bench

## Play against the AI

From the repository root, on the `feature/advanced-ai` branch:

1. Python 3.14 and xdelta3 (macOS: `brew install python@3.14 xdelta`), then
   `python3.14 -m venv .venv && .venv/bin/pip install -r work/tools/requirements-runtime.txt`.
2. Put your own Pokémon HeartGold (USA) ROM at `work/rom/Pokemon - HeartGold Version (USA).nds`.
3. Download the release patch `Origin_HeartGold_v4.0.3_EN_v1.0.0-rc8.xdelta` from the repository's GitHub releases
   and apply it: `mkdir -p work/build/advanced-ai/base && xdelta3 -d -s "work/rom/Pokemon - HeartGold Version (USA).nds" Origin_HeartGold_v4.0.3_EN_v1.0.0-rc8.xdelta work/build/advanced-ai/base/rc8_release.nds`.
4. Install the AI: `.venv/bin/python work/advanced-ai/builder/install.py --input work/build/advanced-ai/base/rc8_release.nds --out work/build/advanced-ai/ai.nds`.
5. Make the test saves from a save of your own game (a raw 512 KiB `.sav` from melonDS or a flashcart, or a DeSmuME
   `.dsv`; at least one Pokémon that is not an Egg): `.venv/bin/python work/advanced-ai/testbench/lib/saves.py make --base /path/to/your/save.sav`.
6. Play: `.venv/bin/python work/advanced-ai/testbench/versus/aiplay.py 3 --rom work/build/advanced-ai/ai.nds --payload work/advanced-ai/payload/payload.json`.
   Click the window once, then: DS A = X, B = Z, X = S, Y = A, L = Q, R = W, Start = Enter, Select = Right Shift,
   D-pad = arrow keys, touch screen = left mouse button. Close the window or press Ctrl+C to stop; every battle is
   logged under `work/build/advanced-ai/runs/aivsai/human/`.

The ROMs and saves are yours and stay out of git (`*.nds`, `*.dsv`, `*.sav` are ignored).

## The test bench

Every test and test tool for the advanced trainer AI lives here: our own unit tests and the test bench ported from the
Spanish translation (commit `dc8577c`) ([PLAN.md](../PLAN.md), phases 1 and 3). Each ported tool's docstring and its
directory's README say what changed from the Spanish tool.

```
T=work/advanced-ai/testbench
.venv/bin/python $T/lib/saves.py make --base /path/to/your/save.sav        # once: the test saves (or, the reference
ADVAI_ES_REPO=/path/to/spanish/repo .venv/bin/python $T/lib/saves.py make  #   ones, from the Spanish repository)
.venv/bin/python $T/run.py static|quick|deep --rom ROM --payload PAYLOAD [--workers N] [--list] [--only STEP,...]
                 [--options-receipt RECEIPT] [--record]     # exit 1 when a step failed
```

The payload is the AI build's `payload.json`: `work/advanced-ai/payload/payload.json` for ours,
`work/build/advanced-ai/es/payload/payload.json` (the builder's `--layout es`) for the Spanish rc44. Every tool imports
the others by bare name after `import tbpaths` (`lib/README.md`, "Import convention").

**Saves and references.** The references in `references/` were recorded with the reference saves (the Spanish
workspace's, `saves.py make` from its repository). Saves derived from your own game (`make --base`, `lib/saves.py`
lists what is normalised and what still comes from your save) run every tool, but they are other bytes: every tier
prints where its saves came from, the deep tier compares the AI-vs-AI logs with the reference only with the reference
saves (otherwise it judges the win range alone and says so), and `--record` refuses other saves.

An **AI build** is our standard build, then the difficulty installer, then the AI installer. A change to any of the
three makes a new AI build, and the tiers below run on it.

## Layout

| Directory | What it holds | Tier |
|---|---|---|
| `run.py` | The one entry point: `run.py static`, `run.py quick`, `run.py deep`. The list of what each tier runs (`STEPS`) lives here and nowhere else; a step whose tool is missing is listed as pending and skipped | all |
| `lib/` | Shared code: the emulator runner, ROM data readers, the payload's addresses, the frozen names (`names.json`), the test saves, the emulator and simulator pools, the random teams, failure sorting, seed bookkeeping | – |
| `unit/` | Our own tests: builder, golden test, `ids.h`, trainer marks, installer guards, fix-region overlap, sizes | static |
| `bench/` | Graded decisions from set-up positions: `aibench`, its scenarios, batches and claim checks | static (claims), quick (runs) |
| `checks/` | Pass/fail behaviour checks. Quick: `aimode_check`, `lead_check`, `read_check`, `menulock --advanced foe_pp4 foe_pp4_one foe_pp4_bench foe_pp4_double` (only those four: the others test Spanish fixes we lack), `ai_smoke`, and `options_trainer_ai` (the Options row; only on a difficulty build with the row, given `--options-receipt`). Deep: `fscheck` (foresight), `storycheck` (story battles with the AI on; a case the build without the AI ends the same way is INHERITED and passes), `itcm_arena` | quick, deep |
| `props/` | Property tests on random positions (`aiprops`) | quick (short), deep (full) |
| `versus/` | AI-vs-AI games against the hack's AI, their report, team generation, the live view, play mode, analysis helpers | deep |
| `fuzz/` | Random battles played to the end: `aifuzz --double --mode advanced` | deep |
| `sim/` | The PC battle simulator (C), driven by the ROM's data: `bench_check.py --rom ROM [--layout en]` (exit 2: no bench record, a skip); `simbuild.py` builds the simulator | static, development |
| `hostai/` | The AI built for the PC (C): `replay.py --rom ROM [--layout en]` replays the bench record (exit 2: no bench record, a skip) | static |
| `dev/` | Tools no tier runs: `aibuild`, `aibatch`, `aitune`, `aicalc`, `aitime`, engine probes; `dev/tests/` holds `aitune.py --selftest`'s tests, which the static tier runs | static (`aitune --selftest`), none |
| `references/` | Recorded reference results: bench scores, AI-vs-AI log digests, property-test seeds. No ROM bytes | all |

Every directory gets its own README when it is created: what is in it, what it needs, how to run it.

Run output goes to the ignored `work/build/advanced-ai/runs/` (a tier's to `runs/tiers/<tier>_<layout>_<time>/`).
`--layout en` compiles the host AI with `en.json`'s `-DAI_NO_STEER`; the simulator's and the host build's output goes
to `work/build/advanced-ai/{sim,hostai}/<ROM>[_<layout>]/`. Pre-battle saves are made locally by `lib/saves.py` and
checked by SHA-256 against their manifest, and are never committed (`*.dsv` and `*.sav` are ignored). The Spanish Violet
Gym save's lead has edited stats (998/297 HP after a battle): the bench, AI-vs-AI and property tests replace both
parties before every battle, and the checks that fight with the save's own party cap its HP first, since the AI's range
check would otherwise hand every turn to overlay 11.

## Tiers

| Tier | When | What runs | Time |
|---|---|---|---|
| Static | Every `check.py` run, fast and `--full` | `unit/`; the bench's claim checks against ROM data (no emulator); the self-tests of `aiprops`, `aivsai_report`, `aivsai_live`, `score_round`, `aitune`; `versus/test_*.py` and `lib/test_*.py` (trainer names, the save derivation); `hostai/replay.py` and `sim/bench_check.py` on the ROM's bench record (skipped until the quick tier made one) | about 1 min (28-66 s on the English AI build, most of it the unit tests) |
| Quick | Every AI build: the `ai` part of `check.py --full --emu` | `bench/` (365 graded scenarios; 364 on our data, see `bench/README.md`); `checks/`: `aimode_check` (each setting, doubles, partner, Gym trainer, story character), `lead_check`, `read_check`, `menulock` (the foe's four no-PP cases), `ai_smoke`, `options_trainer_ai` (with `--options-receipt`); a short `props/` run (20 positions, seed 1) | 18.5 min with 3 emulators on the English AI build (bench 6.7 min, checks 9.4 min, props 2.3 min) |
| Deep | Any change to the AI, to the overlay-14 code it hooks, or to the engine code it calls; every release candidate | `versus/`: 80 games (seed 101) compared with the reference; the full `props/` run (100 positions, seed 1); `checks/`: `fscheck` (foresight), `storycheck` (story battles with the AI on), `itcm_arena`; `fuzz/aifuzz.py --double --mode advanced` | 61 min with 3 emulators (AI-vs-AI 18.6 min, props 11.5, story 9.2, fuzz 17.3, foresight and arena 4.8) |

The references are in `references/<layout>/` (`references/README.md`).

Every judged step reports the AI's fallbacks (turns the hack's AI decided where the advanced AI should have), and fails
on more than the reference has.

**Quick tier passes when:**
- the bench scores at or above the reference, with 0 fallbacks, every decision from overlay 10, no error, and no more
  runs with clipped text than the reference (our ROM's ability pop-ups clip with the AI on or off);
- every check in `checks/` passes;
- the property tests find no violation other than the reference's known ones (each with a reviewer's reason).

**Deep tier passes when** its checks, fuzzing and full property run pass as above, and the 80 game logs are
byte-identical to the reference. The Spanish logs are deterministic
(synced luck, pinned clock): rc42's 80 logs were byte-identical to rc41's.

If the logs differ, the report must name the change that caused it, and the win count must stay within the Spanish 95%
range (80–94%). A new reference is recorded only with a reviewer's sign-off.

## What comes from the Spanish test bench

| Spanish file | Lines | Goes to |
|---|---|---|
| `tools/emu.py`, `aidata.py`, `romio.py`, `emupool.py`, `simpool.py`, plus `gen4text.py` (as `text.py`), `savetool.py`, and the parts of `aifuzz.py` (`randteams.py`, `failures.py`) and `aitune.py` (`seeds.py`) that several directories use. Not ported: `melon.py` (no melonDS backend) and `buildpool.py` (the builder does not run the Spanish `build.py`) | 1,849 | `lib/` |
| `tools/aibench.py`, `tests/ai_scenarios.py`, `tests/ai_checks.py`, `tests/ai_helpers.py`, `tests/ai_batches/` (27 files) | 2,584 + batches | `bench/` |
| `tools/aimode_check.py` (rewritten for the Options row), `lead_check.py`, `read_check.py`, `fscheck.py`, `qa/ai_research/menulock.py`, the `storycheck --ai` cases | 1,944 + cases | `checks/` |
| `tools/aiprops.py` | 1,181 | `props/` |
| `tools/aivsai.py`, `aivsai_report.py`, `aiteams.py`, `aivsai_live.py`, `aiplay.py`, `qa/aivsai/human_games.py`, `score_round.py`, `mirror_check.py`, `fix_outcomes.py` | 4,619 | `versus/` |
| `tools/aifuzz.py` | 460 | `fuzz/` |
| `tools/sim/` | ~17,300 together with `hostai/` (C and Python) | `sim/` |
| `tools/hostai/` | (above) | `hostai/` |
| `tools/aibuild.py`, `aibatch.py`, `aitune.py` (+ `tests/aitune/`), `aicalc.py`, `aitime.py`, `qa/ai_research/` probes (`aiprobe`, `factprobe`, `paraprobe`, `effectcheck`, `bpp_dump`, `animcheck`) | 6,397 + tests | `dev/` |

Not ported: the checks for features we do not port (`ainpc_check.py`, `uxcheck.py`, `impactcheck.py`,
`pokeanimcheck.py`, `aura_check.py`, `vscheck.py`, `hardmode_check.py`).

## How the ported tools were changed

- **Imports.** The Spanish tools sat in one flat folder and imported each other by name. Here every script puts `lib/`
  on `sys.path` and imports `tbpaths`, which adds every test bench directory, so the modules keep their bare names.
- **Symbols.** Every AI-build address comes from the build's `payload.json` through `lib/payload.py` (the slot and
  overlay-11 code ranges, the debug record, the tuning table, the test words of `src/engine.h`), in place of the
  Spanish `build.ITCM_SYMS`, `require_itcm_match` and fixed constants. The hack's own engine addresses stay constants.
- **Speed toggle.** Not ported. The ROM is never changed; the emulator runs as fast as it goes, and walking uses 8
  frames per tile (the value the Spanish tools used for rc44 and for the hack's main loop).
- **Names.** Species, moves, abilities, items, trainer classes and natures come from the frozen table `lib/names.json`
  (the Spanish workspace's English names by ROM id), never from the ROM's text, so the same games log the same names
  on both ROMs.
- **English text.** The battle's verdict in `aivsai` and `fix_outcomes`, and a failure's move message, are read in
  English and in Spanish.
- **Turning the AI on.** The tools write flags 0x2C2/0x2C3 into the save in RAM after every state load
  (`lib/emu.py set_ai_setting`, as the Spanish `impactcheck.py` did), so no test depends on the Options row. They also
  set them in the battery save the pre-battle state is made from (`aibench.setting_save`), as the Spanish tools did:
  with the flags only in RAM, 3 of 365 rc44 bench decisions came one frame earlier or later than the Spanish tool's.
- **Emulator.** py-desmume 0.0.9 with execution hooks; no melonDS backend. Battery saves live in the test bench's own
  DeSmuME config folder (`RUNS/xdg`), never `~/.config/desmume`; workers open symlinks of the ROM, not copies. The
  emulator pool shares our harness's slots.
