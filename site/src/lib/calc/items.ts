// Item helpers, adapted from @smogon/calc items.ts (MIT; see LICENSE).
// Removed: TR Fling powers, Natural Gift (needs berry data the hack does not export), Drives, Memories.
import type {StatID, TypeName} from './types.ts';

export const SEED_BOOSTED_STAT: {[item: string]: StatID} = {
  'Electric Seed': 'def',
  'Grassy Seed': 'def',
  'Misty Seed': 'spd',
  'Psychic Seed': 'spd',
};

export function getItemBoostType(item: string | undefined): TypeName | undefined {
  switch (item) {
  case 'Draco Plate':
  case 'Dragon Fang':
    return 'Dragon';
  case 'Dread Plate':
  case 'Black Glasses':
    return 'Dark';
  case 'Earth Plate':
  case 'Soft Sand':
    return 'Ground';
  case 'Fist Plate':
  case 'Black Belt':
    return 'Fighting';
  case 'Flame Plate':
  case 'Charcoal':
    return 'Fire';
  case 'Icicle Plate':
  case 'Never-Melt Ice':
    return 'Ice';
  case 'Insect Plate':
  case 'Silver Powder':
    return 'Bug';
  case 'Iron Plate':
  case 'Metal Coat':
    return 'Steel';
  case 'Meadow Plate':
  case 'Rose Incense':
  case 'Miracle Seed':
    return 'Grass';
  case 'Mind Plate':
  case 'Odd Incense':
  case 'Twisted Spoon':
    return 'Psychic';
  case 'Fairy Feather':
  case 'Pixie Plate':
    return 'Fairy';
  case 'Sky Plate':
  case 'Sharp Beak':
    return 'Flying';
  case 'Splash Plate':
  case 'Sea Incense':
  case 'Wave Incense':
  case 'Mystic Water':
    return 'Water';
  case 'Spooky Plate':
  case 'Spell Tag':
    return 'Ghost';
  case 'Stone Plate':
  case 'Rock Incense':
  case 'Hard Stone':
    return 'Rock';
  case 'Toxic Plate':
  case 'Poison Barb':
    return 'Poison';
  case 'Zap Plate':
  case 'Magnet':
    return 'Electric';
  case 'Silk Scarf':
  case 'Pink Bow':
  case 'Polkadot Bow':
    return 'Normal';
  default:
    return undefined;
  }
}

export function getBerryResistType(berry: string | undefined): TypeName | undefined {
  switch (berry) {
  case 'Chilan Berry':
    return 'Normal';
  case 'Occa Berry':
    return 'Fire';
  case 'Passho Berry':
    return 'Water';
  case 'Wacan Berry':
    return 'Electric';
  case 'Rindo Berry':
    return 'Grass';
  case 'Yache Berry':
    return 'Ice';
  case 'Chople Berry':
    return 'Fighting';
  case 'Kebia Berry':
    return 'Poison';
  case 'Shuca Berry':
    return 'Ground';
  case 'Coba Berry':
    return 'Flying';
  case 'Payapa Berry':
    return 'Psychic';
  case 'Tanga Berry':
    return 'Bug';
  case 'Charti Berry':
    return 'Rock';
  case 'Kasib Berry':
    return 'Ghost';
  case 'Haban Berry':
    return 'Dragon';
  case 'Colbur Berry':
    return 'Dark';
  case 'Babiri Berry':
    return 'Steel';
  case 'Roseli Berry':
    return 'Fairy';
  default:
    return undefined;
  }
}

const FLING_100 = new Set([
  'Hard Stone',
  'Room Service',
  'Claw Fossil',
  'Dome Fossil',
  'Helix Fossil',
  'Old Amber',
  'Root Fossil',
  'Armor Fossil',
  'Old Amber',
  'Fossilized Bird',
  'Fossilized Dino',
  'Fossilized Drake',
  'Fossilized Fish',
  'Plume Fossil',
  'Jaw Fossil',
  'Cover Fossil',
  'Sail Fossil',
  'Rare Bone',
  'Skull Fossil',
]);

const FLING_90 = new Set([
  'Deep Sea Tooth',
  'Thick Club',
]);

