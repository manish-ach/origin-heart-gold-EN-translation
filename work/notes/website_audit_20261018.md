# Website audit, 2026-10-18

Audit only, no code changed. Scope: the guide site in `site/` (Astro 7.3.5, Starlight 0.42.5) on branch
`website-fix-proposal` (off `website-fix`), the live site at
https://originheartgold.github.io/origin-heart-gold-EN-translation/ (production plus `/preview/`), and the copycat fansite
https://pokemonoriginheartgold.com/ (read only).

Goal: make the free GitHub Pages site clearly the best site for the game and clearly the **official** home of the
translation: SEO, discoverability (including LLM/AI search), accessibility, design, performance and UX.

## How this was measured

- **Local build with production URLs.** `python3 work/tools/site/sync_guide.py`, then in `site/`:
  `GUIDE_SITE_URL=https://originheartgold.github.io GUIDE_BASE=/origin-heart-gold-EN-translation/
  GUIDE_REPO_URL=https://github.com/originheartgold/origin-heart-gold-EN-translation npm run build`
  (4,693 pages, about 15 s). `dist/` was served under the real base path through a symlink
  `<scratch>/serve/origin-heart-gold-EN-translation -> site/dist` and `python3 -m http.server` on 127.0.0.1.
  Locally the in-browser patcher shows "isn't available" because `public/patch/` is only fetched in CI.
- **Every built page scripted.** A Python pass over `dist/**/*.html` collected title, description, canonical, robots,
  `h1` count, Open Graph and Twitter tags, JSON-LD and page size.
- **Browser review with agent-browser.** At 1440 and 390 px, in light and dark: axe-core (`wcag2a, wcag2aa, wcag21aa,
  wcag22aa`), a DOM probe (heading order, landmarks, alt text, image size attributes, horizontal overflow, targets under
  24 px, unlabelled controls, tables), keyboard Tab order and focus styles, screenshots, Pagefind queries and Web Vitals
  read from the Performance API on the live site.
- **Pages covered.** Home, Patch, FAQ, the guide overview, chapter 3, the Pokémon index, Cyndaquil, the Locations index,
  Azalea Town, the Items index, Miracle Seed, the Moves index, Protect, the Trainers index, Giovanni (record 244), Team
  Builder, Save editor, TMs, Abilities, Base stat changes and 404 (local and live).
- **Live endpoints checked with curl.** `robots.txt` at the host root and the project path, `llms.txt`, the sitemap,
  `latest.json`, response headers and the GitHub repo and release metadata (`gh api`, read only).

## What already works (keep it)

- `lang="en"`, a skip link, one `main` landmark, header, nav and footer on every Starlight page. The focus outline is a
  2 px solid accent on every focusable element tried (header, sidebar, hero and cards). No heading-level skips on the
  20 sampled pages, and no missing `alt` attributes (decorative art uses `alt=""` with `aria-hidden`).
- Images carry width and height, so CLS stays near 0: 0.001 to 0.002 measured live. No web fonts on the guide (system
  stack).
- No page scrolls sideways at 390 px. Wide tables are wrapped in `.table-scroll`, which scrolls on its own and gets
  focus and `role=region` once it overflows.
- Every page has a self-referencing canonical, except the 13 legacy redirect pages and the save editor (see below).
  `trailingSlash: always` is consistent, and GitHub Pages returns a real HTTP 404 for missing paths.
- Pagefind search works well: "surf" returns 737 hits topped by the Surf chapter and HM03, "ho-oh" and "hooh" both find
  Ho-Oh, "english patch" leads with Patch your game, and "melonDS", "dsi" and "r4" find the FAQ.
- The preview build has `noindex, nofollow`, a banner and no analytics. GoatCounter is cookie-free and loads only on the
  production origin.
- The Patch page is already better than anything the copycat offers. It patches in the browser and verifies CRC32 and
  SHA-1, while the copycat only links our release and suggests third-party patchers. **Make this the headline.**

## What the copycat does better (match or beat; don't copy its text)

pokemonoriginheartgold.com, observed 2026-10-18:

- **Keyword-first naming.** Its `<title>` is "Pokemon origin heartgold - English version", its H1 is "Pokemon Origin
  HeartGold" and its description says "English patch", "walkthrough", "Pokedex" and "Wiki". Only **3 of our 4,693
  titles contain "Pokémon"** and **none contains "English"**.
