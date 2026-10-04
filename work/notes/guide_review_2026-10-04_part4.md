# Guide review, part 4: late Johto, common mechanics and known issues

Date: 2026-10-04. Scope: all of guide chapters 11–13 and `guide/known-issues.md`. Review only: no guide, tools, banks, ROMs or decision records changed.

## Evidence and snapshot

Read the four documents in full, relevant prior errata and the earlier review reports. Independently inspected consequential event branches with the existing `scriptdump.py`/`romdata.py`, then read relevant engine bytes directly from the untouched Chinese ROM. The cached arm9 and **all** cached event-script members were compared with freshly loaded `work/rom/origin_v4.0.3_cn.nds`; both comparisons were byte-identical. `file @offset` below means event-script member and byte offset, never a text-file line.

The guide changed outside this review while the overall review was running. Latest file modification times observed, UTC: chapter 11 10:39:08, chapter 12 10:35:03, chapter 13 10:38:58, known issues 10:39:03. Line references below use that state. Chapter 13 **already correctly** says Surf needs the Rainbow Badge, obstacle prompts do not require the learned move, the Clefairy dance repeats, and Unown Report notes are unavailable. Do not apply an older report that claims those corrections are still missing.

This is a sampled static review, not a successful emulator walkthrough or an exhaustive verification of every list, coordinate, battle engine detail and reachable map path. Existing suspected bugs are not new discoveries here.

## Recommended corrections

### 1. Include running away in the late legendary warnings

**P2; high confidence in the branch/engine behavior; not runtime tested.** Chapter 12 lines 421, 527, 543 and 554–555 warn about catches and knockouts but omit escape. Chapter 11's Lugia entry correctly includes running away. The same misleadingly named `CheckBattleWon` command governs all these encounters.

Command 220 is mapped by arm9 `0x020F793C + 220*4` to `0x02048DF0`. Its call at `0x02048E14` goes to `0x0205172C`, whose Thumb code returns false only for outcomes 2 and 3 (loss/draw); every other outcome returns true. Thus the command is not a test for a victory alone. The scripts then permanently set the encounter flags:

- Lugia: 104 @3915–3967, flag 579; this is the existing documented flee-loss comparison.
- Dialga/Palkia: 130 @2706–2776, flags 2342/2343.
- Giratina: 135 @2500–2528, flag 2340.
- Regigigas: 131 @1008–1036, flag 2305.
- Arceus: 131 @1335–1367, flag 2306.
- Lake trio and Raikou use the same pattern (934 scripts 29–31; 260 @5082–5116).

**Shortest correction:** “Save first. Catching it, knocking it out or running away removes it permanently. Losing lets you retry.” Apply consistently, including the corresponding known-issues summaries. Label the Arceus/Regigigas mechanics as scripted but inaccessible in normal post-story play (finding 7), rather than suggesting an executable catch route. These are extensions of documented encounter-loss warnings, not new hack findings.

### 2. The photo schedule is NPC dialogue presented as reliable directions

**P2; high confidence.** Chapter 11 lines 192–214 calls the house's table “Useful for finding them.” At least two entries demonstrably conflict with the actual scripts and with other guide entries:

- Brock, line 198: “daily 17:00–20:00.” File 5 @608–652 tests the hour against 17, 18 and 19 using successive not-equal rejection branches. No hour passes all three. The hide flag is set on rejection. Known issues already documents this as D-1394.
- Clair, line 212: “Fridays.” File 111 @795 requires final-Hall-of-Fame flag 2261; @1678–1738 accepts hours 6, 7, 8 or 9; @1966 clears hide flag 521. No weekday check is on this appearance path. Chapter 12 line 591 correctly gives the morning window.

**Shortest correction:** replace the 16-row quote-derived table with “He gives Gym Leader photo tips, but some are inaccurate; see the verified photo locations.” Link to a canonical verified table. If retaining this table, explicitly title it “What the NPC says” and mark known false rows; it must not be the player's authoritative schedule. A full audit of the other fourteen rows remains necessary before promoting them to verified directions.

### 3. Remove the save-safety assurance and surface the existing save-write finding

**P2; high confidence about invalid accesses; impact on a real save remains uncertain.** Known issues line 7 assures readers that their save is not harmed unless an entry says otherwise. The page omits the existing **D-1333** finding from `work/notes/softlock_audit.md`, including the Mt. Mortar expedition interaction covered in chapter 11.

