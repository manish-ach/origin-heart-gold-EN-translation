# Decision register: workflow

**Status (reviewed 2026-09-29): current.** The "PROGRESS.md import" and "Cut-over" sections are historical: the cut-over happened on 2026-09-28.

Every translation decision is recorded in one place. That covers names and terms, character voices, style, layout and content rules, and open questions. You can review them there and change them later without hunting through free text.

| File | What it is |
|---|---|
| `work/translate/decisions/decisions.jsonl` | **Source of truth.** One JSON object per line, with stable ids `D-0001`, `D-0002` and so on. Edit it only through the tool. |
| `work/tools/decisions.py` | CLI: `list`, `show`, `add`, `set`, `usages`, `rename`, `resolve`, `report`, `import-csv`, `import-progress`, `render-progress`. |
| `work/translate/decisions/DECISIONS.md` | Generated review document. It opens with the "Needs your review" section. |
| `work/translate/decisions/decisions.csv` | Generated spreadsheet for review. You can edit it and import it back. |
| `work/translate/decisions/DIGEST.md` | Generated compact digest (`render-progress --out work/translate/decisions/DIGEST.md`) for translator agents. |
| `work/translate/decisions/HACK_FINDINGS.md` | Generated report of the hack findings (`python3 work/tools/findings_report.py`), with the current English of each string. |
| `work/translate/decisions/rewrap/*.tsv` | Strings a `rename` could not finish on its own: re-wrap or check by hand. Created by the first `rename` that needs it (none so far). |
| `work/snapshots/banks_<time>_before_D-NNNN_rename.tgz` | Backup of the banks that a `rename` touched. |
| `work/tools/test_decisions.py` | Tests. Run them with `python3 -m unittest -v work/tools/test_decisions.py`. |

## Record fields

| Field | Meaning |
|---|---|
| `type` | One of: `term` (zh → en name or term), `voice` (character voice profile), `style`, `layout`, `content` (tone, censorship, motto/lyrics rules, softening), `technical`, `question`. |
| `subtype` | Free text. Common values: character, place, item, move, ability, species, nickname, role, trainer-class, organisation, catchphrase, badge, speaker-label, ui-term, phrase. Questions use question, verify-in-game, content-softening, context-note, hack-finding (suspected bugs in the hack, D-1195; listed in `HACK_FINDINGS.md` by `work/tools/findings_report.py`) or integrity. |
| `zh`, `aliases` | The Chinese term and its other forms. `usages` and `rename` search for all of them. |
| `en` | The chosen rendering. For rules and questions, the full text. |
| `rationale`, `alternatives` | Why this rendering was chosen, and which options were rejected. A `rename` adds the old rendering to `alternatives` automatically. |
| `scope` | `"global"`, or a list of banks such as `["a027/0445"]`. `usages` and `rename` stay inside the scope. |
| `refs` | Example strings, such as `a027/0445#110` or `a027/0445#151-242`. |
| `related` | Linked records. For example, a question lists the terms it mentions. |
| `source` | Who made the decision: `agent:B046-B047`, `coordinator`, `user` or `glossary`. |
| `status` | `accepted` = reviewed by a human. `provisional` = an agent's choice, not reviewed yet. `needs-review` = disputed or conflicting. `superseded` (with `superseded_by`). For questions, `open` or `resolved` (with `answer` and `decision_id`). |
| `confidence` | `high`, `medium` or `low`. Invented names, placeholders and guesses are `low`. |
| `conflicts_with` | Other records that render the same zh differently. |
| `origin_line`, `origin_section`, `origin_text`, `origin_hash` | Where the record came from in PROGRESS.md. `origin_text` is the whole original bullet, so nothing is lost. |
| `mentions` | Later PROGRESS.md lines that repeated the same decision, for example "(already used)". |
| `history` | Every change, as `{date, field, old, new, by, reason}`. |
| `review_notes` | Your comments from the CSV. |

## For translator agents: recording decisions

Read `work/translate/decisions/DIGEST.md` before you start. It lists every name, rule and voice. Look a term up with `python3 work/tools/decisions.py list --search 金婆婆`. Reuse existing renderings exactly.

Record each **new** decision as soon as you make it, in place of the old "append to PROGRESS.md".

