# Site data and player docs from the released ROM

Status: implemented on branch `fix/site-export-built-rom` (2026-10-18). The website data (`site/src/data/*.json`,
`work/tools/site/export_data.py`) and the player docs (`work/docs/*.md`, `work/tools/docs/gen_docs.py`) now describe
the ROM players get from the newest release, not the untouched Chinese ROM.

## Why

Both generators read `work/rom/origin_v4.0.3_cn.nds`. Every ROM-level fix then had to be repeated by hand on the
site side (the Boldore/Gurdurr evolutions in `export_data.py`, the trainer EV order in `romdata.parse_trpoke`) or
was simply missing: on the site rc8 players saw the Blackthorn tutor teaching Flail, a Saffron tutor teaching Charge
and Petilil unable to evolve into Hisuian Lilligant, three hack bugs rc8 fixes; the rc8 release docs still said
Boldore evolves by trade. PLAN_RC9 section 3 needs the trainer EVs, "Lunar Guard" and the English Pokédex order to
follow the rc9 release.

## Which ROM

`romdata.select_rom(spec)`; `--rom` on `export_data.py`, `gen_docs.py` and `site/build.py`, or the environment
variable `OHG_DOCS_ROM`:

| spec | ROM | use |
|---|---|---|
| `release:latest` (default) | the highest version `work/release/<tag>/` (vX.Y.Z or vX.Y.Z-rcN, a final beats its rcs, as the site workflow sorts) that has a `latest.json` | committed data |
| `release:<tag>` | that release | at a release (RELEASING.md section 1 step 6) |
| `build` | `work/build/origin_hg_v4.0.3_en_wip.nds`, the standard builder's output | local previews only |
| `cn` | the untouched Chinese hack | comparisons, regression checks |
| `<path>.nds` | any ROM | experiments |

A release ROM is the release's xdelta applied to the clean USA ROM with `xdelta3`, written to
`work/build/release-roms/<tag>.nds` (gitignored, never committed) and refused unless it hashes to the
`patched_sha1` of the release's `latest.json`. For rc8 this is `a54a647599d59ed0060dfc4375c289d6e041318a`, the
"Result ROM SHA-1" in its README.

