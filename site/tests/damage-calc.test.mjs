import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadCalc, buildCalcData, fromTrainerMon, mirrorField, defaultLevelUpMoves } from '../src/lib/calc/index.ts';

const read = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = read('species'), moves = read('moves'), abilities = read('abilities'), items = read('items'), trainers = read('trainers');
// Same table as src/lib/verified-mechanics.ts (a .ts file with types Node cannot strip on import from here).
const formChanges = [
  { base: 6, result: 1027, item: 325, condition: 'Any nature except Timid or Modest.' },
  { base: 6, result: 1028, item: 325, condition: 'Timid or Modest nature.' },
  { base: 150, result: 1440, item: 114, condition: 'No nature requirement.' },
  { base: 493, result: 1162, item: 298, condition: 'Its Multitype Ability changes its type to match the Plate.' },
];
const data = buildCalcData({ species, moves, abilities, items, trainers, formChanges });
const calc = loadCalc(JSON.parse(JSON.stringify(data)));

const verifiedSource = readFileSync(new URL('../src/lib/verified-mechanics.ts', import.meta.url), 'utf8');
test('test form table matches verified-mechanics.ts', () => {
  assert.match(verifiedSource, /base: 6, result: 1027, item: 325, condition: 'Any nature except Timid or Modest\.'/);
  assert.match(verifiedSource, /base: 6, result: 1028, item: 325, condition: 'Timid or Modest nature\.'/);
  assert.match(verifiedSource, /base: 150, result: 1440, item: 114/);
});

// ---------------------------------------------------------------- helpers
const ALL = v => ({ hp: v, atk: v, def: v, spa: v, spd: v, spe: v });
const MOVE = Object.fromEntries(moves.map(m => [m.name, m.id]));
const ABILITY = Object.fromEntries(abilities.map(a => [a.name, a.id]));
const ITEM = Object.fromEntries(items.map(i => [i.name, i.id]));
const NO_GUARD = ABILITY['No Guard'], IMMUNITY = ABILITY['Immunity'];
const MACHAMP = 68, SNORLAX = 143;
const set = (speciesId, extra = {}) => ({ speciesId, level: 50, nature: 'Serious', abilityId: NO_GUARD, itemId: null,
  moveIds: [], ivs: ALL(31), evs: ALL(0), ...extra });
const machamp = (extra = {}) => set(MACHAMP, extra);
const snorlax = (extra = {}) => set(SNORLAX, { abilityId: IMMUNITY, ...extra });
const hit = (attacker, defender, moveName, field = {}) => {
  const out = calc.calculateMatchup({ ...attacker, moveIds: [MOVE[moveName]] }, defender, field);
  return { ...out.moves[0], out };
};

const pokeRound = n => (n % 1 > 0.5 ? Math.ceil(n) : Math.floor(n));
const chain = mods => mods.reduce((M, m) => (m === 4096 ? M : (M * m + 2048) >> 12), 4096);
const mod = (value, mods) => pokeRound((value * chain(mods)) / 4096);
/** Independent re-implementation of the hack's formula (work/notes/damage_calc_mechanics.md §1). */
function ref({ L = 50, bp, A, D, spread = false, weather = 4096, glaive = false, crit = false, stab = 4096, eff = [1], burn = false, final = [] }) {
  let base = Math.floor(Math.floor(Math.floor((2 * L) / 5 + 2) * bp * A / D) / 50) + 2;
  if (spread) base = pokeRound((base * 3072) / 4096);
  if (weather !== 4096) base = pokeRound((base * weather) / 4096);
  if (glaive) base = Math.floor((base * 200) / 100);
  if (crit) base = Math.floor((base * 150) / 100);
  const fm = Math.max(41, Math.min(131072, chain(final)));
  return Array.from({ length: 16 }, (_, i) => {
    let r = Math.floor((base * (85 + i)) / 100);
    if (stab !== 4096) r = (r * stab) / 4096;
    r = pokeRound(r);
    // The game applies the combined effectiveness in one shift (0x022261B8; damage_calc_parity.md "types2").
    r = Math.floor(r * eff.reduce((x, f) => x * f, 1));
    if (burn) r = Math.floor(r / 2);
    return pokeRound(Math.max(1, (r * fm) / 4096));
  });
}
// L50, IV 31, EV 0, neutral nature: Machamp Atk 150 / Def 105 / SpA 85; Snorlax HP 235 / Def 85 / SpD 130.
const M_ATK = 150, M_SPA = 85, S_DEF = 85, S_SPD = 130;

// ---------------------------------------------------------------- (a) formula, hand-computed
test('stats follow the standard formula', () => {
  assert.deepEqual(calc.stats(machamp()).stats, { hp: 165, atk: 150, def: 105, spa: 85, spd: 110, spe: 75 });
  assert.deepEqual(calc.stats(snorlax()).stats, { hp: 235, atk: 130, def: 85, spa: 85, spd: 130, spe: 50 });
  // Adamant: Atk ×1.1 floor, SpA ×0.9 floor
  const adamant = calc.stats(machamp({ nature: 'Adamant' })).stats;
  assert.equal(adamant.atk, 165);
  assert.equal(adamant.spa, 76);
});

test('neutral hit: Machamp Strength vs Snorlax (hand-computed rolls)', () => {
  // base = floor(floor(22·80·150/85)/50)+2 = floor(3105/50)+2 = 64; rolls floor(64·(85..100)/100)
  const r = hit(machamp(), snorlax(), 'Strength');
  assert.deepEqual(r.rolls, [54, 55, 55, 56, 56, 57, 58, 58, 59, 60, 60, 61, 62, 62, 63, 64]);
  assert.equal(r.minDamage, 54);
  assert.equal(r.maxDamage, 64);
  assert.equal(r.minPercent, 22.9);
  assert.equal(r.maxPercent, 27.2);
  assert.equal(r.koChanceText, '52.9% chance to 4HKO'); // 4 × 54 < 235 HP ≤ 4 × 64
  assert.ok(r.modelled);
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
});

