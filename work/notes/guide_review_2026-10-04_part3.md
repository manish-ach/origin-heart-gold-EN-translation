# Guide review, part 3: early and middle Johto

Date: 2026-10-04. Scope: chapters 08–10 (1,889 lines at initial read), including their central romance entry. Review only; no guide, tool, translation-bank or ROM edits by this reviewer.

## Method and limits

Read all three chapters, the relevant old errata, repository/style instructions and decision workflow; compared the earlier reviews where their subjects overlap. Used existing `work/tools/docs/scriptdump.py` and `romdata.py` against the untouched Chinese v4.0.3 ROM (the existing ROM cache). File numbers below refer to `a/0/1/2`; `@` means a byte offset, not a text-file line. English banks identify dialogue; ROM script control flow and trainer records establish behavior. This is sampled static verification, not a complete replay or a new collision audit. Party-state, map reachability and engine-dependent outcomes explicitly marked below still need runtime verification.

## Corrections and improvements

### 1. Correct the central romance timeline and remove its absolute Crystal claim

**P2, high confidence that the documentation contradicts its own verified script conditions; medium confidence about an executable early-romance recovery route.** `guide/09-ilex-goldenrod.md:479–489,522` describes the Dream World as a round-3 investigation and asserts the Super Rod always comes first. `guide/10-ecruteak-olivine.md:553` consequently says Crystal's gift cannot undo a Dream World choice. But chapter 10's farm entry already correctly explains that the investigation is offered on first arrival, independently of the HQ order.

The farmer checks completed-Dream-World flag 2289 @251:106, then sick-Miltank flag 744 @117. Acceptance sets 2299 @1419 and stage `0x40a3=5` @1423, which arms the stable event. Elm clears 744 @840:3194/3324, so the farm is sick before the round-3 order. Crystal's gift checks only gift flag 175 @907:928 and Super Rod possession @946; accepting removes the rod @4329 and clears her lock 2145 @4417. Jasmine's badge scene hides Crystal @909:16090. The gift has no Dream World check.

**Shortest useful correction:** “Do the love reading before accepting the farmer's investigation, which is available on your first visit.” Delete “the Olivine Super Rod comes before it” and “It can't undo the Dream World choice.” In the technical note, say: “The Super Rod gift clears Crystal's lock even after the Dream World in the scripts; an early-investigation route has not been tested in game.” Do not promote an untested sequence as a guaranteed romance workaround. Her confession still needs the reading and other conditions, and only one confession remains possible.

The central opening should say **“The scripts provide a romance route, but several partners' dates or moving-in scenes are unavailable”**, rather than implying the complete four-stage path works for every partner. Keep the existing specific restrictions in one canonical table.

### 2. The central Misty row repeats the dangerous post-game timing error

**P2, high confidence; evidence inherited from part 1's independent trace.** `09:519` says “Cerulean Gym, post-game.” Part 1 establishes file 758 @3665→6418→7044 requires flag 2311 clear, while final Hall of Fame file 822 @2454 sets it. Use **“Cerulean Gym, after the Radio Tower liberation and before the final Hall of Fame”**, retaining the precise-access runtime caveat from part 1. Link directly to the corrected confession entry, not only chapter 02. The dates column's dangling “04” should be a direct link to the Resort Zone date.

### 3. State the shrine's one-time gifts and shared visit restriction accurately

**P2, high confidence.** `09:133` says “Each legendary appears once per visit to Ilex Forest,” easily read as repeatable gifts and inaccurate about the shared appearance gate. File 52 first checks shared visit flag 2298 @2563, then permanent received flags 2296 @2574 and 2297 @2585. Shaymin appearance sets 2298 @3655; receiving it sets 2296 @3403 and gives species 492 Lv.90 @3428. Celebi appearance sets 2298 @3815; receiving it sets 2297 @3501 and gives species 251 Lv.90 @3530. Ilex entry clears only 2298 @92:130. A scan of all disassembled event scripts found no ClearFlag for 2296 or 2297.

**Shortest useful correction:** “One Shaymin and one Celebi per game. After meeting Shaymin, return through Ilex Forest before trying for Celebi.” Keep the day/night, lead Pokémon, Gracidea and spare-slot instructions. For a refusal/full party, say the Pokémon can be spoken to again while present; re-entering Ilex permits another appearance of an unreceived Pokémon. This also explains why waiting until night at the shrine does not by itself advance to Celebi.

