# Move data audit: names, descriptions and data (v4.0.3 CN)

**Status (reviewed 2026-09-29): current** (analysis of the v4.0.3 move data; the findings are in the register).

Read-only analysis for D-0816, D-0817, D-0933, D-0980 and D-1037. Under D-1195 we translate the hack's text as written. This note only says which text matches the move data, as input for the hack-findings list.

Scratch scripts: `<scratchpad>/moveaudit/` (`decode.py`, `scan.py`, `thumb.py`).

## 1. Where the live move data is

- **Live table: `extra/new_move_data.narc`.** It has 921 records of 40 bytes, one per move id 0–920, which matches the 921 strings in banks 0738/0739. In the arm9 NARC path table (at arm9 `0x10E21C`), it is NARC id **276**.
- **Code proof.** `GetMoveAttr` was rewritten and now lives at `0x0201A274`. It keeps a 4-slot cache with a stride of 0x2C. On a cache miss it calls `ReadWholeNarcMemberByIdPair(dest, 0x2C+0xE8 = 276, move)`. The attribute getter at `0x0201A2E0` switches over 83 attributes and reads the 40-byte layout shown below.
- **The vanilla loaders are gone from v4.** `LoadWazaEntry` and `LoadAllWazaTbl` both read NARC 11 = `a/0/1/1` and are still present in v3 (arm9 `0x2072E44` and `0x2072D94`). They are missing from v4, and no remaining code loads NARC 11 as move data.
- **`a/0/1/1` is dead data in v4.** It still has 471 × 16-byte entries. It is the v3 hack's table, where the hack reused vanilla slots for new moves (Snarl in #49, Play Rough in #175 and so on), plus a few v4 edits (#110, #199, #192, #461, …). **Almost every stale description in bank 0738 matches this dead table, not the live one.**
- **Not hg-engine.** The format is the Gen-5 (BW) move record plus 4 bytes:

| off | field | off | field |
|---|---|---|---|
| 0 | type (0 Nor…9 **Fairy**…17 Dark) | 14 | crit stage |
| 1 | quality (0 dmg, 1 status, 2 stat, 4 dmg+status, 6 dmg+foe stat, 7 dmg+self stat, 8 drain, 13 unique…) | 15 | flinch % |
| 2 | category (0 status, 1 phys, 2 spec) | 16–17 | effect id (vanilla HGSS battle-effect ids up to 276, plus new ids above that) |
| 3 / 4 / 5 | power / accuracy (101 = never misses) / PP | 18 | recoil (−) / drain (+) % |
| 6 | priority (s8) | 19 | heal % |
| 7 | hit count min/max (nibbles) | 20 | target (7 = user, 5 = all foes…) |
| 8–9 / 10 | condition (1 par, 2 slp, 3 frz, 4 brn, 5 psn, 6 conf) / its chance | 21–23 / 24–26 / 27–29 | stat ids (1 Atk 2 Def 3 SpA 4 SpD 5 Spe 6 Acc 7 Eva) / stages / chance |
| 11–13 | condition kind / min / max turns | 32–39 | flag words (bit2 = recharge, bit0 = contact, …) |

**Caveat.** For some moves the vanilla effect id and the BW fields disagree. Examples: effect 80 (recharge) without the recharge flag, and effect 262 (Volt Tackle, recoil) with recoil byte 0. The data alone can't show which field the battle code honours. Those cases are marked **ambiguous** below and need an in-game test.

## 2. D-0816 / D-0817 disputed slots

Data format is "type cat power/acc/PP, effect id, extras". The US column is vanilla HeartGold `a/0/1/1`.