Independent verification found file 168 @235 checking flag 7286 (`0x1C76`) and @1954 setting it; file 962 @1819 sets flag 4461 (`0x116D`). Arm9 `GetFlagAddr` at `0x0204F8E4` handles these as ordinary flags, shifts their ids by 3 to obtain byte indexes, compares against `0x194`, calls an assertion when beyond the bound, then still forms the address at base + `0x2E0` + index. Its associated save-block size function at `0x0204F840` returns `0x474`. These ids exceed both the intended flag area and that block. Whether the assertion aborts or execution continues, this does not support a blanket safety guarantee; the exact effect on adjacent saved data has not been measured here.

**Shortest correction:** “Most findings concern missed rewards or scenes; freezes and uncertain save-data effects are identified separately.” Add a short D-1333 entry linking to the audit: “The Route 1 promotion and Mt. Mortar expedition use out-of-range flags. The effect on saved data is unverified.” Do not claim observed save corruption or prescribe avoiding the story-required expedition as a proven workaround. This is an already registered finding; do not create another record.

### 4. Remove unnecessary learned-Whirlpool prerequisites

**P2; high confidence static evidence, retain the central runtime caveat.** Chapter 12 line 290 explicitly requires a party Pokémon to know Whirlpool; chapter 10's Whirl Islands prerequisite identified by part 3 also needs harmonizing. Chapter 13 now correctly distinguishes interacting with an obstacle from choosing a learned move in the party menu.

File 146 @2540 asks `GetPartySlotWithMove` for move 250, then @2559 checks badge 6 (Volcano). The command's handler at arm9 `0x0204C8D4` reads the move argument but does not use it to choose the Pokémon: @`0x0204C902` calls overlay 1 `0x02205200`, which calls arm9 `0x02053500`. That routine iterates party slots and uses the healthy/non-Egg check at `0x02053354`. It does not inspect the requested move. The same command drives the other scripted obstacle prompts; Surf's water prompt separately checks badge 3 (Rainbow), visible in overlay 1 @`0x021E65EE` onward. Waterfall's script independently checks badge 7 at 146 @2402.

**Shortest correction at Dragon's Den:** “Cross the whirlpool by examining it with the Volcano Badge; no party Pokémon needs to know Whirlpool. See Field moves.” Give a direct chapter 13 anchor. Keep Fly/Flash's learned-move requirement distinct. Do not remove HM item requirements from NPC quests that actually check possession.

### 5. Correct the Jirachi resource instruction where players act on it

**P3; high confidence.** Chapter 11 line 439 says a Star Piece is used per repair, while the caveat that none is required is buried at line 449 with a dead prose pointer to “Suspected hack bugs.”

File 81 @1134–1160 gates the stone on final-Hall-of-Fame flag 2261. Its repair path @1801–1870 performs `TakeItem [91,1]` @1841, then unconditionally increments `0x408C` @1849 and compares with 24 @1855; there is no inventory check or branch on removal success. This confirms the existing known-issues report.

**Shortest correction:** “Choose Yes repeatedly to repair the stone. Each repair takes a Star Piece if you have one, but still counts if you have none.” Keep the normal post-investigation seven-repair figure as a static, untested estimate. Move shared-variable explanation to the technical source. Players need the count and actual requirement, not a counter implementation walkthrough.

### 6. Chapter 13 overstates the Lake of Rage item's automatic weekly return

**P3; high confidence.** Chapter 13 line 89 says it comes back every later calm Wednesday. Chapter 12 line 435 correctly adds the required intervening visit on another day.

File 934 @1749 checks calm-day marker `0x4037=0xF229`. The non-calm branch clears collected flag 327 @1782. The calm branch @5595–5614 checks 327 and skips unhiding the item when already collected. Merely letting a week pass does not execute the non-calm map-load branch. The engine weekday gate at arm9 `0x0203A580` checks Rocket-HQ flag 202, maps 88/45 and weekday 3; this does not itself clear item flag 327.

**Shortest correction:** “It returns on a later Wednesday if you visited the lake on a non-calm day in between.” Prefer one canonical explanation in chapter 13, with the reward table linking to it, to avoid another two-copy drift.

### 7. Put the unavailable Arceus route limitation before its instructions

