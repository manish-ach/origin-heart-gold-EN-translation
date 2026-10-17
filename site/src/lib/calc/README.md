# Origin HeartGold damage engine

Vendored and trimmed from [@smogon/calc](https://github.com/smogon/damage-calc) (MIT, see `LICENSE`; published as `/licenses/smogon-damage-calc.txt` and linked from the Team Builder credit line; the `/*! @license */` banner in `index.ts` is kept in the bundle by `vite.build.rolldownOptions.output.comments.legal` in `astro.config.mjs`),
upstream commit `9c57e9b8` (2026-10-11), package `calc/` 0.12.0. The Gen 5–9 path (`mechanics/gen789.ts`,
`mechanics/util.ts`, `desc.ts`, `stats.ts`, `items.ts`, `pokemon.ts`, `move.ts`, `field.ts`, `result.ts`) was
copied and adapted; hack-specific changes are marked `OHG:` in the code.

Behaviour source of truth: `work/notes/damage_calc_mechanics.md` ("Recommended calc model") and
`work/notes/damage_calc_data.md` (battle weight, trainer natures/genders/friendship).

## Files

| File | Role |
|---|---|
| `index.ts` | Public API (`loadCalc`, `fromTrainerMon`, `mirrorField`, `buildCalcData`); documented at the top |
| `data-projection.ts` | Builds the compact `calc-data.json` from `src/data/*.json` (build time) |
| `generation.ts` | OHG `Generation`: species/moves/abilities/items keyed by the hack's ids, type chart, natures |
| `caveats.ts` | Player-facing caveat texts and the lists of unmodelled/unverified effects |
| `mechanics/ohg.ts` | The damage routine (from `gen789.ts`) |
| `mechanics/util.ts`, `desc.ts`, `stats.ts`, `items.ts`, `pokemon.ts`, `move.ts`, `field.ts`, `result.ts`, `types.ts` | Trimmed upstream core |

Format: TypeScript limited to erasable syntax (no enums, namespaces or parameter properties) with explicit `.ts`
imports, so both Vite/Astro and Node's type stripping (`npm test`) load it directly.

## Removed from upstream

Gen 1–4 mechanics (`gen12.ts`, `gen3.ts`, `gen4.ts`), `gen56.ts`, `champions.ts`, Terastallization and Stellar,
Dynamax / Max Moves / G-Max side effects, Z-Moves, Mega Evolution by Mega Stone, the bundled Showdown data
(`data/*`), Natural Gift berry data, Techno Blast/Multi-Attack tables (replaced by small inline maps), TR Fling
powers, 39-roll tables, Salt Cure, Nightmare, `Generations`, the CommonJS `index.ts` wrapper, and the
`State` namespace (replaced by plain interfaces in `types.ts`).

## OHG deviations (numbers = list in `damage_calc_mechanics.md` "Recommended calc model")

1. Data from the site JSON: species stats/types incl. forms 1027+, move type/category/power/hits/priority/crit
   stage, flags from `flagBits` (bit 0 contact, 7 punch, 8 sound, 29 bite, 34 slicing, 30 ballistic) — §4, §1.
2. Glaive Rush ×2 (×200/100, floor) after weather, before crit (`defenderSide.glaiveRush`). Emulator-verified: the
   vulnerability lasts from the move until the user's next action — §1 step 6, parity note "glaive".
3. Crit ×1.5 (×150/100, floor); crit rates 1/24, 1/8, 1/2, 1 returned as `critChance` — §1 Critical-hit rate.
4. Overgrow/Blaze/Torrent/Swarm at HP ≤ ½ — §2.
5. Swarm takes ×0.75 from super-effective hits — §2.
6. Limber and Shell Armor: Def ×1.25 against physical; Shell Armor still blocks crits — §2.
7. Marvel Scale: Def and SpD ×1.5 — §2.
8. Damp: every Fire move ×0.8 (0xCCD); holder's Water ×1.2 — §2.
9. Iron Fist ×1.3 — §2.
10. Tough Claws ×1.3 on all moves — §2.
11. Quick Feet: physical Atk ×1.5 while statused, ignores burn — §2, §1 step 11.
12. Sniper: +1 crit stage and ×1.5 on crits — §2.
13. Leaf Guard in sun: SpA ×1.5, Def ×1.5 against physical — §2.
14. Cursed Body: Ghost ×1.3 to the attacking stat — §2.
15. Telepathy: Psychic ×1.3 on Psychic Terrain (terrain id INFERRED → caveat) — §2.
16. Wonder Skin: SpD ×1.5 against special — §2.
17. Battle Armor blocks crits — §2.
18. Mega Launcher: hard-coded list (Water Pulse, Aura Sphere, Dark Pulse, Dragon Pulse, Origin Pulse), ×1.5 — §2.
19. Custom abilities 312–327: Burning/Azure/Grass/Dark Skin and Dragonize (-ate ×1.2), Mega Claws (physical ×1.3),
    Flame Mane (Fire ×1.5), Desert Hawk (physical ×1.3 in sand; speed effect unknown → caveat), Mega Sol (own moves
    in sun), #327 (never protects its holder: ×0.75 for a statused ALLY in doubles, not modelled → caveat;
    emulator-verified), Aurora Shine / Wildfire / Thunder Roar set Aurora Veil / sun /
    Electric Terrain on entry (field option `abilityField`), Ninja Bond blocks like Wonder Guard (caveat),
    Blazing Awe absorbs Fire — §2.