```sh
D=work/tools/decisions.py
# a name or term (prints the new id, e.g. D-0590)
python3 $D add --type term --subtype character --zh 小爱 --en Amber \
    --rationale "Movie 1 (Mewtwo Strikes Back) clone girl; official name" \
    --ref a027/0331#12 --source agent:B048-B049 --confidence high
# add --alias 爱酱 for other zh forms and --alternative "Ai" for rejected options
# invented or uncertain names: --confidence low
# a rule
python3 $D add --type layout --subtype wrapping --source agent:B048-B049 \
    --en "SIZE-200% lines: at most 10 characters per line; split with {NEWLINE}."
# a character voice
python3 $D add --type voice --subtype character --title "Mr. Fuji" --zh 富士老人 --source agent:B048-B049 \
    --en "gentle, sorrowful old man; formal, few contractions"
# an open question (always with refs)
python3 $D add --type question --subtype verify-in-game --source agent:B048-B049 \
    --ref a027/0338#9 --en "SIZE-200% line shortened to ‘Spare Zapdos!’; check it fits at 2x in game."
# more examples for an existing decision
python3 $D set D-0335 refs+=a027/0476#4 --by agent:B048-B049 --reason "more uses"
```

- `add` refuses a term whose zh already has a *different* rendering, and names the existing record. Reuse that rendering. If you are sure it is wrong, add a question instead of forcing a new rendering. `--force` records a competing rendering, and both records are marked `needs-review`.
- If you add a term that already exists with the same English, the command prints the existing id and adds nothing.
- Never edit `decisions.jsonl` by hand. The tool locks the file, so concurrent `add`s are safe.
- Keep appending the batch ids and counts to `PROGRESS.md` → "Done". Only decisions have moved to the register.

## For the user: reviewing

1. Regenerate the review files: `python3 work/tools/decisions.py report`. This takes about 6 seconds, because it scans the workspace to count usages.
2. Open `DECISIONS.md`. Start with **Needs your review**:
   - open questions (answer them with `resolve`)
   - conflicts (`needs-review`)
   - low-confidence choices (invented names, placeholders)
   - every provisional agent choice, grouped by type and subtype
   - context notes (route/branch maps that need no action)

   Next come tables per term subtype, the voices, the rules, a "same English for different Chinese" list and a changelog. **Usage** `a/b (+c todo)` means that `a` of the `b` translated strings whose zh contains the term also contain the chosen English; `c` strings are untranslated. When `a` is much lower than `b`, run `decisions.py usages D-NNNN` to see the strings that differ.
3. Or review in a spreadsheet with `decisions.csv` (UTF-8). You can edit these columns:
   - `en`: for a term, this renames it everywhere (see below)
   - `status`: for example `provisional` → `accepted`, `accepted` in bulk, or `needs-review`
   - `confidence`, `subtype`, `rationale`
   - `review_note`: a free comment, kept in `review_notes`

   Leave the other columns alone. Then run:
   ```sh
   python3 work/tools/decisions.py import-csv work/translate/decisions/decisions.csv          # dry run: lists changes + rename diffs
   python3 work/tools/decisions.py import-csv work/translate/decisions/decisions.csv --apply --by user
   ```
4. Answer a question with `python3 work/tools/decisions.py resolve D-0497 --answer "It's Karen" [--decision-id D-0105] --by user`.

## Changing a decision

- **Record-only changes** such as status, confidence, rationale, scope or refs:
  `decisions.py set D-0138 status=accepted confidence=high --reason "checked the Violet Gym scene" --by user`.
  Use `field+=value` or `field-=value` to change a list, and `field=null` to clear a field. Every change goes into `history`.
- **A different English name for a term:** always use `rename`, never `set en=`:
  ```sh
  python3 work/tools/decisions.py rename D-0335 --en "Granny Gold" --reason "sounds better" --dry-run   # diff + QA preview
  python3 work/tools/decisions.py rename D-0335 --en "Granny Gold" --reason "sounds better" --by user
  ```
  `rename` does the following:
  1. It finds every workspace string whose zh contains the term or an alias, within the record's scope.
  2. It skips strings where the term appears only inside a longer registered term. For example, `水都` → Alto Mare does not touch strings that only have `水都群岛` (the Alto Mare Islands), which has its own record. `rename` names related records whose English contains the old text, so you can rename those too. `--include-shadowed` overrides the skip.
  3. It replaces the old English with word boundaries. It handles plurals and possessives, a leading "the", ALL-CAPS and sentence-initial capitals. A match that was split across `{NEWLINE}` or `{CLEAR}` is joined with a space.
  4. It sets the string's `status` to `draft` and appends `[D-NNNN rename date: old → new]` to `notes`.
  5. It backs up the touched banks to `work/snapshots/…_before_D-NNNN_rename.tgz` and writes each bank atomically. If a bank changed on disk since it was read, `rename` retries, and after 3 failed attempts it skips that bank and warns.
  6. It runs QA before and after, reports **new** errors (for example `line_too_wide`) and runs `qa.py check` on each touched bank.
  7. It writes `decisions/rewrap/D-NNNN_<time>.tsv`. This lists strings with new layout issues, joined line breaks, a changed article, or the term in zh but not the old English in en. Its header has the `qa.py wrap --reflow` command for each bank. Re-wrap those strings, check them by eye, and run `qa.py check` until it reports 0 errors.

  `--old TEXT` (repeatable) replaces other spellings as well, such as an old variant.
