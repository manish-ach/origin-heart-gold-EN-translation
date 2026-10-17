// Shared mechanics helpers, adapted from @smogon/calc mechanics/util.ts (MIT; see LICENSE).
// Removed: Gen 1–2 stage tables, Tera/Stellar STAB, Teraform Zero, Embody Aspect, Champions branches.
// OHG changes are marked "OHG:" with the section of work/notes/damage_calc_mechanics.md.
import type {Generation, MoveCategory, StatID, StatsTable, Terrain, TypeName, Weather} from '../types.ts';
import type {Field, Side} from '../field.ts';
import type {Move} from '../move.ts';
import type {Pokemon} from '../pokemon.ts';
import {displayStat} from '../stats.ts';
import type {RawDesc} from '../desc.ts';

const EV_ITEMS = [
  'Macho Brace',
  'Power Anklet',
  'Power Band',
  'Power Belt',
  'Power Bracer',
  'Power Lens',
  'Power Weight',
];

export function isGrounded(pokemon: Pokemon, field: Field) {
  return (field.isGravity || pokemon.hasItem('Iron Ball') ||
    (!pokemon.hasType('Flying') &&
      !pokemon.hasAbility('Levitate') &&
      !pokemon.hasItem('Air Balloon')));
}

/** Stage table 2/8 … 8/2 (OHG §1 Attack: table at 0x0224DB84, VERIFIED standard). */
export function getModifiedStat(stat: number, mod: number) {
  const table = [
    [2, 8], [2, 7], [2, 6], [2, 5], [2, 4], [2, 3], [2, 2],
    [3, 2], [4, 2], [5, 2], [6, 2], [7, 2], [8, 2],
  ];
  const [num, den] = table[6 + Math.max(-6, Math.min(6, mod))];
  return Math.floor(OF16(stat * num) / den);
}

export function computeFinalStats(
  gen: Generation, attacker: Pokemon, defender: Pokemon, field: Field, ...stats: StatID[]
) {
  const sides: Array<[Pokemon, Side]> = [[attacker, field.attackerSide], [defender, field.defenderSide]];
  for (const [pokemon, side] of sides) {
    for (const stat of stats) {
      if (stat === 'spe') {
        pokemon.stats.spe = getFinalSpeed(gen, pokemon, field, side);
      } else {
        pokemon.stats[stat] = getModifiedStat(pokemon.rawStats[stat], pokemon.boosts[stat]);
      }
    }
  }
}

export function getFinalSpeed(gen: Generation, pokemon: Pokemon, field: Field, side: Side) {
  const weather = field.weather || '';
  const terrain = field.terrain;
  let speed = getModifiedStat(pokemon.rawStats.spe, pokemon.boosts.spe);
  const speedMods = [];

  if (side.isTailwind) speedMods.push(8192);

  if ((pokemon.hasAbility('Unburden') && pokemon.abilityOn) ||
      (pokemon.hasAbility('Chlorophyll') && weather.includes('Sun')) ||
      (pokemon.hasAbility('Sand Rush') && weather === 'Sand') ||
      (pokemon.hasAbility('Swift Swim') && weather.includes('Rain')) ||
      (pokemon.hasAbility('Slush Rush') && weather === 'Hail') ||
      (pokemon.hasAbility('Surge Surfer') && terrain === 'Electric')
  ) {
    speedMods.push(8192);
  } else if (pokemon.hasAbility('Quick Feet') && pokemon.status) {
    speedMods.push(6144);
  } else if (pokemon.hasAbility('Slow Start') && pokemon.abilityOn) {
    speedMods.push(2048);
  } else if (isQPActive(pokemon, field) && getQPBoostedStat(pokemon) === 'spe') {
    speedMods.push(6144);
  }

  if (!(pokemon.hasAbility('Unburden') && pokemon.abilityOn)) {
    if (pokemon.hasItem('Choice Scarf')) {
      speedMods.push(6144);
    } else if (pokemon.hasItem('Iron Ball', ...EV_ITEMS)) {
      speedMods.push(2048);
    } else if (pokemon.hasItem('Quick Powder') && pokemon.isSpecies(132)) {
      speedMods.push(8192);
    }
  }

  speed = OF32(pokeRound((speed * chainMods(speedMods, 410, 131172)) / 4096));
  if (pokemon.hasStatus('par') && !pokemon.hasAbility('Quick Feet')) {
    // OHG: paralysis halves Speed (emulator-verified, damage_calc_parity.md "para").
    speed = Math.floor(OF32(speed * 50) / 100);
  }
  return Math.max(0, Math.min(10000, speed));
}