- **Download first.** A top navigation bar with **Download** highlighted (Download, Features, Walkthrough, Wiki, More:
  FAQ, Changelog, About), a primary "Get the English patch" button, and a release panel on the home page ("Current
  English patch v1.0.0-rc8 · Released 13 October 2026 · Read the changes").
- **Full metadata.** `og:image` (a 1200×630 social card) with `og:image:alt`, `twitter:image`, `og:type=website`,
  `og:locale=en_US`, `theme-color` and `site.webmanifest`.
- **JSON-LD.** WebSite, WebPage (with `dateModified`), VideoGame (version and creators) and BreadcrumbList, the last one
  even on its 404 page.
- **Root files.** `robots.txt` at the host root with a `Sitemap:` line, `sitemap.xml`, and a custom 404 page with
  `noindex,follow`. It has no `llms.txt` either: that is an opening for us.
- **Pages we lack.** Changelog, Known issues, Credits & sources, Privacy and Disclaimer pages in its own navigation.
- **Visuals.** A real in-game screenshot in the hero instead of Pokémon artwork, and a "Content reviewed <date>" line on
  the Download page.
- **It describes itself as independent**, "not affiliated with ... the game and translation teams", and links to our
  "Official RC8 release notes". We can be the obvious official source simply by saying so everywhere it counts.

---

## Findings

Severity: **critical** (hurts the official/SEO goal now), **high**, **medium**, **low**.
Items marked **[USER]** need a user decision before anyone implements them.

### Bucket A: SEO, official signals and discoverability files

**W-001: Home page title is duplicated and has no search terms**
- Area: SEO. Severity: critical. Page: `/`.
- Evidence: the title is `Origin HeartGold Guide | Origin HeartGold Guide`, because Starlight appends the site title to
  the page title `Origin HeartGold Guide` (`src/content/docs/index.mdx`). It has no "Pokémon", "English",
  "translation" or "patch".
- Fix: set the home `<title>` outright, without the suffix, from a Starlight route middleware (`src/routeData.ts`,
  registered with `routeMiddleware` in `astro.config.mjs`) that rewrites `head` for the index route. Suggested wording
  **[USER]**: "Pokémon Origin HeartGold in English: official translation patch and guide" (about 70 characters; a
  shorter variant is fine). Mirror it in `og:title`.

**W-002: Site name and title template leave out "Pokémon", "English" and "walkthrough"**
- Area: SEO. Severity: high. Pages: all 4,693.
- Evidence: the template is `<page> | Origin HeartGold Guide`. Pokémon pages read `#0155 Cyndaquil | Origin HeartGold
  Guide`, guide chapters `Chapter 3: … | Origin HeartGold Guide` (37 titles are over 60 characters, all chapters or long
  form names), moves `Protect | Origin HeartGold Guide`.
- Fix (route middleware, per section): the Pokédex becomes "Cyndaquil (#0155): location, moves, stats · Origin
  HeartGold", the guide "Chapter 3: Cerulean City… · Origin HeartGold walkthrough", moves "Protect (move) · Origin
  HeartGold". Keep each under about 60 characters by dropping the suffix when the page title is long.
- **[USER]** The brand string: keep "Origin HeartGold Guide", or use "Pokémon Origin HeartGold (English)"? It is the
  name that represents the project.

**W-003: The site never says it is the official home of the translation**
- Area: official signals. Severity: critical. Pages: home, about, patch, footer.
- Evidence: a search for "official site", "official home" and similar finds nothing in `src/content/docs`. The footer
  has only the Nintendo disclaimer, the header calls the site "THE ENGLISH PLAYER'S GUIDE", and the hero says "Your
  English companion".
- Fix:
  - Add a short official statement to the hero eyebrow or version line (`src/components/Hero.astro`), the footer
    (`src/components/Footer.astro`), the top of `about.mdx` and the Patch page.
  - Example wording **[USER]**: "The official website of the Origin HeartGold English translation. The patch is
    published only here and on our GitHub releases page." Optionally add: "Other sites that mirror or host the patch
    are not run by us." Don't name the copycat.
  - Also say it in JSON-LD (W-008) and `llms.txt` (W-009).

**W-004: The GitHub repo doesn't point to the site**
- Area: official signals / SEO. Severity: critical. Not a code change.
- Evidence (`gh api`): `homepage` is empty, `description` is just the URL `…/guide/`, and `topics` is `[]`. The repo
  ranks well and the copycat links to it, so this is the cheapest authority signal there is.
- Fix **[USER]** (repo settings):
  - Homepage: `https://originheartgold.github.io/origin-heart-gold-EN-translation/`.
  - Description, for example: "Official English translation patch for Pokémon Origin HeartGold (起源心金) v4.0.3, with
    an in-browser patcher, walkthrough and Pokédex."
  - Topics: `pokemon`, `rom-hack`, `translation`, `nds`, `heartgold`, `xdelta`, `english-patch`.

**W-005: Release notes and the release README don't link to the site**
- Area: official signals. Severity: high. Not a code change.
- Evidence: the rc8 release body has no `originheartgold.github.io` link. Its assets are `latest.json`, the `.xdelta`
  and `README.txt`.
- Fix **[USER]**: add an "Official website: <url> · Patch in your browser: <url>/patch/" line to the release notes
  template and to `README.txt`. The release process owns these; no generator was found under `work/tools`.

**W-006: No social card image**
- Area: SEO / social. Severity: high. Pages: all.
- Evidence: no `og:image` or `twitter:image` on any page, yet `twitter:card=summary_large_image`, so links shared on
  Discord, Reddit or X show no image. The copycat ships a 1200×630 card.
- Fix:
  - Add `site/public/og/default.png` (1200×630) and set `og:image`, `og:image:width`, `og:image:height`,
    `og:image:alt` and `twitter:image` from the route middleware.
  - Optional per-page cards: Pokémon pages can use their artwork URL, which is already used on the page.
- **[USER]** Graphics are sourced, never generated. What may the card show? Options: (a) text-only, in the site's
  colours and system font, like the OHG favicon; (b) a screenshot of our own English build (title screen or a first-hour
  scene, already the kind of image the guide uses); (c) the hero composition with PokéAPI artwork.

**W-007: Open Graph details are wrong**
- Area: SEO. Severity: medium. Pages: all.
- Evidence:
  - `og:type=article` on every page, including home and indexes.
  - `og:locale=en` (should be `en_US` or `en_GB`).
  - `og:site_name` is "Origin HeartGold Guide".
  - No `theme-color`.
- Fix: in the route middleware, set `og:type=website` for home and indexes, `og:locale=en_US` and the agreed brand
  (W-002). Add `<meta name="theme-color">` with light and dark values in the `head` array in `astro.config.mjs`.

**W-008: No structured data**
- Area: SEO / official signals. Severity: high. Pages: all.
- Evidence: 0 of 4,693 pages contain `application/ld+json`. The copycat ships WebSite, WebPage, VideoGame and
  BreadcrumbList.
- Fix: emit JSON-LD from the route middleware or a small `src/components/JsonLd.astro` added through the Head override:
  - **Every page:** `WebSite` (`name`, `alternateName` such as "Origin HeartGold English" and "起源心金 English patch",
    `url`, `inLanguage`, `publisher`) and `Organization` (name of the translation project, `url`, `logo` = PNG icon from
    W-025, `sameAs` = GitHub repo plus the official channels from W-026 **[USER]**).
  - **Every page with breadcrumbs:** `BreadcrumbList`, from the same data as `PageTitle.astro` (see W-020).
  - **`/patch/`:** `SoftwareApplication`:
    - `applicationCategory: GameApplication` and `operatingSystem: "Nintendo DS (emulator or hardware)"`.
    - `softwareVersion` and `datePublished` from `latest.json` at build time.
    - `offers.price: 0` and `downloadUrl`: the release page.
    - `isBasedOn`: a `VideoGame` "Pokémon HeartGold Version" plus the hack 起源心金 by 雁南飞TB and Alex (credits as in
      AGENTS.md).
  - **`/faq/`:** `FAQPage`. Google only shows FAQ rich results for authoritative government and health sites since 2023,
    so this is for Bing and LLM crawlers. Low priority within this item.
- Validate with the Rich Results Test after deploy.

**W-009: No `llms.txt`**
- Area: discoverability (LLM / AI search). Severity: high.
- Evidence: `/origin-heart-gold-EN-translation/llms.txt` returns 404. The copycat has none either.
- Fix: add an Astro endpoint `src/pages/llms.txt.ts`, which ships under the project path. Content:
  - The one-paragraph official statement and current version, from `latest.json`.
  - Where the patch is (`/patch/` and GitHub releases), with requirements (HeartGold USA, CRC32 C180A0E9).
  - Links to the FAQ, the guide overview, every chapter (with its summary), the Pokédex, locations, items, moves,
    trainers, Team Builder and save editor, plus the credits from AGENTS.md.
- Optional:
  - `llms-full.txt` with the FAQ and patch instructions in Markdown.
  - Per-chapter `.md` endpoints generated from the same sources.
- Respect the guide-text rules: no map ids, coordinates or flags. A true `/llms.txt` at the host root needs W-010
  option B.

**W-010: The project-path `robots.txt` is ignored**
- Area: SEO / discoverability. Severity: high.
- Evidence:
  - CI writes `site/dist/robots.txt` = `Disallow: /origin-heart-gold-EN-translation/preview/`
    (`.github/workflows/site.yml` line 229). Crawlers only read `https://originheartgold.github.io/robots.txt`, which is
    a 404, so everything is allowed and **no `Sitemap:` line is discoverable**.
  - `https://originheartgold.github.io/` itself is a GitHub 404, so anyone who trims the URL lands on an error page.
  - The `/preview/` noindex meta already works, so preview exclusion doesn't depend on robots.
- Option A, no new repo:
  - Leave the project `robots.txt` (harmless) and rely on `<meta name="robots" content="noindex">` for preview,
    redirect and 404 pages.
  - Submit `sitemap-index.xml` in Google Search Console and Bing Webmaster Tools as a URL-prefix property for
    `https://originheartgold.github.io/origin-heart-gold-EN-translation/`, verified by a meta tag (W-011).
  - Optionally ping IndexNow with a key file under the project path (keyLocation may sit in a subpath; it then covers
    only URLs under that path).
- Option B **[USER]**: create the free user-site repo `originheartgold/originheartgold.github.io` (no domain cost). It
  serves the host root, so we can publish:
  - `/robots.txt` with `Sitemap: https://originheartgold.github.io/origin-heart-gold-EN-translation/sitemap-index.xml`.
  - `/llms.txt`.
  - `/favicon.ico`.
  - `/index.html` as a minimal landing page or redirect (meta refresh plus canonical) to the project site.
- Never `Disallow: /…/preview/` in a root robots.txt: that would hide the noindex tag from crawlers and could let
  preview URLs be indexed without content.

**W-011: No Search Console or Bing verification**
- Area: SEO. Severity: high. **[USER]** Needs the user's Google and Bing accounts.
- Fix: add optional `GUIDE_GOOGLE_VERIFICATION` and `GUIDE_BING_VERIFICATION` env vars in `site.config.mjs`, emitted as
  `google-site-verification` and `msvalidate.01` meta tags in production builds only (`astro.config.mjs` `head`). Then
  submit the sitemap, request indexing of home, patch and FAQ, and watch the copycat in Performance › Queries.

**W-012: The sitemap lists noindex redirect pages and has no `lastmod`**
- Area: SEO. Severity: medium.
- Evidence: `sitemap-0.xml` has 4,692 URLs, including the 13 legacy `guide/<old-region>/` pages that are `noindex`
  "Guide moved" stubs. There are 0 `<lastmod>` entries.
- Fix:
  - Add `@astrojs/sitemap` explicitly in `astro.config.mjs` (Starlight then uses ours) with `filter` excluding the
    legacy slugs (from `src/generated/guide_legacy.json`) and `/404/`.
  - Add `serialize` to set `lastmod`: the build date for data pages, or the git date of the chapter TOML or guide
    source.

**W-013: Legacy "Guide moved" pages have no canonical**
- Area: SEO. Severity: low. File: `src/pages/guide/[legacy].astro`.
- Evidence: `noindex`, no canonical, a JS redirect, and the meta refresh only inside `<noscript>`.
- Fix: add `<link rel="canonical">` to the main target chapter and drop them from the sitemap (W-012). Keep the JS that
  maps old anchors.

**W-014: 476 pages share their title with another page (84 groups)**
- Area: SEO. Severity: high.
- Evidence:
  - Trainers: "Team Rocket Grunt" ×142, "Blue" ×19, "Unnamed trainer" ×13, "Gold" ×12, "Misty" ×10, "Cynthia" ×9,
    "Steven" ×9 and so on. Descriptions repeat in the same groups.
  - Pokémon: `pokemon/ultra-necrozma/` and `pokemon/ultra-necrozma-1278/`; `pokemon/zygarde-complete-forme/` and
    `pokemon/zygarde-complete-forme-1241/`.
  - Items: `items/eviolite/` and `items/eviolite-584/`.
  - Cross-section: `items/metronome/` and `moves/metronome/`.
- Fix:
  - `src/pages/trainers/records/[id].astro`: add the first battle place or team context to title and description
    (e.g. "Team Rocket Grunt, Rocket Hideout B1F").
  - `src/pages/pokemon/[slug].astro` and `src/pages/items/[slug].astro`: give the duplicate records a distinguishing
    suffix, or a canonical to the main record if the data is identical (check with the data owner).
  - Item and move pages with the same name get "(item)" and "(move)" in the title.

**W-015: Descriptions are thin or generic**
- Area: SEO. Severity: medium.
- Evidence:
  - 787 descriptions are under 70 characters (items: "Where to get Miracle Seed in Origin HeartGold.", 46).
  - 5 are over 160 (`/`, `/faq/`, `/difficulty/`, `/overworld-abilities/`, chapter 33).
  - 5 pages use the site default description: `guide/` (the walkthrough hub), `guide/known-issues/`,
    `guide/hidden-items/`, `guide/ruins-of-alph-silver/` and `404`.
  - Chapter summaries are 53 to 101 characters.
- Fix:
  - Item, move, ability and location templates: fold one or two data facts into the description (pocket, price, best
    source, number of locations).
  - `sync_guide.py`: chapter descriptions as "Origin HeartGold walkthrough, chapter N: <summary>".
  - Give the guide index, Known issues and Hidden items pages their own description frontmatter in their source.

**W-016: The home hero doesn't say what this is**
- Area: content / official signals. Severity: high. File: `src/components/Hero.astro`.
- Evidence:
  - The H1 is "Origin HeartGold." The eyebrow, "A familiar world. A new adventure.", and the tagline, "There's more to
    discover.", say nothing about English, a translation or a patch.
  - "Patch your game ↗" is a secondary text link.
  - The version line shows only "起源心金 v4.0.3", not the English patch version or date. The copycat shows "English
    v1.0.0-rc8 · 13 October 2026".
- Fix **[USER]** (wording that represents the project):
  - The H1 can keep the stylised look but should read "Pokémon Origin HeartGold in English", or add a visible subtitle
    inside the H1.
  - The eyebrow says "Official English translation".
  - Two equal primary buttons: "Patch your game" (download or patch) and "Start the walkthrough".
  - A release strip read at build time from `latest.json`: version, date, link to what's new on `/patch/`.
  - The `index.mdx` frontmatter `hero.tagline` and `actions` are dead (Hero.astro ignores them): clean them up.

**W-017: No changelog page on the site**
- Area: content / SEO. Severity: medium.
- Evidence: the copycat ranks with `/changelog/`. We link to GitHub, and only the "What's new in rc8" section on the
  Patch page exists on the site.
- Fix: add `/changelog/` generated at build time from `CHANGELOG.md` (player-facing parts only, following the guide
  language rules) or from the release notes in `latest.json`. Link it from the hero release strip, the Patch page and
  the sidebar.

**W-018: Section is called "quest guide", but players search "walkthrough"**
- Area: SEO / content. Severity: medium.
- Fix **[USER]** (section naming): keep "quest guide" in the UI but add "walkthrough" to the guide index H1 or intro
  ("Origin HeartGold walkthrough: the quest guide"), to chapter titles and descriptions (W-002, W-015) and to the
  sidebar label.

**W-019: The Patch page title and description miss "download" and "English patch"**
- Area: SEO / UX. Severity: medium. Files: `src/content/docs/patch.mdx`, `src/components/Patcher.astro`.
- Evidence: title "Patch your game". The direct `.xdelta` download and the manual route sit under a collapsed "If the
  patcher doesn't work for you" block.
- Fix:
  - SEO title "Download the English patch (v1.0.0-rc8) · Origin HeartGold".
  - Under the drop zone, one plain line: "Prefer to patch yourself? Download the .xdelta (42 MB) · release notes ·
    SHA-1".
  - The official-source line from W-003.

**W-020: Breadcrumbs show marketing names instead of the hierarchy**
- Area: UX / SEO. Severity: medium. File: `src/components/PageTitle.astro`.
- Evidence:
  - "Home / Explore the world" (Locations), "Home / Build your moveset" (Moves), "Home / Start your adventure" (Patch),
    "Home / Your adventure, your team" (save editor).
  - On index pages the second crumb is a non-link `span` naming a section that doesn't exist as such.
  - No `aria-current="page"`.
- Fix: keep the playful text as the eyebrow if wanted, but make breadcrumbs `Home / Locations / Azalea Town`. Use an
  `ol` with `aria-current` on the last item, and emit the same list as BreadcrumbList JSON-LD (W-008).

**W-021: Pokémon forms create near-duplicate pages**
- Area: SEO (duplicate content). Severity: low.
- Evidence: 74 `-form-NN` Pokémon pages (for example 63 Alcremie forms, Vivillon patterns) plus 79 `-<id>` duplicate
  slugs, many with identical data apart from colour.
- Fix **[USER]**: purely cosmetic forms with identical data get `<link rel="canonical">` to the base form page (they
  stay listed and reachable). Forms with different stats, types or moves keep their own canonical. The availability
  rules in site/README stay as they are: no page is removed.

**W-022: Preview pages canonicalise to themselves**
- Area: SEO. Severity: low.
- Evidence: the `/preview/` canonical is `…/preview/`. It is `noindex, nofollow`, which is fine.
- Fix: when `PREVIEW` is set, compute the canonical against the production base (strip `preview/`), so any stray link
  equity goes to production.

**W-025: The favicon is an SVG that draws text in the system font; no raster icons**
- Area: official signals / SEO. Severity: medium. Files: `site/public/`, `astro.config.mjs` `head`.
- Evidence:
  - Only `favicon.svg`. Its "OHG" text uses whatever font the OS has, so it renders differently everywhere.
  - No `apple-touch-icon`, `site.webmanifest`, `favicon.ico` or PNG sizes.
  - The save editor has a second, different favicon.
- Fix:
  - Convert the text to paths in the SVG.
  - Export `favicon-48.png`, `-96`, `-192`, `-512` and `apple-touch-icon.png` (180).
  - Add a manifest with name, short_name, theme_color and icons, and link it all from `head`. The save editor should
    use the same icon.
  - A host-root `favicon.ico` needs W-010 option B.
- No new art is involved: it is the existing monogram.

**W-026: No "official links" block**
- Area: official signals. Severity: medium. **[USER]**
- Evidence: the Starlight `social` config has only GitHub. Players can't tell which Discord, Reddit or other community
  channels are the project's.
- Fix: list the official channels (whichever the user confirms) in `about.mdx`, the footer, `social` in
  `astro.config.mjs`, Organization `sameAs` (W-008) and `llms.txt`.

### Bucket B: accessibility, design and UX

**W-030: 404 page shows the home hero, not "page not found"**
- Area: UX / SEO. Severity: high. Pages: `/404.html` (live and local).
- Evidence:
  - `Hero.astro` renders the home hero unconditionally, so the 404 page reads "Origin HeartGold. There's more to
    discover." with no "not found" message, no search and no recovery links.
  - It has `canonical …/404/` and no `noindex`.
  - Its footer links are unstyled browser-default blue.
- Fix:
  - `Hero.astro`: render the home hero only for the index route and fall back to Starlight's default `Hero` otherwise.
  - Add a `404` content entry with a "Page not found" title, a search button, links to Patch, Walkthrough, Pokédex and
    FAQ, and a note that old guide links redirect automatically.
  - Set `noindex` and no canonical, in the route middleware or 404 frontmatter `head`.
  - `custom.css`: style `.page-help a` outside `.sl-markdown-content`.

**W-031: Text contrast below 4.5:1 in light theme**
- Area: a11y. Severity: high (WCAG 1.4.3 failures).
- Evidence (axe):
  - Chapter "Opens up" quest lists: links `#94691c` on `#f3e9ce`, **4.03:1** (`.chapter-unlocks`, `.quest-note a`),
    5 nodes on chapter 3 alone, so the same on every chapter.
  - Patch page: the caution-aside link `#94691c` on `#fceac5`, **4.12:1**.
  - Save editor: `.brand-sub` "save editor" `#8b867b` on `#efece5`, **3.07:1**.
  - Pokémon page "Artwork: PokéAPI" caption: undetermined over a gradient; check manually.
  - Dark theme had no violations on the same pages.
- Fix: in `src/styles/custom.css`, links on accent-low or aside backgrounds use `--sl-color-accent-high` (`#6d4a0d`
  light). Darken `.brand-sub` in the save editor stylesheet (`work/save-editor`). Give the figcaption a solid background
  or darker text.

**W-032: The table-scroll wrapper sets a prohibited, meaningless ARIA label**
- Area: a11y. Severity: medium. File: `site/public/ohg.js`, `setupTableScroll`.
- Evidence:
  - axe `aria-prohibited-attr` on every page with tables (FAQ, chapters, Pokémon, locations, items, trainers, moves).
    `aria-label` is set on a `div` that only gets `role=region` when it overflows.
  - The label comes from the first `th`, giving "# table — scroll for more columns" or "Pokémon table — …".
- Fix:
  - Set `aria-label` together with `role=region` and `tabindex` only when the table overflows; remove all three
    otherwise.
  - Build the label from the nearest preceding heading, or `aria-labelledby` its id: "Level-up moves (scrollable
    table)".