**P2 for presentation of an unavailable objective; high confidence about the script obstruction, no new reachability proof.** Chapter 12 lines 547–561 begins as a normal post-Hall-of-Fame catch walkthrough and postpones “probably can't get the Azure Flute” until the notes. Known issues and the shrine entry already establish a definite script obstruction in the normal sequence.

Independently checked file 942 @104–121: `0x40B7 >= 4` branches to the keep-it-safe line **before** testing final-Hall-of-Fame flag 2261. The gift @521–539 gives item 536 and advances this variable to 5; it cannot be reached through the offer once the variable is 4. The existing League-HQ trace sets 4 before the finale. File 131's centre-circle trigger needs 5. Earlier collision evidence says the alternative temple doorway cannot be walked to; this reviewer did not repeat that collision test.

**Shortest correction:** label the section “Sinjoh Ruins: unavailable post-story encounters,” open with the Azure Flute blockage, and put scripted encounter details in an optional technical disclosure. Retain the exact shrine link and confidence limit; do not promise the centre-circle steps can be followed. Remove “catching all three is the first step toward Arceus” at line 529, or immediately qualify that Arceus is blocked in normal play.

### 8. Repair remaining cross-chapter contradictions and overclaims

**P3; high confidence for documented contradictions.**

- Chapter 11 line 239 says the **only** working romance reset is the Island Forest wish. Part 3 independently traced Crystal's Super Rod reset (907 @4417 clears 2145); chapter 12 lines 52–54 already mentions it. Change to “For Yellow and Misty, use the Island Forest wish before the Dream World.” This keeps the sentence scoped to the unavailable Battle Tower workaround discussed there.
- Chapter 11 line 158 presents “every party Pokémon must be Fighting-type” as the exact gate, then lists only Staraptor as an exception. The existing known-issues entry correctly describes a fixed banned-species list with many later-generation exceptions. Use “Chuck asks for Fighting types; the game checks a fixed species list” and link to the exceptions, like Pryce's clearer explanation at line 364.
- Chapter 11 line 247 says all Frontier facilities and the Trainer House “work as in HeartGold,” directly after describing broken Multi Battle partner availability. Remove the blanket equivalence unless their actual mechanics, teams and rewards are audited. “The Frontier offers Tower, Factory, Hall, Castle and Arcade challenges, plus the BP Exchange” is sufficient.
- Known issues line 465 says “buy HM08 at Mt. Mortar.” Chapter 11's correctly described map-return quest gives the HM. Change **buy** to **receive** and link directly to that quest. This is particularly valuable because obtaining it closes an earlier reward.
- Known issues calls badge id 4 “Soul Badge” in the Route 9/Marisa entries, while the corrected field-move table maps badge 4 to Sabrina's **Marsh Badge**. Reconcile with part 1's badge mapping and actual GiveBadge scenes; do not propagate the source-file label as the player's badge name.
- Chapter 13 line 121's Lighthouse photographer condition says “once the Lighthouse story is done.” File 65 checks flag 477 and weekday 3/6; that flag is already set at new game (149 @82), again on the Route 39 arrival scene (249 @4122), and at the start of the medicine errand (66 @2515). It is not a completed-SecretPotion check. Safest short text: “Lighthouse 5F: a photographer appears on Wednesdays and Saturdays.” If adding story gating, trace access to 5F and explain the actual applicable stage; do not infer it from a hide flag's name.

### 9. Tighten navigation and reduce detail that competes with decisions

**P3; editorial, supported by the document read.**

