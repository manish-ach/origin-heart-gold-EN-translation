# Bundled English reference verification

Supported scope is English Origin HeartGold v4.0.3. Users select only a save;
no ROM or other reference input is required. Structural checks cannot determine
save language reliably, so there is no nickname/language rejection heuristic.

## Source and permitted content

The user approved bundling editor-required English names and numeric metadata on
2026-10-04. The 183,253-byte generated TypeScript module contains 1,025 species
names, 921 move metadata records (902 selectable named moves), 790 item/pocket
mappings (768 named entries), 1,441 compact personal records (six base stats and
one growth index), 415 form lookup entries and eight 101-level growth tables.
Names retain the translation build's abbreviations. No dialogue, graphics, raw
archives, ROM bytes or save data are included.

`src/generated-reference.ts` contains schema version 1, the English v4.0.3 profile,
source ROM SHA-256, extracted archive/name-bank/form-table SHA-256 hashes and
payload SHA-256. It was generated from the existing local English WIP build.
`src/rom.ts` validates the established numeric-data fingerprints before extraction.
The generator requires complete English catalogs and writes only explicit fields.
The generated module is source, not ignored; the compiled `dist/` remains ignored.

Startup validation rejects malformed versions, counts, names, IDs, ranges, hash
shapes and unexpected fields. A failure disables save import and shows a useful
reload/build message. Cryptographic content verification is performed by the test
suite and deterministic generator check. The browser imports only the bundled
provider; a module-graph regression test excludes the developer ROM parser.

## Repeatable checks

Run from the worktree root, using an existing local English build:

```sh
ORIGIN_EN_ROM=/path/to/English.nds npm --prefix work/save-editor test
node work/save-editor/scripts/generate-reference.mjs --check /path/to/English.nds
node work/save-editor/scripts/verify-bundled-local.mjs /path/to/English.nds /path/to/saves
```

To intentionally refresh metadata, run `generate-reference.mjs` without `--check`,
rebuild, review source hashes and rerun every check. No downloads or ROM build is
part of this process. Ordinary `npm test` needs no ROM; the exhaustive local-ROM
comparison is explicitly skipped unless `ORIGIN_EN_ROM` is supplied.

2026-10-04 results:

- All **166 tests pass**, including the optional local-ROM comparison.
- Every 1,025 × 256 species/form lookup matches the original provider, including
  all returned growth thresholds. Every move, item and name catalog matches.
- Deterministic generator `--check` passes; schema, malformed-data and content hash
  tests pass. Field allowlists prevent accidental inclusion of unrelated game data.
- Six real saves (13 party Pokémon, 48 pockets) pass exact old-provider versus
  bundled-provider stat/move/item edit byte equivalence, money cap, no-op and
  source-file hash checks.
- Existing deeper fixture harnesses also passed with `ORIGIN_REFERENCE=bundled`:
  independent IV/EV edits, quantity/remove/add, checksums and changed-byte allowlists.
  All 12 resulting stat/inventory saves are byte-identical to the corresponding
  earlier fixtures already verified in native English save/reset/reload runs.
  No new emulator run was necessary: save mutation routines are unchanged and
  the newly bundled path produces those exact verified bytes.

Reproduce the deeper harnesses with new ignored output directories:

```sh
ORIGIN_REFERENCE=bundled node work/save-editor/scripts/verify-stats-local.mjs /path/to/English.nds /path/to/saves work/save-editor/local/bundled-stats-new
ORIGIN_REFERENCE=bundled node work/save-editor/scripts/verify-inventory-local.mjs /path/to/English.nds /path/to/saves work/save-editor/local/bundled-inventory-new
```

## Save-only browser checklist

Passed in a fresh in-app browser page on 2026-10-04, without selecting any ROM:

1. Only one file input appears, accepting `.sav`. Import `full_bag_6mons.sav`.
   Party names immediately show Charmeleon, Archaludon and other expanded species;
   moves and item names appear, stats and all inventory controls are enabled.
2. Search `flame`, select Flamethrower and Apply. Name and correct PP are retained.
   Attempt 16 PP: rejected with a 0–15 message. Discard restores applied state.
3. Set an EV HP draft to 200, set IV Attack to 31 and Apply IVs. EV draft stays 200
   and edited export remains disabled. Apply EVs independently.
4. Enter a money draft of 123456, change first item quantity to 7 and Apply pocket.
   Money draft survives and blocks edited export. Apply money enables export.
5. Select Medicine and search `potion`: only Potion, Max Potion, Hyper Potion and
   Super Potion appear. All controls work with the bundled data automatically.
6. Browser logs contain no application warnings/errors.

Actual browser download-file delivery remains unverified because of the previous
in-app observer limitation. Download payload bytes and native persistence are
verified separately above; the UI continues to say “Download requested”.
