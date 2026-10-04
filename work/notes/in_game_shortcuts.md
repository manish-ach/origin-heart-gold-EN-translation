# In-game shortcuts: Origin HeartGold v4.0.3

Audited 2026-10-04 against the untouched Chinese hack (ROM CRC32 `59CBBDAA`). This is the source inventory for a website controls page. Button names refer to the Nintendo DS buttons, regardless of an emulator's keyboard or controller bindings.

**Coverage:** reproduced the generator, the stats panel, soft reset and both title-screen combinations below. Also swept 68 single-button/two-button cases across the field and stats screens, searched the translated message banks, and scanned ARM9 and all 120 overlays for input-handler leads. This is not proof that every screen, button sequence, accessory mode or unlock condition has been exhausted. In particular, text in a debug bank does not establish that its menu can be opened.

## Website-ready shortcuts

These entries were reproduced in the original Chinese ROM using isolated emulator states. Button mode was 0 (normal) in the field test state. Describe the generator separately from ordinary gameplay controls: it creates Pokémon.

| Where | Buttons | What happens |
|---|---|---|
| In the field, with normal movement available | **Hold SELECT, then press X** | Opens the Pokémon configuration/generator menu. |
| Pokémon generator, outside field editing or a preview | **START** | Generates the configured Pokémon. **X is not required.** A successful party addition displays a confirmation. |
| Pokémon summary → stats/moves page | **L** | Opens the panel showing IVs and EVs together. It does not open from the first summary page. |
| IV/EV panel open | **L or B** | Closes that panel and restores the ordinary stats-page view. |
| Title screen, displaying “PUSH START BUTTON” | **Down + X + Y** | Opens the microphone test. |
| Title screen, displaying “PUSH START BUTTON” | **Up + B + SELECT** | Opens the delete-save confirmation. Confirming deletion erases the save; opening the prompt alone does not. |
| During play | **L + R + START + SELECT** | Soft-resets the game. Unsaved progress is lost. |

**Hint discrepancy (D-1458):** the Chinese tip says L/R displays IVs and EVs. In this normal-button-mode test, R did nothing with the panel either closed or open. The table deliberately gives the reproduced L control. The translation and game behavior were left unchanged; other button modes still need checking.

### Using the Pokémon generator

| Buttons | Context and action | Evidence |
|---|---|---|
| Up / Down | Select a field on the current page. | Input handler; Up used in the edit check. |
| L / R | Previous / next configuration page. There are eight pages. | Input handler; R page change reproduced. |
| A | Begin editing the selected field. | Reproduced with species. |
| Up / Down while editing | Increase / decrease the selected value. | Handler; species 1 → 2 reproduced with Up. |
| Left / Right while editing a numeric field | Move between editable decimal positions, where supported by that field. | Input handler; not separately exercised. |
| A / B while editing | Accept / cancel the field edit. | Handler; A acceptance reproduced. |
| START | Generate the configured Pokémon, while browsing fields. | Reproduced without X. |
| A after the generation confirmation | Dismiss the confirmation and return to configuration. | Input handler. |
| X / Y while browsing fields | Show two variants of the configured Pokémon's encounter-text preview. | Both previews reproduced; these are not generation buttons. |
| X or Y while viewing that preview | Leave the preview. | Input handler. |
| B while browsing fields | Close the generator. | Reproduced. |

Opening the menu is specifically **SELECT held + a new X press**. “X + SELECT” is convenient shorthand, but holding X first and only then pressing SELECT need not trigger it. The originally reported “X + START to generate” works because the generator checks START before its X/Y preview handling.

Generation also has a PC Box branch and a separate Box confirmation in the original code/text. The successful party branch was reproduced; overflow with a full party and full PC was not tested. Do not promise that generation always goes into the party or that it always succeeds.

## Controls documented by the game

These are useful additions to a controls page, but were not independently exercised in this audit.

| Where | Buttons | Action | Source |
|---|---|---|---|
| Field, after obtaining the ability to run | Hold B | Run. The touchscreen Sprint button is another option. | `a027/0542#8` |
| An evolution in progress | B | Cancel the evolution. | `a027/0444#82`, `a027/0387#16` |
| Pokégear map | X over a location | Display that location's information. | `a027/0789#0`, `a027/0184#15` |

### EV Allocator: requires the item

The **EV Allocator** is item 745. The existing item/source audit lists it among items with **no acquisition source and no script use** (`work/notes/docs_crossref.md`). Its menu text and graphics exist, but this audit did not establish ordinary in-game access. Keep this in an advanced/item-specific section, not among universally available field shortcuts.

| Buttons | Action stated by the menu | Source |
|---|---|---|
| SELECT | Clear the current Pokémon's EVs, with a confirmation prompt. | `a027/0815#12`, `#14` |
| START | Restore the EVs the current Pokémon had on entering the screen, with a confirmation prompt. | `a027/0815#13`, `#15` |
| X / Y | Switch Pokémon. The text does not specify which direction belongs to each button. | `a027/0815#16` |
| L / R | Adjust EVs in steps of 64. The text does not specify the sign for each button. | `a027/0815#16` |

