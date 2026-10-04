# Coordinator follow-ups (run after the main translation pass)

**Status (reviewed 2026-09-29): current (items marked done or open with dates, 2026-09-29).**

1. **Menu-width audit.** Multichoice/menu option strings are checked only relative to the Chinese ("ui" category). Find the real menu window widths (script multichoice windows) and check every option. Known long ones: 0589/0590 store menus (D-0999), 0142 #113–115, 0053 Sabrina options (D-0854). **Done 2026-09-29**: 994 script menus measured, real widths in `qa_config.json` (`menu_*` categories), 0 overflows left (D-1320; PROGRESS.md Done, "Follow-ups 1/3/4").
2. **Move name vs data audit (D-0816, D-0817).** Read move data from the ROM (type, power, effect) for the slots whose description and name disagree, and propose renames. **Done 2026-09-29**: `move_data_audit.md`; the mismatches are hack findings D-1305–D-1317 (text kept as the hack wrote it, D-1195).
3. **In-game check list.** Collect every "verify-in-game" question into one checklist for the user: double-size (200%) lines, quiz answers, big-text shouts. **Done 2026-09-29**: `ingame_checklist.md`. The in-game checks themselves are still open (nothing ticked).
4. **Consistency sweep.** For each accepted or provisional term decision, run `decisions.py usages` and fix inconsistent strings. **Done 2026-09-29**: 791 term decisions checked, 33 strings fixed (PROGRESS.md Done, "Follow-ups 1/3/4").
5. **Remaining full-width punctuation and symbols** in the English (e.g. ＠０ placeholders). **Done 2026-09-29** in the final sweep (D-1297, D-1299). QA still warns on 114 strings, all deliberate: ideographic-space padding (e.g. 0189 #172) and debug/leftover banks 0161, 0163, 0173, 0290.
6. **Final QA and build**, release notes and credits. **Done 2026-09-29**: QA 0 errors on all 821 banks; releases v1.0.0-rc1 and v1.0.0-rc2 (`CHANGELOG.md`, `work/release/`); credits in `README.md` and `credits_and_sources.md`. The final 1.0.0 is not released yet.
7. **Orphan strings.** todo/tm strings that no R batch covers (e.g. 0225 #5–8, 0280 #106, 0309 #22, 0429 #14–15). Translate them in a final sweep. **Done 2026-09-29**: the final sweep translated every remaining todo string; the listed ids were full-width Latin, not Chinese (`ws.py stats`: todo=0).

# After the translation is finished (user request, 2026-09-29)

Do these only after the translation is fully done: sweep complete, follow-ups 1–7 done, and the final build passing.

## Phase A: integrity (softlocks and broken quests)
1. **Event-script softlock audit.** Read every event script in the hack ROM (a/0/1/2 plus the hack's script overlays) and look for dead ends: flags set but never cleared, choices with no exit, warps to unreachable maps, required items that are never given, and branches gated on story flags that can't all be reached. **Done 2026-09-29**: `softlock_audit.md` (findings D-1331–D-1336).
2. **Did our changes break anything?** Cross-check every place where the game compares, stores or copies text: **Done 2026-09-29**: `integrity_audit_text.md`. It found one bug of ours (trainer names over 7 characters, D-1326), fixed in rc2.
   - in-game trades: OT names and nicknames in fixed buffers, which must fit;
   - gifts and Mystery Gift;
   - passwords and phrases the player must type or choose (Rocket HQ doors, Buena's Password, the PC puzzle, Easy Chat answers): are they typeable on the new keyboard, do they fit the buffer, and does the script compare against the right string?
   - quiz answers mapped by index, the Name Rater, and default names;
   - the text code patches (name lengths, keyboard) against every naming-screen caller.
   Compare the Chinese ROM and our build script by script; only text and the documented patches may differ.
3. Verify the riskiest flows in the emulator where it's practical, and give the user a short melonDS checklist for the rest. **Partly done 2026-09-29**: headless DeSmuME checks of the intro, outfit chooser, naming screen and trainer names (`integrity_audit_text.md` §5); the melonDS checklist is in `ingame_checklist.md`. Trades, Name Rater and passwords are not verified in game yet.

## Phase B: documentation, Pokémon Legacy style (generated from the ROM's own data)
4. Generate English docs from the hack ROM's data files, not from the author's spreadsheets or other sites: **Done 2026-09-29**: `work/docs/` (generator `work/tools/docs/gen_docs.py`). Not covered: berry/apricorn trees, Safari Zone objects, Pokéwalker, Frontier sets, roamers (see `work/docs/README.md`). Not published as an artifact.
   - Pokémon: types, abilities (incl. hidden), base stats, evolutions, level-up learnsets, TM/HM and tutor compatibility;
   - wild encounters per map, time of day, method (grass, surf, rods, rock smash, radio swaps);
   - items: field items, hidden items, gifts, shops, prizes, and key/quest items with where and how you get them;
   - trainers: rival, Gym Leaders, Elite Four, Champion and story battles, with full teams (levels, moves, items, abilities), per branch and difficulty where the hack has them;
   - in-game trades, move tutors and their costs, the Move Reminder.
   Publish as Markdown pages in the repo (and optionally an artifact).
4b. **Cross-check the generated docs against the author's spreadsheets** (user requirement), row by row: **Done 2026-09-29**: `spreadsheet_crossref.md`, English versions in `work/docs/author_notes/`, findings D-1345–D-1352.
   - `Pokémon Origin HeartGold v4.0.3 Cn Items.xlsx` (sheet 3.2道具: item changes, prices/effects, how to obtain, how consumed);
   - `Pokémon Origin HeartGold v4.0.3 Cn List of Pokemons.xlsx` (4.0精灵数据 species/abilities/types/stats, 4.0招式变动 move changes, 4.0新增技能机 new TMs, 4.0特性 ability changes, 特性适用范围);
   - `Pokémon Origin HeartGold v4.0.3 Cn Encounters.xlsx` (地图概览 / 遭遇索引 / 遭遇明细);
   - `Pokémon Origin HeartGold v3 Cn Documents.xls` (v3 reference only: flag v3→v4 differences rather than treating them as errors).
   Classify each mismatch as: the ROM differs from the sheet (hack data or doc bug → finding), a sheet typo, or our extraction bug (fix it). Publish an English version of each sheet's content alongside the ROM-derived docs, noting where they disagree.
5. **Cross-reference:** every key or quest item must be obtainable, in the place the script expects, before it's needed. Every TM and tutor the text mentions must exist. Encounter data must match the text's hints. **Done 2026-09-29**: `docs_crossref.md` (generated), findings D-1338–D-1344 (D-1340 later resolved as a false positive: the two "unused" trades are loan Pokémon).
6. **Review the existing documentation:** the author's spreadsheets (v4.0.3 Encounters/Items/List of Pokémon, v3 Documents), README, CONTRIBUTING, AGENTS.md, CHANGELOG, the notes/*.md files, STYLE.md, the digest and the reports. Check each against the ROM data and the current state. Investigate anything exceptional or unexpected, fix the inaccuracies, and log the hack's own data oddities as findings. **Done 2026-09-29**: `docs_review.md`. The spreadsheet part is covered by 4b.