test('STAB ×1.5 rounds half down and super effective ×2 (Brick Break)', () => {
  // base 60; roll 85: floor(60·0.85) = 51 → 51·1.5 = 76.5 → 76 (pokeRound) → ×2 = 152
  const r = hit(machamp(), snorlax(), 'Brick Break');
  assert.equal(r.rolls[0], 152);
  assert.equal(r.rolls[15], 180);
  assert.deepEqual(r.rolls, ref({ bp: 75, A: M_ATK, D: S_DEF, stab: 6144, eff: [2] }));
});

test('critical hit ×1.5 (floor) and ignores screens', () => {
  const r = hit(machamp(), snorlax(), 'Strength', { crit: true, defenderSide: { reflect: true } });
  assert.equal(r.maxDamage, 96); // floor(64 · 1.5)
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF, crit: true }));
  assert.equal(r.critChance, 1);
});

test('burn halves physical damage', () => {
  const r = hit(machamp({ status: 'brn' }), snorlax(), 'Strength');
  assert.equal(r.maxDamage, 32);
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF, burn: true }));
  // Guts ignores the burn and raises Atk ×1.5
  const guts = hit(machamp({ status: 'brn', abilityId: ABILITY['Guts'] }), snorlax(), 'Strength');
  assert.deepEqual(guts.rolls, ref({ bp: 80, A: mod(M_ATK, [6144]), D: S_DEF }));
});

test('spread moves ×0.75 in doubles only', () => {
  // Earthquake: base 79 in singles; doubles pokeRound(79·0.75 = 59.25) = 59
  assert.equal(hit(machamp(), snorlax(), 'Earthquake').maxDamage, 79);
  const doubles = hit(machamp(), snorlax(), 'Earthquake', { gameType: 'Doubles' });
  assert.equal(doubles.maxDamage, 59);
  assert.deepEqual(doubles.rolls, ref({ bp: 100, A: M_ATK, D: S_DEF, spread: true }));
  // Single-target move in doubles is not reduced
  assert.equal(hit(machamp(), snorlax(), 'Strength', { gameType: 'Doubles' }).maxDamage, 64);
});

test('screens: ×0.5 in singles, ×2732/4096 in doubles', () => {
  assert.equal(hit(machamp(), snorlax(), 'Strength', { defenderSide: { reflect: true } }).maxDamage, 32);
  // 64 · 2732 / 4096 = 42.69 → 43
  assert.equal(hit(machamp(), snorlax(), 'Strength', { gameType: 'Doubles', defenderSide: { reflect: true } }).maxDamage, 43);
  // Light Screen does not affect physical moves; it does affect special ones
  assert.equal(hit(machamp(), snorlax(), 'Strength', { defenderSide: { lightScreen: true } }).maxDamage, 64);
  const hv = hit(machamp(), snorlax(), 'Hyper Voice', { defenderSide: { lightScreen: true } });
  assert.deepEqual(hv.rolls, ref({ bp: 90, A: M_SPA, D: S_SPD, final: [2048] }));
});

test('weather ×1.5 / ×0.5 at the weather step', () => {
  const sun = hit(machamp(), snorlax(), 'Fire Punch', { weather: 'Sun' });
  assert.deepEqual(sun.rolls, ref({ bp: 75, A: M_ATK, D: S_DEF, weather: 6144 }));
  const rain = hit(machamp(), snorlax(), 'Fire Punch', { weather: 'Rain' });
  assert.deepEqual(rain.rolls, ref({ bp: 75, A: M_ATK, D: S_DEF, weather: 2048 }));
});

test('mirrorField swaps the sides', () => {
  assert.deepEqual(mirrorField({ weather: 'Sun', attackerSide: { reflect: true } }),
    { weather: 'Sun', attackerSide: undefined, defenderSide: { reflect: true } });
});

// ---------------------------------------------------------------- (b) deviations
test('dev 1: move flags come from flagBits (punch, sound, bite, slicing)', () => {
  const g = calc.generation;
  assert.equal(g.moves.get(MOVE['Mega Punch']).flags.punch, 1);
  assert.equal(g.moves.get(MOVE['Hyper Voice']).flags.sound, 1);
  assert.equal(g.moves.get(MOVE['Crunch']).flags.bite, 1);
  assert.equal(g.moves.get(MOVE['Metal Claw']).flags.slicing, 1, 'hack sets slicing on Metal Claw');
  assert.equal(g.moves.get(MOVE['Strength']).flags.contact, 1);
  assert.equal(g.moves.get(MOVE['Earthquake']).target, 'allAdjacent');
  assert.equal(g.moves.get(MOVE['Rock Slide']).target, 'allAdjacentFoes');
  assert.equal(g.moves.get(MOVE['Crunch']).secondaries, true);
  assert.equal(g.moves.get(MOVE['Close Combat']).secondaries, false);
  assert.equal(g.moves.get(MOVE['Draco Meteor']).dropsStats, 2);
  assert.deepEqual(g.moves.get(MOVE['Bullet Seed']).multihit, [2, 5]);
  assert.equal(g.moves.get(MOVE['Bone Rush']).multihit, 3, 'hack data: Bone Rush hits 3 times');
  assert.equal(g.moves.get(MOVE['Bone Rush']).type, 'Rock', 'hack data: Bone Rush is Rock');
  // Sharpness reads the slicing bit: Metal Claw ×1.5
  const sharp = hit(machamp({ abilityId: ABILITY['Sharpness'] }), snorlax(), 'Metal Claw');
  assert.deepEqual(sharp.rolls, ref({ bp: 90, A: M_ATK, D: S_DEF }));
});

test('dev 2: Glaive Rush vulnerability ×2 after weather, before crit (emulator-verified, no caveat)', () => {
  const r = hit(machamp(), snorlax(), 'Strength', { defenderSide: { glaiveRush: true }, crit: true });
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF, glaive: true, crit: true }));
  assert.ok(!r.caveats.some(c => c.includes('Glaive Rush')));
});

