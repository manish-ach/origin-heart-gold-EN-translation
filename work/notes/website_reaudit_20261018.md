# Website re-audit, 2026-10-18 (step 6)

Final check of the website programme on branch `website-fix-proposal` (steps 2–5: `fd2f5132` … `766b382e`), against
the first audit in `work/notes/website_audit_20261018.md` (W-001 … W-056). Step 6 fixed what it found
(`f9881b62` … `e244077d`, listed under "New findings").

## How this was measured

- **Builds.** Production (`GUIDE_SITE_URL=https://originheartgold.github.io GUIDE_BASE=/`, `--force`, 4,694 pages) and
  the tester preview (`GUIDE_PREVIEW=1 GUIDE_BASE=/preview/`), both after `sync_guide.py`. Served with
  `python3 -m http.server`; the CI `robots.txt` was added by hand. The in-browser patcher shows "isn't available"
  locally because `public/patch/` is only fetched in CI.
- **Every built page scripted:** title, description, canonical, robots, `h1`, Open Graph, JSON-LD (parsed), icons,
  manifest, theme-color, sitemap membership and `lastmod`.
- **Browser.** axe-core 4.12 (`wcag2a, wcag2aa, wcag21aa, wcag22aa`, through agent-browser) plus the step-4 DOM probe
  (contrast with gradients, 24 px targets with spacing, headings, landmarks, duplicate ids, ARIA, unlabelled controls,
  untagged Chinese, sideways overflow) on 23 page types — home, patch, FAQ, guide, chapter 3, Pokédex, Cyndaquil,
  locations, Azalea Town, items, Miracle Seed, moves, Protect, trainers, Giovanni, Team Builder, save editor, TMs,
  abilities, stat changes, changelog, about, 404 — at 1440 and 390 px, light and dark (92 runs). Keyboard: Tab order and
  focus rings on six page types at both widths, the phone Menu popover and the sidebar drawer (Tab in, Escape back to
  the button).
- **Repo checks:** `npm test` with `GUIDE_TEST_DIST=1`, `check_site.py`, the Python site tests, all ten Playwright
  browser scripts.
- **Old address.** `redirect_site.py` run on the production build, served by a small server that answers unknown paths
  under `/origin-heart-gold-EN-translation/` with that folder's `404.html` and status 404, the way GitHub Pages serves a
  project site.

Harness limits: axe timed out on `/pokemon/` (1,440 rows, 34,000 elements) in every run. The static scan and the DOM probe
cover that page instead. Real crawlers, the Rich Results Test and the GitHub Pages push could not be run locally.

## Scorecard

| Area | Before (first audit) | After | Evidence now |
|---|---|---|---|
| SEO metadata | 3/10: duplicated home title, 476 duplicate titles, no JSON-LD, sitemap with noindex pages and no `lastmod` | **9/10** | 0 duplicate titles and descriptions among self-canonical pages; JSON-LD on all 4,681 real pages; sitemap 4,471 URLs, all with `lastmod`, none noindex or non-canonical; 0 descriptions under 70 characters |
| Official signals | 2/10: never says "official", repo doesn't point to the site | **8/10** | Statement in the hero, patch page, footer, About, FAQ, JSON-LD and llms.txt; GitHub and Discord as project links; repo About still needs the user |
| AI discoverability | 1/10: no llms.txt, robots ignored | **9/10** | `/llms.txt` 13 KB (llmstxt.org format), `/llms-full.txt` 298 KB, root `robots.txt` with `Sitemap:` |
| Accessibility (WCAG 2.2 AA) | 6/10: contrast fails, prohibited ARIA, unnamed tables, 20 px targets | **9/10** | axe: 0 violations in 88 of 92 runs (the 4 others: the `/pokemon/` timeout); probe: 0 contrast failures; static scan: 0 problems on 4,681 pages; two keyboard and target issues fixed in step 6 |
| Design and UX | 6/10: no nav on home or phones, 404 showed the hero, cramped tables | **8.5/10** | Main nav on every page, phone Menu and drawer, real 404, trainer cards on phones, calmer home |
| Performance | 4/10: 512 px thumbnails (100+ MB per list page), 4.4 MB trainers page | **7.5/10** | Thumbnails: 1–2 KB sprites; `/trainers/` 0.91 MB; `/pokemon/` 1.56 MB; Protect 0.95 MB. Still heavy: `/reference-sources/` 3.1 MB, save editor JS 1.1 MB |
| Content clarity | 5/10: hero said nothing about English or a patch | **8.5/10** | H1 "Pokémon Origin HeartGold — English translation", release line, changelog, walkthrough wording |

## Status of every finding

Fixed = verified in the step-6 build. Commits are on `website-fix-proposal`.

