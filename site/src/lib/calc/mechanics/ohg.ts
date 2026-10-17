// Origin HeartGold damage routine.
// Adapted from @smogon/calc mechanics/gen789.ts (MIT; see ../LICENSE), upstream commit 9c57e9b8.
// Removed: Tera/Stellar, Dynamax/Max Moves, Z-Moves, Champions, Gen 1–8-only branches.
// Every hack-specific change is marked "OHG:" with its item number in the deviation list of
// work/notes/damage_calc_mechanics.md ("Recommended calc model") or the section it comes from.
import type {Generation, StatID, Terrain, TypeName} from '../types.ts';
import {getBerryResistType, getFlingPower, getItemBoostType, SEED_BOOSTED_STAT} from '../items.ts';
import type {RawDesc} from '../desc.ts';
import type {Field} from '../field.ts';
import type {Move} from '../move.ts';
import type {Pokemon} from '../pokemon.ts';
import {Result} from '../result.ts';
import {getHiddenPower} from '../stats.ts';
import {
  chainMods,
  checkAirLock,
  checkDauntlessShield,
  checkDownload,
  checkForecast,
  checkInfiltrator,
  checkIntimidate,
  checkIntrepidSword,
  checkItem,
  checkMultihitBoost,
  checkSeedBoost,
  checkWindRider,
  checkRawStatChanges,
  computeFinalStats,
  countBoosts,
  getBaseDamage,
  getStatDescriptionText,
  getFinalDamage,
  getModifiedStat,
  getQPBoostedStat,
  getMoveEffectiveness,
  getShellSideArmCategory,
  getWeight,
  handleFixedDamageMoves,
  isGrounded,
  OF16, OF32,
  pokeRound,
  isQPActive,
  getStabMod,
} from './util.ts';

/** OHG §19: custom -ate abilities (Normal → type, ×1.2) next to the official ones. */
const ATE_ABILITIES: Record<string, TypeName> = {
  'Aerilate': 'Flying',
  'Galvanize': 'Electric',
  'Pixilate': 'Fairy',
  'Refrigerate': 'Ice',
  'Burning Skin': 'Fire',
  'Azure Skin': 'Water',
  'Grass Skin': 'Grass',
  'Dark Skin': 'Dark',
  'Dragonize': 'Dragon',
};

/** OHG §18: Mega Launcher is a hard-coded move list in the hack (×1.5), not the pulse flag. */
export const MEGA_LAUNCHER_MOVES = ['Water Pulse', 'Aura Sphere', 'Dark Pulse', 'Dragon Pulse', 'Origin Pulse'];

const TECHNO_BLAST: Record<string, TypeName> = {
  'Burn Drive': 'Fire', 'Chill Drive': 'Ice', 'Douse Drive': 'Water', 'Shock Drive': 'Electric',
};

/** OHG §4: pinch abilities activate at HP ≤ ½ (helper 0x0223B07C). */
function inPinch(pokemon: Pokemon) {
  return pokemon.curHP() * 2 <= pokemon.maxHP();
}

