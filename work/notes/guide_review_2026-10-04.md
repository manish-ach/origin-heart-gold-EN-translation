# Guide and documentation review

Review date: 2026-10-04. Status: review complete. Proposed corrections were not applied by this review; concurrent edits are noted below.

The guide needs targeted factual corrections and more precise links before another broad rewrite. Keep its useful answer tables and branch warnings, correct prerequisites and irreversible outcomes, and remove duplicated explanations and developer detail from player instructions.

## Review plan and reports

Five reviews ran sequentially, with one subagent active at a time. Each reads its assigned content and checks consequential claims against the untouched Chinese hack using existing ROM readers, scripts, maps and translation banks. Historical audit findings are leads, not assumed facts. A static review does not establish that every route works in a playthrough.

1. [Early Kanto](guide_review_2026-10-04_part1.md): chapters 1–3. Complete.
2. [Late Kanto and the League](guide_review_2026-10-04_part2.md): chapters 4–7. Complete.
3. [Johto](guide_review_2026-10-04_part3.md): chapters 8–10. Complete.
4. [Late Johto, shared mechanics and known issues](guide_review_2026-10-04_part4.md): chapters 11–13 and Known issues. Complete.
5. [Reference documentation and website](guide_review_2026-10-04_part5.md). Complete; representative ROM records sampled rather than every generated row.

[Editorial review and baseline checks](guide_review_2026-10-04_editorial.md) covers navigation, concision, presentation of evidence and maintenance documentation.

## Highest priority gameplay corrections

| Player impact | Correction | Evidence |
|---|---|---|
| Miss an early starter gift | Talk to Mom for the Running Shoes and get Daisy’s Town Map before collecting the Pallet gift. Daisy alone is insufficient. | Part 1, finding 1; scripts 736 and 842 |
| Miss a romance opportunity | Misty’s confession is before the final Hall of Fame, subject to the other route conditions. The current chapter 2 says after. | Part 1, finding 2; scripts 758 and 822 |
| Prepare for healing that never occurs | Yellow’s four Multi Battles heal before and after the series, not between fights. | Part 1, finding 4; script 739 |
| Follow a blocked route | Moving in appears blocked by the original hack; chapter 1 must not promise it as a working reward. | Part 1, finding 5; script 843 and starter flag writers |
| Search for an unavailable second gift | Swablu requires accepting the Route 5 rescue available to your starter, not obtaining both Bulbasaur and Growlithe. | Part 1, finding 3; scripts 9, 179, 183 and 197 |
| Lose optional rewards | Put the burglary and Route 5 raid deadlines before the Sabrina takeover step, and link their exact quests. | Part 1, findings 7–8; part 2, finding 8 |
| Follow the wrong sequence | Pass the Five Island Elder’s trial before asking him to release the disciple. | Part 2, finding 1; script 737 |
| Follow a shortcut that does not work | The ordinary Tohjo Falls hermit battle does not remove Route 21’s Mr. Mime. | Part 2, finding 2; script 114 |
| Consume a legendary encounter by fleeing | Explicitly include running away in the permanent-loss warning for the affected late legendary encounters. | Part 4, finding 1; encounter scripts and engine result check |
| Rely on an unsupported safety assurance | Remove the blanket statement that saves are unharmed; describe the existing out-of-range flag finding and its unverified effects. | Part 4, finding 3; D-1333 and engine flag bounds |
| Attempt an inaccessible objective | Put the Azure Flute blockage before Arceus instructions, rather than after the catch walkthrough. | Part 4, finding 7; script 942 |
| Follow conflicting romance conditions | Remove the assumption that the Dream World always follows Crystal’s Super Rod gift; keep any recovery route explicitly untested. | Part 3, finding 1; scripts 251 and 907 |

See the individual reports for exact guide lines, script offsets, concise replacement wording, lesser corrections and verification limits.

## Website corrections

- **Fix starter filtering before release:** the chapter 7 Giovanni story entry is hidden for Pikachu and Bulbasaur because its heading mentions Charmander. Only the Charizardite reward is starter-specific. Restrict the reward, not the whole quest.
- Use explicit quest metadata and stable identifiers rather than deriving restrictions and completion keys from headings. “Small extras” currently shares a completion key across chapters 7 and 13.
- Link item sources and tutor locations to the relevant location and exact quest, preserving meaningful prerequisites. A valid link to a broad location does not establish an item is currently obtainable.
- Correct trainer IV rendering for the 36 teams with mixed per-Pokémon values, and include Mew’s universal TM compatibility in move learner counts. The sampled raw records agree with the export; these are presentation errors.
- Label the 770-species availability figure as identified sources or inferred evolution/breeding routes, rather than proven runtime obtainability. See part 5 for extraction omissions and verification scope.

## Improve navigation without adding length

- Replace chapter-level links with exact quest links when referring to a named prerequisite or continuation.
- Keep one canonical explanation for romance, field moves, the pilgrimage and League HQ investigations. Regional entries give the local action and link back.
- Add a compact canonical entry for Lance’s post-final-Hall gifts; existing Red Orb/Jade Orb links point to a chapter with no such entry.
- Put permanent-loss warnings before the relevant choice. The known-issues page is a supporting index, not a substitute for a warning in the quest.
- Fold script evidence away from player prose. Move harmless shared flags and unreachable content into the maintenance audit.
- Preserve meaningful requirements and uncertainty when shortening. Do not replace accurate branch conditions with vague “post-game” labels.

## Recommended edit order

