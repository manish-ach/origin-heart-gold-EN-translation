# Name selection verification

> Historical ROM-input milestone. The current editor supports English Origin v4.0.3
> with bundled reference data and requires only a save. See `verification-reference.md`
> for the current workflow and verification; Chinese support is not in scope.

Run from the worktree root:

```sh
npm --prefix work/save-editor test
node work/save-editor/scripts/verify-names-local.mjs /path/to/English.nds /path/to/Chinese.nds /path/to/save.sav
```

2026-10-04: 161 automated tests pass. Real English and Chinese ROM checks with
`full_bag_6mons.sav` pass: all 921 move metadata records and 790 item pocket
mappings agree; choosing move/item by name produces exactly the same bytes as
the corresponding numeric edit. No-op, empty slot, export/reparse, and source
preservation pass. The script writes no saves or game text.

English ROM: 902 named move choices, 1,025 named species, 768 named items before
pocket filtering. Chinese ROM: zero English names, correctly reported without
inventing translations. Name banks are a/0/2/7 members 219, 232, 739. Move PP
comes from hash-verified extra/new_move_data.narc (921 records of 40 bytes, PP
at offset 5). The old a/0/1/1 table is stale and is not used.

Browser checklist (passed in the in-app browser):

1. Import a save and English ROM. Party displays species/move names including
   expanded species. Search `flame`: four matching moves. Typing search leaves
   ROM picker enabled: search alone creates no edit draft.
2. Choose Flamethrower: PP becomes 15, PP Ups zero. Submit PP16: rejection; PP15:
   successful apply. Selecting the already-selected move leaves no pending draft.
3. Choose Medicine, search `potion`: only matching medicine choices. Duplicate
   stack selection is rejected. Full pocket disables Add.
4. Remove one stack, search/select Super Potion under New item, Add, then Apply.
   Pocket applies. A concurrently entered money draft survives and blocks edited
   export; discarding it re-enables export. Existing applied move remains named.
5. Browser console: no application errors during successful checks. Native
   select controls supply keyboard semantics; a scripted ArrowDown follow-up
   hit a browser-tool timeout, so keyboard automation is not claimed as passed.

Regression tests cover name search accents/case/apostrophes, duplicate names,
unknown identifiers, search-without-edit, same-selection no-op, parser bounds,
expanded indices, placeholder exclusion, PP Ups/empty moves, and all prior
save/stat/inventory integrity checks. Duplicate names are distinguished by a
secondary identifier in the choice label. Ordinary names never require IDs.

No save binary mutation routines changed. Existing Chinese/English emulator
persistence evidence remains applicable, augmented by named-vs-numeric exact
byte equivalence; no new emulator run was needed. Actual browser download-file
delivery remains outside this milestone (existing observer limitation).

Limits: English names require the user's English Origin ROM, which can be used
with Chinese saves. Names retain in-game abbreviations; full canonical aliases
are not bundled. Learnset legality and item obtainability are not enforced.
Unknown current values remain intact; an Identifier detail provides diagnostics.