export function calculateOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field
) {
  // #region Initial

  checkAirLock(attacker, field);
  checkAirLock(defender, field);
  checkForecast(attacker, field.weather);
  checkForecast(defender, field.weather);
  checkItem(attacker, field.isMagicRoom);
  checkItem(defender, field.isMagicRoom);
  checkRawStatChanges(attacker, field.attackerSide.isPowerTrick, field.isWonderRoom);
  checkRawStatChanges(defender, field.defenderSide.isPowerTrick, field.isWonderRoom);
  checkSeedBoost(attacker, field);
  checkSeedBoost(defender, field);
  checkDauntlessShield(attacker);
  checkDauntlessShield(defender);

  computeFinalStats(gen, attacker, defender, field, 'def', 'spd', 'spe');

  checkIntimidate(gen, attacker, defender);
  checkIntimidate(gen, defender, attacker);
  checkDownload(attacker, defender, field.isWonderRoom);
  checkDownload(defender, attacker, field.isWonderRoom);
  checkIntrepidSword(attacker);
  checkIntrepidSword(defender);

  checkWindRider(attacker, field.attackerSide);
  checkWindRider(defender, field.defenderSide);

  if (move.named('Meteor Beam', 'Electro Shot')) {
    attacker.boosts.spa +=
      attacker.hasAbility('Simple') ? 2
      : attacker.hasAbility('Contrary') ? -1
      : 1;
    attacker.boosts.spa = Math.min(6, Math.max(-6, attacker.boosts.spa));
  }

  computeFinalStats(gen, attacker, defender, field, 'atk', 'spa');

  checkInfiltrator(attacker, field.defenderSide);
  checkInfiltrator(defender, field.attackerSide);

  const desc: RawDesc = {
    attackerName: attacker.name,
    moveName: move.name,
    defenderName: defender.name,
    isWonderRoom: field.isWonderRoom,
  };

  if (move.named('Photon Geyser')) {
    move.category = attacker.stats.atk > attacker.stats.spa ? 'Physical' : 'Special';
  }

  const result = new Result(gen, attacker, defender, move, field, 0, desc);

  if (move.category === 'Status' && !move.named('Nature Power')) {
    return result;
  }

  if (move.flags.punch && attacker.hasItem('Punching Glove')) {
    desc.attackerItem = attacker.item;
    move.flags.contact = 0;
  }

  if (move.named('Shell Side Arm') &&
    getShellSideArmCategory(attacker, defender, field.isWonderRoom) === 'Physical') {
    move.category = 'Physical';
    move.flags.contact = 1;
  }

  const breaksProtect = attacker.hasAbility('Unseen Fist') && !!move.flags.contact;
  if (field.defenderSide.isProtected && !breaksProtect) {
    desc.isProtected = true;
    return result;
  }

  if (move.name === 'Pain Split') {
    const average = Math.floor((attacker.curHP() + defender.curHP()) / 2);
    result.damage = Math.max(0, defender.curHP() - average);
    return result;
  }

  const defenderAbilityIgnored = defender.hasAbility(
    'Armor Tail', 'Aroma Veil', 'Aura Break', 'Battle Armor',
    'Big Pecks', 'Bulletproof', 'Clear Body', 'Contrary',
    'Damp', 'Dazzling', 'Disguise', 'Dry Skin',
    'Earth Eater', 'Filter', 'Flash Fire',
    'Flower Gift', 'Flower Veil', 'Fluffy', 'Friend Guard',
    'Fur Coat', 'Good as Gold', 'Grass Pelt', 'Guard Dog',
    'Heatproof', 'Heavy Metal', 'Hyper Cutter', 'Ice Face',
    'Ice Scales', 'Illuminate', 'Immunity', 'Inner Focus',
    'Insomnia', 'Keen Eye', 'Leaf Guard', 'Levitate',
    'Light Metal', 'Lightning Rod', 'Limber', 'Magic Bounce',
    'Magma Armor', 'Marvel Scale', "Mind's Eye", 'Mirror Armor',
    'Motor Drive', 'Multiscale', 'Oblivious', 'Overcoat',
    'Own Tempo', 'Pastel Veil', 'Punk Rock', 'Purifying Salt',
    'Queenly Majesty', 'Sand Veil', 'Sap Sipper', 'Shell Armor',
    'Shield Dust', 'Simple', 'Snow Cloak', 'Solid Rock',
    'Soundproof', 'Sticky Hold', 'Storm Drain', 'Sturdy',
    'Suction Cups', 'Sweet Veil', 'Tangled Feet', 'Telepathy',
    'Thermal Exchange', 'Thick Fat', 'Unaware',
    'Vital Spirit', 'Volt Absorb', 'Water Absorb', 'Water Bubble',
    'Water Veil', 'Well-Baked Body', 'White Smoke', 'Wind Rider',
    'Wonder Guard', 'Wonder Skin'
  );

  const attackerIgnoresAbility = attacker.hasAbility('Mold Breaker', 'Teravolt', 'Turboblaze');
  const moveIgnoresAbility = move.named('Moongeist Beam', 'Photon Geyser', 'Sunsteel Strike');

  if (defenderAbilityIgnored && (attackerIgnoresAbility || moveIgnoresAbility)) {
    if (attackerIgnoresAbility) desc.attackerAbility = attacker.ability;
    if (defender.hasItem('Ability Shield')) {
      desc.defenderItem = defender.item;
    } else {
      defender.ability = '';
    }
  }

  const ignoresNeutralizingGas = [
    'As One (Glastrier)', 'As One (Spectrier)', 'Battle Bond', 'Comatose',
    'Disguise', 'Gulp Missile', 'Ice Face', 'Multitype', 'Neutralizing Gas',
    'Power Construct', 'RKS System', 'Schooling', 'Shields Down',
    'Stance Change', 'Tera Shift', 'Zen Mode', 'Zero to Hero',
  ];

  if (attacker.hasAbility('Neutralizing Gas') &&
    !ignoresNeutralizingGas.includes(defender.ability || '')) {
    desc.attackerAbility = attacker.ability;
    if (defender.hasItem('Ability Shield')) {
      desc.defenderItem = defender.item;
    } else {
      defender.ability = '';
    }
  }

  if (defender.hasAbility('Neutralizing Gas') &&
    !ignoresNeutralizingGas.includes(attacker.ability || '')) {
    desc.defenderAbility = defender.ability;
    if (attacker.hasItem('Ability Shield')) {
      desc.attackerItem = attacker.item;
    } else {
      attacker.ability = '';
    }
  }

  // OHG §17 / §6: Battle Armor and Shell Armor block crits; Merciless always crits a poisoned target.
  const isCritical = !defender.hasAbility('Battle Armor', 'Shell Armor') &&
    (move.isCrit || (attacker.hasAbility('Merciless') && defender.hasStatus('psn', 'tox'))) &&
    move.timesUsed === 1;

  let type = move.type;
  if (move.originalName === 'Weather Ball') {
    const holdingUmbrella = attacker.hasItem('Utility Umbrella');
    const isMegaSol = attacker.hasAbility('Mega Sol');
    type =
      (field.hasWeather('Sun', 'Harsh Sunshine') || isMegaSol) && !holdingUmbrella ? 'Fire'
      : field.hasWeather('Rain', 'Heavy Rain') && !holdingUmbrella ? 'Water'
      : field.hasWeather('Sand') ? 'Rock'
      : field.hasWeather('Hail') ? 'Ice'
      : 'Normal';
    if (isMegaSol) desc.attackerAbility = attacker.ability;
    else desc.weather = field.weather;
    desc.moveType = type;
  } else if (move.named('Hidden Power')) {
    // OHG §4 type-change hooks: standard IV formula, table skips Fairy, power stays 60.
    type = getHiddenPower(attacker.ivs).type;
    desc.moveType = type;
  } else if (move.named('Judgment') && attacker.item && attacker.item.includes('Plate')) {
    type = getItemBoostType(attacker.item)!;
  } else if (move.originalName === 'Techno Blast' && attacker.item && TECHNO_BLAST[attacker.item]) {
    type = TECHNO_BLAST[attacker.item];
    desc.moveType = type;
  } else if (move.originalName === 'Multi-Attack' && attacker.item && attacker.item.endsWith(' Memory')) {
    type = attacker.item.substring(0, attacker.item.indexOf(' ')) as TypeName;
    desc.moveType = type;
  } else if (
    move.named('Nature Power') ||
    (move.originalName === 'Terrain Pulse' && isGrounded(attacker, field))
  ) {
    type =
      field.hasTerrain('Electric') ? 'Electric'
      : field.hasTerrain('Grassy') ? 'Grass'
      : field.hasTerrain('Misty') ? 'Fairy'
      : field.hasTerrain('Psychic') ? 'Psychic'
      : 'Normal';
    desc.terrain = field.terrain;
    if (!(move.named('Nature Power') && attacker.hasAbility('Prankster')) &&
      ((defender.types.includes('Dark') ||
      (field.hasTerrain('Psychic') && isGrounded(defender, field))))) {
      desc.moveType = type;
    }
  } else if (move.originalName === 'Revelation Dance') {
    type = attacker.types[0] === '???' && attacker.types[1] ? attacker.types[1] : attacker.types[0];
  } else if (move.named('Aura Wheel') && attacker.speciesId === 1341) {
    type = 'Dark'; // Morpeko (Hangry Mode)
  } else if (move.named('Raging Bull')) {
    // Paldean Tauros forms: the breed's second type (Combat is pure Fighting).
    if (attacker.isSpecies(128)) type = attacker.speciesId === 128 ? 'Normal' : (attacker.types[1] ?? attacker.types[0]);
    field.defenderSide.isReflect = false;
    field.defenderSide.isLightScreen = false;
    field.defenderSide.isAuroraVeil = false;
  } else if (move.named('Ivy Cudgel')) {
    if (attacker.isSpecies(1017)) type = attacker.types[1] ?? 'Grass';
  } else if (move.named('Brick Break', 'Psychic Fangs')) {
    field.defenderSide.isReflect = false;
    field.defenderSide.isLightScreen = false;
    field.defenderSide.isAuroraVeil = false;
  }

  if (attacker.hasAbility('Electromorphosis') && attacker.abilityOn) {
    field.attackerSide.isCharge = true;
  }

  let hasAteAbilityTypeChange = false;
  let isLiquidVoice = false;
  const noTypeChange = move.named(
    'Revelation Dance',
    'Judgment',
    'Nature Power',
    'Techno Blast',
    'Multi-Attack',
    'Natural Gift',
    'Weather Ball',
    'Terrain Pulse',
    'Struggle',
    'Hidden Power',
  );

  if (!noTypeChange) {
    const ateType = attacker.ability ? ATE_ABILITIES[attacker.ability] : undefined;
    if (ateType && type === 'Normal') {
      type = ateType;
      hasAteAbilityTypeChange = true;
    } else if ((isLiquidVoice = attacker.hasAbility('Liquid Voice') && !!move.flags.sound)) {
      type = 'Water';
    } else if (attacker.hasAbility('Normalize')) {
      type = 'Normal';
      hasAteAbilityTypeChange = true;
    }
    if (hasAteAbilityTypeChange || isLiquidVoice) {
      desc.attackerAbility = attacker.ability;
    }
  }

  move.type = type;

  const isGhostRevealed =
    attacker.hasAbility('Scrappy') || attacker.hasAbility('Mind\'s Eye') ||
      field.defenderSide.isForesight;
  const isRingTarget = defender.hasItem('Ring Target') && !defender.hasAbility('Klutz');
  const isCorrosion = attacker.hasAbility('Corrosion');
  const type1Effectiveness = getMoveEffectiveness(
    gen, move, defender.types[0], isGhostRevealed, field.isGravity, isRingTarget, isCorrosion
  );
  const type2Effectiveness = defender.types[1]
    ? getMoveEffectiveness(gen, move, defender.types[1], isGhostRevealed, field.isGravity, isRingTarget, isCorrosion)
    : 1;

  let typeEffectiveness = type1Effectiveness * type2Effectiveness;
  // OHG §1 step 10 (emulator-verified, work/notes/damage_calc_parity.md "types2"): the game applies the
  // COMBINED effectiveness as one shift (0x022261B8: code 7 = ×1, <<1/<<2, >>1/>>2), so ×2×½ is exactly ×1
  // and ×¼ is one floor. Applying the two factors one at a time loses 1 when ×½ comes first on an odd value.
  let typeFactors = [typeEffectiveness];

  if (typeEffectiveness === 0 && move.hasType('Ground') &&
    defender.hasItem('Iron Ball') && !defender.hasAbility('Klutz')) {
    typeEffectiveness = 1;
    typeFactors = [1];
  }

  if (typeEffectiveness === 0 && move.named('Thousand Arrows')) {
    typeEffectiveness = 1;
    typeFactors = [1];
  }

  if (typeEffectiveness === 0) {
    return result;
  }

  if ((move.named('Sky Drop') &&
        (defender.hasType('Flying') || getWeight(defender, desc, 'defender') >= 200 || field.isGravity)) ||
      (move.named('Synchronoise') && !defender.hasType(attacker.types[0]) &&
        (!attacker.types[1] || !defender.hasType(attacker.types[1]))) ||
      (move.named('Dream Eater') &&
        (!(defender.hasStatus('slp') || defender.hasAbility('Comatose')))) ||
      (move.named('Steel Roller') && !field.terrain) ||
      (move.named('Poltergeist') &&
        (!defender.item || (isQPActive(defender, field) && defender.hasItem('Booster Energy'))))
  ) {
    return result;
  }

  // OHG §21: primal rain and sun only change the damage step (×1.5/×0.5); whether moves fail is
  // UNKNOWN, so the upstream "move fails" rule is not applied (the API raises a caveat).

  if (field.hasWeather('Strong Winds') && defender.hasType('Flying') &&
      (gen.types.get(move.type)!.effectiveness['Flying'] ?? 1) > 1) {
    typeEffectiveness /= 2;
    typeFactors = [typeEffectiveness];
    desc.weather = field.weather;
  }

  if ((defender.hasAbility('Wonder Guard', 'Ninja Bond') && typeEffectiveness <= 1) ||
      (move.hasType('Grass') && defender.hasAbility('Sap Sipper')) ||
      (move.hasType('Fire') && defender.hasAbility('Flash Fire', 'Well-Baked Body', 'Blazing Awe')) ||
      (move.hasType('Water') && defender.hasAbility('Dry Skin', 'Storm Drain', 'Water Absorb')) ||
      (move.hasType('Electric') &&
        defender.hasAbility('Lightning Rod', 'Motor Drive', 'Volt Absorb')) ||
      (move.hasType('Ground') &&
        !field.isGravity && !move.named('Thousand Arrows') &&
        !defender.hasItem('Iron Ball') && defender.hasAbility('Levitate')) ||
      (move.flags.bullet && defender.hasAbility('Bulletproof')) ||
      (move.flags.sound && !move.named('Clangorous Soul') && defender.hasAbility('Soundproof')) ||
      (move.priority > 0 && defender.hasAbility('Queenly Majesty', 'Dazzling', 'Armor Tail')) ||
      (move.hasType('Ground') && defender.hasAbility('Earth Eater')) ||
      (move.flags.wind && defender.hasAbility('Wind Rider'))
  ) {
    desc.defenderAbility = defender.ability;
    return result;
  }

  if (move.hasType('Ground') && !move.named('Thousand Arrows') &&
      !field.isGravity && defender.hasItem('Air Balloon')) {
    desc.defenderItem = defender.item;
    return result;
  }

  if (move.priority > 0 && field.hasTerrain('Psychic') && isGrounded(defender, field)) {
    desc.terrain = field.terrain;
    return result;
  }

  desc.HPEVs = getStatDescriptionText(gen, defender, 'hp');

  const fixedDamage = handleFixedDamageMoves(attacker, move);
  if (fixedDamage) {
    if (attacker.hasAbility('Parental Bond')) {
      result.damage = [fixedDamage, fixedDamage];
      desc.attackerAbility = attacker.ability;
    } else {
      result.damage = fixedDamage;
    }
    return result;
  }

  if (move.named('Final Gambit')) {
    result.damage = attacker.curHP();
    return result;
  }

  // OHG §4 "Fixed damage": Super Fang, Nature's Madness and Ruination take ½ of the target's HP.
  if (move.named('Nature\'s Madness', 'Super Fang', 'Ruination')) {
    result.damage = Math.max(1, Math.floor(defender.curHP() / 2));
    return result;
  }

  if (move.named('Endeavor')) {
    result.damage = Math.max(0, defender.curHP() - attacker.curHP());
    return result;
  }

  if (move.named('Spectral Thief')) {
    let stat: StatID;
    for (stat in defender.boosts) {
      if (defender.boosts[stat] > 0) {
        attacker.boosts[stat] +=
          attacker.hasAbility('Contrary') ? -defender.boosts[stat] : defender.boosts[stat];
        if (attacker.boosts[stat] > 6) attacker.boosts[stat] = 6;
        if (attacker.boosts[stat] < -6) attacker.boosts[stat] = -6;
        attacker.stats[stat] = getModifiedStat(attacker.rawStats[stat], attacker.boosts[stat]);
        defender.boosts[stat] = 0;
        defender.stats[stat] = defender.rawStats[stat];
      }
    }
  }

  if (move.hits > 1) {
    desc.hits = move.hits;
  }

  // #endregion
  // #region Base Power

  const basePower = calculateBasePowerOHG(gen, attacker, defender, move, field, hasAteAbilityTypeChange, desc);
  if (basePower === 0) {
    return result;
  }

  // #endregion

  const attack = calculateAttackOHG(gen, attacker, defender, move, field, desc, isCritical);
  const defense = calculateDefenseOHG(gen, attacker, defender, move, field, desc, isCritical);
  const hitsPhysical = move.overrideDefensiveStat === 'def' || move.category === 'Physical';
  const defenseStat = hitsPhysical ? 'def' : 'spd';

  // #region Damage

  const baseDamage = calculateBaseDamageOHG(
    gen, attacker, defender, basePower, attack, defense, move, field, desc, isCritical
  );

  if ((attacker.hasAbility('Triage') && move.drain) ||
      (attacker.hasAbility('Gale Wings') &&
       move.hasType('Flying') &&
       attacker.curHP() === attacker.maxHP())) {
    move.priority = 1;
    desc.attackerAbility = attacker.ability;
  }

  if (hasTerrainSeed(defender) &&
    field.hasTerrain(defender.item!.substring(0, defender.item!.indexOf(' ')) as Terrain) &&
    SEED_BOOSTED_STAT[defender.item!] === defenseStat) {
    desc.defenderItem = defender.item;
  }

  const stabMod = getStabMod(attacker, move, desc);

  // OHG §1 step 11: burn halves physical damage unless Guts, Facade or (OHG §11) Quick Feet.
  const applyBurn =
    attacker.hasStatus('brn') &&
    move.category === 'Physical' &&
    !attacker.hasAbility('Guts', 'Quick Feet') &&
    !move.named('Facade');
  desc.isBurned = applyBurn;
  const finalMods = calculateFinalModsOHG(gen, attacker, defender, move, field, desc, isCritical, typeEffectiveness);

  const finalMod = chainMods(finalMods, 41, 131072);

  const isSpread = field.gameType !== 'Singles' && !field.isSpreadSingle &&
     ['allAdjacent', 'allAdjacentFoes'].includes(move.target);

  let childDamage: number[] | undefined;
  if (attacker.hasAbility('Parental Bond') && move.hits === 1 && !isSpread) {
    const child = attacker.clone();
    child.ability = 'Parental Bond (Child)';
    checkMultihitBoost(gen, child, defender, move, field, desc);
    childDamage = calculateOHG(gen, child, defender, move, field).damage as number[];
    desc.attackerAbility = attacker.ability;
  }

  const damage = [];
  for (let i = 0; i < 16; i++) {
    damage[i] = getFinalDamage(baseDamage, i, typeFactors, applyBurn, stabMod, finalMod);
  }
  result.damage = childDamage ? [damage, childDamage] : damage;

  if (move.timesUsed > 1 || move.hits > 1) {
    const origDefBoost = desc.defenseBoost;
    const origAtkBoost = desc.attackBoost;

    const numAttacks = move.timesUsed > 1 ? move.timesUsed : move.hits;
    if (move.timesUsed > 1) desc.moveTurns = `over ${move.timesUsed} turns`;
    let usedItems = [false, false];
    const damageMatrix = [damage];
    for (let times = 1; times < numAttacks; times++) {
      usedItems = checkMultihitBoost(gen, attacker, defender, move,
        field, desc, usedItems[0], usedItems[1]);
      const newAttack = calculateAttackOHG(gen, attacker, defender, move, field, desc, isCritical);
      const newDefense = calculateDefenseOHG(gen, attacker, defender, move, field, desc, isCritical);
      hasAteAbilityTypeChange = hasAteAbilityTypeChange &&
        (attacker.hasAbility('Normalize') || !!(attacker.ability && ATE_ABILITIES[attacker.ability]));

      const newBasePower = calculateBasePowerOHG(
        gen, attacker, defender, move, field, hasAteAbilityTypeChange, desc, times + 1
      );
      const newBaseDamage = calculateBaseDamageOHG(
        gen, attacker, defender, newBasePower, newAttack, newDefense, move, field, desc, isCritical
      );
      const newFinalMods = calculateFinalModsOHG(
        gen, attacker, defender, move, field, desc, isCritical, typeEffectiveness, times
      );
      const newFinalMod = chainMods(newFinalMods, 41, 131072);

      const damageArray = [];
      for (let i = 0; i < 16; i++) {
        damageArray[i] = getFinalDamage(newBaseDamage, i, typeFactors, applyBurn, stabMod, newFinalMod);
      }
      damageMatrix[times] = damageArray;
    }
    result.damage = damageMatrix;
    desc.defenseBoost = origDefBoost;
    desc.attackBoost = origAtkBoost;
  }

  // #endregion

  return result;
}

