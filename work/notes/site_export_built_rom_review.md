# Review: fix/site-export-built-rom (site data and docs from the released ROM)

Reviewer: independent agent, 2026-10-18. Commits reviewed: 7bf6e5ac, 2d07bf29, d2440e71 on top of website-fix
d7e34ca4. Design note: `work/notes/site_export_built_rom.md`.

## Verdict: APPROVE

The ROM selection, SHA-1 check, hash-keyed cache, layout guard, EV-order reader and both reader fixes are correct
and do what the note says. The regenerated rc8 data differs from the committed data only where an enabled rc8 fix
or a guide edit explains it, and no name, description or EV changed by accident. CI needs no ROM and does not call
the exporter. None of the findings below blocks the merge. Finding M-1 needs action when this line meets `develop`.

## What was checked and how

- **ROM selection.** `tag_key` and `release_tags` sort numerically, a final release beats its rcs, and prep or
  tester folders (`v1.0.0-rc7-public-prep`, `-all-fixes-tester-2`, `wip`) never count, even though some of them
  hold a `latest.json` with tag `v1.0.0-rc7`. A `--rom` flag beats `OHG_DOCS_ROM`, which beats the default.
  - A fresh run in a clean worktree, with no `work/build`, rebuilt `v1.0.0-rc8.nds` from the xdelta. The result
    hashes to `a54a6475…318a`, the cache was written as `docs_cache/<sha1>.pkl`, and `--check` passed.
  - `--rom release:v1.0.0-rc5` also rebuilds and passes the layout guard.
  - `--check --rom cn` and `--check` with `OHG_DOCS_ROM=release:v1.0.0-rc5` both exit 1 with a clear
    "ROM mismatch" message.
- **CI.** `.github/workflows/site.yml` never runs `export_data.py`, `gen_docs.py` or `build.py`. In a worktree with
  no `work/rom`, `work/release` or `work/extract`, the CI unittest steps pass: 52 tests (7 skipped) and 78 tests.
  The new `test_rom_selection.py` needs no ROM.
- **Trainer EV order (`romdata.trainer_ev_order`, romdata.py:301).**
  - The disassembly at 0x02072884 is the same on the Chinese ROM and on rc8: `mov r0,r4; movs r1,#13..18;
    mov r2,r7; adds r2,#0x14+i; bl SetMonData`. The reader returns `(0,1,2,4,5,3)` on both.
  - I applied the three immediates of `trainer-ev-order` (develop `work/patches/trainer-ev-order/fix.toml`:
    0x728A8→0x11, 0x728B4→0x12, 0x728C0→0x10) to rc8's arm9 in memory. The reader then returns `(0,…,5)`, and
    the EVs it produces match develop's committed `trainers.json` (43e8f2fb) for all 1,023 trainers.
  - The branch's committed `trainers.json` matches the Chinese order for all 1,023 trainers. 215 trainers differ
    between the two orders, which is the fix's "215 of 216 trainers".
  - Any other code at those addresses (another register, another source offset, or not a permutation) raises an
    error, and `check_layout` reports it. The reader cannot silently pick a wrong order.
  - Every site and docs path goes through `gen_docs.load_trainers`, which passes the order. The one other caller,
    `battle_reference.py:183`, reads only moves.
- **Pickup.** On both ROMs, `read_table` returns the same table and finds a 10% gate. On rc8 the gate is the one
  `honey-gather` moved to 0x0222BD38. A unit test covers the moved gate and rejects a wrong `bl` target.
- **Trainer-condition loop skip (gen_docs.py:1166).** I compared the export with and without the new line:
  - Chinese ROM: 0 trainers' conditions differ.
  - rc8: exactly 1 differs. Trainer #32 (Pryce, double battle) regains "before you have the Glacier Badge"; without
    the line it loses it.
  - There is no unit test for this (finding m-3).
- **`fixedBy` and `fix_in_rom`.** `petilil-hisuian-lilligant` reads False on the Chinese ROM and True on rc8.
- **Text from the ROM.**
  - No CJK text anywhere in the player-facing data. The only CJK strings are the workbook sheet labels in `evidence.sheet`, the
    `game` title in `meta`, and one `priorAuditNote`, all as before.
  - `moves.json`: 0 differences.
  - `species.json` and `items.json`: no `name` field changed.
  - Long names stay the full official ones (Crabominable, Fletchinder, Corviknight, Squawkabilly). The truncated
    ROM forms appear only in the `game` alias field, as before.