- **Replacing a decision with a new one:** add the new record, then
  `set D-OLD status=superseded superseded_by=D-NEW --reason ...`.

Don't run a `rename` while a translator agent is working on the same banks. The tool refuses to overwrite a bank that changes under it, but a string can still be edited just before the rename and just after.

## PROGRESS.md import (until cut-over)

`python3 work/tools/decisions.py import-progress [--dry-run]` reads `work/translate/PROGRESS.md` and adds only what is new.

- It matches existing records by a hash of the parsed item text first, and then by zh + type.
- If the zh already exists with the same English, the new line is added to that record's `mentions`.
- If the English differs, the tool adds a new record and marks both `needs-review` with `conflicts_with`. There is one exception: when the new line comes from the coordinator or the user, it supersedes the agent's record instead.
- Coordinator term decisions resolve open questions that mention the same zh.
- Sections map to records as follows:

| PROGRESS.md section | Becomes |
|---|---|
| Decisions | style, layout, content or technical rules. A bullet that is only a `zh → en` list becomes terms, and quoted `zh → “en”` pairs inside a rule become extra terms. |
| Character voice | voices |
| Names decided | terms. The source is taken from the batch in the `###` heading. |
| Resolved by coordinator | accepted coordinator records |
| Open questions | questions, with refs taken from the text |
| Done | skipped (it's a progress log) |

- Defaults: agent names are `provisional`; coordinator and user decisions are `accepted` with confidence `high`; notes that say invented, placeholder, guess or `?` give confidence `low`.
- `origin_line` is the line number at import time. Lines shift as agents insert text into sections, so the stable key is `origin_hash`. If an agent edits an existing line, the edited line is imported as new (or as a mention).

## Cut-over (coordinator)

1. Let the running translator agent finish its batch. Don't cut over mid-batch.
2. Run the import one last time, then regenerate the review files and the digest:
   ```sh
   python3 work/tools/decisions.py import-progress
   python3 work/tools/decisions.py list --status needs-review          # conflicts the new lines introduced
   python3 work/tools/decisions.py report
   python3 work/tools/decisions.py render-progress --out work/translate/decisions/DIGEST.md
   ```
3. Freeze PROGRESS.md. Put this note under its title:
   > Decisions, names, character voices and open questions now live in `work/translate/decisions/decisions.jsonl` (digest: `decisions/DIGEST.md`; review: `decisions/DECISIONS.md`). The sections below are frozen as of <date>; add new entries with `work/tools/decisions.py add`. Only the "Done" log is still appended here.

   Optionally move the frozen sections to `PROGRESS_archive.md`. The records keep `origin_text`, so nothing depends on the old file.
4. Edit the translator brief (now `AGENTS.md`):
   - In "Read first", replace the PROGRESS.md bullet with:
     "`work/translate/decisions/DIGEST.md`: every decided name, rule and character voice (generated from the decision register; reuse names exactly). Look up a term with `python3 work/tools/decisions.py list --search <zh or en>`. `work/translate/PROGRESS.md` → Done: which batches are finished."
   - Replace Finish step 1 with:
     "1. Append the batch ids you completed to `work/translate/PROGRESS.md` → Done. Record every NEW name, term, rule or character voice with `python3 work/tools/decisions.py add ... --source agent:<your batch ids>` (one call each; see `work/notes/decisions_workflow.md`). Use `--confidence low` for invented or uncertain names. Record anything uncertain as `add --type question --ref <bank/id> --en "<issue>"`. Never edit decisions.jsonl by hand or add decisions to PROGRESS.md."
   - Add to "Don't": "Don't use `decisions.py rename`, `set` on others' records, or `import-csv`. Those are for the user and the coordinator."
5. After each batch, run `report` and `render-progress --out …/DIGEST.md`, so the next agent reads a fresh digest and the user sees a fresh review. Then check `list --source agent:<batch> --status needs-review` for conflicts.
6. `import-progress` stays harmless after cut-over: it only adds what isn't there yet. Run it once more if an agent still appended to the old sections by mistake.
