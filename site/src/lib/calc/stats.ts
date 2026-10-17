// Stat formulas, adapted from @smogon/calc stats.ts (MIT; see LICENSE). Gen 1–2 and Champions code removed.
import type {Generation, NatureName, StatID, StatsTable, TypeName} from './types.ts';

const HP_TYPES: TypeName[] = [
  'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel',
  'Fire', 'Water', 'Grass', 'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark',
];

export const STAT_IDS: StatID[] = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];

export function displayStat(stat: StatID) {
  switch (stat) {
  case 'hp': return 'HP';
  case 'atk': return 'Atk';
  case 'def': return 'Def';
  case 'spa': return 'SpA';
  case 'spd': return 'SpD';
  case 'spe': return 'Spe';
  default: throw new Error(`unknown stat ${stat}`);
  }
}

/**
 * Gen 3+ formula. OHG (VERIFIED, arm9 0x0206D6C0): non-HP stats are
 * floor((2·Base + IV + floor(EV/4)) · L / 100) + 5, then the nature; HP is the standard formula (INFERRED).
 * EVs are used as given: trainer EVs can exceed the 510 total.
 */
export function calcStat(
  gen: Generation, stat: StatID, base: number, iv: number, ev: number, level: number, nature?: NatureName
) {
  if (stat === 'hp') {
    return base === 1
      ? base
      : Math.floor(((base * 2 + iv + Math.floor(ev / 4)) * level) / 100) + level + 10;
  }
  const nat = nature ? gen.natures.get(nature) : undefined;
  const n = nat?.plus === stat && nat?.minus === stat ? 1
    : nat?.plus === stat ? 1.1
    : nat?.minus === stat ? 0.9
    : 1;
  return Math.floor((Math.floor(((base * 2 + iv + Math.floor(ev / 4)) * level) / 100) + 5) * n);
}

/**
 * Hidden Power type from IVs. OHG: the type table skips Fairy and the power stays 60 (Gen 6+ behaviour;
 * no power handler exists, INFERRED).
 */
export function getHiddenPower(ivs: StatsTable) {
  let typeBits = 0;
  let i = 1;
  for (const s of ['hp', 'atk', 'def', 'spe', 'spa', 'spd'] as StatID[]) {
    typeBits += i * (ivs[s] % 2);
    i *= 2;
  }
  return {type: HP_TYPES[Math.floor((typeBits * 15) / 63)], power: 60};
}
