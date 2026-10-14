# Advanced trainer AI: port plan

Branch `feature/advanced-ai` (from `main` 204e1f8, rc8; `origin/main` 425c1ee merged in). Research behind this plan:
[docs/research-2026-10-13.md](docs/research-2026-10-13.md). The directory layout and the rules every phase follows are
in [README.md](README.md).

The feature is the Spanish translation's advanced trainer AI at release rc44 (Spanish workspace commit `dc8577c`, by
luisvent, reused with their permission). It ships as an optional setting, off by default (D-1575). Built and tested on the branch;
not merged yet (PR target: `develop`).

## Decisions

| # | Decision | By |
|---|---|---|
| 1 | Reuse the Spanish AI source | luisvent, 2026-10-13 |
| 2 | Port the AI core only; nothing else from the Spanish build for now | luisvent, 2026-10-13 |
| 3 | Keep the Spanish behaviour: the AI reads the player's committed action (70%/30% gate) and uses foresight | luisvent, 2026-10-13 |
| 4 | The setting lives on the Options screen; no Pokémon Centre NPC | luisvent, 2026-10-13 |
| 5 | Build it with arm-none-eabi-gcc, version-pinned | luisvent, 2026-10-13 |
| 6 | Port the whole AI test bench and run it on every AI build | luisvent, 2026-10-13 |
| 7 | Everything for the feature lives in `work/advanced-ai/`, tests in `work/advanced-ai/testbench/` | luisvent, 2026-10-13 |
| 8 | The next release includes the AI in its one xdelta, off by default | luisvent, 2026-10-13 |
| 9 | Row values OFF / KEY / ALL, with the help line as built | luisvent, 2026-10-13 |
| 10 | The PR targets `develop` | luisvent, 2026-10-13 |
| 11 | The property test's `hp p0072 T` case is accepted as the Spanish AI's own behaviour | luisvent, 2026-10-13 |
| 12 | No real-hardware test before merge: the release notes say so and ask testers to report | luisvent, 2026-10-13 |
| 13 | Credit: "Advanced trainer AI: from the Spanish translation by luisvent." | luisvent, 2026-10-13 |
| 14 | Test saves are derived from the developer's own save (`testbench/lib/saves.py make --base`), never committed | luisvent, 2026-10-13 |
| 15 | This branch records main's current build hashes in `work/patches/expected.toml` | luisvent, 2026-10-13 |

luisvent is a contributor, not the maintainer: these are recorded in the decision register as provisional
(`--source agent:advanced-ai`), pending the maintainer's acceptance.

## What comes from the Spanish build

Every Spanish file is taken from commit `dc8577c` and listed in `PROVENANCE.md` (path, sha256, permission).

### Ported unchanged: into `src/`, then verified by the golden test

| Spanish file | Lines | What it is |
|---|---|---|
| `work_es/tools/ai/advai.c` | 8,129 | The AI: snapshot, move/switch/item valuation, battle simulation, veto rules, read gate (`foe_choice`, `rd_gate`), foresight, `ai_resume`, `ai_slot_free`, `write_action`, fallback to the hack's AI |
| `work_es/tools/ai/replace.c` | 522 | Which Pokémon to send in after a faint |
| `work_es/tools/ai/lead.c` | 117 | The trainer's lead pick in singles |
| `work_es/tools/ai/engine.h` | 198 | Engine addresses, structure offsets and the hack functions the AI calls (Chinese v4.0.3) |
| `work_es/tools/ai/tune.h` | 16 | The tuned constants (the game runs the defaults) |
| `work_es/tools/asm/aiselect.s` | 139 | `ai_serves`, `ai_slot_select`, `ai_entry`, `ai_bag_check`: who the AI serves, loading overlay 10, routing each poll |
| `check_flag` from `work_es/tools/asm/hardmode.s` | 8 | Reads a script flag; `aiselect.s` needs it. Only this routine is taken, not hard mode |

### Ported with changes