| slot | zh name (0739) | en name | zh description (0738) says | live data (new_move_data) | dead a/0/1/1 (v3/v4) | US vanilla | verdict |
|---|---|---|---|---|---|---|---|
| 49 | 音爆 | Sonic Boom | yell attack, 100% foe Sp. Atk −1 (= Snarl) | Normal Spec 1/90/20, eff 130 (fixed 20 dmg) | Dark Spec 55/95/15, eff 71, 100% (Snarl; v3 name 大声咆哮) | Normal Spec 1/90/20 eff 130 | **Name matches.** Description is stale v3 Snarl text. Snarl is now #555. |
| 110 | 缩入壳中 | Withdraw | Attack and Speed +1 | Water Status –/40PP, eff 11, Def +1 (self) | v4 edit: Water Status 10PP, eff 212 (Dragon Dance) | eff 11 Def +1, 40PP | **Name matches.** The description follows a v4 edit made only to the dead table. v3's description said 物防上升 (Def +1). |
| 175 | 抓狂 | Flail | playful attack, 10% Atk −1 (= Play Rough) | Normal Phys 1/100/15, eff 99 (Flail) | Fairy Phys 90/90/10, eff 68, 10% (Play Rough; v3 name 嘻闹) | Flail | **Name matches.** Description is stale v3 Play Rough text. Play Rough is now #583. |
| 177 | 气旋攻击 | Aeroblast | storm attack, more accurate in rain, 10% paralysis | Flying Spec 100/95/5, eff 43, crit +1 | Flying Spec 100/85/10, eff 152 (Thunder-style), 10% (v3 暴风 "Hurricane") | Aeroblast | **Name matches.** Description is stale v3 暴风. Hurricane is now #542 (110/70, 30% confusion). |
| 199 | 锁定 | Lock-On | Sp. Atk and Speed +1 | Normal Status –/5PP, eff 94 (Lock-On), no stat change | v4 edit: Electric Status 10PP, eff 53 (Sp. Atk +2) | Lock-On | **Name matches.** The description follows a v4 edit made only to the dead table. v3's description was vanilla ("next attack always hits"). |
| 209 | 电光 | Spark | electric charge, user takes recoil (= Wild Charge) | Electric Phys 65/100/20, eff 6, 30% paralysis, recoil 0 | Electric Phys 90/100/10, eff 48 recoil (v3 疯狂伏特) | Spark | **Name matches.** Description is stale v3 Wild Charge. Wild Charge is now #528. |
| 268 | 充电 | Charge | attack, then switch out (= Volt Switch) | Electric Status –/20PP, eff 174 (Charge), Sp. Def +1 (self) | Electric Spec 70/100/20, eff 228 U-turn (v3 伏特替换) | Charge | **Name matches.** Description is stale v3 Volt Switch. Volt Switch is now #521. |
| 344 | 伏特攻击 | Volt Tackle | high-voltage shock, may paralyse (no recoil mentioned) | Electric Phys **100**/100/**10**, eff **262** (vanilla recoil + paralysis script), 10% paralysis, **recoil byte 0** | Electric Phys 100/100/10, eff 6 (no recoil), 10% | 120/100/15, eff 262 | **Name matches.** The description matches the v3 no-recoil design and the BW recoil byte, but the effect id is the vanilla recoil script. **Ambiguous: test in game whether the user takes recoil.** |

In all eight slots the **name bank 0739 matches the live data. The description bank 0738 is what is wrong.** Six slots are v3 descriptions that weren't updated when v4 moved Snarl, Play Rough, Hurricane, Wild Charge and Volt Switch to their own ids. Two (#110, #199) are v4 edits made only to the dead `a/0/1/1` table.

## 3. Tutor lines (D-0933, D-0980, D-1037, plus one new)

Tutor scripts (`a/0/1/2`) use `8C 00 0C 80 <move> 06 80` to set the move, `AF 00 60 01 01 06 80 <move>` to teach it, and `8B 00 06 80 xx 80 <move>` to check it. Script file ↔ bank links come from `bank_maps.json` (`scripts_bank`).

| bank / lines | script | move the script teaches | text says | verdict |
|---|---|---|---|---|
| 0542 #76–#90 (Cherrygrove, Chatot "Sing" tutor) | 847 (MAP_CHERRYGROVE) | none. Script 847 has no tutor commands and doesn't reference messages 76–90 (it uses 70–75 and 91–95). No script anywhere teaches Sing (#47). | Sing / Moon Ball in #76–#80, then Leech Seed and Baton Pass | **Dead text.** A half-edited copy of the 0544 Leech Seed tutor that the game never shows. |
| 0544 #2–#19 (Cherrygrove PC 1F) | 849 | **Leech Seed (73)**. The "already knows" check also uses 73. | Leech Seed and Friend Ball; #11 says "already knows **Baton Pass**" | Script = Leech Seed. #11 is a text slip. Baton Pass is taught in New Bark (script 839). |
| 0563 #60–#72 (Azalea, charcoal maker's master) | 871 | **Solar Blade (669)**, Grass Phys 125/100/10 | #60 praises **Air Cutter** (真空斩, the old v3 name of #314: crit +1, Leek, Sniper). #61–#72 say Solar Blade. | Script = Solar Blade. #60 describes the wrong move. |
| 0605 #33–#46 (Ecruteak Gym) | 918 | **Poltergeist (809)**, Ghost Phys 110/90/5, eff 0 (no type-specific behaviour in the data) | #42 "works very differently when a Ghost type uses it" and #43 "to learn **Curse**" | Script = Poltergeist. #42 and #43 are Curse wording left over. Curse (#174) is taught in Sprout Tower 2F (script 17). |
| **0626 #62–#68 (Blackthorn Move Tutor House) — new** | 944 | **move 175 = Flail** (Normal, variable power) in the live data, next to Draco Meteor (434) | Play Rough (嬉闹), "super effective against Dragon types, helps at Blackthorn Gym"; #67 even keeps the v3 spelling 嘻闹 | **Gameplay bug in the hack.** The script still teaches v3's slot 175, which is Flail in v4. Play Rough is now #583. The player gets Flail. |

I checked all 71 tutor scripts in the same way. No other tutor teaches a move whose number is still a v3 id. The Route 13 tutor (script 201) teaches #555 Snarl, Mt. Moon Square teaches #585 Moonblast, Route 15 teaches #605 Dazzling Gleam and the Saffron Dojo teaches #521 Volt Switch, all correctly. 0548 #55's Gyro Ball mention is flavour text: the Shell Smash tutor there is correct.

## 4. Full scan of all 920 moves: further mismatches

Method:
- For each move, compare the percentages, stat changes (which stats, direction, stages), status conditions, flinch, recoil, priority, crit and hit counts written in the zh description against the live record.
- For slots 1–467, also diff the v3 and v4 names and descriptions, and the dead and live tables.

Descriptions that simply leave out a secondary effect are not listed. That is common and usually harmless, e.g. Headbutt's "30% 害怕" wording or Metal Claw's stat boost.

### 4a. Description contradicts the live data (new findings)

| slot | zh / en name | zh description says | live data | source of the stale text |
|---|---|---|---|---|
| 55 | 水枪 / Water Gun | scalding water, **30% burn** (= Scald) | Water Spec 40/100/25, eff 0, no burn | v3 slot was Scald (v3 name 热水, dead table 80 BP, 30% burn) |
| 295 | 洁净光芒 / Luster Purge | attacks with **moonlight**, 10% foe **Sp. Atk** −1 (= Moonblast) | Psychic Spec 95/100/5, 30% foe **Sp. Def** −1 | v3 slot was Moonblast (v3 name 月亮之力). Moonblast is now #585. |
| 354 | 精神突进 / Psycho Boost | attacks with **magic power**, 10% foe Sp. Atk −1 (= v3 Dazzling Gleam) | Psychic Spec 140/90/5, **user** Sp. Atk −2 (100%) | v3 slot was 魔法闪耀. Dazzling Gleam is now #605. |
| 294 | 萤火 / Tail Glow | Sp. Atk **and Speed** +1 | Sp. Atk **+3** (eff 321) | neither the dead table (eff 53, Sp. Atk +2) nor vanilla |
| 417 | 诡计 / Nasty Plot | Sp. Atk **and Speed** +1 | Sp. Atk **+2** (eff 53) | dead table eff 211 (Calm Mind); v4 description edited |
| 461 | 新月舞 / Lunar Dance | Sp. Atk and Speed +1 | eff **270** (vanilla Lunar Dance: user faints, heals switch-in) **and** BW stat fields Spe +1 / SpA +1 (self) | **Ambiguous.** The description matches the BW fields, not the effect id. |
| 192 | 电磁炮 / Zap Cannon | **20%** paralysis | 120/**50**/5, **100%** paralysis | dead-table v4 edit (110/85/10, 20%) |
| 59 | 暴风雪 / Blizzard | **20%** freeze | 110/70/5, **10%** freeze | dead table (20%) |
| 158 | 终结门牙 / Hyper Fang | **20%** flinch | **10%** flinch | dead table (20%) |
| 308 | 加农水炮 / Hydro Cannon | **20%** Speed −1 | 100/100/10, **10%** Speed −1. Also eff 80 (recharge script) but recharge flag off (ambiguous) | dead table (eff 70, 20%) |
| 81 | 吐丝 / String Shot | Speed −**1** | Speed −**2** (eff 60) | vanilla Gen 4 wording |
| 230 | 甜甜香气 / Sweet Scent | evasion −**1** | evasion −**2** (eff 64) | vanilla Gen 4 wording |
| 729 | 电电加速 / Zippy Zap | always goes first and **always lands a critical hit** (LGPE version) | Electric Phys **80**/100/10, priority +2, **user evasion +1 (100%)**, no crit (SV version) | new-move text from a different game version |