export function getMoveEffectiveness(
  gen: Generation,
  move: Move,
  type: TypeName,
  isGhostRevealed?: boolean,
  isGravity?: boolean,
  isRingTarget?: boolean,
  isCorrosion?: boolean,
) {
  if (isGhostRevealed && type === 'Ghost' && move.hasType('Normal', 'Fighting')) {
    return 1;
  } else if (isGravity && type === 'Flying' && move.hasType('Ground')) {
    return 1;
  } else if (move.named('Freeze-Dry') && type === 'Water') {
    return 2;
  } else {
    // OHG (emulator-verified, work/notes/damage_calc_parity.md "corrosion"): Corrosion does NOT let Poison
    // moves damage Steel types (Poison Jab and Sludge Bomb did nothing to a Registeel), so `isCorrosion`
    // leaves the chart unchanged. Its handler (events 0x5C/0x5D) is not a damage factor.
    void isCorrosion;
    let effectiveness = gen.types.get(move.type)!.effectiveness[type] ?? 1;
    if (effectiveness === 0 && isRingTarget) {
      effectiveness = 1;
    }
    if (move.named('Flying Press')) {
      effectiveness *= gen.types.get('Flying')!.effectiveness[type] ?? 1;
    }
    return effectiveness;
  }
}

export function checkAirLock(pokemon: Pokemon, field: Field) {
  if (pokemon.hasAbility('Air Lock', 'Cloud Nine')) {
    field.weather = undefined;
  }
}

export function checkForecast(pokemon: Pokemon, weather?: Weather) {
  if (pokemon.hasAbility('Forecast') && pokemon.isSpecies(351)) {
    switch (weather) {
    case 'Sun':
    case 'Harsh Sunshine':
      pokemon.types = ['Fire'];
      break;
    case 'Rain':
    case 'Heavy Rain':
      pokemon.types = ['Water'];
      break;
    case 'Hail':
      pokemon.types = ['Ice'];
      break;
    default:
      pokemon.types = ['Normal'];
    }
  }
}

export function checkItem(pokemon: Pokemon, magicRoomActive?: boolean) {
  if ((pokemon.hasAbility('Klutz') && !EV_ITEMS.includes(pokemon.item!)) || magicRoomActive) {
    pokemon.disabledItem = pokemon.item;
    pokemon.item = '';
  }
}

export function checkRawStatChanges(pokemon: Pokemon, powerTrickActive?: boolean, wonderRoomActive?: boolean) {
  if (powerTrickActive) {
    [pokemon.rawStats.atk, pokemon.rawStats.def] = [pokemon.rawStats.def, pokemon.rawStats.atk];
  }
  if (wonderRoomActive) {
    [pokemon.rawStats.def, pokemon.rawStats.spd] = [pokemon.rawStats.spd, pokemon.rawStats.def];
  }
}

