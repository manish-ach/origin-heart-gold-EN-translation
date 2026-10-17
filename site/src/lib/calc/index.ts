/*! @license MIT
 * Origin HeartGold damage calculator engine. Damage formula and KO-chance code adapted from the
 * Pokémon Showdown damage calculator (@smogon/calc, https://github.com/smogon/damage-calc, commit 9c57e9b8).
 * Copyright (c) 2013-2025 Honko and other contributors. Full licence text: site/src/lib/calc/LICENSE.
 */
/**
 * Public API (everything else in this folder is internal).
 *
 *   const data = await (await fetch(`${base}team-builder/calc-data.json`)).json();
 *   const calc = loadCalc(data);
 *   const me = {speciesId: 9, level: 30, nature: 'Modest', abilityId: 67, itemId: null, moveIds: [57],
 *               ivs: {hp: 31, ...}, evs: {hp: 0, ...}};
 *   const foe = calc.fromTrainerMon(trainers[0].team[0]);
 *   const out = calc.calculateMatchup(me, foe, {gameType: 'Singles'});
 *   out.moves[0] → {moveId, name, minDamage, maxDamage, minPercent, maxPercent, rolls, koChanceText,
 *                   description, caveats, notes, ...}
 *   out.field → {weather, terrain, weatherFrom, terrainFrom}: *From = {side: 'attacker'|'defender', speciesId,
 *               name, ability} when an entry Ability set it (null when given in the field or absent)
 *   koChanceText is NO_KO_TEXT ('no KO in 9 hits') for a damaging move that does not KO within 9 hits.
 *   calc.speedOrder(me, foe, field) → {aSpeed, bSpeed, faster: 'a' | 'b' | 'tie', caveats}
 *
 * Set shape (CalcSet): {speciesId, level, nature (name or null = neutral), abilityId, itemId | null, moveIds,
 *   ivs {hp,atk,def,spa,spd,spe}, evs {...}, boosts?, status? ('brn','par','psn','tox','slp','frz'),
 *   curHPPercent? (1–100), gender? ('M'|'F'|'N'), abilityOn?, alliesFainted?, friendship? (0–255), caveats?}
 * Ids are the hack's ids from species/moves/abilities/items.json. A Pokémon holding the item of a held-item
 * form (Charizardite, Plates, Griseous Orb…) is calculated as that form.
 *
 * Field shape (CalcField): {gameType?: 'Singles'|'Doubles', weather?: 'Sun'|'Rain'|'Sand'|'Hail'|
 *   'Harsh Sunshine'|'Heavy Rain'|'Strong Winds', terrain?: 'Electric'|'Grassy'|'Psychic'|'Misty',
 *   gravity?, trickRoom?, magicRoom?, wonderRoom?, crit? (force critical hits),
 *   spreadTargets? (Doubles: Pokémon a spread move hits this turn; 1 = full damage, default assumes 2+),
 *   abilityField? (default true: weather/terrain/Aurora Veil set by an entry Ability when not given),
 *   attackerSide?: CalcSide, defenderSide?: CalcSide}
 * CalcSide: {reflect?, lightScreen?, auroraVeil?, stealthRock?, spikes? (0–3), helpingHand?, tailwind?,
 *   friendGuard?, battery?, powerSpot?, charge?, foresight?, protect?, leechSeed?, flowerGift?,
 *   steelySpirit?, glaiveRush? (this side's Pokémon is under Glaive Rush's after-effect)}
 * "attackerSide" is the side of the first set passed in. Use mirrorField(field) for the reverse matchup.
 *
 * Every result carries `caveats`: short player-facing notes for anything assumed, unverified or not
 * modelled. The UI must show them next to the number. `modelled: false` means no number could be given.
 */
