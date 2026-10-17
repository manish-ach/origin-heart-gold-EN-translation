# Damage calculator: data added to the site export

Research date 2026-10-14. Reference ROM: the untouched Chinese ROM `work/rom/origin_v4.0.3_cn.nds` (D-1002).
Addresses are for the CN v4.0.3 arm9 (loaded at 0x02000000) and overlay 14 (battle engine, see
`damage_calc_mechanics.md`). Exporter: `work/tools/site/export_data.py`; readers in `work/tools/docs/romdata.py`;
tests in `work/tools/docs/test_trainer_runtime.py`.

Legend: **VERIFIED** = read from the code or the data and checked in the emulator; **INFERRED**; **UNKNOWN**.

## Fields added

| file | field | coverage | status |
|---|---|---|---|
| `species.json` | `height` (dm), `weight` (hg) | ids 1–1025 (all base species); not on the 415 form records 1026–1440 | VERIFIED (Pokédex data) |
| `trainers.json` team | `nature` now filled for the 2,731 generated natures | 3,891 of 3,891 Pokémon | VERIFIED |
| `trainers.json` team | `natureSource`: `"set"` (1,160, stored in the party data) or `"generated"` (2,731, from the personality value) | all | VERIFIED |
| `trainers.json` team | `gender`: `male` 2,454 / `female` 1,160 / `genderless` 277 | all | VERIFIED |
| `trainers.json` team | `friendship`: 255 for all 3,891 (no party has Frustration) | all | VERIFIED |

Nothing else in the data changed (checked by stripping the new fields from a full regeneration and from the
committed files: identical).

## 1. Height and weight

**Source (VERIFIED):** NARC `a/0/7/4` (the HGSS Pokédex data archive, expanded by the hack). Member 0 = height in
decimetres, member 1 = weight in hectograms, one u32 per **species index** (`romdata.ZUKAN_HEIGHT/WEIGHT`).
Member 0 has 1,026 rows (row 0 = 999, a placeholder), member 1 has 1,389 rows. `a/2/1/4` is the untouched
vanilla copy (494 rows) and is not used.

**Checks:**
- In-game Pokédex on the CN ROM (emulator, `emu_dex` capture): Charizard 1.7 m / 90.5 kg; the entry the
  hack's Pokédex shows as No. 0649 is Phantump (species index 708): 0.4 m / 7.0 kg = rows 708; No. 0650
  Trevenant (709): 1.5 m / 71.0 kg. So the Pokédex reads the rows by species index, not by its own numbering.
- Official values match for Bulbasaur 0.7/6.9, Charizard 1.7/90.5, Pikachu 0.4/6.0, Snorlax 2.1/460.0,
  Dragonite 2.2/210.0, Rayquaza 7.0/206.5, Arceus 3.2/320.0, Victini 0.4/4.0, Genesect 1.5/82.5,
  Phantump 0.4/7.0, Eternatus 20.0/950.0, Pecharunt 0.3/0.3 (m/kg).

**Forms not exported:** rows 1026–1388 of the weight member hold form weights in another order than the hack's
species indexes (e.g. rows 1028–1030 = 60.8 kg three times, the Deoxys formes, while index 1028 is Mega Charizard
Y; rows 1031–1057 = 5.0 kg, the Unown letters). The code that maps a form to its row was not found, so the
415 form records have no `height`/`weight`.

### The battle does not use these weights (VERIFIED, likely a hack bug)

The battle Pokémon keeps its weight in a u16 at `+0x29C` (getter ov14 `0x02218200`). The battle-weight function
ov14 `0x02205E60` returns `max(1, round(field × modifier / 4096))`, with the modifier from event `0x8A`
(Heavy Metal, Light Metal, Float Stone and similar). Low Kick and Grass Knot (thresholds 100/250/500/1000/2000 hg)
and Heavy Slam / Heat Crash (ratio 5/4/3/2) call it.

Nothing writes the species weight into `+0x29C`. In the emulator (CN ROM, trainer battles 6, 102 and others) the field is 0
for every battle Pokémon when the set-up ends, and the clamp at ov14 `0x022164D8` sets it to 1. With a Lv100
Venusaur using Grass Knot against trainer 102's Milotic (162.0 kg in the Pokédex), the weight function
returned 1 and the move handler wrote base power **20** (RewriteValue var 49). So in this hack:

- Low Kick and Grass Knot always have 20 power (weight 0.1 kg; modifiers cannot raise 1 past the 10 kg step).
- Heavy Slam and Heat Crash compare 1 with 1 (ratio < 2): 40 power, unless a weight modifier applies to
  either side (Heavy Metal ×2 gives 2, ratio 2: 60).

For the calc, use battle weight 1 (D-1002), not `species.weight`. `species.weight` is the Pokédex value, for
display. This is a candidate hack finding (a bug of the original hack), recorded in the decision register as D-2540.

## 2. Trainer personality values, natures and genders

Party loader arm9 `0x0207272C` (per Pokémon from `0x020727A2`). VERIFIED in code, then reproduced exactly in
the emulator (see Validation).

```
mod  = 0x78 if class_gender[class & 0xFF] == 1 else 0x88   # 0x0207277A; table 0x020FF77C (0x02072720)
for each Pokémon (record r):
    seed = trainerId + r.species + r.level + r.ivByte       # 0x020727B6..0x020727C4, then SetLCRNGSeed
    rnd  = seed; repeat (class & 0xFF) times: rnd = LCRandom()   # 0x020727DC; LCRNG 0x02020480:
                                                            # s = s*0x41C64E6D + 0x6073, returns s >> 16
    0x0207295C(species, form, r.byte1, &mod):               # only when byte 1 != 0
        low nibble g != 0: mod = genderRatio(species, form) + (2 if g == 1 else -2)
        high nibble 1: mod &= ~1;  high nibble 2: mod |= 1
    pid  = (rnd << 8) + mod                                 # 0x020727F2
    CreateMon(species, level, ivByte*31/255, fixed pid, OT id type 2)   # 0x0206D0C0
```