export function calculateBasePowerOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  hasAteAbilityTypeChange: boolean,
  desc: RawDesc,
  hit = 1,
) {
  const turnOrder = attacker.stats.spe > defender.stats.spe ? 'first' : 'last';

  let basePower: number;

  switch (move.name) {
  case 'Payback':
    basePower = move.bp * (turnOrder === 'last' ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Bolt Beak':
  case 'Fishious Rend':
    basePower = move.bp * (turnOrder !== 'last' ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Pursuit': {
    const switching = field.defenderSide.isSwitching === 'out';
    basePower = move.bp * (switching ? 2 : 1);
    if (switching) desc.isSwitching = 'out';
    desc.moveBP = basePower;
    break;
  }
  case 'Electro Ball': {
    const r = Math.floor(attacker.stats.spe / defender.stats.spe);
    basePower = r >= 4 ? 150 : r >= 3 ? 120 : r >= 2 ? 80 : r >= 1 ? 60 : 40;
    if (defender.stats.spe === 0) basePower = 40;
    desc.moveBP = basePower;
    break;
  }
  case 'Gyro Ball':
    basePower = Math.min(150, Math.floor((25 * defender.stats.spe) / attacker.stats.spe) + 1);
    if (attacker.stats.spe === 0) basePower = 1;
    desc.moveBP = basePower;
    break;
  case 'Punishment':
    basePower = Math.min(200, 60 + 20 * countBoosts(defender.boosts));
    desc.moveBP = basePower;
    break;
  case 'Sonic Boom':
  case 'Dragon Rage':
    // OHG (emulator-verified, damage_calc_parity.md "fixed"): no fixed-damage handler; the damage routine
    // reads power 1 from the move data, so these deal 1–3 damage (STAB, type, crit and so on still apply).
    basePower = 1;
    desc.moveBP = basePower;
    break;
  case 'Low Kick':
  case 'Grass Knot': {
    // OHG (damage_calc_data.md §1, VERIFIED): battle weight is never filled in, so it is always 0.1 kg → 20.
    const w = getWeight(defender, desc, 'defender');
    basePower = w >= 200 ? 120 : w >= 100 ? 100 : w >= 50 ? 80 : w >= 25 ? 60 : w >= 10 ? 40 : 20;
    desc.moveBP = basePower;
    break;
  }
  case 'Hex':
  case 'Infernal Parade':
    basePower = move.bp * (defender.status || defender.hasAbility('Comatose') ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Barb Barrage':
    basePower = move.bp * (defender.hasStatus('psn', 'tox') ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Heavy Slam':
  case 'Heat Crash': {
    const wr = getWeight(attacker, desc, 'attacker') / getWeight(defender, desc, 'defender');
    basePower = wr >= 5 ? 120 : wr >= 4 ? 100 : wr >= 3 ? 80 : wr >= 2 ? 60 : 40;
    desc.moveBP = basePower;
    break;
  }
  case 'Stored Power':
  case 'Power Trip':
    basePower = 20 + 20 * countBoosts(attacker.boosts);
    desc.moveBP = basePower;
    break;
  case 'Acrobatics':
    basePower = move.bp * (attacker.hasItem('Flying Gem') ||
        (!attacker.item ||
          (isQPActive(attacker, field) && attacker.hasItem('Booster Energy'))) ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Assurance':
    basePower = move.bp * (defender.hasAbility('Parental Bond (Child)') ? 2 : 1);
    break;
  case 'Wake-Up Slap':
    basePower = move.bp * (defender.hasStatus('slp') || defender.hasAbility('Comatose') ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Smelling Salts':
    basePower = move.bp * (defender.hasStatus('par') ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Weather Ball': {
    const isStrongWinds = field.hasWeather('Strong Winds');
    const isMegaSol = attacker.hasAbility('Mega Sol');
    basePower = move.bp * ((field.weather && !isStrongWinds) || isMegaSol ? 2 : 1);
    if (field.hasWeather('Sun', 'Harsh Sunshine', 'Rain', 'Heavy Rain') &&
      attacker.hasItem('Utility Umbrella') && !isMegaSol) basePower = move.bp;
    desc.moveBP = basePower;
    break;
  }
  case 'Terrain Pulse':
    basePower = move.bp * (isGrounded(attacker, field) && field.terrain ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Rising Voltage':
    basePower = move.bp * ((isGrounded(defender, field) && field.hasTerrain('Electric')) ? 2 : 1);
    desc.moveBP = basePower;
    break;
  case 'Psyblade':
    basePower = move.bp * (field.hasTerrain('Electric') ? 1.5 : 1);
    if (field.hasTerrain('Electric')) {
      desc.moveBP = basePower;
      desc.terrain = field.terrain;
    }
    break;
  case 'Fling':
    basePower = getFlingPower(attacker.item);
    desc.moveBP = basePower;
    desc.attackerItem = attacker.item;
    break;
  case 'Dragon Energy':
  case 'Eruption':
  case 'Water Spout':
    basePower = Math.max(1, Math.floor((150 * attacker.curHP()) / attacker.maxHP()));
    desc.moveBP = basePower;
    break;
  case 'Flail':
  case 'Reversal': {
    const p = Math.floor((48 * attacker.curHP()) / attacker.maxHP());
    basePower = p <= 1 ? 200 : p <= 4 ? 150 : p <= 9 ? 100 : p <= 16 ? 80 : p <= 32 ? 40 : 20;
    desc.moveBP = basePower;
    break;
  }
  case 'Return':
  case 'Pika Papow':
  case 'Veevee Volley':
    // OHG §4: friendship based, minimum 1 (Gen 5+ formula friendship / 2.5).
    basePower = Math.max(1, Math.floor((attacker.friendship * 10) / 25));
    desc.moveBP = basePower;
    break;
  case 'Frustration':
    basePower = Math.max(1, Math.floor(((255 - attacker.friendship) * 10) / 25));
    desc.moveBP = basePower;
    break;
  case 'Nature Power':
    move.category = 'Special';
    move.secondaries = true;
    if (attacker.hasAbility('Prankster') && defender.types.includes('Dark')) {
      basePower = 0;
      desc.moveName = 'Nature Power';
      desc.attackerAbility = 'Prankster';
      break;
    }
    switch (field.terrain) {
    case 'Electric':
      basePower = 90;
      desc.moveName = 'Thunderbolt';
      break;
    case 'Grassy':
      basePower = 90;
      desc.moveName = 'Energy Ball';
      break;
    case 'Misty':
      basePower = 95;
      desc.moveName = 'Moonblast';
      break;
    case 'Psychic':
      if (attacker.hasAbility('Prankster') && isGrounded(defender, field)) {
        basePower = 0;
        desc.attackerAbility = 'Prankster';
      } else {
        basePower = 90;
        desc.moveName = 'Psychic';
      }
      break;
    default:
      basePower = 80;
      desc.moveName = 'Tri Attack';
    }
    break;
  case 'Water Shuriken':
    // OHG §6: Battle Bond's handler rewrites Water Shuriken's power to 20.
    basePower = attacker.hasAbility('Battle Bond') ? 20 : move.bp;
    desc.moveBP = basePower;
    break;
  case 'Triple Axel':
    basePower = hit * 20;
    desc.moveBP = move.hits === 2 ? 60 : move.hits === 3 ? 120 : 20;
    break;
  case 'Triple Kick':
    basePower = hit * 10;
    desc.moveBP = move.hits === 2 ? 30 : move.hits === 3 ? 60 : 10;
    break;
  case 'Crush Grip':
  case 'Wring Out':
    basePower = 100 * Math.floor((defender.curHP() * 4096) / defender.maxHP());
    basePower = Math.floor(Math.floor((120 * basePower + 2048 - 1) / 4096) / 100) || 1;
    desc.moveBP = basePower;
    break;
  case 'Hard Press':
    basePower = 100 * Math.floor((defender.curHP() * 4096) / defender.maxHP());
    basePower = Math.floor(Math.floor((100 * basePower + 2048 - 1) / 4096) / 100) || 1;
    desc.moveBP = basePower;
    break;
  default:
    basePower = move.bp;
  }
  if (basePower === 0) {
    return 0;
  }
  const bpMods = calculateBPModsOHG(
    gen, attacker, defender, move, field, desc, basePower, hasAteAbilityTypeChange, turnOrder, hit
  );
  basePower = OF16(Math.max(1, pokeRound((basePower * chainMods(bpMods, 41, 2097152)) / 4096)));
  return basePower;
}

/** Items a Pokémon cannot lose to Knock Off, so Knock Off gets no ×1.5 (species by national-dex id). */
function keepsItem(defender: Pokemon, item: string) {
  return (defender.isSpecies(493) && item.includes('Plate')) ||
    (defender.isSpecies(487) && item.includes('Griseous')) ||
    (defender.isSpecies(483) && item === 'Adamant Crystal') ||
    (defender.isSpecies(484) && item === 'Lustrous Globe') ||
    (defender.isSpecies(649) && item.endsWith(' Drive')) ||
    (defender.isSpecies(773) && item.endsWith(' Memory')) ||
    (defender.isSpecies(382) && item === 'Blue Orb') ||
    (defender.isSpecies(383) && item === 'Red Orb') ||
    (defender.isSpecies(888) && item === 'Rusted Sword') ||
    (defender.isSpecies(889) && item === 'Rusted Shield') ||
    (defender.isSpecies(1017) && item.endsWith(' Mask')) ||
    // OHG §6: held-item forms (INFERRED to be protected like Mega Stones).
    (defender.isSpecies(6) && item === 'Charizardite') ||
    (defender.isSpecies(150) && item === 'Steel Armor') ||
    (defender.isSpecies(658) && item === 'Ninja Scroll');
}

export function calculateBPModsOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  basePower: number,
  hasAteAbilityTypeChange: boolean,
  turnOrder: string,
  hit: number
) {
  const bpMods = [];

  const defenderItem = (defender.item && defender.item !== '') ? defender.item : defender.disabledItem;
  let resistedKnockOffDamage =
    !defenderItem || (isQPActive(defender, field) && defenderItem === 'Booster Energy') ||
    keepsItem(defender, defenderItem);
  if (!resistedKnockOffDamage && hit > 1 && !defender.hasAbility('Sticky Hold')) {
    resistedKnockOffDamage = true;
  }

  if ((move.named('Facade') && attacker.hasStatus('brn', 'par', 'psn', 'tox')) ||
    (move.named('Brine') && defender.curHP() <= defender.maxHP() / 2) ||
    (move.named('Venoshock') && defender.hasStatus('psn', 'tox')) ||
    (move.named('Lash Out') && (countBoosts(attacker.boosts) < 0))
  ) {
    bpMods.push(8192);
    desc.moveBP = basePower * 2;
  } else if (
    move.named('Expanding Force') && isGrounded(attacker, field) && field.hasTerrain('Psychic')
  ) {
    move.target = 'allAdjacentFoes';
    bpMods.push(6144);
    desc.moveBP = basePower * 1.5;
  } else if ((move.named('Knock Off') && !resistedKnockOffDamage) ||
    (move.named('Misty Explosion') && isGrounded(attacker, field) && field.hasTerrain('Misty')) ||
    (move.named('Grav Apple') && field.isGravity)
  ) {
    bpMods.push(6144);
    desc.moveBP = basePower * 1.5;
  } else if (move.named('Solar Beam', 'Solar Blade') &&
      field.hasWeather('Rain', 'Heavy Rain', 'Sand', 'Hail')) {
    bpMods.push(2048);
    desc.moveBP = basePower / 2;
    desc.weather = field.weather;
  } else if (move.named('Collision Course', 'Electro Drift')) {
    const isGhostRevealed =
      attacker.hasAbility('Scrappy') || attacker.hasAbility('Mind\'s Eye') ||
      field.defenderSide.isForesight;
    const isRingTarget = defender.hasItem('Ring Target') && !defender.hasAbility('Klutz');
    const types = defender.types;
    const e1 = getMoveEffectiveness(gen, move, types[0], isGhostRevealed, field.isGravity, isRingTarget);
    const e2 = types[1] ? getMoveEffectiveness(gen, move, types[1], isGhostRevealed, field.isGravity, isRingTarget) : 1;
    if (e1 * e2 >= 2) {
      bpMods.push(5461);
      desc.moveBP = basePower * (5461 / 4096);
    }
  }

  if (field.attackerSide.isHelpingHand) {
    bpMods.push(6144);
    desc.isHelpingHand = true;
  }

  // Field effects. OHG §1 Terrain: ×1.3 (Gen 8+ value), VERIFIED.
  const terrainMultiplier = 5325;
  if (isGrounded(attacker, field)) {
    if ((field.hasTerrain('Electric') && move.hasType('Electric')) ||
        (field.hasTerrain('Grassy') && move.hasType('Grass')) ||
        (field.hasTerrain('Psychic') && move.hasType('Psychic'))
    ) {
      bpMods.push(terrainMultiplier);
      desc.terrain = field.terrain;
    }
  }
  if (isGrounded(defender, field)) {
    // OHG §1 Terrain: Grassy Terrain halves Earthquake (move 89) only.
    if ((field.hasTerrain('Misty') && move.hasType('Dragon')) ||
        (field.hasTerrain('Grassy') && move.named('Earthquake'))
    ) {
      bpMods.push(2048);
      desc.terrain = field.terrain;
    }
  }

  // Abilities

  if ((attacker.hasAbility('Technician') && basePower <= 60) ||
    (attacker.hasAbility('Flare Boost') &&
      attacker.hasStatus('brn') && move.category === 'Special') ||
    (attacker.hasAbility('Toxic Boost') &&
      attacker.hasStatus('psn', 'tox') && move.category === 'Physical') ||
    // OHG §18: Mega Launcher boosts a fixed move list.
    (attacker.hasAbility('Mega Launcher') && move.named(...MEGA_LAUNCHER_MOVES)) ||
    (attacker.hasAbility('Strong Jaw') && move.flags.bite) ||
    (attacker.hasAbility('Steely Spirit') && move.hasType('Steel')) ||
    (attacker.hasAbility('Sharpness') && move.flags.slicing)
  ) {
    bpMods.push(6144);
    desc.attackerAbility = attacker.ability;
  }

  if (field.attackerSide.isCharge && move.hasType('Electric')) {
    bpMods.push(8192);
    desc.isCharge = true;
  }

  const aura = `${move.type} Aura`;
  const isAttackerAura = attacker.hasAbility(aura);
  const isDefenderAura = defender.hasAbility(aura);
  const isUserAuraBreak = attacker.hasAbility('Aura Break') || defender.hasAbility('Aura Break');
  const isFieldFairyAura = field.isFairyAura && move.type === 'Fairy';
  const isFieldDarkAura = field.isDarkAura && move.type === 'Dark';
  const auraActive = isAttackerAura || isDefenderAura || isFieldFairyAura || isFieldDarkAura;
  const auraBreak = field.isAuraBreak || isUserAuraBreak;
  if (auraActive) {
    if (auraBreak) {
      bpMods.push(3072);
      desc.attackerAbility = attacker.ability;
      desc.defenderAbility = defender.ability;
    } else {
      bpMods.push(5448);
      if (isAttackerAura) desc.attackerAbility = attacker.ability;
      if (isDefenderAura) desc.defenderAbility = defender.ability;
    }
  }

  if (
    (attacker.hasAbility('Sheer Force') && move.secondaries) ||
    (attacker.hasAbility('Sand Force') &&
      field.hasWeather('Sand') && move.hasType('Rock', 'Ground', 'Steel')) ||
    (attacker.hasAbility('Analytic') &&
      (turnOrder !== 'first' || field.defenderSide.isSwitching === 'out' || attacker.abilityOn)) ||
    // OHG §10: Tough Claws ×1.3 on every move the holder uses (no contact check).
    attacker.hasAbility('Tough Claws') ||
    (attacker.hasAbility('Punk Rock') && move.flags.sound) ||
    // OHG §9: Iron Fist is ×1.3.
    (attacker.hasAbility('Iron Fist') && move.flags.punch) ||
    // OHG §15: Telepathy, Psychic moves on Psychic Terrain (terrain id INFERRED).
    (attacker.hasAbility('Telepathy') && move.hasType('Psychic') && field.hasTerrain('Psychic'))
  ) {
    bpMods.push(5325);
    desc.attackerAbility = attacker.ability;
  }

  if (field.attackerSide.isBattery && move.category === 'Special') {
    bpMods.push(5325);
    desc.isBattery = true;
  }

  if (field.attackerSide.isPowerSpot) {
    bpMods.push(5325);
    desc.isPowerSpot = true;
  }

  if (attacker.hasAbility('Rivalry') &&
    ['M', 'F'].includes(attacker.gender) && ['M', 'F'].includes(defender.gender)) {
    if (attacker.gender === defender.gender) {
      bpMods.push(5120);
      desc.rivalry = 'buffed';
    } else {
      bpMods.push(3072);
      desc.rivalry = 'nerfed';
    }
    desc.attackerAbility = attacker.ability;
  }

  if (hasAteAbilityTypeChange) {
    bpMods.push(4915);
  }

  if (attacker.hasAbility('Reckless') && (move.recoil || move.hasCrashDamage)) {
    bpMods.push(4915);
    desc.attackerAbility = attacker.ability;
  }

  if (defender.hasAbility('Dry Skin') && move.hasType('Fire')) {
    bpMods.push(5120);
    desc.defenderAbility = defender.ability;
  }

  // OHG §8: Damp lowers every Fire move on the field ×0.8 (0xCCD) and powers the holder's Water moves ×1.2.
  if (move.hasType('Fire') && (attacker.hasAbility('Damp') || defender.hasAbility('Damp'))) {
    bpMods.push(3277);
    if (attacker.hasAbility('Damp')) desc.attackerAbility = attacker.ability;
    else desc.defenderAbility = defender.ability;
  } else if (move.hasType('Water') && attacker.hasAbility('Damp')) {
    bpMods.push(4915);
    desc.attackerAbility = attacker.ability;
  }

  if (attacker.hasAbility('Supreme Overlord') && attacker.alliesFainted) {
    const powMod = [4096, 4506, 4915, 5325, 5734, 6144];
    bpMods.push(powMod[Math.min(5, attacker.alliesFainted)]);
    desc.attackerAbility = attacker.ability;
    desc.alliesFainted = attacker.alliesFainted;
  }

  // Items

  if (attacker.hasItem(`${move.type} Gem`)) {
    bpMods.push(5325); // OHG §23: Gems ×1.3
    desc.attackerItem = attacker.item;
  } else if (
    (attacker.isSpecies(483) && attacker.hasItem('Adamant Orb', 'Adamant Crystal') &&
     move.hasType('Steel', 'Dragon')) ||
    (attacker.isSpecies(484) && attacker.hasItem('Lustrous Orb', 'Lustrous Globe') &&
     move.hasType('Water', 'Dragon')) ||
    (attacker.isSpecies(487) && attacker.hasItem('Griseous Orb', 'Griseous Core') &&
     move.hasType('Ghost', 'Dragon')) ||
    // OHG §20: Soul Dew is a stat boost here, not ×1.2 power.
    (attacker.item && move.hasType(getItemBoostType(attacker.item))) ||
    (attacker.isSpecies(1017) && attacker.hasItem('Cornerstone Mask', 'Hearthflame Mask', 'Wellspring Mask'))
  ) {
    bpMods.push(4915);
    desc.attackerItem = attacker.item;
  } else if (attacker.hasItem('Punching Glove') && move.flags.punch) {
    bpMods.push(4506);
  }
  return bpMods;
}

export function calculateAttackOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  isCritical = false
) {
  let attack: number;
  const attackSource = move.named('Foul Play') ? defender : attacker;
  const attackStat =
    move.named('Body Press')
      ? (field.isWonderRoom ? 'spd' : 'def')
      : (move.category === 'Special' ? 'spa' : 'atk');
  desc.attackEVs =
    move.named('Foul Play')
      ? getStatDescriptionText(gen, attackSource, attackStat, field.defenderSide.isPowerTrick)
      : getStatDescriptionText(gen, attackSource, attackStat, field.attackerSide.isPowerTrick, field.isWonderRoom);
  if (field.attackerSide.isPowerTrick) {
    if ((move.category === 'Physical' && !move.named('Foul Play')) || move.named('Body Press')) {
      desc.isPowerTrickAttacker = true;
    }
  }
  const boosts = attackSource.boosts[attackStat];
  if (boosts === 0 || (isCritical && boosts < 0)) {
    attack = attackSource.rawStats[attackStat];
  } else if (defender.hasAbility('Unaware')) {
    attack = attackSource.rawStats[attackStat];
    desc.defenderAbility = defender.ability;
  } else {
    attack = getModifiedStat(attackSource.rawStats[attackStat], boosts);
    desc.attackBoost = boosts;
  }

  // Hustle is applied directly to the stat (OHG §2, VERIFIED).
  if (attacker.hasAbility('Hustle') && move.category === 'Physical') {
    attack = pokeRound((attack * 3) / 2);
    desc.attackerAbility = attacker.ability;
  }
  const atMods = calculateAtModsOHG(gen, attacker, defender, move, field, desc);
  attack = OF16(Math.max(1, pokeRound((attack * chainMods(atMods, 410, 131072)) / 4096)));
  return attack;
}

export function calculateAtModsOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc
) {
  const atMods = [];
  const inSun = field.hasWeather('Sun', 'Harsh Sunshine');

  if ((attacker.hasAbility('Slow Start') && attacker.abilityOn && move.category === 'Physical') ||
      (attacker.hasAbility('Defeatist') && attacker.curHP() <= attacker.maxHP() / 2)
  ) {
    atMods.push(2048);
    desc.attackerAbility = attacker.ability;
  } else if (
    (attacker.hasAbility('Solar Power') && inSun && move.category === 'Special') ||
    (attacker.isSpecies(421) && attacker.hasAbility('Flower Gift') && inSun && move.category === 'Physical') ||
    // OHG §13: Leaf Guard raises Sp. Atk ×1.5 in sun.
    (attacker.hasAbility('Leaf Guard') && inSun && move.category === 'Special')
  ) {
    atMods.push(6144);
    desc.attackerAbility = attacker.ability;
    desc.weather = field.weather;
  } else if (attacker.hasAbility('Gorilla Tactics') && move.category === 'Physical') {
    atMods.push(6144);
    desc.attackerAbility = attacker.ability;
  } else if (
    (attacker.hasAbility('Guts') && attacker.status && move.category === 'Physical') ||
    // OHG §11: Quick Feet raises physical Attack ×1.5 while statused.
    (attacker.hasAbility('Quick Feet') && attacker.status && move.category === 'Physical') ||
    // OHG §4: pinch abilities at HP ≤ ½.
    (inPinch(attacker) &&
      ((attacker.hasAbility('Overgrow') && move.hasType('Grass')) ||
       (attacker.hasAbility('Blaze') && move.hasType('Fire')) ||
       (attacker.hasAbility('Torrent') && move.hasType('Water')) ||
       (attacker.hasAbility('Swarm') && move.hasType('Bug')))) ||
    (move.category === 'Special' && attacker.abilityOn && attacker.hasAbility('Plus', 'Minus'))
  ) {
    atMods.push(6144);
    desc.attackerAbility = attacker.ability;
  } else if (
    (attacker.hasAbility('Steelworker') && move.hasType('Steel')) ||
    (attacker.hasAbility('Dragon\'s Maw') && move.hasType('Dragon')) ||
    (attacker.hasAbility('Rocky Payload') && move.hasType('Rock')) ||
    // OHG §19: Flame Mane, Fire ×1.5 to the attacking stat.
    (attacker.hasAbility('Flame Mane') && move.hasType('Fire'))
  ) {
    atMods.push(6144);
    desc.attackerAbility = attacker.ability;
  } else if (
    (attacker.hasAbility('Transistor') && move.hasType('Electric')) ||
    // OHG §14: Cursed Body, Ghost moves ×1.3 (0x14CD).
    (attacker.hasAbility('Cursed Body') && move.hasType('Ghost')) ||
    // OHG §19: Mega Claws, physical ×1.3; Desert Hawk, physical ×1.3 in sand.
    (attacker.hasAbility('Mega Claws') && move.category === 'Physical') ||
    (attacker.hasAbility('Desert Hawk') && move.category === 'Physical' && field.hasWeather('Sand'))
  ) {
    atMods.push(5325);
    desc.attackerAbility = attacker.ability;
    if (attacker.hasAbility('Desert Hawk')) desc.weather = field.weather;
  } else if (attacker.hasAbility('Stakeout') && attacker.abilityOn) {
    atMods.push(8192);
    desc.attackerAbility = attacker.ability;
  } else if (
    (attacker.hasAbility('Water Bubble') && move.hasType('Water')) ||
    (attacker.hasAbility('Huge Power', 'Pure Power') && move.category === 'Physical')
  ) {
    atMods.push(8192);
    desc.attackerAbility = attacker.ability;
  }

  if (field.attackerSide.isFlowerGift && !attacker.hasAbility('Flower Gift') && inSun &&
    move.category === 'Physical') {
    atMods.push(6144);
    desc.weather = field.weather;
    desc.isFlowerGiftAttacker = true;
  }

  if (field.attackerSide.isSteelySpirit && move.hasType('Steel')) {
    atMods.push(6144);
    desc.isSteelySpiritAttacker = true;
  }

  if ((defender.hasAbility('Thick Fat') && move.hasType('Fire', 'Ice')) ||
      (defender.hasAbility('Water Bubble') && move.hasType('Fire')) ||
      (defender.hasAbility('Purifying Salt') && move.hasType('Ghost')) ||
      (defender.hasAbility('Heatproof') && move.hasType('Fire'))) {
    atMods.push(2048);
    desc.defenderAbility = defender.ability;
  }

  const isTabletsOfRuinActive = (defender.hasAbility('Tablets of Ruin') || field.isTabletsOfRuin) &&
    !attacker.hasAbility('Tablets of Ruin');
  const isVesselOfRuinActive = (defender.hasAbility('Vessel of Ruin') || field.isVesselOfRuin) &&
    !attacker.hasAbility('Vessel of Ruin');
  if ((isTabletsOfRuinActive && move.category === 'Physical') ||
    (isVesselOfRuinActive && move.category === 'Special')) {
    if (defender.hasAbility('Tablets of Ruin') || defender.hasAbility('Vessel of Ruin')) {
      desc.defenderAbility = defender.ability;
    } else {
      desc[move.category === 'Special' ? 'isVesselOfRuin' : 'isTabletsOfRuin'] = true;
    }
    atMods.push(3072);
  }

  if (isQPActive(attacker, field)) {
    if ((move.category === 'Physical' && getQPBoostedStat(attacker) === 'atk') ||
      (move.category === 'Special' && getQPBoostedStat(attacker) === 'spa')) {
      atMods.push(5325);
      desc.attackerAbility = attacker.ability;
    }
  }

  if ((attacker.hasAbility('Hadron Engine') && move.category === 'Special' && field.hasTerrain('Electric')) ||
    (attacker.hasAbility('Orichalcum Pulse') && move.category === 'Physical' && inSun &&
      !attacker.hasItem('Utility Umbrella'))) {
    atMods.push(5461);
    desc.attackerAbility = attacker.ability;
  }

  if ((attacker.hasItem('Thick Club') && attacker.isSpecies(104, 105) && move.category === 'Physical') ||
      (attacker.hasItem('Deep Sea Tooth') && attacker.isSpecies(366) && move.category === 'Special') ||
      (attacker.hasItem('Light Ball') && attacker.isSpecies(25))
  ) {
    atMods.push(8192);
    desc.attackerItem = attacker.item;
  } else if (
    (attacker.hasItem('Choice Band') && move.category === 'Physical') ||
    (attacker.hasItem('Choice Specs') && move.category === 'Special') ||
    // OHG §20: Soul Dew, Sp. Atk ×1.5 for Latias/Latios.
    (attacker.hasItem('Soul Dew') && attacker.isSpecies(380, 381) && move.category === 'Special')
  ) {
    atMods.push(6144);
    desc.attackerItem = attacker.item;
  }
  return atMods;
}

export function calculateDefenseOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  isCritical = false
) {
  let defense: number;
  const hitsPhysical = move.overrideDefensiveStat === 'def' || move.category === 'Physical';
  const defenseStat = hitsPhysical ? 'def' : 'spd';
  desc.defenseEVs = getStatDescriptionText(
    gen, defender, defenseStat, field.defenderSide.isPowerTrick, field.isWonderRoom
  );
  if (field.defenderSide.isPowerTrick && (field.isWonderRoom !== hitsPhysical)) {
    desc.isPowerTrickDefender = true;
  }

  const boosts = defender.boosts[defenseStat];
  if (boosts === 0 || (isCritical && boosts > 0) || move.ignoreDefensive) {
    defense = defender.rawStats[defenseStat];
  } else if (attacker.hasAbility('Unaware')) {
    defense = defender.rawStats[defenseStat];
    desc.attackerAbility = attacker.ability;
  } else {
    defense = getModifiedStat(defender.rawStats[defenseStat], boosts);
    desc.defenseBoost = boosts;
  }

  // OHG §1 Defense / §21: sand gives Rock SpD ×1.5; weather 4 (Hail) gives Ice Def ×1.5. Both direct.
  if (field.hasWeather('Sand') && defender.hasType('Rock') && !hitsPhysical) {
    defense = pokeRound((defense * 3) / 2);
    desc.weather = field.weather;
  }
  if (field.hasWeather('Hail') && defender.hasType('Ice') && hitsPhysical) {
    defense = pokeRound((defense * 3) / 2);
    desc.weather = field.weather;
  }

  const dfMods = calculateDfModsOHG(gen, attacker, defender, move, field, desc, isCritical, hitsPhysical);

  return OF16(Math.max(1, pokeRound((defense * chainMods(dfMods, 410, 131072)) / 4096)));
}

export function calculateDfModsOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  isCritical = false,
  hitsPhysical = false
) {
  const dfMods = [];
  const inSun = field.hasWeather('Sun', 'Harsh Sunshine');
  // OHG §7: Marvel Scale raises Def and SpD while statused (no category check).
  if (defender.hasAbility('Marvel Scale') && defender.status) {
    dfMods.push(6144);
    desc.defenderAbility = defender.ability;
  } else if (defender.isSpecies(421) && defender.hasAbility('Flower Gift') && inSun && !hitsPhysical) {
    dfMods.push(6144);
    desc.defenderAbility = defender.ability;
    desc.weather = field.weather;
  } else if (field.defenderSide.isFlowerGift && inSun && !hitsPhysical) {
    dfMods.push(6144);
    desc.weather = field.weather;
    desc.isFlowerGiftDefender = true;
  } else if (defender.hasAbility('Grass Pelt') && field.hasTerrain('Grassy') && hitsPhysical) {
    dfMods.push(6144);
    desc.defenderAbility = defender.ability;
  } else if (defender.hasAbility('Fur Coat') && hitsPhysical) {
    dfMods.push(8192);
    desc.defenderAbility = defender.ability;
  } else if (
    // OHG §13: Leaf Guard, Def ×1.5 against physical moves in sun.
    (defender.hasAbility('Leaf Guard') && inSun && hitsPhysical) ||
    // OHG §16: Wonder Skin, SpD ×1.5 against special moves.
    (defender.hasAbility('Wonder Skin') && !hitsPhysical)
  ) {
    dfMods.push(6144);
    desc.defenderAbility = defender.ability;
    if (defender.hasAbility('Leaf Guard')) desc.weather = field.weather;
  } else if (defender.hasAbility('Limber', 'Shell Armor') && hitsPhysical) {
    // OHG §6: Limber and Shell Armor, Def ×1.25 against physical moves.
    dfMods.push(5120);
    desc.defenderAbility = defender.ability;
  }

  const isSwordOfRuinActive = (attacker.hasAbility('Sword of Ruin') || field.isSwordOfRuin) &&
    !defender.hasAbility('Sword of Ruin');
  const isBeadsOfRuinActive = (attacker.hasAbility('Beads of Ruin') || field.isBeadsOfRuin) &&
    !defender.hasAbility('Beads of Ruin');
  if ((isSwordOfRuinActive && hitsPhysical) || (isBeadsOfRuinActive && !hitsPhysical)) {
    if (attacker.hasAbility('Sword of Ruin') || attacker.hasAbility('Beads of Ruin')) {
      desc.attackerAbility = attacker.ability;
    } else {
      desc[hitsPhysical ? 'isSwordOfRuin' : 'isBeadsOfRuin'] = true;
    }
    dfMods.push(3072);
  }

  if (isQPActive(defender, field)) {
    if ((hitsPhysical && getQPBoostedStat(defender) === 'def') ||
      (!hitsPhysical && getQPBoostedStat(defender) === 'spd')) {
      desc.defenderAbility = defender.ability;
      dfMods.push(5324);
    }
  }

  if ((defender.hasItem('Eviolite') && defender.species.nfe) ||
      (!hitsPhysical && defender.hasItem('Assault Vest'))) {
    dfMods.push(6144);
    desc.defenderItem = defender.item;
  } else if (
    (defender.hasItem('Metal Powder') && defender.isSpecies(132) && hitsPhysical) ||
    (defender.hasItem('Deep Sea Scale') && defender.isSpecies(366) && !hitsPhysical)
  ) {
    dfMods.push(8192);
    desc.defenderItem = defender.item;
  }
  // OHG §20 (hack bug, emulator-verified, work/notes/damage_calc_parity.md "souldew"): Soul Dew's Sp. Def
  // handler (event 0x77) checks the ATTACKER's id (0x0220C5C0, copied from its Sp. Atk handler; Deep Sea
  // Scale uses the defender's 0x0220C5D8). So a Latias/Latios holding it raises the TARGET's Sp. Def ×1.5
  // when it uses a special move, and a holder that is hit gets no Sp. Def boost.
  if (attacker.hasItem('Soul Dew') && attacker.isSpecies(380, 381) && move.category === 'Special') {
    dfMods.push(6144);
    desc.attackerItem = attacker.item;
  }
  return dfMods;
}

function calculateBaseDamageOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  basePower: number,
  attack: number,
  defense: number,
  move: Move,
  field: Field,
  desc: RawDesc,
  isCritical = false,
) {
  let baseDamage = getBaseDamage(attacker.level, basePower, attack, defense);
  // OHG §1 step 4: ×0.75 when the move hits more than one target. Emulator-verified: ×1 (target ratio 4096)
  // when a spread move hits a lone foe in a Double Battle (damage_calc_parity.md "doubles3").
  const isSpread = field.gameType !== 'Singles' && !field.isSpreadSingle &&
     ['allAdjacent', 'allAdjacentFoes'].includes(move.target);
  if (isSpread) {
    baseDamage = pokeRound(OF32(baseDamage * 3072) / 4096);
  }

  if (attacker.hasAbility('Parental Bond (Child)')) {
    baseDamage = pokeRound(OF32(baseDamage * 1024) / 4096);
  }

  // OHG §1 step 5 / §21: rain and sun (incl. primal) ×1.5/×0.5; Mega Sol makes the holder's moves use sun.
  const isMegaSol = attacker.hasAbility('Mega Sol');
  const sun = field.hasWeather('Sun', 'Harsh Sunshine') || isMegaSol;
  const rain = field.hasWeather('Rain', 'Heavy Rain') && !isMegaSol;
  if (sun && move.named('Hydro Steam') && !attacker.hasItem('Utility Umbrella')) {
    baseDamage = pokeRound(OF32(baseDamage * 6144) / 4096);
    if (isMegaSol) desc.attackerAbility = attacker.ability;
    else desc.weather = field.weather;
  } else if (!defender.hasItem('Utility Umbrella')) {
    if ((sun && move.hasType('Fire')) || (rain && move.hasType('Water'))) {
      baseDamage = pokeRound(OF32(baseDamage * 6144) / 4096);
      if (isMegaSol) desc.attackerAbility = attacker.ability;
      else desc.weather = field.weather;
    } else if ((sun && move.hasType('Water')) || (rain && move.hasType('Fire'))) {
      baseDamage = pokeRound(OF32(baseDamage * 2048) / 4096);
      if (isMegaSol) desc.attackerAbility = attacker.ability;
      else desc.weather = field.weather;
    }
  }

  // OHG §1 step 6 / deviation 2: ×2 (×200/100, floor) after weather, before the crit, while the
  // defender has volatile condition 0x2D (INFERRED to be Glaive Rush's after-effect).
  if (field.defenderSide.isGlaiveRushed) {
    baseDamage = Math.floor(OF32(baseDamage * 200) / 100);
    desc.isGlaiveRushed = true;
  }

  // OHG §1 step 7 / deviation 3: crit ×1.5 (×150/100, floor).
  if (isCritical) {
    baseDamage = Math.floor(OF32(baseDamage * 150) / 100);
    desc.isCritical = isCritical;
  }

  return baseDamage;
}

