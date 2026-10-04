# v4.0.3 ROM verification: capture chains, tools, charms and visible encounters

2026-10-04. Findings only; no guides, generated docs, translations, production tools or ROMs changed. This is fresh **static binary verification**, not a new emulator playthrough. Addresses below are RAM addresses in the specified ARM9/overlay, not whole-ROM file offsets.

Inputs: `work/rom/origin_v4.0.3_cn.nds` and `work/build/origin_hg_v4.0.3_en_wip.nds`. Decoded the ARM9 and all 120 overlays directly using ndspy; inspected the relevant Thumb instruction paths with Capstone. Full disassembly, scratch scripts and per-range SHA-256 comparisons are ignored under `work/build/source-verify-mechanics/`. All **16 examined ranges match exactly** between those two ROMs (`parity.json`). This establishes parity for the cited handlers, not every path or every historical English patch.

## M-01 — Chain Logger has an engine-level new-save grant

**Resolves REF-01 / COM-03, high static confidence.** Overlay 37 setup routine `0x021E4C48–0x021E4C8E` gets the bag through ARM9 `0x02076E28`, constructs item **744** with `0xBA << 2`, sets quantity 1, and calls AddBagItem (`0x02076A08`) at `0x021E4C74`. This is an engine setup grant, so searching only map `GiveItem` commands cannot establish that the logger is absent.

The bag adder itself at ARM9 `0x02076A08` locates a slot and stores item/quantity. The initialization caller does not check its return value; unusual capacity/failure conditions were not reproduced. Combined with the earlier logger screen test, this is sufficient to reject “not in the game,” without implying that every other item in that list is obtainable.

## M-02 — EV Allocator is granted by post-battle synchronization

**Resolves REF-01 / COM-03 existence; refines advertised timing.** Overlay 14 `0x0222B910` synchronizes the player's battle party. At `0x0222B950–0x0222B97C`, it obtains the player's bag, tests for item **745** with HasBagItem (`0x02076B20`), and adds one if absent using `0x02076A08`. Item 745 is the literal at `0x0222B9FC`.

This is reached from `0x0222B828 → 0x0222B834` before branching on battle outcome. It is a repeatable “ensure item exists” operation, not a map-script gift and not a starter-selection instruction. The release's “after starter” description is compatible with receiving it around the first battle, but **the exact first ordinary acquisition moment was not played through**. Do not claim it appears immediately on selecting a starter based on this trace alone. Capacity failures and exceptional battle types were not exercised.

## M-03 — Mother's rewards include three traced charms, not all four

**Resolves part of REF-01; contradicts the four-charms summary for this fixed reward path.** ARM9 table `0x02106FC0–0x02106FF5` contains nine six-byte `(item, savings threshold, purchase cost)` entries. The last three are:

| Item | Threshold checked against savings | Amount deducted |
|---|---:|---:|
| 740 Catching Charm | 30,000 | 3,000 |
| 741 Exp. Charm | 40,000 | 3,000 |
| 743 Shiny Charm | 50,000 | 3,000 |

The other six are items 294, 289, 290, 291, 292, 293. Consumer `0x0209280C–0x0209286C` loops over exactly nine entries, skips already-purchased entries, compares current savings against the threshold, marks the purchase, queues quantity 1, subtracts the cost and stops if the delivery queue fills. The companion random-reward branch `0x020928B2–0x020928DA` selects from a byte-valued table and adds 149 to the item value; that branch cannot produce item 742.

**Oval Charm 742 is absent from these mother's fixed and random purchase paths.** This does not prove global unavailability; it means the announcement is insufficient evidence to list an Oval Charm savings reward. Thresholds are tested against the supplied savings balance, not a claim about cumulative lifetime deposits or guaranteed immediate delivery. No ordinary phone/delivery sequence was replayed.

## M-04 — Actual chain thresholds resolve the overlapping source labels

**Resolves COM-03 boundary question; new original-hack UI discrepancy.** The engine uses the saved completed-capture count, read by ARM9 `0x0202959C` from save-block offset `+0x19`:

| Completed count before generating the next encounter | Dedicated shiny-roll multiplier | HA selection threshold | Distinct IVs forced to 31 |
|---|---:|---:|---:|
| 0–5 | 1 | 0% in this chain branch | 0 |
| 6–9 | 3 | 10% | 1 |
| 10–19 | 5 | 50% | 2 |
| 20–255 | 7 | 70% | 4 |

Evidence: ARM9 `0x02019EB8–0x02019EEE` (shiny multiplier), overlay 2 `0x02248A44–0x02248AC4` (HA/IV), and overlay 28 `0x02260FA8–0x02260FF8` (dynamic logger display). All three agree at **10 and 20**. The Chinese UI's static labels `a027/0814#10` (“6–10”), `#11` (“10–20”), `#12` (“21+”) therefore do not accurately describe the implemented boundaries. Preserve the translation's faithful wording; record this as an original-game finding if a future documentation/decision pass is authorized.

