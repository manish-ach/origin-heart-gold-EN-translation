// Player-facing caveats: every effect the engine does not model, or models from an INFERRED/UNKNOWN
// finding in work/notes/damage_calc_mechanics.md. A result that depends on one of these carries the text.

/** Moves whose damage the engine cannot work out (no number is shown). */
export const UNMODELLED_MOVES: Record<string, string> = {
  'Beat Up': 'Beat Up hits once per healthy party member; not calculated.',
  'Present': 'Present has random power (or heals); not calculated.',
  'Magnitude': 'Magnitude has random power; not calculated.',
  'Spit Up': 'Spit Up depends on Stockpile; not calculated.',
  'Natural Gift': 'Natural Gift depends on the held Berry; not calculated.',
  'Trump Card': 'Trump Card depends on remaining PP; not calculated.',
  'Counter': 'Counter returns damage taken; not calculated.',
  'Mirror Coat': 'Mirror Coat returns damage taken; not calculated.',
  'Metal Burst': 'Metal Burst returns damage taken; not calculated.',
  'Comeuppance': 'Comeuppance returns damage taken; not calculated.',
  'Bide': 'Bide returns damage taken; not calculated.',
  'Psywave': 'Psywave deals random damage; not calculated.',
  'Guillotine': 'One-hit KO move: knocks out if it hits.',
  'Horn Drill': 'One-hit KO move: knocks out if it hits.',
  'Fissure': 'One-hit KO move: knocks out if it hits.',
  'Sheer Cold': 'One-hit KO move: knocks out if it hits.',
  'Me First': 'Me First copies the target\'s move; not calculated.',
};

/** Moves calculated at their base power whose power can change in battle. */
export const CONDITIONAL_MOVES: Record<string, string> = {
  'Assurance': 'Assurance doubles if the target was already hit this turn.',
  'Revenge': 'Revenge doubles if the user was hit first this turn.',
  'Avalanche': 'Avalanche doubles if the user was hit first this turn.',
  'Stomping Tantrum': 'Stomping Tantrum doubles after a failed move.',
  'Temper Flare': 'Temper Flare doubles after a failed move.',
  'Rollout': 'Rollout grows on each consecutive turn; first turn shown.',
  'Ice Ball': 'Ice Ball grows on each consecutive turn; first turn shown.',
  'Fury Cutter': 'Fury Cutter grows on each consecutive hit; first use shown.',
  'Echoed Voice': 'Echoed Voice grows on each consecutive turn; first turn shown.',
  'Round': 'Round doubles when an ally used it first.',
  'Retaliate': 'Retaliate doubles after an ally fainted last turn.',
  'Fusion Flare': 'Fusion Flare doubles after Fusion Bolt.',
  'Fusion Bolt': 'Fusion Bolt doubles after Fusion Flare.',
  'Fire Pledge': 'Pledge moves reach 150 power when combined.',
  'Water Pledge': 'Pledge moves reach 150 power when combined.',
  'Grass Pledge': 'Pledge moves reach 150 power when combined.',
  'Fickle Beam': 'Fickle Beam sometimes doubles to 160 power.',
  'Last Respects': 'Last Respects grows with fainted party members; none assumed.',
  'Rage Fist': 'Rage Fist grows each time the user was hit; none assumed.',
  'Gust': 'Gust doubles against a flying target.',
  'Twister': 'Twister doubles against a flying target.',
  'Pursuit': 'Pursuit doubles against a switching target.',
};

/** Fixed-damage or assumed-power moves (a number is shown, with this caveat). */
export const ASSUMED_MOVES: Record<string, string> = {
  'Fling': 'Fling power uses the official item values; not confirmed in this game.',
};

/**
 * Emulator-verified behaviour that differs from the official games (work/notes/damage_calc_parity.md). These
 * are certain, so they go into the matchup's `notes`, not its caveats.
 */
export const VERIFIED_MOVE_NOTES: Record<string, string> = {
  'Sonic Boom': 'Sonic Boom is not fixed damage in this game: it hits as a 1-power move (checked in game).',
  'Dragon Rage': 'Dragon Rage is not fixed damage in this game: it hits as a 1-power move (checked in game).',
};
export const VERIFIED_NOTES = {
  hail: 'Hail here works like Snow: Ice types get Defense ×1.5 and nobody takes hail damage (checked in game).',
  corrosion: 'Corrosion does not let Poison moves hit Steel types in this game (checked in game).',
  soulDew: 'Soul Dew in this game: the holder\'s Sp. Atk ×1.5, but its target\'s Sp. Def ×1.5 too, and no Sp. Def boost for the holder (checked in game).',
};

