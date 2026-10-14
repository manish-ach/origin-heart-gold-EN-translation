# Difficulty candidate test suite

Run from the repository root with the existing `.venv/bin/python`. No downloads,
original ROM/save writes, production edits or emulator startup are needed for
the default suite. Generated binaries, masks, staged ROMs, logs and reports stay
under ignored `work/build/difficulty-v2/tests/`.

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py
.venv/bin/python work/research/difficulty-armips/tests/run.py --require-complete
```

The first command runs host/static/framework tests; `success: true` describes
that selected scope, **not feature completion**. The second must exit nonzero
until every case in `required_native.json` has current native evidence. The
manifest currently declares 69 cases. `complete` is separate from host success.

The parent can request emulator permission for this stable command:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --require-complete
```

`--native` runs host checks, then serial, supervised processes:
`ui` (240 seconds by default; use `--native-timeout 360` for the extended matrix),
`reload`, `cold0`, and `newgame` (120 seconds each), then `battle` (the same
`--native-timeout` bound as UI), followed by the selected ITEMS jobs
(each also bounded by `--native-timeout`; default: Potion ALL/restricted). They use the installed
candidate and copied batteries with no old `.dst`, RTC/movie override or host
settings writes. Each phase has its own terminal result/process/log files under
`native-tests/`. All phases are attempted so an independent defaults probe is
not lost behind a UI failure. Reload requires a current, nonce-bound native Save
checkpoint and byte-identical exported battery; stale checkpoints fail closed.

Current prepared UI coverage includes the five original input cases, six focus
captures, every ordinary row Apply/Cancel, 32 difficulty/title/TEXT SPEED input
combinations, native Save/export/Origin CRC-mirror inspection, and a real
L/R/START/SELECT reset with nonzero-before/zero-after BSS and saved-word reload.
The separate reload process checks native SaveData, custom/ordinary reentry,
startup title extraction and a real field text-printer read. The blank-battery
phase traces native Options initialization and captures the new-game sequence.
The parent last ran all three earlier phases successfully: 50 host checks and
8 native cases passed; explicit review of all five current focus images brought
that source-bound run to **9/69**. The current additions change the source binding,
so those prior passes must be rerun. All 11 UI cases now have registered drivers;
registration alone is not acceptance.

The new `cold0` phase imports a second battery produced by real Options/Save
input during the UI matrix (all difficulty flags set, title0/NORMAL). It compares
actual startup-reader and field-printer execution with the existing title1/FAST
cold reload, verifies full Options words and CRC/mirror coherence, and requires
the complete fresh 32-combination UI matrix with no custom preview calls. It
copies prerequisite trace/process/image artifacts into its own evidence directory.

The new-game gate now checks exact native word0x204, native initializer execution
before SaveData publication and again after selecting New Game, published identity,
and unsaved-state flag0. It pairs this with the same-run representative legacy
battery (native Options0x200, both coherent CRC-validated mirrors, unchanged source).
The parent visually confirmed actual new-game introductory notes on the previous
run; no long introductory playthrough or naming/save fixture is substituted for
these native initialization/default oracles. New captures remain source-bound.

The first battle checkpoint is prepared, **not yet natively exercised**. Parent
launch only, from the repository root:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope pair --native-timeout 360
```

This runs host checks and one bounded battle process, without rerunning UI. Its
fresh candidate boot uses an isolated copy of `memcheck/trainer.sav`, no `.dst`
and no RTC/movie override. Deterministic typed save-core edits of validated
source-battery slot0 supply level12/11/8 Rattata inputs, with recalculated stats,
full HP, fixed IVs/EVs/nature and EXP from the candidate's growth archive. The
debug generator is no longer used: a parent run produced a checksum-invalid
record before battle, and that failure is not attributed to the original hack
without a CN baseline. Nothing repairs or retries that failed native output.
Prepared raw templates and numeric metadata are saved and hashed as evidence;
future failures also dump raw live party bytes without decoding or repairing.
Party/progression fixtures are written only in the field;
difficulty settings use held-L Options and native Apply. A scripted native wild
Magikarp15 with Splash and pre-entry current HP1 lets the lead take a turn,
switch through the actual UI, and let the second fighter win with one native
Dragon Rage. Parent traces observed move82 dealing1 HP; this driver does not
change damage or classify that behavior as a hack/candidate bug. Immediately
after native creation, strict closed-record save-core decoding and typed HP-only
editing prepare each native party copy before any begin hook. Original/edited
raw records, hashes and constructor/setup ownership are recorded. Species,
level, EXP and boxed bytes remain unchanged. Live HP is never written; native
HP1 at input and HP0 at reward calculation must prove the KO. No attack retries.
The third slot stays benched
and holds Exp. Share. These are input fixtures, not forced awards/eligibility.

Pair mode compares Cap OFF/ON at cap12, with read-only code-identity-guarded
traces of constructor/setup ownership, begin/free, native participation, raw
and final eligibility, EVs, messages1D/1E, application/command1F and cache/backing
checksums. Same-root reuse is accepted only if actually observed with changed
settings at cap12; this does not prove a progression cap change. The oracle checks
every run before accepting: begin and free each advance generation once, uint32
wrap skips zero, adjacent lifetimes connect, and no historical generation revives.
Begin/free entry generations are recorded explicitly; older traces lacking them
cannot satisfy the revised oracle. Three-plus-run host regressions include later
immediate/older epoch revival and both begin/free wrap boundaries.
Without observed reuse and changed settings the case remains incomplete. Failed setup,
missing native observations, unexpected participation, or incomplete battle
fail the process. `failure.png`, `failure-state.json`, per-milestone JSON/PNGs,
`result.json` and `process.log` stay in `native-tests/battle/` for parent feedback.

After the pair works, `--battle-scope matrix` runs six sequential battles adding
Share OFF at both cap settings and a seven-point partial-cap pair. Reusable
`native_battle_helpers.py` handles cold boot, native Options inputs, guarded
hooks/returns, resident checks and input fixtures for subsequent items work.
`native_battle_oracles.py` contains the read-only trace comparisons. Registration
of seven battle cases is not acceptance. Aggregate/sequential no-banking,
exclusions, other constructors, progression and item cases remain incomplete;
the driver does not claim those or the deferred-message case.

The first parent trial exposed two independent problems: rejected scripted-wild
entry control8 (separately fixed in shipping candidate `bb625d52…cf4`) and battle
inputs that returned to the menu without switching or defeating the opponent.
The new `native_battle_input.py` avoids `battle_turn()`/B-mashing. It captures
the move menu, target confirmation, party list, SHIFT submenu and resulting
screen. Native action0221D7A8, actor ID, move ID, PP consumption and opponent HP
must prove each move; active ID must change1→2 after touching SHIFT128,108.
Cancelled/unsubmitted actions fail immediately. Parent must now rerun the pair.
The strict snapshot oracle requires constructor LR02050433/control0 followed
by exact flags0/control8 at capture; the separate `runtime.ordinary_0` requirement
still needs an actual random-wild control0 fixture and is explicitly incomplete.

Final combined execution uses `--native --battle-scope matrix --require-complete`
(with an appropriate bounded `--native-timeout`). Every phase and prior visual
attestation remains bound to all current test sources; targeted battle execution
does not make stale UI evidence current. The single shared binding helper now
also hashes the native script command schema used to construct battle inputs.
Candy and Day Care remain intentionally unchanged under D-2304/D-2307.

The last preview failure was a test probe error: field overlay1 reuses
`021E53EC`, overlay50's row-preview address. Four hits occurred 61–66 frames
after Options exit, with r0=6 rather than a state pointer. The probe now compares
actual loaded instruction bytes against the installed overlay50, retaining
address-reuse diagnostics separately. Genuine custom preview calls still fail.

After the assistant or human reviewer has inspected all six fresh `focus-0.png` … `focus-5.png` captures
(four rows including TRAINER AI, then CANCEL and APPLY; `support.FOCUS_COUNT`),
record that specific review without launching native code. Identify the actual
reviewer with `--reviewer`; the parent assistant performed the latest review:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --record-focus-review "Reviewed all six: readable glyphs/help, no overlap or stationary outline, correct row dash and both footer focus colors."
```

