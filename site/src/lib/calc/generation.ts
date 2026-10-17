// The Origin HeartGold `Generation`: species, moves, abilities, items, type chart and natures, keyed by
// the hack's own ids and built from the compact calc-data payload (see data-projection.ts).
import type {
  Generation, MoveCategory, MoveData, MoveTarget, NamedRecord, Nature, NatureName, Specie, StatsTable,
  TypeData, TypeName,
} from './types.ts';
import type {CalcData} from './data-projection.ts';

const TYPES: TypeName[] = [
  'Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel',
  'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark', 'Fairy',
];

// OHG §1 Type chart (VERIFIED): the hack's 18×18 matrix at ov14 0x0224DA40 is identical to the Gen 6–9
// chart. Listed as attacking type → {defending type: multiplier}; omitted pairs are ×1.
const CHART: Record<string, Partial<Record<TypeName, number>>> = {
  Normal: {Rock: 0.5, Ghost: 0, Steel: 0.5},
  Fighting: {Normal: 2, Flying: 0.5, Poison: 0.5, Rock: 2, Bug: 0.5, Ghost: 0, Steel: 2, Psychic: 0.5, Ice: 2, Dark: 2, Fairy: 0.5},
  Flying: {Fighting: 2, Rock: 0.5, Bug: 2, Steel: 0.5, Grass: 2, Electric: 0.5},
  Poison: {Poison: 0.5, Ground: 0.5, Rock: 0.5, Ghost: 0.5, Steel: 0, Grass: 2, Fairy: 2},
  Ground: {Flying: 0, Poison: 2, Rock: 2, Bug: 0.5, Steel: 2, Fire: 2, Grass: 0.5, Electric: 2},
  Rock: {Fighting: 0.5, Flying: 2, Ground: 0.5, Bug: 2, Steel: 0.5, Fire: 2, Ice: 2},
  Bug: {Fighting: 0.5, Flying: 0.5, Poison: 0.5, Ghost: 0.5, Steel: 0.5, Fire: 0.5, Grass: 2, Psychic: 2, Dark: 2, Fairy: 0.5},
  Ghost: {Normal: 0, Ghost: 2, Psychic: 2, Dark: 0.5},
  Steel: {Rock: 2, Steel: 0.5, Fire: 0.5, Water: 0.5, Electric: 0.5, Ice: 2, Fairy: 2},
  Fire: {Rock: 0.5, Bug: 2, Steel: 2, Fire: 0.5, Water: 0.5, Grass: 2, Ice: 2, Dragon: 0.5},
  Water: {Ground: 2, Rock: 2, Fire: 2, Water: 0.5, Grass: 0.5, Dragon: 0.5},
  Grass: {Flying: 0.5, Poison: 0.5, Ground: 2, Rock: 2, Bug: 0.5, Steel: 0.5, Fire: 0.5, Water: 2, Grass: 0.5, Dragon: 0.5},
  Electric: {Flying: 2, Ground: 0, Water: 2, Grass: 0.5, Electric: 0.5, Dragon: 0.5},
  Psychic: {Fighting: 2, Poison: 2, Steel: 0.5, Psychic: 0.5, Dark: 0},
  Ice: {Flying: 2, Ground: 2, Steel: 0.5, Fire: 0.5, Water: 0.5, Grass: 2, Ice: 0.5, Dragon: 2},
  Dragon: {Steel: 0.5, Dragon: 2, Fairy: 0},
  Dark: {Fighting: 0.5, Ghost: 2, Psychic: 2, Dark: 0.5, Fairy: 0.5},
  Fairy: {Fighting: 2, Poison: 0.5, Steel: 0.5, Fire: 0.5, Dragon: 2, Dark: 2},
};

const NATURES: Array<[NatureName, string?, string?]> = [
  ['Adamant', 'atk', 'spa'], ['Bashful'], ['Bold', 'def', 'atk'], ['Brave', 'atk', 'spe'],
  ['Calm', 'spd', 'atk'], ['Careful', 'spd', 'spa'], ['Docile'], ['Gentle', 'spd', 'def'],
  ['Hardy'], ['Hasty', 'spe', 'def'], ['Impish', 'def', 'spa'], ['Jolly', 'spe', 'spa'],
  ['Lax', 'def', 'spd'], ['Lonely', 'atk', 'def'], ['Mild', 'spa', 'def'], ['Modest', 'spa', 'atk'],
  ['Naive', 'spe', 'spd'], ['Naughty', 'atk', 'spd'], ['Quiet', 'spa', 'spe'], ['Quirky'],
  ['Rash', 'spa', 'spd'], ['Relaxed', 'def', 'spe'], ['Sassy', 'spd', 'spe'], ['Serious'],
  ['Timid', 'spe', 'atk'],
];
export const NATURE_NAMES = NATURES.map(n => n[0]);