export function checkIntimidate(gen: Generation, source: Pokemon, target: Pokemon) {
  const blocked =
    target.hasAbility('Clear Body', 'White Smoke', 'Hyper Cutter', 'Full Metal Body') ||
    target.hasAbility('Inner Focus', 'Own Tempo', 'Oblivious', 'Scrappy') ||
    target.hasItem('Clear Amulet');
  if (source.hasAbility('Intimidate') && source.abilityOn && !blocked) {
    if (target.hasAbility('Contrary', 'Defiant', 'Guard Dog')) {
      target.boosts.atk = Math.min(6, target.boosts.atk + 1);
    } else if (target.hasAbility('Simple')) {
      target.boosts.atk = Math.max(-6, target.boosts.atk - 2);
    } else {
      target.boosts.atk = Math.max(-6, target.boosts.atk - 1);
    }
    if (target.hasAbility('Competitive')) {
      target.boosts.spa = Math.min(6, target.boosts.spa + 2);
    }
  }
}

export function checkDownload(source: Pokemon, target: Pokemon, wonderRoomActive?: boolean) {
  if (source.hasAbility('Download')) {
    let def = target.stats.def;
    let spd = target.stats.spd;
    if (wonderRoomActive) [def, spd] = [spd, def];
    if (spd <= def) {
      source.boosts.spa = Math.min(6, source.boosts.spa + 1);
    } else {
      source.boosts.atk = Math.min(6, source.boosts.atk + 1);
    }
  }
}

export function checkIntrepidSword(source: Pokemon) {
  if (source.hasAbility('Intrepid Sword') && source.abilityOn) {
    source.boosts.atk = Math.min(6, source.boosts.atk + 1);
  }
}

export function checkDauntlessShield(source: Pokemon) {
  if (source.hasAbility('Dauntless Shield') && source.abilityOn) {
    source.boosts.def = Math.min(6, source.boosts.def + 1);
  }
}

export function checkWindRider(source: Pokemon, attackingSide: Side) {
  if (source.hasAbility('Wind Rider') && attackingSide.isTailwind) {
    source.boosts.atk = Math.min(6, source.boosts.atk + 1);
  }
}

export function checkInfiltrator(pokemon: Pokemon, affectedSide: Side) {
  if (pokemon.hasAbility('Infiltrator')) {
    affectedSide.isReflect = false;
    affectedSide.isLightScreen = false;
    affectedSide.isAuroraVeil = false;
  }
}

export function checkSeedBoost(pokemon: Pokemon, field: Field) {
  if (!pokemon.item) return;
  if (field.terrain && pokemon.item.includes('Seed')) {
    const terrainSeed = pokemon.item.substring(0, pokemon.item.indexOf(' ')) as Terrain;
    if (field.hasTerrain(terrainSeed)) {
      if (terrainSeed === 'Grassy' || terrainSeed === 'Electric') {
        pokemon.boosts.def = pokemon.hasAbility('Contrary')
          ? Math.max(-6, pokemon.boosts.def - 1)
          : Math.min(6, pokemon.boosts.def + 1);
      } else {
        pokemon.boosts.spd = pokemon.hasAbility('Contrary')
          ? Math.max(-6, pokemon.boosts.spd - 1)
          : Math.min(6, pokemon.boosts.spd + 1);
      }
      pokemon.item = '';
    }
  }
}