**W-033: Tables have no captions or accessible names**
- Area: a11y. Severity: medium.
- Evidence: every sampled table lacks `<caption>`, `aria-label` and `aria-labelledby` (226 on `/trainers/`, 13 on Azalea
  Town, 6 on Cyndaquil).
- Fix: add `<caption class="sr-only">` or `aria-labelledby=<heading id>` in the table components (`EncTable`,
  `MoveTable`, `TrainerCard`, `TrainerTeamPreview`, `PokemonReferenceTable`, `WildEncounters`) and in the Markdown
  table wrapper.

**W-034: The save editor doesn't feel like part of the site**
- Area: a11y / design / UX. Severity: medium. Files: `site/src/pages/save-editor/index.astro`, `work/save-editor`.
- Evidence:
  - No `h1` (0 headings) and no footer or disclaimer.
  - Title "Origin HG Save Editor", no canonical, OG tags or description beyond one line.
  - Its own brand ("Origin HG save editor"), its own theme toggle and storage key, and IBM Plex from Google Fonts
    (third-party request; privacy and performance).
  - The empty state is only "Drop your .sav or .dsv here", with no backup warning, no help link and no link to the
    FAQ.
  - The JS bundle is 1.1 MB (269 KB gzip).
- Fix:
  - Add an `h1` ("Origin HeartGold save editor"), an intro with a "keep a backup" note and a link to the FAQ, and the
    site disclaimer footer.
  - Title "Save editor · Origin HeartGold", canonical and OG tags.
  - System fonts or self-hosted fonts.
  - Reuse Starlight's `starlight-theme` storage key so the theme follows the rest of the site.