This records candidate/source binding, invocation nonce and all six image hashes.
The gate may accept this visual slice despite a later independent assertion
failure, but never promotes any other case from that failed run. Running,
interrupted, stale-source or changed-image evidence is rejected. New native
invocations require a new review. The parent-reviewed cf22 captures are retained
as a historical attestation; subsequent driver changes make them stale.

## Current bounded stage: no-effect, Oran/Leppa and revival counts

Shipping remains the separate revival fix on candidate73b188...; tests do not
change gameplay. Parent's14 PP/revival boots passed before these source edits.
Fresh source binding is required for every final combined phase.

After receipt rebuild, run these independently:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope oran-leppa --native-timeout 180
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope no-effect --native-timeout 180
```

Oran/Leppa: four boots, both settings, roughly1–2 minutes plus host checks.
Require Oran155 HP1→11 and Leppa154 selected move slot1 PP7→17 (slot0 stays4),
exactly one native consumption3→2 and enemy Splash turn, both PP views and full
Bag identity/delta. Existing Pecha/Blue evidence is not rerun by this scope.

No-effect: eight boots, roughly2–3 minutes plus host checks. Full-HP Potion17,
healthy Antidote18, full-PP Ether38 ([10,40,0,0], chosen slot1), and living
injured bench Revive28 (recipient2 HP1, displayed slot1). ALL uses actual UI:
require outcome[0,0,0], failure message event3F for actor1, callback return0,
zero consumption, quantity3/full Bag unchanged, unchanged player HP/status/PP,
and exactly one enemy Splash turn. Living Revive must not invoke ordinary HP
healing or any revival HP add. Restricted hides each addition and cancels with
no action, quantity, command or turn change. Assertions are native expectations
awaiting feedback; no eligibility, gate result or outcome is host-written.

Conditions are explicit in driver/fixture evidence and have separate
`item-NNN-category-C-no-effect` index keys and owned directories. No-effect
cannot overwrite or satisfy positive addition slices. `items.no_effect` requires
all four item pairs under the exact current binding and supervised nonces;
partial HP/status/PP evidence cannot silently omit revival coverage.

All successful revival positives28/29/37 now require native attr23 retained1,
attr38 suppressed0 for the exact actor1/target2 addresses, zero ordinary-heal
callback02221B84, zero signed adjustment0222A0A0, and exactly one dispatch,
revival HP call and HP add (LR0222AE0F). Add amount and resulting HP must be
15/31/31 at fixture max31. Duplicate callbacks/adds fail even if maxHP clipping
leaves the final value unchanged. These strengthened positives need a fresh
positive revival rerun; no-effect living Revive proves the zero-add branch only.

Generic case aggregation is order-independent: obsolete binding never replaces
a current pass; obsolete evidence alone remains incomplete. Current invalid
reports claiming the same case still veto a pass, including nonce/process,
driver, artifact and old-state failures. Other cases are independent. Addition
pairs and latest-index invalidation remain strict. Regressions cover both
report orders, current failures, clipped duplicates, wrong attr/target, wrong
no-effect consumption/outcome/turn and real typed condition fixtures.

Later stale-input tests may inject a selected-item INPUT immediately before a
native gate as explicitly authorized fault injection. They must label that
scope and leave returns/eligibility/commands/outcomes native. No such tests or
volatile status setup are implemented in this checkpoint.

## Evidence layers

### Original CN / candidate field Revive baseline — first native feedback pending

D-2322 is conditional and remains unresolved. Wild controls found Revive hidden;
field use is measured separately and cannot establish battle equivalence.
After receipt rebuild, the parent runs:

```sh
.venv/bin/python work/research/difficulty-armips/tests/native_items_field.py --native-timeout 180
```

Two sequential fresh boots, CN first then candidate, approximately1–2 minutes;
timeout180 seconds per child. This standalone diagnostic does not run host
checks or grant manifest passes. Its index is build-output
`tests/native-tests/items-field/latest.json`; each run retains separate results,
process logs, UI PNGs, raw closed records, fixture and source/ROM hashes.

Inputs are the existing valid typed level12 party: healthy lead, fainted bench
slot1 (HP0/max31), healthy slot2, with Revive3 in the medicine pocket. Party
writes end before Bag UI. The driver touches field Bag, medicine tab, item0,
Use, then displayed field slot1. Original static wrapper0209002C resolves its
selected index through0207339C and invokes0208FA50; the trace requires actual
native selection of slot1 and its exact backing record. Field selection does
not reuse battle's sorted slot2. If native Use/selection is not observed, it
fails with screenshots rather than injecting an item command or availability.

Read-only code-bound hooks capture selection0209002C, application0208FA50,
HP helper020901C4, HP/maxHP getter0206D848(attrA3/A4), HP setter0206DF70(attrA3),
and removal02076AA4. The initial
and settled records must decode strictly sealed and valid. Only the selected
record's decoded HP may change; all other decoded fields remain equal. The
PID-encrypted party tail is never read as a numeric HP value: native call
observations use getter returns, helper arguments and setter input values. With
stable PID, only the selected HP ciphertext pair may differ; other encrypted
bytes remain exact. A host regression uses real encrypted typed records and
rejects open/checksum-invalid records before any native execution. Full Bag
comparison allows only Revive quantity3→2 and requires a matching native
removal. Multiple healing/setter calls are retained as observations, not hidden.
The field report states actual HP and call counts, and explicitly keeps
`battle_equivalence_proven=false`. Ordinary revival HP15 remains unchanged.

The UI route uses existing field coordinates, previously exercised for other
items; this specific Revive path still needs parent native feedback. Native
slot/caller/effect evidence is required, not a screenshot-only success.

### Independent PP and eligible-item checkpoints — parent feedback pending

Revival remains incomplete at the unchanged HP15 oracle while the user/parent
considers the newly enabled trainer-ALL double-application path. Native control
pair7ae998382378477cadf60508a189ab88 observed Revive hidden with original mask0
in both candidate ALL wild and CN wild; it explicitly did not prove native
effect equivalence. No correction or HP30 acceptance is implemented.

After rebuilding the receipt, run the independent four-item PP scope:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope pp-only --native-timeout 180
```