1. Fix false filtering, irreversible-choice warnings and wrong prerequisites or event order.
2. Reconcile repeated facts against one canonical explanation, with exact reciprocal quest links.
3. Correct reference-page availability labels and carry necessary branch conditions into acquisition information.
4. Trim repeated scene summaries and harmless technical commentary; preserve useful answer tables and preparation advice.
5. Regenerate the site and PDF from their sources, check the fresh output’s links, then test filters, deep links and completion state. Play-test the explicitly listed uncertain routes separately.

## Baseline and limits

The initial freshness check passed for 18 documentation pages, seven data files and 15 guide pages. The final check found all 15 generated guide pages stale after concurrent edits; reference documents and data remained current. The existing website build passes its internal link check: 2,371 pages, 221,944 links, zero broken links. This does not prove semantic correctness or browser filter behavior.

At the initial read, 359 guide entries contained 169 links to other chapter tops and seven links to specific entries. A later source recount found 360 entries, 165 chapter-top links and 17 section links. The initial built known-issues page exposed 726 detected developer-jargon matches outside folded sources. Concurrent edits have now moved that evidence into 194 Source blocks, with zero matches for those jargon patterns in the current source’s main text. Preserve that improvement; the remaining work is better prioritization and semantic cross-links.

No guide, game, translation-bank, tool or generated content changes have been made by this review. D-1432 was added through the decision tool to formalize the already-documented Bugsy party-count concern; it remains an untested suspected hack issue. No downloads, ROM builds, commits or publication were performed. Emulator playthrough and live website interaction have not been performed.

## Concurrent guide edits

Guide files changed outside this review while the sequential checks were running. Chapter 13’s field-move, Clefairy-repeat and Unown Report corrections are now present; they are not pending findings here. The README patch example was also updated to rc4. These concurrent improvements are preserved in the review’s status notes. The final individual generator checks found the 18 reference documents and seven data files current, but all 15 generated guide pages stale. The earlier zero-broken-link result applies to the existing build, not those newer source edits. Findings should be located by their heading and source offsets because document line numbers can shift. The main gameplay corrections above were checked against the later source text and remained outstanding at reconciliation.

## Applied (2026-10-04)

All findings of this review and its five parts were applied on 2026-10-04 (user-approved fix phase), after a reconciliation pass that checked every finding against the current guide and the untouched Chinese hack. The reconciliation counted, for chapters 1–3, 15 fixed by earlier edits, 12 outstanding and 1 conflict; for chapters 4–7, 15 fixed, 20 outstanding and 1 conflict; for chapters 8–10, 5 fixed and 22 outstanding; plus a prioritised website/generator list (P1–P3) merged with an independent data-docs report. Every outstanding and conflict row has since been fixed in `guide/*.md`, the generators (`work/tools/docs/gen_docs.py`, `places.py`, `work/tools/site/export_data.py`, `sync_guide.py`) and the site pages. The working tables lived in the session scratchpad and are not kept in the repo; this section is the lasting record.

**Outcomes.** The gameplay corrections listed above are in the guide (Mom and Daisy before the Pallet gift, Misty's confession before the final Hall of Fame, no heal between Yellow's four Multi Battles, moving in shown as blocked, the Route 2 warehouse battle only on talking to the grunt, the Five Island order, the Tohjo Falls hermit, fleeing in the permanent-loss warnings, the Azure Flute blockage first, the Dream World order). Badge numbering was re-traced (badge 4 is the Marsh Badge, Saffron Gym; badge 5 is the Soul Badge). New canonical entries: Lance's visit home (ch. 1) and Giovanni catching Arceus (ch. 8); renamed headings were relinked across all chapters, the guide index and the site, and `check_site.py` reports 0 broken links. "Post-game" now means only after the final Hall of Fame; whole-quest starter/gender tags only; optional `<!-- quest: … -->` metadata gives stable ids and filters. Known issues gained a "Check these first" index and one anchor per issue. Website: trainer cards on a location page list only that area's battles, IV ranges and Mew's TM learners are fixed, availability figures are labelled "with a source found in the game data" (species and forms vs national-dex species), tutor and trade mentions in the guide link to `/tutors/` and the location pages, and the `--jargon` check now also covers trainer and location pages (0 hits). Generated trainer docs: the letter-by-letter starter note is fixed, the Victory Road 3F starter teams (#268, #272) are "probably never" (the hack never records your starter), the leftover League-entrance and Cherrygrove rival scenes (#489–#491, #495–#497) are marked "never used: the scene can't trigger", and the unreachable Dark Cave (Route 31 side) copy of the Whirl Islands Challenge is no longer listed (those trainers are fought on Route 41).

**Battle format of `TrainerBattle X, X`.** Re-research of the field code showed the same id twice makes a Double Battle against one trainer: one team, sent out two at a time (Chuck 4, Pryce 6, Morty 6; Giovanni opens with Mewtwo and Tyranitar). The guide and generators no longer say "two copies of the team". This supersedes the "two copies" wording in `guide_errata.md` and parts 2–3 of this review. The hack's own battle code was not found, so the guide marks this "not confirmed in game" for Chuck and Giovanni.

**Still not confirmed in game** (static analysis only; marked in the guide): the battle format above; Misty staying hidden after a won Resort Zone date (D-1402); Yellow's Champion-room Singles running a Double Battle; moving in being blocked; Morty's three Lv. 1 Pokémon; the MooMoo Farm Miltank falling sick for good if the Dream World is finished before the League HQ's third order; Bugsy's party-count rule (D-1432); the Azure Flute being unobtainable after the Hall of Fame; the out-of-range story records; and the other suspected hack bugs flagged on the Known issues page (47 entries). None of these was play-tested; an emulator pass over them is the remaining verification step.