- Chapter 11's Mahogany HQ entry sends the player backward to chapter 12 for Lake of Rage, forward to chapter 12 for B3F, and back again for Archer. Put the red Gyarados → transmitter → shop → Boot Camp password → HQ floors sequence in one place, or provide exact reciprocal anchors at each transition. A complete second B3F walkthrough is unnecessary.
- Chapter 12 line 105 points to chapter 11 “step 4” for Archer's room; Archer is **step 5** there. Prefer a heading anchor rather than a brittle step number.
- Chapter 12 starts with Route 46, an early-Johto required event, then later returns to Route 47, which precedes the Route 42/Lake of Rage story. Mark out-of-order entries clearly or place them at their actual progression points. Location order alone should not imply story order.
- Prioritize direct anchors for the Durin Berry gift → Swinub → spray recipe, Lance's home visit → Burned Tower → beasts, Rainbow Wing → Morty → Bell Tower, Lugia ritual and the central field-move table. Replace “next page,” “previous entries,” “tutor table,” “see Known issues” without a link and references to absent “Suspected hack bugs” sections.
- Keep the expedition warning, but write its exact window: “After Lance visits your house, see the Burned Tower release scene **before rematching the expedition leader**.” Chapter 11 line 306 currently reads as a permanent ban on the rematch. The existing branch evidence is 842 @2223 sets `0x409F=11`; the Burned Tower scene needs 11; 962 @3482 overwrites it with 3. Losing already-completed beast release is not established. Link this warning from the Burned Tower and Raikou entries.
- Move long species-ban lists, every unchosen menu response, full scene summaries and implementation history behind optional detail. Visible quest instructions need the start, actionable choices, prerequisites/deadlines, reward and next destination. Keep concise “save first” and “no healing” warnings visible.
- Known issues should lead with consequential missables/freezes, then group cosmetic and unreachable content separately. It currently gives equal prominence to unavailable test scenes and lost rewards. Deduplicate Route 30 romance and Battle Tower partner entries; link to one canonical issue instead. Existing issue identifiers should be stable link targets, so a guide entry can land on the actual warning rather than a large regional section.

## Current instructions that held up in sampled checks

| Area | Independent evidence | Assessment |
|---|---|---|
| Whirl Islands payout | 872 @2417/2428/2439/2450 tests 2097 four times; @3199 clears only signup 2094; @3214 can set it again | Northwest-only and repeated payouts are correctly reported. The normal four-island quest description can stay if the actual behavior is clearly noted. |
| Whirl prizes | 872 reward branches @2495–2523, @3115–3184, @3958 onward | Existing prize sets agree with the sampled item/count instructions. |
| Jirachi repair | 81 @1841–1861 | Missing inventory gate is real in script; needs clearer player-facing requirement, finding 5. |
| Lake trio tests | 935 @750–799 battle; @888–905 friendship255; flags649/651/652 | Sequential trials and max-friendship threshold agree. Day-dependent appearance and loss warning need the clarifications above. |
| Clair photograph | 111 @795, @1678–1738, @1966 | Chapter12's morning window is accurate; chapter11's Fridays claim is not. |
| Clefairy repeatability | 8 @6–197; 10 @26,309,775,1985; arm9 hour table `0x020F2A94`; daily clear `0x0203FBAC` | Current chapter13 timing and reset are supported. Daily clear zeroes24 bytes beginning at flag2720, covering2741. Pick-up-before-leaving warning is supported. |
| Unown Report | 38 @877–929,1519–1545,2033; scan of reachable SetVar/AddVar/CopyVar instructions | No reachable writer of `0x40EC` found; zero-state branches yield the existing no-progress line, including after seeing all letter Unown. Current correction is supported. Did not independently test !/? encounters. |
| Shared expedition/beast progress | 962 @3482; 842 @2223; existing Burned Tower scene condition | Preserve the warning, scoped to before releasing the beasts. |
| Field moves | command141 handler and first-healthy helper, 146 Waterfall/Whirlpool gates, ov1 Surf prompt | Current central HM-free explanation is supported; fix contradictory local prerequisites. |
| Azure Flute | 942 @104–121 and @521–539 | The premature >=4 branch blocks the normal late gift; present this before the inaccessible encounter instructions. |
| Out-of-range flags | 168 @235/1954; 962 @1819; arm9 `0x0204F8E4` and `0x0204F840` | Existing D-1333 is missing from the player known-issues page; do not guarantee save safety. |

## Coverage limits and next verification

Read all 2,037 lines across the four reviewed files, including the entire known-issues catalogue. Static checks prioritized irreversible encounters, story gates, field moves, time conditions, rewards and resets. The existing known-issues claims for other chapters were read for contradictions and usable advice, not individually re-proven; parts 1–3 handle their primary gameplay evidence.

Not performed: a new collision/path audit of the Distortion World or temple entrance, complete runtime battle/team verification, a full photographer schedule audit, every tutor compatibility list, every merchant quantity/price, every unused scene, or emulator testing of midnight/week changes, escape outcomes, party-menu field moves and save corruption. Highest-value follow-ups are an emulator check of HM-free obstacle interaction and late encounter escape handling, a fresh-save photo schedule check, the known save-write effects, and walking the pad maze to turn the current destination-coordinate table into an actual route. No downloads, builds, game-data exports or new decision records were required.