**W-035: No global navigation on the home page; on phones there is no menu at all**
- Area: UX / design. Severity: high. Files: `src/components/GuideHeader.astro`, `MobileMenuToggle.astro`.
- Evidence:
  - The splash template has no sidebar. At 390 px the home header shows only the logo, search and "Save editor ↗", so
    Pokédex, Trainers or FAQ are reachable only by scrolling through cards.
  - On other pages the main destinations are buried in a roughly 60-link sidebar.
  - The copycat has a five-item top bar with Download highlighted.
- Fix: a compact primary nav in `GuideHeader`, the same on every page: **Patch**, **Walkthrough**, **Pokédex**,
  **Trainers**, **FAQ**, with Patch styled as the primary action. Collapse it into the menu button below about 50 rem,
  and show the menu button on the home page too.

**W-036: The ↗ "external" arrow is used on internal links**
- Area: UX. Severity: low.
- Evidence: the hero "Patch your game ↗" and header "Save editor ↗" point to same-site pages with no `target`.
- Fix: use → or no icon in `Hero.astro` and `GuideHeader.astro`. Keep ↗ for real external links only.

**W-037: Trainer and encounter tables are cramped on phones**
- Area: design / UX. Severity: medium.
- Evidence: at 390 px `trainers/records/244/` wraps place names and party lists one or two words per line (very tall
  rows). 226 of 226 tables on `/trainers/`, 8 of 10 on Giovanni and 8 of 13 on Azalea Town need sideways scrolling.