Eight serial cold boots, approximately2–3 minutes plus host checks. Exactly
Ether38, Max Ether39, Elixir40 and Max Elixir41; no revival case is selected.
ALL requires native PP effects, quantity/turn and both PP views; restricted
must hide these additions and return without action or inventory change.

First eligible-item checkpoint:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope berry-flute-checkpoint --native-timeout 180
```

Four boots (Pecha151 and Blue Flute65, each in BOTH settings), about1–2 minutes
plus host checks. Both settings must expose and execute each native item:
poison/sleep clears through the native status handler, quantity3→2, exactly
one enemy Splash turn, and outcome[0,1,0]. A hidden-list cancel cannot pass.
Blue Flute consumption follows the inspected native path and remains subject
to actual feedback; standard-game reusable behavior is not assumed.

The follow-up `--items-scope berry-flute` prepares eight boots for Pecha151,
Oran155, Leppa154 and Blue Flute65. Oran requires HP1→11; Leppa selects nonzero
move slot1 and requires PP7→17 while slot0 stays4, in both PP views. All require
owner/actor/target identity and exact full-Bag quantity delta. These are prepared
paths, not new native passes. The first four boots should run before this group.

Native physical pocket attr5 at02076480 extracts bits7..10 of item halfword+8:
berries use pocket4 (Bag+688h), Blue Flute pocket6 (Bag+7E8h); medicine is pocket1
(Bag+5E8h). This differs from attr12's low5-bit field. Fixture preparation
validates the actual metadata and stocks only that physical pocket. These four
native items have dispatch byte0/discriminator1, unlike additions'2/1. Their
original attr13 masks are retained. All20 additions remain a separate table
scope; eligible positives do not count as additional medicine coverage or full
restricted-mode coverage (held/field exclusions and other items remain pending).

The current bounded stage above now implements separate no-effect fixtures,
including injured living Revive. Earlier positive native evidence is historical
after the new source edits; see the current-stage requirements.

### Ether/Revive four-boot checkpoint — reordered-target rerun pending

After receipt rebuild, run this bounded checkpoint first:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope pp-revive-checkpoint --native-timeout 180
```

Four serial cold boots: Ether38 ALL/restricted, then Revive28 ALL/restricted.
Expected duration about1–2 minutes plus host checks. Ether's lead has Dragon
Rage/Splash with PP4/7 (native maxima10/40), and touch selects move slot1 at192,72.
Require PP4/17 in both active and original views, quantity3→2 and one enemy
Splash turn. Revive's lead stays healthy; bench party slot1/recipient2 starts
fainted. The native roster moves fainted entries behind healthy entries, so this
fixture uses displayed UI slot2 (second row left), distinct from fixture slot1
and recipient2. Require0→floor(maxHP/2), quantity3→2 and one enemy Splash turn, with
actor1 and all other players unchanged. Restricted must hide the item and cancel
without changing either PP view, HP, status, full Bag or pending command.

Before touching a party slot, the trace records the native roster at controller+1Ch
and the temporary UI party. It checks all three recipient identities and HP,
and hashes each full236-byte source/copy record. Native02215204 uses02218FC8
to move fainted entries to the end; parent02202B70..94 copies this roster into
the UI party. At commitment, a read-only hook observes022151A0 called from
02202C06 and verifies that the displayed index resolves to the same BattleMon
and backing record. The encoded command must still target recipient2 with
actor1. Host regressions reject the old UI slot1 selection, wrong resolver
identity/index, mismatched copies and missing mapping evidence.

Parent run fac532370466475b893ed624f3c33c2d passed both Ether slices and the
restricted Revive slice. Revive ALL selected healthy recipient3 and produced
outcome[0,0,0] without consumption: this was a menu mapping failure, not an
accepted revival or no-effect case. These results are historical after the
mapping fix; all four slices require fresh source-bound evidence.

