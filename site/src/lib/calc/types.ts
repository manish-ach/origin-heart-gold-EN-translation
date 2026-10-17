// Type declarations for the vendored damage engine (adapted from @smogon/calc data/interface.ts and
// state.ts, MIT; see LICENSE). Interfaces only, so Node's type stripping and Vite can both load the code.

export type StatID = 'hp' | StatIDExceptHP;
export type StatIDExceptHP = 'atk' | 'def' | 'spa' | 'spd' | 'spe';
export type StatsTable<T = number> = {[stat in StatID]: T};

/** 'U' = gender not known (a Pokémon whose species can be either gender and none was set). */
export type GenderName = 'M' | 'F' | 'N' | 'U';
export type StatusName = 'slp' | 'psn' | 'brn' | 'frz' | 'par' | 'tox';
export type GameType = 'Singles' | 'Doubles';
export type Terrain = 'Electric' | 'Grassy' | 'Psychic' | 'Misty';
/** 'Hail' is the weather Snow Warning and Hail set in this hack (engine weather 4). */
export type Weather = 'Sand' | 'Sun' | 'Rain' | 'Hail' | 'Harsh Sunshine' | 'Heavy Rain' | 'Strong Winds';

export type NatureName =
  'Adamant' | 'Bashful' | 'Bold' | 'Brave' | 'Calm' |
  'Careful' | 'Docile' | 'Gentle' | 'Hardy' | 'Hasty' |
  'Impish' | 'Jolly' | 'Lax' | 'Lonely' | 'Mild' |
  'Modest' | 'Naive' | 'Naughty' | 'Quiet' | 'Quirky' |
  'Rash' | 'Relaxed' | 'Sassy' | 'Serious' | 'Timid';

export type TypeName =
  'Normal' | 'Fighting' | 'Flying' | 'Poison' | 'Ground' | 'Rock' | 'Bug' | 'Ghost' | 'Steel' |
  'Fire' | 'Water' | 'Grass' | 'Electric' | 'Psychic' | 'Ice' | 'Dragon' | 'Dark' | 'Fairy' | '???';

export type MoveCategory = 'Physical' | 'Special' | 'Status';
export type MoveTarget = 'normal' | 'allAdjacent' | 'allAdjacentFoes' | 'self' | 'other';

export interface MoveFlags {
  contact?: 1 | 0;
  bite?: 1 | 0;
  sound?: 1 | 0;
  punch?: 1 | 0;
  bullet?: 1 | 0;
  pulse?: 1 | 0;
  slicing?: 1 | 0;
  wind?: 1 | 0;
}

/** One species or form record, keyed by the hack's record id (forms 1027+ included). */
export interface Specie {
  readonly id: number;
  readonly name: string;
  /** National-dex number of the base species (species.json baseSpeciesId). */
  readonly baseId: number;
  readonly types: [TypeName] | [TypeName, TypeName];
  readonly baseStats: Readonly<StatsTable>;
  /** Fixed gender, or undefined when the species can be either. */
  readonly gender?: 'M' | 'F' | 'N';
  /** Can still evolve (Eviolite). */
  readonly nfe?: boolean;
  readonly abilityIds: number[];
}

export interface MoveData {
  readonly id: number;
  readonly name: string;
  /** null = variable/fixed power ("var." in the data); 0 = status. */
  readonly basePower: number | null;
  readonly type: TypeName;
  readonly category: MoveCategory;
  readonly flags: MoveFlags;
  /** Has a secondary effect that Sheer Force removes (inferred from the effect fields). */
  readonly secondaries?: boolean;
  readonly target: MoveTarget;
  readonly recoil?: [number, number];
  readonly hasCrashDamage?: boolean;
  readonly willCrit?: boolean;
  readonly critStage: number;
  readonly drain?: [number, number];
  readonly priority: number;
  readonly multihit?: number | [number, number];
  /** Lowers the user's attacking stat by this many stages after use (Draco Meteor, Overheat…). */
  readonly dropsStats?: number;
  readonly ignoreDefensive?: boolean;
  readonly overrideOffensiveStat?: StatIDExceptHP;
  readonly overrideDefensiveStat?: StatIDExceptHP;
}

export interface NamedRecord {
  readonly id: number;
  /** The name the mechanics code tests against (curly quotes straightened, duplicates disambiguated). */
  readonly name: string;
  /** The player-facing name from the site data. */
  readonly displayName: string;
}

export interface TypeData {
  readonly name: TypeName;
  readonly effectiveness: Readonly<{[type in TypeName]?: number}>;
}

export interface Nature {
  readonly name: NatureName;
  readonly plus?: StatID;
  readonly minus?: StatID;
}

export interface Generation {
  /** Always 9: the engine follows the Gen 7–9 branches of the upstream code where they differ. */
  readonly num: 9;
  readonly species: ReadonlyMap<number, Specie>;
  readonly moves: ReadonlyMap<number, MoveData>;
  readonly movesByName: ReadonlyMap<string, MoveData>;
  readonly abilities: ReadonlyMap<number, NamedRecord>;
  readonly items: ReadonlyMap<number, NamedRecord>;
  readonly types: ReadonlyMap<TypeName, TypeData>;
  readonly natures: ReadonlyMap<NatureName, Nature>;
}

export interface PokemonOptions {
  level?: number;
  ability?: string;
  abilityOn?: boolean;
  alliesFainted?: number;
  /** 0–255; Return/Frustration power. Default 255. */
  friendship?: number;
  boostedStat?: StatIDExceptHP | 'auto';
  item?: string;
  gender?: GenderName;
  nature?: NatureName;
  ivs?: Partial<StatsTable>;
  evs?: Partial<StatsTable>;
  boosts?: Partial<StatsTable>;
  originalCurHP?: number;
  curHP?: number;
  status?: StatusName | '';
  toxicCounter?: number;
  moves?: string[];
  overrides?: Partial<Specie>;
}

export interface MoveOptions {
  ability?: string;
  item?: string;
  isCrit?: boolean;
  hits?: number;
  timesUsed?: number;
  timesUsedWithMetronome?: number;
  overrides?: Partial<MoveData>;
}

export interface SideState {
  spikes?: number;
  isSR?: boolean;
  isReflect?: boolean;
  isLightScreen?: boolean;
  isProtected?: boolean;
  isSeeded?: boolean;
  isForesight?: boolean;
  isCharge?: boolean;
  isTailwind?: boolean;
  isHelpingHand?: boolean;
  isFlowerGift?: boolean;
  isPowerTrick?: boolean;
  isFriendGuard?: boolean;
  isAuroraVeil?: boolean;
  isBattery?: boolean;
  isPowerSpot?: boolean;
  isSteelySpirit?: boolean;
  isSwitching?: 'out' | 'in';
  /** OHG: the Pokémon on this side is under Glaive Rush's after-effect (takes ×2, INFERRED). */
  isGlaiveRushed?: boolean;
}

export interface FieldState {
  gameType?: GameType;
  weather?: Weather;
  terrain?: Terrain;
  isMagicRoom?: boolean;
  isWonderRoom?: boolean;
  isGravity?: boolean;
  isAuraBreak?: boolean;
  isFairyAura?: boolean;
  isDarkAura?: boolean;
  isBeadsOfRuin?: boolean;
  isSwordOfRuin?: boolean;
  isTabletsOfRuin?: boolean;
  isVesselOfRuin?: boolean;
  /** OHG: a spread move that hits only one Pokémon this turn (no ×0.75; emulator-verified). */
  isSpreadSingle?: boolean;
  attackerSide?: SideState;
  defenderSide?: SideState;
}