### 4. Morty's battle description should match its scripted opponents

**P2, high confidence about the script, runtime team presentation untested.** `10:236` calls the match a “6-on-6 Double Battle.” File 918 checks party sizes 1–5 @1055–1133, then uses `TrainerBattle [31,31,0,0]` @13687: two copies of trainer 31, whose untouched ROM record has six Pokémon. This is the same duplicated-trainer construction already described explicitly for Entei and Marauder elsewhere in these chapters.

**Shortest useful correction:** “Bring six accepted Pokémon. The challenge is a Double Battle against two copies of Morty's team.” Avoid promising a numerical opponent total until the battle engine presentation is verified. The fixed species-list explanation is accurate in principle; move the full long list into a compact expandable reference/table and leave a few obtainable examples plus key exclusions in the route text.

### 5. Harmonize the Houndour warning with the recommended bug-hunt order

**P3, high confidence editorial correction supported by the existing script issue.** `09:66` correctly recommends finishing the hunt before starting the ranger quest, but `09:92` unconditionally tells readers to report the catch before finishing the hunt. Read independently, these prescribe opposite orders.

**Shortest useful correction:** “Safest order: finish Bugsy's hunt, then start this quest. If you've already caught Houndour during the hunt, claim the Safari Balls before reporting the hunt to Bugsy.” File 92's Houndour progression and hunt-end reset share `0x409b`; the existing detailed warning is sufficient proof context. Keep one clear action order, with a short recovery exception.

Also shorten the Rocky Helmet explanation at `09:169`: “Take it after the hunt; taking it earlier blocks Ariados and can cost the top reward.” The current “at most three bugs” sounds compatible with the reward table's top tier of three player-handled bugs, because it mixes total bugs handled with the player's counter.

### 6. Remove the contradictory Lunar Wing requirement for re-entry

**P3, high confidence.** `10:493` requires a Lunar Wing in the Bag, while `09:556` correctly says the script never checks it. File 251 script 9 checks only final-Hall-of-Fame flag 2261 @882, then jumps to the message @1295 and warp @1316. No HasItem occurs on that path.

**Shortest useful correction:** “After the final Hall of Fame, examine the back wall of the west stable room to return to the Dream World.” Link to chapter 09's exact legendary entry; leave the exit statue's Lunar Wing behavior there.

### 7. Carry existing limitations into the player-facing rules consistently

**P3, high confidence.** Jasmine's `10:580` says every party member must qualify and lists accepted high-Defense species, while the existing known-issues entry says Yungoos, Gumshoos, Flapple and Appletun pass its incomplete species list. File 909 uses a list of `PlayerHasSpecies` checks, as Morty and Falkner do. Use “Jasmine asks for at most three Pokémon with base Defense 130+. The game enforces a fixed species list; Aegislash is refused.” Link to exceptions instead of duplicating the entire list twice. Do not present the intended rule as an exact stat calculation.

Bugsy's count issue is **already documented**, not a new discovery: initial script 866 @147–209 jumps to comparisons of temporary `0x8005` @367/@380 without first loading party size; the only `GetPartyCount` is rematch @4541. During this review the chapter 08 wording was observed already explaining this uncertainty. Preserve that caveat; don't strengthen “most likely bring six” into a verified promise. I formalized the existing suspicion as **D-1432** after a decision-register search returned no existing party-count finding; no behavior was changed.

### 8. Make the high-value cross-references useful and remove obsolete prose pointers

**P3, high confidence editorial finding.** All three chapters repeatedly say “see the tutor table,” “see bugs,” “see Questions,” “next page,” or link a whole long chapter followed by a quoted heading. Some referenced “Questions” or “Suspected hack bugs” sections are no longer in the chapter. Replace these with exact section anchors or the corresponding site reference page. Priority targets:

- `08:433`: give one **pre-Route-33** Moomoo Milk source, not a generic item-list pointer. The local generated item reference includes Route 8 and Resort Zone Pokémon Center shops and earlier gifts; verify the chosen shop's availability and link it. MooMoo Farm is later, and its milk stall is initially closed.
- `08:469–476`: add a direct link to the chapter 13 Ruins of Alph navigation/diagram if that route is retained. The Molly escape and dream chambers need a clear next-step path more than extra scene summary.
- `08:593–598`: “one item a day, one per talk” is ambiguous between a daily purchase cap and a weekday-specific stock list. State the verified stock rotation; test/trace repeat purchases before claiming a daily cap.
- `09:479` and `10:486`: use exact reciprocal anchors between the farm investigation and the central partner-selection steps.
- `10:599`: link directly to the SecretPotion acquisition in chapter 11.
- `10:512`: reconcile “you need HM05 for the Whirl Islands” with chapter 13's HM-free overworld findings (D-1428). This reviewer did not retrace engine checks; the common-mechanics reviewer should decide the final prerequisite wording.

Move source byte offsets/flags into expandable technical notes. Keep visible warnings when they change what a player must do. Drop explanatory harmless shared-flag history from `08:411` after retaining “one item only.” Give a short “before moving on” list for Route 33, the Plain Badge and Route 37 rather than repeating the same deadline in many paragraphs.

## Static checks that supported current instructions

These are samples, not certification of every claim in a chapter:

| Area | Evidence checked | Result |
|---|---|---|
| Cherrygrove Slugma reward | 847 Slugma branch; trainer 745 data | Three Slugma Lv.28/25/25 and 5 Heal Balls on the helping/winning route agree with current text. |
| Mr. Pokémon quiz deadline | 229 @30 tests HM08 before @51 Dark Cave flag and @62 gift flag | Keep explicit “before owning HM08” warning. |
| Gyro Ball request | 854 @3872–3895 sets 1850 without TakeItem | Keep “you retain the TM.” |
| Molly's Entei fights | 51 @801 HealParty; battles @818/@2623 both [671,671,0,0] | Current duplicate-team and single-pre-series-heal language is materially useful. |
| Railway crew ending | 51 @4253 sets hide flag 1904 | Consistent with current main-route advice; prior collision review not independently repeated. |
| Academy reward risk | 82 reward/answer flag 1858 flow | Preserve the warning about a TM-track answer followed by a loss; no additional correction found. |
| Heatran encounter | 57 weekday @1531, battle @2158, stone removal @2208, appearance @2226 | Tuesday + consumed Magma Stone route consistent; encoded wild level was not independently decoded here. |
| Green/Red Route 30 dates | 228 @761 checks confession, @789 starter flag, @1022 Red exclusion; heals @3773/@7438 | Current reversed confession condition and starter-flag caveat agree; not a successful runtime route test. |
| Love reading deadline | 895 @14 checks 2289; paid reading sets 1618, successful branch sets 1619 @993 | Keep first-reading/no-retry warning; deadline is investigation completion, not an assumed fixed badge sequence. |
| Dream World choice | 898 choice-lock writes, @2307–2329 completion, @2337–2377 no-choice locks | Correct to warn old-man choice comes before the Will/Karen fight and statue exit. |
| Sammy/Celebi supplies | 52 @3574 checks Fresh Water ×10; light-species branch precedes it | Existing “berries untested by script, supplies not consumed” caveat remains appropriate. |
| Plain Badge | 883 main badge and Multi Battle branch, 32/888/890 references | Current friendly vs Multi Battle distinction and event deadlines are readable; no new correction from sampled branches. |
| Ho-Oh chain | 924 menu, 918 Clear Bell branch, 21 references | Main sequence agrees with current text; leave alternate Lugia menu bug for part 4's dedicated trace. |
| Beasts release | 23 @4276 onward; 842 reference | Keep Lance-at-home prerequisite; part 4 must include the expedition overwrite warning already in known issues. |
| Crystal's rod | 907 @928–960, @4329–4427 | Gift taken once; exclusion cleared. Ordering claim needs correction as above. |

## Coverage and remaining validation

All sections were read for understandable directions, clear conditions, concision and links. Static inspection focused on the branches listed above and the consequential findings; not every merchant price, quiz answer, coordinate, species ban, trainer move, item repeatability or cosmetic branch was re-derived. Old errata corrections are largely present in these chapters, so the old report is a useful lead list but not a completed-verification certificate.

Highest-value runtime checks: early Dream World followed by Crystal's gift before Jasmine; Morty's actual duplicate-team battle presentation; Bugsy with different party sizes and prior NPC interactions; shrine refusal/full-party/day-to-night transitions; the exact reachable confession window for Misty (coordinated with part 1). No ROM was built, downloaded or modified.