Native command bits20..27 hold the move slot; word+4 holds target recipient and
word+8 holds actor ID. These are distinct from party slot indices. Trace includes
party args+30, ov9 move-choice selection, specific PP/revive callback target and
return, and the separate outcome structure returned by022217C8 (sixth argument
at entry SP+4). Successful ordinary use must return outcome words[0,1,0] and
actually consume inventory. The outcome pointer must belong to the caller stack
frame; it is not the fifth-argument allocated result object.

Corrected literal-address proof: active move records start mon+252h, original
records start+25Ah, both stride18. PP/max offsets are254h/255h and25Ch/25Dh;
link flag is262h. Constructor02217014 copies both views and sets link1. The
shared battle helper still observes the original view; ITEMS explicitly records
both. Earlier ignored research notes describing252h as25Ah were incorrect.

The table also prepares Max Ether39, Elixir40, Max Elixir41, Max Revive29 and
Revival Herb37. After the first checkpoint's feedback, `--items-scope pp-revive`
runs all seven additions (14 boots); `--items-scope all-additions` includes
Potion and all20 additions, with both Full Restore lists (44 boots). Table entries
and host tests do not count as native passes. Parent's previous30 HP/status boots
passed before these source edits and are deliberately stale now. Native volatile
berry/flute positives and no-effect controls remain separate pending stages.

### Revive deferred HP diagnostic — acceptance intentionally still failing

Parent run30bcff4d347045feb2610e105aeaeba4 correctly selected UI2/recipient2.
The callback returned HP15 from HP0, but returned-menu HP was30 (max31), with
one consumption and one enemy turn. This is unresolved; the final-HP oracle
still expects15. Neither an original-hack bug nor expected doubling is asserted.
After receipt rebuild, the bounded diagnostic is:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-item 28 --native-timeout 180
```

Two serial cold boots (roughly one minute plus host checks), with retained ALL
and restricted results. An ALL failure at the existing final-HP assertion is
expected if the behavior repeats. Read `battle.events` in its result.json:
`revive_hp_write` watches only the target's two-byte live HP field, recording
raw registers, PC-adjacent code and stack without writing memory. The observed
HP is callback-time memory, not an assumed before/after value for a store.
Code-guarded entry/return traces `revival_dispatch` (02223610),
`revival_hp_call` (0222ADFC) and `revival_hp_add` (02217834) independently record
HP and amounts. The watch spans pre-Bag through returned-menu, is removed on
failure too, and propagates callback errors through the harness error bridge.
No diagnostic event grants native acceptance or changes expected effects.

The four effect/dispatch/add windows match untouched CN statically; comparison
hashes, disassembly and a conditional native control plan are retained under
`work/build/difficulty-v2/items-next-research/revive-hp-*`. A new writer trace
must precede any behavior claim or revised expectation.

### Candidate/CN wild reachability controls — parent execution pending

The diagnostic run79a7c9c917f445ac82d36a3bfa2be1fe observed two native HP-add
calls:0→15 via0222ADFC, then15→30 via0222A0A0 (return address0222A0C7).
The memory write callback emitted no events; execution-hook entry/return pairs
supply the observed HP-change evidence. Added `revival_adjust` and
`revival_event31` events expose the second caller and event arguments. The
signed-HP routine, five direct caller windows and event-dispatch window match
CN statically. Full native behavior/reachability equivalence is still unknown.

After receipt rebuild, the parent runs this separate, bounded diagnostic:

```sh
.venv/bin/python work/research/difficulty-armips/tests/native_items_control.py --native-timeout 180
```

Two sequential subprocesses cold boot candidate ALL wild and untouched CN wild.
Allow about1–2 minutes, capped at180 seconds each. The runner does not run host
checks; run the ordinary host suite first. Each uses candidate-derived typed
valid fixtures with matched source battery, sealed party records and numeric
metadata verified equal on CN. Native WildBattle constructor0/control0 must
become capture0/control8; enemy input replacement precedes battle capture.
No old state, eligibility, command, result or effect write is permitted.

Original CN uses independently guarded original code, no DG labels or synthetic
DG lifecycle. The driver records native attr13 for item28 and all five actual
Bag lists. If native lists hide Revive, it performs native Back and requires
unchanged party/full Bag/command, with no action/effect/consume. It reports
`native_ui_unreachable`; it never forces an item into the list. If visible, it
uses the observed party mapping to select recipient2, then records native
callback/HP callers/quantity/outcome/turn through the returned menu.

Fresh per-invocation directories are under `tests/native-tests/items-controls/`
in the build output; `latest.json` identifies the paired report. Exact source,
ROM, input and artifact hashes are retained with distinct supervised nonces.
This diagnostic has empty `cases`, is never read by the ordinary manifest gate,
and cannot mark Revive or CN equivalence passed. A successful diagnostic exit
means the observations completed, including a conclusive hidden-item outcome.
The ordinary final-HP oracle remains15 pending reviewed independent evidence.
If CN hides Revive, inherited code alone cannot establish original reachable
behavior: the newly exposed ALL path must be evaluated separately, with any
shipping solution assigned to a separate agent after trace review.

### Trainer ITEMS HP/status matrix — prior source passed, rerun required

After rebuilding the receipt, the parent runs:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope hp-status --native-timeout 180
```

This runs host checks followed by 30 serial, independently supervised cold boots:
Potion17 and additions18–25,27,34,35,42,54, each ALL/restricted, with Full
Restore23 selected separately from categories0 and1 (four processes). The last
Antidote runs took about19 seconds each; budget roughly10–15 minutes for the
matrix on the same machine. The timeout is per process, not a total deadline.
For a smaller new-path checkpoint use `--items-item 23` instead of
`--items-scope hp-status` (four processes, about1–2 minutes).

Artifacts are retained under
`work/build/difficulty-v2/tests/native-tests/items/runs/<invocation>/item-NNN-category-C/<mode>/`.
`items/latest.json` indexes the current pair for each item/list location. A rerun
allocates new directories and invalidates every selected variant before spawning;
unselected variants remain indexed but exact global source binding is mandatory.
The old two flat output directories are historical and no longer consulted.
Single-item runs can accumulate coverage only while sources/receipt remain equal.

