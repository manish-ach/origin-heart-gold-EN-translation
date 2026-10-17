// Battle Pokémon state, adapted from @smogon/calc pokemon.ts (MIT; see LICENSE).
// OHG changes: species are looked up by the hack's record id, species checks use national-dex ids
// (`isSpecies`) instead of Showdown names; Dynamax, Tera and Gen 1–2 handling removed.
import type {
  GenderName, Generation, NatureName, PokemonOptions, Specie, StatID, StatIDExceptHP, StatsTable,
  StatusName, TypeName,
} from './types.ts';
import {calcStat, STAT_IDS} from './stats.ts';

export class Pokemon {
  gen: Generation;
  name: string;
  species: Specie;
  speciesId: number;
  baseId: number;

  types: [TypeName] | [TypeName, TypeName];

  level: number;
  gender: GenderName;
  ability?: string;
  abilityOn: boolean;
  alliesFainted?: number;
  friendship: number;
  boostedStat?: StatIDExceptHP | 'auto';
  item?: string;
  disabledItem?: string;

  nature: NatureName;
  ivs: StatsTable;
  evs: StatsTable;
  boosts: StatsTable;
  rawStats: StatsTable;
  stats: StatsTable;

  originalCurHP: number;
  status: StatusName | '';
  toxicCounter: number;
  moves: string[];

  constructor(gen: Generation, speciesId: number, options: PokemonOptions = {}) {
    const base = gen.species.get(speciesId);
    if (!base) throw new Error(`Unknown species id ${speciesId}`);
    this.species = {...base, ...(options.overrides || {})} as Specie;
    this.gen = gen;
    this.speciesId = this.species.id;
    this.baseId = this.species.baseId;
    this.name = this.species.name;
    this.types = this.species.types;

    this.level = options.level || 100;
    this.gender = options.gender || this.species.gender || 'U';
    this.ability = options.ability || undefined;
    this.abilityOn = !!options.abilityOn;
    this.alliesFainted = options.alliesFainted;
    this.friendship = options.friendship ?? 255;
    this.boostedStat = options.boostedStat;
    this.item = options.item || undefined;
    this.nature = options.nature || 'Serious';
    this.ivs = withDefault(options.ivs, 31);
    this.evs = withDefault(options.evs, 0);
    this.boosts = withDefault(options.boosts, 0);

    this.rawStats = {} as StatsTable;
    this.stats = {} as StatsTable;
    for (const stat of STAT_IDS) {
      const val = calcStat(gen, stat, this.species.baseStats[stat], this.ivs[stat], this.evs[stat],
        this.level, this.nature);
      this.rawStats[stat] = val;
      this.stats[stat] = val;
    }

    const curHP = options.curHP || options.originalCurHP;
    this.originalCurHP = curHP && curHP <= this.rawStats.hp ? curHP : this.rawStats.hp;
    this.status = options.status || '';
    this.toxicCounter = options.toxicCounter || 0;
    this.moves = options.moves || [];
  }

  maxHP() {
    return this.rawStats.hp;
  }

  curHP() {
    return this.originalCurHP;
  }

  hasAbility(...abilities: string[]) {
    return !!(this.ability && abilities.includes(this.ability));
  }

  hasItem(...items: string[]) {
    return !!(this.item && items.includes(this.item));
  }

  hasStatus(...statuses: StatusName[]) {
    return !!(this.status && statuses.includes(this.status));
  }

  hasType(...types: TypeName[]) {
    return types.some(type => this.types.includes(type));
  }

  hasOriginalType(...types: TypeName[]) {
    return this.hasType(...types);
  }

  /** National-dex species check (all forms of that species). */
  isSpecies(...baseIds: number[]) {
    return baseIds.includes(this.baseId);
  }

  clone() {
    return new Pokemon(this.gen, this.speciesId, {
      level: this.level,
      ability: this.ability,
      abilityOn: this.abilityOn,
      alliesFainted: this.alliesFainted,
      friendship: this.friendship,
      boostedStat: this.boostedStat,
      item: this.item,
      gender: this.gender,
      nature: this.nature,
      ivs: {...this.ivs},
      evs: {...this.evs},
      boosts: {...this.boosts},
      originalCurHP: this.originalCurHP,
      status: this.status,
      toxicCounter: this.toxicCounter,
      moves: this.moves.slice(),
      overrides: this.species,
    });
  }
}

function withDefault(current: Partial<StatsTable> | undefined, val: number): StatsTable {
  const table = {hp: val, atk: val, def: val, spa: val, spd: val, spe: val};
  if (current) {
    for (const stat of STAT_IDS) {
      const v = current[stat as StatID];
      if (typeof v === 'number' && Number.isFinite(v)) table[stat] = v;
    }
  }
  return table;
}