The menu also contains +4, +64, −4 and −64 labels (`#8–11`) and a message requiring all EVs to be allocated (`#7`). Those labels alone do not establish a D-pad mapping or the exit rules; do not invent either.

## Code leads that are not yet website instructions

| Combination / lead | What is established | What remains unverified |
|---|---|---|
| L + Down + X in the Pokéwalker interface | Overlay 103 explicitly checks all three held bits at `0x021EAA1C`. Menu handlers call it and start a separate operation. | Exact user-facing steps and effect in this hack, accessory prerequisites and successful completion. |
| R + Up + SELECT in the Pokéwalker interface | Overlay 103 checks all three held bits at `0x021EAA40`. The following operation additionally requires a save-state condition equal to 2 at `0x021EA9C4`. | Exact recovery behavior and a suitable paired-Pokéwalker save. Do not present it as an unrestricted field shortcut. |
| L + R held, then X in an overlay 8 routine | `0x021E5634` checks L/R held plus newly pressed X and advances an internal script pointer. | A reachable caller, the relevant screen and the effect. Do not call this a general cutscene-skip shortcut. |
| Debug menus in banks 0152, 0156, 0164, 0173 and 0175 | Many testing controls and menu labels survive in the ROM. The generator is demonstrably reachable. | Access to the other menus. Their presence does not make all their controls supported shortcuts. |
| Other PC, battle, multiplayer and minigame controls | Outside the two-screen runtime sweep. | Screen-specific testing before describing a universal or exhaustive controls list. |

## Evidence and reproducibility

All raw dumps, screenshots, emulator states and scratch probes stay in ignored `work/build/shortcut-audit/`. No ROM was built or modified, no tool was downloaded, and the probes used a ROM symlink with emulator save output confined to that scratch directory. They started from the existing `work/build/generator-verification/cn-before.dst` state. Delete-save confirmation was never accepted.

### Static references

- **Generator entry:** overlay 1, `0x021E5BA4–0x021E5BC8`. Reads held keys at `gSystem + 0x44`, checks SELECT (`0x0004`), then reads newly pressed keys at `+0x48` and checks X (`0x0400`). Calls overlay 2 `0x02248C7C`.
- **Generator text:** overlay 2 loads `a027/0164` at `0x02248CAE`. Message `#127` is the party confirmation, `#128` the Box confirmation. The menu is not unidentified hardcoded text.
- **Generate:** overlay 2 `0x02248F0E–0x02248FC8` checks START (`0x0008`), then calls `0x02249238`. It does not require X.
- **Generator navigation/editing:** overlay 2 `0x02248EB4–0x02249154`; L/R handling at `0x02248FEA–0x0224902E`, previews at `0x02249030–0x02249062`, edit handling at `0x02249074`.
- **Stats-screen L:** ARM9 `0x02087CD4–0x02087CFE` checks L (`0x0200`) and summary page 1. The game's tip at `a027/0444#83` says L/R; use the tested, context-specific instructions above rather than expanding that into an assumed global toggle.
- **Title combinations:** overlay 56 `0x021E4B9E` checks the full `0x0046` mask (Up/B/SELECT); `0x021E4BCA` checks `0x0C80` (Down/X/Y). The same masks also occur at `0x021EA086` and `0x021EA0A0`.
- **Button mapping:** `gSystem = 0x021D0094`; normal held/new/repeat words are `+0x44/+0x48/+0x4C`. Input remapping lives in ARM9 `0x0201AE08–0x0201AF2C`; non-default button modes need their own checks.

The generator entry/controls, stats handler, title shortcut handler and Pokéwalker chord-handler byte ranges were compared against `work/build/origin_hg_v4.0.3_en_wip.nds`: **all five ranges match the Chinese ROM exactly**. This supports behavior parity for those handlers; it is not an English-ROM playthrough or a visual-layout check. The precise ranges and SHA-256 values are in local `code-comparison.json`.

### Runtime artifacts

- Generator: `opened.png`, `start-alone.png`, `page-r.png`, `edit-species.png`, `preview-x.png`, `preview-y.png`, `exit-b.png`.
- Stats: `summary.png`, `summary-L.png`, `summary-R.png`, `stats-L-twice.png`, `panel-before.png`, `panel-then-L.png`, `panel-then-R.png`, `panel-then-B.png`.
- System/title: `reset-800.png`, `title-ready.png`, `title-UP-B-SELECT.png`, `title-DOWN-X-Y.png`.
- Sweep: `matrix.json` and `matrix.log`; 34 cases each in the field and stats screen: L/R/X/Y/START/SELECT individually, then all 28 pairs from A/B/X/Y/L/R/START/SELECT. Simultaneous press/release tests do not cover every ordering, hold duration, three-button combination or D-pad combination.
- `key-readers.txt` records 494 candidate contexts from the static scan. These are leads, not 494 verified shortcuts. The scan can miss indirect/data-driven input handling and can find non-code data decoded as instructions.

The two-screen sweep found no second generator-entry combination. EV Allocator text was not loaded by any tested combination. Absence in this bounded test is not proof of absence elsewhere in the game.