| Spanish source | Goes to | Change for this project |
|---|---|---|
| `work_es/tools/ai/link.ld` | `src/link.ld` | New memory regions for our layout (see "Memory layout"). The section rules stay |
| `build.py`: `link_ai`, `resident_sections`, `slot_spill`, `largest_first`, `ai_overlay_entry`, `room_line`, `AI_CFLAGS` | `builder/build.py` | One standalone builder with two layouts: `--layout es` (the golden test only) and `--layout en`. Output only in the ignored `work/build/advanced-ai/` |
| `build.py` `AI_IDS` + `ai_ids_header()` | `src/ids.h` | A frozen numeric header replaces name lookup through our old rc3 names. It is checked to equal the Spanish generation, and a test names each ID through our glossary |
| `build.py` `IMPORTANT_TRAINERS` (453), `KEEP_LEAD_TRAINERS` (129) | `data/` | Trainer-ID lists, written as bits 0 and 1 of header byte 2 in `a/0/5/5`. The selection rule (`work_es/tools/trainers/important.py`) is documented next to them; porting the generator is optional |
| Flags 0x2C2 (on) and 0x2C3 (important trainers only) | `src/aiselect.s` | Same flags and meanings, so a save's setting means the same in both translations. The switch is our Options row instead of the NPC |
| Steering (`steer_gate`, externs from `steer.s`) | `src/advai.c` | Compiled out. We have no hard mode, and the hack's scripts must not be able to switch it on through flag 0x218 |
| Test words at the top of ITCM (`NOREAD`, `NOLEAD`, `SELFPLAY`, the foresight word, Read and Replaced records) | `src/engine.h` | Kept, but moved if the resident code goes to main RAM. They stay test-only |
| The whole AI test bench | `testbench/` | See [testbench/README.md](testbench/README.md): what comes over, where each tool goes, the three tiers that run on every AI build |

### Not ported

| Spanish feature | Why |
|---|---|
| Battle experience: reaction lines, pauses, cries, recall sound, last-Pokémon music, shake, flash, dodge, replays (`battleux*`, `uxdrama*`, `uximpact.c`, `uxpace.s`, `uxshow.s`, `uxmoments.s`, `uxhits.s`, `pokeanim.c`) and the 1,723 lines in bank 718 | Scope (decision 2) |
| VS intro (`vsintro.s`, a/0/5/8 sprites) | Scope |
| Boss aura (`aura.c`, bit 2 marks, battle strings) | Scope; needs hard mode |
| Luck steering (`steer.s`, hooks 0x02223D36 and 0x0222025C) | Scope; needs hard mode |
| Hard mode, level caps, hard-mode items and EXP (`hardmode.s` except `check_flag`, `levelcap.s`, `hmitems.s`, `hardexp.s`) | Scope; we have our own difficulty settings |
| Foe party balls on the battle menu (`fgauge.c`) | Scope (not part of the AI) |
| Pokémon Centre NPC (script 2072, 24 map objects, bank 38 strings) | Decision 4 |
| Speed toggle, event Pokémon, Spanish text and graphics, `grow_arm9` and the Spanish ITCM layout | Scope / not applicable |
| `enginefix.s` (hack bugs the Spanish AI testing found) | Separate track: each bug through the D-2387 process ([research](docs/research-2026-10-13.md), section 7). The AI does not need them: it already works around the resist-berry bug |
| Spanish ports of our own fixes | We already have the originals |
| Checks for features not ported: `ainpc_check.py`, `uxcheck.py`, `impactcheck.py`, `pokeanimcheck.py`, `aura_check.py`, `vscheck.py`, `hardmode_check.py` | They test the NPC, battle experience, aura, VS intro and hard mode |

## Memory layout for the English build

