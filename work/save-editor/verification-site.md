# Native guide save-editor page

`/save-editor/` is a native **Starlight page** using the guide's header, sidebar,
page title, typography and light/dark theme. The editor controls render directly
in that page. There is no iframe, embedded application document or `/app/` route.

The `SaveEditor.astro` adapter reuses the existing editor's control markup and
TypeScript. It removes the standalone hero, duplicate main/title, step labels and
footer, leaving Starlight responsible for the page structure. The standalone
prototype remains available for development; its custom palette and stylesheet
are not imported into the guide.

All editor-specific CSS is rooted under `.save-editor`, uses Starlight color/text
variables and styles the dynamically generated controls as well as initial markup.
Only pages containing this editor receive a wider content column. The page has no
right-hand table of contents. It retains the guide's search and theme switcher.

## Local processing and build

The canonical editor still reads and edits saves locally with no upload/network
code. Existing guide JavaScript does not read the file input. The native page's
CSP permits same-origin connections for guide search/prefetch and blocks form
submissions and objects. It intentionally does not apply the former isolated
page's restrictive script/style policy, which would break Starlight's required
inline theme initialization and styles. Guide asset/search requests are distinct
from save uploads; no save contents are sent.

Astro/Vite processes the canonical editor source during ordinary `astro build`.
No separate editor build, new site dependency or build hook is needed. The website
workflow includes `work/save-editor/**` in its push/PR path filters. Only the
approved English reference metadata bundle ships with the editor; save/ROM files,
local fixtures and the developer ROM parser do not.

## Worktree boundary and changed files

This task did not modify the original checkout. Both branches are unborn and the guide
exists only in the original checkout, so this worktree contains a **minimal site
overlay**, not a standalone complete guide:

- `site/astro.config.mjs`: native page sidebar entry.
- `site/src/content/docs/index.mdx`: home-page editor card.
- `site/src/pages/save-editor/index.astro`: native Starlight page.
- `site/src/components/SaveEditor.astro`: shared-control adapter and script entry.
- `site/src/styles/save-editor.css`: scoped guide-native controls/layout.
- `.github/workflows/site.yml`: editor path triggers.

The previous iframe wrapper and isolated `app.astro` route have been removed.
Apply this overlay alongside `work/save-editor/` in the complete canonical checkout;
do not replace the rest of the site with this partial folder. No merge, commit,
deployment, publication, dependency download or ROM build was performed.

## Reproduce the ignored preview build

Run from the editor worktree root using existing canonical-site dependencies:

```sh
node work/save-editor/scripts/prepare-site-preview.mjs /path/to/canonical-repo work/save-editor/local/site-preview-new
GUIDE_BASE=/poke/ node /path/to/canonical-repo/site/node_modules/astro/bin/astro.mjs build --root work/save-editor/local/site-preview-new/site
node work/save-editor/scripts/verify-site.mjs work/save-editor/local/site-preview-new/site/dist /poke/
ORIGIN_EN_ROM=/path/to/existing/English.nds npm --prefix work/save-editor run check
```

The helper copies code/config and borrows generated guide content, data, vendor
assets and dependencies via local symlinks in ignored `local/`. Existing release
patches and generated PDF downloads are excluded. Do not commit this fixture.
After integrating into a complete checkout, normal `npm --prefix site run build`
(or CI's existing direct `npx astro build`) is sufficient.

## Current verification (2026-10-04)

- Native `/poke/save-editor/` build: **2,373 pages**, successful.
- Static verifier passes: exactly one main landmark and one `Save editor` h1;
  editor controls directly present; no iframe, standalone hero or old `/app/`
  route; unique input IDs; same-site/base-prefixed asset references all exist.
- Scoped editor CSS uses Starlight variables and contains no standalone palette.
  The canonical editor bundle contains reference metadata, not the ROM parser;
  output contains no ROM/save files. Native shell scripts/styles remain allowed.
- Editor compiler, typed ESLint and **218 tests pass with zero skips**, including
  local English-ROM parity. No editor behavior/mutation code changed in this
  native-layout correction.
- This task did not write original source files. Concurrent guide changes added Mechanics and Calendar navigation; those additions are preserved in this overlay. The local preview serves the native
  page at `http://127.0.0.1:4180/poke/save-editor/` (HTTP200).

Evidence is in ignored `local/site-integration-20261004/`, particularly
`build-native.log`, `verify-native-project.json` and `editor-check-native.log`.
Earlier root/nested-base reports there describe the superseded isolated layout;
the base helper was unchanged, but they are not fresh native-layout checks.
The fixture omits the existing generated guide PDF, so the prior whole-guide link
check had one known fixture-only missing PDF. It had no editor link errors.

Browser discovery and documented URL selection both reported no available browser,
despite the user's visible preview. **A fresh visual inspection or native-page
file import/download could not be automated.** Static layout/asset/CSP checks and
editor regression tests passed; the earlier actual browser download → reopen →
game evidence is in `verification-export.md`. Nonfatal Starlight head-directive
warnings remain in the build log for existing MDX pages.