### 4b. Data-side oddities (text is not wrong, or the data is internally ambiguous)

These are not hack-text bugs. They're listed because they affect how in-game checks should be read.

- **Effect 80 (recharge) without the recharge flag, plus a v3-style secondary effect:** #307 Blast Burn (10% burn), #308 Hydro Cannon (10% Speed −1), #338 Frenzy Plant (50% drain), #439 Rock Wrecker (10% flinch). The descriptions match the secondary effects (no recharge mentioned). Hyper Beam, Giga Impact and Roar of Time do have the recharge flag.
- **#66 Submission:** eff 48 (¼ recoil) but recoil byte 0 and 10% flinch. The description says flinch and no recoil (same pattern as #344).
- **#401 Aqua Tail:** eff 0, but BW fields give 10% Def −1. The description says 10% Def −1.
- **#198 Bone Rush** (骨棒乱打) is **Rock** type in the live data (Ground in vanilla and in the dead table), hitting exactly 3 times. The description agrees on 3 hits and doesn't mention type.
- **Effect 0 on moves with special behaviour:** #809 Poltergeist, #812 Flip Turn and others. Many Gen 5+ moves carry eff 0 and are probably special-cased by move id in code, so this is not flagged as a mismatch.
- **Chance fields empty for vanilla chance-based effects:** #161 Tri Attack (eff 36, description says 20%) and #318 Silver Wind (eff 140, description says 10% all stats) have no chance or stat fields set. AncientPower #246 does have them (stat 9 = all stats, +1 at 10%).

