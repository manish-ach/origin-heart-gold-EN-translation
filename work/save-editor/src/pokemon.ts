import { EditorError } from './errors.js';
/** Origin v4.0.3 boxed Pokémon codec; see research-pokemon.md for native evidence. */
export type PokerusStatus = 'none' | 'infected' | 'cured';
export function isPokerusStatus(value: unknown): value is PokerusStatus {
  return value === 'none' || value === 'infected' || value === 'cured';
}
export interface PokemonMove { id: number; pp: number; ppUps: number }
import { mapStats, calculateStats, adjustCurrentHp, validateStatValues, experienceForLevel } from './stats.js';
import type { StatValues } from './stats.js';
export type { StatValues } from './stats.js';
export interface PokemonStatChanges { ivs?: StatValues; evs?: StatValues; level?: number; nature?: number }
export interface DecodedPokemon {
  pid: number; speciesId: number; moves: PokemonMove[];
  shiny: boolean; naturalShiny: boolean; shinyOverride: boolean;
  pokerus: { status: PokerusStatus; strain: number; days: number; raw: number };
  ivs: StatValues; evs: StatValues; nature: number; form: number; experience: number; isEgg: boolean;
  party?: { level: number; currentHp: number; stats: StatValues; status: number };
}
const STAT_KEYS = ['hp', 'attack', 'defense', 'speed', 'spAttack', 'spDefense'] as const;
function statValues(read: (index: number) => number): StatValues {
  return mapStats((_key, index) => read(index));
}

