# Guide editorial and cross reference review

Review date: 2026-10-04. This is a proposal, not a record of applied fixes. Gameplay findings are in the five part reviews. The existing guide and generated content were left unchanged.

## Baseline

- `python3 work/tools/site/build.py --check`: 18 documentation pages, seven site data files and 15 guide pages unchanged.
- `python3 work/tools/site/check_site.py --jargon`: the existing build contains 2,371 pages and 221,944 internal links, with zero broken links. This checks the existing build, not a newly rebuilt site or browser interactions.
- The numbered guide chapters contain 359 entries. Their 176 links to other numbered chapters include 169 chapter-only links and seven section links. Some chapter-only links are appropriate; references to a named quest should target its heading.
- The known-issues page accounts for all 726 detected developer-jargon matches outside folded sources: three coordinates, 79 flags, 27 variables, 275 script-file references, 283 line references, ten map identifiers and 49 decision identifiers. Matches are not a count of unique defects.
- Location matching does not resolve 29 of 359 headings. Some are intentionally game-wide entries; others are real location aliases, including Diglett's Cave, Dragon's Den, Pokémon Tower and Forest of Time. The part 5 review examines the consequences.

## Recommended changes

### Correct the evidence status before polishing prose

[The guide introduction](../../guide/README.md) originally said its account is exactly how the hack behaves (that wording was softened by a concurrent edit); [About](../../site/src/content/docs/about.md) says reading the data makes it exact. Static extraction can miss branch conditions, runtime checks and unreachable content. Replace both claims with: “Based on the hack’s scripts and data. Some steps still need in-game confirmation.” Keep uncertainty beside the affected step.

[The earlier errata](guide_errata.md) opens with an applied status, but the chapter reviews find corrections still absent. Replace the blanket status with an item-level pending/applied/rejected list and verify each applied item against current guide text. Historical audits such as [docs_review.md](docs_review.md) should clearly retain their dated scope, rather than imply their release counts remain current.

### Link to the action the player needs

For named prerequisites and continuations, replace chapter links with exact quest anchors. Keep chapter links for general browsing. Prioritize missable prerequisites, multi-region story chains, the romance route, field-move requirements and quest item sources.

Maintain one canonical explanation per mechanic or chain. Regional entries should give the local action and link to the canonical explanation. The romance introduction appears in chapter 1 alongside a much longer central explanation in chapter 9; conflicting timing is already a confirmed finding in part 1.

Keep detailed trainer teams, encounter tables and item-source lists in their reference pages. A quest should repeat only information that changes preparation or the decision at that step, such as a forced consecutive battle or an unusual party requirement. Link directly to the supporting record rather than making the player search a large table.

### Keep known issues useful to players

**Reconciled after concurrent edits:** the current Markdown now puts technical evidence in 194 Source blocks, with zero matches for the checked jargon patterns outside those blocks. The folding recommendation below has been implemented in source, although the generated site was stale at the intermediate check. The remaining recommendation is to prioritize actionable warnings and move harmless or unreachable content out of the player index.

[Known issues](../../guide/known-issues.md) mixes permanent-loss risks, cosmetic errors, harmless shared flags and unreachable scripts. Put actionable warnings beside their quest steps and retain a concise regional index of consequences and workarounds. Move implementation evidence to folded Technical source blocks, following [the site writing conventions](../../site/README.md). Keep unused content and harmless shared flags in the maintenance audit rather than the player warning list.

For example, the Pidgeot loan warning should explain that the returned Pokémon is a fixed level-20 Pidgeot rather than the one lent, and link to the loan quest. The trade-record number and script offsets belong in its source block. This preserves an important warning while removing implementation detail from the instructions.

### Use a short entry pattern without padding

Use only fields that help the specific quest:

1. Where and when, including prerequisites.
2. A prominent missable or permanent-loss warning where needed.
3. Numbered actions, with branch-specific instructions at the choice.
4. Reward, cost and whether it repeats.
5. Exact links to the prerequisite, continuation or supporting reference.
6. Folded technical evidence.

Do not impose a rigid word cap on complex puzzles. Shorten repeated explanations and unused-script commentary first. Preserve quantities, party restrictions, retry behavior and uncertainty.

### Reconcile introductory documentation

- **Resolved by a concurrent edit:** [README](../../README.md) now uses the rc4 patch filename, matching its status. No remaining correction for the old rc2 example.
- [Contribute](../../site/src/content/docs/contribute.md) offers a translation Discord without providing a destination. Add a verified project invitation if one exists, or remove that option. Do not invent a link.
- [The site home page](../../site/src/content/docs/index.mdx) promises every quest, Pokémon, item and trainer. Qualify coverage to match the extractor limitations and branch checks established in part 5.

## Acceptance criteria for a later edit pass

- Every consequential factual correction has a ROM script, map, data or runtime-code reference; inherited notes alone do not count as verification.
- Every named dependency links to its precise entry where an entry exists.
- Warnings appear before the irreversible choice and preserve starter, gender and story conditions.
- Player-facing known issues omit script jargon; evidence remains available to maintainers.
- Update handwritten guide sources and relevant generators, then regenerate their outputs. Do not hand-edit generated pages.
- Run the content freshness checks and check a fresh site build for links. Browser-test starter/gender filters and deep links separately; static link checks do not prove these behaviors.
- Keep untested runtime claims explicit. No guide review alone establishes full play-through validation.

## Concurrent guide edits

Guide files changed outside this review while the sequential checks were running. Chapter 13’s field-move, Clefairy-repeat and Unown Report corrections are now present; they are not pending findings here. An intermediate repeat of `site/build.py --check` found the 18 reference documents and seven data files current, but 12 of 15 generated guide pages stale. The earlier zero-broken-link result applies to the existing build, not those newer source edits. The final reference review found all 15 generated guide pages stale, while reference docs and data remained current. Use heading and script offsets to locate findings because document line numbers have shifted.