| Id | Status | Evidence |
|---|---|---|
| W-001 home title | Fixed | `37663908`: "Pokémon Origin HeartGold English Patch & Guide", mirrored in `og:title` |
| W-002 title template | Fixed | `37663908`: "<page> · Origin HeartGold English", shortened past 60 characters. 7 chapter titles are still 66–76 characters because the chapter name alone is that long (low) |
| W-003 official statement | Fixed | `e38b7b0e`, wording `571b51e3`, `2fb79b62`, `3fcc2136` |
| W-004 repo homepage, description, topics | **Open (user)** | Repo settings; see "For the user" |
| W-005 release notes link | Fixed in tooling | `3ac8c6f3`: release.yml adds the website footer; RELEASING.md puts it in README.txt. Shows from the next release |
| W-006 social card | Fixed | `31bee276`, `571b51e3`: 1200×630 text-only card in Inter outlines, `og:image` and `twitter:image` with alt on every page |
| W-007 Open Graph | Fixed | `og:locale=en_US`, site name, light and dark `theme-color`, `og:type=website` on home. Section indexes stay `article` (negligible) |
| W-008 JSON-LD | Fixed | Organization + WebSite everywhere, WebPage + BreadcrumbList, VideoGame (version and date from releases.json) on home, patch and changelog, FAQPage. All 4,681 blocks parse |
| W-009 llms.txt | Fixed | `c4d9a7cf`; step 6 `d70e35d7` stops the preview's copies linking into `/preview/` |
| W-010 robots / host root | Fixed by the root move (option B) | `fd2f5132`, `37663908`: root `robots.txt` (allow all + `Sitemap:`), no `Disallow: /preview/`. Live once Pages is on for the user-site repo |
| W-011 Search Console / Bing | Code ready, **token open (user)** | Step 6 `e244077d`: Actions variables `GUIDE_GOOGLE_VERIFICATION` / `GUIDE_BING_VERIFICATION` become meta tags in production builds (tested with dummy values) |
| W-012 sitemap | Fixed | `37663908`: 4,471 URLs, none noindex or non-canonical, every URL has `lastmod` |
| W-013 legacy stubs | Fixed | Canonical to the target chapter, out of the sitemap, anchor mapping kept (an old `guide/pallet-to-pewter/#…` link lands on chapter 1 at the right anchor, also through the old address) |
| W-014 duplicate titles | Fixed | 0 duplicates among self-canonical indexable pages. 276 trainer records in 67 groups are canonical to their character's main record, and links inside the site point there (`d7c01ade`) |
| W-015 thin descriptions | Fixed | 0 under 70 characters (15 were cut at "Sp." / "S.S." until step 6 `67de3a89`). 3 run past 165 (FAQ 190, overworld abilities 189, save editor 166); guide descriptions from `sync_guide.py` end in "…" (low) |
| W-016 hero | Fixed | `e38b7b0e`, `2fb79b62`: H1, eyebrow, primary "Download the English patch", release line, dead frontmatter cleaned |
| W-017 changelog | Fixed | `c4d9a7cf`: `/changelog/` rc3–rc8 with contributors; `9929d5ab` adds it to RELEASING |
| W-018 "walkthrough" | Fixed | Guide index "Origin HeartGold walkthrough and quest guide", chapter descriptions, llms.txt |
| W-019 patch page | Fixed | Title "Download the English patch", official line, release line |
| W-020 breadcrumbs | Fixed | `nav[aria-label=Breadcrumb] > ol`, real section names, `aria-current="page"`, same list in JSON-LD |
| W-021 cosmetic forms | **Left (user decision)** | e.g. `alcremie-form-10` is still self-canonical |
| W-022 preview canonicals | Fixed | Preview canonicals and `og:url` point at production; step 6 does the same for its llms files |
| W-025 favicons and manifest | Fixed | `31bee276`: outlined SVG, ICO 16/32/48, PNG 48–512, maskable, apple-touch, manifest; the save editor uses the same set |
| W-026 official links | Fixed (GitHub, Discord) | Footer, About, FAQ, `social`, `sameAs`, llms.txt. Add other channels if the user wants |
| W-030 404 | Fixed | "Page not found", search, recovery links, `noindex, follow`, no canonical |
| W-031 contrast | Fixed | `c302dcd6`, `9efbfbe8`: 0 axe and 0 probe contrast failures in light and dark |
| W-032 table-scroll ARIA | Fixed | `7e0fb2b6` |
| W-033 table names | Fixed | `7e0fb2b6`: static scan finds 0 unnamed tables on 4,681 pages |
| W-034 save editor | Fixed, one part left | `9efbfbe8`: h1, site dress, SEO tags, shared theme key, no Google Fonts. Step 6 `7b653d4d`: a save can now be opened from the keyboard. Left: 1.1 MB JS bundle (269 KB gzip) |
| W-035 global nav | Fixed | `bac0ed08`: header nav from 78rem, Menu popover on home and 404, links at the top of the drawer, `aria-current` |
| W-036 ↗ on internal links | Fixed | `bac0ed08`; step 6 `c890b3ca` covers the Trainers hero and section cards (same-page anchors) and Team Builder's Pokédex link |
| W-037 phone tables | Fixed | `c302dcd6`: trainer teams and encounter lists stack as cards below 40rem |
| W-038 24 px targets | Fixed | `c302dcd6`, `f84bba1d`, `9f543b81`; step 6 `85c71479`: ability links in team tables and the Pokédex were 23 px |
| W-039 home entry points | Fixed | `2fb79b62` |
| W-040 in-game screenshots | **Left (user decision)** | — |
| W-050 thumbnails | Fixed | `d3c69cd0`: 96 px PokéAPI sprites with a fallback chain (artwork, official artwork, placeholder; `trainers-browser.mjs` blocks PokéAPI to test it) |
| W-051 big pages | Partly fixed | `5c2b37d7`: `/trainers/` 4.34 → 0.91 MB, 60,015 → 9,355 elements; `/pokemon/` 2.21 → 1.56 MB; learner tables use `content-visibility`. Left: `/reference-sources/` 3.1 MB, `/pokemon/` still about 34,000 elements |
| W-052 hero priority | Fixed | `fetchpriority=high` on Ho-Oh, lazy starters on phones, preconnect |
| W-053 search UI and CSS | Left as is | Starlight loads Pagefind's UI (94 KB) when the browser is idle; CSS not split per page. Acceptable |
| W-054 save editor fonts | Fixed | `9efbfbe8` |
| W-055 Pages caching | Info, unchangeable | `max-age=600` on GitHub Pages |
| W-056 local build docs | Fixed | `766b382e` |