const BLOCKS = [
  [0,32,64,96],[0,32,96,64],[0,64,32,96],[0,96,32,64],
  [0,64,96,32],[0,96,64,32],[32,0,64,96],[32,0,96,64],
  [64,0,32,96],[96,0,32,64],[64,0,96,32],[96,0,64,32],
  [32,64,0,96],[32,96,0,64],[64,32,0,96],[96,32,0,64],
  [64,96,0,32],[96,64,0,32],[32,64,96,0],[32,96,64,0],
  [64,32,96,0],[96,32,64,0],[64,96,32,0],[96,64,32,0],
  [0,32,64,96],[0,32,96,64],[0,64,32,96],[0,96,32,64],
  [0,64,96,32],[0,96,64,32],[32,0,64,96],[32,0,96,64],
] as const;
function view(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}
function crypt(payload: Uint8Array, seed: number): Uint8Array {
  const result = Uint8Array.from(payload);
  const data = view(result);
  for (let offset = 0; offset < payload.length; offset += 2) {
    seed = (Math.imul(seed, 0x41c64e6d) + 0x6073) >>> 0;
    data.setUint16(offset, data.getUint16(offset, true) ^ (seed >>> 16), true);
  }
  return result;
}
function checksum(payload: Uint8Array): number {
  const data = view(payload);
  let sum = 0;
  for (let offset = 0; offset < 128; offset += 2) sum += data.getUint16(offset, true);
  return sum & 0xffff;
}
function unpack(record: Uint8Array) {
  if (!(record instanceof Uint8Array) || (record.length !== 136 && record.length !== 236)) {
    throw new EditorError('invalid-pokemon', 'Expected a 136-byte boxed or 236-byte party Pokémon record.');
  }
  const header = view(record);
  if (header.getUint16(4, true) !== 0) throw new EditorError('invalid-pokemon', 'Unsupported Pokémon flags: record may be open or corrupt.');
  const expected = header.getUint16(6, true);
  const payload = crypt(record.subarray(8, 136), expected);
  if (checksum(payload) !== expected) throw new EditorError('invalid-pokemon', 'Pokémon checksum mismatch.');
  const pid = header.getUint32(0, true);
  const [a, b, c, d] = BLOCKS[(pid >>> 13) & 31]!;
  return { pid, payload, a, b, c, d };
}
export function decodePokemon(record: Uint8Array): DecodedPokemon {
  const { pid, payload, a, b, d } = unpack(record);
  const data = view(payload);
  const ivWord = data.getUint32(b + 16, true);
  const natureOverride = (data.getUint32(b + 20, true) >>> 25) & 63;
  const trainer = data.getUint32(a + 4, true);
  const naturalShiny = ((trainer >>> 16) ^ (trainer & 65535) ^ (pid >>> 16) ^ (pid & 65535)) < 8;
  const shinyOverride = (data.getUint32(b + 20, true) >>> 31) !== 0;
  const tail = record.length === 236 ? view(crypt(record.subarray(136), pid)) : undefined;
  return {
    pokerus: { raw: payload[d + 26]!, strain: payload[d + 26]! >>> 4, days: payload[d + 26]! & 15,
      status: (payload[d + 26]! & 15) ? 'infected' : (payload[d + 26]! >>> 4) ? 'cured' : 'none' },
    pid, shiny: naturalShiny || shinyOverride, naturalShiny, shinyOverride,
    ivs: statValues(i => (ivWord >>> (5 * i)) & 31),
    evs: statValues(i => data.getUint8(a + 16 + i)),
    nature: natureOverride ? natureOverride - 1 : pid % 25,
    form: data.getUint8(b + 24) >>> 3,
    experience: data.getUint32(a + 8, true),
    isEgg: (ivWord & 0x40000000) !== 0,
    ...(tail ? { party: {
      level: tail.getUint8(4), currentHp: tail.getUint16(6, true),
      status: tail.getUint32(0, true), stats: statValues(i => tail.getUint16(8 + i * 2, true)),
    }} : {}),
    speciesId: data.getUint16(a, true),
    moves: Array.from({length: 4}, (_, i) => ({
      id: data.getUint16(b + i * 2, true), pp: data.getUint8(b + 8 + i), ppUps: data.getUint8(b + 12 + i),
    })),
  };
}
/** Change four complete move slots; all other plaintext and party-tail bytes survive. */
export function patchPokemonMoves(record: Uint8Array, moves: readonly PokemonMove[]): Uint8Array {
  const { payload, b } = unpack(record);
  if (!Array.isArray(moves) || moves.length !== 4) throw new EditorError('invalid-pokemon', 'Exactly four move slots are required.');
  const data = view(payload);
  for (let i = 0; i < 4; i++) {
    const move = moves[i];
    if (!move || !Number.isInteger(move.id) || move.id < 0 || move.id > 65535 ||
        !Number.isInteger(move.pp) || move.pp < 0 || move.pp > 255 ||
        !Number.isInteger(move.ppUps) || move.ppUps < 0 || move.ppUps > 3) {
      throw new EditorError('invalid-pokemon', 'Invalid move ID, PP, or PP Ups.');
    }
    data.setUint16(b + i * 2, move.id, true);
    payload[b + 8 + i] = move.pp;
    payload[b + 12 + i] = move.ppUps;
  }
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** Update independently selected training inputs, then recalculate encrypted party stats. */
export function patchPokemonStats(
  record: Uint8Array, changes: PokemonStatChanges,
  personal: { baseStats: readonly [number, number, number, number, number, number]; growthRate: number },
  growthThresholds?: readonly number[],
): Uint8Array {
  const decoded = decodePokemon(record);
  if (!decoded.party) throw new EditorError('invalid-pokemon', 'Stat editing requires a 236-byte party Pokémon record.');
  if (!changes || typeof changes !== 'object') throw new EditorError('invalid-pokemon', 'Invalid stat changes.');
  const ivs = changes.ivs ?? decoded.ivs;
  const evs = changes.evs ?? decoded.evs;
  const level = changes.level ?? decoded.party.level;
  const nature = changes.nature ?? decoded.nature;
  validateStatValues(ivs, 'IV');
  validateStatValues(evs, 'EV');
  if (!Number.isInteger(level) || level < 1 || level > 100) throw new EditorError('invalid-pokemon', 'Level must be 1–100.');
  if (!Number.isInteger(nature) || nature < 0 || nature > 24) throw new EditorError('invalid-pokemon', 'Unsupported nature.');
  const unchanged = STAT_KEYS.every(key => ivs[key] === decoded.ivs[key] && evs[key] === decoded.evs[key]) &&
    level === decoded.party.level && nature === decoded.nature;
  if (unchanged) return Uint8Array.from(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Egg stat editing is unsupported.');
  const { payload, a, b, pid } = unpack(record);
  const data = view(payload);
  let ivWord = data.getUint32(b + 16, true) & 0xc0000000;
  STAT_KEYS.forEach((key, index) => {
    ivWord |= ivs[key] << (index * 5);
    data.setUint8(a + 16 + index, evs[key]);
  });
  data.setUint32(b + 16, ivWord >>> 0, true);
  if (nature !== decoded.nature) {
    const original = data.getUint32(b + 20, true);
    data.setUint32(b + 20, ((original & 0x81ffffff) | ((nature + 1) << 25)) >>> 0, true);
  }
  if (level !== decoded.party.level) data.setUint32(a + 8, experienceForLevel(level, personal.growthRate, growthThresholds), true);
  const stats = calculateStats(personal.baseStats, ivs, evs, level, nature, decoded.speciesId);
  const tailBytes = crypt(record.subarray(136), pid);
  const tail = view(tailBytes);
  tail.setUint8(4, level);
  tail.setUint16(6, adjustCurrentHp(decoded.party.currentHp, decoded.party.stats.hp, stats.hp, decoded.speciesId), true);
  STAT_KEYS.forEach((key, index) => tail.setUint16(8 + index * 2, stats[key], true));
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  result.set(crypt(tailBytes, pid), 136);
  return result;
}

/** Origin's native override avoids changing PID, gender, nature or ability. */
export function patchPokemonShiny(record: Uint8Array, shiny: boolean): Uint8Array {
  if (typeof shiny !== 'boolean') throw new EditorError('invalid-pokemon', 'Choose a shiny state.');
  const decoded = decodePokemon(record);
  if (shiny === decoded.shiny) return Uint8Array.from(record);
  if (!shiny && decoded.naturalShiny) throw new EditorError('invalid-pokemon', 'This Pokémon is naturally shiny. Removing that would require changing its identity and is not supported.');
  const { payload, b } = unpack(record);
  const data = view(payload);
  const word = data.getUint32(b + 20, true);
  data.setUint32(b + 20, (shiny ? word | 0x80000000 : word & 0x7fffffff) >>> 0, true);
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** Change native infection state; retain existing strain, with a one-day new infection. */
export function patchPokemonPokerus(record: Uint8Array, status: PokerusStatus): Uint8Array {
  if (!isPokerusStatus(status)) throw new EditorError('invalid-pokemon', 'Choose None, Infected or Cured for Pokérus.');
  const decoded = decodePokemon(record);
  if (decoded.pokerus.status === status) return Uint8Array.from(record);
  const { payload, d } = unpack(record);
  const strain = decoded.pokerus.strain || 1;
  payload[d + 26] = status === 'none' ? 0 : (strain << 4) | (status === 'infected' ? 1 : 0);
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}