import {calculateOHG} from './mechanics/ohg.ts';
import {getEndOfTurn} from './desc.ts';
import {Field} from './field.ts';
import {Move} from './move.ts';
import {Pokemon} from './pokemon.ts';
import {getFinalSpeed} from './mechanics/util.ts';
import {buildGeneration, INERT_ITEM_IDS, NATURE_NAMES} from './generation.ts';
import type {CalcData} from './data-projection.ts';
import type {
  FieldState, GenderName, Generation, NatureName, SideState, StatsTable, StatusName, Terrain, Weather,
} from './types.ts';
import {
  ABILITY_CAVEATS, ASSUMED_MOVES, CAVEATS, CONDITIONAL_MOVES, FRIENDSHIP_MOVES, ITEM_CAVEATS, NO_KO_TEXT, UNMODELLED_MOVES,
  VERIFIED_EOT_TEXTS, VERIFIED_MOVE_NOTES, VERIFIED_NOTES,
  WEIGHT_CAVEAT, WEIGHT_METAL_CAVEAT, WEIGHT_MOVES,
} from './caveats.ts';

export type {CalcData};
export {buildCalcData, defaultLevelUpMoves} from './data-projection.ts';
export {NO_KO_TEXT};

export interface CalcSet {
  speciesId: number;
  level: number;
  nature: NatureName | null;
  abilityId: number | null;
  itemId: number | null;
  moveIds: number[];
  ivs?: Partial<StatsTable>;
  evs?: Partial<StatsTable>;
  boosts?: Partial<StatsTable>;
  status?: StatusName | '' | null;
  curHPPercent?: number;
  gender?: 'M' | 'F' | 'N' | null;
  abilityOn?: boolean;
  alliesFainted?: number;
  /** 0–255 (Return/Frustration). Missing or null: 255 assumed, with a caveat when such a move is used. */
  friendship?: number | null;
  /** Caveats that belong to the set itself (fromTrainerMon fills these). */
  caveats?: string[];
}

export interface CalcSide {
  reflect?: boolean; lightScreen?: boolean; auroraVeil?: boolean; stealthRock?: boolean; spikes?: number;
  helpingHand?: boolean; tailwind?: boolean; friendGuard?: boolean; battery?: boolean; powerSpot?: boolean;
  charge?: boolean; foresight?: boolean; protect?: boolean; leechSeed?: boolean; flowerGift?: boolean;
  steelySpirit?: boolean; glaiveRush?: boolean;
}

export interface CalcField {
  gameType?: 'Singles' | 'Doubles';
  weather?: Weather | null;
  terrain?: Terrain | null;
  gravity?: boolean; trickRoom?: boolean; magicRoom?: boolean; wonderRoom?: boolean;
  crit?: boolean;
  /** Doubles: how many Pokémon a spread move hits this turn (default 2+; 1 = no ×0.75 reduction). */
  spreadTargets?: number;
  abilityField?: boolean;
  attackerSide?: CalcSide;
  defenderSide?: CalcSide;
}

export interface MoveResult {
  moveId: number;
  name: string;
  type: string;
  category: 'Physical' | 'Special' | 'Status';
  priority: number;
  /** false: the engine cannot give a number for this move (see caveats). */
  modelled: boolean;
  minDamage: number;
  maxDamage: number;
  minPercent: number;
  maxPercent: number;
  /** The 16 damage rolls (for multi-hit moves: the same roll on every hit, summed; see hitRolls). */
  rolls: number[];
  hitRolls: number[][] | null;
  koChanceText: string;
  koChance: number | null;
  koHits: number;
  description: string;
  /** Chance this move lands a critical hit (OHG table 1/24, 1/8, 1/2, 1). */
  critChance: number;
  caveats: string[];
  /** Certain, emulator-verified facts about this move in this matchup ("checked in game"). */
  notes: string[];
}

/** The Pokémon whose entry Ability set the weather or terrain. */
export interface FieldSource {side: 'attacker' | 'defender'; speciesId: number; name: string; ability: string}