export const WEIGHT_MOVES = ['Low Kick', 'Grass Knot', 'Heavy Slam', 'Heat Crash'];
/** Always shown on weight moves: the hack never fills in battle weight (emulator-verified). */
export const WEIGHT_CAVEAT = 'In this game weight-based moves always use the minimum weight (0.1 kg).';
export const WEIGHT_METAL_CAVEAT = 'Heavy Metal / Light Metal / Float Stone on minimum weight is inferred, not verified.';
export const FRIENDSHIP_MOVES = ['Return', 'Frustration', 'Pika Papow', 'Veevee Volley'];

type Side = 'attacker' | 'defender' | 'both';
/** Duplicate item ids whose lack of effect was checked in the emulator (damage_calc_parity.md "helmet", "items"). */
export const VERIFIED_INERT_ITEM_IDS = [110, 324];
/**
 * End-of-turn texts (desc.ts getEndOfTurn) whose amounts were checked in the emulator: Leftovers 1/16, burn 1/16,
 * poison 1/8, badly poisoned n×(1/16), sandstorm 1/16, Black Sludge 1/8 on a non-Poison holder.
 */
export const VERIFIED_EOT_TEXTS = ['Leftovers recovery', 'burn damage', 'poison damage', 'toxic damage',
  'sandstorm damage', 'Black Sludge damage'];
/** Ability effects that are not modelled or not verified, by engine ability name. */
export const ABILITY_CAVEATS: Record<string, [Side, string]> = {
  'Sturdy': ['defender', 'Sturdy survives a one-hit KO from full HP; not reflected in the KO chance.'],
  'Intimidate': ['defender', 'Intimidate\'s −1 Attack is included, as when it comes in; set stat stages by hand otherwise.'],
  'Disguise': ['defender', 'Disguise blocks the first hit; not included.'],
  'Ice Face': ['defender', 'Ice Face blocks the first physical hit; not included.'],
  'Stance Change': ['both', 'Stance Change form switches are not included.'],
  'Zen Mode': ['both', 'Zen Mode form change at low HP is not included.'],
  'Schooling': ['both', 'Schooling form changes are not included.'],
  'Power Construct': ['both', 'Power Construct form change is not included.'],
  'Shields Down': ['both', 'Shields Down form change is not included.'],
  'Hunger Switch': ['attacker', 'Hunger Switch form change is not included.'],
  'Zero to Hero': ['both', 'Zero to Hero form change is not included.'],
  'Gulp Missile': ['defender', 'Gulp Missile is not included.'],
  'Imposter': ['both', 'Imposter transforms into the target; not included.'],
  'Illusion': ['both', 'Illusion is not included.'],
  'Trace': ['both', 'Trace copies the opponent\'s Ability; not included.'],
  'Flash Fire': ['attacker', 'Flash Fire\'s boost after absorbing a Fire move is not included.'],
  'Blazing Awe': ['attacker', 'Blazing Awe\'s boost after absorbing a Fire move is not included.'],
  'Moxie': ['attacker', 'Stat boosts gained during battle are not included; set stat stages by hand.'],
  'Beast Boost': ['attacker', 'Stat boosts gained during battle are not included; set stat stages by hand.'],
  'Speed Boost': ['both', 'Stat boosts gained during battle are not included; set stat stages by hand.'],
  'Moody': ['both', 'Stat boosts gained during battle are not included; set stat stages by hand.'],
  'Anger Point': ['defender', 'Anger Point maxes Attack after a critical hit; not included.'],
  'Truant': ['attacker', 'Truant only attacks every other turn.'],
  'Ninja Bond': ['defender', 'Ninja Bond assumed to block hits like Wonder Guard (not confirmed in game).'],
  'Wildfire': ['both', 'Wildfire\'s sun is applied; its chip damage is not included.'],
  'Desert Hawk': ['both', 'Desert Hawk\'s Speed effect is not known and not included.'],
  'Aurora Shine': ['defender', 'Aurora Shine assumed to have set up Aurora Veil.'],
  'Innards Out': ['defender', 'Innards Out damage to the attacker is not included.'],
  'Battle Bond': ['attacker', 'Battle Bond: only the Water Shuriken power change is included.'],
  'Unnamed ability #327': ['defender', 'This unnamed Ability does not protect its holder; in a Double Battle it cuts damage to a statused ally by 25% (not included).'],
};