| Part | Spanish rc44 | English plan |
|---|---|---|
| Overlay 10 | 0x021E4DA0: overlay 11 copy + 34,144 B slot code, bss 0x9E0, 2,688 B free | The same. The slot shape does not depend on our other code |
| Resident code ~23.8 KB | Appended to the ITCM block at 0x01FF8620 | **A:** a new autoload section at 0x01FF8FC0, after text speed, leaving the existing ITCM block (and difficulty's pin on it) unchanged. Needs proof that the SDK ITCM arena is never allocated, and the ITCM arena bound word 0x020D1A28 (owned by text-speed) moved past it. **B:** main RAM (below) |
| Resident code ~24.2 KB | New autoload section at 0x02264920 | Main RAM, a new autoload section next to difficulty's at 0x023DC000, lowering the arena-high word 0x020D1970 again. Costs ~24 KB of main heap (~52 KB with option B) |
| Work RAM 4,056 B + 116 B records | ITCM top | Same place with option A; main RAM with option B |
| Hooks | 5 core + 2 steering BL in overlay 14 | The 5 core ones, each guarded by its original bytes: 0x02223D10, 0x02203736, 0x02203C06, 0x022029CC, 0x022153C2 |

Phase 0 measures which option is safe. A is preferred: it keeps the heap and runs from fast memory, as the Spanish
build does. The chosen layout is then documented in `docs/memory-layout.md`.

**Delivery vehicle.** `builder/install.py` runs after the difficulty installer, on its pinned output. It writes
overlay 10 and its y9 entry, the autoload sections, the arena words, the 5 hooks and the trainer marks. Then
`builder/verify.py` re-reads everything independently and writes a receipt. For a release, `builder/release.py` runs
both on difficulty's verified candidate and makes the xdelta (builder/README.md, "Release").

The reviewed compiler output (bytes, symbols, source digest) is committed in `payload/`, like text speed's
`payload.json`, so normal builds need no compiler. The release repro check recompiles with the pinned gcc 16.2.0 and
binutils 2.47 and requires identical bytes.

Later, both this and difficulty should move into the patch registry. That needs an "overlay replace" and an "autoload
section" kind, which difficulty also lacks.

## Phases

Each phase ends in a state that can be checked. Nothing is merged before phase 5. Each phase updates the status table in
[README.md](README.md), and the README of every directory it creates.

### Phase 0: environment and measurements

1. Put the untouched Chinese ROM at `work/rom/origin_v4.0.3_cn.nds` in the worktree (ignored). The copy in the Spanish
   workspace matches our recorded sha256 `4807ab2c…95c8`.
2. Install the pinned build tools that are missing here: armips v0.11.0, `ld.lld` (difficulty's link), Python 3.14.8
   (`work/.python-version`; pyenv has no such version on this machine) and the Python environment. These are
   downloads, so they need the user's go-ahead.
3. Build the rc8 baseline and the difficulty candidate, and check them against `expected.toml` and difficulty's pins.
4. Measure:
   - **ITCM arena:** a melonDS write watchpoint on 0x01FF8FC0–0x02000000 across field, menus and battles (singles,
     doubles, Bag, party, summary). Zero writes allows option A.
   - **Main heap:** headroom with `memcheck.py` on the battle-heavy screens, with 24 KB and 52 KB removed.

**Exit:** placement chosen; `docs/memory-layout.md` written.

### Phase 1: faithful extraction

1. Copy the "ported unchanged" files into `src/` and write `PROVENANCE.md`.
2. Write `builder/build.py` with the gcc/binutils version check.
3. **Golden test** (`testbench/unit/`): with `--layout es`, the builder reproduces rc44's overlay 10 image, y9 entry,
   ITCM AI code and main-RAM AI code byte for byte. Hashes are recorded in the test; no ROM bytes are committed.
4. Freeze `src/ids.h` and test it against the Spanish generation and our glossary.

**Exit:** golden test and unit tests pass. Our ROM is not touched yet.

### Phase 2: the English build of the engine

1. Source changes in `src/` as separate reviewed commits: steering compiled out, the test-word addresses moved if
   option B.
2. Run `--layout en` and commit the reviewed payload in `payload/`.
3. Write `builder/install.py` and `builder/verify.py` as described under "Delivery vehicle", with the trainer marks in
   `data/`.
4. Static checks in `testbench/unit/`:
   - no overlap with any fix region;
   - every engine address the AI calls lies outside fix regions;
   - header byte 2 is read nowhere in the hack (capstone scan);
   - sizes stay within budget;
   - a double build is byte-identical.

**Exit:** the candidate ROM boots. With both flags clear, gameplay matches the difficulty candidate. Setting the flags
through the harness turns the AI on.

### Phase 3: test bench and runtime verification

1. Port the whole test bench into `testbench/`, following [testbench/README.md](testbench/README.md).
2. Wire the tiers in:
   - the static tier into `check.py`;
   - the quick tier as an `ai` part of `--emu` (next to `fixes`, `scenarios`, `textfit`, `freeze`);
   - the deep tier as `testbench/run.py deep`, which the release runbook requires.
3. Record the reference results from the first passing AI build in `testbench/references/`.
4. **AI off:** our emulator suite and difficulty's native cases pass unchanged.
5. **AI on:**

   | Check | Target |
   |---|---|
   | 80 AI-vs-AI games against the hack's AI | within the Spanish 95% range (80–94% wins) |
   | Fallbacks | none beyond the Spanish rate |
   | `aiprops` violations | 0 |
   | `aibench` | at or above the Spanish 97.8% |

6. **Cases:**
   - each setting;
   - doubles and multi battles (handed to the hack's AI);
   - partners;
   - the Bag or party opened while the trainer waits;
   - a replacement after a faint;
   - the lead pick;
   - our fixes the AI's calls pass through (zero-PP Struggle, targeting, faint timing).
7. Heap headroom with English text, a melonDS interpreter run, and one real-DS smoke test (needs a flashcart owner).

**Exit:**
- the three tiers run from `check.py` and the release runbook;
- reference results are recorded;
- a test report in `docs/` shows every gate passed or explained.

### Phase 4: the Options setting

1. Add a TRAINER AI row to Options page 2, next to ITEMS, SHARE and CAP. It has three values: OFF / KEY / ALL (labels
   to confirm). It writes flags 0x2C2/0x2C3 through the same draft/apply/cancel transaction as difficulty.
2. This changes difficulty's `native/options.c`, outside this directory (README, "Touch points"). Page 2 draws three
   rows at y 8/40/72 with the controls hint at 108, so a fourth row needs a layout change; it is reviewed with
   screenshots.
3. Native checks in `testbench/checks/`: captures, cursor, touch, apply, cancel, save and reload.

Phase 4 can run in parallel with phase 3, because phase 3 sets the flags through the harness.

**Exit:** the setting works in game and persists in the save.

### Phase 5: review and merge

1. An independent review by a separate agent, then fixes.
2. Documentation:
   - every README in this directory current;
   - CHANGELOG and release notes (an optional feature, off by default);
   - credits for the Spanish project;
   - a pointer from `AGENTS.md` to this directory;
   - the decisions recorded by the maintainer.
3. Merge into `develop` with the installer not run by default. The next release ships it (decision 8): its release
   step is `builder/release.py`, after difficulty and before the three tiers on the release ROM (RELEASING.md, step 3).

## Risks

- **Fast memory may not be free.** If the ITCM arena is in use, every resident byte goes to main RAM, where English
  text already presses the heap.
- **Three owners share the same bytes.**
  - Text speed owns 0x020D1A28.
  - Difficulty pins arm9 and overlay 14 and owns the Options page.
  - The AI touches all three.
  Every change needs those owners' checks to pass again.
- **The slot is nearly full.** Overlay 10 has 2.7 KB of slack, so a compiler change or new AI code can overflow it into
  overlay 14.
- **Our fixes change the code the AI calls.** It calls about 85 engine addresses. None is inside a fix region, but our
  fixes alter some of the code paths behind them.
- **No real-hardware evidence.** Neither the Spanish nor our build has run the AI on a DS.
- **Tied to hack v4.0.3.** Every address the AI uses is a v4.0.3 address.
