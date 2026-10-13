# Guide restructure: chapters in unlock order (2026-10-13)

Source: tester feedback. The quest bodies in `guide/NN-*.md` stay as they are (they are the storage).
A new layer, `guide/chapters/NN-<slug>.toml`, says which chapter each quest belongs to, what the player
does in that chapter (the walkthrough) and what each step unlocks or closes. `sync_guide.py` will build
chapter pages from these files; region pages stop being the navigation. Region files are NOT moved or
renamed; only edit a quest body when a fact is wrong (see "Rules").

## Why this exists / background
- `quest_ledger.json` was lost (never committed; rc8's sync_guide.py needs it). `work/tools/site/quest_ledger.json`
  is restored from a dangling git blob: ids, sources, legacy keys only; every stage is `unknown`.
  Keep ids and `legacy_keys` untouched (they carry players' saved "Done" ticks).
- Chapter files replace the ledger's `stage/requires/deadlines/warnings` fields as the home of verified unlock data.

## Chapter file format (TOML)
```toml
id = "ch01-first-badge"            # ch<NN>-<slug>, NN = play order, two digits
order = 1
title = "Chapter 1: The First Badge"
summary = "Pallet Town to Pewter City and Brock."     # one sentence, player language
kind = "story"                      # story | postgame
intro = """Plain Markdown. What the player is doing in this chapter, and the main-quest reminder."""

[[steps]]                           # walkthrough, in play order. Main-quest beats AND quest unlocks.
id = "s01"                          # unique within the chapter
text = """Plain Markdown, player language, landmarks, no map ids/coordinates/flags."""
main = true                         # true = story beat the player must do; false = optional pointer
unlocks = ["q-0001"]                # quest ids that become available at this step (rendered as links)
closes  = ["q-0001"]                # quest ids that become unavailable once this step is done (WARNING box)
evidence = "guide/01-pallet-to-pewter.md#...; script bank 733; emulator case X"   # folded Source line, may be technical

[[quests]]                          # EVERY quest id in exactly one chapter, in the order shown on the page
id = "q-0001"
missable = true                     # optional: closes for good (a step's `closes` should list it)
needs = ["q-0002"]                  # optional: other quests that must be done first (verified only)
available_note = "Needs Volcano Badge."   # optional one-line player text shown above the quest body
level_note = "Ariana's team is Lv. 64."   # optional
```
Rules enforced by the validator (to be written): every `q-` id in the ledger appears in exactly one
`[[quests]]`; ids in `unlocks`/`closes` exist and are in the SAME chapter or an earlier one; chapter `order`
values are unique; `postgame` chapters come after all `story` chapters.

## Rules for the agents
1. Language: `work/notes`-style rules: plain player English, landmarks and room names, never map ids,
   coordinates, flag numbers or file lines in `text`/`intro` (those go in `evidence`).
2. Verify, don't guess. Every unlock/close/prerequisite claim is checked against the game scripts
   (`work/tools/docs/scriptdump.py`, `places.py`, `landmarks.py`, `scene.py`; see `site/README.md`) or the
   emulator harness (memory `emu-harness`; run against a fresh build). The tester's remarks in the feedback
   are leads, not facts. Record the method in `evidence`. If you cannot verify, say so in `evidence`
   (`UNVERIFIED:`) and phrase the player text cautiously.
3. Source of truth for the story order is the Chinese hack (D-1002), not vanilla FireRed/HGSS.
4. Quest bodies: change one only where the heading or a fact is wrong (e.g. "Route 2 East" that is really
   west; a missing missable/starter tag; a level). Keep `<!-- quest: ... id=q-NNNN -->` ids. After editing,
   `python3 work/tools/site/sync_guide.py --check` must still pass its validation (the "would change" list is fine).
5. Missable quests: `missable = true` in `[[quests]]` AND add `missable=yes` in the quest's `<!-- quest: -->` line if absent.
6. Post-game (after the FINAL Hall of Fame) quests go in `kind = "postgame"` chapters, never in story chapters.
   Victory Road / Yellow / Lance etc: decide by when the player can first do them.
7. Do not touch ROMs, other agents' files, `work/rom`, build outputs. Never delete files. Do not commit; the coordinator commits.
8. A quest that belongs to a later part of the game than your segment: put its id in
   `work/notes/guide_chapters_handoff.md` (append a line: id, title, why, what to verify) and leave it out of your
   chapter files. The next agent must place it. Quests handed to you must be placed by you.
9. Walkthrough prose must be written from the game, not from FireRed memory. Keep it short: a chapter reads as
   a checklist of where to go next with the quest pointers inline.
10. Record uncertain things as questions in `work/notes/guide_chapters_questions.md` (append: quest id, issue, options).
