# Archived Chinese source review: generated reference sections

Reviewed 2026-10-04. Findings only; no documentation, guide, generator, ROM, bank or decision changes. Paths below are repository-relative; `A/` abbreviates `work/research/chinese_sources/2026-10-04/`.

## Evidence and coverage

Reviewed current README, items, encounter tables, Pokémon/form pages, moves, trades/tutors and trainer documentation against the preserved release announcement/history, public comments, and ten legacy item/species/tutor articles. Inspected existing cross-reference and graphics notes for corroboration. This is targeted external-evidence review, not a fresh full-ROM extraction or runtime audit. Video descriptions/titles are leads only; footage was not downloaded. Guide images were not exhaustively inspected.

Primary release evidence is **A/search-0.txt:219–281**, the indexed body of [Alex’s 4.0 announcement](https://tiebac.baidu.com/p/10981775037?fr=good), dated August 29, 2026 in the author profile. **A/search-0.txt:130** preserves the September 5 4.02 typing excerpt from [Alex’s profile](https://youhua.baidu.com/home/main?lp=home_follow_main&un=chendelpiero). Direct Tieba captures failed; indexed evidence can be stale or incomplete. The convenient search-extracts.txt does not contain these complete passages. Author intent for 4.0 is not proof of this 4.0.3 binary’s behavior.

## Items

### REF-01 — unsupported “not in the game” classification

**Known, still open; high confidence in documentation defect.** `work/docs/items.md:181` still labels Chain Logger, EV Allocator, the four charms and many other items “not in the game” merely because script sources were not found. `work/notes/docs_crossref.md:87` repeats the dead-data classification. The release announcement (A/search-0.txt:258,262–266) describes initialization/starter grants and mother’s savings rewards. `work/notes/graphics_layout_audit.md:25` documents opening Chain Logger in the bag in a local runtime test; this proves functioning content, not its normal acquisition path. Existing research already records this issue (`work/notes/chinese_sources_review_2026-10-04.md`).

Future action: change the generator’s absence wording to an extraction limit and separately trace engine initialization/reward mechanisms. Do not declare the whole list obtainable. Preserve individual item uncertainty.

### REF-02 — legacy Heart Scale exchange directions are reversed relative to current tables

**New source conflict; high confidence in mismatch, no demonstrated docs defect.** The July 1, 2023 [Heart Scale article](https://www.9game.cn/news/8299427.html), A/pages/583d0e08a26e3011/text.txt (article body), puts the scale exchange at the fishing-rod house and the pearl exchange in Lavender’s church. Current `work/docs/items.md:2155` instead has Lavender House Of Memories giving Heart Scale for Big Pearl; `:2196–2198` has the Route 12 Fishing Brother house giving Big Pearls for Net Balls. This is a concrete reason not to import legacy directions. Future action: script-verify those two exchange directions before reusing the old guide; retain current tables meanwhile.

### REF-03 — legacy Life Orb / Shiny Stone acquisition need version checks

**Leads; low external confidence.** July 2023 [Life Orb article](https://www.9game.cn/news/8298943.html), A/pages/2228a27efa5c23df/text.txt, claims an item ball east of Cerulean absent for Pikachu starters. Current items table’s Life Orb occurrence is the Route 32 Pokémon Center gift (`work/docs/items.md:1519`), not that ball. [Shiny Stone article](https://www.9game.cn/news/8299299.html), A/pages/2c34b2aeb3f1313d/text.txt, claims a Safari object/day-dependent Roselia held-item route. README explicitly excludes Safari object areas, so this second case is a coverage lead rather than a contradiction. Future action: trace the claimed ball’s current item/branch and Safari/held-item data before adding routes; do not copy the exact legacy requirements as current.

**No-action corroboration:** legacy Magnet locations broadly agree with items.md:1339/1352; Amulet Coin sources with :1318/1591; Hard Stone exchange with :2108; Viridian Exp. Share with :1286. Sources respectively A/pages/32bfae4e0c8a46cf,7445464f8da6b32a,567980774ccb3014,6eda487f8ffefcd8/text.txt, original URLs linked in A/README.md. Their 2023 dates and incomplete conditions prevent stronger validation claims.

## Pokémon species and forms

### REF-04 — held-item form acquisition missing from generated source summaries

**New documentation coverage lead; high confidence in missing explanation, medium in 4.0 intent.** `work/docs/pokemon_1026-1440.md:52,87` (Mega Charizard X/Y), heading #1194 Ash-Greninja, and `:13846` (Armored Mewtwo) say no source found. Release items 8/18/25 describe held-item transformations; Charizard’s Y selection is stated as Modest/Timid, otherwise X. Current item sources exist: items.md:525 Steel Armor, :1675 Ninja Scroll, :2208/:2407 Charizardite. `work/notes/spreadsheet_crossref.md:154` already acknowledges runtime/held-item forms; :235 identifies Steel Armor’s purpose.

Future action: audit runtime form-change hooks and item IDs, then add distinct form-acquisition support and links. Do not turn these into ordinary evolutions, assume all Mega forms work, or publish the nature rule as binary-verified yet.

### REF-05 — Serperior and Staraptor corroborated, Servine not covered

**Known; high confidence in agreement.** The 4.02 excerpt explicitly supports the existing Fighting/Flying Staraptor and Grass/Dragon Serperior rows (`work/docs/pokemon.md:421,520`). `work/notes/sheet_mismatch_verification.md:135` still groups Servine/Serperior as undetermined. Future action: attach the author provenance to Serperior’s stale-sheet explanation only; leave Servine unresolved. No typing edits needed.

**No-action:** Crystal Onix’s new static encounter is author-confirmed intent and already represented at `work/docs/pokemon_1026-1440.md:13802` (Lv40 Island Cave). The announcement does not itself confirm the level/location. The legacy Togepi article explicitly admits the author did not hatch the egg, so it is inadequate proof of any omitted current gift.

## Encounters

### REF-06 — current Route 31 table rejects commenter’s Ralts advice

**New source conflict; high confidence in table mismatch, low comment confidence.** A/comments.md comment 316446552784 on [v4 stream](https://www.bilibili.com/video/BV1Mx8S6eEL8/) claims Ralts through Route 31 Hoenn radio. Current encounters.md Route 31 section (`:4487`) lists Whismur/Linoone; species page `pokemon_0252-0386.md:1018` also lacks Route 31. Future action: retain parsed tables, optionally inspect radio hooks/runtime to exclude custom replacement logic. Do not import vanilla advice from a commenter. The uploader’s separate reply confirms the stream as 4.0.3, not each comment or episode.

### REF-07 — encounter probability presentation needs an overworld/date scope caveat

**New coverage lead; medium confidence.** `work/docs/encounters.md:5–7` explains table probabilities and encounter rates without distinguishing overworld spawns. Release item 21 describes six overworld spawns, reduced random encounters while present, repels and shiny retention; item 23 describes date-specific mythical encounters. README’s Method and limits lists other omissions but not these systems. Future action: audit engine spawn/calendar hooks and clarify which methods use the published table probabilities. Do not assume these systems invalidate the tables, invent dates, or change availability counts from the announcement’s “777”.

**No-action corroboration:** legacy Route 12 Super Rod Feebas advice agrees with encounters.md:2229. Radio availability remains explicitly unverified; preserve that caveat.

## Moves and trades/tutors

### REF-08 — legacy Metal Claw values are stale; free lesson remains a lead

**New source conflict; high confidence in numerical mismatch.** June 27, 2023 [Metal Claw article](https://www.9game.cn/news/8280029.html), A/pages/6e0f419ea9321cd5/text.txt, calls the move 50 power and says a Charmander free lesson is unconfirmed. Current moves.md:240 gives 60 power, while trades_tutors.md:37 agrees with its Level Ball cost and Pewter location. Future action: retain current move data and trace the tutor’s starter/free-use branch only if documenting exceptions. Do not import the old move evaluation or upgrade its admitted rumor into fact.

No additional validated move/trade correction found. Tutor-video titles provide a route checklist but no exact cost, compatibility or move evidence without footage.

## Trainers and README

### REF-09 — author’s EV/team changes corroborate scope, not individual teams

**Lead / no correction; medium confidence in stated intent.** Release item 3 mentions redesigned teams and late trainers’ allocated EVs; trainers.md:9 already explains per-stat EVs. A/comments.md 317034343712 criticizes early-generation teams and 317035302048 discusses planned changes. These are not replacement team specifications. Future action: preserve ROM-derived teams; record future release comparisons separately. Neither blanket “unchanged from 3.0” nor “every trainer modernized” is warranted.

README already distinguishes 1,440 represented species/forms from 771 national species with found/inferred sources and warns about runtime values. The release’s 777 dex count is not directly comparable. Future revision should explicitly list runtime item grants, held-item form transformations and calendar/overworld systems among coverage gaps, pending the audits above.

## Priorities

1. REF-01: correct unsupported absence classification when edits are authorized.
2. REF-04 and REF-07: verify runtime form and encounter coverage gaps.
3. REF-05: strengthen existing provenance without changing correct values.
4. REF-02/03/06/08: retain as source conflicts/test leads; no current documentation correction justified solely by them.

All findings are review proposals. Nothing was added to the decision register or changed in reviewed resources.
