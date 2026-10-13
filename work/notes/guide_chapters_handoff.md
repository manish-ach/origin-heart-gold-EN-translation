# Guide chapters: handoff between agents

## Agent 1 (guide/01-03) done. Where the story stops

Chapters written (guide/chapters/): ch01-first-badge (order 1), ch02-mt-moon (2), ch03-cerulean-cascade (3), ch04-underground-path (4), ch05-vermilion-thunder (5), ch06-ss-anne (6), ch07-rock-tunnel-lavender (7), ch08-celadon (8). All kind = "story". **Last chapter: ch08-celadon, order 8.** The next agent starts at order 9.

Where the story stops: ch08 ends with the Rainbow Badge at the Celadon Rocket hideout finale (Surf now available). Next in play order (verified from scripts): Cycling Road / Fuchsia (Soul Badge) and Surf routes to Cinnabar (Volcano Badge, Detrick lab Mewtwo scene), then Pokémon Tower "make Sabrina laugh" which starts the Saffron takeover (Marsh Badge), then the Silver Conference.

**Saffron before Celadon.** Order proved: Rock Tunnel rescue -> tower story / Agatha -> Route 8 gatehouse lets you into Saffron -> Goodshow meeting in Saffron (sets 0x40B9, opens the Route 7 gate) -> Route 7 -> Celadon. So the pre-takeover Saffron quests of files 04/05 (q-0113 Gym test and pocket dimension, q-0114 Cynthia and Steven, q-0115 Copycat, q-0116 dog lover, q-0117 Hunyuan Dojo, q-0120 small extras, q-0112 first scene) belong at the START of ch08-celadon (or in its steps). Append them to ch08-celadon.toml ([[quests]] and a step) instead of a later chapter, and move the Goodshow-meeting text of q-0112 accordingly. Check which of them really open before Celadon.

Also for the next agent: Celadon roof quiz q-0076 (Fluffy Tails for q-0074), q-0077..q-0082 belong with ch08 or right after it; Surf (Rainbow Badge) is the gate for the Power Plant (q-0060, below) and Cinnabar.

Quest-body edits made: see the report (Route 2 headings, missable tags, When lines for q-0009/q-0012).

## Quests of guide/01-03 that belong later (not placed)