export function calculateFinalModsOHG(
  gen: Generation,
  attacker: Pokemon,
  defender: Pokemon,
  move: Move,
  field: Field,
  desc: RawDesc,
  isCritical = false,
  typeEffectiveness: number,
  hitCount = 0
) {
  const finalMods = [];

  // OHG §1 Screens (VERIFIED): ×0.5 singles, ×2732/4096 doubles, skipped on a crit.
  if (field.defenderSide.isReflect && move.category === 'Physical' &&
      !isCritical && !field.defenderSide.isAuroraVeil) {
    finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
    desc.isReflect = true;
  } else if (
    field.defenderSide.isLightScreen && move.category === 'Special' &&
    !isCritical && !field.defenderSide.isAuroraVeil
  ) {
    finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
    desc.isLightScreen = true;
  }
  if (field.defenderSide.isAuroraVeil && !isCritical) {
    finalMods.push(field.gameType !== 'Singles' ? 2732 : 2048);
    desc.isAuroraVeil = true;
  }

  if (attacker.hasAbility('Neuroforce') && typeEffectiveness > 1) {
    finalMods.push(5120);
    desc.attackerAbility = attacker.ability;
  } else if (attacker.hasAbility('Sniper') && isCritical) {
    finalMods.push(6144);
    desc.attackerAbility = attacker.ability;
  } else if (attacker.hasAbility('Tinted Lens') && typeEffectiveness < 1) {
    finalMods.push(8192);
    desc.attackerAbility = attacker.ability;
  }

  if (defender.hasAbility('Multiscale', 'Shadow Shield') &&
      defender.curHP() === defender.maxHP() &&
      hitCount === 0 &&
      (!field.defenderSide.isSR && (!field.defenderSide.spikes || defender.hasType('Flying')) ||
      defender.hasItem('Heavy-Duty Boots')) && !attacker.hasAbility('Parental Bond (Child)')
  ) {
    finalMods.push(2048);
    desc.defenderAbility = defender.ability;
  }

  if (defender.hasAbility('Fluffy') && move.flags.contact && !attacker.hasAbility('Long Reach')) {
    finalMods.push(2048);
    desc.defenderAbility = defender.ability;
  } else if (
    (defender.hasAbility('Punk Rock') && move.flags.sound) ||
    (defender.hasAbility('Ice Scales') && move.category === 'Special')
  ) {
    finalMods.push(2048);
    desc.defenderAbility = defender.ability;
  }

  if ((defender.hasAbility('Solid Rock', 'Filter', 'Prism Armor') && typeEffectiveness > 1) ||
    // OHG §5: Swarm also takes ×0.75 from super-effective hits.
    (defender.hasAbility('Swarm') && typeEffectiveness > 1)) {
    // OHG §19: ability #327 does NOT protect its holder. Its event-0x6D handler (0x0223A928) skips the holder
    // and gives ×0.75 to a statused ALLY in a Double Battle (emulator-verified: a paralysed holder took full
    // damage, work/notes/damage_calc_parity.md "a327"). Allies' abilities are not inputs here (caveat).
    finalMods.push(3072);
    desc.defenderAbility = defender.ability;
  }

  if (field.defenderSide.isFriendGuard) {
    finalMods.push(3072);
    desc.isFriendGuard = true;
  }

  if (defender.hasAbility('Fluffy') && move.hasType('Fire')) {
    finalMods.push(8192);
    desc.defenderAbility = defender.ability;
  }

  if (attacker.hasItem('Expert Belt') && typeEffectiveness > 1) {
    finalMods.push(4915);
    desc.attackerItem = attacker.item;
  } else if (attacker.hasItem('Life Orb')) {
    finalMods.push(5324);
    desc.attackerItem = attacker.item;
  } else if (attacker.hasItem('Metronome') && move.timesUsedWithMetronome! >= 1) {
    const timesUsedWithMetronome = Math.floor(move.timesUsedWithMetronome!);
    if (timesUsedWithMetronome <= 4) {
      finalMods.push(4096 + timesUsedWithMetronome * 819);
    } else {
      finalMods.push(8192);
    }
    desc.attackerItem = attacker.item;
  } else if (
    // OHG §3 items: Muscle Band / Wise Glasses are ×1.1 final modifiers (item param 10 → 4505).
    (attacker.hasItem('Muscle Band') && move.category === 'Physical') ||
    (attacker.hasItem('Wise Glasses') && move.category === 'Special')
  ) {
    finalMods.push(4505);
    desc.attackerItem = attacker.item;
  }

  if (move.hasType(getBerryResistType(defender.item)) &&
      (typeEffectiveness > 1 || move.hasType('Normal')) &&
      hitCount === 0 &&
      !attacker.hasAbility('Unnerve', 'As One (Glastrier)', 'As One (Spectrier)')) {
    if (defender.hasAbility('Ripen')) {
      finalMods.push(1024);
    } else {
      finalMods.push(2048);
    }
    desc.defenderItem = defender.item;
  }

  return finalMods;
}

function hasTerrainSeed(pokemon: Pokemon) {
  return pokemon.hasItem('Electric Seed', 'Misty Seed', 'Grassy Seed', 'Psychic Seed');
}