All modes use actual trainer5, native Options Apply, and valid typed fixtures
from `memcheck/trainer.sav` with candidate-derived metadata. Enemy inputs are
healthy and Splash-only and written before begin. No debug generator or old
state is used. HP medicines start at1 HP; status medicines start at full HP with
the matching major status. Full Restore starts at1 HP and poisoned. Controls
and enemy are healthy. The level12 fixture clamps large heals at max HP; this
proves native healing to the cap, not a separate unclamped200-HP measurement.
Full Heal/Cookie/Gateau currently exercise poison, not every possible status.

ALL must show the exact native lists/mask, pass Use and both gates, target slot0,
encode the owned command, execute the expected HP/status change, consume one of
three items and exactly one enemy Splash turn. Full Restore must appear in both
lists even when selecting one. Restricted must hide the item and blue-Back cancel
at236,170 without changing all864h Bag bytes, HP, status, PP or command/slot state.
Native success and cancel can both return13; only item0/category4 proves cancel.
Each process ends at the command menu; it does not claim a battle victory/free.

Read-only status observations now use the common native handler02221CE8 with
its status ID in r3, and capture each return. Full Heal/Restore can legitimately
visit several status handlers returning0; exactly one must cure the fixture's
status and return1. Unexpected target/status/HP mutations fail. The inventory
reader validates the setup+108 Bag pointer and every physical pocket entry.
Setup+F8 is TrainerInfo, never a Pokémon-party pointer.

Each implemented addition requires every ALL/restricted/list slice from the same
matrix invocation, different supervised process nonces and identical input hashes.
A single pass or one Full Restore list cannot certify the addition. Adding a case
table row alone does not grant evidence. `runtime.ordinary_1` still requires real
flags1/control0, epoch, owner and copied-Options observations.

Parent previously passed Potion and Antidote pairs on candidate47f802…71e9a.
Those results become historical when test sources change. Parent also passed all30 HP/status boots on the prior test sources.
PP/revival paths now await the four-boot checkpoint above; berry/flute positives, native
no-effect controls, remembered/stale gates, doubles, exclusions and pagination
remain incomplete. No broad restricted or no-effect claim is emitted. Final
UI/growth/ITEMS reruns must share the final source binding.

See [fixture seams and historical checkpoints](../research/items-native-checkpoint.md).

| Layer | Actual subject and coverage | Limit |
| --- | --- | --- |
| Host policy FFI | Compiles shipping `policy.c`; unsigned edges/randoms, eligibility, independent award vectors, all item IDs/context differentials | Arithmetic/policy isolation, not battle distribution |
| Host ASan/UBSan | Shipping Options/settings, runtime/caps, items, growth wrappers; native memory/primitive callbacks mocked | Not ARM or native UI execution; leak checking disabled for intentionally process-lifetime fixture buffers |
| Options/settings | 524,288 codec combinations; protected halfword/no-op store; transactions/ownership; actual input/render C; original title/TEXT SPEED compatibility | Native save mirrors, renderer and previews still need runtime evidence |
| Runtime/caps | 262,144 badge/flag states and native-reader mock cases, 4,718,592 nondecreasing completion edges, flag/badge equivalence and skipped gaps, exact flags/control classifier (including loss-allowed 0x801 and rejection of every other 0x800 value), 72 option/context lifecycle combinations, original begin/free, root reuse, frozen state, identity/bounds failures | Mocks do not prove the game's entry/control/owner contracts |
| Growth wrapper | Original first, nonboolean result, deferred/raw/snapshot/cache unchanged; partial/zero/old-overlevel/uint32 awards; all 256 recipient IDs; invalid context/owner/bounds bypass | Native messages 1D/1E, application 1F, EV and backing Pokémon still untested |
| Items | 524,288 list combinations; every valid item/flag through all C gates, all20 expansions against native archive facts; native delegation, sentinels, cancellation-only memory writes, synthetic other command unchanged | Not real effects, inventory/turn handling or doubles slot mapping |
| ROM data | Fresh NARC party/script records vs schedule and current site; gym/story maxima, delayed predicates, relevant script instructions, constructor hash; 791 item records and 20 additions | Does not prove all paths/legacy saves at runtime; whole-site documentary hashes do not block unrelated edits |
| ARM compile/assembly | Fresh shipping C compilation/link and armips, candidate payload equality, all hooks/edit/placement guards and negative inputs, actual ARM layouts, one aligned halfword commit store | Static compilation/emission is not ARM C execution |
| ABI instruction models | Actual assembled bytes: 1,536 item adapter cases, 40 runtime adapter cases, title/TEXT SPEED shifts/masks over all65,536 words; nine Options tail thunks | Deliberately bounded instruction interpreters, not CPU emulators |
| Installer | Real isolated install/reopen/byte census, 52 rejection cases; bounds/overlap/source pins; undeclared ROM/ARM7/item/resident edits; simulated late verification/source-change failures preserve prior candidate+receipt | Does not simulate disk failure during two-file promotion or prove hardware memory ownership |
| Test sensitivity | Disposable source mutations (disabled clamp, lost TEXT SPEED bit, wrong Full Restore mask, replay acceptance, restored cap decreases) are rejected by C drivers | Mutants never enter installer/gameplay; no shipping code changed |
| Runner | Nonzero/signal/timeout/spawn/interruption, stale nonce/binding/artifact/old-state/host-evidence rejection; real installed register accessor with primitive stub | Framework tests are never native acceptance |

D-2312 keeps raw gym maxima in `gym_schedule.json` distinct from effective
caps. The native `progression.skipped_decreases` case keeps its stable ID but
now requires evidence that both former drops are removed, new recipients can
grow beyond80/88, and skipped-gym ordering and old EXP remain correct. Clair
still needs real completion-flag/badge evidence: cap100 on both sides cannot
prove her completion. These remain required native cases, not host substitutes.

The original four foundation assembly tests and three source-ROM guards remain.
They test the historical foundation in isolation, not the integrated loader.

## Reports and freshness