test('dev 3: crit rates 1/24, 1/8, 1/2, always', () => {
  assert.equal(hit(machamp(), snorlax(), 'Strength').critChance, 1 / 24);
  assert.equal(hit(machamp({ itemId: ITEM['Scope Lens'] }), snorlax(), 'Strength').critChance, 1 / 8);
  assert.equal(hit(machamp({ itemId: ITEM['Scope Lens'] }), snorlax(), 'Slash').critChance, 1 / 2);
  assert.equal(hit(machamp({ itemId: ITEM['Scope Lens'], abilityId: ABILITY['Super Luck'] }), snorlax(), 'Slash').critChance, 1);
  assert.equal(hit(set(83, { itemId: ITEM['Leek'] }), snorlax(), 'Strength').critChance, 1 / 2);
  assert.equal(hit(set(113, { itemId: ITEM['Lucky Punch'] }), snorlax(), 'Strength').critChance, 1 / 2);
  const storm = hit(machamp(), snorlax(), 'Storm Throw');
  assert.equal(storm.critChance, 1);
  assert.deepEqual(storm.rolls, ref({ bp: 60, A: M_ATK, D: S_DEF, crit: true, stab: 6144, eff: [2] }));
});

test('dev 4: Overgrow/Blaze/Torrent/Swarm at HP ≤ ½', () => {
  const low = hit(machamp({ abilityId: ABILITY['Overgrow'], curHPPercent: 49 }), snorlax(), 'Vine Whip');
  assert.deepEqual(low.rolls, ref({ bp: 45, A: mod(M_ATK, [6144]), D: S_DEF }));
  const mid = hit(machamp({ abilityId: ABILITY['Overgrow'], curHPPercent: 45 }), snorlax(), 'Vine Whip');
  assert.deepEqual(mid.rolls, low.rolls, 'between ⅓ and ½ still active (official games need ⅓)');
  const high = hit(machamp({ abilityId: ABILITY['Overgrow'], curHPPercent: 60 }), snorlax(), 'Vine Whip');
  assert.deepEqual(high.rolls, ref({ bp: 45, A: M_ATK, D: S_DEF }));
});

test('dev 5: Swarm takes ×0.75 from super-effective hits', () => {
  const r = hit(machamp(), snorlax({ abilityId: ABILITY['Swarm'] }), 'Brick Break');
  assert.deepEqual(r.rolls, ref({ bp: 75, A: M_ATK, D: S_DEF, stab: 6144, eff: [2], final: [3072] }));
  assert.deepEqual(hit(machamp(), snorlax({ abilityId: ABILITY['Swarm'] }), 'Strength').rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
});

test('dev 6: Limber and Shell Armor give Def ×1.25 against physical moves', () => {
  for (const name of ['Limber', 'Shell Armor']) {
    const r = hit(machamp(), snorlax({ abilityId: ABILITY[name] }), 'Strength');
    assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: mod(S_DEF, [5120]) }), name);
    const special = hit(machamp(), snorlax({ abilityId: ABILITY[name] }), 'Hyper Voice');
    assert.deepEqual(special.rolls, ref({ bp: 90, A: M_SPA, D: S_SPD }), `${name} special unchanged`);
  }
  // Shell Armor still blocks crits
  assert.equal(hit(machamp(), snorlax({ abilityId: ABILITY['Shell Armor'] }), 'Strength', { crit: true }).critChance, 0);
});

test('dev 7: Marvel Scale raises Def and SpD while statused', () => {
  const sp = hit(machamp(), snorlax({ abilityId: ABILITY['Marvel Scale'], status: 'par' }), 'Hyper Voice');
  assert.deepEqual(sp.rolls, ref({ bp: 90, A: M_SPA, D: mod(S_SPD, [6144]) }));
  const ph = hit(machamp(), snorlax({ abilityId: ABILITY['Marvel Scale'], status: 'par' }), 'Strength');
  assert.deepEqual(ph.rolls, ref({ bp: 80, A: M_ATK, D: mod(S_DEF, [6144]) }));
});

test('dev 8: Damp weakens every Fire move ×0.8 and powers the holder\'s Water moves ×1.2', () => {
  const vsDamp = hit(machamp(), snorlax({ abilityId: ABILITY['Damp'] }), 'Fire Punch');
  assert.deepEqual(vsDamp.rolls, ref({ bp: mod(75, [3277]), A: M_ATK, D: S_DEF }));
  const ownFire = hit(machamp({ abilityId: ABILITY['Damp'] }), snorlax(), 'Fire Punch');
  assert.deepEqual(ownFire.rolls, vsDamp.rolls);
  const water = hit(machamp({ abilityId: ABILITY['Damp'] }), snorlax(), 'Water Gun');
  assert.deepEqual(water.rolls, ref({ bp: mod(40, [4915]), A: M_SPA, D: S_SPD }));
});

test('dev 9: Iron Fist is ×1.3', () => {
  const r = hit(machamp({ abilityId: ABILITY['Iron Fist'] }), snorlax(), 'Mega Punch');
  assert.deepEqual(r.rolls, ref({ bp: mod(80, [5325]), A: M_ATK, D: S_DEF }));
});

test('dev 10: Tough Claws ×1.3 on every move, contact or not', () => {
  const r = hit(machamp({ abilityId: ABILITY['Tough Claws'] }), snorlax(), 'Hyper Voice');
  assert.deepEqual(r.rolls, ref({ bp: mod(90, [5325]), A: M_SPA, D: S_SPD }));
});

test('dev 11: Quick Feet ×1.5 physical Atk while statused and ignores burn', () => {
  const r = hit(machamp({ abilityId: ABILITY['Quick Feet'], status: 'brn' }), snorlax(), 'Strength');
  assert.deepEqual(r.rolls, ref({ bp: 80, A: mod(M_ATK, [6144]), D: S_DEF }));
});

test('dev 12: Sniper +1 crit stage and ×1.5 on crits', () => {
  assert.equal(hit(machamp({ abilityId: ABILITY['Sniper'] }), snorlax(), 'Strength').critChance, 1 / 8);
  const r = hit(machamp({ abilityId: ABILITY['Sniper'] }), snorlax(), 'Strength', { crit: true });
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF, crit: true, final: [6144] }));
});