The IV helper ARM9 `0x0206D4DC–0x0206D550` selects distinct stat indices without replacement and writes 31; additional naturally perfect IVs remain possible. HA selection still depends on the species' actual ability data. It is not proof every species has a useful hidden ability.

### Do not publish the UI fractions as exact overall shiny odds

ARM9 `0x02019EF0–0x02019F46` adds one to the multiplier if Shiny Charm 743 is in the bag, computes integer `4096 / multiplier`, then succeeds when the RNG remainder modulo that integer is zero. Thus the dedicated check uses denominators 4096, 1365, 819 and 585 without the charm; with it, 2048, 1024, 682 and 512. Overlay 28's display also divides 4096 by the multiplier.

These are the **dedicated forced-shiny check's denominators**, not an established exact final distribution. A failed check proceeds through ordinary PID creation (`overlay 2 0x02247ED2–0x02247EEE`; ARM9 `0x0206D394`) and the real OT ID is subsequently written. Residual natural shininess, PID/nature conditioning and modulo bias mean this audit does not establish a simple exact combined probability. Avoid claiming exactly `3/4096`, `5/4096` or `7/4096` for every encounter.

## M-05 — Chain identity includes form; “any shiny resets” has an exception

**Resolves COM-03 reset rule, high static confidence with important source refinement.** The capture bookkeeping handler is overlay 14 `0x02215B90–0x02215D06`. It reads the captured Pokémon's species (`GetMonData` field 5) and form (field `0x70`). At `0x02215C4C–0x02215C6E` it compares both against the saved chain identity.

- Different species **or form**, or no previous identity: update encounter category, clear the previous chain, and initialize the new species/form with count **1** (`0x02215C70–0x02215CA6`; setter ARM9 `0x02029544–0x02029568`).
- Same species/form and shiny: clear category and identity/count (`0x02215CAC–0x02215CC4`).
- Same species/form and nonshiny: increment, capped at **255** (`0x02215CCA–0x02215CD6`).

The shiny test is only in the **same-identity** branch. A different-species/form shiny follows the earlier new-chain branch and starts at 1. Thus “catching any shiny always leaves count zero” is **not** what this code implements. This particular branch behavior was not reproduced by catching a shiny in an emulator; report it as a strong static finding, not a played scenario.

The inspected direct references to the chain clear/increment/set helpers are this capture handler. No defeat/flee update was found in those references, supporting the author's no-break-on-defeat/flee rule; absence of direct references is not exhaustive proof against every indirect write or exceptional event.

## M-06 — Chain bonuses also reach scripted wild encounters

**Corroborates COM-03 static encounter scope with bounded evidence.** A script battle handler at ARM9 `0x020434DE` calls `0x02050418`, which invokes overlay 2 `0x02248394` at `0x02050444`. That creator uses `0x02247D74` for its ordinary branch and `0x02247C64` for a forced-shiny branch. Both feed `0x022489DC`, the shared HA/IV routine. The ordinary branch calls the chain shiny check at `0x02247D9C`.

The bonus routine reads the saved count without requiring the newly generated species to equal the chained species. That supports chaining one species to improve a later scripted wild encounter. However, `0x022483F6–0x0224840C` also applies a separate three-perfect-IV operation in one scripted path. Do not reduce every static encounter's final IV behavior to the simple chain table, or extend this conclusion to gifts, Eggs and every special encounter constructor.

## M-07 — Visible spawn cap, suppression and persistence have concrete code

**Partially resolves COM-04 / REF-07.** ARM9 `0x02019858–0x02019C30` creates visible encounters. It uses six slots, checks the active count against 6 (`0x020198A2–0x020198A8`), and uses object IDs `0xF0–0xF5`. The slot finder `0x02019C34` also stops at six.

A save-block-21 counter at `+0x65` must be zero via `0x0202DD30` (`0x0201986E–0x0201987A`); this is the counter accessed through `0x0202DD28` by the item-use path in overlay 2. This supports Repel suppressing new visible spawns. It does not establish that already-visible Pokémon immediately disappear when using a Repel.

**Ordinary encounter reduction has exceptions.** Overlay 2 `0x02247934–0x02247952` checks that visible encounters exist, excludes terrain values `0x16` and `0x1D` via ARM9 `0x0205AA34`, divides the rate parameter by three using integer division, and halves a secondary parameter. Therefore “all random encounters are exactly one-third as frequent whenever any visible Pokémon exists” is too broad. The exact player-facing labels for those two terrain codes and the full compound probability were not resolved here.

**One retained shiny record:** the spawning code stores species, form, map and level in a single volatile RAM record at **`0x021CFF50`** (species `+0x0C`, form `+0x0E`, respawn marker `+0x10`, map `+0x14`, level `+0x16`) (`0x02019AF6–0x02019B0A`). Map cleanup `0x02019FE8–0x0201A03E` removes the six active objects while retaining a map-matching respawn marker. Spawn selection `0x020199B0–0x020199F0` uses the retained record if the map matches and no existing shiny slot is active. A later generated shiny writes the same single record; there is no six-shiny save queue in this path. Interacting with the matching special slot clears that retained record at `0x0201A1C4–0x0201A1EC`.