### 4c. Checked and consistent

- The remaining v3 → v4 name changes in 0739 (166 slots in 1–467, minus the reused ones above) are official-name modernisations of the same move, e.g. 手刀 → 空手劈. Descriptions still fit.
- The other v3-reused slots, #314 (真空斩 → 空气利刃, both Air Cutter) and #68 (Counter), are the same move.
- Duplicate descriptions (#71/#72, #235/#236, #245/#453, #473/#540, #521/#812) are official shared texts.

## 5. Proposed hack-finding records

The first five update existing records, adding the data verdict to their text. The rest are new.

- `a027/0738#49` (D-0816): the live data is Sonic Boom (Normal, fixed 20 damage). The description is stale v3 Snarl text. The name is right.
- `a027/0738#175` (D-0816): the live data is Flail. The description is stale v3 Play Rough (now #583). The name is right.
- `a027/0738#177` (D-0816): the live data is Aeroblast (100/95/5, high crit). The description is stale v3 暴风 "Hurricane" (now #542). The name is right.
- `a027/0738#199` (D-0816): the live data is Lock-On (eff 94, no stat boost). The description's Sp. Atk/Speed +1 comes from an edit to the unused a/0/1/1 table. The name is right.
- `a027/0738#209` (D-0816): the live data is Spark (65 BP, 30% paralysis, no recoil). The description is stale v3 Wild Charge (now #528). The name is right.
- `a027/0738#268` (D-0816): the live data is Charge (status, Sp. Def +1). The description is stale v3 Volt Switch (now #521). The name is right.
- `a027/0738#344` (D-0816): Volt Tackle is 100 BP / 10 PP with 10% paralysis. The effect id is the vanilla recoil script (262) but the recoil byte is 0, so recoil is uncertain. The description mentions no recoil. Verify in game.
- `a027/0738#110` (D-0817): the live data is Withdraw, Def +1. The description's Attack/Speed +1 comes from an edit to the unused a/0/1/1 table.
- `a027/0544#11` (D-0933): script 849 teaches and checks Leech Seed (73). "Already knows Baton Pass" is a text slip.
- `a027/0542#76` (D-0933): the Sing / Moon Ball tutor lines #76–#90 are never shown. Script 847 has no tutor and doesn't reference them, and no script teaches Sing.
- `a027/0563#60` (D-0980): script 871 teaches Solar Blade (669). Line #60 describes Air Cutter.
- `a027/0605#43` (D-1037): script 918 teaches Poltergeist (809). #43's "Curse" and #42's Ghost-type remark are Curse leftovers. The Poltergeist data has no type-dependent effect.
- **NEW** `a027/0626#62`: the Blackthorn tutor promises Play Rough (#62–#68), but script 944 teaches move 175, which is Flail in v4 (Play Rough moved to #583). The player gets Flail. This is a real gameplay bug, not just text.
- **NEW** `a027/0738#55`: the Water Gun description is Scald (scalding water, 30% burn), a stale v3 slot. The live data is plain Water Gun 40/100/25.
- **NEW** `a027/0738#295`: the Luster Purge description is Moonblast (moonlight, 10% Sp. Atk −1), a stale v3 slot. The live data is 95 BP with 30% Sp. Def −1.
- **NEW** `a027/0738#354`: the Psycho Boost description is v3 Dazzling Gleam (magic power, 10% foe Sp. Atk −1). The live data is 140/90, user Sp. Atk −2.
- **NEW** `a027/0738#294`: the Tail Glow description says Sp. Atk and Speed +1. The live data is Sp. Atk +3.
- **NEW** `a027/0738#417`: the Nasty Plot description says Sp. Atk and Speed +1. The live data is Sp. Atk +2.
- **NEW** `a027/0738#461`: the Lunar Dance description says Sp. Atk/Speed +1. The data has the vanilla Lunar Dance effect (270) plus BW Sp. Atk/Speed +1 fields, so it's ambiguous. Verify in game.
- **NEW** `a027/0738#192`: the Zap Cannon description says 20% paralysis. The live data is 100% paralysis (120/50/5).
- **NEW** `a027/0738#59`: the Blizzard description says 20% freeze. The live data is 10%.
- **NEW** `a027/0738#158`: the Hyper Fang description says 20% flinch. The live data is 10%.
- **NEW** `a027/0738#308`: the Hydro Cannon description says 20% Speed drop. The live data is 10%, with a recharge effect id but no recharge flag.
- **NEW** `a027/0738#81`: the String Shot description says Speed −1. The live data is −2. (Same pattern: `a027/0738#230` Sweet Scent evasion −1 vs −2.)
- **NEW** `a027/0738#729`: the Zippy Zap description says it always crits. The live data is 80 BP, +2 priority and user evasion +1, with no crit.
- **NEW (optional, data-only)** `a027/0738#307`: Blast Burn, Hydro Cannon, Frenzy Plant (#338) and Rock Wrecker (#439) use recharge effect 80 without the recharge flag, and their descriptions give v3 secondary effects. Check in game whether they recharge.