- Fix: below about 40 rem, render trainer encounter rows as stacked cards (place, battle type, team) via CSS grid in the
  trainer components. Keep sortable reference tables scrollable.

**W-038: Sort buttons in table headers are only 20 px tall**
- Area: a11y (WCAG 2.2 2.5.8). Severity: low.
- Evidence: `Type` 28×20 px, `Move` 31×20 px and similar on every sortable index.
- Fix: in `custom.css`, give `table.sortable th .sort-button` `min-height: 24px` (44 px on coarse pointers) and add
  padding.

**W-039: The home page has too many entry points**
- Area: design / content. Severity: low. File: `src/content/docs/index.mdx`.
- Evidence: Patch and Save editor each appear 3 times (header, hero and cards). "Jump in" lists 13 link cards after 4
  explore cards.
- Fix: after W-016 and W-035, cut "Jump in" to around 6 task-based cards (Stuck on the stolen Gloom?, Team Builder,
  Calendar, TMs, Known issues, Save editor).

**W-040: Hero art is Pokémon artwork, not the game**
- Area: design / content. Severity: low. **[USER]**
- Evidence: the copycat's hero shows an in-game screenshot ("Route 1"), which communicates "this is a playable DS game"
  immediately.
- Fix: optionally add one or two screenshots of our English build, the same kind the guide already uses, to the home or
  Patch page.