test('dev 13: Leaf Guard in sun: SpA ×1.5, Def ×1.5 against physical', () => {
  const atk = hit(machamp({ abilityId: ABILITY['Leaf Guard'] }), snorlax(), 'Hyper Voice', { weather: 'Sun' });
  assert.deepEqual(atk.rolls, ref({ bp: 90, A: mod(M_SPA, [6144]), D: S_SPD }));
  const def = hit(machamp(), snorlax({ abilityId: ABILITY['Leaf Guard'] }), 'Strength', { weather: 'Sun' });
  assert.deepEqual(def.rolls, ref({ bp: 80, A: M_ATK, D: mod(S_DEF, [6144]) }));
  assert.deepEqual(hit(machamp(), snorlax({ abilityId: ABILITY['Leaf Guard'] }), 'Strength').rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
});

test('dev 14: Cursed Body ×1.3 on Ghost moves', () => {
  // Snorlax attacking Machamp with Shadow Sneak; Snorlax Atk 130, Machamp Def 105
  const r = hit(snorlax({ abilityId: ABILITY['Cursed Body'] }), machamp(), 'Shadow Sneak');
  assert.deepEqual(r.rolls, ref({ bp: 40, A: mod(130, [5325]), D: 105 }));
});

test('dev 15: Telepathy ×1.3 on Psychic moves in Psychic Terrain (flagged)', () => {
  const r = hit(machamp({ abilityId: ABILITY['Telepathy'] }), snorlax(), 'Psychic', { terrain: 'Psychic' });
  assert.deepEqual(r.rolls, ref({ bp: mod(90, [5325, 5325]), A: M_SPA, D: S_SPD }));
  assert.ok(r.caveats.some(c => c.startsWith('Telepathy')));
});

test('dev 16: Wonder Skin SpD ×1.5 against special moves', () => {
  const r = hit(machamp(), snorlax({ abilityId: ABILITY['Wonder Skin'] }), 'Hyper Voice');
  assert.deepEqual(r.rolls, ref({ bp: 90, A: M_SPA, D: mod(S_SPD, [6144]) }));
});

test('dev 17: Battle Armor blocks crits', () => {
  const r = hit(machamp(), snorlax({ abilityId: ABILITY['Battle Armor'] }), 'Strength', { crit: true });
  assert.equal(r.critChance, 0);
  assert.deepEqual(r.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
});

test('dev 18: Mega Launcher boosts only its hard-coded list', () => {
  const ml = extra => machamp({ abilityId: ABILITY['Mega Launcher'], ...extra });
  assert.deepEqual(hit(ml(), snorlax(), 'Water Pulse').rolls, ref({ bp: 90, A: M_SPA, D: S_SPD }));
  assert.deepEqual(hit(ml(), snorlax(), 'Dragon Pulse').rolls, ref({ bp: mod(85, [6144]), A: M_SPA, D: S_SPD }));
  assert.deepEqual(hit(ml(), snorlax(), 'Hydro Pump').rolls, ref({ bp: 110, A: M_SPA, D: S_SPD }));
  assert.deepEqual(hit(ml(), snorlax(), 'Terrain Pulse').rolls, ref({ bp: 50, A: M_SPA, D: S_SPD }));
});

test('dev 19: custom abilities', () => {
  // -ate customs: Normal → type, ×1.2 power
  for (const [name, type] of [['Burning Skin', 'Fire'], ['Azure Skin', 'Water'], ['Grass Skin', 'Grass'], ['Dark Skin', 'Dark'], ['Dragonize', 'Dragon']]) {
    const r = hit(machamp({ abilityId: ABILITY[name] }), snorlax(), 'Strength');
    assert.equal(r.type, type, name);
    assert.deepEqual(r.rolls, ref({ bp: mod(80, [4915]), A: M_ATK, D: S_DEF }), name);
  }
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Mega Claws'] }), snorlax(), 'Strength').rolls,
    ref({ bp: 80, A: mod(M_ATK, [5325]), D: S_DEF }));
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Flame Mane'] }), snorlax(), 'Fire Punch').rolls,
    ref({ bp: 75, A: mod(M_ATK, [6144]), D: S_DEF }));
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Desert Hawk'] }), snorlax(), 'Strength', { weather: 'Sand' }).rolls,
    ref({ bp: 80, A: mod(M_ATK, [5325]), D: S_DEF }));
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Desert Hawk'] }), snorlax(), 'Strength').rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
  // Mega Sol: the holder's moves use sun with no weather on the field
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Mega Sol'] }), snorlax(), 'Fire Punch').rolls,
    ref({ bp: 75, A: M_ATK, D: S_DEF, weather: 6144 }));
  // #327 protects a statused ALLY in doubles, never its holder (emulator-verified; caveat for the ally effect)
  const g327 = hit(machamp(), snorlax({ abilityId: 327, status: 'par' }), 'Strength');
  assert.deepEqual(g327.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
  assert.ok(g327.caveats.some(c => c.startsWith('This unnamed Ability')));
  assert.deepEqual(hit(machamp(), snorlax({ abilityId: 327 }), 'Strength').rolls, ref({ bp: 80, A: M_ATK, D: S_DEF }));
  // Aurora Shine: Aurora Veil on entry
  const veil = hit(machamp(), snorlax({ abilityId: ABILITY['Aurora Shine'] }), 'Strength');
  assert.deepEqual(veil.rolls, ref({ bp: 80, A: M_ATK, D: S_DEF, final: [2048] }));
  assert.ok(veil.caveats.some(c => c.startsWith('Aurora Shine')));
  assert.deepEqual(hit(machamp(), snorlax({ abilityId: ABILITY['Aurora Shine'] }), 'Strength', { abilityField: false }).rolls,
    ref({ bp: 80, A: M_ATK, D: S_DEF }));
  // Wildfire: sun on entry
  const wild = hit(machamp({ abilityId: ABILITY['Wildfire'] }), snorlax(), 'Fire Punch');
  assert.equal(wild.out.field.weather, 'Sun');
  assert.deepEqual(wild.rolls, ref({ bp: 75, A: M_ATK, D: S_DEF, weather: 6144 }));
  // Thunder Roar: Electric Terrain on entry (×1.3 for grounded Electric moves)
  const roar = hit(machamp({ abilityId: ABILITY['Thunder Roar'] }), snorlax(), 'Thunder Punch');
  assert.equal(roar.out.field.terrain, 'Electric');
  assert.deepEqual(roar.rolls, ref({ bp: mod(75, [5325]), A: M_ATK, D: S_DEF }));
});

