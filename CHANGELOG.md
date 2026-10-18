# Changelog

All notable changes to the English translation of 起源心金 (Pokémon Origin HeartGold) v4.0.3.
Patches apply to **Pokémon HeartGold (USA)**, CRC32 `C180A0E9`.

## [Unreleased]

### Added
- **Advanced trainer AI, optional (D-2503, D-2506):** a stronger AI for opposing trainers, switched off by default. A trainer it controls plans each turn with your team in view: it weighs every move, switch and item by working out how the turn would go, avoids moves that cannot work, switches out of bad match-ups, picks its lead Pokémon, and sometimes reads the move you chose that turn. To turn it on, open **OPTIONS**, go to page **2/2 (DIFFICULTY)** and set **TRAINER AI**:
  - **OFF** (default): every trainer uses the hack's own AI, as before.
  - **KEY:** important trainers only: Gym Leaders and every trainer in a Gym, the Elite Four, Champions, rivals, Team Rocket's boss and Executives, other story characters, Ace Trainers and Veterans.
  - **ALL:** every trainer.

  Choose CONFIRM, then save the game to keep the setting. Double battles, multi battles with a partner included, always keep the hack's own AI, and so does any turn the advanced AI cannot handle.
- **Not tested on real hardware yet.** The advanced AI's tests run in an emulator (DeSmuME). If you play with it on a DS, DSi or 3DS, please report how it goes, whether it works or not.

- **New website address:** the guide, Pokédex and in-browser patcher are now at https://originheartgold.github.io/. Old links to `originheartgold.github.io/origin-heart-gold-EN-translation/` forward to the same page.

### Added (tools)
- `work/advanced-ai/builder/release.py`: installs the advanced AI on difficulty's verified candidate and writes the release xdelta and a receipt that chains every hash, from the standard build to the patch (RELEASING.md, step 3). Covered by `work/advanced-ai/testbench/unit/test_release.py`.

### Release notes
- The release patch is one xdelta: the standard build, the difficulty settings and the advanced trainer AI. A release that ships the AI passes its static, quick and deep test levels on the release ROM.

### Credits
Advanced trainer AI: from the Spanish translation by luisvent.

## [1.0.0-rc8] - 2026-10-13

Release candidate. Adds the Victory Road freeze fix and switches on 22 further fixes that rc7 carried switched off, plus the text fixes below. Hardware and Delta remain untested.