## New findings from this re-audit

| # | Severity | Finding | Status |
|---|---|---|---|
| N-1 | High (WCAG 2.1.1) | Save editor: "Open save" and "Choose file" were `<label>`s for a `hidden` file input, so the keyboard couldn't reach them and a keyboard user couldn't load a save. This predates the programme | Fixed `7b653d4d`: real buttons that open the input. Playwright opens the file chooser with Enter. The static scan now flags a label for a hidden input |
| N-2 | Medium (WCAG 2.5.8, step-5 regression) | Ability links in trainer team tables and the Pokédex were 23 px tall, one per row (18 failing targets on Azalea Town, 1,578 on `/pokemon/`) | Fixed `85c71479` (24 px) |
| N-3 | Medium (SEO) | 15 descriptions were cut at an abbreviation: "Berserk (ability) in Origin HeartGold: Ups Sp. 3 Pokémon can have it.", "…board the S.S." | Fixed `67de3a89`, with a unit test and a built-site check |
| N-4 | Low (UX) | ↗ on same-page and same-site links: Trainers "Find a trainer", the nine section cards, Team Builder's "Pokédex" | Fixed `c890b3ca`; the scan now checks `#` links too |
| N-5 | Low (SEO hygiene) | The preview's `llms.txt` / `llms-full.txt` linked into `/preview/` 596 times; text files can't carry noindex | Fixed `d70e35d7`, with a test |
| N-6 | — | W-011 had no hook for verification tokens | Added `e244077d` |
| N-7 | Low (design) | Encounter-method and time hint buttons inside headings ("Headbutt trees: Azalea Town") lose the heading's bold weight and sit a little lower. This predates the programme | Open: `.ohg-hint` could inherit `font-weight` |
| N-8 | Low (design) | Home at 390 px: the release line wraps with a lone "· What's new" on the second line | Open |
| N-9 | Low (SEO) | The 13 legacy "Guide moved" stubs have no description, icons or theme-color (noindex redirect pages, harmless). 3 descriptions are over 165 characters; 7 chapter titles are over 65 | Open, cosmetic |
| N-10 | Info | The redirect site keeps `?query` and `#anchor` only with JavaScript; without it, the meta refresh lands on the page (or the home page for unknown paths) without them. Unavoidable on static hosting | By design |

The rest checked clean:
- Canonicals: production self-canonical, preview canonicals point at production, 404 has none.
- JSON-LD: one block per page, all parse.
- Titles: no duplicates among self-canonical pages.
- Keyboard: no focus traps. Every focused element shows a focus ring.
- Menus: the phone Menu and the drawer take Tab in order, close on Escape and return focus to their button.
- Overflow: no page scrolls sideways at 390 px.
- Trainer directory: its script (filters, paging, loading a team, no-JS links) passes. Sprite fallbacks work with PokéAPI blocked.
- Changelog and 404: render correctly in both themes.
- Robots and sitemap: correct.
- Social card and favicons: render.
- Old address: FAQ with `#anchor`, Cyndaquil, the home page, `moves/?type=…#move-table`, a made-up path, `/preview/`, a
  legacy guide anchor and a trainer record all land on the matching page at the root, with JavaScript. Non-HTML files
  (icons, the patch tool, Team Builder data) are copied, and `test_redirect_site.py` covers `patch/latest.json` and the `.xdelta`.