20. Soul Dew (hack bug D-2541, emulator-verified): a Latias/Latios holder using a special move gets SpA ×1.5 AND its
    target gets SpD ×1.5 (the event-0x77 handler checks the attacker's id); a holder that is hit gets nothing — §3.
21. Hail (engine weather 4, set by the Hail move and Snow Warning) is Gen 9 Snow: Ice Def ×1.5 and no chip damage
    (emulator-verified); sand: Rock SpD ×1.5, 1/16 chip; primal sun/rain only change the damage step (move failure
    UNKNOWN → caveat) — §1 Defense, §1 step 5.
22. Items 110/111/252/324 are inert (distinct engine names, caveat when held; 110 and 324 emulator-verified);
    584/600/576/590 are the live ones (584 Eviolite and 590 Rocky Helmet 1/6 verified) — §3.
23. Gems ×1.3, terrain ×1.3, -ate/Normalize ×1.2, Transistor ×1.3, Knock Off ×1.5, Hidden Power 60 with the IV type
    table (no Fairy); Muscle Band/Wise Glasses are ×1.1 final modifiers — §1 Terrain, §2, §3, §4.
24. Stats: standard formula; trainer IVs = `hpIvs` (HP) and `ivs` (others), EVs as given (no 510 cap); natures,
    genders and friendship from trainers.json (`damage_calc_data.md` §2) — §5.
25. Held-item forms: Charizardite → 1027 (any nature but Timid/Modest) or 1028; Steel Armor → 1440, Plates,
    Griseous Orb, Ninja Scroll (from `formChanges` in `verified-mechanics.ts`) — §6.

Also from the notes: type effectiveness applied as ONE combined step (×2·×½ is exactly ×1; emulator-verified,
the old one-factor-at-a-time order lost 1 point on odd values — parity note "types2"); Sonic Boom / Dragon Rage
have no fixed damage and hit as 1-power moves (emulator-verified hack bug D-2542); Corrosion does not let Poison moves
hit Steel (emulator-verified, D-2543);
Grassy Terrain halves Earthquake only (§1 Terrain); Psyshock/Psystrike/Secret Sword hit Def, Chip Away/Sacred
Sword/Darkest Lariat ignore stages, Tera Blast 100, Super Fang/Ruination/Nature's Madness ½ HP, Return/Frustration
from friendship — §4; battle weight is always 1 hg, so Low Kick /
Grass Knot are 20 power and Heavy Slam / Heat Crash 40 (60 with Heavy Metal, INFERRED; hack bug D-2540) — `damage_calc_data.md` §1.

Emulator-verified (work/notes/damage_calc_parity.md; regression fixtures in `site/tests/damage-calc-parity.*`):
the whole formula order and rounding, crit ×1.5, spread ×0.75 (2 and 3 targets), screens ×0.5 / ×2732
in doubles, weather, sand/hail defence boosts, burn, Glaive Rush, Parental Bond's ×0.25 second hit (applied at the
spread step), paralysis Speed ×0.5, Leftovers / burn / sand 1/16, poison 1/8, badly poisoned n·⌊max/16⌋, Black
Sludge 1/8, Life Orb ×1.3 and 1/10 recoil, Rocky Helmet 1/6, Stealth Rock 1/8, Sitrus Berry 1/4 at ≤ ½.

Assumed but untraced (flagged by caveats): Sheer Force's move list, Bulletproof's move list, the other
end-of-turn amounts (Leech Seed, Grassy Terrain, Dry Skin, Rain Dish, Ice Body, Poison Heal, Bad Dreams, trapping).