/** Ability ids whose site name is shared with another id; the engine needs the distinct upstream names. */
const ABILITY_NAMES: Record<number, string> = {
  266: 'As One (Glastrier)', 267: 'As One (Spectrier)',
  301: 'Embody Aspect (Teal)', 302: 'Embody Aspect (Hearthflame)',
  303: 'Embody Aspect (Wellspring)', 304: 'Embody Aspect (Cornerstone)',
};

/**
 * OHG §3 / deviation 22 (VERIFIED absent from the item handler table): these renamed vanilla slots have
 * no battle effect. They get a distinct engine name so that e.g. "Eviolite" only matches the live id 584.
 */
export const INERT_ITEM_IDS = [110, 111, 252, 324];

const TARGET_NAMES: MoveTarget[] = ['normal', 'allAdjacent', 'allAdjacentFoes', 'other'];
const CATEGORY: Record<string, MoveCategory> = {P: 'Physical', S: 'Special', X: 'Status'};
const STAT_ORDER = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'] as const;

/** Per-move data the hack's code keys on the move rather than on the move table (OHG §4). */
const MOVE_PATCHES: Record<string, Partial<MoveData>> = {
  'Psyshock': {overrideDefensiveStat: 'def'},
  'Psystrike': {overrideDefensiveStat: 'def'},
  'Secret Sword': {overrideDefensiveStat: 'def'},
  'Chip Away': {ignoreDefensive: true},
  'Sacred Sword': {ignoreDefensive: true},
  'Darkest Lariat': {ignoreDefensive: true},
  'Jump Kick': {hasCrashDamage: true},
  'High Jump Kick': {hasCrashDamage: true},
  'Tera Blast': {basePower: 100}, // OHG §4: handler sets 100
};

export function buildGeneration(data: CalcData): Generation {
  if (!data || data.v !== 1) throw new Error('Unsupported calc-data version');
  const species = new Map<number, Specie>();
  for (const [id, name, baseId, types, stats, abilityIds, hidden, flags, gender] of data.species as any[]) {
    const baseStats = {} as StatsTable;
    STAT_ORDER.forEach((stat, i) => { baseStats[stat] = stats[i]; });
    const allAbilities = [...abilityIds];
    if (hidden && !allAbilities.includes(hidden)) allAbilities.push(hidden);
    species.set(id, {
      id, name, baseId, types: types.slice(0, 2) as Specie['types'], baseStats,
      gender: gender || undefined,
      nfe: !!(flags & 1),
      abilityIds: allAbilities,
    });
  }

  const moves = new Map<number, MoveData>();
  const movesByName = new Map<string, MoveData>();
  for (const [id, name, type, cat, power, priority, target, flags, critStage, hits, drain, extra] of data.moves as any[]) {
    const move: MoveData = {
      id, name, type, category: CATEGORY[cat],
      basePower: power,
      priority,
      target: TARGET_NAMES[target] ?? 'normal',
      flags: {
        contact: flags & 1 ? 1 : 0,
        punch: flags & 2 ? 1 : 0,
        sound: flags & 4 ? 1 : 0,
        bite: flags & 8 ? 1 : 0,
        slicing: flags & 16 ? 1 : 0,
        bullet: flags & 32 ? 1 : 0,
      },
      critStage,
      willCrit: critStage >= 6,
      multihit: hits ? (hits[0] === hits[1] ? hits[0] : [hits[0], hits[1]]) : undefined,
      drain: drain > 0 ? [drain, 100] : undefined,
      recoil: drain < 0 ? [-drain, 100] : undefined,
      secondaries: !!(extra & 1),
      dropsStats: (extra >> 1) || undefined,
      ...(MOVE_PATCHES[name] || {}),
    };
    moves.set(id, move);
    movesByName.set(name, move);
  }

  const abilities = new Map<number, NamedRecord>();
  for (const [id, name] of data.abilities as any[]) {
    abilities.set(id, {id, name: ABILITY_NAMES[id] ?? name.replace(/[‘’]/g, '\''), displayName: name});
  }

  const items = new Map<number, NamedRecord>();
  for (const [id, name] of data.items as any[]) {
    const engineName = INERT_ITEM_IDS.includes(id) ? `${name} (no battle effect, #${id})` : name.replace(/[‘’]/g, '\'');
    items.set(id, {id, name: engineName, displayName: name});
  }

  const types = new Map<TypeName, TypeData>();
  for (const attacking of TYPES) {
    const effectiveness: Partial<Record<TypeName, number>> = {'???': 1};
    for (const defending of TYPES) effectiveness[defending] = CHART[attacking][defending] ?? 1;
    types.set(attacking, {name: attacking, effectiveness});
  }
  const neutral: Partial<Record<TypeName, number>> = {'???': 1};
  for (const t of TYPES) neutral[t] = 1;
  types.set('???', {name: '???', effectiveness: neutral}); // typeless (OHG type 18) is always neutral

  const natures = new Map<NatureName, Nature>();
  for (const [name, plus, minus] of NATURES) {
    natures.set(name, {name, plus: plus as Nature['plus'], minus: minus as Nature['minus']});
  }

  return {num: 9, species, moves, movesByName, abilities, items, types, natures};
}