**Release ROM, not the standard build.** The release ROM is what players run: the standard build plus the
difficulty layer (rc8) and from rc9 the advanced AI. It is also the only ROM that can be rebuilt exactly for a past
release. Compared with the Chinese ROM, rc8's release ROM differs in the members the readers use only where fixes
put it: evolution records 525/533, 9 item records (the Bag's Use flag, not exported), 60 script files, 19 event files,
all message banks, arm9 code (appended to; the tables stay at their addresses) and 12 overlays. Its trainer data
(`a/0/5/5`, `a/0/5/6`) is byte-identical to the Chinese ROM: the difficulty layer changes behaviour at run time,
not the stored parties, so the site shows the normal (default) parties. Data from `build` or `cn` must never be
committed: the site test requires `meta.json` to name a release.

**Identity.** `meta.json` gets `rom: {label, kind, sha1, tag}`; `/reference-sources/` prints the label and SHA-1;
every generated docs page names the ROM in its header comment (the Chinese ROM keeps the old header).
`export_data.py --check` exits 1 when the committed `meta.json` names another ROM than the requested one (or none),
as well as when a file would change. `gen_docs.py --check` fails the same way through the page headers.

**Cache.** `work/build/docs_cache/<ROM SHA-1>.pkl` (was `work/build/docs_cache.pkl`, keyed only by mtime), so the
Chinese, release and build caches never mix. The message archive (`a/0/2/7`) is now cached too. `romdata.Rom()` with
no path still opens the Chinese ROM, so the tools that analyse the hack itself (translation context, fix tests,
emulator helpers, `reconcile_references.py`) are unchanged.

**Layout guard.** The readers use fixed arm9 addresses of the Chinese v4.0.3. The English build patches code in
place and only appends to the arm9, so they still hold. `romdata.check_layout` refuses a ROM where the TM table, form
table, std-script mapping, hidden-item table, special-mart lists or the trainer party builder no longer decode,
instead of exporting nonsense from a build that moved a table.

## Where each field comes from

From the ROM being described (the release ROM by default):

| Data | Source | Notes |
|---|---|---|
| species stats, types, abilities, held items, catch rate, gender, egg groups, growth, EV yield | `a/0/0/2` | |
| level-up moves, evolutions, tutor compatibility, egg moves | `a/0/3/3`, `a/0/3/4`, `data/tutor_moves.narc`, `data/egg_moves.narc` | evolutions: trade-evolutions-levelup now comes from the data; the hand-applied `BUILD_EVOLUTIONS` override is removed |
| moves, items (price, pocket), Pokédex height/weight | `extra/new_move_data.narc`, `a/0/1/7`, `a/0/7/4` members 0/1 | |
| wild encounters, Headbutt, Bug-Catching Contest, Safari, calendar slots | `a/0/3/7`, `a/2/5/2`, `mushi_encount.bin`, `a/2/3/0`, arm9 0x020F6A64 | |
| trainers, parties, natures, genders, friendship | `a/0/5/5`, `a/0/5/6`, arm9 class-gender table and party builder | EV order read from the party builder's code (below) |
| gifts, statics, trades, tutors, marts, item balls, hidden items, trainer locations and conditions | scripts `a/0/1/2`, events `a/0/3/2`, `a/1/1/2`, arm9 tables | script fixes (tutors, Forest of Time guard, Pryce's rule) flow through; script evidence offsets (`evidence.pc`) are offsets in the described ROM |
| TM list, forms, fossils, Pickup | arm9 tables, overlay 22, overlay 14 | Pickup: the honey-gather fix rewrites the collector, the reader now accepts its gate (0x0222BD38) as well as the Chinese one (0x0222BD2A) |
| names (species, moves, items, abilities, types, trainers, classes, trade nicknames) | the ROM's message banks 232, 739, 219, 711, 724, 719, 720, 198 | `Rom.bank`: decoded with `msgtool` and the build's charmaps; the 9-bit packed trainer names lose their `{COMPRESSED}` marker. Fuller forms of shortened names still come from the glossary (`full_names`) |
| move, ability and item descriptions | banks 738, 712, 218 | `Rom.bank_full`: the ROM's text as `en`; a string still Chinese in the ROM keeps the workspace's `en`, so no Chinese leaks |
| dialogue options in trainer/gift conditions, NPC first lines (landmarks) | the map's message bank | |

Still from the workspace, the Chinese ROM or curated files (deliberately):

| Data | Source | Why |
|---|---|---|
| `zh` names (crossref name index) | `work/translate/banks/*.json` `zh` | Chinese source text |
| description `translationStatus` | workspace bank row | review status is a workspace notion; it can describe a newer English line than the ROM's |
| map names, area grouping, slugs | `work/translate/bank_maps.json`, `work/docs/place_names.json`, `places.py` | the build does not change map headers; changing the source of names would move slugs/URLs |
| "changed vs HeartGold" comparisons | the USA ROM (`vanilla_evos`, `species_comparisons.py`, `move_comparisons.py`) | unchanged |
| hack-bug notes in reviewed lists | `work/tools/site/extra_sources.json` etc. | an entry can now say `"fixedBy": "<fix id>"` with `"withFix": {...}`: when `romdata.fix_in_rom` finds that fix's arm9 code in the ROM, only the `withFix` fields apply. Used for petilil-hisuian-lilligant (Petilil, Hisuian Lilligant) |
| tutor notes `TUTOR_NOTES` | `export_data.py` | keyed by (move taught, script file), so they disappear by themselves once a fix teaches the promised move (rc8: Blackthorn, Saffron) |
| quest links | `guide/*.md`, chapter files | the exporter now writes chapter links directly (relink_guide's map from `sync_guide.py`), so its output equals the committed data; run `sync_guide.py` first (`build.py` does) |
| author workbook reconciliation | `reconcile_references.py` with `R.Rom()` (Chinese) | reads only encounter tables, identical in the Chinese and rc8 ROMs; the workbooks describe the hack. Its tutor claims are compared with the Chinese ROM's tutors (row 585 is pinned to Flail); `battle_reference.fixed_tutor_note` joins a claim whose configured move no longer has a tutor to the tutor in the same place that now teaches the claimed move, as matching, with the old audit note marked as the original hack's |

## Site-side patches removed or made ROM-driven

- `export_data.BUILD_EVOLUTIONS` / `apply_build_evolutions` (Boldore Lv 35, Gurdurr Lv 40): removed, the release
  ROM's evolution records say so. With `--rom cn` the pages show the hack's trade evolutions again.
- Trainer EV order (`romdata.parse_trpoke`): the reorder `(0, 1, 2, 4, 5, 3)` was not a site-side patch but the
  Chinese party builder's behaviour (it copies record bytes 20..25 into MON_DATA fields 13..18 = HP, Atk, Def, Spe,
  SpA, SpD). rc8 has the same code, so rc8's EVs are unchanged. The fix trainer-ev-order (D-2552, rc9) changes the
  builder's three `movs r1, #field` immediates. `romdata.trainer_ev_order` now reads those immediates (as
  `work/advanced-ai/testbench/versus/aiteams.py` does) and `parse_trpoke` applies the order it finds, so the same
  code is right for the Chinese ROM, rc8 and rc9: PLAN_RC9 section 3's "drop the reorder" happens by itself when the
  data is exported from the rc9 ROM. No hard-coded switch.
- Petilil / Hisuian Lilligant hack-bug notes: gated by `fixedBy` (above).

## Export fix found on the way

`gen_docs._cond_paths` (the "ways into a battle" walk behind trainer conditions) followed a GoTo back into a block
already on its path. pryce-weather-rule replaces Pryce's 28 species checks with a loop; the walk spent its depth
limit going round the loop and lost "before you have the Glacier Badge" (Pryce's Gym battle would have shown no
condition). Back edges into blocks already on the path are now skipped. The Chinese ROM's output is unchanged
(checked: `export_data.py --rom cn` and `gen_docs.py --rom cn` give byte-identical output before and after).

## Regression checks done

- `--rom cn` before and after the change: the site data is identical except `meta.rom` and the removed Boldore/Gurdurr
  override (the pages now show the hack's own trade evolutions for the Chinese ROM); the docs are identical except the
  README's regeneration commands.
- Before this change the committed data was already out of date against the Chinese export in ways that came from the
  workspace, not the ROM: retranslated descriptions, trainer class "Evil Sci.", trainer names "Beedrill swarm", menu
  options. Those are post-rc8 workspace edits; reading the text from the ROM keeps them off the site until they ship.

## Diff of the regenerated rc8 data (committed data -> release:v1.0.0-rc8)

| File | Category | Count | Explained by |
|---|---|---|---|
| species.json | tutor move lists: Flail (175) replaced by Play Rough (583) | 176 species | tutor-blackthorn-play-rough (D-2356, enabled in rc8) |
| tutors.json | Blackthorn tutor: Flail -> Play Rough; the hack-bug note is gone; the workbook's Play Rough claim (row 585) now matches, its audit note reads "Original hack (fixed in this game): ROM teaches Flail here (D-1305)" | 1 entry removed, 1 added | tutor-blackthorn-play-rough |
| tutors.json | Saffron Dojo "Charge" tutor entry removed (the Volt Switch entry stays) | 1 | tutor-saffron-volt-switch (D-2357) |
| species.json | Petilil: Black Belt evolution no longer "never"/blocked, note says the patch fixes it | 1 species (evoTo, evoNotes) | petilil-hisuian-lilligant (D-2334) via `fixedBy` |
| species.json | Hisuian Lilligant: how to get it "Evolve Petilil" instead of the Sun Stone workaround; evoFrom not blocked; note | 1 species (how, acquisition, otherSources, evoFrom, evoNotes) | petilil-hisuian-lilligant |
| items.json | Black Belt `evolutionUses`: Petilil -> Hisuian Lilligant no longer blocked | 1 item | petilil-hisuian-lilligant |
| trainers.json | Forest of Time trainer #763: both battles "only in some story branches" | 1 trainer | forest-of-time-sammy-guard (D-2370): the scenes now run only while the Sammy chapter is active |
| species.json | Raticate (#20) S.S. Anne trade: evidence offset 4969 -> 4972 in script 156 | 1 | reward-qty's script insert shifts the file's offsets |
| meta.json | `rom` record added | 1 | this change |
| species.json, areas.json | Lavender Town Mr. Fuji: quest links now also list "Pokémon Tower: side battles and extras" | 2 | the guide (`guide/*.md`), not the ROM: the committed data was exported before that guide edit |

Not in the diff, as expected: Boldore/Gurdurr (already shown at Lv 35/40 by the removed override), descriptions and
names (the committed data already matched rc8's text), trainer EVs (rc8 keeps the Chinese order). Fixes whose effect
is code or presentation only (battle sounds, freezes, price checks, Honey Gather, overworld sprites, the Bag's Use
entry) do not change exported data.

Docs (`work/docs`, `work/notes/docs_crossref.md`): the same tutor, Petilil, Forest of Time and Boldore/Gurdurr
changes, plus the ROM named in every page header and the README's source paragraph.

**Unexplained differences: none found.**

## Open questions

1. `gen_docs.py` now also defaults to the release ROM, so `work/docs` (shipped in the release ZIP) describes the
   released game. `work/notes/docs_crossref.md` (a maintainer cross-check of hack findings) is generated in the same
   run and so also reads the release ROM. Should the crossref keep reading the Chinese ROM instead?
2. Code-only hack bugs that later fixes remove are invisible to the exporter. Curated notes that describe them
   (guide known issues, `pokemon_acquisition_notes.json`, the damage calculator's `site/src/lib/calc/mechanics/ohg.ts`,
   e.g. Sonic Boom/Dragon Rage dealing 1 HP, which rc9's fixed-damage-moves changes) still need a hand update or a
   `fixedBy` gate at each release. Should `fixedBy` be extended to those files?
3. "English Pokédex order" (PLAN_RC9 section 3): the exporter reads only members 0/1 (height, weight) of `a/0/7/4`;
   the site has no in-game sort order. Confirm nothing on the site should follow dex-english-initials.
4. Map and area names still come from `bank_maps.json` (a workspace snapshot) rather than the ROM's map-name bank;
   switching would risk changing slugs/URLs.