- q-0006 Viridian City: Yellow's first Pokémon (Gym's Virtue trial) - needs the Viridian Gym reopened after Granny Mae's trial on Two Island (flag 1705, file 782). Place with Sevii/Granny Mae. Verify: where the Two Island trial sits in play order.
- q-0007 Viridian Gym: the Wisdom quiz - same gate as q-0006 (second examiner after Virtue). Place right after q-0006. The Earth Badge (Giovanni) follows.
- q-0015 Viridian Forest: lend her a Pidgeot (Pikachu starters) - Pikachu starters with the Volcano Badge but no Earth Badge and not yet Champion (script 115 L2225: CheckFlag 1288, CheckBadge 7, flag 2404). Place in the chapter where the Volcano Badge is won (Cinnabar). MISSABLE (closes at the Earth Badge or the first Hall of Fame). Tester suspicion CONFIRMED. missable=yes already added to its quest line.
- Note: q-0014 (in ch01) closes at the Volcano Badge: add `closes = ["q-0014"]` to the step in the Cinnabar chapter where Blaine gives the Volcano Badge (also q-0015 becomes available there).
- q-0019 Victory Road: "Which one is the real Blue?" - final Team Rocket chapter, before the final Hall of Fame (file 109). Verify the stage; the wrong answer closes Blue's romance route.
- q-0020 Victory Road 1F: fake item ball (Lv. 70 Electrode) - same stage as q-0019 (file 109 script 9).
- q-0021 Romance route (Victory Road confessions, Yellow's dates, your house) - mixed: confessions before the final Hall of Fame, dates and the Mom visit after it. Needs a split decision.
- q-0022 Pallet Town: Lance's visit home - POSTGAME (after the final Hall of Fame).
- q-0032 Mt. Moon: Groudon (Red Orb) - POSTGAME.
- q-0041 Route 25: Suicune - POSTGAME (after the post-game Burned Tower scene).
- q-0042 Cerulean Gym / Cape: Misty's romance - confession in the final chapter (male players, before the final Hall of Fame), dates after it. Same stage handling as q-0021.
- q-0053 Diglett's Cave: warm stone in the statue - after the Silver Conference closing ceremony (var 0x40A2 >= 13). Brock photo part needs the final Hall of Fame (and is unreachable by a hack bug).
- q-0060 Power Plant: Zapdos and the ecologist - needs Surf (the Power Plant door on Route 10 is only reachable over water; collision check on zone 18 with water blocked), i.e. after the Rainbow Badge. Also has a League HQ round-1 chain and a post-game catch.
- q-0065 Pokémon Tower: make Sabrina laugh - needs the Volcano Badge AND the Cinnabar lab Mewtwo scene, and the Goodshow meeting in Saffron has played. It starts the Saffron takeover; closes q-0033 (raid), q-0035 (burglary case), q-0054 (Swablu), q-0056 (Squirtle Squad) and later quests of files 04 (Battle Marathon etc.). Put `closes` on that step: q-0033, q-0035, q-0054, q-0056 (all placed in ch03-ch05; the Route 5 raid and burglary case also in the guide text).
- Note: q-0066 (placed in ch04): its Veteran Dawn and Ace Trainer Marisa parts need the Marsh Badge (Marisa also after the Radio Tower Observation Deck scene). Mention in the Marsh Badge chapter's steps; no second placement possible.
- q-0067 Rock Tunnel: Regirock, Regice, Registeel - League HQ investigation round 1 (after the first Hall of Fame, after the Goodshow briefing).

Other closes owed by later chapters (quests are placed earlier): q-0012/q-0009 (done in ch08), q-0066 Cynthia (ch06), q-0043 (three gyms; Cerulean partner away during the HQ investigation), q-0024 (Pewter Apricorn ball service ends after the Slowpoke Well event in Johto), q-0036/q-0037 (kid away during the HQ investigation).

## Agent 2 (guide/04-06) done. Where the Kanto story stops

Chapters written (guide/chapters/): ch09-fuchsia-soul-badge (order 9), ch10-cinnabar-volcano-badge (10), ch11-saffron-takeover-marsh-badge (11), ch12-alto-mare-viridian-earth-badge (12), ch13-victory-road-indigo-conference (13). All kind = "story". Agent 2 also appended to agent 1's ch07 (step s08, Route 12/13 quests q-0097..q-0105) and ch08 (Saffron pre-takeover quests q-0113..q-0117, q-0120; Celadon extras q-0076..q-0082; steps s01/s02/s04/s05 edited, s07 added; Surf wording corrected). **Last chapter: ch13-victory-road-indigo-conference, order 13. The next agent starts at order 14.**

**END OF THE KANTO STORY = the first Hall of Fame entry (flag 2404) at the end of ch13**: Indigo Conference (qualifiers on Victory Road, tournament, then the Elite Four and Blue). Next in play order (read from the guide, not yet verified by script): Cerulean Cave, Giovanni's duel (q-0178) -> Mt. Silver lodge rehabilitation (q-0179) -> Johto (New Bark, Cherrygrove, ...). Agent 3 starts there.

Facts agent 3 and later agents need:
- **"Silver Conference" is not the Indigo Conference.** The Indigo Conference (Kanto) ends at the first Hall of Fame. The "first Silver Conference" is a later Johto-era event at Mt. Silver (script file 107, closing ceremony @9518 sets var 0x40A2 = 13; Goodshow's briefing at file 31 @1625 sets 14, then the League HQ investigations start, q-0192). Anything the guide says is "after the Silver Conference" belongs after the Johto badges.
- **Sea route and Sevii islands:** the One Island travel agency (ferries to Four to Seven Island, file 894 script 11) and the Vermilion/Olivine ship to Johto are shut while flag 2024 is clear. 2024 is set by Gold's Route 39 scene in Johto (file 249 @4066). So everything that needs Four to Seven Island or the Three Island bikers is Johto-era, even though the Marsh Badge opens One and Two Island in Kanto.
- Surf: HM03 is only the item ball in Fuchsia Forest (items.json, no GiveItem in any script); it is picked up during Koga's Soul Badge trial (ch09). agent 1's remark "Rainbow Badge = Surf available" is wrong (the Rainbow Badge only allows using it); ch08 text was corrected.
- Placed in this segment: q-0015 (Pidgeot loan, ch10, closes at the Earth Badge in ch12), q-0014 closes at the Volcano Badge (ch10 s03), q-0060 (Power Plant, early part, ch09 after Surf), q-0065 (Tower, ch11, closes q-0033/35/54/56 plus q-0089/90/93/94), q-0006/q-0007 (Viridian Gym, ch12), q-0020 (Victory Road 1F ball, ch13), q-0131 (Blaine rematch, ch13).

### Quests of guide/04-06 and the handoff list that belong to later chapters (not placed)

League HQ investigation (after the Johto badges, q-0192 and following):
- q-0067 Rock Tunnel: Regirock, Regice, Registeel - round 1.
- q-0130 Cinnabar: Lawrence and Moltres - round 1 (Lawrence fight), plus the post-game Moltres catch (see POSTGAME). The same scene removes the Egg man and the Egg (q-0126, placed in ch10: add `closes = ["q-0126"]` on the round-1 step when the round-1 chapter exists).
- q-0129 Seafoam: Team Rocket and Kyogre - round 2 (Cerulean Gym lead). That scene hides Articuno for good: add `closes = ["q-0128"]` (TM14 Blizzard, placed in ch10).
- q-0060 (placed in ch09): the "Team Rocket chain" at the Power Plant is round 1, mention in that chapter's steps.
- q-0147 Secret Forest (Latios, Latias, Soul Dew): round 4 (after the Lake of Rage scene, needs Bianca, who appears after the Seven Island sign-up).
- q-0161..q-0168 Island Pilgrimage (Seven Island start q-0161, Two Island trial q-0162, Three Island q-0163, Four Island guard q-0164 and Sky Pillar Peak q-0165, Five Island Elder q-0166, Six Island q-0167, Ritual Shrine q-0168): after round 4; q-0141 (Five Island trials), q-0142, q-0143, q-0144, q-0145 (Mew hunt, after the Five Island disciple), q-0137 (lost daughter, Three Island trial), q-0138 (Island Forest, do before the Lucky Meowth God), q-0169, q-0170, q-0171, q-0172, q-0177 (Sevii small extras: mixed, Six/Seven Island). q-0138 and q-0170 have to be done before the Deoxys/Lucky Meowth God step (post-game, q-0175).
- q-0053 Diglett's Cave statue (Magma Stone): after the Silver Conference closing ceremony (file 107 @9518; var 0x40A2 >= 13). Brock's photo part is a hack bug (unreachable).

Johto-era, opens when flag 2024 / a Johto badge is reached:
- q-0132 Route 42 gatehouse crowd (opens after the Route 47 Rocket battle with Gold).
- q-0133 Two Island: Water-type quiz for Piplup - needs the Mineral Badge (Olivine).
- q-0136 Three Island bikers (asker appears after Gold's Route 39 battle, file 249 L5025; missable: bikers leave when the Dragon's Den is cleared, Rising Badge), q-0157 (Big Sis), q-0158 (Shipyard Ruins Chief; Protector missable before the Dragon's Den).
- q-0159 Four Island Mystery Stone buyer (do before the Rising Badge) and q-0160 Four Island extras: need the agency (2024).
- q-0149 Manaphy Egg: starts in the Alto Mare Waters (Surf, open earlier) but the chain needs Four/Five/Six Island (agency). UNVERIFIED: whether the islands can be reached by Surf without the agency.
- q-0106 Resort Zone backpacker (Johto, Route 48 guesthouse) and q-0108 Pal Park Fixed Catch mode (opens after the Cianwood Gym story).
- Final-march (final Team Rocket chapter, before the final Hall of Fame; VR 1F objects Blue/Yellow hidden by flag 2311): q-0019 ("real Blue?"), q-0021 (romance route confessions on VR, Yellow's dates and house: mixed stages), q-0042 (Misty's romance, mixed), q-0173 (Victory Road 3F Silver/Crystal confessions).

### POSTGAME (after the FINAL Hall of Fame) - agent 4 places these in the postgame chapter(s)

- q-0107 Resort Zone: Misty's date and the Couples Double Battle (needs flag 2261, start from Misty's date menu in the Cerulean Gym; a hack bug can leave Misty missing from the Gym afterwards, known issue).
- q-0174 Sky Pillar Peak: Rayquaza (Jade Orb from Lance's visit).
- q-0175 Six Island: Deoxys and the Lucky Meowth God (Red and Blue Orbs from Lance's visit; one chance).
- q-0176 Ritual Shrine: borrowing the Azure Flute (probably unobtainable: the keeper checks var 0x40b7 >= 4 before the final HoF).
- q-0022 Pallet Town: Lance's visit home, q-0032 Mt. Moon Groudon (Red Orb), q-0041 Route 25 Suicune (from agent 1's list).
- Post-game parts of quests placed earlier: Zapdos catch (q-0060, ch09), Articuno catch (q-0128, ch10), Moltres catch (q-0130), Kyogre catch (q-0129), Latias extra scene (q-0147).
