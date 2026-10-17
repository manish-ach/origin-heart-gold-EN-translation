// Move state, adapted from @smogon/calc move.ts (MIT; see LICENSE).
// OHG changes: moves are looked up by the hack's move id; Z-Moves, Max Moves and Tera removed.
import type {
  Generation, MoveCategory, MoveData, MoveFlags, MoveOptions, MoveTarget, StatIDExceptHP, TypeName,
} from './types.ts';

export class Move {
  gen: Generation;
  id: number;
  name: string;
  originalName: string;
  ability?: string;
  item?: string;
  overrides?: Partial<MoveData>;

  hits: number;
  timesUsed: number;
  timesUsedWithMetronome?: number;
  bp: number;
  /** The data power was "var." (variable or fixed damage). */
  isVariablePower: boolean;
  type: TypeName;
  category: MoveCategory;
  flags: MoveFlags;
  secondaries: boolean;
  target: MoveTarget;
  recoil?: [number, number];
  hasCrashDamage: boolean;
  struggleRecoil: boolean;
  mindBlownRecoil: boolean;
  isCrit: boolean;
  critStage: number;
  drain?: [number, number];
  priority: number;
  dropsStats?: number;
  ignoreDefensive: boolean;
  overrideOffensiveStat?: StatIDExceptHP;
  overrideDefensiveStat?: StatIDExceptHP;
  breaksProtect: boolean;
  isZ: boolean;
  isMax: boolean;
  multiaccuracy: boolean;

  constructor(gen: Generation, moveId: number, options: MoveOptions = {}) {
    const base = gen.moves.get(moveId);
    if (!base) throw new Error(`Unknown move id ${moveId}`);
    const data: MoveData = {...base, ...(options.overrides || {})};
    this.gen = gen;
    this.id = data.id;
    this.name = data.name;
    this.originalName = data.name;
    this.ability = options.ability;
    this.item = options.item;
    this.overrides = options.overrides;

    this.hits = 1;
    if (data.multihit) {
      if (typeof data.multihit === 'number') {
        this.hits = data.multihit;
      } else if (options.hits) {
        this.hits = options.hits;
      } else {
        this.hits = options.ability === 'Skill Link' ? data.multihit[1] : data.multihit[0] + 1;
      }
    }
    if (options.hits && typeof data.multihit === 'number') this.hits = options.hits;
    this.timesUsedWithMetronome = options.timesUsedWithMetronome;

    this.isVariablePower = data.basePower === null;
    this.bp = data.basePower || 0;
    this.type = data.id === 165 ? '???' : data.type; // Struggle deals typeless damage
    this.category = data.category;
    this.dropsStats = data.dropsStats;
    this.timesUsed = options.timesUsed || 1;
    this.secondaries = !!data.secondaries;
    this.target = data.target || 'normal';
    this.recoil = data.recoil;
    this.hasCrashDamage = !!data.hasCrashDamage;
    this.struggleRecoil = data.id === 165;
    this.mindBlownRecoil = false;
    this.critStage = data.critStage || 0;
    this.isCrit = !!options.isCrit || !!data.willCrit;
    this.drain = data.drain;
    this.flags = {...data.flags};
    this.priority = data.priority || 0;
    this.ignoreDefensive = !!data.ignoreDefensive;
    this.overrideOffensiveStat = data.overrideOffensiveStat;
    this.overrideDefensiveStat = data.overrideDefensiveStat;
    this.breaksProtect = false;
    this.isZ = false;
    this.isMax = false;
    this.multiaccuracy = false;
  }

  named(...names: string[]) {
    return names.includes(this.name);
  }

  hasType(...types: Array<TypeName | undefined>) {
    return types.includes(this.type);
  }

  clone() {
    const copy = new Move(this.gen, this.id, {
      ability: this.ability,
      item: this.item,
      isCrit: this.isCrit,
      hits: this.hits,
      timesUsed: this.timesUsed,
      timesUsedWithMetronome: this.timesUsedWithMetronome,
      overrides: this.overrides,
    });
    copy.hits = this.hits;
    return copy;
  }
}