### Fixed
- **Victory Road arch (D-2415, D-2416):** stepping under the arch in front of the stairs in the final chapter no longer freezes the game on a real DS (melonDS and hardware); the NPCs now finish their walk before the script ends. Reported on a DS Lite.
- **sibling-ribbon-freeze (D-2331):** the seven weekday siblings' ribbon scene no longer leaves the message on screen with the player locked (invalid opcode 2009 becomes Noop).
- **romance-mail-mismatch (D-2332; open question D-2333):** the Cynthia romance scenes in the Pallet Town house take the Snow Mail they check for, and her "I'm busy" reply shows her own line.
- **petilil-hisuian-lilligant (D-2334):** Petilil holding a Black Belt by day evolves straight into Hisuian Lilligant instead of into another Petilil.
- **blank-player-name (D-2335 to D-2339; open question D-2340):** the player's name is no longer blank in Clair's photo offer, the Pallet Town photographer's first line and Brock's Route 2 lines.
- **battle-faint-cry (D-2341):** a Pokémon that faints cries again, in the low, drawn-out faint cry, and makes the falling sound as it slides off the screen, on both sides (as in HeartGold).
- **battle-hit-sound (D-2342):** a move that deals damage plays the hit sound again, louder when super effective and softer when not very effective (as in HeartGold). One-hit KO moves and hits on a substitute are still silent.
- **blank-player-name-batch (D-2343 to D-2345):** the player's name is no longer blank in 53 more script lines (Route 1 kid, Route 30 woman, Misty, "League Champion ..." greetings, received-Pokémon lines and others); adds a BufferPlayersName command in front of each message. 15 positions with undecodable native commands are left alone and listed in `work/notes/blank-player-name-batch_fix.md`.
- **blank-player-name-class-c (D-2353 to D-2355; answers D-2345):** the player's name is no longer blank in five more lines ("... got Pidgeot back!" at the Route 36 gardener, Prof. Oak's "you were so late, ..." Pikachu offer, the Hitmonlee and Hitmonchan offers). The remaining class C positions are not bugs.
- **photographer-no-healthy-mon (D-2347):** answering Yes to the Pallet Town photographer while no Pokémon in the party can fight no longer freezes the game; he gives his usual decline reply.
- **giovanni-hotspring-loss (D-2349, D-2350):** losing to Giovanni at the Mt. Silver hot spring is a normal whiteout instead of a freeze on a black screen.
- **tutor-blackthorn-play-rough (D-2356):** the Blackthorn Move Tutor teaches Play Rough instead of Flail.
- **tutor-saffron-volt-switch (D-2357):** the Saffron Dojo tutor teaches Volt Switch on every path instead of Charge on some of them.
- **double-battle-single-fallback (D-2358, D-2359):** a scripted Double Battle that starts with fewer than two Pokémon in the party becomes a Single Battle instead of freezing (Department Store 6F and about 130 other sites).
- **fortune-ideal-price-check (D-2362):** the Goldenrod fortune teller's ideal-Pokémon reading checks for the $10,000 she charges, so a player with $300 to $9,999 is refused instead of left with $0.
- **ssanne-tm-price-check (D-2364):** the S.S. Anne shop checks for the $4,000 the Frustration TM costs, so a player with $400 to $3,999 is refused instead of ending with $0.
- **gamecorner-500-coins (D-2365):** at the raised Game Corner price, "500 coins for $50000" gives 500 coins instead of 50.
- **haircut-younger-price-check (D-2367):** the younger Haircut Brother accepts the $300 he charges instead of refusing a player with $300 to $499.
- **forest-of-time-sammy-guard (D-2370, D-2371):** the Forest of Time's Sammy arrival and Marauder scenes only run while the Sammy chapter is active, so the Ilex Forest bug hunt can no longer start them early or leave the hunt stuck at a marker the reward does not accept.
- **evolution-items-use (D-2392; open questions D-2393, D-2394):** the Ice Stone and the Dragon Scale show USE in the Bag, so the Pokémon that evolve with them (Mr. Mime, Alolan Sandshrew and Vulpix, Cetoddle and Darumaka with the Ice Stone; Exeggcute into Alolan Exeggutor with the Dragon Scale) can evolve. Seven more evolution items that cannot be obtained in the game get the same fix (Cracked Pot, Galarica Cuff and Wreath, both Apples, both Armors). Evolutions that need holding an item are unchanged.
- **overworld-pokemon-sprites (D-2395, D-2396, D-2398):** 36 stationary overworld Pokémon (the Pewter Jigglypuff, the Lighthouse Ampharos, the Machoke in the Goldenrod basement and others) are drawn as the species their Chinese text and cry name instead of a Generation 5 species. The S.S. Aqua Bulbasaur stays an Ivysaur sprite.
- **reward-qty (D-2409, D-2411):** a reward of more than one item (the Viridian Academy's 2 Ultra Balls and 162 other gifts of 2 to 20 items) says how many ('Obtained Ultra Ball x2!') instead of reading as a single item. Off by default.
- **Route 21 Lairon (D-2398):** the Pokémon in the Mr. Mime barrier scene is Lairon, as the Chinese text says (可多拉), not Onix: lines a027/0732#18 and #19.
- **Celadon Skitty kid (D-2405):** the boy names the item as the Bag does, "Fluffy Tail" instead of "Skitty tail" (a027/0484#141; user-approved).
- **Rock Tunnel tutor names the move he teaches (D-2386, D-2361):** the Bug Catcher in Rock Tunnel who asks for a Dusk Ball now says Pollen Puff in his offer and in the learn, thanks, forget and give-up lines, because Pollen Puff is the move he actually teaches. The Chinese dialogue still says Signal Beam (left over from the earlier hack version); this is a deliberate, user-approved text change. His joke that he thought Signal Beam lights up caves is unchanged.
- **Exp. Share item with SHARE OFF (D-2403):** turning SHARE OFF no longer switches off the Exp. Share item. A Pokémon holding an Exp. Share keeps its normal bench share (same EXP and EVs as SHARE ON, CAP still applies); other benched Pokémon still get nothing. Reported on Discord (#bugs).
- **ITEMS setting renamed DEFAULT / ALL (D-2412):** DEFAULT now keeps the Chinese hack's real battle-item rules (rc7's LIMITED allowed only berries and flutes, but the original also allows Potion, Super Potion, drinks, Heal Powder and Berry Juice). ALL still adds the twenty extra medicines. The Options help text follows the choice.
- **Difficulty settings in story battles you're allowed to lose:** CAP and SHARE now also apply in battles where the story continues even if you lose, such as Blue in Pewter City before Brock's Gym. Before, these battles ignored both settings: Pokémon could gain EXP above the level cap, and benched Pokémon still got EXP with SHARE OFF. The ITEMS setting now also applies in these battles, as in every other trainer battle: with DEFAULT, you can only use the items the Chinese hack allows there. Losing them still continues the story as before.

### Still switched off (built on request)
- **ss-anne-softlock (D-2348), trainer-abilities (D-2401, D-2402), safari-zone-closed (D-2407, D-2408), route3-misty-actors (D-2351, D-2352):** merged but not part of the standard patch.
- **overworld-pokemon-cries (D-2398 to D-2400):** superseded by overworld-pokemon-sprites and never built.
- Decided by the user on 2026-10-12 to stay as in the Chinese hack: the Pidgeot loan (D-2383), the Sprout Tower monks' offering with no money check (D-2384), the Misty love-letter branch (D-2382), losing to Deoxys (D-2380).

### Added (tools)
- New fix kind `[[script_insert]]` (`work/tools/scriptinsert.py`, `narcpatch.py`, `fixes.py`): inserts a command into a script member and relocates its offsets; used by blank-player-name-batch. Covered by `work/tools/test_script_insert.py`.

### Release notes
- Apply the xdelta to clean **Pokémon HeartGold (USA)**, CRC32 **`C180A0E9`**. Back up your save and load the battery save when updating, rather than an old savestate. ROMs and saves are never distributed.
- The standard builder now produces the 69-fix baseline (rc7: 47). The difficulty options are installed separately, as in rc7 (`work/research/difficulty-armips/build.py --enable-difficulty`); their code changed since rc7 (ITEMS DEFAULT, Exp. Share with SHARE OFF, loss-allowed story battles); the rc8 patch is built with it (see VALIDATION.txt in the release package).
- The Boldore and Gurdurr level-up evolutions (Lv 35 / Lv 40) are unchanged since rc6.

## [1.0.0-rc7] - 2026-10-11

Release candidate. Public native validation remains incomplete; multiplayer testing is excluded from its validation scope (D-2330). Hardware and Delta remain untested.

### Added
- A second Options page with three independent difficulty settings:
  - **ITEMS — LIMITED / ALL:** LIMITED restricts the player's Bag in trainer battles to berries and flutes. ALL enables the expanded battle-item selection. Held items retain their original rules.
  - **SHARE — ON / OFF:** OFF stops benched Pokémon from receiving shared EXP and EVs.
  - **CAP — OFF / ON:** ON limits battle EXP using gym progression. Caps do not decrease as gyms are completed. Pokémon already above the cap remain usable; rejected EXP is not saved for later. Rare Candy and Day Care retain their original behavior.
- Updated startup notices with translation credits, release version and project information; removed the QR promotion and unsupported permission claim.

### Fixed
- **Lugia's entrance:** fixed the animation crash after Lawrence's first battle in Whirl Islands.
- **Double Battle targeting:** improved initial target selection and D-pad navigation between eligible opponents and allies. CANCEL stays selected when chosen.
- **Struggle:** selecting FIGHT now uses Struggle when every known move has zero PP.
- **Rock Tunnel:** losing to the corner child trainer now triggers the normal blackout instead of black screens.
- **Pokémon Tower:** losing to Magcargo now triggers the normal blackout instead of a broken immediate retry.
- **Healing HP bars:** corrected healing playback when the affected Pokémon has switched out.
- **Cute Charm:** now applies infatuation instead of displaying “fell in love” without the effect.
- **Party status displays:** in-battle party screens reflect newly inflicted and cured conditions, including Heal Bell and Aromatherapy cures.
- **Fainting animations:** Pokémon knocked out by multi-hit moves wait for their HP bar to finish draining.
- **Battle messages:** “The wild” and “The foe's” prefixes match the Pokémon named in the message.
- **Pryce's challenge:** checks actual weather-changing Abilities instead of rejecting Pokémon by species.
- **Honey Gather:** restored post-battle Honey collection. Honey Gather and Pickup only report an award when it was successfully added to the Bag.

### Release notes
- Apply the xdelta to clean **Pokémon HeartGold (USA)**, CRC32 **`C180A0E9`**. Back up your save and load the battery save when updating, rather than an old savestate. ROMs and saves are never distributed.
- The standard builder produces the 47-fix baseline. Opt-in difficulty is installed separately with `work/research/difficulty-armips/build.py --enable-difficulty`; see its documentation. The rc7 candidate includes difficulty.
- Baseline strict validation passed all 11 stages with 1,133 tests and zero skips. Independent difficulty recompilation and 53 negative checks passed. The packaged xdelta independently decoded to candidate SHA-256 `81ec4501ef92c01872e97fc61d1e763c84cb1e7fcb92164ed1aa1623e1b9ec39`. These checks do not establish a complete native acceptance pass.
- Expedition progress, Ho-Oh/Silver marker and Mt. Mortar flag changes remain disabled; hit-sound and faint-cry changes are excluded.

## [1.0.0-rc6] - 2026-10-09

Tester release. Adds a text speed option and the anti-piracy fix for real hardware, and fixes freezes and battle bugs of the original hack that players reported. 3,985 strings in 478 text banks differ from rc5.

### Added
- Options has a seventh row, TEXT SPEED: NORMAL or FAST (D-1604). NORMAL is the hack's original text speed. FAST prints up to three letters per frame when the frame has room and is never slower than NORMAL (D-1601). New games start on FAST; existing saves read as NORMAL. Text speed is an optional addition to the Chinese hack, so it is an exception to D-1002 (D-1575).

### Changed
- Text prints faster in towns and routes at both settings (D-1603). In maps where the hack's game loop runs at 30 fps, text used to print one letter every two frames; it now prints one per frame, as in the US game on FAST. Pauses counted in text printer turns, including auto-advance waits, are about half as long in those scenes.
- Pokégear calls wait for A or B on every page, also right after a battle (D-1600). The hack's battle code leaves auto-advance on (D-1599). Other text shown right after a battle may still advance by itself.
- Real DS, DSi and 3DS hardware support is being tested: six of the hack's anti-piracy checks now return the genuine-cartridge result (D-1616, D-1617). Nothing changes on emulators. Not yet tested on any real console or flashcart.
- Translation: every string with Chinese text (60,800) was reread against the Chinese, clause by clause, with its scene. 2,192 lines changed, mostly for meaning, dropped or added content and softened tone (D-2081, D-2201). Hack text slips that the game itself proves wrong are fixed with the user's approval in 51 lines, e.g. refusals for a full party that said "Bag" now say "party", and battle and system messages whose Chinese contradicts what the game does (Rest, Toxic, the Day-Care level, blackout) (D-2272, D-1496). Yellow calls you "Big Bro" or "Big Sis", as in the Chinese (D-2274); Earl speaks plainly (D-2273).
- Line breaks in 762 strings are rebalanced; the wording is unchanged. The last page of 156 questions now leaves room for the prompt icons, and 612 strings no longer show a page with a single word on it.

### Fixed
- Overworld freeze when certain objects come on screen: in the Team Rocket hideout under Mahogany Town (walking towards the camera ambush), on Five Island and on Seven Island. An object asked for an animation frame its texture doesn't have, and the game crashed (seen on melonDS and reported on iOS Delta; DeSmuME happened to keep going). Such an object now keeps the texture it already shows. A Bell Tower object can hit the same problem, but only in a state forced during testing. The untouched Chinese hack freezes in the same places, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2083, D-1337).
- Black screen or freeze with Bulbasaur as the following Pokémon next to water, e.g. at the Viridian City pond (reported on iOS Delta). A freeze reported on Route 22 next to Misty (Delta, melonDS) is probably the same bug: the faulty lookup shows at that pond with Bulbasaur following. The game looked up the wrong graphics for Bulbasaur's reflection in the water, one Pokémon off the range of following Pokémon, and read an empty pointer; Bulbasaur now uses its own graphics like every other following Pokémon, and no other Pokémon changes. Checked on melonDS (the game hung before the fix and no longer does) and DeSmuME; not tested on hardware. The untouched Chinese hack does the same, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2270, D-1337).
- Pallet Town, your house: after you take Poliwag along, the game now asks "Give Poliwag a nickname?" instead of naming Poliwhirl. The Chinese hack names Poliwhirl here too, although you receive a Poliwag; the English is corrected with the user's approval (D-2282, D-1496).
- Route 5 Underground Path, after the underground battles (playing as a girl): when the police officer arrives, Red no longer says "Officer! Thank goodness you got here in time!" twice in a row. The Chinese hack repeats the line too; the English drops the repeat with the user's approval (D-2283, D-1496).
- Chinese characters and the wrong Pokémon in battle text: after Nature Power the game said "The foe's (错误)Pikachu's accuracy rose drastically!" (seen on Route 24, naming your first party Pokémon even when it was benched), and every turn a Pokémon was infatuated by Attract it said "The foe's (错误)<your Pokémon> fell in love with <the foe>!". Nature Power now says "Nature Power turned into Earthquake!" (or whichever move it calls), and the infatuation line names the infatuated Pokémon and the one it is in love with, on both sides, in wild, trainer and double battles. Both lines got the wrong data in the original hack (D-2285). (错误) means "error": it is the hack's own marker for a message that names no valid Pokémon, written into the battle code rather than the message text; it now reads "(Error) " should any other message still reach it. Checked on DeSmuME and melonDS. The untouched Chinese hack does the same, so these are bugs of the original hack; fixing them is a user-approved exception to "hack bugs are reported, not fixed" (D-2284, D-2286, D-1337). Six battle lines (accuracy rose drastically, fell in love with) now break earlier so they still fit with the marker.
- Pokémon now learn their evolution moves when they evolve, as in modern games: Crobat gets Cross Poison, Charizard Air Slash, Gyarados Bite, and so on for every species the hack gives one (reported on Discord by several players). The hack's move lists include these moves, but the game only ever looked for moves of the Pokémon's current level, so they were skipped and only the Move Reminder could teach them. On evolution the game now offers the evolution moves first and then the moves of the new level, with the usual "wants to learn" question and the forget-a-move screen when the Pokémon already knows four moves. Each move is offered once, so a move you decline is not asked for again. This works for every kind of evolution (Rare Candy, level-up after a battle, stones, trades and the rest); ordinary level-ups and the Day Care are unchanged. The untouched Chinese hack has the same bug; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2287, D-2288, D-1602, D-1337).
- Freeze in the Safari Zone: with two or more Pokémon that can battle, about one wild encounter in four turned into a broken Double Battle against one real Pokémon and an invisible, nameless second opponent, and the game froze (stuck at the command menu in DeSmuME, a crash in melonDS; reported on Discord and DraStic). Safari Zone encounters are now always single battles; random wild Double Battles elsewhere are unchanged, and the Bug-Catching Contest was never affected (you enter it with one Pokémon). The untouched Chinese hack does the same, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2289, D-1535, D-1337).
- Type-change messages in battle named the last move used instead of the new type, e.g. "Kecleon transformed into the Air Slash type!" after Color Change, "…into the Soak type!" after Soak, or the move's name after Protean (reported on Discord). The game never filled in the type's name, so the message showed whatever word was left over, usually the move from the message before. It now names the new type ("Kecleon transformed into the Flying type!") wherever a move or Ability turns a Pokémon into a single type (Color Change, Protean, Soak, Conversion, Camouflage, Magic Powder and the like). The same goes for "… type was added to …" after Trick-or-Treat and Forest's Curse, which named the move too. The type change itself was always right. Checked in DeSmuME with all of these, and with Soak on melonDS. It shares its code space with the "(Error)" fix above. The untouched Chinese hack does the same, so this is a bug of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" (D-2290, D-1461, D-1337).
- Boldore and Gurdurr only evolved by trading, so Gigalith could not be obtained without a trade partner. Boldore now evolves into Gigalith at Lv 35 and Gurdurr into Conkeldurr at Lv 40, the levels the hack author's own species sheet gives; trading them no longer evolves them. Checked in DeSmuME and melonDS 1.1 (a Rare Candy at Lv 34 / Lv 39 evolves them; before the fix it did not). The untouched Chinese hack has the trade evolutions, so this is a data error of the original hack; fixing it is a user-approved exception to "hack bugs are reported, not fixed" for data errors the author's own documentation proves (D-2291, D-1349, D-1337).
- Screens and labels: on the summary's IV/EV panel the IV numbers no longer run into "Defense" and "Sp. Atk" (D-1574). The PC box shows full Pokémon names (D-1511, D-1537). The Pokédex search and list bars no longer show garbled labels, and the details tab and its page header read DATA (D-1505, D-1536, D-1542). In battle, the FIGHT label clears the lead Pokémon's icon (D-1506), the INFO panel shows every Ability ("Abil.:") and the turns left (D-1504, D-1508), and the INFO descriptions fit their panel (D-0518). Pokédex categories, Bag descriptions and Pokégear map lines fit their windows (D-1531, D-1532, D-1533), and 56 battle messages are laid out so a long name and move still fit (D-1566).

