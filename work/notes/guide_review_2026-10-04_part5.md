# Guide review, part 5: reference data, website and contributor documentation

Reviewed 2026-10-04; final checks at approximately 10:48 UTC. Review only: no guide, generator, translation, ROM or website changes. Other work was changing guide files during this review, so freshness is a point-in-time result.

## Findings and shortest improvements

### P1 — Starter filtering hides a story scene for two starters

`guide/07-league-to-cherrygrove.md:29` calls the whole Cerulean Cave Giovanni entry “(Charmander starters)”. `work/tools/site/sync_guide.py:heading_tags` turns that into `data-starter="Charmander"`; `site/public/ohg.js:apply` hides the whole section for Pikachu/Bulbasaur. The entry itself correctly explains that only the Charizardite conversion requires Charmander. The untouched ROM file 912 checks flag 1287 at 5414 and item 504 at 5425, branching to 5554 when absent; the common story continues. This filter removes necessary story instructions.

**Shortest improvement:** remove the starter restriction from this heading, retain it beside the reward, and preserve the old fragment as an alias when renaming. Longer term, give quest visibility explicit metadata separate from reward/branch conditions; title wording should not silently change who can see a quest. Check the three starter settings against the same mandatory-story checklist.

### P2 — Done checkboxes collide across chapters

`site/public/ohg.js:42–48,62` stores and reads completion by bare heading ID. Both chapter 07 and chapter 13 have `## Small extras`, becoming `small-extras`. Marking either complete marks the other complete, and “Hide finished” can hide the wrong content.

**Shortest improvement:** use a stable quest identifier, or at least page path plus fragment, consistently in storage and filtering. Migrate old values conservatively; heading edits should not silently erase progress. Verify chapter 07 and 13 independently.

### P2 — Correct data is rendered as incorrect team-wide IV information

`site/src/components/TrainerCard.astro:38` prints only `t.team[0].ivs` followed by “in every stat” below the whole team. **36 exported teams have different per-Pokémon IV values.** Example trainer 1 (Green): Bulbasaur has 12, Jigglypuff/Ditto/Tangela each have 6. The untouched party bytes support these values. The JSON is correct; the template loses the distinction.

**Shortest improvement:** show IVs per Pokémon only when they differ, or omit the footer for mixed teams. Keep the compact footer only when every party member shares the value.

### P2 — “Learned by” misses universal TM learners

`site/src/pages/moves/index.astro:11` skips `s.tms === 'all'` instead of adding that species to each TM/HM move. Mew (151) has a documented Five Island gift and `tms: "all"`, so TM/HM learner counts omit it unless another learning method happens to add it. This contradicts the Mew page's accurate “Can learn every TM and HM.”

**Shortest improvement:** expand the universal compatibility marker using the TM/HM move IDs for counting. Label these as compatible species/forms, not independently verified obtainable Pokémon, unless reachability is established.

### P2 — Location matching silently drops meaningful crossreferences

`AreaIndex.find` in `work/tools/site/sync_guide.py:80` uses literal strings. Straight apostrophes in guide headings do not match curly apostrophes in area names: **Diglett's Cave, Dragon's Den and Rotom's Room** are concrete examples. Other missing associations include **Sea Cottage, Pokémon Tower, Silph Co., Forest of Time, Dance Theater and MooMoo Farm**, whose guide names differ from area grouping/naming. At the final scan, 331 of 357 colon-bearing quest headings matched and 26 did not. Some unmatched headings are legitimately global and should not be assigned a single area.

`site/src/pages/locations/[slug].astro:15–26` derives its reverse quest list from the same generated location tag, so each failed match loses links in both directions. `place.split(' → ')[0]` also links only the first place of multi-location chains; for example Route 30 → Route 31 does not automatically attach the quest to Route 31. An ordinary broken-link checker cannot detect these absent links.

**Shortest improvement:** normalize apostrophes and use a small reviewed alias/explicit area-ID list, allowing multiple places per quest. Report unmatched headings for editorial review, with an explicit exemption for global topics. Verify Diglett’s Cave links directly to the Magma Stone quest and back.

### P2 — Item, gift and tutor pages lose the conditions that make them usable

`work/tools/site/export_data.py:285–327` exports item source place/quantity/payment but no condition or quest reference. `site/src/pages/items/[slug].astro` consequently presents Charizardite as two MysteryStone exchanges without the Cerulean Cave starter condition, and Magma Stone as a gift in Diglett’s Cave without its late story requirement. File 5 explicitly checks story variable 16546 against 13 at 262–268 before permitting the Magma Stone interaction. Item pages contain neither the precise quest link nor the relevant warning.

The tutor template at `site/src/pages/tutors/index.astro:10,22–24` prints locations and “see the quest guide” / “limited (see guide)” as plain text. Location pages say “See the quests above” even when none matched. This forces readers to search a long guide after reaching the correct reference row.

**Shortest improvement:** attach one concise condition and canonical quest URL to conditional sources, with location links. Reuse the quest's explanation rather than repeating it. Link TM/HM labels directly to their item pages instead of the broad Items index, and allow moves to lead to their learner lists. Avoid expanding every reference table with full walkthroughs.

### P2 — Blackthorn Flail tutor needs the game's misleading label beside it

The ROM really teaches Flail: file 944 uses `SetMonMove …,175` at 3461 and 3619, while the translated dialogue repeatedly says Play Rough. The generated tutor row correctly says Flail but does not explain how to recognize that NPC or link the known issue. A player searching the offered name will not find that row. This is a documentation crossreference issue, **not a request to fix the hack** (D-1337).

