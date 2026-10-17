# Origin HeartGold v4.0.3: battle-damage mechanics for a damage calculator

Research date 2026-10-14. Read-only. Reference ROM: `work/rom/origin_v4.0.3_cn.nds` (D-1002). Nothing in the repo was changed.

Legend:
- **VERIFIED**: read from the hack's own code or data. The evidence is given.
- **INFERRED**: strongly suggested by the structure, but not traced end to end.
- **UNKNOWN**: not settled.

No emulator battle was run for this note. Every "VERIFIED" item below is a static disassembly result. Spot-check a few with the emulator harness before shipping the calc.

## Evidence and method

- Decoded binaries already exist (gitignored): `work/build/source-verify-mechanics/ov14.bin` and `arm9.bin` (plus `.txt` disassembly).
  - Overlay 14 is the battle engine. RAM base `0x022007E0`, size `0x52540` (ndspy overlay table).
- Scratch tools live in this folder:
  - `annot.py`: resolves literal pools and writes `ov14.ann.txt`.
  - `handlers2.py` / `summ.py` / `show.py`: extract the ability/item/move event-handler tables.
  - `ability_h.txt`, `item_h.txt`, `move_h.txt`: raw extraction output.
  - `ab_summ.txt`, `it_summ.txt`, `mv_summ.txt`: one line per damage-relevant handler.
