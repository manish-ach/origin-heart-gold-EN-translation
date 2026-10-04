# Author's spreadsheets vs the ROM (Phase B step 4b)

> **Update 2026-09-29:** the badge-tier Poké Mart list is never opened by any script (see sheet_mismatch_verification.md §6); rows citing it as a source (e.g. Quick Ball) are superseded by the regenerated items.md.

**Status (reviewed 2026-09-29): current (Phase B step 4b).**

Row-by-row cross-check of the hack author's own spreadsheets (repo root) against the data in the untouched Chinese ROM, as read by `work/tools/docs/romdata.py` / `gen_docs.py` (the same data as the player docs in `work/docs/`). English versions of the sheets are in [`work/docs/author_notes/`](../docs/author_notes/README.md). Hack findings from this pass: D-1345 to D-1352 (source `agent:phaseB2`). Scratch scripts: `<scratchpad>/phaseB2/cmp_*.py` (not kept in the repo).

## Method

- Sheets read with openpyxl (`.xlsx`) and xlrd (`.xls`).
- Chinese names mapped to ids through the ROM's own name banks first (species 0232, moves 0739, items 0219, abilities 0711, types 0724), then through the glossary (`work/glossary/*.json`: old fan names such as 巴大蝴 = Butterfree, abbreviations such as 普/斗/超). Forms (冰六尾, 洛托姆1, 超级喷火龙X…) are matched to the form's personal record by best agreement of stats, types and abilities among the species' forms.
- Places in the free-text notes are mapped to map headers (`bank_maps.json` `map_name_zh`, routes "N号路", islands "N之岛", building aliases such as 满金百货 = Goldenrod City, "X东路" = the routes next to town X, plus every map on the same town-map square). A note counts as confirmed when the ROM has a source of that item on one of those maps.
- ROM sources of an item: item balls, hidden items, script gifts and paid exchanges (`GiveItem` and the give-item std scripts), `SpecialMartBuy` lists and the badge-tier Poké Mart list, at map level.
- Every mismatch is classed **(a)** the ROM differs from the sheet (hack data changed or sheet outdated: a hack finding), **(b)** a slip in the sheet (the ROM and the game's own text agree with each other, or the sheet contradicts itself), **(c)** our extraction or generation bug (fixed in the generator). Name spellings (old fan names, 3D龙2 vs 多边兽２型) are not mismatches.
- v3 `Documents.xls` is compared only to flag what changed between v3 and v4 (§5). Those are not errors.

## Match rates

| Workbook / sheet | Compared | Matches | Rate | Notes |
|---|---|---|---|---|
| List of Pokemons / 4.0精灵数据: base stats | 4,926 values (821 rows) | 4,872 | 98.9% | 54 values in 27 rows |
| 4.0精灵数据: types | 821 type pairs | 813 | 99.0% |  |
| 4.0精灵数据: abilities 1/2/hidden | 2,463 slots | 2,456 | 99.7% | Giratina forms swapped; Cresselia's ability #327 has no name |
| 4.0精灵数据: evolution column | 372 notes (level or item) | 351 | 94.4% | 4 more are not comparable (breeding note, runtime forms) |
| 4.0招式变动: type/category/power/accuracy/PP | 280 fields (56 moves) | 278 | 99.3% | descriptions: see §1.3 |
| 4.0新增技能机: TM number → move | 38 | 38 | 100% |  |
| 4.0新增技能机: move data | 190 fields | 189 | 99.5% | Meteor Beam accuracy |
| 4.0新增技能机: shop ("位置") | 38 | 38 | 100% |  |
| 4.0特性: ability exists with a name | 59 | 58 | 98.3% | 月光守护 (#327) has no name string |
| 特性适用范围: Sharpness (锋锐) list | 23 moves | 23 | 100% | slicing flag, move flag bit 34 |
| 特性适用范围: Mega Launcher list | 13 moves | — | — | no list or flag found in the data |
| Encounters / 遭遇明细: slots | 5,979 slots | 5,975 | 99.9% | all 142 maps / 136 encounter records covered, no slot missing |
| Encounters / 遭遇索引: species per map and method | 1,360 cells | 1,357 | 99.8% | the same 3 map/method cells |
| Items / 3.2道具: id → name | 536 rows | 529 | 98.7% | the 7 others are renames the sheet notes, or new hack items |
| 3.2道具: TM/HM → move | 100 | 100 | 100% | 3 old names (岩切, 飞空, 旋涡) |
| 3.2道具: price in "售价与效果" | 32 prices | 30 | 93.8% | Oran Berry; Sitrus matches the script vendors (₽1000) |
| 3.2道具: obtain notes ("新统计的获得方式") | 770 clauses (402 items) | 684 confirmed | 88.8% | 41 unconfirmed, 41 no place named, 4 random |
| 3.2道具: tutor list (bottom rows 541–619) | 79 tutors | 75 place / 53 of 57 costs | 95% |  |

The 41 unconfirmed obtain clauses break down as: 16 apricorn-tree clauses (apricorn trees are not extracted, class c coverage), 10 place-granularity cases confirmed by hand (e.g. "Whirl Islands challenge" is run from Cianwood; "Rock Tunnel Pokémon Center" is the Route 10 Pokémon Center), and 15 real differences (13 a, 2 b) listed in §3. The place matching is lenient (any map on the same town-map square counts), so §3 also lists a few differences found by reviewing the shop lists directly (e.g. Micle/Custap Berry are not sold in Celadon).

## Mismatches by class

| Class | Count | Where |
|---|---|---|
| (a) ROM differs from the sheet | 76 | 31 species rows, 15 evolutions, 5 moves, 2 abilities, 3 wild-slot rows (4 slots), 13 item/shop rows, 1 group of rarity-S items, 3 item names, 3 tutors (incl. the known D-1305 and D-1339) |
| (b) slip in the sheet | 15 | 4 column swaps and the 2 Giratina rows, Relicanth, Porygon2's item, Meteor Beam, 3 tutor costs, Machine Part place, TM43 house, anti-aging spray ingredient |
| (c) our extraction/generation | 3 fixed + 2 coverage gaps | vendor prices, tutor payment after teaching; apricorn trees and random item sources not modelled |

## 1. List of Pokemons workbook

### 1.1 4.0精灵数据 (species)

Stats are HP/Atk/Def/SpA/SpD/Spe. "Row" is the spreadsheet row.

| Row | Sheet name | ROM species | Field | Sheet | ROM | Class |
|---|---|---|---|---|---|---|
| 10 | 水箭龟 | Blastoise | Atk | 73 | 78 | a |
| 10 | 水箭龟 | Blastoise | SpA | 90 | 85 | a |
| 30 | 穿山鼠 | Sandshrew (form 1) | types | 冰 | Ice/Steel | a |
| 32 | 穿山王 | Sandslash (form 1) | Def | 110 | 120 | a |
| 61 | 哥达鸭 | Golduck | Atk | 78 | 82 | a |
| 61 | 哥达鸭 | Golduck | Def | 80 | 78 | a |
| 61 | 哥达鸭 | Golduck | SpD | 82 | 80 | a |
| 79 | 玛瑙水母 | Tentacool | Atk | 35 | 40 | b |
| 79 | 玛瑙水母 | Tentacool | Def | 40 | 35 | b |
| 84 | 小火马 | Ponyta | HP | 65 | 50 | b |
| 84 | 小火马 | Ponyta | SpA | 50 | 65 | b |
| 85 | 烈焰马 | Rapidash | types | 火 | Fire/Fairy | a |
| 85 | 烈焰马 | Rapidash | Def | 75 | 70 | a |
| 85 | 烈焰马 | Rapidash | SpA | 60 | 65 | a |
| 93 | 小海狮 | Seel | SpA | 75 | 45 | a |
| 155 | 急冻鸟 | Articuno (form 1) | Def | 100 | 85 | a |
| 155 | 急冻鸟 | Articuno (form 1) | SpA | 95 | 125 | a |
| 155 | 急冻鸟 | Articuno (form 1) | SpD | 125 | 100 | a |
| 155 | 急冻鸟 | Articuno (form 1) | Spe | 85 | 95 | a |
| 246 | 小小象 | Phanpy | SpA | 20 | 40 | a |
| 289 | 乐天河童 | Ludicolo | Def | 80 | 70 | a |
| 304 | 懒人翁 | Slakoth | HP | 60 | 45 | a |
| 325 | 恰雷姆 | Medicham | HP | 80 | 60 | a |
| 325 | 恰雷姆 | Medicham | Atk | 80 | 60 | a |
| 379 | 冰鬼护 | Glalie | types | 冰/恶 | Ice | a |
| 404 | 代欧奇希斯（1普通) | Deoxys | Atk | 150 | 180 | a |
| 404 | 代欧奇希斯（1普通) | Deoxys | Def | 50 | 20 | a |
| 404 | 代欧奇希斯（1普通) | Deoxys | SpA | 150 | 180 | a |
| 404 | 代欧奇希斯（1普通) | Deoxys | SpD | 50 | 20 | a |
| 417 | 姆克鸟 | Staravia | HP | 60 | 55 | a |
| 417 | 姆克鸟 | Staravia | Atk | 85 | 75 | a |
| 417 | 姆克鸟 | Staravia | SpA | 35 | 40 | a |
| 417 | 姆克鸟 | Staravia | SpD | 55 | 40 | a |
| 418 | 姆克鹰 | Staraptor | types | 普/飞 | Fighting/Flying | a |
| 430 | 铁面龙 | Shieldon | Atk | 22 | 42 | a |
| 430 | 铁面龙 | Shieldon | SpA | 62 | 42 | a |
| 461 | 胡说盆栽 | Bonsly | HP | 60 | 50 | a |
| 461 | 胡说盆栽 | Bonsly | Atk | 85 | 80 | a |
| 461 | 胡说盆栽 | Bonsly | SpD | 55 | 45 | a |
| 462 | 魔尼尼 | Mime Jr. | Atk | 15 | 25 | a |
| 462 | 魔尼尼 | Mime Jr. | SpA | 80 | 70 | a |
| 462 | 魔尼尼 | Mime Jr. | Spe | 65 | 60 | a |
| 473 | 河马兽 | Hippowdon | types | 地 | Ground/Rock | a |
| 494 | 冰精灵 | Glaceon | HP | 80 | 70 | a |
| 511 | 帝牙卢卡 | Dialga | Atk | 120 | 100 | a |
| 511 | 帝牙卢卡 | Dialga | SpD | 100 | 120 | a |
| 513 | 帕路奇亚 | Palkia | Atk | 120 | 100 | a |
| 513 | 帕路奇亚 | Palkia | Spe | 100 | 120 | a |
| 517 | 骑拉帝纳（1起源） | Giratina (form 1) | ability1 | 压迫感 | Levitate | b |
| 517 | 骑拉帝纳（1起源） | Giratina (form 1) | ability2 | 压迫感 | Levitate | b |
| 518 | 骑拉帝纳（0别种） | Giratina | ability1 | 飘浮 | Pressure | b |
| 518 | 骑拉帝纳（0别种） | Giratina | ability2 | 飘浮 | Pressure | b |
| 518 | 骑拉帝纳（0别种） | Giratina | hidden | 飘浮 | ------ | b |
| 519 | 克雷色利亚 | Cresselia | hidden | 月光守护 | ability #327 | a |
| 528 | 青藤蛇 | Servine | types | 草 | Grass/Dragon | a |
| 529 | 君主蛇 | Serperior | types | 草 | Grass/Dragon | a |
| 554 | 修建老匠 | Conkeldurr | SpD | 75 | 65 | a |
| 597 | 萌芽鹿 | Sawsbuck | Def | 75 | 70 | a |
| 597 | 萌芽鹿 | Sawsbuck | SpD | 80 | 70 | a |
| 630 | 勇士雄鹰 | Braviary | types | 斗/飞 | Normal/Flying | a |
| 654 | 掘地兔 | Diggersby | Atk | 76 | 56 | a |
| 676 | 伞电蜥 | Helioptile | Atk | 33 | 38 | b |
| 676 | 伞电蜥 | Helioptile | Def | 38 | 33 | b |
| 680 | 仙子精灵 | Sylveon | Def | 80 | 70 | a |
| 731 | 穿着熊 | Bewear | Def | 90 | 80 | a |
| 731 | 穿着熊 | Bewear | SpD | 80 | 60 | a |
| 747 | 鳞甲龙 | Hakamo-o | Atk | 65 | 75 | b |
| 747 | 鳞甲龙 | Hakamo-o | SpA | 75 | 65 | b |

