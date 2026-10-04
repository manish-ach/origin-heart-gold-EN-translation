# Chinese-source review of our guides and reference docs

2026-10-04. **Findings only: no guide, generated reference, translation, game, or tool edits.** Four section subagents reviewed chapters 01–06, chapters 07–12, reference docs, and archived images; the coordinator reviewed common mechanics/chapter 13 and consolidated their results.

The strongest new actionable guide omission is the repeatable Lavender Big Pearl → Heart Scale trade. Existing documentation also overstates what “no extracted source” proves about key-item availability. Several useful mechanics explanations are missing from the player-facing guide, although that guide explicitly focuses on quests. Most conflicting external advice is obsolete, unversioned, or weaker than our current Chinese-ROM evidence.

## Section reports — complete findings and evidence

| Review | Report | Coverage |
|---|---|---|
| Kanto and Sevii | [Chapters 01–06](chinese_source_review_guide_01_06.md) | K01–K05; chapter-by-chapter coverage; targeted original-ROM script checks and 11 screenshot inspections |
| Johto and late game | [Chapters 07–12](chinese_source_review_guide_07_12.md) | GJ-01–08; Gym/romance conflicts, password and weekday corroboration, limits by chapter |
| Reference documentation | [Items, Pokémon, encounters, moves, tutors, trainers, README](chinese_source_review_reference_docs.md) | REF-01–09; current tables versus archived articles and author statements |
| Visual evidence | [Archived screenshots](chinese_source_review_visual_evidence.md) | V01–05; all 62 saved images triaged, six opened full-size, unsupported infographic claim isolated |
| Common mechanics and evidence quality | [Chapter 13, known issues, mechanics, archive defect](chinese_source_review_common.md) | COM-01–05 and ARCH-01; existing runtime research checked against release claims |

These reports contain **33 labelled entries**, including overlaps, corroborations and rejected source claims. They are not 33 documentation bugs. The register below deduplicates the main future actions; retain the section reports for all observations and exact local/source references.

## Prioritized findings register

| Priority | Finding / current status | Evidence and future action |
|---|---|---|
| 1 | **Missing Lavender Heart Scale trade** — confirmed new guide omission | K01 / REF-02. Original CN script 772 takes one Big Pearl and gives one Heart Scale, repeatably. Reference items already places it at House of Memories. Add a future guide entry and connect Route 12 Net Balls → Big Pearls to Saffron relearning. The legacy article reverses the locations and must not supply directions. |
| 1 | **“Not in the game” is stronger than the extraction proves** — known reference limitation, newly corroborated | REF-01. Items without script sources include engine-managed v4 tools/charms; the author advertises automatic grants and a local test opened Chain Logger. Future wording should distinguish “no extracted source” from proven unavailability, then trace normal grants. Not every listed key item is thereby proven obtainable. |
| 1 | **Romance moving-in contradiction needs runtime adjudication** — new external lead, not a proven guide error | GJ-01 / K05. Author claims romance fixes; a modern comment describes wrong partners in home scenes, whereas our static analysis suggests a universal block. Version/save/path are unspecified. Prioritize clean CN v4.0.3 reproduction with gender, partner, starter and flag 106 recorded. Preserve current caveats until resolved. |
| 2 | **Automatic EXP/EV sharing lacks a player explanation** — verified local mechanics, optional broader-guide coverage | COM-02 / REF-09. Existing original-ROM code and controlled runtime tests support automatic sharing. Reject the video description's native-toggle claim. Document tested behavior and scope; this review proposes no optional code patch. |
| 2 | **Held-item forms are not ordinary encounter/evolution sources** — reference coverage lead | REF-04. Author describes Charizard nature-dependent Mega form, Ninja Scroll Greninja and armored Mewtwo; current “no source” summaries omit runtime transformations. Trace the hooks before adding exact activation instructions. |
| 2 | **HM-free intent should be separated from runtime uncertainty** — known behavior, stronger primary-source intent evidence | COM-01 / GJ-07. Chapter 13 and known issues still call intent only possible. Alex explicitly advertises the feature. Future wording can clarify intent while preserving party-menu exceptions and untested per-path behavior. |
| 2 | **Fossil purchase lacks restoration follow-up** — confirmed missing explanation, partially verified destination | K02. Museum interaction and legacy source support the next step; trace standard-script story/party-space/return gates before writing a full walkthrough. Current $5,000 price is correct. |
| 2 | **Chain Logger, IV/EV controls and EV Allocator need player coverage** — mixed verified controls and source-only rules | COM-03 / REF-01. Reuse tested L/B summary controls. Verify normal tool grants and chain rules. Source UI labels overlap at chain count 10; do not silently choose a threshold. |
| 2 | **Overworld encounter and shiny persistence scope is missing** — author-backed coverage lead | COM-04 / REF-07. Existing tables do not explain visible spawns, temporary shiny retention or special-date hooks. Verify these systems; no calendar/species/date should be invented from the announcement. |
| 3 | **Pickup, held-item restoration, breeding and battle-information changes** — source-backed coverage leads | COM-05. Useful v4 mechanics are absent from the quest guide, but exceptions and behavior still need checks. Do not expand faithfully translated source descriptions to compensate. |
| 3 | **Life Orb, Safari Shiny Stone and free Metal Claw lesson** — unresolved legacy leads | REF-03/08 and chapter 01–06 other leads. Check current scripts/runtime/Safari object data before publishing routes or exceptions. Legacy age and explicit rumor wording weaken these claims. |
| 2 (research infrastructure) | **Derived search index omits release evidence** — confirmed archive defect | ARCH-01. Raw search snapshots retain the announcement; `search-extracts.txt` drops leading-newline blocks. A later archive-only indexing fix should normalize before testing titles and verify inclusion. No tool fix made in this review. |

