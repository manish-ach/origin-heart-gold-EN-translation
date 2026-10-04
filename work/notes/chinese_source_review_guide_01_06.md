# Archived Chinese-source review: guide chapters 01–06

Date: 2026-10-04. Findings only; no guide, generated documentation, translation, tool or decision-register changes.

## Scope and evidence limits

Compared the current chapter contents and headings with relevant archived article bodies, screenshots, release extracts, video descriptions and comments under `work/research/chinese_sources/2026-10-04/` (abbreviated **A/** below). Reviewed prior `guide_review_2026-10-04_part1.md` and `part2.md` to avoid reopening applied corrections. This is a source-driven review across six chapters, not a fresh line-by-line proof of every script, trainer party or map coordinate. No video footage was available or inspected. Read-only checks with `scriptdump.py` used the untouched Chinese v4.0.3 ROM for the specific claims below.

The 2023 item articles are legacy material, usually with no precise version. Several are duplicated syndicated text, not independent confirmations. The general download-site walkthrough labelled v3.0 also mixes descriptive claims and advertising. Screenshots in Togepi, Hard Stone and Amulet Coin articles proved to be generic title screens, not evidence for their item claims. A recent page date does not establish v4 content.

## Findings requiring a future guide addition

### K01 — Repeatable Heart Scale route is missing from the guide

- **Status:** new confirmed coverage gap; existing item reference is correct. **Confidence:** high for the trade; normal map accessibility was not re-tested.
- **Locations:** `guide/03-vermilion-to-celadon.md:347`, “Route 10 / Lavender Town: the girl who waits”; `guide/04-celadon-fuchsia-saffron.md:481`, “Route 12: the Fishing Guru's Super Rod”; `guide/05-saffron-cinnabar.md:157`, “Saffron City: small extras”.
- **Issue:** chapter 4 explains repeatable Net Balls → Big Pearls, and chapter 5 explains spending Heart Scales on move relearning, but the guide has no Lavender House of Memories Big Pearl → Heart Scale entry. This leaves the useful repeatable acquisition chain disconnected.
- **Chinese lead:** `A/pages/583d0e08a26e3011/text.txt`, [9game article 8299427](https://www.9game.cn/news/8299427.html), 2023 legacy/unversioned. Its body mentions the two trades but reverses the locations. Do not copy its directions.
- **Independent verification:** Chinese script file **772, script 4, @296–391** checks Big Pearl item 89, takes one at @358 and awards Heart Scale item 93 ×1 at @371–383. There is no one-time flag in that routine. `work/docs/items.md:2155` already records this at Lavender House of Memories. Route 12's current guide identifies script 200 and correctly states Net Balls → Big Pearls; `work/docs/items.md:2196` agrees.
- **Future action:** add a short Lavender trade entry and cross-link it from the Super Rod apprentice and Saffron relearner. Retain the existing correct Route 12 trade direction; do not replace it with the archived article's reversed instructions.

### K02 — Fossil buying instructions stop before explaining restoration

- **Status:** new guide completeness lead, partly corroborated; not a price or behavior correction. **Confidence:** high that the guide omits the destination; medium on a ready-to-publish restoration walkthrough pending its standard-script gates.
- **Location:** `guide/02-pewter-to-vermilion.md:156`, “Mt. Moon: the fossil seller”.
- **Issue:** the entry explains how to buy Helix/Dome Fossils repeatedly, but no chapter explains where to restore them. The Museum is already visited earlier, making this a useful next-step link.
- **Chinese source:** `A/pages/b7d527c536261643/text.txt`, [9game article 8279946](https://www.9game.cn/news/8279946.html), 2023 legacy/unversioned. Body directs buyers to Pewter Museum. Inspected `A/images/9164cea43c6a66eb.jpg`: actual fossil-seller screenshot, with both fossil menu choices. `A/images/2de8174b9d4efef3.png` is anime artwork and supplies no gameplay evidence.
- **Independent corroboration:** ROM script 753 contains the Museum fossil-information and extraction interaction (`@266` and external-message/extraction interaction around `@517–535`); script 133 separately confirms the current **$5,000** charge at @2149/@2175 and @2216/@2242. The guide price should remain as written.
- **Future action:** trace the Museum extraction standard script, required story state, leave-and-return behavior and party-space condition before adding a complete restoration entry. Do not carry over the article's unrelated Kabuto ability claim without a separate v4 check.

## Archived conflicts: retain current guide, do not import these claims

### K03 — The Cinnabar Egg is Treecko, not the article's tentative Togepi

- **Status:** resolved external-source conflict. **Confidence:** high.
- **Location:** `guide/05-saffron-cinnabar.md:264`, “Cinnabar Island: the Egg in the lava”.
- **Source:** `A/pages/3748b1abdbe2c819/text.txt`, [9game article 8305779](https://www.9game.cn/news/8305779.html), and syndicated `A/pages/fd0a74722d62e621/text.txt`, [article 8307974](https://www.9game.cn/news/8307974.html), July 2023. The author says they have not hatched it and are repeating another person's result; this is explicitly weak evidence. Inspected `A/images/ae88017f8ffb7791.jpg`: only a generic Chinese HeartGold title screen.
- **Independent check:** v4.0.3 script 812 **@4613 `GiveEgg [252,14]`**, preceded by species 252 at @4605. Species 252 is Treecko, matching the guide.
- **Future action:** no guide correction. Keep this example in source-quality notes so searches do not reintroduce the Togepi claim.

### K04 — Legacy Gloom-auction money advice overstates the requirement

- **Status:** resolved external-source conflict; current guide already supplies the stronger detail. **Confidence:** high documentary confidence; the underlying auction script was not re-disassembled in this pass.
- **Location:** `guide/03-vermilion-to-celadon.md:507`, “Celadon City: the stolen Gloom”.
- **Source:** `A/pages/bf08e262248025e3/text.txt`, [Bulexiu walkthrough](https://www.bulexiu.com/yx/4660.html), version unspecified/legacy content despite a recent-looking page date. Item 8 tentatively recommends at least 100,000 cash. The same article still claims the traded Onix carries Metal Coat, contradicted by the archived 2023 Metal Coat article's explicit removal since 2.02.
- **Current local evidence:** the guide already explains the **$65,535** money check, **$50,000** later payment, and alternative eligible-Pokémon route; its cited script evidence is stronger than this tentative general walkthrough.
- **Future action:** retain the current instructions. Do not present this page as v4 authority or replace the amount with 100,000.

### K05 — A romance “fix” announcement does not invalidate documented remaining bugs

- **Status:** already-known issues with additional external corroboration; runtime check remains appropriate. **Confidence:** medium for corroboration, high that the sources cannot establish a universal fix.
- **Location:** `guide/01-pallet-to-pewter.md:366` and `:371`, “Romance route”, Mom visit and living together.
- **Source:** `A/search-0.txt:235`, [Alex's 4.0 announcement](https://tiebac.baidu.com/p/10981775037?fr=good), says romance bugs were fixed without naming all affected branches. `A/comments.md`, comment **314633041953**, on [BV1xNej6CEGE](https://www.bilibili.com/video/BV1xNej6CEGE/), reports female-player partner scenes switching characters at home and an earlier love-letter scene failing. The comment itself does not pin down a binary version or save state.
- **Independent local evidence:** current chapter already cites file 736's earlier flag-106 branch into Cynthia's scene and file 843's flag-106 early exit, and explicitly distinguishes static findings from unconfirmed runtime behavior.
- **Future action:** preserve the warnings. Use the comment to prioritize untouched-CN reproduction with recorded version, starter, player gender and partner; do not mark all romance bugs fixed from the release summary, or claim this comment independently reproduces the exact static path.

## Coverage by chapter and positive checks

| Chapter | Archived evidence actually examined and current-guide comparison | Result |
|---|---|---|
| 01 — Pallet–Pewter | v3-labelled Ddooo body (`A/pages/cedc7c9689321f7f/text.txt`, source: a software-download portal, link not kept) gives Mom's shoes, Daisy's map and all five Viridian quiz answers; those match current `01:34` and `01:52`. Legacy Hard Stone body (`A/pages/567980774ccb3014/text.txt`, [source](https://www.9game.cn/news/8303414.html)) broadly agrees with `01:312`; its inspected image is generic and cannot verify quantities. Romance evidence reviewed as K05. | Current quiz reward and corrected gift conditions are already present. No new contradiction from actual source content. Game-wide opening tools/automatic grants are coordinator-owned overlap, not counted again here. |
| 02 — Pewter–Vermilion | Fossil article and actual seller screenshot (K02); legacy Amulet Coin body (`A/pages/7445464f8da6b32a/text.txt`, [source](https://www.9game.cn/news/8298850.html)) agrees on bike lending but omits current Rainbow Badge timing. Inspected `images/7b8f04e9e60ab64c.jpg` is only a title screen. Legacy painter advice in Bulexiu describes returning later; current `02:108` correctly distinguishes the surviving wild Ralts from the lost living-painter gift. | K02 is a coverage lead; no new behavior correction. Keep current detailed timing rather than collapsing to legacy shorthand. |
| 03 — Vermilion–Celadon | Metal Coat article (`A/pages/c8d59b49a5558cf0/text.txt`, [source](https://www.9game.cn/news/8274957.html)) agrees with Scyther-side Metal Coat / other-side Electirizer at `03:253`; five reprints are not five independent checks. Password article (`A/pages/62ad69e6aeff3ee1/text.txt`, [source](https://www.9game.cn/news/8284061.html)) and inspected screenshots `images/382d76f19cb9235c.jpg`, `30d837f7a58868e2.jpg`, `c68d50fcfe426004.jpg` show accepted Persian-statue program, six colour digits and bottom-to-top/right-to-left order, matching `03:554`. The images do not verify the guide's weekday/hour table. Lavender trade checked directly (K01). | K01 new omission; K04 rejected legacy advice. Preserve the current password table pending any separate need to revalidate script 172. |
| 04 — Celadon–Fuchsia–Saffron | Route 12 exchange comparison in K01; legacy Shiny Stone article (`A/pages/2c34b2aeb3f1313d/text.txt`, [source](https://www.9game.cn/news/8299299.html)) suggests Safari Zone Roselia after block/time setup. This is not evidence against current `04:194`'s unreachable Cycling Road ball. No actual screenshot of that Safari process was available. | No confirmed new factual correction. Safari acquisition is a source-only lead for encounter/item reviewers, not a replacement for the ball warning. |
| 05 — Saffron–Cinnabar | Treecko checked directly (K03); Heart Scale relearner connected to missing trade (K01). Current Five Island trial ordering and late Latias fountain return were checked against prior review and are already corrected. | K03 resolves source conflict in favor of guide; no new required behavior correction. |
| 06 — Sevii–Indigo | Read current Elder quiz/trial, qualifier password instructions and pilgrimage headings against available source descriptions/comments. `A/comments.md` legacy-release comment 207879239856 asks for Elder quiz help but supplies no answers. The archived v4 playthrough episode list is useful navigation only; no footage/transcript substantiates those trials. | No new actionable source-based correction. Current removal of mandatory fake-password detour and trial-before-disciple ordering are already applied. Lack of detailed source coverage is not confirmation of every chapter claim. |

## Other leads, not ready for guide changes

- **Metal Claw tutor free lesson rumor:** [2023 article 8280029](https://www.9game.cn/news/8280029.html), `A/pages/6e0f419ea9321cd5/text.txt`, explicitly labels the Charmander-starter free lesson unconfirmed. Inspected `images/8fac74d35c9d551d.png` and `39604195701d2b57.png` show the Museum-side access and a tutor asking for one Level Ball; they do not establish a free branch. `work/docs/trades_tutors.md:37` agrees on the normal Level Ball price. Investigate the actual starter branch before adding any exception.
- **V4 footage for a later verification pass:** `A/videos.md` entry BV1Mx8S6eEL8 has detailed episode navigation. Uploader reply 317025190368 in `A/comments.md` says yes to a viewer asking if it is 4.0.3; this helps choose footage but does not prove every recorded episode uses that binary. No gameplay conclusion here depends on unseen footage.
- **Early v4 mechanics:** Alex's release body in `A/search-0.txt` describes starter-time EV Allocator, initial Chain Logger, party-wide EXP/EVs and savings-reward charms. Chapters 01–02 do not explain these; coordinator is consolidating this game-wide omission. Do not remove the correctly documented legacy Exp. Share quiz reward merely because party-wide EXP exists.

## Outcome

One confirmed guide omission (K01), one partly verified completeness lead (K02), two resolved external conflicts (K03–K04), and one already-known issue with additional corroboration (K05). No claim above authorizes modifying hack behavior. Only this findings note was added.
