# Damage calculator: in-game parity (emulator)

Run date 2026-10-14. Reference ROM: the untouched Chinese ROM `work/rom/origin_v4.0.3_cn.nds` (D-1002), DeSmuME
through `work/tools/emu_harness.py`. Engine under test: `site/src/lib/calc/` (branch `feature/damage-calc`).
Earlier static findings: `damage_calc_mechanics.md`; trainer data: `damage_calc_data.md`.

**Result:** after the fixes below, every observed hit equals the calc's number for the game's own roll:
**225 / 225 real hits** and **1,078 / 1,078** AI damage estimates (same routine, see Method). 111 further AI
estimates were left out because the calc gives no number for them by design (immune targets, Counter/Mirror Coat),
and 24 because the routine returns its minimum of 1 for an immune target while the calc returns 0 (no real hit
can happen there). Eight engine fixes; six caveats removed, two reworded, two added.

## Method

**Exact, not statistical.** The harness hooks the damage routine `ov14 0x0220876C` and reads, for every call:

| address | value |
|---|---|
| `0x0220876C` (entry) | attacker / defender battle Pokémon (r0/r1), move param (r2: `+0` move id, `+8` type, `+9` category), effectiveness code (r3), target ratio `[sp]`, crit flag `[sp+4]`, caller (lr) |
| `0x02208848` / `0x0220885A` / `0x02208868` / `0x02208870` | power, attack stat, defence stat, level |
| `0x02208882` / `0x022088A0` / `0x022088BA` | base damage, weather ratio, Glaive Rush flag (condition `0x2D`) |
| `0x022088E4` | the random roll `R` (85–100) |
| `0x022088FA` / `0x02208938` / `0x02208966` | STAB ratio, damage before the final modifiers, final-modifier chain |
| `0x02208994` | the final damage (stored u16) |

The calc's 16 rolls are indexed by `R − 85`, so each hit gives one exact expected number. The battle Pokémon struct
(`+0x00` species, `+0x16` ability, `+0x1C` max HP, `+0x1E` current HP, `+0x20` item, `+0x24` level, `+0x22C…0x234`
Atk/Def/SpA/SpD/Spe, `+0x240…0x246` stat stages Atk/Def/SpA/SpD/Spe/Acc/Eva, 6 = neutral) is read at each call;
the calc's stats (from the decoded IVs/EVs/nature) are compared with these too, so every case also checks stats.

- **Callers:** `0x0221C441` is a real hit. `0x02223447` is the AI's own damage estimate: the foe AI runs the same
  routine (with its own roll) for each of its moves before acting. (The mechanics note called the call at
  `0x02223442` a confusion self-hit; in these runs it only produced AI estimates.) Both are compared; the tables
  count real hits only.
- **Pokémon:** the player's Pokémon are built with the hack's own generator (`generate_pokemon`), then given moves,
  item, ability and status with the save core's fixture edit (the battle reads the ability with
  `GetMonData(0xA)`, `0x022161AE`). Wild opponents: a scripted `WildBattle`, edited in every RAM copy right after
  the wild finalizer (moves, item, ability). Trainer opponents: the game's `TrainerBattle` (`TrainerBattle t t`
  = a double battle with one team); for some cases their moves/ability are edited at the loader's end
  (`0x0207291A`). The party is cut to the scenario's Pokémon so nothing levels up or evolves mid-run.
- **Forcing:** HP and Speed are written into the battle struct before a turn when a case needs it (½-HP
  abilities, Sitrus Berry, move order, keeping a target alive). A forced critical hit sets the routine's crit
  argument (tests the ×1.5 and stage handling, not the crit chance). Stat stages, weather and the Glaive Rush
  flag are taken from the game state (Intimidate's drop is in the observed stages, so the calc does not apply it
  twice).
- **Without a damage number** (end of turn, recoil, move order) the HP of every battle Pokémon is logged before
  and after each turn, and the order of the damage calls within a frame gives the move order.

**Harness** (new, `work/tools/damage_parity/`): `scen.py` (one scenario per process; `rebuild` re-derives the calc
inputs), `plib.py` (hooks, readers, doubles target selection), `calc_cmp.mjs` (runs the calc on the records),
`summarize.py`, `run_all.py` (3 emulators at a time), `mkfix.py` (writes the test fixtures), `specs/*.json`
(26 scenarios). Run: `.venv/bin/python work/tools/damage_parity/run_all.py <run>` (the project venv); output in
`work/build/parity/<run>/` (git-ignored). The final run is `work/build/parity/final1/` (about 7 minutes).
The save is `work/build/memcheck/trainer.sav` of the main checkout (or `$PARITY_SAV`).