test('dev 20: Soul Dew (hack bug, emulator-verified): holder SpA ×1.5 and its target\'s SpD ×1.5; no SpD for the holder', () => {
  const latios = extra => set(381, { abilityId: ABILITY['Levitate'], ...extra });
  const base = calc.stats(latios()).stats;
  const r = hit(latios({ itemId: ITEM['Soul Dew'] }), snorlax(), 'Dragon Pulse');
  assert.deepEqual(r.rolls, ref({ bp: 85, A: mod(base.spa, [6144]), D: mod(S_SPD, [6144]), stab: 6144 }));
  assert.ok(r.out.notes.some(n => n.startsWith('Soul Dew')));
  const def = hit(machamp(), latios({ itemId: ITEM['Soul Dew'] }), 'Hyper Voice');
  assert.deepEqual(def.rolls, ref({ bp: 90, A: M_SPA, D: base.spd, eff: [1, 1] }));
  // physical moves are untouched
  assert.deepEqual(hit(latios({ itemId: ITEM['Soul Dew'] }), snorlax(), 'Strength').rolls, ref({ bp: 80, A: base.atk, D: S_DEF }));
  // not for other species
  assert.deepEqual(hit(machamp({ itemId: ITEM['Soul Dew'] }), snorlax(), 'Hyper Voice').rolls, ref({ bp: 90, A: M_SPA, D: S_SPD }));
});

test('dev 21: Hail gives Ice types Def ×1.5; sand gives Rock types SpD ×1.5', () => {
  const glaceon = set(471, { abilityId: ABILITY['Ice Body'] });
  const gDef = calc.stats(glaceon).stats.def;
  const hail = hit(machamp(), glaceon, 'Strength', { weather: 'Hail' });
  assert.deepEqual(hail.rolls, ref({ bp: 80, A: M_ATK, D: pokeRound(gDef * 1.5) }));
  assert.ok(!hail.caveats.some(c => c.startsWith('Hail')));
  assert.ok(hail.out.notes.some(n => n.startsWith('Hail here works like Snow')));
  const golem = set(76, { abilityId: ABILITY['Rock Head'] });
  const spd = calc.stats(golem).stats.spd;
  const sand = hit(machamp(), golem, 'Hyper Voice', { weather: 'Sand' });
  assert.deepEqual(sand.rolls, ref({ bp: 90, A: M_SPA, D: pokeRound(spd * 1.5), eff: [0.5, 1] }));
  // Snow Warning sets Hail on entry
  assert.equal(hit(machamp(), set(471, { abilityId: ABILITY['Snow Warning'] }), 'Strength').out.field.weather, 'Hail');
});

test('dev 22: items 110/111/252/324 are inert; 584/600/576/590 are live', () => {
  const ivysaur = item => set(2, { abilityId: ABILITY['Overgrow'], itemId: item });
  const def = calc.stats(ivysaur(null)).stats.def;
  const live = hit(machamp(), ivysaur(584), 'Strength');
  assert.deepEqual(live.rolls, ref({ bp: 80, A: M_ATK, D: mod(def, [6144]) }));
  const inert = hit(machamp(), ivysaur(110), 'Strength');
  assert.deepEqual(inert.rolls, ref({ bp: 80, A: M_ATK, D: def }));
  assert.ok(inert.caveats.some(c => c.startsWith('This ') && c.includes('no battle effect in this game (checked in game)')));
  const helmet = hit(machamp(), snorlax({ itemId: 324 }), 'Strength');
  assert.ok(helmet.caveats.some(c => c.includes('This Rocky Helmet has no battle effect')));
  // Air Balloon: only 576 grants the Ground immunity
  assert.equal(hit(machamp(), snorlax({ itemId: 576 }), 'Earthquake').maxDamage, 0);
  assert.equal(hit(machamp(), snorlax({ itemId: 252 }), 'Earthquake').maxDamage, 79);
  for (const id of [110, 111, 252, 324]) assert.match(calc.generation.items.get(id).name, /no battle effect/);
  for (const id of [584, 600, 576, 590]) assert.doesNotMatch(calc.generation.items.get(id).name, /no battle effect/);
});

test('dev 23: Gems ×1.3, terrain ×1.3, Knock Off ×1.5, Hidden Power 60, Transistor ×1.3, -ate ×1.2', () => {
  // 75 · 5325/4096 = 97.503 → 98; Knock Off 65 · 6144/4096 = 97.5 exactly → 97 (half rounds down)
  assert.deepEqual(hit(machamp({ itemId: ITEM['Fire Gem'] }), snorlax(), 'Fire Punch').rolls, ref({ bp: 98, A: M_ATK, D: S_DEF }));
  assert.deepEqual(hit(machamp(), snorlax(), 'Thunder Punch', { terrain: 'Electric' }).rolls, ref({ bp: 98, A: M_ATK, D: S_DEF }));
  assert.deepEqual(hit(machamp(), snorlax({ itemId: ITEM['Leftovers'] }), 'Knock Off').rolls, ref({ bp: 97, A: M_ATK, D: S_DEF }));
  assert.deepEqual(hit(machamp(), snorlax(), 'Knock Off').rolls, ref({ bp: 65, A: M_ATK, D: S_DEF }));
  const hp = hit(machamp(), snorlax(), 'Hidden Power');
  assert.equal(hp.type, 'Dark'); // all IVs 31
  assert.deepEqual(hp.rolls, ref({ bp: 60, A: M_SPA, D: S_SPD }));
  const hpFire = hit(machamp({ ivs: { hp: 31, atk: 30, def: 31, spa: 30, spd: 31, spe: 30 } }), snorlax(), 'Hidden Power');
  assert.equal(hpFire.type, 'Fire');
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Transistor'] }), snorlax(), 'Thunder Punch').rolls,
    ref({ bp: 75, A: mod(M_ATK, [5325]), D: S_DEF }));
  assert.deepEqual(hit(machamp({ abilityId: ABILITY['Pixilate'] }), snorlax(), 'Strength').rolls,
    ref({ bp: mod(80, [4915]), A: M_ATK, D: S_DEF }));
  // Muscle Band is a ×1.1 final modifier here
  assert.deepEqual(hit(machamp({ itemId: ITEM['Muscle Band'] }), snorlax(), 'Strength').rolls,
    ref({ bp: 80, A: M_ATK, D: S_DEF, final: [4505] }));
});