Class (b) here: Tentacool, Ponyta, Helioptile and Hakamo-o swap two values that the ROM has in the official order (vanilla HeartGold for #1–493), so the sheet transposed them. Giratina: the sheet gives the Origin form Pressure and the Altered form Levitate; the ROM (and the official games) have the reverse. Dialga and Palkia are also swaps, but there the ROM moved away from the official values, so they count as (a). Cresselia's hidden ability is #327 in the ROM, the sheet's 月光守护, but no name string exists for it (D-1346). Finding for the data rows: D-1349.

### 1.2 Evolution column

The column mixes "evolves at" (on the lower stage) and "evolves by" (on the higher stage); both directions were checked.

| Row | Species | Sheet | ROM | Class |
|---|---|---|---|---|
| 3 | Ivysaur → Venusaur | 36 | Lv 32 | a |
| 105 | Krabby → Kingler | 26 | Lv 28 | a |
| 109 | Exeggcute | 35 | Leaf Stone (Exeggutor) or Dragon Scale (Alolan Exeggutor) | a |
| 213 | Misdreavus | 25 | Dusk Stone | a |
| 413 | Piplup | 20 | Lv 16 | a |
| 414 | Prinplup → Empoleon | 45 | Lv 36 | a |
| 481 | Mantyke | 30 | level up with Remoraid in the party | a |
| 547 | Boldore | 35 | trade | a |
| 553 | Gurdurr | 40 | trade | a |
| 587 | Zorua | 48 | Lv 30 | a |
| 718 | Mareanie | 38 | Lv 30 | a |
| 737 | Sandygast | 32 | Lv 42 | a |
| 779 | Milcery | 35 | level up holding a Sweet (7 items) | a |
| 787 | Kleavor | 35 (from Scyther) | no evolution; Scyther only evolves into Scizor. Kleavor is wild on Route 42 | a |
| 680 | Sylveon | learns a Fairy move, friendship 150 | level up knowing a Fairy-type move (no friendship check) | a |
| 248 | Porygon2 | level up holding 聚焦镜片 (Zoom Lens) by day | level up holding Scope Lens (焦点镜片) by day | b |
| 386 | Relicanth | 500 | does not evolve | b |

Not comparable: Azumarill (a breeding note), Lycanroc Dusk, female Basculegion and Armored Mewtwo (forms set at run time or by a held item).

### 1.3 4.0招式变动 (move changes) and 4.0新增技能机 (new TMs)

Compared with the live move table `extra/new_move_data.narc`.

| Row | Move | Field | Sheet | ROM | Class |
|---|---|---|---|---|---|
| 招式变动 10 | Skull Bash | power | 100 | 120 | a |
| 招式变动 25 | Cross Chop | accuracy | 90 | 100 | a |
| 招式变动 40 | Dragon Claw | effect | "easily lands a critical hit" | crit stage 0 (ROM description: no crit either) | a |
| 招式变动 50 | Rock Wrecker | range | 双 (both foes) | single target (target 0) | a |
| 招式变动 42 | Bounce | effect | "(one-turn move)" | effect 263 (vanilla two-turn Bounce) without the charge flag: verify in game | a |
| 技能机 34 | TM125 Meteor Beam | accuracy | 95 | 90 (official value) | b |

Descriptions: the sheet quotes official-style descriptions; the ROM's own text (bank 0738) matches the sheet word for word for 17 of 56 changed moves and for all 38 new TMs. Where they differ, the numbers in the sheet agree with the live data and the ROM text is stale: Luster Purge (ROM text 10% Sp. Atk, data and sheet 30% Sp. Def; known, move_data_audit), Hydro Cannon (D-1315), Magma Storm (ROM text 2–5 turns, data and sheet 4–5). These are covered by the existing move-audit findings (D-1308 to D-1319).

Range (范围) against the target byte: 单 = 0, 双 = 5 (both foes) or 11 (foe side), 全 = 4 (all adjacent) or 10 (field), 自 = 7, 双（我方） = 12 (own side). All rows fit except Rock Wrecker (above) and Coaching (单 in the sheet, target 6 = own side, which is how the move works; not counted).

TM numbers (TM93–TM130), moves and shop towns all match the arm9 TM table and the `SpecialMartBuy` lists. The town list at the bottom of the sheet (shop map ids 500, 474, 426…) also matches: every listed map opens a shop, except Celadon Dept. Store 1F (map 370) and 6F (map 375), which have none (lobby; vending machines).

### 1.4 4.0特性 (ability changes) and 特性适用范围 (which moves)

Each of the 59 abilities exists in the ROM; 58 have names. The ROM descriptions (bank 0712) agree with the sheet's summaries except:

| Ability | Sheet | ROM | Class |
|---|---|---|---|
| 水幕 Water Veil | adds an Aqua Ring effect | description: prevents burns only | a (D-1351) |
| 月光守护 (#327) | Cresselia's hidden ability | description at 0712#327, no name string (bank 0711 ends at #326) | a (D-1346) |

Percentages and multipliers in the sheet (Effect Spore 50%, Pressure 10% flinch, Iron Fist ×1.3, Overgrow at ½ HP…) are not stated in the ROM text and live in battle code, which this pass did not disassemble; they are **not verified**.

Sharpness (锋锐): all 23 listed moves, including the author's additions (Metal Claw, Shadow Claw, Crush Claw, Dragon Claw, Dire Claw, Razor Wind, Razor Leaf, Aerial Ace, Fury Cutter, Kowtow Cleave), carry move flag bit 34, which is set on 32 moves in total (the others are official slicing moves such as Cut, Cross Poison, Secret Sword, Behemoth Blade). Mega Launcher (超级发射器): no flag bit or move-id table matching the 13 listed moves was found; not verified.

## 2. Encounters workbook

The sheet looks machine-made from the ROM (its "原始字段" column names the pret fields), and it matches almost perfectly: all 142 maps with wild data, all 136 encounter records, every method with a non-zero rate and every slot, with no extra slots for zero-rate methods.

| Sheet row | Map | Method / slot | Sheet | ROM | Class |
|---|---|---|---|---|---|
| 5420 | Route 24 | surfing, slot 4 (1%) | Mareanie | Squirtle Lv 10 | a |
| 1238 | Route 36 | night, slot 6 | Growlithe (form 0) | Growlithe form 1 (Hisuian, Fire/Rock) | a |
| 4784–4785 | Route 7 | night, slots 4–5 | Growlithe (form 0) | Growlithe form 1 (Hisuian) | a |

Finding D-1348. The overview sheets (地图概览, 遭遇索引) agree with the detail sheet and so with the ROM, apart from the same slots. Their "共用索引" notes are right: e.g. Dark Cave (map 176) and the Power Plant (map 489) share encounter record 69.

## 3. Items workbook (3.2道具)

The sheet is named "3.2" and 453 of its 456 obtain notes are identical to the v3 `Documents.xls` item sheet, so it is largely the v3.2 list; several differences below are v4 changes it never caught up with.

### 3.1 Items the sheet places or sells that the ROM does not

| Row | Item | Sheet says | ROM | Class |
|---|---|---|---|---|
| 173 | Qualot Berry | Saffron City shop | no fixed source anywhere | a |
| 176 | Tamato Berry | Saffron City shop | no fixed source anywhere | a |
| 171 | Pomeg / Kelpsy / Hondew / Grepa Berry (rows 171–175) | Saffron shop; Fuchsia shard exchange | Fuchsia exchange only; Saffron sells no berries | a |
| 203 | Liechi / Ganlon Berry (rows 203–204) | Celadon Dept. Store 5F | only sold on the S.S. Anne (map 307, ₽800) | a |
| 205 | Salac / Petaya / Apicot / Lansat Berry (rows 205–208) | Celadon Dept. Store 5F | no fixed source anywhere | a |
| 211 | Micle / Custap Berry (rows 211–212) | Route 9 girl; Celadon Dept. Store 5F | Route 9 vendor only (₽1500) | a |
| 288 | Grip Claw | item ball, Goldenrod Dept. Store B1F | no source; B1F (map 200) has TM60, Revival Herb, Max Elixir and a hidden Parlyz Heal | a |
| 34 | Lemonade | Azalea Town shop | Azalea's list 45 has SilverPowder, Nest Ball, TM62/120/124/128; Lemonade only from vending machines | a |
| 88 | TinyMushroom | Azalea Town shop | not in Azalea's list; Route 9 vendor and hidden items | a |
| 244 | Magnet | Union Cave, Saturday vendor | the Union Cave B1F vendor (file 57) sells Old Amber, Dawn Stone, Fluffy Tail, Protector, TwistedSpoon, Hard Stone and Focus Sash (₽100); no Magnet | a |
| 17 | Quick Ball | regular shops | not in the badge-tier Poké Mart list; sold in Saffron, a gift on Route 16 | a |
| 375 | TM46 Thief | Six Island Meowth quest reward | no source (known: D-1339) | a |
| 157 | Oran Berry | ₽50 | vendors ₽100 (New Bark) and ₽80 (Goldenrod); Viridian shop ₽20 | a |
| 483 | Machine Part | Goldenrod cafeteria (满金食堂) | Olivine Cafe (map 231) and the Olivine port | b |
| 372 | TM43 Secret Power | Route 27, house of 日雄 and others | Route 26 Week Siblings' house (map 297) | b |
| 431 | ??? (anti-aging spray, #429) | made from Rare Candy, Sacred Ash, Lemonade | 10 Durin Berries, 5 Rare Candies, Sacred Ash, Fresh Water, ₽10000 (script and dialogue 0121#143 agree) | b |

Finding D-1345 (a rows), D-1352 (b rows). "No fixed source" leaves out random sources this pass cannot see (the Goldenrod lottery, phone-contact gift berries, the Pokéwalker).

### 3.2 Items the sheet says have no source (rarity S) that the ROM does sell

Full Restore (sold in several shops; also item balls and hidden), X Attack, X Defense, X Speed, X Accuracy, X Sp. Atk, X Sp. Def, Guard Spec. and Dire Hit (Celadon 5F list 22, Saffron list 5; several also hidden). Class (a), D-1345.

### 3.3 Names, TMs and prices

| Row | Id | Sheet | ROM (0219) | Class |
|---|---|---|---|---|
| 116 | 114 | ？？？ | 钢铁铠甲 Steel Armor (Armored Mewtwo's item, new in v4) | a (sheet outdated) |
| 431 | 429 | 宝物袋, "renamed to 抗老喷雾" | ？？？: the rename was not made (D-1346) | a |
| 481 | 479 | 遗失物品 (Lost Item) | 战利品 Spoils | a (sheet outdated) |
| 440 | 438 | 发电厂钥匙, "changed to 防水服" | 防水服 Diving Suit | — |
| 442 | 440 | 银河团钥匙, "changed to 徽章袋子" | 装徽章的袋子 Badge Pouch | — |
| 471 | 469 | 安侬笔记 | 未知图腾笔记 Unown Report (same item, other name) | — |
| 25 | 23 | 痊愈药(治愈之力） | 治愈之力 Full Restore | — |

All 100 TM/HM rows name the move the arm9 table has (岩切 = Rock Polish, 飞空 = Fly, 旋涡 = Whirlpool are older names).

### 3.4 Move tutor list (rows 541–619)

75 of 79 tutors are at the place the sheet gives; 3 more are at a neighbouring map with a different name (Meteor Mash: "house at the foot of Mt. Silver" = Route 28; Bug Bite: "Viridian Forest north exit" = the Route 2 gate; Yawn: after the marathon = Route 18). Costs:

| Row | Move | Sheet | ROM script | Class |
|---|---|---|---|---|
| 585 | Play Rough (Blackthorn) | free | the script teaches Flail (#175): known, D-1305 | a |
| 554 | Volt Switch (Saffron Dojo) | ₽10000 | ₽10000; but a Pokémon with a free move slot gets Charge (#268): D-1347 | a |
| 588 | Dragon Rush (Dragon's Den shrine) | free | takes 1 MysteryStone | a |
| 590 | Tri Attack (Six Island) | Heavy Ball | Lure Ball (dialogue 0625#63/#72 agrees; so does the sheet's own Lure Ball row 496) | b |
| 605 | Power Gem (Cliff Cave) | free | Moon Ball (the sheet's own Moon Ball row 500 agrees) | b |
| 571 | Volt Tackle (Ecruteak house) | free | you give 10 Moomoo Milk first (dialogue 0610#38 agrees) | b |

The ROM also has tutors the list leaves out: Headbutt (Route 25), Hurricane (Route 32), Frenzy Plant / Blast Burn / Hydro Cannon (Islander's House, map 364) and the Charge branch above.

## 4. Class (c): our extraction and generation

| Problem | Effect in the docs | Fix |
|---|---|---|
| `script_gifts` charged every paid item with all payments in the 120 bytes before it on the same script path, so a vendor with one branch per item showed its own price plus the previous branch's (e.g. Union Cave: Fluffy Tail "₽3000, ₽1000") | about 40 rows of items.md "Prize exchanges and paid items" (Route 22 and Route 9 vendors, Cerulean TM and shard exchanges, S.S. Anne, Vermilion port…) | payments are now taken after the previous give; a bundle (one payment, several gives) still falls back to the earlier payment. Regression test `test_vendor_prices` |
| Tutor payment taken after teaching, in a block reached by `GoTo`, was missed | Saffron Dojo Volt Switch showed no payment (sheet: ₽10000) | new `cost_after()` follows the script forward from the teaching command when the window finds nothing; only this row changed |
| The Saffron Dojo Charge row had no warning | trades_tutors.md | row now points to D-1347 |
| Apricorn trees are not extracted (script commands 623–625, per-tree table not located) | the sheet's 15 tree clauses cannot be checked | not fixed; listed under "Not covered" |
| Random item sources (lottery, phone-contact berries, Pokéwalker) are not modelled | "no fixed source" means only the fixed sources | not fixed; stated in §3.1 |

After the fixes: `python3 work/tools/docs/gen_docs.py` regenerated items.md, trades_tutors.md and docs_crossref.md; `python3 -m unittest work/tools/docs/test_gen_docs.py` passes (18 tests).

## 5. v3 Documents.xls: what changed from v3 to v4 (not errors)

| v3 sheet | Compared with | Changed in v4 |
|---|---|---|
| 新种族值 (#1–493) | v4 ROM personal data | 400 of 506 species changed: stats 237, types 62, abilities 311 |
| 技能 (v3 move list, internal ids) | v4 live move table | 191 of 467 moves: name 162 (v3 reused slots; v4 moved Snarl, Play Rough, Hurricane, Wild Charge, Volt Switch… to their own ids), power 38, accuracy 31, type 11, PP 20 |
| 特性 (82 v3 ability changes) | v4 4.0特性 sheet and ROM | 48 are not in the v4 sheet. v4 keeps some in its ROM text (5-turn weather abilities, Sturdy, Lightning Rod / Storm Drain raise Sp. Atk, Inner Focus blocks Intimidate, Electric Skin). The v3 custom abilities Icy Breath, Power Burst, Super Absorb, Time Flies, Space Warp, Hard/Toxic/Psyche/Cursed/Insect Skin, Endless Rain, Parched Land, Breath and Sweet Dreams no longer exist; Turboblaze's v3 "double Speed in sun" is back to the official effect |
| 道具 | v4 3.2道具 | obtain notes identical for 453 items, different for 3 (Master Ball quest, Fast Ball on Route 6, the Curse tutor moved to the Lavender ghost tower) |
| 精灵分布笔记, 联动公园设置 | — | v3 distribution notes and Pal Park table; superseded by the v4 Encounters workbook, not compared |

## 6. Not compared

- The hack's own dex numbers (4.0图鉴编号) and the sheet's stat totals.
- Battle-code behaviour of abilities and moves (percentages, multipliers, Mega Launcher).
- Apricorn trees, lottery and other random prizes, Pokéwalker, phone gifts.
- The "调色板号" (palette) and "稀有程度" (rarity) columns, except where rarity S says "no source".

## Findings logged

- D-1345: sheet sources the ROM lacks; shop contents; S-rarity items sold.
- D-1346: item #429 and ability #327 have no name.
- D-1347: Saffron Dojo teaches Charge to a Pokémon with a free move slot.
- D-1348: 4 wild slots differ.
- D-1349: species stats/types/evolutions differ.
- D-1350: move data differ.
- D-1351: ability notes vs ROM text; v3 abilities.
- D-1352: slips in the author's sheets.