- `trainerId` is BattleSetup's trainer id for that battler (`+0x18 + 4·battler`): the TrainerBattle id, which is
  the `a/0/5/5` record for ordinary trainers.
- `mod` is set once per party and **never reset**, so a byte-1 change carries over to the next Pokémon. It also
  carries over between Pokémon with byte 1 = 0. Trainer 6's Rattata (byte 1 = 0) gets low byte 0x89 from the Starly
  before it. Observed.
- With class 0 there is no LCRandom call and the seed itself is shifted (13 trainers; observed with 167 and 29).
- Nature (`0x0206F1A0`): field 190 (the party data's explicit nature, stored as `nature + 1` at `0x020728C8`)
  when set, else `pid % 25`.
- Gender (`0x0206F344` → `0x0206F3A0`, set at creation into field 111): the **base species'** gender ratio,
  even for a form (it loads personal data by the raw species, with no form lookup). 0 = male, 254 = female,
  255 = genderless, else female when `ratio > (pid & 0xFF)`. The byte-1 gender tweak uses the form's ratio.
  `export_data.py` does the same (PID with the form's ratio, gender with the base species' ratio), so the
  review note about mixing the two ratios needs no data change.
- Explicit natures are unchanged; the PID (and so the gender) is generated the same way for them.

Functions: `romdata.trainer_personalities`, `nature_from_personality`, `gender_from_personality`.

### Ability slot: not exported

The ability doesn't depend on the PID here. CreateBoxMon draws `LCRandom() % 100` after the OT-ID loop
(`0x0206D31C`) and stores `≥ 50` in field 188. `0x02071524` then picks personal ability 2 (or 1 if empty) when
188 is set, the hidden ability when field 113 is set, else ability 1. Only 3 trainer records have no explicit
ability: two Castform (one ability) and the empty record of trainer 760. So the slot never matters, and it is not
exported.

## 3. Friendship

`0x020729A8`, run after the moves are set: friendship (field 9) = 0 when any move slot is Frustration (218), else
255. This overwrites the species' base friendship from CreateMon. No trainer Pokémon knows Frustration: none of the explicit
movesets has it, and none of the 150 default (level-up) movesets can, because no learnset has it at or below
the level. So `friendship` is 255 everywhere. The exporter would write `null` for a default moveset whose
learnset could give Frustration.

## Validation (emulator, CN ROM, 2026-10-14)

Harness (`work/tools/emu_harness.py`, DeSmuME, `trainer.sav` from the main checkout's `work/build/memcheck`, clock
pinned). The game's TrainerBattle starts each battle. Exec hooks: `0x020727C6` (seed), `0x0207281E` (species, level,
pid argument of CreateMon), `0x0207291A` (finished Pokémon, decoded), `0x022164D8` (battle Pokémon weight),
`0x02205E9A/0x02205EA6` (battle weight), `0x0220FD30` (RewriteValue, power var 49). Scripts and logs:
a session scratchpad, not kept (`emu_trainer.py`, `emu_weight.py`, `emu_dexshot.py`,
`compare.py`).

| trainer | class | what it covers | PIDs |
|---|---|---|---|
| 6 | 2 (male) | byte 1 = 0x20, carry-over to the next Pokémon | 2/2 |
| 9 | 50 (female) | female class, 0x20 on all four | 4/4 |
| 165 | 58 | gender nibble 3 (ratio − 2) | 3/3 |
| 167, 29 | 0 | no RNG call | 10/10 |
| 557 | 95 | explicit natures, Giratina-O | 6/6 |
| 102 | 36 | (Grass Knot run) | 2/2 |

All 27 different Pokémon (29 rows; trainer 6 was run twice) have exactly the predicted PID. The decoded Pokémon's
nature (pid % 25 for the generated ones), gender (block B gender bits) and friendship (255) match the export.
Unit tests pin these values and hash the code regions above (`TrainerPersonalityTests`).

## Regenerating

`export_data.py` adds the new fields itself. `romdata.Rom` now reads `a/0/7/4` too and rebuilds an older
`docs_cache.pkl` that lacks it.

The committed `site/src/data/*.json` are older than the committed inputs: a plain regeneration on this branch
also rewrites move, item and ability descriptions, trainer conditions and names, and guide quest links in 6 files.
These changes come from the bank and guide edits of commit 425c1ee, not from this work. To keep this diff limited
to the new fields, the files in this branch were made by regenerating into a scratch folder and copying only
`height`, `weight`, `nature`, `natureSource`, `gender` and `friendship` into the committed JSON (same serialiser).
A later full regeneration gives the same values for these fields.

## Open points

- Battle weight is always 1 (above): recorded as hack finding D-2540 (open). The calc uses weight 1, as the game does.
- Form heights and weights: the mapping from a form to its row in `a/0/7/4` is not known.
- `TrainerCard.astro` no longer says "“Generated” means the nature can vary": every nature is now exact.
- PIDs assume the battle's trainer id is the `a/0/5/5` record number, as for every script TrainerBattle. Battles that
  start with another id (none known) would differ.
- Byte 0x1A of a party record sets field 189. `0x0206F3F8` returns 1 for it, so it is probably a forced-shiny
  flag (INFERRED). It isn't exported and doesn't affect damage.