export interface MatchupResult {
  attacker: {speciesId: number; name: string; stats: StatsTable; maxHP: number; curHP: number};
  defender: {speciesId: number; name: string; stats: StatsTable; maxHP: number; curHP: number};
  field: {weather: Weather | null; terrain: Terrain | null; weatherFrom: FieldSource | null; terrainFrom: FieldSource | null};
  moves: MoveResult[];
  /** Caveats that apply to the whole matchup (also repeated in each move's caveats). */
  caveats: string[];
  /** Informational notes (form changes, assumptions that are certain). */
  notes: string[];
}

const DEFAULT_ABILITY_ON = new Set(['Intimidate', 'Slow Start']);
const PINCH_HEAL_BERRIES = new Set(['Sitrus Berry', 'Oran Berry', 'Figy Berry', 'Wiki Berry', 'Mago Berry',
  'Aguav Berry', 'Iapapa Berry', 'Enigma Berry']);
const WEATHER_ABILITIES: Record<string, Weather> = {
  'Drought': 'Sun', 'Wildfire': 'Sun', 'Orichalcum Pulse': 'Sun', 'Desolate Land': 'Harsh Sunshine',
  'Drizzle': 'Rain', 'Primordial Sea': 'Heavy Rain', 'Sand Stream': 'Sand', 'Snow Warning': 'Hail',
  'Delta Stream': 'Strong Winds',
};
const TERRAIN_ABILITIES: Record<string, Terrain> = {
  'Electric Surge': 'Electric', 'Thunder Roar': 'Electric', 'Hadron Engine': 'Electric',
  'Psychic Surge': 'Psychic', 'Misty Surge': 'Misty', 'Grassy Surge': 'Grassy',
};
// OHG §3 crit table (VERIFIED 0x0224D9E8): stage 0–3 = 1/24, 1/8, 1/2, always.
const CRIT_RATES = [1 / 24, 1 / 8, 1 / 2, 1];
const SPEED_ITEMS = new Set(['Quick Claw', 'Custap Berry', 'Lagging Tail', 'Full Incense']);

function uniq(list: string[]) {
  return [...new Set(list.filter(Boolean))];
}

function toSide(side: CalcSide = {}): SideState {
  return {
    isReflect: !!side.reflect, isLightScreen: !!side.lightScreen, isAuroraVeil: !!side.auroraVeil,
    isSR: !!side.stealthRock, spikes: Math.max(0, Math.min(3, side.spikes || 0)),
    isHelpingHand: !!side.helpingHand, isTailwind: !!side.tailwind, isFriendGuard: !!side.friendGuard,
    isBattery: !!side.battery, isPowerSpot: !!side.powerSpot, isCharge: !!side.charge,
    isForesight: !!side.foresight, isProtected: !!side.protect, isSeeded: !!side.leechSeed,
    isFlowerGift: !!side.flowerGift, isSteelySpirit: !!side.steelySpirit, isGlaiveRushed: !!side.glaiveRush,
  };
}

/** The same field seen from the other Pokémon (swaps the two sides). */
export function mirrorField(field: CalcField = {}): CalcField {
  return {...field, attackerSide: field.defenderSide, defenderSide: field.attackerSide};
}

/**
 * Converts a trainers.json team entry into a CalcSet. Trainer IVs: `ivs` for Atk/Def/SpA/SpD/Spe and
 * `hpIvs` for HP; EVs exactly as given (may exceed 510). The nature, gender and friendship exported for the
 * trainer (set or computed from the party loader) are used as given; a missing nature is assumed neutral and
 * flagged. An empty move list means default level-up moves, looked up in `defaultMoves`.
 */
