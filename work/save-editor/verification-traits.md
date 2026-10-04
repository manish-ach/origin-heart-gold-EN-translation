# Party traits: verification and remaining scope

English Origin HeartGold v4.0.3 only. PC boxes, story flags, quests and progression
editing are excluded. All browser inputs remain save-only; no ROM is requested.

## Implemented behavior

Shiny uses the hack's native logical B+20 bit31 override. It does not regenerate
PID or trainer ID, reorder encrypted blocks, reseed party data or change nature,
gender, ability, form, nickname or any other identity-dependent value. The nearby
nature bits25–30 are preserved. Naturally shiny Pokémon remain shiny; the editor
disables the non-shiny choice and the mutation function rejects it explicitly.

Pokérus offers None / Infected / Cured. Native D+26 high nibble retains strain;
low nibble is remaining days. New infections use one day, retaining an existing
strain or choosing strain1 when none exists. Cured retains strain and clears days;
None clears both. Reselecting the current status leaves the exact byte unchanged,
including unusual existing values. Native runs confirmed old fixture dates can
cure a new one-day infection during boot; the UI explains that elapsed days since
the last save can cause immediate curing. The editor never changes the save clock.
The UI does not claim verified infection
propagation or EV-bonus behavior. Native evidence is in `research-traits.md`.

The full suite passes **203 tests**, including local English-ROM parity (no skips).

## Repeatable checks

From the worktree root:

```sh
ORIGIN_EN_ROM=/path/to/English.nds npm --prefix work/save-editor test
node work/save-editor/scripts/verify-traits-local.mjs /path/to/saves work/save-editor/local/traits-new
```

Synthetic tests cover every shuffle selector, all 256 existing disease bytes,
natural shininess on either side of XOR8, both override states, malformed inputs,
nonzero-offset buffers, exact no-ops, shiny restoration, and independent operation
composition with moves and nature/stat changes. Every non-target logical byte and
the entire encrypted party tail must survive. Nature edits preserve the shiny bit.

Six existing saves / 13 party Pokémon pass local integration checks. These assert
only the chosen Pokémon's boxed checksum/ciphertext and selected general-block CRC
change; backups, counters, other party members and all unrelated save regions are
preserved. Every original file's hash remains unchanged. Fixtures and reports stay
in ignored `local/traits-fixtures-verified/`.

## Native verification result (2026-10-04)

`local/traits-runtime-en-fresh/report.json` passes with **zero gaps** and in-game
save counter **9 → 10**. All six party members retain expected traits, stats and
moves after save/reset/reload. Input ROM/save hashes are unchanged. Actual native
getter returns were audited in both phases (25 calls loaded, 23 reloaded): shiny
on/off correct for all six, infected true for slots1/4, cured true for slots2/5,
and neither state for slots3/6. Slot1's summary visibly displays the shiny star
and PKRS badge together. Hooks only observe; they do not alter game memory.

Earlier exploratory runs are retained under ignored `local/`. They exposed native
elapsed-day curing on old saves and a menu-navigation issue in the harness. The
final run uses a fresh in-game export, reapplies traits with the same editor codec,
and retains strict expected-byte checks. No clock or calendar fields were edited.

## Native verification procedure

Use an existing local English build and a freshly saved in-game fixture when
checking the active state, because elapsed-day processing is intentional:

```sh
/path/to/poke/.venv/bin/python work/save-editor/scripts/verify-runtime.py \
  --repo /path/to/poke --rom /path/to/English.nds \
  --save work/save-editor/local/traits-new/full_bag_6mons.sav \
  --expect work/save-editor/local/traits-new/full_bag_6mons.sav.moves.json \
  --expect-stats work/save-editor/local/traits-new/full_bag_6mons.sav.stats.json \
  --expect-traits work/save-editor/local/traits-new/full_bag_6mons.sav.traits.json \
  --observe-traits --persistence --out work/save-editor/local/traits-runtime-new \
  --timeout 480
```

The harness must report no gaps, a higher in-game save counter, preserved traits,
stats and moves after reset/reload, and unchanged input ROM/save hashes. Trait
hooks observe the actual native shiny/infected/cured getter return values for
bounded party addresses and PIDs. Cured Pokémon short-circuit the infected helper
in the native summary; a true cured result proves that state without a redundant
infected call. No runtime memory is written.

## Browser checks (2026-10-04)

In a fresh page, select `full_bag_6mons.sav` without any ROM:

1. Choose Shiny, choose Infected, and enter a money draft of 123456. Apply Shiny:
   Pokérus and money drafts survive, and edited export remains disabled.
2. Enter EV HP 200 and Apply Pokérus: EV and money drafts survive. Applied infection
   displays one day remaining. Discard money and EV drafts: export is enabled.
3. Apply Cured, then None; both display correctly. Apply Not shiny: exact original
   save bytes are restored and edited export is disabled again.
4. A pending shiny draft blocks party switching and survives Apply IVs. Discard
   resets only shiny, leaving the applied IV change available for export.
5. Browser warning/error logs are empty. The page explicitly excludes PC boxes and
   story/quest editing. Each trait has an independent Apply/Discard form.

Browser download-file delivery remains a pre-existing unverified release check;
“Download requested” deliberately does not assert successful delivery.

## Remaining focused priorities

- **Held items:** searchable give/remove controls, with mail handling explicitly
  constrained. This is the clearest missing link between party and inventory.
- **Nickname and friendship:** common party edits, after verifying name encoding
  and native friendship behavior/limits.
- **Heal and reorder:** restore HP/status/PP and rearrange the existing party,
  preserving all per-Pokémon and follower relationships.
- **Release polish:** change summary/undo for applied edits, leave-page protection,
  and end-to-end downloaded-file reopening across supported desktop/mobile browsers.

Ability selection, species/form changes and egg editing are optional later work,
requiring separate Origin-specific research. They are not prerequisites for this
focused editor. No PC-box or progression work is proposed.
