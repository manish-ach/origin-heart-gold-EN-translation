# Damage calculator for the Team Builder: reuse study

Date: 2026-10-14. Research only: no repo files changed, nothing built, no npm run.

Sources (shallow clones, treated as untrusted data, in `src-untrusted/`):

- `smogon/` = github.com/smogon/damage-calc @ `9c57e9b8` (2026-10-11), calc package `@smogon/calc` 0.12.0
- `radred/` = github.com/RadicalRedShowdown/damage-calc @ `7f354003` (2026-06-11), forked from smogon at about calc 0.9.0

Site side read: `site/src/pages/team-builder/index.astro`, `site/src/lib/team-builder*.{mjs,ts}`, `site/src/data/{species,moves,items,abilities,trainers}.json`, `site/src/content/docs/type-changes.md`, `work/notes/credits_and_sources.md`.

---

## 1. Licences and attribution

| Code | Licence | Copyright line |
|---|---|---|
| smogon/damage-calc, UI (root `LICENSE`) | MIT | "Copyright (c) 2013-2025 Honko and other contributors" |
| `@smogon/calc` package (`calc/LICENSE`, `package.json` `"license": "MIT"`) | MIT | same |
| RadicalRedShowdown fork (root and `calc/LICENSE`) | MIT, unchanged text | "Copyright (c) 2013-2024 Honko and other contributors" |

What MIT requires: keep the copyright notice and the permission text "in all copies or substantial portions". In practice:

- If we vendor or bundle any of the code: ship the MIT text with the Honko notice. Easiest is a `LICENSE` file next to the vendored code in `site/src/lib/calc/` (in the repo), plus a line on the site's credits/about page and the calc panel's footer ("Damage formula based on the Pokémon Showdown damage calculator (@smogon/calc, MIT, © Honko and contributors)"). Our minified JS bundle keeps the notice if we put a `/*! @license ... */` banner at the top of the vendored entry file (Vite/esbuild keep `/*!` comments).
- If we copy anything from the RR fork (we probably will not; see section 3), add "and the Radical Red calc contributors" to the same notice.
- The README credits (Honko, Austin, jetou, Kris…) are customary, not required.
- Data caveat: the fork's set files (`src/js/data/sets/*.js`) are Smogon analyses (gen1–9) and Radical Red trainer data. We must not ship either: we have our own trainer data. The smogon `calc/src/data/*` tables are derived from Pokémon Showdown (also MIT). We would not ship those either (we inject our own data), so there is no data-licence issue.
- The site is already a non-commercial fan guide that credits hg-engine; MIT adds nothing incompatible.

## 2. Architecture of `@smogon/calc`

### Data layer (`calc/src/data/interface.ts`)

`calculate(gen, attacker, defender, move, field?)` (`calc.ts`) dispatches only on `gen.num`:

```ts
const MECHANICS = [calculateChampions, calculateRBYGSC, calculateRBYGSC, calculateADV,
  calculateDPP, calculateBWXY, calculateBWXY, calculateSMSSSV, calculateSMSSSV, calculateSMSSSV];
return MECHANICS[gen.num](gen, attacker.clone(), defender.clone(), move.clone(), field ?? new Field());
```

A `Generation` is a plain interface: `{num, abilities, items, moves, species, types, natures}`. Each table is `{get(id: ID): T | undefined; [Symbol.iterator]()}`, with `ID` = lowercase alphanumeric `toID(name)`. The record shapes are small:

- `Specie`: `name, types[1|2], baseStats{hp,atk,def,spa,spd,spe}, weightkg, gender?, nfe?, abilities?{0}, otherFormes?, baseSpecies?`
- `Move`: `name, basePower, type, category, flags{contact,punch,bite,sound,bullet,pulse,slicing,wind}, priority, recoil?, drain?, multihit?, willCrit?, secondaries?, self?{boosts}, target?, ignoreDefensive?, override*Stat?, breaksProtect?` …
- `Item`: `name, isBerry?, naturalGift?{basePower,type}, megaStone?`
- `Ability`: just `name`
- `Type`: `name, effectiveness{[TypeName]: 0|0.5|1|2}`. The type chart comes from data, so Fairy and any chart change can be injected.
- `Nature`: `name, plus?, minus?`