export function fromTrainerMon(mon: any, {defaultMoves}: {defaultMoves?: Record<string, number[]>} = {}): CalcSet {
  const caveats: string[] = [];
  let nature: NatureName | null = null;
  if (typeof mon.nature === 'string' && (NATURE_NAMES as string[]).includes(mon.nature)) {
    nature = mon.nature as NatureName;
  } else {
    caveats.push(CAVEATS.natureGenerated);
  }
  const gender = mon.gender === 'male' || mon.gender === 'M' ? 'M'
    : mon.gender === 'female' || mon.gender === 'F' ? 'F'
    : mon.gender === 'genderless' || mon.gender === 'N' ? 'N' : null;
  const iv = Number.isFinite(mon.ivs) ? mon.ivs : 0;
  const hpIv = Number.isFinite(mon.hpIvs) ? mon.hpIvs : iv;
  const evs = Array.isArray(mon.evs) ? mon.evs : [0, 0, 0, 0, 0, 0];
  let moveIds: number[] = Array.isArray(mon.moveIds) ? mon.moveIds.filter((id: number) => id > 0) : [];
  if (!moveIds.length) {
    const fallback = defaultMoves?.[`${mon.id}:${mon.level}`];
    if (fallback) moveIds = fallback.slice();
    else caveats.push(CAVEATS.levelUpMovesMissing);
  }
  return {
    speciesId: mon.id,
    level: mon.level,
    nature,
    abilityId: mon.abilityId || null,
    itemId: mon.itemId || null,
    moveIds,
    ivs: {hp: hpIv, atk: iv, def: iv, spa: iv, spd: iv, spe: iv},
    evs: {hp: evs[0] || 0, atk: evs[1] || 0, def: evs[2] || 0, spa: evs[3] || 0, spd: evs[4] || 0, spe: evs[5] || 0},
    gender,
    friendship: Number.isFinite(mon.friendship) ? mon.friendship : null,
    caveats,
  };
}