**Shortest improvement:** annotate “Flail (NPC calls it Play Rough)” with a link to the Blackthorn guide/known issue. Preserve actual move 175 in compatibility data.

### P2 — Extraction coverage is stated as proven availability

`work/docs/README.md:60` calls 770 species “obtainable in game”; `work/notes/docs_crossref.md:261` says the other 255 cannot be obtained except externally/with cheats. Yet README's coverage explicitly excludes Safari object areas, roamers and other systems. `gen_docs.py:availability` seeds from script records and then adds evolution and breeding closure without establishing all event/map reachability, evolution item/condition availability, or breeding prerequisites. `static_mons` and `trade_places` scan commands, not full runtime routes.

This review found **no specific newly disproven trade**: all 13 trade/loan records have a script command and an attached object/coordinate entry in the reviewed map-event data. That establishes attachment, not that every starter/story state reaches every trade. Do not report a dead trade based only on parser concerns.

**Shortest improvement:** change the summary to “770 species with an identified source or inferred evolution/breeding route”; say “no source found by this audit” for the other 255. Keep omissions adjacent. Mark runtime-unverified sources rather than deriving certainty from a nonempty string. Treat unknown evolution methods 34–41 as unresolved requirements, as the existing reference README already does. This also corrects the About page's claim that extracting data “makes it exact”.

### P2 — Public documentation links to ignored local-only material

`work/docs/README.md:49` links to `author_notes/README.md`, which `.gitignore` explicitly excludes as maintainer-local material. That link is unsuitable as an ordinary public documentation destination. The page also references `work/notes/spreadsheet_crossref.md`, which is not ignored; its publication status was not established. This checkout has no tracked files, so an empty `git ls-files` result cannot establish what the published repository contains. The existing site link check does not cover these Markdown destinations.

**Shortest improvement:** remove the public link or label it as maintainer-local material and offer a committed summary that does not reproduce third-party text. Do not force-add ignored author spreadsheets/translations to solve navigation. Extend documentation link checks to tracked-file availability, distinct from website-only checks.

### P3 — Keep player references concise and contributor entry points direct

Root README has clear patch prerequisites, CRC/SHA-1, no-ROM policy and a direct quest guide link. CONTRIBUTING clearly distinguishes text edits and optional builds. No external patcher, release or emulator claim was independently checked online in this local review. The About page's release step should link directly to Releases rather than telling players to find the GitHub icon. Reference README's page index leads with file sizes; short purpose labels are more useful for players, with extraction format details retained below for maintainers.

The website abbreviations (for example DazzlngGleam and ScorchSands) match the game's name banks, so they are not translation errors. Search aliases/full-name hints would improve findability without replacing the names players see in game. Sorting table headers currently receive click handlers but no keyboard-focusable button; use actual header buttons for keyboard access. These are lower priority than missing conditions and misleading filtering.

## Independent checks and coverage

Read the untouched Chinese ROM directly with ndspy into memory, bypassing the cached reader for the primary byte samples; no ROM copy/build was produced. Compared representative raw records with committed site JSON:

- **Species:** IDs 1, 25, 133, 493, 1025, 1026 and 1440; base stats and types matched, including Pikachu's hack-specific 40/60/50/60/50/110 and alternate-form records.
- **Moves:** IDs 1, 85, 175, 605 and 920; type/category/power/accuracy/PP matched, including Flail's variable-power sentinel.
- **Items:** IDs 1, 4, 17, 328, 373 and 574; raw prices matched. TM46 Thief correctly has no exported source.
- **Trainers:** IDs 1, 16, 100, 500 and 1023; representative raw first-party species/level/item/move records matched the exported teams. This exposed the separate IV presentation error; this was not a full battle AI or every-party-member validation.
- **Encounters:** fresh records 111 (Route 1), 137 (Viridian Forest), and 65 (Blackthorn City). Morning land-slot species/weights matched for the first two; Blackthorn surf raw slots support Magikarp 99% / Horsea 1% and the displayed level spans. Map association used the existing bank_maps mapping; map headers were not independently reverse-engineered anew.
- **Trades/loans:** all 13 records' requested/received species and command references inspected, with attached map object/coordinate entries checked. This does not prove all branch predicates or visibility flags are reachable. Poliwag/Poliwhirl gift-event reachability was not traced in this pass.
- **Tutors:** independently confirmed Blackthorn's move 175 and dialogue mismatch. Export has no duplicate tutor move IDs at this snapshot. Did not independently verify all 85 move lists or every payment branch.
- Read generated-doc headers/limits, availability and relevant export/template logic, navigation/filter code, README/CONTRIBUTING/site README/About and CI publication inputs. Did not read every generated row.

## Freshness and link checks

Final read-only checks, approximately 10:48 UTC:

- `python3 work/tools/docs/gen_docs.py --check`: **18 pages, 0 changed**.
- `python3 work/tools/site/export_data.py --check`: **7 data files, 0 changed**.
- `python3 work/tools/site/sync_guide.py --check`: **15 guide pages, 15 changed** after concurrent source-guide edits. Regenerate after edits settle; this is not evidence that generated data is inaccurate.
- `python3 work/tools/site/check_site.py`: **2,371 pages, 221,944 links, 0 broken** against the pre-existing `site/dist`. No site build was run, so this does **not** validate the changed source guide or missing semantic crossreferences.

No emulator/browser interaction, downloads, new decisions, exhaustive source availability proof or new game-data exports were performed. Existing chapter 13/known-issues source-folding improvements were not reported as unfixed defects.