`report.json` is atomically replaced with a non-success `running` record before
tests begin. It records each passing test, failures/skips, source identities,
evidence layers, required native case status and `complete`. Host driver receipts
and mutation receipts are similarly invalidated before work. Native process
reports carry unique invocation nonces. Native case evidence must match the
current input/candidate, receipt, all recorded implementation inputs, current
test sources, harness and copied source battery, with hashed trace/screenshot
artifacts. Candidate build artifacts are rehashed before native startup. Bindings
are rechecked after replay. Finder `.DS_Store` and bytecode are not source inputs.

Child failure, signal or timeout finalizes a failed/interrupted report and kills
an outstanding child process group. SIGKILL of the supervisor itself cannot be
caught; a leftover `running` report is never acceptable and is marked interrupted
on the next invocation. A failed or stale native report cannot leave a previous
successful case accepted. Native screenshots still require the separate visible
UI review case; callback/Options-word assertions alone do not certify rendering.

## Provenance and remaining serial handoff

`drivers/options_check.c`, `drivers/runtime_check.c`, `drivers/items_check.c`
were promoted from the implementation agents' ignored scratch drivers in
`integration-impl/` and `items/impl/`. Runtime edges were extended; item masks
are regenerated from the source ROM on every run. `items_abi_model.py` and
`compat_abi_model.py` were promoted from the scratch assembly checks and now use
freshly linked/assembled artifacts. No historical executable/report is accepted
as a fresh pass. Growth driver, runtime ABI model, ROM-data checks, installer
negatives, evidence framework and UI driver are durable suite additions.

Native UI execution exposed the stationary red cursor bug, now fixed in source
(see research/options-cursor-fix.md). Current-source native acceptance, including
direct Options touch reentry, remains pending; the driver deliberately
fails if the callback does not execute or if the native page mode differs from
the request. If blocked, preserve the bounded report and fix the driver/feature
serially. Do not extend a timeout indefinitely or replace an outcome on the host.

The next agent should first run the approved native command, inspect screenshots
and traces, then add save/reload/reset and native battle drivers. The 69-case
manifest contains concrete EXP-message/EV/no-redistribution, root-generation,
progression and item-effect oracles, including all20 medicine additions and both
local doubles slots. Any shipping fix belongs to a separate fix agent and needs
a new candidate/receipt; old native evidence becomes stale by construction.

Status source proof for the ITEMS matrix: candidate ov14 `02216228..022162B4`
imports party attribute160. Bits1–7 represent sleep (native status2); bit8 maps
to poison5, bit16 to burn4, bit32 to freeze3 and bit64 to paralysis1. The importer
stores eight-byte status records at `mon+38+8*status_id`. Native `02216D28` tests
the low three bits of each second word. The item callback table at `0224D19C`
selects wrappers `02221D4C/58/64/70/7C`, which pass IDs2/5/4/3/1 to
`02221CE8`. The common handler tests applicability, removes the status through
`02221D14`, and returns1. Tests read these fields and never write live effects.
Typed fixture encoding is confined to pre-entry input records.


## Singles native fault-input gate checkpoint

After rebuilding the receipt, parent runs from repo root:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope gates --native-timeout 180
```

Three sequential cold boots (about 1–2 minutes plus host/build) isolate Use,
first item-return backstop, and target-return backstop. Each restricted fixture
stocks Potion17 and Pecha151 at quantity3 in their actual native pockets. The
Use/target probes select Pecha through UI; the first-return probe uses actual
Back. One logged `nativeFaultInput` writes only Bag args selected-item/category
bytes immediately before the selected gate. This is fault injection, not proof
that stale inputs arise in ordinary play. Native cancellation must produce
item0/category4, leave full inventory/mons/command destination/slot unchanged,
and return to command selection. Target denial must actually rebuild Bag before
Back. Genuine Fight then executes exactly one Splash per player/enemy with both
PP views decremented once and no item effect/consumption. No outputs, registers,
eligibility, command records or committed outcomes are host-written.

`--items-gate-item 791` or `65535` repeats the three gates with an invalid
selected ID and requires no metadata call for that ID within the gate. These
extra slices do not substitute for valid-denied Potion or satisfy remembered
item coverage. First run the default Potion checkpoint for native UI feedback.

The driver is `native_items_gates.py`; trace and independent oracle are in
`native_items_gates_trace.py` / `native_items_gates_oracles.py`. Supervised nonce,
process log, screenshots, typed fixture provenance and trace remain separately
under `native-tests/items-gates/runs/<invocation>/gate-<gate>-item-<id>/`.
`items-gates/latest.json` replaces only the selected gate/input entries. Native
acceptance replays the oracle after ordinary binding/artifact checks and allows
only that gate's manifest case. No stale binding is refreshed. Doubles, actual
remembered-item persistence and malformed remembered IDs remain unimplemented;
the new selected-ID probes do not claim those cases. Successful revival callback
counts still require fresh positive28/29/37 evidence on the final source binding.

Gate actor identity uses both native views explicitly. `02215170(1)` returns
root+54h (controller/UI view), while argument0 returns root+144h (engine view).
`02230920` resolves owner/slot through the UI roster; each view has its own
ID table at+8Ch (`022150DA..FC` installs the same mon pointer into that view's
ID table and roster). Thus controller+584h and engine root+1D0h+4*ID need not
be equal. The gate trace requires the actual controller lookup return, UI
roster and UI ID table to agree, then binds the engine ID table through the
same ID, identical sealed backing-record hashes and matching mon state. Party
selection uses the UI actor pointer and requires exact backing/copy identity.
Command before/after/return/denied equality remains strict. The first native
three-job run stopped on the former cross-view pointer assertion; it proved
neither a command mutation nor successful Fight continuation. Fresh rerun is
required after this test correction.


## Malformed remembered-input checkpoint

After receipt rebuild, parent can run two sequential cold boots:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope remembered-invalid --native-timeout 180
```

