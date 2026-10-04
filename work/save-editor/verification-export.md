# Actual browser download → reopen → play

Scope: English Origin HeartGold v4.0.3 party and inventory editing. This check uses
actual files saved by the browser, not a CLI-generated substitute. No ROM build,
new dependencies, story editing or PC-box editing is involved.

## Repeatable browser procedure

Use an existing local English build and the six-party `full_bag_6mons.sav` fixture.
Keep originals untouched. Copy the fixture into ignored `local/` with a unique
basename, and record the original and copy SHA-256 before opening the page. The
scenario expects slot1 Charmeleon at level9, moves ThunderPunch / Swords Dance /
Rolling Kick / Poison Sting, no Pokérus, and Scope Lens first in Items.

1. Open the editor and select the isolated copy through its file chooser. No ROM
   selection is needed. Click **Export unchanged**. Find that exact basename in
   the browser's download destination and require 524,288 bytes and the source
   SHA-256. A button click or download-event timeout alone is not proof either way.
2. On slot1, select **Flamethrower** for move1, set PP12 and PP Ups1, Apply moves.
   Set IV Attack31 and Defense31, Apply IVs. Set EV HP200 and Speed100, Apply EVs.
   Set level25 and Modest, Apply level & nature. The preview must show HP84,
   Attack44, Defense41, Sp. Atk57, Sp. Def39 and Speed59.
3. Set Shiny and Apply Shiny; set Pokérus Cured and Apply Pokérus. Cured is used
   deliberately because this fixture is old: active infection can expire on load
   through normal elapsed-day processing. Active infection already has separate
   native coverage in `verification-traits.md`.
4. Set money123456 and Apply money. Set first Items stack (Scope Lens) quantity7.
   Confirm edited export is disabled with that pending draft. Apply pocket and
   confirm export becomes enabled. Click **Download edited save**.
5. Record the actual downloaded file's path, length and hash. Reopen that exact
   file with the editor's chooser. Require successful checksums, all choices
   retained, the six preview stats above, and edited export disabled until a new
   change. Export unchanged again: this second browser file must exactly match
   the edited download. Check the browser console for application errors.
6. Audit the actual downloaded files with the read-only script below. It derives
   untouched values from the original and explicit changes from this scenario;
   it never creates or patches a save. It rejects any changed bytes outside
   slot1, money, the first stack's quantity and the selected general checksum.
7. Pass **the downloaded path itself** to the native harness below. Require the
   game to load, open summaries, save in-game, reset and reload; require a higher
   save counter, unchanged input hashes, matching all six party states, all eight
   pockets, money and trait getter returns. Audit the native copied records to
   check PP and PP Ups in addition to the harness's move-ID checks.

Run every command from the editor worktree root. Replace paths with the actual
browser downloads and use new ignored output directories on each run:

```sh
ORIGIN_EN_ROM=/path/to/English.nds npm --prefix work/save-editor test
node work/save-editor/scripts/verify-browser-export.mjs \
  /path/to/isolated-source.sav /path/to/download-unchanged.sav \
  /path/to/download-edited.sav work/save-editor/local/export-new/audit
/path/to/poke/.venv/bin/python work/save-editor/scripts/verify-runtime.py \
  --repo /path/to/poke --rom /path/to/English.nds \
  --save /path/to/download-edited.sav \
  --expect work/save-editor/local/export-new/audit/moves.json \
  --expect-stats work/save-editor/local/export-new/audit/stats.json \
  --expect-traits work/save-editor/local/export-new/audit/traits.json \
  --expect-inventory work/save-editor/local/export-new/audit/inventory.json \
  --observe-traits --persistence \
  --out work/save-editor/local/export-new/runtime --timeout 480
node work/save-editor/scripts/verify-browser-export.mjs \
  /path/to/isolated-source.sav /path/to/download-unchanged.sav \
  /path/to/download-edited.sav work/save-editor/local/export-new/final-audit \
  work/save-editor/local/export-new/runtime/report.json
```

## Browser result (2026-10-04)

The standard app buttons in the **Codex in-app browser** produced real files in
`~/Downloads/`. Its `waitForEvent('download')` observer timed out even when the
file had successfully arrived. This was an observer limitation, not a failed
export. No application fix was necessary. An exploratory persistent-link change
was reverted before the final run. The final run used the unchanged app Blob /
anchor-click implementation; no downloadMedia, shell fetch or synthetic download
was used to obtain these files.

Evidence lives under ignored `local/export-e2e-20261004/`:

| Artifact | SHA-256 |
| --- | --- |
| Original fixture, isolated `browser-e2e-20261004.sav`, and actual `browser-e2e-20261004-unchanged.sav` download | `b3aca10747cd0f1adc3d5852a50dddaaa36ed8680f5ba04012cfe3110faad90f` |
| Actual `browser-e2e-20261004-edited.sav` download and its browser re-export `browser-e2e-20261004-edited-unchanged.sav` | `70d03d3a866e54dea2d3d6789abadf004e119ca760d3abfaca2a1d6b962c3383` |

All three browser output files are 524,288 bytes. Reopening retains every selected
value above, with no browser warnings/errors. The audit finds exactly 144 changed
bytes, all allowed; backup mirrors, counters, other Pokémon, PC storage and all
unrelated bytes are preserved. The original fixture and isolated source stay
unchanged. The complete automated suite passes 203 tests, with zero skips.

This is one local desktop browser and one representative combined-edit scenario.
It does not claim coverage of Safari, Firefox, mobile download/import workflows,
emulator save-state formats or every inventory action in a single browser run.
Broader codec/inventory/trait coverage remains documented in the other reports.
The UI correctly says “Download requested” because browser delivery cannot be
confirmed reliably by page JavaScript.

## Native result (2026-10-04)

`local/export-e2e-20261004/runtime/report.json` reports **passed**, zero gaps and
in-game counter **8 → 9**. It uses the actual edited Downloads file as `--save`,
with SHA-256 `70d03d3a866e54dea2d3d6789abadf004e119ca760d3abfaca2a1d6b962c3383`.
All six complete decoded party records, including PP/PP Ups, match at load and
reset/reload. Money and all eight pockets match at load, reload and native battery
export. Fifty native getter observations include slot1 shiny=true and cured=true.
The summary screenshot visibly confirms Modest, level25, shiny Charmeleon.

The native saved file has SHA-256
`bd29c7efed2d760d185bfd0e681f1ce5ae05b712d4b2b0acd8a5811980b9381a`. It also
reopens successfully in the browser, showing counter9 and every selected edit
intact. Source saves and ROM remain unchanged. The read-only audit passes again
with the native report supplied; a negative control using the unchanged file as
the purported edited download is rejected.

No app or save-codec changes were required. Added only this procedure, the
read-only `scripts/verify-browser-export.mjs` audit, and README verification links.
Earlier milestone documents' “download unverified” statements describe their
historical scope; this report closes that gap for the tested desktop workflow.