## Conflicting advice to keep out of our resources

- **Cinnabar Egg → Togepi:** rejected. Current original-ROM GiveEgg uses species 252, Treecko (K03).
- **Gloom auction requires $100,000:** rejected as replacement guidance. Current guide gives the more precise $65,535 check, $50,000 payment and alternative route (K04).
- **Legacy Gym rules:** Falkner three rather than up to four; Morty 3v3 rather than six-member gate; Jasmine Defense above 100 rather than current 130+ wording/species-list enforcement. Preserve the current version-specific evidence (GJ-02–04).
- **Yellow berry reward Iapapa equals Lum:** reject the infographic's alleged correction. Current guide distinguishes Yellow Iapapa and Green Lum; underlying effect/version remains untested (V01).
- **Route 31 Hoenn radio gives Ralts:** unsupported by current tables, which list Whismur/Linoone (REF-06).
- **Metal Claw power 50:** legacy advice conflicts with current extracted power 60. Normal tutor Level Ball cost remains supported (REF-08).
- **EXP-sharing toggle and universal HM-mule advice:** rejected as current instructions; see COM-01/02 and GJ-07.
- **Author's romance fixes mean all warnings can be removed:** unsupported. Broad release wording does not resolve particular original-ROM paths (K05/GJ-01).

## Useful corroboration without a correction

- Boot Camp password **14246** appears directly in modern episode metadata (GJ-05).
- Lake trio **Wednesday** agrees with a legacy comment; numeric shortcut 31224 is not yet checked against current menu order (GJ-06).
- Celadon password colour/order clues, fossil price, day/night boundaries, and part of qualifier progression have visual support (V02–05).
- Staraptor Flying/Fighting and Serperior Grass/Dragon are corroborated by the author's 4.02 text. It does **not** corroborate Servine (REF-05).
- Murkrow's coin reward, several early gifts and existing route instructions are already documented; previous applied guide corrections were not counted again.

## Evidence limits and preservation

Sources are preserved in the ignored local archive at `work/research/chinese_sources/2026-10-04/`; its [tracked pointer note](chinese_sources_archive.md) describes access and provenance. Reports link original URLs and distinguish the author's v4 announcements, modern self-reported playthrough version, legacy articles, and anonymous comments. Syndicated copies and repeated decorative images are not independent confirmation.

Video metadata/descriptions/comments were examined, **not full footage or transcripts**. Public comment capture is incomplete; blocked Tencent/Tieba/private material supplies no hidden evidence. Most images do not identify a precise build. Detailed map flags, every trainer team and all known issues were not freshly re-tested. Targeted script checks and prior runtime results are identified individually. No finding licenses changing original hack behavior.

A pre-review SHA-256 baseline covers all 32 Markdown files under `guide/` and `work/docs/`. Final comparison: **32 of 32 unchanged; no added or removed Markdown files in those directories**. Only findings reports were written during this review. No build or translation QA was required for this research-only task.