This is the next bounded diagnostic (roughly one minute native plus host/build),
not complete `items.remembered` acceptance. `native_items_remembered.py` reuses
the supervised gate driver, typed Potion/Pecha fixture and native Fight
continuation. It injects791 or65535 solely into actual UI args+1Ch at verified
ov9 021EC250, before the native load021EC256. It requires the wrapper to receive
the exact ID/UI/Bag, zero native inventory-count and metadata calls throughout
the validator, return0, and native clearing of remembered ID+1Ch and category
+1Bh. Selected-item outputs and registers are never written. Full native Bag,
mons and command/slot state must remain unchanged through opening/Back, followed
by exactly one real Splash from each actor. Retained case directories use
`gate-remembered-item-00791` / `gate-remembered-item-65535`; existing gate results
are separate index entries. No broad manifest pass is emitted for these partial
slices. This differs from `--items-gate-item`, which tests selected-item gates.

Authentic valid-denied remembered Potion still needs actual ALL Potion use,
Dragon Rage KO, field Options change, second battle and native shortcut
filtering. It is deliberately separate from malformed-input injection, and is
not yet implemented. Doubles and fresh final positive revival counts remain
pending; previous runs are historical after source edits.


## ITEMS DEFAULT revision (D-2412)

DEFAULT keeps the untouched Chinese battle-item rules, so Potion (17) is visible and usable
in both DEFAULT and ALL, like the berries and the flutes (`restricted_allowed`). Exactly
twenty medicines are ALL-only additions (`ADDITIONS`). The singles/doubles gate probes
and the persistence diagnostic therefore use `GATE_ITEM` (Hyper Potion 25, an addition
with the same HP-1 fixture) as the DEFAULT-denied item instead of Potion; their job ids
end in `-item-00025`. Potion is covered by its own all/restricted pair as the
native-eligible control.

## Authentic remembered Potion persistence diagnostic

After receipt rebuild, parent runs one cold boot containing two native battles:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope remembered-persistence --native-timeout 240
```

Approximately 1–2 minutes native plus host/build. `native_items_persistence.py`
uses a first-entry typed actor with HP1, Dragon Rage/Splash and candidate-derived
PP, plus a valid pre-entry HP1 Splash enemy. It actually uses Potion in ALL
(HP1->21, quantity3->2, native remembered setter17/category0, one enemy turn),
then genuinely KOs with Dragon Rage. Native award/HP0, teardown and snapshot
invalidation are observed. The first-entry enemy callback is removed before
any second construction. Party/inventory are never reinstalled or reseeded.

At the field boundary, strict closed party hashes/decoded records and full Bag
are compared before/after actual Options Apply to restricted and before the
second ordinary TrainerBattle. Its player backing hashes must match the carried
field party. The native remembered validator must receive17, return0 and clear
remembered item/category itself; restricted lists must exclude17. Opening and
Back must preserve quantity2/full Bag, mons, command destination and slot.
There are no fault-input writes in this driver. Failure to retain the actual
remembered item is a diagnostic failure, never replaced with injected memory.

Evidence is retained under `items-gates/runs/<invocation>/gate-persistence-item-00017/`.
This is initially a case-specific diagnostic; broad `items.remembered` remains
unclaimed until both this authentic route and malformed-input slices have fresh
validated evidence under the final binding. Existing gate probes are unchanged.
Doubles remains the next stage after native feedback.

## First doubles pending-action diagnostic

After receipt rebuild, parent runs one bounded cold boot:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope doubles-checkpoint --native-timeout 240
```

`native_items_doubles.py` starts actual script `TrainerBattle(6,6,0,0)` and
requires native flags3/control0 plus a bound restricted entry snapshot. Before
entry it validates trainer6 metadata and every existing native enemy record in
the populated trainer parties, retains raw originals, and replaces only valid
party inputs with full-HP Splash records. It records all setup party pointers
before assertions; no battle flags, eligibility or outcome is written.

The diagnostic observes two local owner0 controller actors/slots and binds each
UI roster/ID table to its engine counterpart. A real first-slot Splash must
queue into its actual command destination and reach the second-slot menu without
executing a turn. Its finalized pending command is snapshotted there (native
target bookkeeping can finish after the initial move encoder returns). Opening
Bag and native Back in slot1 triggers one input-only Potion17 injection at the
first commit gate. Native item0/category4 cancellation must preserve the exact
first pending command, second command/destination/slot, full Bag and all mons.
Then a genuine second Splash must execute both local moves and two enemy moves
exactly once, with exact PP changes and no item effect/consumption.

This is intentionally one second-slot gate, not all gates on both slots, and
emits no broad doubles manifest pass. Constructor/mapping/UI disagreement fails
with diagnostic artifacts for parent feedback. Output is retained separately at
`items-gates/runs/<invocation>/gate-doubles-item-slot1-item-00017/`. Expect roughly
one minute native plus host/build. Existing singles/persistence probes remain
unchanged; source changes deliberately stale previous native acceptance.

The first doubles native probe confirmed flags3/control0 and local actors1/2
at slots0/1. It stopped before gate injection because the initial test wrongly
expected one move-encoder call. Native UI emits a preliminary Splash command
with selector5 (literal at02211FF8; BL02212006, LR0221200B), then a selected target position
(BL0221266E, LR02212673). Both observations are retained. The revised oracle
requires exactly this ordered, callsite-byte-bound pair for each actor, equal
move/destination/ownership, and the precise selector-bit change; it never drops
an arbitrary duplicate or treats the preliminary command as a completed move.
Native actor lookup proves arrival at slot1 despite identical actor names in the
screenshot. The subsequent run reached denial/preservation and four actual
Splash actions (IDs2,1,13,14), then exposed the oracle's incorrect move-slot
name/assumption: the second actor encodes target position2, not0. Native02200960
packs this argument in command bits4..7;02212634..3A validates/stores a target
position before02212666 loads it. The driver now names it `target_position`
and observes native022151D0 (position ->02228580 owner/slot -> view roster).
Every selected Splash requires a prior native resolver result matching that
position, the current UI view and its own actor pointer. It does not merely
allow0/2. Both encoder stages and the strict pending-action/turn checks remain.
The added resolver evidence and corrected oracle await a fresh parent rerun.


### Six doubles gate/slot cases