test('dev 24: trainer IVs (hpIvs for HP), EVs as given, set natures', () => {
  const trainer = trainers.find(t => t.id === 7);
  const mon = trainer.team.find(m => m.name === 'Victreebel');
  const s = calc.fromTrainerMon(mon);
  assert.deepEqual(s.ivs, { hp: 31, atk: 24, def: 24, spa: 24, spd: 24, spe: 24 });
  assert.deepEqual(s.evs, { hp: 252, atk: 0, def: 0, spa: 0, spd: 6, spe: 252 });
  assert.equal(s.nature, 'Modest');
  assert.equal(s.level, 82);
  assert.deepEqual(s.moveIds, [437, 79, 92, 188]);
  assert.deepEqual(s.caveats, []);
  // Victreebel base 80/105/65/100/70/70 (hack data), level 82, Modest
  const base = species.find(x => x.id === 71).stats;
  const st = (b, iv, ev, n = 1) => Math.floor((Math.floor(((2 * b + iv + Math.floor(ev / 4)) * 82) / 100) + 5) * n);
  const expected = {
    hp: Math.floor(((2 * base[0] + 31 + 63) * 82) / 100) + 82 + 10,
    atk: st(base[1], 24, 0, 0.9), def: st(base[2], 24, 0), spa: st(base[3], 24, 0, 1.1),
    spd: st(base[4], 24, 6), spe: st(base[5], 24, 252),
  };
  assert.deepEqual(calc.stats(s).stats, expected);
  // EV totals above 510 are kept
  const big = trainers.flatMap(t => t.team).find(m => m.evs && m.evs.reduce((a, b) => a + b, 0) > 510);
  if (big) assert.equal(Object.values(calc.fromTrainerMon(big).evs).reduce((a, b) => a + b, 0), big.evs.reduce((a, b) => a + b, 0));
  // A missing nature is assumed neutral and flagged
  const unknown = fromTrainerMon({ ...mon, nature: null });
  assert.equal(unknown.nature, null);
  assert.ok(unknown.caveats.includes('Nature generated by the game; assumed neutral.'));
});

test('dev 25: held-item forms (Charizardite by nature, Steel Armor, Plates)', () => {
  const zard = (nature) => set(6, { nature, abilityId: ABILITY['Blaze'], itemId: ITEM['Charizardite'] });
  const x = calc.calculateMatchup({ ...zard('Adamant'), moveIds: [MOVE['Strength']] }, snorlax());
  assert.equal(x.attacker.speciesId, 1027);
  assert.ok(x.notes[0].includes('Mega Charizard X'));
  // Blaze (slot 2) maps to the form's ability: Mega Claws
  assert.equal(x.moves[0].description.includes('Mega Claws'), true);
  assert.equal(calc.calculateMatchup({ ...zard('Timid'), moveIds: [MOVE['Strength']] }, snorlax()).attacker.speciesId, 1028);
  assert.equal(calc.calculateMatchup({ ...zard('Modest'), moveIds: [] }, snorlax()).attacker.speciesId, 1028);
  // Without the stone it stays Charizard
  assert.equal(calc.calculateMatchup(set(6, { moveIds: [] }), snorlax()).attacker.speciesId, 6);
  const mewtwo = calc.calculateMatchup(set(150, { itemId: 114, moveIds: [] }), snorlax());
  assert.equal(mewtwo.attacker.speciesId, 1440);
  assert.deepEqual(calc.generation.species.get(1440).types, ['Psychic', 'Steel']);
  const arceus = calc.calculateMatchup(set(493, { abilityId: ABILITY['Multitype'], itemId: 298, moveIds: [MOVE['Judgment']] }), snorlax());
  assert.equal(arceus.attacker.speciesId, 1162);
  assert.equal(arceus.moves[0].type, 'Fire');
});

test('Return/Frustration use friendship; fixed-damage moves', () => {
  const ret = hit(machamp({ friendship: 255 }), snorlax(), 'Return');
  assert.deepEqual(ret.rolls, ref({ bp: 102, A: M_ATK, D: S_DEF }));
  assert.ok(!ret.caveats.some(c => c.startsWith('Friendship')));
  assert.equal(hit(machamp({ friendship: 255 }), snorlax(), 'Frustration').maxDamage, ref({ bp: 1, A: M_ATK, D: S_DEF })[15]);
  assert.ok(hit(machamp(), snorlax(), 'Return').caveats.some(c => c.startsWith('Friendship')));
  assert.equal(hit(machamp(), snorlax(), 'Seismic Toss').maxDamage, 50);
  assert.equal(hit(machamp(), snorlax(), 'Super Fang').maxDamage, 117);
  // Sonic Boom / Dragon Rage: no fixed damage in this hack, a 1-power special move (emulator-verified)
  const boom = hit(machamp(), snorlax(), 'Sonic Boom');
  assert.deepEqual(boom.rolls, ref({ bp: 1, A: M_SPA, D: S_SPD }));
  assert.ok(!boom.caveats.some(c => c.startsWith('Sonic Boom')));
  assert.ok(boom.out.notes.some(n => n.startsWith('Sonic Boom is not fixed damage')));
  const counter = hit(machamp(), snorlax(), 'Counter');
  assert.equal(counter.modelled, false);
  assert.equal(counter.rolls.length, 0);
});

