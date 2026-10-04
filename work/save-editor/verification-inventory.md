# Inventory verification procedure

> Historical ROM-input milestone. The current editor supports English Origin v4.0.3
> with bundled reference data and requires only a save. See `verification-reference.md`
> for the current workflow and verification; Chinese support is not in scope.

Run every command from the editor worktree root. Do not download/build ROMs or
replace source saves. All native evidence belongs in ignored `local/` folders.

## Automated gate

1. Run `npm --prefix work/save-editor test`. Expected current result: **154 passed**.
2. Run `scripts/verify-inventory-local.mjs` as documented in README with an
   existing ROM, save directory, and new ignored output directory.
3. Run `scripts/verify-runtime.py --expect-inventory ... --persistence` for both
   untouched Chinese and English ROMs against the generated full-bag fixture.
4. Require report `status: passed`, empty `gaps`, `inventory_expectation_check:
   checked`, `in_game_save_reload: passed`, source hashes unchanged, and a native
   counter increase. A missing emulator/snapshot or timeout is incomplete.
5. Check `observed_inventory`, `reloaded_inventory`, `native_export_inventory`
   against `expected_inventory`: money, each of eight pockets, and shortcuts.
   Party move identities and full-save byte allowlists are additional controls.

The integration script checks quantity edits, removes and adds independently in
each of eight pockets for every fixture. The native fixture combines the final
results. Exact no-op export and each operation's allowable byte differences are
checked before launching the game. Native observations read bounded owner data;
they do not write emulator memory or use save-file decoding as a substitute for
runtime load evidence.

## Browser checklist

Use a separate temporary tab at http://127.0.0.1:4173 and reload after a build.

1. Import `route1_townmap.sav`. Without a ROM, inspect bag and edit money; item
   controls stay disabled. Enter 10000000: Apply must reject and edited download
   remains disabled. Enter 9999999 and Apply: value persists and export enables.
2. Select the existing English Origin ROM. Verify named choices; Chinese names
   outside Latin encoding intentionally fall back to numeric IDs.
3. In Items, Add item; enter quantity 0: Apply must reject. Enter 999 and Apply.
   Remove that stack and Apply: it disappears. Empty pockets are supported.
4. Make simultaneous drafts in Items, Medicine, money, move PP, IV HP and EV HP.
   Apply only Items; every other draft value remains. Switch pockets and back:
   unsaved pocket drafts remain. Apply money and then IVs; EV/move drafts remain.
   Download stays disabled until all pending groups are applied/discarded.
5. In TMs & HMs add a row: 100 rejects, 99 accepts. All other pockets cap at999.
6. Import `full_bag_6mons.sav`: Items is at165 and Add is disabled. In Battle
   items select the same ID in two rows: Apply rejects duplicate stacks. Discard
   restores both original selections. Core tests also reject wrong-pocket IDs.
7. Export unchanged must still represent original bytes (codec tests assert
   this). Edited export is enabled only for applied changed bytes. Do not claim
   browser-file delivery based on a button click; the current in-app observer
   has not confirmed actual download completion.
8. Check console errors. Close the temporary test tab, leaving user tabs intact.

Executed 2026-10-04: money rejection/application, item add/apply/remove, zero and
TM100 rejection, full-pocket blocking, duplicate rejection/discard, cross-group
draft retention, and export readiness passed; no console errors. TM99 acceptance
is covered by core and native tests, rather than a separate browser submission. Browser download completion remains unverified. The preview serves only
app assets; ROMs, saves and local reports are excluded from the HTTP server.

## Coverage limits

- Native CN/EN load+save+reset verified 9,999,999 money and all eight edited
  pockets, including max quantities and add/remove outcomes; counters8→9.
- Shortcut cleanup/slot2→slot1 shift is verified by synthetic tests against
  native unregister semantics. Available real fixtures had shortcuts0/0.
- Arbitrary item effects, item obtainability, placeholder IDs, quest state and
  possession-dependent story behavior are not verified or modified by the editor.
- Bag mail stacks are supported; held-mail message content, Apricorn container
  counters, coins and Battle Points are separate systems and are not edited.