### Bucket C: performance and misc

**W-050: 48 px thumbnails load 512 px artwork**
- Area: perf. Severity: critical (page weight).
- Evidence:
  - `PokemonImage.astro` uses `referenceArtwork()` (`work/save-editor/src/ui/artwork.ts`) for every thumbnail: the
    512×512 HOME PNG from `raw.githubusercontent.com`. `250.png` alone is 133,094 bytes, with `Cache-Control:
    max-age=300` and no `Timing-Allow-Origin`.
  - Counts: `/pokemon/` has 1,441, `/trainers/` 5,056 and `/moves/protect/` 1,497 (similar on every common move and TM
    page). They are lazy, but scrolling pulls on the order of 100+ MB, and raw.githubusercontent may rate-limit.
- Fix options:
  - (a) Small thumbnails use PokéAPI's 96 px sprite (`sprites/pokemon/<id>.png`, about 1 to 2 KB), keeping HOME art for
    the large image.
  - (b) **[USER]** A build step that fetches, resizes to 96 px WebP and self-hosts the thumbnails. That needs approval
    to download and host third-party art, plus a credits entry.
  - (c) Serve via jsDelivr's GitHub CDN for long caching (still 512 px).
- Also add `<link rel="preconnect" href="https://raw.githubusercontent.com" crossorigin>` site-wide (the save editor
  already has it).