- Existing notes:
  - `work/notes/move_data_audit.md` (live move table = `extra/new_move_data.narc`, BW record format).
  - `work/notes/trainer_runtime_review.md` (trainer loader).
  - `work/docs/README.md` (data sources).
  - `site/src/data/battle_notes.json` (the author's change notes; **not** the code, and several notes are wrong, see §2).

## 0. Engine lineage

**VERIFIED (structure) / INFERRED (origin):** the battle engine is a port of Game Freak's **Gen 5 (BW) event-driven battle system**. It is neither vanilla HGSS nor stock hg-engine (hg-engine is credited for v4, but the data formats are not stock hg-engine; see `work/docs/README.md`).

What it has:
- **An event-variable stack.** `GetValue` `0x0220FCC0`, `RewriteValue` `0x0220FD30`, `MulValue` `0x0220FDD4`, push/set `0x0220FCA8/FC9C/FCB4`, capacity 90 (`0x5A`).
- **Handler tables keyed by id:**
  - Abilities: pointer array at `0x0224FF2C`, indexed by ability id.
  - Items: 211 `(id, getter)` pairs at `0x0224BA30`. The lookup at `0x0220C558` compares the raw held-item id.
  - Moves: 411 `(id, getter)` pairs from `0x02251C90` (`0x02251B78 + 35*8`).
  - Each getter returns a table of `(eventId, handler)` pairs.
- **4096-based ("fx") modifiers.** These are Gen 5+ UQ4.12 modifiers. There are no Gen 4 ×15/10-style multipliers.

There is no source code or decomp in the repo. Everything here comes from disassembly.

## 1. Damage formula

**VERIFIED.** The damage routine is at `ov14 0x0220876C`. Called for normal moves from `0x0221C404` and for the confusion-style self-hit from `0x02223442`.

1. **Fixed-damage hooks.** Events `0x6B`/`0x6C` run first. If a handler marks fixed damage (Seismic Toss, Super Fang, Endeavor, Counter, Disguise, Ice Face and so on), the formula is skipped.
2. **Power, Attack, Defense, Level**, each via its own event chain (details below).
3. **Base damage** (`0x02226190`): `floor(floor(floor(2*L/5+2) * Power * A / D) / 50) + 2`.
   - Integer maths. The division by D happens after the full product.
4. **Spread.** `× targetRatio` if it is not 4096. The ratio is 4096 for one target and **3072 (0.75)** when the move hits more than one target (`0x0221CD88`). Applied with pokeRound.
5. **Weather** (`0x02208A60` → `0x02226248`, then event `0x78`):
   - Rain-type weather (ids 1 and 8): Water ×1.5, Fire ×0.5.
   - Sun-type weather (ids 2 and 9): Fire ×1.5, Water ×0.5.
   - Applied with pokeRound.
6. **×2 if the defender has volatile condition `0x2D`** (`× 200 / 100`, floor).
   - This step is not in Showdown's order. **INFERRED** to be Glaive Rush (move 862 has a post-move handler, event `0x34`).
7. **Critical hit:** `× 150 / 100` (floor). That is **×1.5, Gen 6+.**
8. **Random roll:** `× R / 100` with R = 85 + rand(16), i.e. **85–100 inclusive** (`0x022264AC(85,100)`). Floor.
9. **STAB** (`0x02208AD8`, events `0x79`/`0x7A`): 6144 (×1.5).
   - Adaptability rewrites the ratio to 8192 (×2.0).
   - Skipped for typeless (type 18).
   - pokeRound.
10. **Type effectiveness** (`0x022261B8`): bit shifts, so each ×2 and ×0.5 floors per factor. Immune gives 0.
11. **Burn:** ×0.5 (2048, pokeRound). Applies if the move is physical, the attacker is burned, and the "ignore burn" flag (var `0x13`, set by Guts, Facade and Quick Feet) is clear.
12. **Final modifiers.** Event `0x6D` chains onto var `0x47` (screens, Life Orb, Expert Belt, Multiscale, Filter, resist berries and so on). The chain is clamped to at most 32×. The result is truncated to u16 before this step.
13. A result of 0 becomes 1 (unless it is fixed damage).

**Rounding (VERIFIED):**
- Applying a modifier (`0x0222B088`): `r = (v*m) >> 12`, then +1 if `(v*m) & 0xFFF > 0x800`. This is **pokeRound** (rounds half down).
- Chaining modifiers inside one event (`0x0220FDD4`): `(a*b + 0x800) >> 12`. This is Gen 5+ `chainMods`.

This is exactly the Gen 5–9 Showdown order (base → spread → weather → crit → random → STAB → type → burn → final). The one extra step is the ×2 at step 6, between weather and crit.

### Power

`0x02206598`:
- Event `0x70` may rewrite base power (var `0x31`). This covers variable-power moves.
- Event `0x71` chains the power ratio (var `0x1C`).
- Charge (condition `0x0B`) on an Electric move: ratio ×2.
- `Power = pokeRound(BP × ratio)`. No minimum of 1 was seen.

### Attack

`0x02205BCC`:
- Event `0x73` can swap the source Pokémon (Foul Play: var `0x0C`) or ignore stages (Unaware: var 9).
- Event `0x74` picks the stat: Atk for physical, SpA for special. Body Press uses Def.
- Stage table (`0x0224DB84`): 10/40 … 10/10 … 40/10. That is the standard 2/8 … 8/2.
- A crit ignores the attacker's negative stages (`0x02205B24`).
- Event `0x75` chains the attack ratio (var `0x47`, clamped between 410/4096 and 32×), then pokeRound.

### Defense

`0x02205CD4`:
- Physical uses Def, special uses SpD. Event `0x76` can swap: Psyshock, Psystrike and Secret Sword use Def; Chip Away, Sacred Sword and Darkest Lariat ignore stages.
- A crit ignores the defender's positive stages.
- **Sandstorm (weather 3):** Rock-type SpD ×1.5. **Weather 4** (the Snow Warning weather) gives Ice-type **Def ×1.5** (the Gen 9 Snow rule). Both are applied directly to the stat with pokeRound.
- Event `0x77` chains the defense ratio.

### Critical-hit rate

**VERIFIED.** Table at `0x0224D9E8`: stage 0–3 = **1/24, 1/8, 1/2, always** (the Gen 7+ table), capped at stage 3.
- Move crit stage 6 means always crit (Wicked Blow, Surging Strikes and Zippy-type moves; `0x0220899C`).
- Battle Armor / Shell Armor block crits.
- Scope Lens, Razor Claw, Super Luck: +1 stage. Leek (Farfetch'd) and Lucky Punch (Chansey): +2 stages.
- Merciless: always crits against a poisoned target.

### Screens

**VERIFIED** (`0x02247A60`):
- Reflect on physical or Light Screen on special: ×0.5 in a single battle, **×2732/4096 (0.667)** in a double battle.
- Skipped on a crit and when the bypass flag (vars `0x45`/`0x46`, the Infiltrator-style flag) is set.
- Aurora Veil exists. The custom ability 314 Aurora Shine sets it up on entry.

### Terrain

**VERIFIED** (`0x02209AA8…`): Grassy (Grass), Electric (Electric) and Psychic (Psychic) terrain give **×1.3** power (the Gen 8+ value) to a grounded attacker. Grassy Terrain also affects Earthquake (move 89).

### Physical/special split

**VERIFIED.** Category is per move: byte 2 of the move record, read as `[move+9]` in battle.

### Type chart

**VERIFIED.** 18×18 matrix at `ov14 0x0224DA40`. Values: 0 = immune, 2 = ½, 4 = 1, 8 = 2. It is used by `0x0222610C`, and type 18 (typeless) is always neutral.

- Type ids: 0 Normal, 1 Fighting, 2 Flying, 3 Poison, 4 Ground, 5 Rock, 6 Bug, 7 Ghost, 8 Steel, **9 Fairy**, 10 Fire, 11 Water, 12 Grass, 13 Electric, 14 Psychic, 15 Ice, 16 Dragon, 17 Dark.
- The matrix is **identical to the Gen 6–9 chart.** Steel does **not** resist Ghost or Dark, and every Fairy matchup is standard. The vanilla Gen 4 triplet table is gone (no match anywhere in arm9 or the overlays).
- Ability-level effectiveness changes:
  - Corrosion (212) rewrites effectiveness (events `0x5C`/`0x5D`). The author note says "moves deal super-effective damage to Steel"; **INFERRED** to mean Poison hits Steel ×2.
  - Scrappy (113) lets Normal and Fighting moves hit Ghost.
  - Levitate (26) and Wonder Guard (25) work as usual.
- Retypings live in `species.json` `types` (see `type-changes.md`).

## 2. Abilities

The full dump of damage-event handlers is in `ab_summ.txt`; ability ids follow `site/src/data/abilities.json`.

**Standard Gen 5–9 behaviour (VERIFIED values):**

| Ability (id) | Effect |
|---|---|
| Huge Power (37), Pure Power (74) | Physical Atk ×2 |
| Thick Fat (47) | Fire/Ice: attacker's Atk ×0.5 |
| Hustle (55) | Atk ×1.5, applied directly to the stat |
| Plus/Minus (57/58) | SpA ×1.5 when an ally has Plus or Minus |
| Guts (62) | ×1.5 and ignores burn |
| Rivalry (79) | ×1.25 / ×0.75 |
| Heatproof (85) | Fire: attacker's Atk ×0.5 |
| Dry Skin (87) | Fire power ×1.25 |
| Adaptability (91) | STAB ×2 |
| Solar Power (94) | SpA ×1.5 in sun |
| Technician (101) | BP ≤ 60: ×1.5 |
| Tinted Lens (110) | ×2 on resisted hits |
| Filter / Solid Rock / Prism Armor (111/116/232) | ×0.75 on super-effective hits |
| Slow Start (112) | Atk ×0.5 |
| Reckless (120) | ×1.2 on recoil moves, Jump Kick and High Jump Kick |
| Flower Gift (122) | Atk and SpD ×1.5 in sun |
| Sheer Force (125) | ×1.3 |
| Defeatist (129) | Atk and SpA ×0.5 at ≤ ½ HP |
| Friend Guard (132) | ×0.75 |
| Multiscale / Shadow Shield (136/231) | ×0.5 at full HP |
| Toxic Boost / Flare Boost (137/138) | ×1.5 power |
| Analytic (148) | ×1.3 |
| Sand Force (159) | Rock/Ground/Steel ×1.3 in sand |
| Fur Coat (169) | Def ×2 |
| Strong Jaw (173) | ×1.5, bite flag |
| Grass Pelt (179) | Def ×1.5 on Grassy Terrain |
| Dark Aura / Fairy Aura (186/187) | ×5448/4096; Aura Break gives ×0.75 |
| Stakeout (198) | ×2 |
| Water Bubble (199) | Fire against it ×0.5; its Water ×2 |
| Steelworker (200) | ×1.5 |
| Battery (217) | ×1.3 |
| Fluffy (218) | Contact ×0.5, Fire ×2 |
| Neuroforce (233) | ×1.25 on super-effective hits |
| Punk Rock (244) | Sound ×1.3; sound taken ×0.5 |
| Ice Scales (246) | Special taken ×0.5 |
| Power Spot (249) | ×1.3 |
| Steely Spirit (252) | Steel ×1.5 |
| Gorilla Tactics (255) | Atk ×1.5 |
| Transistor (262) | Electric ×1.3 (the Gen 9 value) |
| Dragon's Maw (263) | ×1.5 |
| Purifying Salt (272) | Ghost taken ×0.5 |
| Rocky Payload (276) | ×1.5 |
| Protosynthesis / Quark Drive (281/282) | Best stat ×1.3 |
| Orichalcum Pulse / Hadron Engine (288/289) | ×5461/4096 |
| Sharpness (292) | ×1.5, slicing flag |
| Unaware (109) | Ignores stages |
| Sniper (97) | ×1.5 on crits |
| Supreme Overlord (293) | Present |

- -ate abilities use event `0x3B` to change type (Normal → X) and then add power **×1.2** (`0x0223B0EC`, the Gen 7+ value): Refrigerate (174) → Ice, Pixilate (182) → Fairy, Aerilate (184) → Flying, Galvanize (206) → Electric.
- Normalize (96) makes every move Normal and adds ×1.2.

**Deviations from official games (VERIFIED in code unless marked):**

- **Overgrow, Blaze, Torrent, Swarm (65/66/67/68):** activate at **HP ≤ ½ max** (helper `0x0223B07C`). Applied as Atk/SpA ×1.5 for the matching type.
- **Swarm (68)** also takes **×0.75 from super-effective hits** (final modifier).
- **Limber (7) and Shell Armor (75):** the holder's **Defense ×1.25 against physical moves**.
  - The author's note says "physical damage −25%". The code is a defense-stat modifier, so damage ends up about ×0.8.
  - Shell Armor also blocks crits.
- **Marvel Scale (63):** **Def and SpD** ×1.5 while it has a status condition (no category check).
- **Damp (6):**
  - **Every** Fire move's power is ×0.8 (`0xCCD`). There is no attacker check, so the whole field is affected.
  - The holder's Water moves get ×1.2.
  - The author's note says 25%; the code says 20%.
- **Iron Fist (89):** ×1.3 (punch flag) instead of ×1.2.
- **Tough Claws (181):** ×1.3 power on **every move the holder uses**. There is no contact or category check, despite the author's "physical moves" note.
- **Quick Feet (95):** physical Atk ×1.5 while statused, and ignores the burn halving.
- **Sniper (97):** +1 crit stage on top of the ×1.5 crit bonus.
- **Leaf Guard (102):** in sun, SpA ×1.5 for special moves and Def ×1.5 against physical moves.
- **Cursed Body (130):** Ghost-type moves Atk/SpA ×1.3 (`0x14CD`).
- **Telepathy (140):** Psychic moves ×1.3 when terrain id 4 is active. The author says Psychic Terrain, so id 4 is **INFERRED** to be Psychic Terrain.
- **Wonder Skin (147):** SpD ×1.5 against special moves.
- **Battle Armor (4):** blocks crits (it also has a contact-recoil handler).
- **Mega Launcher (178):** a hardcoded move-id list, **×1.5**, covering only Water Pulse 352, Aura Sphere 396, Dark Pulse 399, Dragon Pulse 406 and Origin Pulse 618, plus Heal Pulse 505 (healing).
  - Terrain Pulse is **not** boosted.
  - The author's `applicability` list (Earth Power and the "cannon" moves: Hydro Pump, Octazooka, Zap Cannon, Hydro Cannon, Flash Cannon, Beak Blast) is **not** what the code does.
- **Sharpness (292):** uses move flag bit 34 (slicing). The hack's data sets this bit on extra moves (Metal Claw, Shadow Claw, Crush Claw, Dragon Claw, Fate Claw, Razor Wind, Razor Leaf, Kowtow Cleave), so read the flag from `moves.json` `flagBits`.
- **Flash Fire (18), Blazing Awe (311):** absorb Fire. No ×1.5 power handler exists (consistent with the author's "+1 SpA stage per hit"). **INFERRED.**
- **Custom abilities (ids 311–327; names from `abilities.json`):**
  - 312 Mega Claws (Mega Charizard X): physical Atk ×1.3. It also has a "can't lower Atk" handler.
  - 317 Burning Skin → Fire, 318 Azure Skin → Water, 319 Grass Skin → Grass, 320 Dark Skin → Dark, 324 Dragonize → Dragon. All are -ate abilities: Normal → that type, ×1.2.
    - battle_notes.json maps "Flame Body custom" to id 49. That is an author-sheet alias: in the code, 49 Flame Body is not a damage handler.
  - 321 Mega Sol: the holder's moves use sun weather (weather ratio rewritten via event `0x78`).
  - 322 Flame Mane: Fire Atk/SpA ×1.5 (the author says "power +50%").
  - 326 Desert Hawk: in sand (weather 3), physical Atk ×1.3 (plus a speed handler).
  - 327 (unnamed; the author calls it "Moonlight Guardian"): ×0.75 damage taken when a status condition is present.
  - 313 Wildfire, 314 Aurora Shine, 315 Thunder Roar set the field on entry (sun+chip, Aurora Veil, Electric Terrain).
  - 316 Concentrate and 325 Mystic Dance are accuracy only.
  - 323 Ninja Bond: Wonder-Guard-style blocking (event `0x58`).
- **Not a damage factor:** Pressure, Stench (flinch), Natural Cure, Water Veil and so on.

**Where to read them:**
- `species.json` `abilityIds` / `abilitySlots` / `hiddenAbilityId`.
- `trainers.json` team `abilityId` (an explicit override is applied by the loader).
- The author's descriptions are `battle_notes.json.abilityChanges`. Treat them as hints only: several contradict the code, as listed above.

## 3. Held items

The item handler table holds 211 ids; the dump is in `it_summ.txt`.

**VERIFIED values:**

| Item | Effect |
|---|---|
| Type-boost items and Plates, incl. Pixie Plate 720 and Fairy Feather 656 | ×1.2 power (helper `0x0220D628`) |
| Masks 660–662 | ×1.2 |
| Adamant/Lustrous/Griseous Orb (135/136/112) and Crystal/Globe/Core (757–759) | ×1.2 for the matching species and types |
| Gems 685–702 | **×1.3** (Gen 6+), one use. All Gems are unobtainable. |
| Choice Band 220 / Specs 297 | ×1.5 Atk/SpA |
| Life Orb 270 | ×1.3 final |
| Expert Belt 268 | ×1.2 final on super-effective hits |
| Muscle Band 266 / Wise Glasses 267 | ×1.1 final, physical/special |
| Metronome 277 | ×(1 + 0.1·n) final |
| Punching Glove 655 | ×1.1 (unobtainable) |
| Eviolite **584** | Def and SpD ×1.5 if the holder can evolve |
| Assault Vest 593 | SpD ×1.5 |
| Light Ball 236 | Atk/SpA ×2 (Pikachu) |
| Thick Club 258 | Atk ×2 |
| Deep Sea Tooth 226 / Scale 227 | SpA / SpD ×2 |
| Metal Powder 257 | Def ×2 against physical |
| Type-resist berries 184–200 and Roseli 664 | ×0.5 final on super-effective hits (Chilan: Normal) |
| Scope Lens 232 / Razor Claw 326 | +1 crit stage |
| Leek 259 / Lucky Punch 256 | +2 crit stages |

- The final-modifier items read a ratio of (100 + param)/100 from item data `a/0/1/7` byte 3. Checked values: Life Orb 30, Expert Belt 20, Muscle Band 10, Wise Glasses 10, Metronome 10.
- **Deviation: Soul Dew 225** gives **SpA and SpD ×1.5** to Latias and Latios. That is the Gen 3–6 behaviour, not Gen 7+'s ×1.2 Dragon/Psychic power.

**Duplicate item ids. VERIFIED that these are absent from the handler table, so they have no battle effect, though the effect is still UNKNOWN in play:**
- **110 "Eviolite", 111 "Weakness Policy", 252 "Air Balloon" and 324 "Rocky Helmet"** are renamed vanilla slots.
- The live battle items are **584, 600, 576 and 590**.
- Trainers hold 584, 600 and 576, but **324 "Rocky Helmet" (58 trainer Pokémon)**. That item has no handler, so it is probably inert. It isn't a damage factor; test it in the emulator before telling players.

Item data: `items.json` (`effects.holdEffectId` is the raw vanilla hold-effect id, **not** used by this engine's handlers). Trainer held item: `trainers.json` `itemId`. Many modern items are `unavailableReason` (unobtainable) but still work in code.

## 4. Moves

**VERIFIED:**
- `moves.json` `type`, `cat`, `power`, `acc` come from the live table `extra/new_move_data.narc` (evidence field; `move_data_audit.md`). These are the hack's values; for example Bone Rush is Rock, and Volt Tackle is 100 power with 10 PP.
- `power` is the string `"var."` for 62 variable or fixed moves and `"—"` for status moves.
- `effects.hits` gives [min, max] hits: 0/0 means a single hit, [2,5] means 2–5. Examples: Triple Axel [3,3], Population Bomb [10,10], Beat Up [6,6], Dragon Darts [2,2].
- `effects.crit_stage`: 6 means always crit.
- `effects.effect`: the effect id. **Do not use effect ids for damage logic.** The engine keys its special behaviour on the **move id** (411 handler entries). Effect ids are vanilla HGSS ids (≤ 276) plus new ones, and several disagree with the BW fields (`move_data_audit.md` §1 caveat).
- `flags` only names contact, slicing, charge and recharge. Use `flagBits` instead. Flag bit = attribute id − 29:

  | Bit | Flag | Read by |
  |---|---|---|
  | 0 | contact | |
  | 7 | punch | Iron Fist |
  | 8 | sound | Punk Rock |
  | 12 | pulse | INFERRED from the Pulse moves; Mega Launcher ignores it |
  | 29 | bite | Strong Jaw |
  | 30 | ballistic | INFERRED |
  | 34 | slicing | Sharpness |

- Charge (`0x0B`) doubles Electric power.

**Damage-relevant move handlers (VERIFIED by move id; `mv_summ.txt`):**

Base-power rewrites (event `0x70`):

| Moves (ids) | Rule |
|---|---|
| Low Kick / Grass Knot (67/447) | Target weight thresholds 20–120 |
| Heavy Slam / Heat Crash (484/535) | Weight ratio thresholds 5/4/3/2 → 120/100/80/60/40 |
| Electro Ball (486) | Speed ratio 4/3/2/1 → 150/120/80/60/40 |
| Gyro Ball (360) | Speed based, capped at 150 |
| Eruption / Water Spout / Dragon Energy (284/323/820) | 150·HP/max, minimum 1 |
| Flail / Reversal (175/179) | HP table |
| Return / Frustration (216/218) | Friendship based, minimum 1 |
| Punishment (386) | ≤ 200 |
| Stored Power / Power Trip (500/681) | Stage based |
| Wring Out / Crush Grip / Hard Press (378/462/912) | HP based |
| Spit Up (255) | Stockpile count |
| Beat Up (251) | Gen 5+ (per party member) |
| Natural Gift / Fling (363/374) | Item data |
| Trump Card (376) | PP based |
| Echoed Voice (497) | Up to 200 |
| Round (496) | |
| Triple Kick / Triple Axel (167/813) | Ramp per hit |
| Present / Magnitude (217/222) | Random |
| Pledges (518–520) | 150 when combined |
| Weather Ball (311) | Type and power change in weather |
| Terrain Pulse (805) | Type and power change on terrain |
| Tera Blast (851) | 100 |
| Fickle Beam (907) | 160 on proc |
| Last Respects (854) / Rage Fist (889) | Counter based |
| Acrobatics (512) | ×2 with no item |
| Hex / Infernal Parade (506/844) | ×2 vs status |
| Wake-Up Slap (358) | ×2 vs sleep |
| Payback, Assurance, Bolt Beak, Fishious Rend, Revenge, Avalanche, Stomping Tantrum, Temper Flare, Rollout/Ice Ball, Gust/Twister | Doubling helper `0x02248CA4` |

Power-ratio modifiers (event `0x71`):

| Moves (ids) | Modifier |
|---|---|
| Facade (263) | ×2 when burned, poisoned or paralysed; ignores burn |
| Knock Off (282) | ×1.5 if the target has a removable item (Gen 6+) |
| Brine (362) | ×2 at ≤ ½ HP |
| Venoshock / Barb Barrage (474/839) | ×2 vs poison |
| Smelling Salts (265) | ×2 vs paralysis |
| Retaliate (514) | ×2 |
| Lash Out (808) | ×2 |
| Fusion Flare/Bolt (558/559) | ×2 |
| Helping Hand (270) | ×1.5 |
| Me First (382) | ×1.5 |
| Solar Beam / Solar Blade (76/669) | ×0.5 in non-sun weather |
| Expanding Force / Misty Explosion (797/802) | ×1.5 on terrain |
| Rising Voltage (804) | ×2 on terrain |
| Psyblade (875) | ×1.5 on Electric Terrain |
| Grav Apple (788) | ×1.5 under Gravity |

Final ×2 and other modifiers (event `0x6D`):
- ×2 vs Minimize: Stomp, Body Slam, Dragon Rush, Heavy Slam, Heat Crash, Flying Press, Supercell Slam.
- ×2 vs Dive: Surf.
- ×2 vs Dig: Earthquake, Magnitude.
- Collision Course / Electro Drift (878/879): ×5461/4096 on super-effective hits.

Type-change hooks (event `0x3B`):
- Hidden Power (237) uses the standard IV formula, with the type table at `0x02252990` skipping Fairy. Power stays at 60 from the data, so there is no IV-based power (Gen 6+). **INFERRED**: no power handler exists.
- Judgment, Multi-Attack, Techno Blast, Revelation Dance, Aura Wheel, Raging Bull, Ivy Cudgel and Natural Gift also change type here.

Stat swaps:
- Foul Play (492): uses the target's Atk.
- Body Press (776): Def as the attack stat (event `0x74`).
- Psyshock, Psystrike, Secret Sword (473/540/548): target's Def.
- Chip Away, Sacred Sword, Darkest Lariat (498/533/663): ignore the target's stages.
- Photon Geyser (722) and Shell Side Arm (801): category switch.

Fixed damage (event `0x6B`):
- Seismic Toss / Night Shade: level.
- Super Fang, Nature's Madness, Ruination: ½ HP.
- Endeavor.
- Final Gambit.
- Counter, Mirror Coat, Metal Burst, Comeuppance (helper `0x0223BCCC`).
- Bide.
- **Sonic Boom (49) and Dragon Rage (82) have no move handler.** How they deal 20/40 is **UNKNOWN**: probably the effect id path, unverified.

Other notes:
- Explosion and Self-Destruct have no Defense-halving handler. This is Gen 5+.
- Weight comes from the battle Pokémon (`0x02218200`) with event `0x8A` modifiers, minimum 1. **The weight source data is UNKNOWN and not exported** (no weight field in `species.json`). Assume official weights until it is checked.

## 5. Stats

**VERIFIED** (arm9 `0x0206D6C0–0x0206D7E6`):
- Non-HP stat = `floor((2·Base + IV + floor(EV/4)) · L / 100) + 5`, then the nature modifier (`0x0206F1F0`).
- **INFERRED:** HP uses the standard `…+L+10` formula, and the nature modifier is the vanilla ×1.1/×0.9 floor.
- There is a nature-override field (190), written by the trainer loader as `nature + 1`.
- Natures: the standard 25 (`romdata.NATURES`).

**IV and EV limits:**
- **INFERRED** vanilla limits: IV 0–31; EV up to 255 per stat and 510 total for the player.
- The EV Allocator only redistributes existing EVs and keeps the total (`chinese_source_rom_verify_mechanics.md` M-08). Its per-stat cap is **UNKNOWN**.
- Trainer EVs are raw bytes. In `trainers.json` they reach 252 per stat but up to **762 in total**, so the 510 total is **not enforced** for trainers.

**Level cap and EXP share:** these are English-patch options (rc7+). They don't change stats or damage.

**Trainer Pokémon** (`trainer_runtime_review.md`; loader at arm9 `0x020727A4–0x02072912`; VERIFIED):
- `ivs`: Atk, Def, SpA, SpD and Spe = `floor(rawIV × 31 / 255)`. Seen values: 0, 1, 6, 12, 18, 24, 28, 30.
- `hpIvs` overrides HP IV only: **10 for Lv ≤ 40, 20 for Lv 41–79, 31 for Lv ≥ 80** (a hack bug: the loop never increments the stat index; it must be kept).
- `evs` is already in display order HP/Atk/Def/SpA/SpD/Spe, or `null` for zero EVs.
- `nature` is `null` (2,731 of 3,891 Pokémon) when the nature is **generated at creation** from the personality value. The site shows this as "Generated".
  - The PID algorithm is **UNKNOWN** for this hack. Vanilla HGSS derives it deterministically from trainer, species and level, and the nature is PID mod 25.
  - For the calc: show a min–max range over natures, or assume neutral, and label it.
- `ability` and `abilityId` are an explicit override when nonzero.
- An empty `moves` list means the default level-up moves (150 Pokémon).
- `form` is not in `trainers.json`. Instead, the species `id` already points at the form entry: 21 slots (Rotom forms, Wormadam Trash, Giratina Origin, Deoxys Speed/Defense; record 865 slot 1 has invalid form 4, so base Deoxys stats).

## 6. Mega Evolution and forms

**VERIFIED (data and emulator-tested per `site/src/lib/verified-mechanics.ts`):** Megas and similar forms are **held-item forms in the party**, not an in-battle Mega Evolution:

| Base | Item | Result |
|---|---|---|
| Charizard 6 | Charizardite 325 | **1027 Mega Charizard X** (Fire/Dragon, Mega Claws) for any nature except Timid/Modest; **1028 Mega Charizard Y** (Fire/Flying, Drought) for Timid or Modest |
| Mewtwo 150 | item 114 | 1440 Armored Mewtwo (Psychic/Steel) |
| Greninja 658 | Ninja Scroll 761 | 1194 Ash-Greninja |
| Giratina 487 | Griseous Orb 112 | 1152 Origin |
| Arceus 493 | Plates 298–313 | Typed forms |

- **INFERRED:** there is no Mega button or in-battle Mega Evolution. No trainer party uses a Mega form.
- The calc should treat the form species id as the Pokémon. When the user gives Charizard a Charizardite, it should automatically pick 1027 or 1028 from the nature.

**Battle-only forms whose handlers exist:**
- Stance Change (176), Zen Mode (161), Schooling (208), Disguise (209), Ice Face (248), Power Construct (211), Hunger Switch (258), Zero to Hero (278), Forecast (59), Flower Gift (122).
- Battle Bond (210): its Water Shuriken power handler rewrites power to 20 (event `0x70`). **INFERRED**: hit count changes elsewhere.
- `species.json` has a `battleOnly` field (7 entries).

## 7. What `trainers.json` gives, and what's missing

Per Pokémon: `id` (species or form entry), `level`, `ability` + `abilityId`, `item` + `itemId`, `moves` + `moveIds`, `nature` (or null), `ivs`, `hpIvs` and `evs`. Per trainer: `double` (battle type) and the trainer's bag `items`.

**Missing for a calc:**
- The generated nature (see §5).
- Gender, which matters for Rivalry and Attract.
- Friendship for Return and Frustration. The loader sets none, so **INFERRED** it is the species base friendship, which is not exported.
- The weight source.
- Stat stages and status at battle start (none).
- AI move choice.
- Whether the English patch's difficulty options matter: they don't touch trainer stats.

## Recommended calc model

Use **@smogon/calc's Gen 5–9 code path (`mechanics/gen789.ts` / `gen56.ts` structure) with generation 9 behaviour**. Disable Tera, Dynamax and Z-moves. Feed it the site's own species, moves, abilities, items and type data instead of the Smogon dex.

The Gen 4 path is wrong for this game on every point: crit ×2, the modifier order, rounding, the missing Fairy type, and the vanilla ability values.

**Deviations to implement:**

1. Data:
   - Species stats and types come from `species.json` (retypes, rebalanced BSTs, custom forms 1027+).
   - Move type, category, power, hits and crit stage come from `moves.json`.
   - Read move flags from `flagBits` (bit 7 punch, 8 sound, 29 bite, 34 slicing).
2. Damage order: insert **×2 (floor via ×200/100) after weather and before crit** when the defender is under Glaive Rush's vulnerability (INFERRED).
3. Crit: ×1.5 (floor). Rates 1/24, 1/8, 1/2, 1 (as Gen 7+; the Gen 6 calc uses 1/16).
4. Overgrow, Blaze, Torrent and Swarm at ≤ ½ HP (×1.5 to the attack stat).
5. Swarm also takes ×0.75 from super-effective hits.
6. Limber and Shell Armor: Def ×1.25 against physical. Shell Armor keeps its crit immunity.
7. Marvel Scale boosts Def **and** SpD ×1.5.
8. Damp: all Fire moves on the field ×0.8 power; the holder's Water moves ×1.2.
9. Iron Fist ×1.3.
10. Tough Claws ×1.3 on **all** of the holder's moves.
11. Quick Feet: physical Atk ×1.5 while statused, and ignores burn.
12. Sniper: +1 crit stage, plus ×1.5 on crits.
13. Leaf Guard: in sun, SpA ×1.5 and Def ×1.5 against physical.
14. Cursed Body: Ghost moves ×1.3 to the attack stat.
15. Telepathy: Psychic ×1.3 on Psychic Terrain.
16. Wonder Skin: SpD ×1.5 against special.
17. Battle Armor: no crits.
18. Mega Launcher: only Water Pulse, Aura Sphere, Dark Pulse, Dragon Pulse and Origin Pulse (×1.5). No Terrain Pulse, and not the author's cannon list.
19. Custom abilities:
    - Burning/Azure/Grass/Dark Skin and Dragonize: Normal → Fire/Water/Grass/Dark/Dragon, ×1.2.
    - Mega Claws: physical Atk ×1.3.
    - Flame Mane: Fire ×1.5 attack stat.
    - Desert Hawk: physical Atk ×1.3 in sand.
    - Mega Sol: own moves in sun.
    - #327: ×0.75 damage taken with a status condition.
    - Aurora Shine: Aurora Veil on entry.
    - Wildfire: sun on entry.
    - Thunder Roar: Electric Terrain on entry.
20. Soul Dew: SpA and SpD ×1.5 for Latias/Latios (not ×1.2 power).
21. Weather 4 (Snow Warning / hail-type) gives Ice-type Def ×1.5. Keep sand's Rock SpD ×1.5.
    - Primal rain and sun use the normal ×1.5/×0.5 at the damage step. Whether moves fail is UNKNOWN.
22. Items 110, 111, 252 and 324 (including the trainers' "Rocky Helmet" 324) have no battle effect. Use ids 584, 600, 576 and 590 for Eviolite, Weakness Policy, Air Balloon and Rocky Helmet.
23. Gems are ×1.3. Terrain boosts are ×1.3. -ate abilities and Normalize are ×1.2. Transistor is ×1.3. Knock Off is ×1.5. Hidden Power has fixed power 60 (all as Gen 7–9).
24. Stats and trainers:
    - Standard stat formula.
    - Trainer IVs: `hpIvs` for HP, `ivs` for the other five.
    - EVs exactly as given (the total may exceed 510).
    - `nature: null` means "generated": show the range or assume neutral, and label it.
25. Forms: no in-battle Mega Evolution. Charizardite picks 1027 or 1028 by nature; Armored Mewtwo, Ash-Greninja, Origin Giratina and the Arceus Plates are also held-item forms.
26. Open checks to do in the emulator before release. **Done 2026-10-14**: `damage_calc_parity.md` (damage
    routine hooked on the CN ROM, 225 real hits and 1,078 AI estimates, all equal to the calc after its fixes):
    - The Glaive Rush ×2 step: **VERIFIED** (after weather, before the crit; lasts until the user's next action).
    - Sonic Boom and Dragon Rage fixed damage: **contradicted**, they are 1-power moves (hack bug).
    - Weight data (Low Kick, Heavy Slam): VERIFIED earlier (`damage_calc_data.md` §1, battle weight 1).
    - Hail versus Snow id 4: **VERIFIED** Snow (Ice Def ×1.5, no chip damage).
    - Item 324 being inert: **VERIFIED** (no recoil; item 590 deals 1/6). Item 110 also inert.
    - Corrosion's exact effectiveness: **contradicted**, Poison moves still do not affect Steel.
    - Parental Bond's second-hit multiplier: **VERIFIED** ×0.25, applied as target ratio 1024 at step 4.
    - Trainer PID/nature generation and friendship: VERIFIED earlier (`damage_calc_data.md` §2–3).
    - Also corrected by the emulator: type effectiveness is one combined shift (not one factor at a time),
      Soul Dew's Sp. Def handler boosts the holder's target (hack bug), ability #327 protects a statused ally
      (not its holder), and a spread move hitting one Pokémon is not reduced.