## Data diff d7e34ca4 → 2d07bf29, recomputed

| Change | Count | Explained by (enabled at v1.0.0-rc8) |
|---|---|---|
| species `tutors`: Flail (175) → Play Rough (583) | 176 species | tutor-blackthorn-play-rough |
| tutors: Flail entry and its hack-bug note replaced by Play Rough; workbook row 585 joins as matching, with the audit note marked as the original hack's | 1 → 1 | tutor-blackthorn-play-rough |
| tutors: the Saffron Dojo restricted "Charge" entry removed | 1 | tutor-saffron-volt-switch |
| Petilil `evoTo`/`evoNotes`; Hisuian Lilligant `evoFrom`, `how`, `acquisition`, `otherSources`, `evoNotes`; Black Belt `evolutionUses` no longer blocked | 2 species, 1 item | petilil-hisuian-lilligant (`fixedBy`) |
| trainer #763: both Forest of Time battles "only in some story branches" | 1 | forest-of-time-sammy-guard |
| Raticate trade evidence offset in script 156: 4969 → 4972 | 1 | reward-qty (script insert) |
| Lavender Town Mr. Fuji quest links (`areas.json` statics[104], `species.json` Cubone) | 2 | guide edit, not the ROM |
| `meta.rom` | 1 | this change |

**Unexplained differences: none.**

I also looked for changes that should be there but are not, against every fix enabled at the rc8 tag:

- **Boldore/Gurdurr:** already shown at Lv 35/40 through the removed override. The rc8 evolution records agree.
- **evolution-items-use:** the site never marked these evolutions as blocked, and the Bag's Use flag is not
  exported.
- **trainer-abilities, overworld-pokemon-cries, safari-zone-closed, ss-anne-softlock, route3-misty-actors, the
  expedition/mortar/Ho-Oh fixes:** disabled at rc8. The trainer data is byte-identical to the Chinese ROM.
- **ssanne-tm-price-check, fortune-ideal-price-check, haircut-younger-price-check:** only the check changes. The
  site already shows the menu price (TM21 ₽4000).
- **gamecorner-500-coins:** guide text only.
- **overworld-pokemon-sprites:** presentation only.
- **reward-qty:** message only, apart from the offset shift above.

Nothing is missing.

## Findings

### Major

**M-1. The merge into `develop` needs hand resolution.** This is not a defect of this branch. `develop` already
carries `trainer-ev-order` (enabled) and 43e8f2fb. That commit:

- drops the reorder in `parse_trpoke`;
- changes `test_trainer_runtime.py` to expect the record order from a call that passes no order;
- puts `trainers.json` and `work/docs/trainers.md` in the fixed order.

A dry merge (`git merge-tree develop fix/site-export-built-rom`) conflicts in `work/tools/docs/romdata.py`,
`work/tools/docs/gen_docs.py`, `site/src/data/trainers.json`, `site/src/data/items.json` and
`site/src/data/areas.json`. It also conflicts in the unrelated `quest_ledger.json` and `decisions.jsonl`, which
the two lines would hit anyway.

Two files auto-merge into a bad state:

- `test_trainer_runtime.py` keeps develop's test, which expects `[1..6]` from
  `parse_trpoke(record, 1)`. That test fails against this branch's default `ev_order=CN_EV_ORDER`
  (romdata.py:317).
- `work/docs/trainers.md` becomes a mix of develop's fixed-order EVs and this branch's rc8 header.

To resolve:

1. Take this branch's `romdata.py` and `gen_docs.py`.
2. Make develop's test pass the order explicitly, or test through `trainer_ev_order`.
3. Regenerate the data and docs with `--rom release:latest`.

On develop the site's trainer EVs then go back to the Chinese order until rc9 is released, which is correct for rc8
players and is the design. The coordinator should expect it.

### Minor

**m-1. `Rom.bank` has no guard against Chinese text (romdata.py:756).** `bank_full` (romdata.py:765) keeps the
workspace English when the ROM still holds a string in Chinese. `Rom.bank` has no such guard, and it supplies the
names, the map banks behind the dialogue options in trainer and gift conditions, and the NPC first lines.

For rc8 this is harmless: there is no CJK in the player data. A later build with an untranslated map line would
put that Chinese line on the site. Suggested fix: the same `text == zh` fallback that `bank_full` uses.