**W-051: Very large list pages (DOM size, INP risk)**
- Area: perf. Severity: high.
- Evidence:
  - `/trainers/`: 4.36 MB HTML (245 KB gzip), 60,181 DOM nodes, 9,236 links. DOMContentLoaded took 2.6 s live on a
    fast desktop, so expect several times that on a mid-range phone.
  - `/reference-sources/`: 3.0 MB. `/pokemon/`: 2.3 MB and 37,460 nodes.
  - Common moves (Protect, Rest, Return, Substitute, Sleep Talk) and their TM item pages: about 1.1 MB and about 18,000
    nodes each.
  - Lighthouse flags DOM size above about 1,400 nodes. Filter and sort on these tables risks poor INP.
- Fix:
  - `/trainers/` (`src/pages/trainers/index.astro`): show a summary per section (name, place, ace, link) and leave full
    teams to the record pages, or wrap each section in `<details>` and use `content-visibility: auto`.
  - Learner tables on move and TM pages: render the first N rows plus "Show all N Pokémon", or drop thumbnails in
    those tables.
  - Add `content-visibility: auto; contain-intrinsic-size` to long table bodies in `custom.css`.

**W-052: Home hero images aren't prioritised**
- Area: perf (LCP on mobile). Severity: medium.
- Evidence: 4 eager 512 px PNGs (about 500 KB) from a third-party origin, no preconnect, `fetchpriority=auto`. Live LCP
  was fast on this machine (136 ms), but on mobile the Ho-Oh image is the LCP candidate.