After the parent-passed one-case checkpoint (e148f11792714a63b83a77acaed57f64),
run the bounded matrix after rebuilding the receipt:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase items --items-scope doubles-gates --native-timeout 240
```

This launches six sequential cold boots: accept, first commit and target commit
at each local command slot0/1. Each retains an independently supervised result,
trace, screenshots and pre-entry fixture provenance under
`items-gates/runs/<invocation>/gate-doubles-<gate>-slot<slot>-item-00017/`.
The one-case `doubles-checkpoint` scope remains available. Budget roughly
3–6 minutes for six boots (240-second limit per case).

All cases inject only selected-item/category INPUT at the chosen native gate.
Accept and target cases first select the actual allowed Pecha Berry; first
commit uses native Bag Back. Target cases map the acting mon to its copied
party UI entry, then require return6, a fresh filtered Bag list, and native Back
to the same command menu. The other gates require their own native13/0 return
and cleared item/category0/4. No item, HP/status, quantity, turn or command-slot
change may occur during denial. Both local Splash commands must subsequently
resolve their native target positions to their own actors, and exactly four
Splash actions must decrement both PP views once with the full Bag unchanged.

For slot1, first-slot Splash is already queued and its command bytes must remain
unchanged through denial and reopening. For slot0, the other action is explicitly
`not_yet_selected`; no queued action is invented, and the prefix must contain
neither a move encoding nor second-slot selection. These cases make no native
backtracking claim. Broad doubles manifest rows remain uncredited: this matrix
retains precise per-case diagnostics and must not substitute for their currently
broader wording. Fresh six-case native results are pending after this source edit.

### Result-changing progression checkpoint (2026-10-10)

See [the functional coverage map](PROGRESSION_COVERAGE.md) for explicit native
fixtures, remaining gaps, and Astra's D-2312 reclassification of nonfunctional
Clair/Morty selected-row obligations as optional research. No victory-script
proof is claimed from controlled badge/flag inputs. Run the six isolated boots:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope progression --native-timeout 240
```

Each result retains the existing strict native growth/action/lifetime oracles
plus actual cap reader return traces and input ownership. All test sources and
fixture inputs remain freshness-bound; earlier UI/items/battle reports become
historical when these sources change. This checkpoint does not certify the full
progression or no-banking gates. The coverage map supersedes older selected-row
requirements in this README; it does not relax missing functional requirements.


### Carried-party cap-rise checkpoint

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope caprise --native-timeout 360
```

One cold boot and two real wild KOs. Cap12 rejects the lead's positive native
request; badge0 is the only between-battle input change. Cap20 must award only
new native requests, with exact party/Bag continuity and native PP/EV backing.
This registers narrow `growth.caprise_no_banking` and `runtime.next_cap` cases;
aggregate multi-opponent `growth.no_banking`, victory scripts, and skipped-Koga
gap closure remain incomplete. See [the coverage map](PROGRESSION_COVERAGE.md).


### Native trainer multiple-KO matrix

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope multiko --native-timeout 600
```

Trainer6 singles, four battles with Share ON/OFF × Cap OFF/ON and identical
pre-entry inputs; real participation
changes and two KOs without a within-battle reset. Native per-opponent records
are bound to actual reward-pass groups, including delayed aggregation semantics.
See [the coverage map](PROGRESSION_COVERAGE.md) for strict oracles and remaining
simultaneous-KO/gap-closure obligations. Parent alone executes the native driver.

The multi-KO matrix binds per-opponent EVs to the completed native temporary
records (the earlier EXP-calculator return has not filled EV bytes yet). Share
OFF must prevent benched EXP/EV applications for each opponent while preserving participant
records against Share ON. Native direct messages and deferred applications are
checked separately. `growth.deferred` covers positive and zero deferred awards;
partial deferred crossing remains unproven. `growth.no_banking` remains incomplete
until current cap-rise and multi-KO evidence are combined by a dedicated gate.

Multi-KO EV provenance: raw yield bytes remain native, including bench yield1.
Observe original eligibility at caller0221F682, return and apply/skip branch;
bind accepted calls at0222AC50/LR0221F6AB to recipient/raw/group/opponent.
Battle-mon EV storage (+248 total, +24A six values) must change only for
eligible recipients, including capped participants. Party backing EV flush
is checked after battle, not assumed at each award group.

### Bounded growth edges

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope edges --native-timeout 600
```

Six battles maximum across three fresh boots: same-party Koga gap55→100;
over-cap lead20 plus level100 fighter Caps OFF/ON; and species1's distinct
candidate growth curve with a seven-EXP partial cap. Stops on the first failed
job. Native original eligibility and EV controls remain mandatory; no assertion
that level100 raw reward is zero. See PROGRESSION_COVERAGE.md for pending broad
gates and the exact input-versus-story distinction. Parent alone runs native.

Target the remaining edge jobs without overwriting the gap report:

```sh
.venv/bin/python work/research/difficulty-armips/tests/run.py --native --native-phase battle --battle-scope edges --edge-cases overlevel curve --native-timeout 600
```

The level100 fighter is a typed, already-evolved Raticate input using candidate
personal/growth/stat tables. This avoids a second unrelated post-battle evolution
and move-learning sequence; native gameplay timeouts and reward checks are unchanged.
The level20 lead remains Rattata and may evolve naturally. Preserved reports still
need matching final source hashes to count as current native evidence.

## Exp. Share holder with SHARE OFF (D-2403)

`native_battle.py --scope holder --kind wild|trainer|double --expect fixed|baseline` runs five battles per kind
(SHARE ON holder control; SHARE OFF holder and plain bench; SHARE OFF + CAP ON holder and plain bench) with one
level-11 bench slot 3 EXP below the cap-12 threshold that holds an Exp. Share (216) or nothing, and decides with
`holder_verdict`: the holder must get the SHARE ON EXP and EVs (clamped to 3 EXP under CAP), the plain bench nothing.
`--expect baseline` encodes the rc7 behaviour (SHARE OFF shares with nobody) and is meant for a build without the fix.
The oracle itself is unit tested in `test_native_battle.py` (`ExpShareHolderOracleTests`); `drivers/growth_check.c`
covers `dg_growth_share_enabled(battle_mon)` on the host.