const FLING_80 = new Set([
  'Assault Vest',
  'Blunder Policy',
  'Chipped Pot',
  'Cracked Pot',
  'Heavy-Duty Boots',
  'Weakness Policy',
  'Quick Claw',
  'Dawn Stone',
  'Dusk Stone',
  'Electirizer',
  'Magmarizer',
  'Oval Stone',
  'Protector',
  'Sachet',
  'Whipped Dream',
  'Razor Claw',
  'Shiny Stone',
]);

const FLING_70 = new Set([
  'Poison Barb',
  'Dragon Fang',
  'Power Anklet',
  'Power Band',
  'Power Belt',
  'Power Bracer',
  'Power Lens',
  'Power Weight',
]);

const FLING_60 = new Set([
  'Adamant Orb',
  'Damp Rock',
  'Heat Rock',
  'Leek',
  'Lustrous Orb',
  'Macho Brace',
  'Rocky Helmet',
  'Stick',
  'Utility Umbrella',
  'Terrain Extender',
]);
const FLING_30 = new Set([
  'Absorb Bulb',
  'Black Belt',
  'Black Sludge',
  'Black Glasses',
  'Cell Battery',
  'Charcoal',
  'Deep Sea Scale',
  'Flame Orb',
  'King\'s Rock',
  'Life Orb',
  'Light Ball',
  'Light Clay',
  'Magnet',
  'Metal Coat',
  'Miracle Seed',
  'Mystic Water',
  'Never-Melt Ice',
  'Razor Fang',
  'Scope Lens',
  'Soul Dew',
  'Spell Tag',
  'Sweet Apple',
  'Tart Apple',
  'Throat Spray',
  'Toxic Orb',
  'Twisted Spoon',
  'Dragon Scale',
  'Energy Powder',
  'Fire Stone',
  'Leaf Stone',
  'Moon Stone',
  'Sun Stone',
  'Thunder Stone',
  'Up-Grade',
  'Water Stone',
  'Berry Juice',
  'Black Sludge',
  'Prism Scale',
  'Ice Stone',
  'Gold Bottle Cap',
  'Luminous Moss',
  'Eject Button',
  'Snowball',
  'Bottle Cap',
]);
const FLING_10 = new Set([
  'Air Balloon',
  'Berry Sweet',
  'Choice Band',
  'Choice Scarf',
  'Choice Specs',
  'Clover Sweet',
  'Destiny Knot',
  'Electric Seed',
  'Expert Belt',
  'Flower Sweet',
  'Focus Band',
  'Focus Sash',
  'Full Incense',
  'Grassy Seed',
  'Lagging Tail',
  'Lax Incense',
  'Leftovers',
  'Love Sweet',
  'Mental Herb',
  'Metal Powder',
  'Mint Berry',
  'Miracle Berry',
  'Misty Seed',
  'Muscle Band',
  'Power Herb',
  'Psychic Seed',
  'Odd Incense',
  'Quick Powder',
  'Reaper Cloth',
  'Red Card',
  'Ribbon Sweet',
  'Ring Target',
  'Rock Incense',
  'Rose Incense',
  'Sea Incense',
  'Shed Shell',
  'Silk Scarf',
  'Silver Powder',
  'Smooth Rock',
  'Soft Sand',
  'Soothe Bell',
  'Star Sweet',
  'Strawberry Sweet',
  'Wave Incense',
  'White Herb',
  'Wide Lens',
  'Wise Glasses',
  'Zoom Lens',
  'Silver Powder',
  'Power Herb',
]);

// TODO: move this data to the data files instead.
export function getFlingPower(item?: string) {
  if (!item) return 0;
  if (['Big Nugget', 'Iron Ball'].includes(item)) return 130;
  if (FLING_100.has(item)) return 100;
  if (item.includes('Plate') || FLING_90.has(item)) return 90;
  if (FLING_80.has(item)) return 80;
  if (FLING_70.has(item)) return 70;
  if (FLING_60.has(item)) return 60;
  if (['Eject Pack', 'Sharp Beak', 'Dubious Disc'].includes(item)) return 50;
  if (['Icy Rock', 'Eviolite', 'Lucky Punch'].includes(item)) return 40;
  if (FLING_30.has(item)) return 30;
  if (item === 'Pretty Feather') return 20;
  if (item.includes('Berry') || FLING_10.has(item)) return 10;
  return 0;
}