- Fix in `Hero.astro`:
  - `fetchpriority="high"` and preconnect for Ho-Oh.
  - `loading="lazy"` for the three starters below 50 rem (they sit below the fold there).
  - Smaller sources (W-050).

**W-053: Search UI and CSS load on every page**
- Area: perf. Severity: low.
- Evidence: Pagefind's `ui-core` (94 KB) is fetched on home load. `middleware.css` is 91 KB raw on every page.
- Fix: check that Starlight's search loads on first interaction (Search button or ⌘K). Audit `custom.css`,
  `team-builder.css` and `battle-check.css` so page-specific CSS ships only where it is used.

**W-054: Third-party fonts in the save editor**
- See W-034. Severity: low (perf and privacy). Self-host or use the system stack.

**W-055: GitHub Pages cache limits**
- Area: perf. Severity: info.
- Evidence: every asset is served with `cache-control: max-age=600`, including hashed `/_astro/` files. This can't be
  changed on GitHub Pages; keeping JS and CSS small (W-053) is the lever.

**W-056: Local build gotcha (documentation)**
- Area: misc. Severity: low.
- Evidence: `npm run build` in a fresh worktree fails in `prebuild` ("TypeScript is not installed in
  work/save-editor/node_modules"). The site's `node_modules` symlink isn't enough; the save editor needs its own.
- Fix: document in `site/README.md` that worktrees need
  `ln -s <main>/work/save-editor/node_modules work/save-editor/node_modules` (gitignored), next to the existing
  `site/node_modules` symlink. Also document `python3 work/tools/site/sync_guide.py` before the build, and the env vars.

---

## Implementation buckets

| Bucket | Findings | Count |
|---|---|---|
| **A: SEO, official signals, discoverability files** | W-001 to W-022, W-025, W-026 | 24 |
| **B: accessibility, design, UX** | W-030 to W-040 | 11 |
| **C: performance and misc** | W-050 to W-056 | 7 |

Suggested order inside A:
1. Route middleware (`src/routeData.ts`): titles, descriptions, OG and JSON-LD all hang off it (W-001, W-002, W-007,
   W-008, W-014, W-015, W-022).
2. Official statement and hero (W-003, W-016, W-019) once the user approves the wording.
3. Discovery files (W-009, W-012, W-013, W-025).
4. The non-code steps the user does: W-004, W-005, W-010, W-011, W-026.

In B, W-030 (404) and W-031 (contrast) are quick and high value. W-035 (global nav) is the largest design change.

In C, W-050 is the biggest single win but needs the user's choice of thumbnail source.

## Decisions needed from the user

1. **Official wording** (W-003, W-016): the official-site statement, the H1 and hero copy, and whether to add
   "other sites are not run by us".
2. **Brand string** for titles and `og:site_name` (W-002): "Origin HeartGold Guide" or something with "Pokémon" and
   "English".
3. **GitHub repo settings** (W-004): homepage, description, topics. These are repo settings, not code.
4. **Release notes and README.txt link** to the site (W-005).
5. **User-site repo `originheartgold.github.io`** (W-010 option B): enables a root robots.txt with the sitemap, root
   llms.txt, root favicon.ico and a landing page at the bare host. Free.
6. **Search Console and Bing Webmaster** accounts and verification tokens (W-011).
7. **Social card image source** (W-006) and optional **in-game screenshots** on home or Patch (W-040), under the
   "graphics are sourced, never generated" rule.
8. **Official community channels** to list (W-026).
9. **Thumbnail source** (W-050): PokéAPI small sprites, or self-hosted resized artwork (needs approval to download and
   host).
10. **Canonicalising cosmetic Pokémon forms** to the base form (W-021).
11. **Calling the guide a "walkthrough"** in titles and labels (W-018).

## Notes for implementers

- Player-facing language: no map ids, coordinates or flags in guide text, `llms.txt`, descriptions or JSON-LD. Use
  landmarks instead.
- Never put ROM data or the patch into the repo. `llms.txt` and JSON-LD link to the release page; they don't embed
  anything.
- Rebuild and re-run the title, description and sitemap script over `dist/` after bucket A. Target: 0 duplicate titles
  outside deliberate cases, no default descriptions, no noindex URL in the sitemap, JSON-LD on 100% of pages.