**Custom data can be injected without forking.** The `@smogon/calc/adaptable` entry exports `calculate, Pokemon, Move, Field, Side, Result, Stats` and imports **no** bundled data (checked: only `index.ts` imports `./data`). We implement `Generation` from our own JSON and pass it in. `Pokemon`/`Move` constructors call `gen.species.get(toID(name))` / `gen.moves.get(toID(name))`, and accept `overrides` for one-off changes (for example a retyped form).

Limits of injection:

- Mechanics are chosen by `gen.num` (0–9). We pick 4 (DPP) or 5–9 (modern). There is no way to plug in our own mechanics function without patching `calc.ts`.
- `TypeName` is a closed union; custom types are impossible without patching. The hack only adds Fairy, which is already in the union, so this is fine.
- Ability/item *behaviour* is not data. It is code that tests `hasAbility('Name')` / `hasItem('Name')`. Unknown names do nothing; they never error.

### Mechanics files and hard-coded names

| File | Size | Lines with `hasAbility/hasItem/named/=== '…'` |
|---|---|---|
| `mechanics/gen4.ts` (DPP) | 24.6 KB | 77 (≈35 abilities, 17 items, 18 named moves) |
| `mechanics/gen56.ts` (BW/XY) | 37.6 KB | 150 |
| `mechanics/gen789.ts` (SM/SS/SV) | 63.6 KB | 295 |
| `mechanics/util.ts` (shared) | 23.6 KB | 89 |
| `desc.ts` (text, KO chance, end-of-turn) | 39.6 KB | many `gen.num` branches |
| `champions.ts` | 37.8 KB | 142 (not needed) |

All behaviour is keyed on **English official names**. Ours must match Showdown's spelling exactly ("Choice Band", "Deep Sea Tooth", "Never-Melt Ice"…), or the effect silently fails. That needs a name map and a test for it.

What gen4.ts gets wrong for this hack *by construction* (it is vanilla Gen 4):

- The type-precedence list (used to order the two type multipliers, which matters for Gen 4 floor rounding) has no `Fairy` (`indexOf` → -1). Harmless for the product, but the rounding order differs.
- It knows no Gen 5+ abilities (Pixilate, Sheer Force, Analytic, Sand Force, Tough Claws, Strong Jaw…) and no Gen 5+ items (Assault Vest, Eviolite, Pixie Plate is in `items.ts` but no Fairy gems/Roseli Berry handling path in gen4). The hack's abilities.json lists **22 added, 20 changed, 17 custom** abilities (author notes), and items.json has 170 items with author notes. None of these exist in gen4.ts.
- Gen 4 crit is ×2 and floors in a fixed order. gen56/gen789 use ×1.5 and 4096-based `chainMods`/`pokeRound`.

**Key open research question before choosing a file:** the hack's v4 engine is built on **hg-engine** (`work/notes/credits_and_sources.md`). hg-engine re-implements damage in C on top of the Gen 4 battle engine, adding Gen 5–9 abilities, items, Fairy and so on. Which formula it follows (Gen 4 floor sequence vs Gen 5+ 4096 modifiers, crit ×2 vs ×1.5, where Fairy sits) is **not yet established** for this ROM. Decide it from the ROM/hg-engine source plus emulator damage rolls (the existing emulator harness), not by assumption. (By default hg-engine is, as far as I know, a "modern mechanics on Gen 4" project, so gen789-style is the likely starting point, but treat that as unverified.)

### Bundle size (estimated from source; nothing was compiled)

- Module format: `tsconfig` targets **ES3 + CommonJS** (`"module": "commonjs", "target": "es3"`); the npm `dist/` is CJS with down-levelled generators/spread polyfills. There is no ESM build and no `sideEffects` field. Vite can consume it (esbuild prebundles CJS), but **it does not tree-shake**: `calc.ts` statically imports all six mechanics files, so every gen ships.
- Core without data (`adaptable` path: calc, desc, field, items, move, pokemon, result, state, stats, util, all mechanics incl. champions) ≈ 300 KB of TS. Estimate ≈ 130–160 KB minified ES3, ≈ 35–40 KB gzip.
- Smogon's own data layer (`calc/src/data`, all gens, species 288 KB + moves 144 KB TS) is not needed with injected data. It is unpacked per gen at load time and is several hundred KB minified.
- One gen only: if vendored and patched so `calc.ts` imports just one mechanics file (and drops `champions.ts`), the core is ≈ 140 KB TS (≈ 55–70 KB min, ≈ 15–20 KB gzip), compiled as modern ESM by Vite.
- Our data, projected to calc fields only: 1,440 species × ~80 B + 920 moves × ~70 B + names of 769 items/327 abilities ≈ 200 KB raw, ≈ 35–45 KB gzip. Load it lazily (a separate JSON fetched on first opening the calc), never inlined in the team-builder page like `#tb-data`.