**Regression tests:** `site/tests/damage-calc-parity.test.mjs` replays all 225 real hits from
`site/tests/damage-calc-parity.fixtures.json` (sets, field, crit, roll, observed damage and stats; trainer
Pokémon as `{trainer: [id, index]}`, i.e. `fromTrainerMon` on the exported data), plus the behaviour checked
without a damage number. `site/tests/damage-calc.test.mjs` was updated for the fixes.

## Cases

Calc = the calc's 16-roll range for that hit; "in game" = roll, crit flag and damage of one representative hit;
n = real hits in the run (all PASS). Pokémon: a Lv 50 Machamp attacker (No Guard unless the case sets an
ability) against a Lv 100 Snorlax (Run Away, no item) unless named.

### 1. Baseline formula

| case | calc | in game | n | verdict |
|---|---|---|---|---|
| neutral, non-STAB (Tackle) | 11–14 | R89 → 12 | 1 | PASS |
| STAB super effective (Brick Break) | 62–74 | R96 → 72 | 1 | PASS |
| crit ×1.5 (Tackle; Brick Break) | 17–21; 92–110 | R93 crit → 19; R96 crit → 104 | 2 | PASS |
| special, non-STAB (Ember) | 5–6 | R93 → 5 | 1 | PASS |
| ×4 / ×¼ (Brick Break / Tackle vs Bastiodon) | 60–72 / 1 | R89 → 60 / R96 → 1 | 5 | PASS |
| ×½·×½ (Rock Slide vs Bastiodon), ×2 / ×¼ vs Crobat, ×2·×½ vs Aerodactyl | | | 9 | PASS |
| **×½·×2 order** (Fire Punch / Flamethrower vs Bastiodon, Rock/Steel) | 10–12 | R96 → 11 | 8 | **FAIL → fixed** (calc gave 10: it floored after ×½, then ×2) |
| burn halves physical, not special; burn + crit | 5–7; 8–10 | R85 → 5; R86 crit → 9 | 4 | PASS |
| rain / sun on Water and Fire (×1.5 / ×0.5) | | R100 rain Water Gun → 9; R86 sun Ember → 7 | 6 | PASS |
| sand: Rock SpD ×1.5 (Sudowoodo) | 2–3 | R95 → 2 (SpD 196 → 294) | 4 | PASS |
| Hail (weather 4): Ice Def ×1.5 (Glalie), SpD unchanged | 5–7 | R97 → 6 (Def 281 → 421) | 4 | PASS |
| Reflect / Light Screen singles ×0.5, crit ignores them | 6–8 | R88 → 7 (final ×2048) | 7 | PASS |
| doubles: spread ×0.75 (Rock Slide, Hyper Voice, Earthquake on 3), Reflect + Light Screen ×2732 | | ratio 3072, final 2732 | 21 | PASS |
| **doubles: spread move on a lone foe** | 385–453 (with spreadTargets 1) | R98 → 443, ratio **4096** | 2 | **FAIL → fixed** (calc always applied ×0.75) |

### 2. Open items