### Added (tools)
- New patch format: every ROM change (code, data, strings and graphics fixes) lives in its own folder `work/patches/<id>/` with a `fix.toml` (why, what, decisions) and, for code, data and strings, an armips source and its disassembly snapshot. `work/patches/FIXES.md` lists them all, generated from the registry. `work/tools/check.py` is the one check entry point (registry and asm lint, ruff, unit tests; `--full` also builds the ROM and compares hashes).
- One shared TypeScript save core (`work/save-core/`) for the save editor and the emulator harness; Python tools reach it through the `save_core.py` bridge, and new checks (`check_save_harness.py`, save-core mutation tests) guard it. Worktrees and CI need `work/save-editor/node_modules` and `npm --prefix work/save-editor run build` before `check.py`.

### Known issues
- Downgrade: a save made with this version and then used in the Chinese hack or an older English patch may show an unusual MUSIC SPEED value, because text speed shares the old 4-bit options field. Set TEXT SPEED to NORMAL and save before downgrading.
- Tested with automated checks in DeSmuME; the fixes above that say so were also checked in melonDS 1.1. The text speed tests did not cover cutscenes, the intro and credits, radio and TV, mail and the naming screen. No full second-emulator pass and no hardware test.

## [1.0.0-rc5] - 2026-10-04