## 3. What the Radical Red fork changed

### Data (edited in place, not injected)

- They **repurposed the Gen 9 slot** as "Radical Red": `species.ts` `SV = extend(SS, SV_PATCH, PLA_PATCH, RR_PATCH)` (RR_PATCH ≈ 670 lines of retypings/restats), `moves.ts` `SV = extend(SS, SV_PATCH, RR_PATCH)` (RR_PATCH ≈ 200 lines), `abilities.ts` `RR = SV.concat([...18 custom abilities: Bone Zone, ORAORAORAORA, Mountaineer, Primal Armor, Quill Rush, …])`.
- `interface.ts`: added move flags `kick`, `bone`; removed Champions (`GenerationNum` 1–9).
- About 3,750 diff lines in species, 830 in moves, 600 in gen789.ts, 420 in desc.ts against current smogon, partly because the fork is ~3 versions behind (no Champions, older Stellar/Tera code).

### Mechanics

All custom behaviour is **hand-patched into `gen789.ts` / `util.ts`** by name. Examples: `Bone Zone` (bone moves ignore immunity, using the new flag), `Mountaineer` (Rock immunity), `ORAORAORAORA` (a Parental-Bond-like second hit that recursively calls `calculateSMSSSV` with a "(Child)" ability), `Flaming Soul` priority, `Sonic Slash` speed-ratio BP, `Corrosion` type-chart override, Frostbite instead of Freeze. **Lesson:** a hack calc is a fork of the mechanics file plus a data patch. Upstream merges then become painful; the fork has not tracked smogon for about a year.

### Trainer sets