// NOTE: only guaranteed, damage-relevant boosts between hits of a multi-hit move.
export function checkMultihitBoost(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  attackerUsedItem = false,
  defenderUsedItem = false
) {
  if (move.named('Power-Up Punch')) {
    attacker.boosts.atk = Math.min(attacker.boosts.atk + 1, 6);
    attacker.stats.atk = getModifiedStat(attacker.rawStats.atk, attacker.boosts.atk);
  }

  const atkSimple = attacker.hasAbility('Simple') ? 2 : 1;
  const defSimple = defender.hasAbility('Simple') ? 2 : 1;

  if (!defenderUsedItem &&
    ((defender.hasItem('Luminous Moss') && move.hasType('Water')) ||
    (defender.hasItem('Maranga Berry') && move.category === 'Special') ||
    (defender.hasItem('Kee Berry') && move.category === 'Physical'))) {
    const defStat = defender.hasItem('Kee Berry') ? 'def' : 'spd';
    if (attacker.hasAbility('Unaware')) {
      desc.attackerAbility = attacker.ability;
    } else {
      if (defender.hasAbility('Contrary')) {
        desc.defenderAbility = defender.ability;
        defender.boosts[defStat] = Math.max(-6, defender.boosts[defStat] - defSimple);
      } else {
        defender.boosts[defStat] = Math.min(6, defender.boosts[defStat] + defSimple);
      }
      if (defSimple === 2) desc.defenderAbility = defender.ability;
      defender.stats[defStat] = getModifiedStat(defender.rawStats[defStat], defender.boosts[defStat]);
      desc.defenderItem = defender.item;
      defenderUsedItem = true;
    }
  }

  if (defender.hasAbility('Seed Sower')) {
    field.terrain = 'Grassy';
  }
  if (defender.hasAbility('Sand Spit')) {
    field.weather = 'Sand';
  }

  if (defender.hasAbility('Stamina')) {
    if (attacker.hasAbility('Unaware')) {
      desc.attackerAbility = attacker.ability;
    } else {
      defender.boosts.def = Math.min(defender.boosts.def + 1, 6);
      defender.stats.def = getModifiedStat(defender.rawStats.def, defender.boosts.def);
      desc.defenderAbility = defender.ability;
    }
  } else if (defender.hasAbility('Water Compaction') && move.hasType('Water')) {
    if (attacker.hasAbility('Unaware')) {
      desc.attackerAbility = attacker.ability;
    } else {
      defender.boosts.def = Math.min(defender.boosts.def + 2, 6);
      defender.stats.def = getModifiedStat(defender.rawStats.def, defender.boosts.def);
      desc.defenderAbility = defender.ability;
    }
  } else if (defender.hasAbility('Weak Armor')) {
    if (attacker.hasAbility('Unaware')) {
      desc.attackerAbility = attacker.ability;
    } else {
      defender.boosts.def = Math.max(defender.boosts.def - 1, -6);
      defender.stats.def = getModifiedStat(defender.rawStats.def, defender.boosts.def);
      desc.defenderAbility = defender.ability;
    }
    defender.boosts.spe = Math.min(defender.boosts.spe + 2, 6);
    defender.stats.spe = getFinalSpeed(gen, defender, field, field.defenderSide);
  }

  if (move.dropsStats) {
    if (attacker.hasAbility('Unaware')) {
      desc.attackerAbility = attacker.ability;
    } else {
      const stat = move.category === 'Special' ? 'spa' : 'atk';
      let boosts = attacker.boosts[stat];
      if (attacker.hasAbility('Contrary')) {
        boosts = Math.min(6, boosts + move.dropsStats);
        desc.attackerAbility = attacker.ability;
      } else {
        boosts = Math.max(-6, boosts - move.dropsStats * atkSimple);
      }
      if (atkSimple === 2) desc.attackerAbility = attacker.ability;
      if (attacker.hasItem('White Herb') && attacker.boosts[stat] < 0 && !attackerUsedItem) {
        boosts += move.dropsStats * atkSimple;
        desc.attackerItem = attacker.item;
        attackerUsedItem = true;
      }
      attacker.boosts[stat] = boosts;
      attacker.stats[stat] = getModifiedStat(attacker.rawStats[stat], attacker.boosts[stat]);
    }
  }

  if (defender.hasAbility('Mummy', 'Wandering Spirit', 'Lingering Aroma') && move.flags.contact) {
    const oldAttackerAbility = attacker.ability;
    attacker.ability = defender.ability;
    if (desc.attackerAbility) {
      desc.defenderAbility = defender.ability;
    }
    if (defender.hasAbility('Wandering Spirit')) {
      defender.ability = oldAttackerAbility;
    }
  }

  return [attackerUsedItem, defenderUsedItem];
}