**m-2. A failed rebuild leaves a large temporary file (romdata.py:669).** `materialize_rom` leaves
`work/build/release-roms/<tag>.nds.tmp` (about 280 MB, gitignored) when `xdelta3` fails or the hash does not
match. The next run overwrites it, so nothing is wrong, only disk space. Each run also hashes the ROM twice, once
in `materialize_rom` and once in `Rom.__init__`, at about 1 s each.

**m-3. The loop skip has no unit test (gen_docs.py:1166).** The A/B check above shows the skip is right, but no
unit test covers it. A small synthetic script with a back edge above a flag check would pin it down.

**m-4. Latent duplicate in `fixed_tutor_note` (battle_reference.py:190-192).** A `tutorNotes` entry without
`configuredMoveId` would be added twice: once by the first list through its `moveId`, and again because
`None not in taught`. All 79 current notes have the field. Suggested fix: require `'configuredMoveId' in x` in
the second list.

**m-5. `release:latest` is the highest *local* release folder (romdata.py:600).** The site workflow serves the
highest *published* GitHub release. RELEASING section 1 writes `latest.json` in step 5 and merges the regenerated
data to `main` in step 7, before the tag and publication in section 2. This has two effects:

- From step 5 on, `--check` on other branches reports a ROM mismatch.
- The site deploys data for the new release while `/patch/` still serves the previous one.

The window is short and the behaviour is safe. A sentence in RELEASING.md step 6 or 7 ("publish soon after
merging", or "merge the data once the release is published") would make it explicit.

### Info

- The curated Boldore/Gurdurr `evoNote` entries in `extra_sources.json:7-22` always say "The English patch from
  rc6 evolves it…". A `--rom cn` export therefore shows them next to the trade evolutions. `fixedBy` gates only
  arm9 code fixes, and `cn` data is never committed, so this is only cosmetic in local comparisons.
- `check_layout` does not check the trainer-class gender table (0x020FF77C) or the calendar slots (0x020F6A64).
  The tables it does check would almost certainly fail too if the arm9 moved, so the risk is low.
- `parse_trpoke` still defaults to the Chinese order for direct callers. Only research and test code calls it
  directly; site and docs paths always pass the order.

## Test results (worktree at d2440e71)

| Check | Result |
|---|---|
| `python3 -m unittest` docs list from site.yml | 52 tests OK (0 skipped with ROMs; 7 skipped in a ROM-less worktree) |
| `python3 -m unittest discover -s work/tools/site -p 'test_*.py'` | 78 tests OK (with and without ROMs) |
| `export_data.py --check` (release:latest = v1.0.0-rc8) | exit 0, 14 data files, 0 changed |
| `gen_docs.py --check` | exit 0, 18 pages, 0 changed (cross-reference from the Chinese ROM, pages from rc8) |
| `sync_guide.py` | 38 guide pages, 0 changed |
| `npm run build -- --force` (GUIDE_BASE=/) | exit 0, 4,693 pages |
| `GUIDE_TEST_DIST=1 npm test` | 186 tests, 186 pass, 0 fail |
| `check_site.py --base /` | 4,693 pages, 828,139 links, 0 broken |

## Trial merge into website-fix-proposal

The trial ran in the worktree `~/Developer/poke-review-merge-trial`, detached at website-fix-proposal `d70e35d7`.
That branch moved past `67de3a89` while the review was running. The merge was done with `--no-commit` and is left
unresolved.

- **Conflicts: one, in `site/README.md`.** The two branches each add a new section after the same paragraph:
  website-fix-proposal adds "After a release: the changelog page" and "Search titles, structured data and
  discovery files", and this branch adds "Which game the data describes". Keeping both sections resolves it.
- **Auto-merged cleanly:** `RELEASING.md` (step 6 and 7 numbering intact), `site/src/pages/reference-sources/index.astro`,
  `site/tests/reference-pages.test.mjs`.
- **Tests on the merged tree** (README conflict markers left in place; the README is not part of the build):

| Check | Result |
|---|---|
| Docs unittests | 52 OK (7 skipped, no ROM) |
| Site unittests | 84 OK |
| Build | 4,694 pages |
| `GUIDE_TEST_DIST=1 npm test` | 201 tests, 201 pass, 0 fail |
| `check_site.py --base /` | 4,694 pages, 914,746 links, 0 broken |