test('weight moves use the minimum battle weight, as the hack does', () => {
  // Battle weight is never filled in (work/notes/damage_calc_data.md §1): Low Kick/Grass Knot 20, Heavy Slam 40.
  const lk = hit(machamp(), snorlax(), 'Low Kick');
  assert.ok(lk.modelled);
  assert.deepEqual(lk.rolls, ref({ bp: 20, A: M_ATK, D: S_DEF, stab: 6144, eff: [2] }));
  assert.ok(lk.caveats.some(c => c.startsWith('In this game weight-based moves')));
  const gk = hit(machamp(), set(1028, { abilityId: ABILITY['Drought'] }), 'Grass Knot');
  assert.ok(gk.modelled && gk.maxDamage > 0);
  assert.deepEqual(hit(machamp(), snorlax(), 'Heavy Slam').rolls, ref({ bp: 40, A: M_ATK, D: S_DEF }));
  const metal = hit(machamp({ abilityId: ABILITY['Heavy Metal'] }), snorlax(), 'Heavy Slam');
  assert.deepEqual(metal.rolls, ref({ bp: 60, A: M_ATK, D: S_DEF }));
  assert.ok(metal.caveats.some(c => c.startsWith('Heavy Metal')));
  assert.ok(!('weightkg' in calc.generation.species.get(SNORLAX)));
});

// ---------------------------------------------------------------- (c) retyped Pokémon
test('retyped Pokémon use the hack\'s types (Blastoise is Water/Steel)', () => {
  assert.deepEqual(calc.generation.species.get(9).types, ['Water', 'Steel']);
  const blastoise = set(9, { abilityId: ABILITY['Torrent'] });
  const bDef = calc.stats(blastoise).stats.def;
  const fight = hit(machamp(), blastoise, 'Brick Break');
  assert.deepEqual(fight.rolls, ref({ bp: 75, A: M_ATK, D: bDef, stab: 6144, eff: [1, 2] }));
  // Poison cannot touch Steel; Fire is neutral (½ × 2 = one ×1 step, never a floor in between)
  assert.equal(hit(machamp(), blastoise, 'Sludge Bomb').maxDamage, 0);
  const fire = hit(machamp(), blastoise, 'Fire Punch');
  assert.deepEqual(fire.rolls, ref({ bp: 75, A: M_ATK, D: bDef, eff: [0.5, 2] }));
  // Fairy is a real type: Pixie Plate boosts Fairy moves, Dragon is immune to nothing here
  assert.equal(calc.generation.types.get('Dragon').effectiveness.Fairy, 0);
  assert.equal(calc.generation.types.get('Steel').effectiveness.Ghost ?? 1, 1);
});

// ---------------------------------------------------------------- (d) trainer conversion
test('fromTrainerMon converts a real trainers.json entry', () => {
  const green = trainers.find(t => t.id === 1);
  const bulba = green.team[0];
  const s = calc.fromTrainerMon(bulba);
  assert.equal(s.speciesId, 1);
  assert.equal(s.level, 15);
  assert.equal(s.abilityId, 65);
  assert.equal(s.itemId, 239);
  assert.deepEqual(s.moveIds, bulba.moveIds);
  assert.deepEqual(s.ivs, { hp: bulba.hpIvs, atk: bulba.ivs, def: bulba.ivs, spa: bulba.ivs, spd: bulba.ivs, spe: bulba.ivs });
  assert.deepEqual(s.evs, ALL(0));
  if (bulba.nature) assert.equal(s.nature, bulba.nature); else assert.ok(s.caveats.length);
  const out = calc.calculateMatchup(s, calc.fromTrainerMon(green.team[1]), {});
  const vineWhip = out.moves.find(m => m.name === 'Vine Whip');
  assert.ok(vineWhip.maxDamage > 0);
  assert.ok(vineWhip.description.includes('Miracle Seed'));
  // Empty move list → default level-up moves
  const empty = trainers.flatMap(t => t.team).find(m => m.id > 0 && !m.moveIds.length);
  const filled = calc.fromTrainerMon(empty);
  assert.ok(filled.moveIds.length > 0);
  const lu = species.find(x => x.id === empty.id).levelup;
  assert.deepEqual(filled.moveIds, defaultLevelUpMoves(lu, empty.level));
  // the oldest move is forgotten; a move already known is not learnt twice
  assert.deepEqual(defaultLevelUpMoves([[1, 1], [1, 2], [5, 3], [9, 4], [12, 5], [15, 2], [20, 6]], 15), [2, 3, 4, 5]);
});

test('speedOrder applies Choice Scarf, Tailwind, paralysis and Trick Room', () => {
  const a = machamp(), b = snorlax();
  assert.deepEqual(calc.speedOrder(a, b).faster, 'a');
  const scarf = calc.speedOrder(set(SNORLAX, { itemId: ITEM['Choice Scarf'] }), machamp());
  assert.equal(scarf.aSpeed, 75);
  assert.equal(scarf.faster, 'tie');
  assert.equal(calc.speedOrder(b, a, { attackerSide: { tailwind: true } }).aSpeed, 100);
  const par = calc.speedOrder(machamp({ status: 'par' }), b);
  assert.equal(par.aSpeed, 37);
  assert.ok(!par.caveats.some(c => c.startsWith('Paralysis')));   // ×0.5 is emulator-verified
  assert.equal(calc.speedOrder(a, b, { trickRoom: true }).faster, 'b');
});