/** Chaining inside one event: (a·b + 0x800) >> 12 (OHG §1 Rounding, VERIFIED = Gen 5+ chainMods). */
export function chainMods(mods: number[], lowerBound: number, upperBound: number) {
  let M = 4096;
  for (const mod of mods) {
    if (mod !== 4096) {
      M = (M * mod + 2048) >> 12;
    }
  }
  return Math.max(Math.min(M, upperBound), lowerBound);
}

/** floor(floor(floor(2L/5+2)·Power·A/D)/50)+2 (OHG §1 step 3, VERIFIED). */
export function getBaseDamage(level: number, basePower: number, attack: number, defense: number) {
  return Math.floor(
    OF32(
      Math.floor(
        OF32(OF32(Math.floor((2 * level) / 5 + 2) * basePower) * attack) / defense
      ) / 50 + 2
    )
  );
}

export function getQPBoostedStat(pokemon: Pokemon): StatID {
  if (pokemon.boostedStat && pokemon.boostedStat !== 'auto') {
    return pokemon.boostedStat;
  }
  let bestStat: StatID = 'atk';
  for (const stat of ['def', 'spa', 'spd', 'spe'] as StatID[]) {
    if (
      getModifiedStat(pokemon.rawStats[stat], pokemon.boosts[stat]) >
      getModifiedStat(pokemon.rawStats[bestStat], pokemon.boosts[bestStat])
    ) {
      bestStat = stat;
    }
  }
  return bestStat;
}

export function isQPActive(pokemon: Pokemon, field: Field) {
  if (!pokemon.boostedStat) {
    return false;
  }
  const weather = field.weather || '';
  const terrain = field.terrain;
  return (
    (pokemon.hasAbility('Protosynthesis') &&
      (weather.includes('Sun') || pokemon.hasItem('Booster Energy'))) ||
    (pokemon.hasAbility('Quark Drive') &&
      (terrain === 'Electric' || pokemon.hasItem('Booster Energy'))) ||
    (pokemon.boostedStat !== 'auto')
  );
}

/**
 * Random roll (85–100), STAB, type, burn and the final modifier chain (OHG §1 steps 8–13, VERIFIED order).
 * OHG: the caller passes the combined type effectiveness, applied once (×2·×½ is exactly ×1;
 * emulator-verified, damage_calc_parity.md "types2").
 */
export function getFinalDamage(
  baseAmount: number,
  i: number,
  effectiveness: number | number[],
  isBurned: boolean,
  stabMod: number,
  finalMod: number,
  protect?: boolean
) {
  let damageAmount = Math.floor(OF32(baseAmount * (85 + i)) / 100);
  if (stabMod !== 4096) damageAmount = OF32(damageAmount * stabMod) / 4096;
  damageAmount = pokeRound(damageAmount);
  for (const factor of Array.isArray(effectiveness) ? effectiveness : [effectiveness]) {
    damageAmount = Math.floor(OF32(damageAmount * factor));
  }

  if (isBurned) damageAmount = Math.floor(damageAmount / 2);
  if (protect) damageAmount = pokeRound(OF32(damageAmount * 1024) / 4096);
  return OF16(pokeRound(Math.max(1, OF32(damageAmount * finalMod) / 4096)));
}

export function getShellSideArmCategory(source: Pokemon, target: Pokemon, wonderRoomActive?: boolean): MoveCategory {
  let physicalDamage = source.stats.atk / target.stats.def;
  let specialDamage = source.stats.spa / target.stats.spd;
  if (wonderRoomActive) {
    physicalDamage = source.stats.atk / target.stats.spd;
    specialDamage = source.stats.spa / target.stats.def;
  }
  return physicalDamage > specialDamage ? 'Physical' : 'Special';
}

/**
 * Battle weight in kg after Heavy/Light Metal and Float Stone (minimum 0.1 kg).
 * OHG (work/notes/damage_calc_data.md §1, VERIFIED in the emulator): the battle weight field is never filled
 * in, so every battler weighs 1 hg; the modifiers then give max(1, 1 × modifier) (Heavy Metal 2 hg, INFERRED).
 */