This strongly supports one-slot re-entry retention. The follow-up below establishes the boot-clearing loop, nearby candidate coordinates and shiny-specific sound call. **Guaranteed accessibility, in-game save/load and a directly instrumented soft-reset sequence remain unverified.** The record is separate from the chain's save-block state; a fresh boot cannot retain volatile RAM without some explicit restoration. No such save-serialization/restoration path was established in this audit, and emulator save states are a separate case from in-game saves. Treat the release's restart-loss warning as sensible source advice pending explicit save/load tests; do not present full persistence guarantees from this static trace.

## M-08 — EV Allocator input mappings are now statically resolved

**Resolves the direction/sign ambiguity in COM-03 and the older shortcut note, high static confidence.** Overlay 105 reads newly pressed normal-mode DS key bits at `0x021E4B1A–0x021E4BB8`:

| Input | Handler action |
|---|---|
| SELECT | Opens clear-EVs confirmation |
| START | Opens restore-entry-EVs confirmation |
| X / Y | Previous / next party member, wrapping |
| Left / Right | Decrease / increase selected EV by 4 |
| L / R | Decrease / increase selected EV by 64 |

The party index step is passed to `0x021E5854`, wrapping modulo party size. Adjustment goes to `0x021E58B0`; limits are enforced there rather than blindly adding/subtracting. Exit calls `0x021E57D4`, comparing each member's current total EVs with the total saved on entering the screen. If any total differs, exit is blocked and the allocate-all message is shown. This is **redistribution of existing EVs**, not free generation of new EV points.

No physical-key/touchscreen allocator scenario was replayed in this pass; alternate button modes and all confirmation/cancel cases remain runtime checks. Existing summary L/B results remain independently attributed to `work/notes/in_game_shortcuts.md`.

## Outstanding checks

- Date-specific mythical calendar: a separate section reviewer owns this trace; no calendar is inferred here.
- Controlled catches at counts 5/6, 9/10 and 19/20; same/different form shiny branch; defeat/flee cases.
- First ordinary acquisition screen for each engine-granted tool and delivery of each mother's charm.
- Emulator reproduction of visible shiny map exit/re-entry, save/load, reset, sound and accessibility of the respawn position; follow-up below provides direct static evidence for boot clearing and the sound/coordinate paths.
- Exact combined shiny probability, all special encounter constructors and actual hidden-ability availability by species.

These remaining checks do not negate the confirmed table/branch findings; they limit claims of complete runtime verification.

## Follow-up: direct boot clearing, shiny cue and respawn coordinates

Fresh static tracing resolves three previous M-07 limits more precisely.

**Boot clears the retained record:** ARM9 entry `0x02000800` reaches the explicit BSS zeroing loop at `0x020008A8–0x020008CC`. The code-settings structure at `0x02000BA0` contains BSS start **`0x021106A0`** and end **`0x021E4980`** at offsets `+0x0C/+0x10`. The loop writes zero every four bytes throughout that range. The retained-shiny record **`0x021CFF50`** is inside it, so loss at fresh game boot is directly established rather than inferred solely from volatile RAM. In-game save serialization/restoration was not exhaustively traced; loading an emulator save state can restore RAM and is not equivalent to a fresh boot. A soft-reset route that re-enters this startup sequence also clears the record, but that exact re-entry was not instrumented here.

**A shiny-specific sound call exists:** overlay 1's visible-object update routine `0x021F67EC` recognizes object IDs `0xF0–0xF5` through ARM9 `0x0201A244`. It reads the slot's shiny flag via `0x0201A19C`, starts an effect at `0x021F685C`, then after its animation counter passes 30 tests the shiny flag again at `0x021F68AA`. If true it calls PlaySE (`0x02005F5C`) at `0x021F68B4` with sound **1562 (`0x61A`)**, from literal `0x021F695C`. This establishes a conditional sound cue in the real code, without claiming an audio recording or naming the sample by ear.

**Respawn uses candidate positions near the player:** `0x020198B8–0x0201991E` obtains the player's tile coordinates, chooses each offset modulo 12, and independently adds/subtracts them. Candidate X/Y therefore lie within **11 tiles on each axis** of the player. The retained-shiny branch later reuses these coordinates when creating the object at `0x02019B70–0x02019B74`, replacing species/form/level from the single saved-in-RAM record. Terrain and occupied-position checks precede creation, so this establishes a nearby candidate search, not a guaranteed immediately adjacent or reachable placement. The map-matching condition still applies.

The boot loop/settings and sound-handler ranges also match the English WIP exactly. Total comparison coverage is now 16 ranges. Fresh emulator map/restart/audio scenarios remain outside this report.