| case | calc | in game | n | verdict |
|---|---|---|---|---|
| Glaive Rush ×2 (foe's Tackle after it) | 51–60 | flag set, R85 → 51 (control 25) | 9 | PASS (verified; caveat removed) |
| Glaive Rush timing | | ×2 from the move until the user's next action: also on the next turn if the foe moves first, gone once the user has moved again | | VERIFIED |
| **Sonic Boom / Dragon Rage** | was 20 / 40 | power **1** in the formula: 1–3 damage (crit 2) | 5 | **FAIL → fixed** (hack bug D-2542, below) |
| Seismic Toss (level), Super Fang (½ HP) | 50; 201 | 50; 201 | 2 | PASS |
| item 324 "Rocky Helmet" on the target | | no recoil after contact; item 590 takes 25 = ⌊150/6⌋ | 4 | VERIFIED inert (caveat reworded) |
| item 110 "Eviolite" on Chansey | 37–44 | R99 → 43, SpD unchanged; item 584 gives Def/SpD ×1.5 | 4 | VERIFIED inert |
| **Corrosion** (Poison Jab, Sludge Bomb vs Registeel) | was ×2 | **no damage call at all**: Poison still cannot hit Steel | 0 | **FAIL → fixed** (hack finding D-2543) |
| Parental Bond second hit | 13–17 total | 2nd hit target ratio 1024 (×0.25 at step 4): 12 + 3 | 10 | PASS (verified; caveat removed) |
| paralysis Speed ×0.5 | | Speed 100 paralysed: moves before 49 and 24, after 51 and 26 | 17 | VERIFIED (caveat removed) |
| Life Orb | 14–18 | final ×5324; recoil 15 = ⌊150/10⌋ | 2 | PASS |
| Leftovers | | +⌊max/16⌋ (222 → 13; 82 → 5) | | VERIFIED |
| burn / sandstorm chip | | ⌊max/16⌋ (150 → 9) | | VERIFIED |
| Hail chip | | **none** (a Machamp kept 114/150 for 4 turns of hail) | | **calc fixed** (hail chip removed) |
| poison / badly poisoned | | ⌊max/8⌋ (434 → 54); toxic n·⌊max/16⌋: 28, 56, 84, 112 at 461 (not ⌊n·max/16⌋ = 57, 86, 115) | | VERIFIED; **toxic formula fixed** |
| Black Sludge on a non-Poison holder | | −⌊max/8⌋ (451 → 56) | | VERIFIED |
| Stealth Rock | | −⌊max/8⌋ on a neutral switch-in (82 → 10, 127 → 15) | | VERIFIED |
| Sitrus Berry | | at ≤ ½ after a hit: +⌊max/4⌋ (434: 213 → 321) | | VERIFIED (the KO-chance caveat stays: it is not modelled) |

### 3. Hack-changed abilities and items

| case | calc | in game | n | verdict |
|---|---|---|---|---|
| Limber defender: Def ×1.25 vs physical, not special, also on a crit | 10–12 | R85 → 10 | 3 | PASS |
| Shell Armor defender: Def ×1.25 | 9–11 | R91 → 10 | 2 | PASS |
| Marvel Scale (paralysed): Def and SpD ×1.5 | 10–12; 5–6 | Def 140 → 210, SpD 281 → 421 | 3 | PASS |
| Damp on the target: Fire power ×0.8 (40 → 32) | 5–6 | R87 → 5 | 2 | PASS |
| Damp holder: own Water ×1.2 (48), own Fire ×0.8 (32) | | | 2 | PASS |
| Iron Fist ×1.3 (Fire Punch 98, Mach Punch 52), not Tackle | 27–32 | R92 → 29 | 3 | PASS |
| Tough Claws ×1.3 on a special, non-contact move (Ember 52) | 6–8 | R86 → 6 | 2 | PASS |
| Overgrow at 75/150 HP (×1.5 Atk), not at 76 or 150 | 22–27 | R87 → 23 (Atk 121 → 181) | 4 | PASS |
| Swarm at ½ HP; Swarm defender ×0.75 from super-effective hits | 23–28; 73–87 | R91 → 25; R98 crit → 85 (final 3072) | 4 | PASS |
| Burning Skin, Dragonize (Normal → type, ×1.2) | 14–17 | Tackle power 48 | 3 | PASS |
| **ability #327** on a paralysed holder | was ×0.75 | full damage | 5 | **FAIL → fixed** (protects a statused ally in doubles instead, below) |
| Expert Belt ×1.2 on super effective only | 74–89 | final 4915 | 2 | PASS |
| Normal Gem ×1.3 once, then consumed | 14–17 | power 52, next turn 40 | 2 | PASS (the second hit needs the item cleared) |
| **Soul Dew** (Latios attacking; Latios hit) | was SpA and SpD ×1.5 on the holder | holder SpA ×1.5 **and the target's SpD ×1.5**; holder's own SpD not raised | 5 | **FAIL → fixed** (hack bug D-2541, below) |

### 4. Early trainers end to end

`calc.fromTrainerMon(trainers.json)` against what the game spawned, both directions (the player's Lv 100 Snorlax
with Tackle/Ember/Water Gun; trainers' AI picked their own moves). Every trainer Pokémon's Atk/Def/SpA/SpD from
the export equals the battle struct, and every hit matches.

| trainer | team | real hits | AI estimates | verdict |
|---|---|---|---|---|
| 8 Rival Blue (Route 22) | Rattata 4, Pidgey 5, Squirtle 7 | 8 | 105 | PASS |
| 4 Rival Blue (Route 5) | Wartortle 22 | 2 | 78 | PASS |
| 102 Beauty Lulu | Milotic 20 (Marvel Scale, Rain Dance), Kirlia 20 | 3 | 98 | PASS |
| 165 Jessie | Arbok 26 (Intimidate), Lickitung 25, Wobbuffet 24 | 5 | 74 | PASS |
| 11 Shady Guy Bob | Sandslash 32, Gastrodon 32, Rhydon 42 (Eviolite), Marowak 32 (Thick Club) | 23 | 587 | PASS |
| 6 Youngster Sol | Starly 4, Rattata 5 (default level-up moves) | 4 | 28 | PASS |

## Fixes made (all marked `OHG:` in the code)

1. **Type effectiveness is one combined step** (`mechanics/ohg.ts`, `typeFactors`). The game shifts once by the
   combined code (`0x022261B8`: 7 = ×1, `<<1`, `<<2`, `>>1`, `>>2`), so ×½·×2 is exactly ×1. The calc applied the
   factors one at a time and lost 1 on odd values when ×½ came first (Fire on Rock/Steel). Test helper `ref()`
   updated the same way.
2. **Sonic Boom and Dragon Rage** are 1-power moves (`mechanics/util.ts`, `calculateBasePowerOHG`): no fixed
   damage. Caveat removed; a note says so.
3. **Corrosion** no longer makes Poison hit Steel (`mechanics/util.ts`). Caveat removed; a note says so.
4. **Soul Dew** (`calculateDfModsOHG`): the holder's special moves get SpA ×1.5 and the target's SpD ×1.5; a holder
   that is hit gets nothing. A note says so.
5. **Ability #327**: no longer reduces damage to its holder; new caveat for its real effect (a statused ally in a
   Double Battle takes ×0.75), which the calc cannot model (allies are not inputs).
6. **Hail** has no chip damage in the end-of-turn KO maths (`desc.ts`); Ice Body healing kept (not tested).
   Caveat removed; a note says Hail works like Snow.
7. **Badly poisoned** damage is n·⌊max/16⌋ (`desc.ts`). (The API has no toxic counter yet, so this only matters
   once one is added.)
8. **Spread moves on a lone target:** new field option `spreadTargets` (1 = no ×0.75; default unchanged = 2 or
   more) and a caveat on spread moves in Doubles when it is not set.

Caveats removed: paralysis, hail, Glaive Rush, Corrosion, Parental Bond, Sonic Boom / Dragon Rage. The end-of-turn
caveat now appears only when an effect that was not checked is in the KO maths (Leftovers, burn, poison, toxic,
sand and Black Sludge damage are checked). The inert-item caveat says "checked in game" for 110 and 324.
Caveats added: ability #327, spread move target count.

## Hack bugs found (behaviour against the hack's own intent; not fixed, D-1002)

1. **Soul Dew's Sp. Def boost goes to the wrong Pokémon.** Its event-0x77 handler is a copy of the Sp. Atk one and
   checks the *attacker's* id (`0x0220C5C0`; Deep Sea Scale's checks the defender, `0x0220C5D8`). A Latias/Latios
   holder gets no Sp. Def boost, and its special attacks raise the target's Sp. Def ×1.5, cancelling its own
   Sp. Atk ×1.5. Observed: Snorlax SpD 266 → 399 against Latios' Psychic; Latios' SpD stayed 96 when hit.