// ---------------------------------------------------------------- (e) whole-data sweeps
test('every species, move, ability and item loads and calculates without throwing', () => {
  let modelledMoves = 0, unmodelled = 0;
  for (const s of species) {
    const st = calc.stats(set(s.id, { abilityId: s.abilityIds[0] || null })).stats;
    assert.ok(st.hp > 0, `species ${s.id}`);
  }
  const allMoves = moves.map(m => m.id);
  for (let i = 0; i < allMoves.length; i += 40) {
    const out = calc.calculateMatchup(machamp({ moveIds: allMoves.slice(i, i + 40) }), snorlax(), {});
    for (const r of out.moves) {
      assert.ok(Number.isFinite(r.minDamage) && Number.isFinite(r.maxDamage), r.name);
      if (r.category !== 'Status') { if (r.modelled) modelledMoves++; else unmodelled++; }
    }
  }
  const probe = [MOVE['Strength'], MOVE['Hyper Voice'], MOVE['Fire Punch'], MOVE['Earthquake']];
  for (const a of abilities) {
    calc.calculateMatchup(machamp({ abilityId: a.id, moveIds: probe }), snorlax(), {});
    calc.calculateMatchup(machamp({ moveIds: probe }), snorlax({ abilityId: a.id }), { gameType: 'Doubles' });
  }
  for (const it of items) {
    calc.calculateMatchup(machamp({ itemId: it.id, moveIds: probe }), snorlax(), {});
    calc.calculateMatchup(machamp({ moveIds: probe }), snorlax({ itemId: it.id }), {});
  }
  console.log(`damaging moves: ${modelledMoves} modelled, ${unmodelled} not modelled`);
  assert.ok(modelledMoves > 550);
});

test('every trainer Pokémon can be calculated against itself', () => {
  let count = 0, withCaveats = 0, emptySlots = 0;
  const caveatCounts = new Map();
  for (const trainer of trainers) {
    for (const mon of trainer.team) {
      if (!mon.id) { emptySlots++; continue; } // unused trainer with an empty party slot
      const s = calc.fromTrainerMon(mon);
      const out = calc.calculateMatchup(s, s, { gameType: trainer.double ? 'Doubles' : 'Singles' });
      count++;
      const all = new Set([...out.caveats, ...out.moves.flatMap(m => m.caveats)]);
      if (all.size) withCaveats++;
      for (const c of all) caveatCounts.set(c, (caveatCounts.get(c) ?? 0) + 1);
      for (const m of out.moves) assert.ok(m.maxDamage >= m.minDamage);
    }
  }
  console.log(`trainer Pokémon: ${count} calculated, ${withCaveats} with caveats, ${emptySlots} empty slots skipped`);
  console.log([...caveatCounts].sort((a, b) => b[1] - a[1]).slice(0, 15).map(([c, n]) => `  ${n} × ${c}`).join('\n'));
  assert.equal(emptySlots, 1);
  assert.equal(count, trainers.reduce((n, t) => n + t.team.length, 0) - emptySlots);
});

test('calc-data payload stays compact and versioned', () => {
  assert.equal(data.v, 1);
  assert.equal(data.species.length, species.length);
  assert.equal(data.moves.length, moves.length);
  assert.ok(JSON.stringify(data).length < 260_000);
});

test('engine requests: structured weather/terrain source, one no-KO phrase, per-move notes, Supreme Overlord', async () => {
  const { NO_KO_TEXT } = await import('../src/lib/calc/index.ts');
  // (a) which Pokémon's Ability set the weather / terrain
  const sun = hit(machamp(), snorlax({ abilityId: ABILITY['Drought'] }), 'Fire Punch');
  assert.deepEqual(sun.out.field.weatherFrom, { side: 'defender', speciesId: SNORLAX, name: sun.out.defender.name, ability: 'Drought' });
  assert.equal(sun.out.field.terrainFrom, null);
  const roar = hit(machamp({ abilityId: ABILITY['Thunder Roar'] }), snorlax(), 'Thunder Punch');
  assert.equal(roar.out.field.terrainFrom.side, 'attacker');
  assert.equal(roar.out.field.terrainFrom.ability, 'Thunder Roar');
  assert.equal(hit(machamp(), snorlax(), 'Strength', { weather: 'Rain' }).out.field.weatherFrom, null, 'given weather has no source');
  // (b) a damaging move that cannot KO within 9 hits has one fixed text; status moves have none
  const weak = hit(set(MACHAMP, { level: 5 }), snorlax({ level: 100 }), 'Pound');
  assert.equal(weak.koHits, 0);
  assert.equal(weak.koChanceText, NO_KO_TEXT);
  assert.equal(NO_KO_TEXT, 'no KO in 9 hits');
  assert.equal(hit(machamp(), snorlax(), 'Growl').koChanceText, '');
  // notes: Sonic Boom's own note on its row; the matchup's checked-in-game facts on every damaging move
  const boom = calc.calculateMatchup({ ...machamp(), moveIds: [MOVE['Sonic Boom'], MOVE['Strength']] }, snorlax(), { weather: 'Hail' });
  assert.ok(boom.moves[0].notes.some(n => n.startsWith('Sonic Boom is not fixed damage')));
  assert.ok(!boom.moves[1].notes.some(n => n.startsWith('Sonic Boom')));
  assert.ok(boom.moves[1].notes.some(n => n.startsWith('Hail here works like Snow')));
  // Supreme Overlord (no species has it in this game; engine callers may still pass alliesFainted): caveat only while not given
  const so = ABILITY['Supreme Overlord'];
  assert.ok(hit(machamp({ abilityId: so }), snorlax(), 'Strength').caveats.some(c => c.startsWith('Supreme Overlord')));
  const two = hit(machamp({ abilityId: so, alliesFainted: 2 }), snorlax(), 'Strength');
  assert.ok(!two.caveats.some(c => c.startsWith('Supreme Overlord')));
  assert.ok(two.maxDamage > hit(machamp({ abilityId: so, alliesFainted: 0 }), snorlax(), 'Strength').maxDamage);
  // battlesAs: a held-item form reports the form's species and Ability
  const x = calc.battlesAs(set(6, { abilityId: ABILITY['Blaze'], itemId: 325, nature: 'Adamant' }));
  assert.equal(x.speciesId, 1027);
  assert.equal(x.changed, true);
  assert.equal(calc.battlesAs(machamp()).changed, false);
});