/** Held-item effects that are not modelled or not verified, by engine item name. */
export const ITEM_CAVEATS: Record<string, [Side, string]> = {
  'Focus Sash': ['defender', 'Focus Sash survives a one-hit KO from full HP; not reflected in the KO chance.'],
  'Focus Band': ['defender', 'Focus Band may let it survive a KO; not reflected in the KO chance.'],
  'Sitrus Berry': ['defender', 'Sitrus Berry healing is not included in the KO chance.'],
  'Oran Berry': ['defender', 'Oran Berry healing is not included in the KO chance.'],
  'Figy Berry': ['defender', 'Pinch-Berry healing is not included in the KO chance.'],
  'Wiki Berry': ['defender', 'Pinch-Berry healing is not included in the KO chance.'],
  'Mago Berry': ['defender', 'Pinch-Berry healing is not included in the KO chance.'],
  'Aguav Berry': ['defender', 'Pinch-Berry healing is not included in the KO chance.'],
  'Iapapa Berry': ['defender', 'Pinch-Berry healing is not included in the KO chance.'],
  'Enigma Berry': ['defender', 'Enigma Berry healing is not included in the KO chance.'],
  'Liechi Berry': ['attacker', 'Pinch-Berry stat boosts are not included; set stat stages by hand.'],
  'Petaya Berry': ['attacker', 'Pinch-Berry stat boosts are not included; set stat stages by hand.'],
  'Ganlon Berry': ['defender', 'Pinch-Berry stat boosts are not included; set stat stages by hand.'],
  'Apicot Berry': ['defender', 'Pinch-Berry stat boosts are not included; set stat stages by hand.'],
  'Starf Berry': ['both', 'Pinch-Berry stat boosts are not included; set stat stages by hand.'],
  'Weakness Policy': ['defender', 'Weakness Policy\'s boost after a super-effective hit is not included.'],
  'Absorb Bulb': ['defender', 'Stat boosts from being hit are not included.'],
  'Cell Battery': ['defender', 'Stat boosts from being hit are not included.'],
  'Snowball': ['defender', 'Stat boosts from being hit are not included.'],
  'Metronome': ['attacker', 'Metronome (item) boost assumes the first use of the move.'],
};

/** KO text when the move does not knock out within 9 hits (the engine's search limit). One phrase everywhere. */
export const NO_KO_TEXT = 'no KO in 9 hits';

export const CAVEATS = {
  natureGenerated: 'Nature generated by the game; assumed neutral.',
  primalWeather: 'Heavy rain / harsh sunshine: whether Fire or Water moves fail is not known; ×0.5 assumed.',
  strongWinds: 'Strong winds behaviour is not confirmed in this game.',
  endOfTurn: 'Some end-of-turn effects in the KO chance use modern-game amounts; not confirmed in this game.',
  multiHit: 'Hits 2–5 times; shown for 3 hits.',
  spreadTargets: 'Spread move: ×0.75 shown for hitting two or more Pokémon; against a lone target it does full damage.',
  sheerForce: 'Sheer Force: which moves it boosts is inferred from move data.',
  bulletproof: 'Bulletproof: the list of blocked ball/bomb moves is inferred.',
  telepathy: 'Telepathy: boost assumed to need Psychic Terrain (not confirmed in game).',
  rivalry: 'Rivalry is not included: it depends on both Pokémon\'s genders, and your Pokémon\'s gender is not set.',
  friendshipAssumed: 'Friendship not known; maximum (255) assumed for Return/Frustration.',
  levelUpMovesMissing: 'This trainer uses its default level-up moves, which are not loaded.',
  inertItem: (name: string, id: number) => VERIFIED_INERT_ITEM_IDS.includes(id)
    ? `This ${name} has no battle effect in this game (checked in game).`
    : `This ${name} has no battle effect in this game, going by the game's code (not confirmed in game).`,
  unknownItem: (_id: number) => 'The held item is not in the calculator data; treated as no item.',
  autoWeather: (who: string, what: string) => `${what} assumed from ${who}'s Ability.`,
  supremeOverlord: 'Supreme Overlord: no fainted allies assumed.',
  speedItem: (name: string) => `${name} can change who moves first; not included.`,
};