2. **Sonic Boom and Dragon Rage deal 1–3 damage.** They have no fixed-damage handler, so the normal formula runs
   with the move data's power of 1 (both are listed as "var." power). The effect id path the mechanics note
   suspected does not give 20/40.
3. **Corrosion does not do what the author's note says** ("super-effective damage to Steel"): Poison moves still
   do not affect Steel types (no damage call; HP unchanged).
4. Already known: battle weight is never filled in (`damage_calc_data.md` §1).

Not bugs as far as can be told, but different from the notes: ability #327 helps a statused **ally** in doubles
(handler `0x0223A928` skips the holder; its entry handler also looks at statused allies), and the hack's
"hail" (weather 4) is Gen 9 Snow.

## Still open / NOT VERIFIED

- **Crit blocking** by Shell Armor / Battle Armor and the crit-rate table: forcing a crit bypasses the block, and
  the rate needs many samples. NOT VERIFIED.
- Abilities and items not in the sample: Quick Feet, Sniper, Leaf Guard, Cursed Body, Telepathy, Wonder Skin,
  Mega Launcher's list, Mega Claws, Flame Mane, Desert Hawk, Mega Sol, Aurora Shine, Wildfire, Thunder Roar,
  Ninja Bond, Sheer Force's list, Bulletproof's list; Muscle Band, Wise Glasses, Metronome, Plates, resist
  berries; duplicate items 111 and 252. Each is a one-spec addition to `work/tools/damage_parity/specs/`.
- End of turn not checked: Leech Seed, Grassy Terrain, Dry Skin, Rain Dish, Ice Body, Poison Heal, Bad Dreams,
  trapping moves, Black Sludge healing on a Poison type (the test holder was at full HP).
- Primal weather (move failure), Strong Winds.
- Parental Bond with fixed-damage moves and in doubles.
- The calc still has no toxic counter, Sitrus/pinch-berry healing or ally abilities as inputs (caveats stay).
- Harness limits: the roll is read, not pinned (each run gives other rolls; every comparison is still exact);
  the generator gives each run different IVs/natures, so the fixtures are tied to the final run's sets, not to
  fixed Pokémon; spread-move target selection uses touch points that assume the CN layout.