## The four browser checks that failed on old and new builds

All four had stale expectations. None was a site bug, and no data was changed. Fixed in `f9881b62`.

1. **browser-smoke, "Scald retained among combined filters".** Scald is new in the hack: its `originalComparison` has no
   HeartGold baseline, so `playerMoveChanges` is empty and `changed=yes` leaves it out. The data was already like that
   when the check was written (`d09ffd7d`). The check now asserts that every row shown matches all four filters, and
   that Scald is left out. Whether moves new to the hack should count as "Changes in this hack" is a product question
   for the user. The data export decides it.
2. **browser-smoke, items/qualot-berry and items/tamato-berry ("Saffron").** The v3 "Saffron City shop" note is
   deliberately hidden for these items (`ItemReferenceNotes.astro` excludes ids 171 and 174; no v4 seller). The pages
   name the Battle Frontier Scratch-Off Cards. The check now expects "Battle Frontier" and no "Saffron".
3. **player-reference-browser and review-fixes-browser, Ursaring evolution.** The page says "holding Moon Stone at
   night (20:00–3:59)". "night" is a time-hint button, so Playwright's `innerText` breaks the line around it. The
   checks now collapse whitespace. Not an evolution-data problem.
4. **encounter-rates-browser, "Pikachu starter:.*Cascade Badge".** The acquisition text reads "Pikachu starter only.
   After the Cascade Badge…" since `744da168`, which updated team-builder-browser but not this script. The next line
   ("Grass/cave, day") had the same hint-button line break. Both regexes are updated.

## Test results (final production build)

- `npm test` (`GUIDE_TEST_DIST=1`): **200 tests, 200 pass, 0 fail.** On the `/preview/` build: 200 tests, 199 pass,
  1 skipped (the SEO test skips on an all-noindex build), 0 fail.
- `check_site.py --base /`: 4,694 pages, 914,933 links, **0 broken**. Preview: 919,613 links, 0 broken.
- Python site tests: **70 OK**.
- Browser scripts, all passing:

  | Script | Result |
  |---|---|
  | browser-smoke | 222 assertions, 52 mobile checks |
  | player-reference-browser | 402 assertions |
  | review-fixes-browser | 120 assertions |
  | encounter-rates-browser | pass |
  | trainers-browser | 46 assertions |
  | mobile-menu-browser | 4 scenarios |
  | quest-filters-browser | pass |
  | pickup-browser | pass |
  | team-builder-browser | 95 checks |
  | team-builder-calc-browser | 82 checks |

## For the user

1. **Merge and turn on Pages for the user-site repo:** `originheartgold/originheartgold.github.io` → Settings → Pages →
   Deploy from a branch, `main`, `/ (root)`. Then rerun the Website workflow and verify (checklist in
   `work/notes/root_site_move.md`).
2. **Repo About (W-004):** Website `https://originheartgold.github.io/`; a description such as "English translation
   patch for Pokémon Origin HeartGold (起源心金) v4.0.3, with an in-browser patcher, walkthrough and Pokédex"; topics.
3. **Search Console and Bing (W-011):** add `https://originheartgold.github.io/` as a URL-prefix property and choose
   the HTML-tag method. Put the tokens in the Actions variables `GUIDE_GOOGLE_VERIFICATION` / `GUIDE_BING_VERIFICATION`,
   rerun the workflow, verify, then submit `sitemap-index.xml`.
4. **Decisions still open:** cosmetic Pokémon forms canonical to the base form (W-021); in-game screenshots on home or
   patch (W-040); whether moves new to the hack count as "changes" in the Moves filter; any further official channels
   (W-026).
5. **Later work (not small):**
   - Split or paginate `/reference-sources/` (3.1 MB).
   - Thin the `/pokemon/` table (34,000 elements).
   - Code-split the save editor bundle (1.1 MB).
   - N-7 and N-8 polish.

## Ready to ship?

**Yes.** No blockers in the site. Every critical and high finding of the first audit is fixed or waiting only on a user
action (repo About, verification tokens). The two real problems this re-audit found (keyboard access to the save
editor, small ability targets) are fixed and covered by tests. Before announcing the address, the move still needs
the post-merge steps: Pages on for `originheartgold.github.io`, a workflow rerun, and the old-link checks in
`root_site_move.md`.