export function getWeight(pokemon: Pokemon, desc: RawDesc, role: 'defender' | 'attacker') {
  let weightHG = 1;
  const abilityFactor = pokemon.hasAbility('Heavy Metal') ? 2
    : pokemon.hasAbility('Light Metal') ? 0.5
    : 1;
  if (abilityFactor !== 1) {
    weightHG = Math.max(Math.trunc(weightHG * abilityFactor), 1);
    desc[`${role}Ability`] = pokemon.ability;
  }
  if (pokemon.hasItem('Float Stone')) {
    weightHG = Math.max(Math.trunc(weightHG * 0.5), 1);
    desc[`${role}Item`] = pokemon.item;
  }
  return weightHG / 10;
}

/** STAB ×1.5, Adaptability ×2, none for typeless (OHG §1 step 9, VERIFIED). */
export function getStabMod(pokemon: Pokemon, move: Move, desc: RawDesc) {
  if (move.type === '???') return 4096;
  let stabMod = 4096;
  if (pokemon.hasOriginalType(move.type)) {
    stabMod += 2048;
  } else if (pokemon.hasAbility('Protean', 'Libero')) {
    stabMod += 2048;
    desc.attackerAbility = pokemon.ability;
  }
  if (pokemon.hasAbility('Adaptability') && pokemon.hasType(move.type)) {
    stabMod += 2048;
    desc.attackerAbility = pokemon.ability;
  }
  return stabMod;
}

export function countBoosts(boosts: StatsTable) {
  let sum = 0;
  for (const stat of ['atk', 'def', 'spa', 'spd', 'spe'] as StatID[]) {
    const boost = boosts[stat];
    if (boost && boost > 0) sum += boost;
  }
  return sum;
}

export function getStatDescriptionText(
  gen: Generation,
  pokemon: Pokemon,
  stat: StatID,
  powerTrickActive?: boolean,
  wonderRoomActive?: boolean,
): string {
  const initialStat: StatID = stat;
  if (wonderRoomActive) {
    if (stat === 'def') stat = 'spd';
    else if (stat === 'spd') stat = 'def';
  }
  if (powerTrickActive) {
    if (stat === 'atk') stat = 'def';
    else if (stat === 'def') stat = 'atk';
  }
  const nature = gen.natures.get(pokemon.nature)!;
  let desc = pokemon.evs[stat] +
    (stat === 'hp' || nature.plus === nature.minus ? ''
    : nature.plus === stat ? '+'
    : nature.minus === stat ? '-'
    : '') + ' ' + displayStat(initialStat);
  if (stat !== initialStat) desc += ' (' + displayStat(stat) + ')';
  const iv = pokemon.ivs[stat];
  if (iv !== 31) desc += ` ${iv} IVs`;
  return desc;
}

/**
 * Fixed-damage moves (OHG §4 "Fixed damage"). Super Fang/Ruination/Nature's Madness, Endeavor and
 * Final Gambit are handled in the main routine because they need both Pokémon.
 */
export function handleFixedDamageMoves(attacker: Pokemon, move: Move) {
  if (move.named('Seismic Toss', 'Night Shade')) {
    return attacker.level;
  }
  // OHG: Sonic Boom and Dragon Rage are NOT fixed damage in this hack (no move handler): the game runs the
  // normal formula with power 1 (emulator-verified, work/notes/damage_calc_parity.md "fixed"). See
  // calculateBasePowerOHG.
  return 0;
}

/** Applying a modifier: (v·m) >> 12, +1 if the remainder > 0x800, i.e. rounds half down (VERIFIED). */
export function pokeRound(num: number) {
  return num % 1 > 0.5 ? Math.ceil(num) : Math.floor(num);
}

export function OF16(n: number) {
  return n > 65535 ? n % 65536 : n;
}

export function OF32(n: number) {
  return n > 4294967295 ? n % 4294967296 : n;
}