export function loadCalc(data: CalcData) {
  const gen: Generation = buildGeneration(data);
  const forms = (data.forms ?? []) as Array<[number, number, number, string[] | null, string[] | null]>;
  const defaultMoves = (data.defaultMoves ?? {}) as Record<string, number[]>;

  /** Builds an engine Pokémon from a set; returns it with the set's caveats and notes. */
  function resolve(set: CalcSet) {
    const caveats: string[] = [...(set.caveats ?? [])];
    const notes: string[] = [];
    let speciesId = set.speciesId;
    const baseSpecies = gen.species.get(speciesId);
    if (!baseSpecies) throw new Error(`Unknown species id ${speciesId}`);
    const nature: NatureName = set.nature && gen.natures.has(set.nature) ? set.nature : 'Serious';
    let abilityId = set.abilityId || baseSpecies.abilityIds[0] || 0;

    // OHG §6 / deviation 25: held-item forms (no in-battle Mega Evolution).
    const form = set.itemId ? forms.find(([base, , item, only, except]) =>
      base === speciesId && item === set.itemId &&
      (!only || only.includes(nature)) && (!except || !except.includes(nature))) : undefined;
    if (form) {
      const formSpecies = gen.species.get(form[1]);
      if (formSpecies) {
        const slot = baseSpecies.abilityIds.indexOf(abilityId);
        const nextAbility = formSpecies.abilityIds[slot >= 0 ? slot : 0] ?? formSpecies.abilityIds[0];
        notes.push(`${baseSpecies.name} holding ${gen.items.get(set.itemId!)?.displayName ?? 'its item'} battles as ${formSpecies.name}.`);
        speciesId = formSpecies.id;
        if (nextAbility) abilityId = nextAbility;
      }
    }
    const species = gen.species.get(speciesId)!;

    let item: string | undefined;
    if (set.itemId) {
      const record = gen.items.get(set.itemId);
      if (!record) caveats.push(CAVEATS.unknownItem(set.itemId));
      else {
        item = record.name;
        if (INERT_ITEM_IDS.includes(record.id)) caveats.push(CAVEATS.inertItem(record.displayName, record.id));
      }
    }
    const ability = abilityId ? gen.abilities.get(abilityId)?.name : undefined;

    const level = Math.max(1, Math.min(100, Math.round(set.level || 1)));
    const gender: GenderName = species.gender ?? (set.gender === 'M' || set.gender === 'F' ? set.gender : 'U');
    const pokemon = new Pokemon(gen, speciesId, {
      level, nature, ability, item, gender,
      abilityOn: set.abilityOn ?? (ability ? DEFAULT_ABILITY_ON.has(ability) : false),
      alliesFainted: set.alliesFainted,
      friendship: Number.isFinite(set.friendship) ? Math.max(0, Math.min(255, set.friendship as number)) : 255,
      boostedStat: ability === 'Protosynthesis' || ability === 'Quark Drive' ? 'auto' : undefined,
      ivs: set.ivs, evs: set.evs, boosts: set.boosts,
      status: set.status || '',
    });
    if (typeof set.curHPPercent === 'number' && set.curHPPercent < 100) {
      const pct = Math.max(0, set.curHPPercent);
      pokemon.originalCurHP = Math.max(pct > 0 ? 1 : 0, Math.ceil((pokemon.maxHP() * pct) / 100));
    }
    // Paralysis halves Speed (emulator-verified, damage_calc_parity.md "para"): no caveat.
    return {pokemon, caveats, notes, friendshipKnown: Number.isFinite(set.friendship)};
  }

  function abilityCaveats(p: Pokemon, role: 'attacker' | 'defender') {
    const entry = p.ability ? ABILITY_CAVEATS[p.ability] : undefined;
    return entry && (entry[0] === 'both' || entry[0] === role) ? [entry[1]] : [];
  }
  function itemCaveats(p: Pokemon, role: 'attacker' | 'defender') {
    const entry = p.item ? ITEM_CAVEATS[p.item] : undefined;
    return entry && (entry[0] === 'both' || entry[0] === role) ? [entry[1]] : [];
  }

  /** Field with weather/terrain/Aurora Veil from entry Abilities (slower Pokémon's weather wins). */
  function buildField(a: Pokemon, b: Pokemon, field: CalcField, caveats: string[]) {
    const source = (p: Pokemon): FieldSource => ({side: p === a ? 'attacker' : 'defender', speciesId: p.speciesId,
      name: p.name, ability: p.ability!});
    let weatherFrom: FieldSource | null = null;
    let terrainFrom: FieldSource | null = null;
    const state: FieldState = {
      gameType: field.gameType === 'Doubles' ? 'Doubles' : 'Singles',
      weather: field.weather || undefined,
      terrain: field.terrain || undefined,
      isGravity: !!field.gravity, isMagicRoom: !!field.magicRoom, isWonderRoom: !!field.wonderRoom,
      isSpreadSingle: field.spreadTargets === 1,
      attackerSide: toSide(field.attackerSide), defenderSide: toSide(field.defenderSide),
    };
    if (field.abilityField !== false) {
      const order = a.stats.spe >= b.stats.spe ? [a, b] : [b, a];
      if (!field.weather) {
        for (const p of order) {
          const w = p.ability ? WEATHER_ABILITIES[p.ability] : undefined;
          if (w) { state.weather = w; }
        }
        const setter = [...order].reverse().find(p => p.ability && WEATHER_ABILITIES[p.ability]);
        if (setter && state.weather) {
          weatherFrom = source(setter);
          caveats.push(CAVEATS.autoWeather(setter.name, state.weather === 'Hail' ? 'Hail' : `${state.weather} weather`));
        }
      }
      if (!field.terrain) {
        for (const p of order) {
          const t = p.ability ? TERRAIN_ABILITIES[p.ability] : undefined;
          if (t) state.terrain = t;
        }
        const setter = [...order].reverse().find(p => p.ability && TERRAIN_ABILITIES[p.ability]);
        if (setter && state.terrain) {
          terrainFrom = source(setter);
          caveats.push(CAVEATS.autoWeather(setter.name, `${state.terrain} Terrain`));
        }
      }
      // OHG §19: Aurora Shine sets Aurora Veil on entry.
      if (a.hasAbility('Aurora Shine')) state.attackerSide!.isAuroraVeil = true;
      if (b.hasAbility('Aurora Shine')) state.defenderSide!.isAuroraVeil = true;
    }
    if (state.weather === 'Heavy Rain' || state.weather === 'Harsh Sunshine') caveats.push(CAVEATS.primalWeather);
    if (state.weather === 'Strong Winds') caveats.push(CAVEATS.strongWinds);
    return {field: new Field(state), weatherFrom, terrainFrom};
  }

  function critChance(attacker: Pokemon, defender: Pokemon, move: Move, forced: boolean) {
    if (defender.hasAbility('Battle Armor', 'Shell Armor')) return 0;
    if (forced || move.critStage >= 6) return 1;
    if (attacker.hasAbility('Merciless') && defender.hasStatus('psn', 'tox')) return 1;
    let stage = move.critStage;
    if (attacker.hasItem('Scope Lens', 'Razor Claw')) stage += 1;
    if (attacker.hasItem('Leek') && attacker.isSpecies(83)) stage += 2;
    if (attacker.hasItem('Lucky Punch') && attacker.isSpecies(113)) stage += 2;
    if (attacker.hasAbility('Super Luck', 'Sniper')) stage += 1; // OHG §12: Sniper also +1 stage
    return CRIT_RATES[Math.min(3, stage)];
  }

  function moveCaveats(attacker: Pokemon, defender: Pokemon, move: Move, friendshipKnown: boolean) {
    const out: string[] = [];
    let unmodelled = false;
    if (FRIENDSHIP_MOVES.includes(move.name) && !friendshipKnown) out.push(CAVEATS.friendshipAssumed);
    if (UNMODELLED_MOVES[move.name]) { out.push(UNMODELLED_MOVES[move.name]); unmodelled = true; }
    if (CONDITIONAL_MOVES[move.name]) out.push(CONDITIONAL_MOVES[move.name]);
    if (ASSUMED_MOVES[move.name]) out.push(ASSUMED_MOVES[move.name]);
    if (WEIGHT_MOVES.includes(move.name)) {
      out.push(WEIGHT_CAVEAT);
      if ([attacker, defender].some(p => p.hasAbility('Heavy Metal', 'Light Metal') || p.hasItem('Float Stone'))) {
        out.push(WEIGHT_METAL_CAVEAT);
      }
    }
    if (move.isVariablePower && !unmodelled && move.category !== 'Status' &&
      !['Seismic Toss', 'Night Shade', 'Sonic Boom', 'Dragon Rage', 'Super Fang', 'Ruination', 'Nature\'s Madness',
        'Endeavor', 'Final Gambit', 'Flail', 'Reversal', 'Return', 'Frustration', 'Gyro Ball', 'Electro Ball',
        'Fling', 'Wring Out', 'Crush Grip', 'Hard Press', 'Punishment', 'Low Kick', 'Grass Knot', 'Heavy Slam',
        'Heat Crash', 'Pika Papow', 'Veevee Volley'].includes(move.name)) {
      out.push(`${move.name} has variable power that is not calculated.`);
      unmodelled = true;
    }
    if (Array.isArray(gen.moves.get(move.id)?.multihit) && !attacker.hasAbility('Skill Link')) out.push(CAVEATS.multiHit);
    if (attacker.hasAbility('Sheer Force') && move.secondaries) out.push(CAVEATS.sheerForce);
    if (defender.hasAbility('Bulletproof') && move.flags.bullet) out.push(CAVEATS.bulletproof);
    if (attacker.hasAbility('Telepathy') && move.type === 'Psychic') out.push(CAVEATS.telepathy);
    if (attacker.hasAbility('Rivalry') && (attacker.gender === 'U' || defender.gender === 'U')) out.push(CAVEATS.rivalry);
    return {caveats: out, unmodelled};
  }

  function calculateMatchup(attackerSet: CalcSet, defenderSet: CalcSet, fieldIn: CalcField = {}): MatchupResult {
    const a = resolve(attackerSet);
    const d = resolve(defenderSet);
    const caveats = [...a.caveats, ...d.caveats];
    const notes = [...a.notes, ...d.notes];
    const {field, weatherFrom, terrainFrom} = buildField(a.pokemon, d.pokemon, fieldIn, caveats);
    // Glaive Rush's ×2 (after weather, before the crit) and its timing are emulator-verified: no caveat.
    if (field.weather === 'Hail') notes.push(VERIFIED_NOTES.hail);
    if (a.pokemon.hasAbility('Corrosion') && d.pokemon.hasType('Steel')) notes.push(VERIFIED_NOTES.corrosion);
    if ([a.pokemon, d.pokemon].some(p => p.hasItem('Soul Dew') && p.isSpecies(380, 381))) notes.push(VERIFIED_NOTES.soulDew);
    caveats.push(...abilityCaveats(a.pokemon, 'attacker'), ...abilityCaveats(d.pokemon, 'defender'));
    if (a.pokemon.hasAbility('Supreme Overlord') && attackerSet.alliesFainted == null) caveats.push(CAVEATS.supremeOverlord);
    caveats.push(...itemCaveats(a.pokemon, 'attacker'), ...itemCaveats(d.pokemon, 'defender'));
    const global = uniq(caveats);

    const moves: MoveResult[] = [];
    for (const moveId of attackerSet.moveIds ?? []) {
      if (!gen.moves.has(moveId)) continue;
      const move = new Move(gen, moveId, {ability: a.pokemon.ability, item: a.pokemon.item, isCrit: !!fieldIn.crit});
      const moveNotes = VERIFIED_MOVE_NOTES[move.name] ? [VERIFIED_MOVE_NOTES[move.name]] : [];
      notes.push(...moveNotes);
      const result = calculateOHG(gen, a.pokemon.clone(), d.pokemon.clone(), move.clone(), field.clone());
      const [minDamage, maxDamage] = result.range();
      const {caveats: mc, unmodelled} = moveCaveats(a.pokemon, d.pokemon, move, a.friendshipKnown);
      if (fieldIn.gameType === 'Doubles' && fieldIn.spreadTargets == null &&
        ['allAdjacent', 'allAdjacentFoes'].includes(move.target)) mc.push(CAVEATS.spreadTargets);
      const maxHP = result.defender.maxHP();
      let rolls: number[];
      let hitRolls: number[][] | null = null;
      const dmg = result.damage;
      if (typeof dmg === 'number') rolls = [dmg];
      else if (typeof dmg[0] === 'number') rolls = (dmg as number[]).length >= 16 ? (dmg as number[]).slice() : [(dmg as number[]).reduce((s, x) => s + x, 0)];
      else {
        hitRolls = (dmg as number[][]).map(r => r.slice());
        rolls = hitRolls[0].map((_, i) => hitRolls!.reduce((s, r) => s + r[i], 0));
      }
      let koChanceText = '';
      let koChance: number | null = null;
      let koHits = 0;
      let description = '';
      const extra: string[] = [];
      const damages = move.category !== 'Status' && maxDamage > 0;
      if (damages) {
        const ko = result.kochance(false);
        koChanceText = ko.text || (ko.n ? '' : NO_KO_TEXT);
        koChance = ko.chance ?? null;
        koHits = ko.n;
        description = result.fullDesc('%', false);
        const eot = getEndOfTurn(gen, result.attacker, result.defender, result.move, result.field);
        if (eot.texts.some(t => !VERIFIED_EOT_TEXTS.includes(t)) && koHits !== 1) extra.push(CAVEATS.endOfTurn);
        if (koHits !== 1 || (ko.chance ?? 0) < 1) {
          for (const berry of PINCH_HEAL_BERRIES) if (d.pokemon.hasItem(berry)) extra.push(ITEM_CAVEATS[berry][1]);
        }
      } else if (move.category !== 'Status') {
        description = result.fullDesc('%', false);
      }
      const isUnmodelled = unmodelled && move.category !== 'Status';
      moves.push({
        moveId,
        name: gen.moves.get(moveId)!.name,
        type: result.move.type,
        category: move.category,
        priority: result.move.priority,
        modelled: !isUnmodelled,
        minDamage: isUnmodelled ? 0 : minDamage,
        maxDamage: isUnmodelled ? 0 : maxDamage,
        minPercent: isUnmodelled ? 0 : Math.floor((minDamage * 1000) / maxHP) / 10,
        maxPercent: isUnmodelled ? 0 : Math.floor((maxDamage * 1000) / maxHP) / 10,
        rolls: isUnmodelled ? [] : rolls,
        hitRolls: isUnmodelled ? null : hitRolls,
        koChanceText: isUnmodelled ? '' : koChanceText,
        koChance: isUnmodelled ? null : koChance,
        koHits: isUnmodelled ? 0 : koHits,
        description: isUnmodelled ? '' : description,
        critChance: critChance(a.pokemon, d.pokemon, move, !!fieldIn.crit),
        caveats: move.category === 'Status' ? uniq(mc) : uniq([...global, ...mc, ...extra]),
        notes: [],
        _own: moveNotes,
      } as MoveResult & {_own: string[]});
    }
    // Per-move notes: the move's own verified behaviour plus the matchup's verified facts (not form changes).
    const shared = uniq(notes).filter(n => / \(checked in game\)\.$/.test(n) && !Object.values(VERIFIED_MOVE_NOTES).includes(n));
    for (const m of moves as Array<MoveResult & {_own?: string[]}>) {
      if (m.category !== 'Status') m.notes = uniq([...(m._own ?? []), ...shared]);
      delete m._own;
    }
    const info = (p: Pokemon) => ({speciesId: p.speciesId, name: p.name, stats: {...p.rawStats},
      maxHP: p.maxHP(), curHP: p.curHP()});
    return {
      attacker: info(a.pokemon), defender: info(d.pokemon),
      field: {weather: field.weather ?? null, terrain: field.terrain ?? null, weatherFrom, terrainFrom},
      moves, caveats: global, notes: uniq(notes),
    };
  }

  /** Who moves first with moves of equal priority. `a` is on field.attackerSide. */
  function speedOrder(aSet: CalcSet, bSet: CalcSet, fieldIn: CalcField = {}) {
    const a = resolve(aSet);
    const b = resolve(bSet);
    const caveats: string[] = [];
    const {field} = buildField(a.pokemon, b.pokemon, fieldIn, caveats);
    const aSpeed = getFinalSpeed(gen, a.pokemon, field, field.attackerSide);
    const bSpeed = getFinalSpeed(gen, b.pokemon, field, field.defenderSide);
    for (const p of [a.pokemon, b.pokemon]) {
      if (p.item && SPEED_ITEMS.has(p.item)) caveats.push(CAVEATS.speedItem(p.item));
      if (p.hasAbility('Desert Hawk')) caveats.push(ABILITY_CAVEATS['Desert Hawk'][1]);
      if (p.hasAbility('Stall')) caveats.push('Stall makes it move last; not included.');
    }
    let faster: 'a' | 'b' | 'tie' = aSpeed === bSpeed ? 'tie' : aSpeed > bSpeed ? 'a' : 'b';
    if (fieldIn.trickRoom && faster !== 'tie') faster = faster === 'a' ? 'b' : 'a';
    return {aSpeed, bSpeed, faster, trickRoom: !!fieldIn.trickRoom, caveats: uniq(caveats)};
  }

  return {
    generation: gen,
    calculateMatchup,
    speedOrder,
    fromTrainerMon: (mon: any) => fromTrainerMon(mon, {defaultMoves}),
    /** Final stats of a set (after nature, IVs, EVs and held-item form), for display. */
    stats: (set: CalcSet) => {
      const {pokemon} = resolve(set);
      return {speciesId: pokemon.speciesId, stats: {...pokemon.rawStats}};
    },
    /** The species and Ability a set battles with (a held-item form changes both), for display. */
    battlesAs: (set: CalcSet) => {
      const {pokemon} = resolve(set);
      let abilityId: number | null = null;
      for (const [id, record] of gen.abilities) if (record.name === pokemon.ability) { abilityId = id; break; }
      return {speciesId: pokemon.speciesId, name: pokemon.name, abilityId, changed: pokemon.speciesId !== set.speciesId};
    },
  };
}

export type CalcEngine = ReturnType<typeof loadCalc>;