- `src/js/data/sets/normal.js` (`SETDEX_SV`, 1,455 sets) and `hardcore.js` (1,560 sets). Keyed **species → set name**, where the set name is the trainer ("Rival Blue Set 1", "Leader Falkner", `*` prefix for hardcore). Each set has `{level, nature, ability, item?, moves[4], ivs, evs?}`. The UI lists them as "Species (Trainer)" in a searchable select2 dropdown. "Normal / Hardcore" mode is a separate HTML page (`normal.template.html`, `hardcore.template.html`) that loads the other setdex.
- The generator for these files is **not** in the repo (the `import/` package is still smogon's usage-stats importer). They are maintained outside the repo and committed as JS.
- `moveset_import.js`: paste a Showdown-format team → saved to `localStorage.customsets` → shown as "imported sets" (the player's own team) next to the trainer sets. "Clear Imported Sets" button.

### UI (mostly unchanged smogon UI: jQuery 1.9 + select2, ~1,600-line HTML templates)

- Header: notation (48ths/%) and mode (One vs One / Normal / Hardcore / Randoms). Gen selector hidden (only gen 9).
- Top: **8 move buttons** (P1's 4 moves, P2's 4 moves), each showing the damage % range. Selecting one shows the **main result line**: "252+ Atk Choice Band Garchomp Earthquake vs. 4 HP / 0 Def Heatran: 320-378 (97.2 - 114.8%) -- 81.3% chance to OHKO", click to copy. Below it the 16 damage rolls.
- Three columns: **Pokémon 1** (set dropdown, types, level, base/IV/EV/stat table, nature, ability with on/off toggle, item, status, current HP, boosts, 4 moves with BP/type/category/crit/hits) | **Field** (singles/doubles, weather, terrain, gravity, per-side Reflect/Light Screen/Stealth Rock/Spikes/Protect/Leech Seed/Helping Hand/Tailwind/Foresight…) | **Pokémon 2** (mirror).
- `honkalculate.template.html`: "mass calc", one Pokémon against every set in the dex, as a sortable table.
- Not in this repo: the "Pokémon box" with sprites and next/previous-trainer navigation seen in some other hack calcs (Run & Bun / Nuzlocke calcs). The RR fork has only the dropdown and the localStorage import.

### Features players actually use it for in a hack (by value)

1. **Opponent's exact trainer set preloaded** (species, level, moves, item, ability, nature) from a searchable list. This is the reason a hack needs its own calc. Smogon sets are useless in a hack.
2. **Damage % ranges + KO-chance text** for all 8 moves at once ("guaranteed 2HKO", "37.5% chance to OHKO", with Leftovers/weather/end-of-turn included in `desc.ts`).
3. **Hack-correct data**: retypings, stat changes, changed moves/abilities. Wrong data makes the tool worse than none.
4. **The player's own Pokémon saved** (import/export Showdown text, remembered locally) so it does not have to be re-entered for every fight.
5. Speed comparison (who moves first, with stat stages, Choice Scarf, paralysis, Tailwind).
6. Field toggles: weather, screens, Stealth Rock, Intimidate/ability on-off, status (burn), stat boosts.
7. Mass calc vs all sets (niche; power users).

## 4. Recommendation

**(b) Vendor + patch** the calc package source into `site/src/lib/calc/`, keeping only the shared core plus **one** mechanics file. Drive it with our own injected `Generation` built from `site/src/data/*.json`, via the `adaptable` design.

Reasons:

- **Correctness for a hack whose engine we are still researching.** We will have to edit the mechanics: Fairy in Gen 4 precedence (or a modern file), 17 custom + 20 changed + 22 added abilities, changed items, hack-specific move changes. With (a), every such change is impossible or needs monkey-patching a CJS dist; `calculate` dispatch is fixed by `gen.num`. With (b), they are normal code edits we can test against emulator damage rolls. That is exactly what RR ended up doing, just without the gen-slot hijack.
- **Bundle size.** (a) ships all six mechanics files plus ES3 polyfills (~35–40 KB gzip core) and cannot tree-shake. (b) with one mechanics file, compiled as ESM by Vite, is ~15–20 KB gzip, plus our lazily loaded data.
- **Maintainability.** Smogon's Gen 4 formula is stable; upstream churn is in Gen 9/Champions, which we drop anyway. Pin the upstream commit in a header comment, keep our patches small and marked `// OHG:`, and keep a parity test file (`site/tests/calc.test.mjs`, run by the existing `node --test`) with known damage rolls from the emulator harness.
- **Licence.** MIT allows (b) freely. Add `site/src/lib/calc/LICENSE` and the `/*! */` banner.
- **Why not (c), our own engine.** A minimal Gen 4 formula is ~300 lines, but the real value (KO-chance text with end-of-turn effects, multi-hit, crit handling, ~100 ability/item interactions, `desc.ts` descriptions) is ~3,000 lines of tested code. Rewriting it means re-finding every edge case. Only worth it if the hg-engine formula turns out to be neither Gen 4 nor Gen 5+ compatible.
- **Why not (a), npm with injected data.** It works for a proof of concept (a day's work: build `Generation` from our JSON, call `calculate`). It is acceptable as a *first spike*, to validate the data mapping, before vendoring. But any hack-specific ability/item/formula fix would need a fork anyway.

Concrete patch list for (b) (and the subset that already applies to (a)):

| # | Where | What | (a) possible? |
|---|---|---|---|
| 1 | new `site/src/lib/calc/ohg-generation.ts` | Implement `Generation` from our JSON: species (`stats[6]` → `baseStats`, `types`, abilities); moves (`power` is a **string** → number, `cat` → `category`, `flags` array → `MoveFlags`, `effects.hits` → `multihit`, `effects.drain`, recoil, `priority`); items (berries + Natural Gift); abilities; types (type chart **from the hack's data, incl. Fairy**); natures. Map our names to Showdown spellings where they differ. Unique `toID` for custom forms. | yes |
| 2 | data gap | **Species weight is not in `species.json`**: Low Kick, Grass Knot, Heavy Slam, Heat Crash need it. Extract from the ROM personal data (or US data for unchanged species). | yes |
| 3 | data gap | **Trainer natures/IVs**: `trainers.json` has `nature: null` for 2,731 of 3,891 trainer Pokémon and a single `ivs` difficulty value plus `hpIvs`. In Gen 4 the nature comes from a PID generated from the trainer and Pokémon data; we must compute it (or confirm how hg-engine sets it) or the calc will be wrong by ±10%. Field `evs` is mostly null. | yes |
| 4 | `calc.ts` | Import only the chosen mechanics file; drop `champions.ts`, gen12, gen3 and the unused modern files. | no |
| 5 | chosen mechanics file | Decide the formula from the hg-engine/ROM research (gen4.ts vs gen789.ts as base). If gen4.ts: add Fairy to the precedence list, Fairy items (Pixie Plate is in `items.ts`), every hack-added Gen 5+ ability/item the ROM implements. If gen789.ts: strip Tera/Dynamax/Z/Terrain/Mega bits that cannot occur, and restore any Gen 4 behaviours hg-engine keeps. | no |
| 6 | mechanics + `util.ts` | Implement the **17 custom and 20 changed abilities** and changed items from `abilities.json`/`items.json` author notes, only where the ROM behaviour is verified. Unverified ones show a "not modelled" warning in the result line instead of a silent wrong number. | no |
| 7 | `desc.ts` | `getEndOfTurn`/`getKOChance` gen-specific divisors (Leftovers, weather chip, burn ⅛ vs 1⁄16, Black Sludge, …) must follow the hack. They branch on `gen.num`. | no |
| 8 | `stats.ts` | Fine for Gen 3+ formula; check hack features (EV Allocator, IV changes) do not alter it. | — |
| 9 | build | Compile as ESM via Vite (drop ES3 polyfills; the `exports.calculate` "kludge" in `index.ts` is not needed: use the `adaptable` exports only). | — |

## 5. UX notes and integration ideas

### How RR/Smogon lay it out

Dense single screen: 8 move-result buttons on top → one sentence result + rolls → three columns (attacker | field | defender), each a full stat/EV/IV editor. Powerful for experts, overwhelming for a casual player, and not usable at phone width.

### Integration into the existing Team Builder (progressive disclosure)

The Team Builder state today is **species ids only** (`#team=1,4,7`, `localStorage 'ohg-team-builder-v1'`). There is no level, moves, item or nature. A calc needs per-member sets, so:

- **Level 0 (unchanged default):** team planning exactly as now. The calc is hidden behind a quiet entry: a "Battle check" tab next to "Field guide" in `.tb-workspace` (and in `.tb-mobile-nav`), or a "Check a fight" button on a filled slot.
- **Level 1, "Will I win this fight?":** pick an opponent from a searchable list of **trainers in play order** (we have `trainers.json` + `trainer_guide.json`; e.g. "Falkner (Violet Gym)"). Show their team as cards. For each pair (your selected slot vs their Pokémon), show only two lines: "Your best move: Thunderbolt 62–74% → 2HKO" and "Their best move: Rock Slide 30–36% → 3HKO", plus a speed badge ("you move first"). Defaults: your Pokémon at the trainer's ace level (or a level stepper), neutral nature, 0 EVs, 31 IVs (or the guide's default), moves = level-up moves known at that level (we have `levelup` in species.json). No EV/IV table visible.
- **Level 2, "Details" disclosure per side:** level, nature, ability, item, moves (4 selects), current HP, status, stat stages. Still no EV grid.
- **Level 3, "Advanced":** EVs/IVs table, field panel (weather, screens, Stealth Rock, Gravity, doubles), crit toggle, 16-roll list, copy-able Showdown-style result sentence.
- **Team-wide matrix (nice extra):** for a chosen trainer, a 6 × N grid of "best % / KO class" with colour scale, so a player sees at a glance which teammate handles which opponent. This is the planner-friendly version of honkalculate.
- **Persistence:** extend the team state from `number[]` to `{id, level?, nature?, ability?, item?, moves?, evs?, ivs?}[]` under a new key (`ohg-team-builder-v2`, migrate v1). Keep the share link compact (only non-default fields). Offer Showdown text import/export: it is the de facto format players already use with RR-style calcs.
- **Honesty markers:** where the hack changed an ability/move/item and the calc does not model it (or it is unverified), show a small "⚠ not modelled: Bone Zone" chip in the result line. Never show a wrong number silently. Link to the move/ability page.
- **Mobile:** stack attacker → result → defender. The result sentence is sticky at the top. Field controls go in a bottom sheet.
- **Performance:** load the calc module and calc JSON lazily (dynamic `import()` when the Battle check tab first opens), so the planner page's weight is unchanged for casual users.
- **Player-facing language** (memory rule): trainer names and places, not map ids or flags; Level 0 copy without jargon ("2HKO" gets a tooltip "knocks out in 2 hits").