Tester release. 233 strings in 62 banks and one graphic differ from rc4: no code, script, map or Pokémon data changed.

### Fixed
- Blank item and move descriptions in the Bag, shops and the battle Bag: 17 English descriptions (Scope Lens, Sticky Barb, Lucky Egg, Soothe Bell, Focus Band, Shed Shell…) were longer than the 114-character buffer those screens copy into, so the game left the box empty. They are shortened to fit (F001); a new check (`text_buffer_check.py`) measures every description against the buffer read from the game's own code.
- Three long dialogues were longer than the 1,024-character buffer for field messages, so the game skipped them and could show missing or old text: the League briefing that sends you to the Bell Tower, Whirl Islands, Dark Cave and Lake of Rage (0065#60), the Lightning Whip lecture (0525#57) and the Marcel and Sunflora story (0389#56). Each one was retranslated from the Chinese with as few changes as possible to fit (D-1480).
- Chain Logger (link-capture) bar: the English graphic used tiles the screen never loads, so it drew garbage. It now stays within the loaded tiles, as the Chinese does (F002).
- Translation fixes from a review of the QA warnings against the Chinese (user-approved): the Plate inscription about a third Pokémon; the movers' Machop → Machoke option; four TM descriptions in the Battle Points prize list (Shadow Ball, Bulk Up, Calm Mind…) and the Air Cutter tutor now give the stat stages and critical-hit stage the Chinese gives; Curse now says "non-Ghost types"; the Route 29 comparison, the Relay Run's three Pokémon, the three circles, the Pokéathlon jump with three Pokémon; the Trainer House rules (one at a time, Pokémon under Lv. 50 unchanged); the Azalea Town TV top 3 (Sea Hare Well, Kurt the Poké Ball maker, D-1474); the Goldenrod sign now says Poké Mart, as the Chinese does (D-1475); the tackle-record announcements address you (D-1476); the Cerulean Gym clue; the bicycle commercial; the Battle Hall line now says Single Battle, as the Chinese does (D-1433).
- Easy Chat: 11 words that shared their English with another word (three "I"s, "YOU", "WOW", "OK"…) are now distinct, so passwords and the word picker are unambiguous (D-1462). New words: THIS GUY, THIS OLD MAN, YOURS TRULY, YOU THERE, LAD, OOOH, UH-HUH, HOWDY, I WON'T, COME ON IN, PERFECTION.
- Trainer names: Gus → Grady (no longer clashes with the other Gus, D-1434) and Nick → Nate (matches his dialogue, D-1116).
- The Mt. Moon couple's song is replaced with hum lines (song rule D-0368, D-1459). A line about the player is gender-neutral (D-1224), and the Route 11 grass-cutter is no longer called a boy (D-1435). The Quagsire thief's menu option now names Quagsire's Poké Ball (D-1482). Smaller fixes: a certificate's line breaks, MooMoo Farm, the debug slot labels.
- 50 Japanese leftover messages (Contest judging, dance and reception text; four Pokéwalker messages) were blank in English, as in US HeartGold. Blanking dropped the hack's control codes, including two YES/NO prompts, which could break a scene if one were ever shown. They are now translated from the Japanese with every code kept (D-1483). Pryce's double-size shout in the Mahogany Town hostage scene is one line on one page again, as in the Chinese (D-1389).

### Changed
- Anime and manga quotes now use the canon English wording (D-1436), checked against Bulbapedia. Team Rocket's motto, Cassidy & Butch's motto and their parodies use the original-series English dub lines ("Prepare for trouble!" … "Meowth! That's right!", D-1437); Team Rocket's defeat line is "Looks like Team Rocket's blasting off again!" (D-1438); Misty is a "Water Pokémon Master"; Crystal's Smoochum is Chumee (VIZ); Goh's catch line follows the dub.

### Added (tools)
- `work/tools/quality_runner.py`: one release gate with an auditable JSON report. It runs the tool and docs tests, translation QA, the build-artifact check, the description-buffer check, the static text checks (binary structure, change boundaries, control codes and buffer sizes for every message), the native text-loading sweep, and the emulator scenarios.
- Emulator scenarios (bag, full bag, Town Map, mart, party, summary, move order, card, battle…) that play the same save on the Chinese ROM and our build. They check the heaps, allocations, rejected text copies, the party and move state, and that text appears in selected screen regions.
- `qa_warning_inventory.py` (reconciles QA warnings against the reviewed ledgers) and a local review site for proposed fixes.

### Documentation
- `work/docs/` regenerated with fixes from a review against the scripts and the Chinese sources: species sources (771 of 1,025 national-dex species), items, trainers, encounters, trades and tutors. Evolutions the hack's code never checks are marked as not possible (D-1481).

### Known issues in the original hack, new since the rc4 notes (reported, not fixed; D-1337)
61 new findings, all in `work/translate/decisions/HACK_FINDINGS.md` and the register. Highlights:
- Evolution methods the code never checks: Nosepass and Eevee by location, Pancham, Galarian Farfetch'd and Yamask, Gimmighoul, Kubfu, White-Striped Basculin, Pawmo, Rellor and Finizen can't evolve that way (D-1481).
- After Protean or Soak, the type-change message names the move instead of the type (D-1461). The battle code is the hack's own.
- Radio quiz: pressing B on a question counts as a right answer (D-1479). Buena shows the lottery line after a right answer but gives no prize (D-1478). Uxie's quiz accepts 14 for question 4 (D-1439).
- Morty's optional 6-on-6 team has three Lv. 1 Pokémon (D-1440). Yellow's Singles option runs a Double Battle (D-1447), and Lex's Doubles option runs a Single Battle (D-1410). Agatha's and Lance's rematches show Koga's and Lorin's names (D-1442).
- Missables and shared flags: the Seafoam post-game Rocket scene removes the Articuno you could still catch before the Hall of Fame (TM14, D-1422); the Unown Report never progresses (D-1427); the Route 17 Shiny Stone can't be obtained (D-1400); several quests share one flag or variable (D-1401, D-1405, D-1412, D-1413, D-1416, D-1424, D-1429, D-1431).
- The Game Corner charges 50,000 for 50 coins (D-1415). Lantern riddles: a wrong answer at riddle 4 or 5 repeats riddles 2–5 (D-1419). The stats-page hint says L/R, but only L opens the IV/EV panel (D-1458).

### Known issues (ours)
- The battle emulator scenarios (`battle`, `battle_switch`) can't yet confirm every battle checkpoint; their memory and text checks pass.

### Verification
Release gate (`quality_runner.py`, all checks) on the rc5 build: 453 tool tests and 25 docs tests pass; translation QA 0 errors; 16 of 18 emulator scenarios pass and the 2 battle scenarios are incomplete, with 0 memory or text findings in any; the build artifact, description buffers (0 overflows) and native text loading (76,862 entries) pass; the static text check finds 0 control-code failures in 76,862 strings (it reports "incomplete" because it can't prove a maximum length for every runtime variable). The ROM differs from rc4 only in the message archive and the link-capture graphic. All 233 changed strings were reread against the Chinese (or the Japanese, for the leftovers).

## [1.0.0-rc4] - 2026-09-30

### Fixed
- Crash when switching Pokémon on the summary screen's skills page, and a bag that was 108 bytes from the same crash. The English text banks are up to 3× the size of the Chinese ones, and screens that loaded whole banks into their fixed memory ran out. Text is now always read line by line (code patch `msgload-all`, D-1390), so no screen loads a whole bank any more. See `work/notes/heap_audit.md`.
- Crash after double-size shouts (e.g. Misty and Gyarados on Route 3, Mt. Moon, Vermilion): 27 lines broke a line inside double-size text, which is drawn below the text box and corrupts memory. Each shout is now one line per page, as in the Chinese (D-1389). QA counts double-size lines as two lines.

### Added
- `work/tools/memcheck.py`: lists every whole-bank text load in the code, and plays menu scenarios on the Chinese ROM and our build in DeSmuME to compare how much memory each screen has left, and checks the game's heaps for corruption (run before every release).

## [1.0.0-rc3] - 2026-09-29

Tester release.

### Fixed
- Applied 390 line fixes (614 strings) from an external review. Most were official US lines kept although the hack had changed the Chinese. Highlights: the Lake of Rage Speed quiz now names Blaziken/Flaaffy, as in the game, so the answer matches; wrong species, move and item names (Muk, Aqua Jet, Ariados, Adrenaline Orb…); remaining softened swearing restored (D-0627); reversed or misleading instructions; inches → centimetres in fishing records.
- Renames to official names: A.J., Lara, Suzie, Bebe, Casey, and Kimono Girl Sakura (吔 renders as 樱). 精英训练家 is Ace Trainer everywhere.
- Town and route signposts with a map graphic now fit their 160 px box (62 signs).
- 85 lines where "Pokémon Center/League", Mt./Prof. or Lv. were split from the next word are rewrapped. Bare "Nidoran" now carries ♀/♂ as the Chinese does. 27 inconsistent renderings of identical Chinese are unified.
- Greetings follow the hack's Chinese ("Hello!"). A player-pronoun line is gender-neutral (D-1224).

### Added
- QA checks: split honorifics and abbreviations (error), species and move names not in the glossary (error), mid-sentence page breaks (warning), `qa.py variants` (identical Chinese, different English), and `decisions.py validate` (register references).

### Documentation (Phase B)
- Player documentation generated from the hack ROM's own data: Pokémon, moves, wild encounters, items, trainers, trades, tutors and the Move Reminder (`work/docs/`, regenerate with `work/tools/docs/gen_docs.py`).
- A row-by-row cross-check of the ROM against the hack team's spreadsheets (English versions of the sheets are kept local, not published) against the ROM (`work/notes/spreadsheet_crossref.md`) and a cross-reference of the docs against the scripts and dialogue (`work/notes/docs_crossref.md`).

### Known issues in the original hack found by Phase B (reported, not fixed)
- The Rock Tunnel move tutor promises Signal Beam but teaches Pollen Puff (D-1338).
- The Saffron Dojo tutor probably teaches Charge instead of Volt Switch to a Pokémon with fewer than four moves (D-1347, verify in game).
- TM46 Thief has no source in the game (D-1339), and 255 national-dex species from Gen 5 on can't be obtained (D-1344).

## [1.0.0-rc2] - 2026-09-29

### Fixed
- Trainer names longer than 7 characters (58 names, e.g. Giovanni, Lt. Surge, Prof. Oak) showed garbage in battle. They are now stored compressed, as in the US ROM, which fits up to 10 characters; the Frontier Brain VS-screen names stay plain. QA now enforces both limits.
- The Rocket HQ PC-puzzle hint now says ‘What it stands on’, matching the Chinese 立身之处 (the answer is the Pokémon's leg counts, 1-4-2-4-6).

### Known issues in the original hack (reported, not fixed; see `work/notes/softlock_audit.md`)
- The seven weekday siblings (Monica…Sunny) probably freeze the game when handing over their ribbon, once all seven have been met (D-1331).
- Two story flags are written past the flag array into save data, and one may mark Weezing as caught in the Pokédex (D-1333).
- The Blackthorn move tutor promises Play Rough but teaches Flail (D-1305).
- Legendary encounters come back after every Hall of Fame even if already caught (D-1335). A few NPC lines never appear (D-1334, D-1336).

### Verified (Phase A)
- Softlock audit: all 966 event-script files decoded; no dead end found on the main story path, and every menu that allows B releases the player.
- Only text, fonts, the listed graphics and the documented code patches differ from the Chinese hack. No event script, map, trainer or encounter data changed.
- In-game trade names, gift nicknames, passwords (all menu- or index-based), quiz answer order, and the naming-screen buffers all work with the English text. See `work/notes/integrity_audit_text.md`.

## [1.0.0-rc1] - 2026-09-29

First complete English release candidate. The final 1.0.0 follows after the script/quest integrity audit (see Known issues).

### Text
- Translated all Chinese text in the game's two message archives (`a/0/2/7`: 817 banks; `battle_string.narc`: 4 banks), 67,078 translatable strings (100%).
- **Story:** the whole Kanto half (Pallet Town → Indigo Plateau → Mt. Silver), the Alto Mare island chain, and the whole Johto half (New Bark → Sinjoh Ruins / Reversal Cave), including every partner, gender and choice branch.
- **Systems:** menus, battle messages (vanilla plus the hack's own), trainer names and classes, locations, Pokédex categories and all 1,440 Pokédex entries, and the move, item, ability and berry descriptions.
- **Side content:** trainer battle text, walking-Pokémon reactions, phone calls, radio, TV, Battle Frontier (facilities, Brains, trainer speeches), Pokéathlon, Easy Chat, mail, minigames and link/Wi-Fi screens, plus unused Diamond/Pearl/Platinum/SoulSilver leftovers.
- Hardcoded text outside the archives (the outfit chooser in overlay 58) is translated.
- Official US HeartGold text is kept wherever the hack left a line unchanged (17,237 strings), with names modernised.
- u/Shake69's partial v3 English was used as translation memory (with permission), and every line was reviewed and most were rewritten.

### Translation policy
- The English follows the hack's Chinese, not vanilla HeartGold. Tone is kept faithful: swearing, innuendo, dark and political content stay at full strength.
- Suspected bugs in the hack's own text are translated as written and listed in `work/translate/decisions/HACK_FINDINGS.md` (236 findings, including one gameplay bug: the Blackthorn move tutor teaches Flail instead of the promised Play Rough). Plain character typos are translated as intended and still listed.
- Modern official names in mixed case (Bulbasaur, Poké Ball). Menu labels use the US all-caps style.
- Song lyrics are never translated. They're replaced with short description lines. Team Rocket's and Cassidy & Butch's mottos use the project's own wording.
- All 1,325 decisions live in the decision register (`work/translate/decisions/`), with a review document (`DECISIONS.md`), a CSV and a change history.

### Graphics
- English type icons for battle, the summary screen and the move relearner. The FAIRY icon comes from hg-engine.
- Status icons (PAR/FRZ/SLP/PSN/BRN) on the battle HP box, party and summary screens.
- Pokédex type badges, header and buttons; touch YES/NO buttons; naming screen labels; trainer card; Pokégear calendar; bag labels; weather banners; battle info panel (Ⓑ EXIT / ✚✚ SWAP).
- Japanese leftovers from the hack's Japanese base were restored to US art: WIN/LOSE/DRAW, CANCEL, START, Pokéathlon instruction screens.
- Bilingual title screen: the original 起源心金 logo with an "Origin HeartGold" subtitle in the game's own font.
- Sources: the US ROM first, then hg-engine. A few labels (weather SNOW/DOWNPOUR/HARSH SUN/WINDS, some Pokédex and trainer-card letters) are composed from existing game glyphs because no English art exists; the naming tabs' QWE/abc letters and the Pokédex button "N" are drawn in the style of the existing labels. See `work/graphics/CREDITS.md`.
- Restored the US glyphs for … “ ”, which the hack had widened to 12 px.

### Gameplay changes (localisation only)
- Name lengths restored to US limits: 7 characters for trainers, 10 for Pokémon (the hack allows 5).
- Naming keyboard: the Chinese pinyin input is removed, and the keyboard opens on ABC. The tabs are ABC / abc / QWE / 1♪.
- No other behaviour changes. As in the original hack, there is no nickname prompt after catching a Pokémon (use the Name Rater).

### Tooling
- QA now enforces the real menu window widths (touch menus and window menus), measured from the game's code.
- `msgtool.py`: extract and insert the hack's text with its Chinese character table, round-tripping byte for byte.
- `ws.py`: the translation workspace. `qa.py`: pixel-accurate width and line checks per box type, tag checks, glossary checks and line wrapping.
- `decisions.py`: the decision register. `findings_report.py`: the hack-findings report.
- `build.py`: one reproducible build (text, glyphs, graphics, hardcoded strings, code patches, verification) that produces the xdelta patch.
- `gfx.py` and `hardcoded.py`: graphics and code patching, each checked against expected bytes.

### Known issues
- Some lines are checked only by tooling, not in game. `work/notes/ingame_checklist.md` lists 68 things to verify in melonDS.
- Not yet done (planned before 1.0.0): an audit of the event scripts for softlocks, and checks that trades, gifts, passwords and quests still work with the English text; plus Pokémon Legacy-style documentation generated from the ROM data and cross-checked against the author's spreadsheets.
- Move descriptions that disagree with the moves' real data are kept as the hack wrote them and listed in `work/notes/move_data_audit.md`.
- Foreign-language Pokédex text (FR/DE/IT/ES) that the game carries for traded Pokémon is left as is.

### Credits
Original hack: 雁南飞TB (Yannanfei TB). v4: Alex (hg-engine). Chinese patches: u/riap0526. v3 English: u/Shake69. Graphics: hg-engine contributors. Character table: Xzonn. See `README.md` and `work/notes/credits_and_sources.md`.
