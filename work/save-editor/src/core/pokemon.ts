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
  /** Origin stores the effective ability as u16 at block B +26 and the species slot (0, 1, 2 = hidden) at block A +13. */
  ability: number; abilitySlot: number; heldItem: number;
  /** Latin-only decode of the nickname; undefined when it uses glyphs this table does not cover. */
  nickname: string | undefined;
  otName: string | undefined; tid: number; sid: number;
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
const NAME_PUNCT: Record<number, string> = {0x1de:' ',0x1ab:'!',0x1ac:'?',0x1ad:',',0x1ae:'.',0x1b3:'’',0x1be:'-',0x1bb:'♂',0x1bc:'♀',0x1c4:':'};
export function decodeName(data: DataView, start: number, maxChars = 11): string | undefined {
  let name = '';
  for (let i = 0; i < maxChars; i++) {
    const code = data.getUint16(start + i * 2, true);
    if (code === 0xffff) break;
    if (code >= 0x121 && code <= 0x12a) name += String.fromCharCode(48 + code - 0x121);
    else if (code >= 0x12b && code <= 0x144) name += String.fromCharCode(65 + code - 0x12b);
    else if (code >= 0x145 && code <= 0x15e) name += String.fromCharCode(97 + code - 0x145);
    else if (code >= 0x15f && code <= 0x19e) name += String.fromCharCode(192 + code - 0x15f);
    else if (NAME_PUNCT[code] !== undefined) name += NAME_PUNCT[code];
    else return undefined;
  }
  return name.trim() || undefined;
}
export function decodePokemon(record: Uint8Array): DecodedPokemon {
  const { pid, payload, a, b, c, d } = unpack(record);
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
    ability: data.getUint16(b + 26, true), abilitySlot: data.getUint8(a + 13),
    heldItem: data.getUint16(a + 2, true), nickname: decodeName(data, c),
    otName: decodeName(data, d, 8), tid: trainer & 0xffff, sid: trainer >>> 16,
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
  const thresholds = growthThresholds ?? Array.from({length: 101}, (_, level) => level ? experienceForLevel(level, personal.growthRate) : 0);
  let storedLevel = decoded.party?.level ?? 1;
  if (!decoded.party) for (let level = 2; level <= 100; level++) if (decoded.experience >= thresholds[level]!) storedLevel = level;
  if (!changes || typeof changes !== 'object') throw new EditorError('invalid-pokemon', 'Invalid stat changes.');
  const ivs = changes.ivs ?? decoded.ivs;
  const evs = changes.evs ?? decoded.evs;
  const level = changes.level ?? storedLevel;
  const nature = changes.nature ?? decoded.nature;
  validateStatValues(ivs, 'IV');
  validateStatValues(evs, 'EV');
  if (!Number.isInteger(level) || level < 1 || level > 100) throw new EditorError('invalid-pokemon', 'Level must be 1–100.');
  if (!Number.isInteger(nature) || nature < 0 || nature > 24) throw new EditorError('invalid-pokemon', 'Unsupported nature.');
  const unchanged = STAT_KEYS.every(key => ivs[key] === decoded.ivs[key] && evs[key] === decoded.evs[key]) &&
    level === storedLevel && nature === decoded.nature;
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
  if (level !== storedLevel) data.setUint32(a + 8, experienceForLevel(level, personal.growthRate, growthThresholds), true);
  const stats = calculateStats(personal.baseStats, ivs, evs, level, nature, decoded.speciesId);
  if (!decoded.party) {
    const result = Uint8Array.from(record), sum = checksum(payload);
    view(result).setUint16(6, sum, true);
    result.set(crypt(payload, sum), 8);
    return result;
  }
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

export const ABILITY_MAX = 326;
/** Write the ability ID (block B +26). When it is one of the species' own abilities,
 * also record that slot (block A +13) so evolution keeps the same slot. A custom
 * ability leaves the slot byte alone. PID, nature and everything else is untouched. */
export function patchPokemonAbility(record: Uint8Array, ability: number, slot?: number): Uint8Array {
  if (!Number.isInteger(ability) || ability < 1 || ability > ABILITY_MAX) throw new EditorError('invalid-pokemon', 'Choose a valid ability.');
  if (slot !== undefined && (!Number.isInteger(slot) || slot < 0 || slot > 2)) throw new EditorError('invalid-pokemon', 'Ability slot must be 0, 1 or 2.');
  const decoded = decodePokemon(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Eggs cannot have their ability changed.');
  if (decoded.ability === ability && (slot === undefined || decoded.abilitySlot === slot)) return Uint8Array.from(record);
  const { payload, a, b } = unpack(record);
  view(payload).setUint16(b + 26, ability, true);
  if (slot !== undefined) payload[a + 13] = slot;
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** Held item lives at block A +2. 0 clears it. */
export function patchPokemonHeldItem(record: Uint8Array, item: number): Uint8Array {
  if (!Number.isInteger(item) || item < 0 || item > 790) throw new EditorError('invalid-pokemon', 'Choose a valid item.');
  const decoded = decodePokemon(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Eggs cannot hold items.');
  if (decoded.heldItem === item) return Uint8Array.from(record);
  const { payload, a } = unpack(record);
  view(payload).setUint16(a + 2, item, true);
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** What the game writes into an unused party slot: an all-zero record, encrypted with seed 0. */
export function emptyPartyRecord(): Uint8Array {
  const record = new Uint8Array(236);
  record.set(crypt(new Uint8Array(128), 0), 8);
  record.set(crypt(new Uint8Array(100), 0), 136);
  return record;
}

const NAME_CODES: Record<string, number> = Object.fromEntries(Object.entries(NAME_PUNCT).map(([code, ch]) => [ch, Number(code)]));
function encodeName(name: string): Uint8Array {
  const out = new Uint8Array(22); const dv = view(out);
  let n = 0;
  for (const ch of name) {
    if (n >= 10) break;
    const c = ch.charCodeAt(0);
    let code: number | undefined;
    if (c >= 48 && c <= 57) code = 0x121 + c - 48;
    else if (c >= 65 && c <= 90) code = 0x12b + c - 65;
    else if (c >= 97 && c <= 122) code = 0x145 + c - 97;
    else if (c >= 192 && c <= 255) code = 0x15f + c - 192;
    else code = NAME_CODES[ch];
    if (code !== undefined) dv.setUint16(2 * n++, code, true);
  }
  dv.setUint16(2 * n, 0xffff, true);
  return out;
}

export interface NewPokemon {
  speciesId: number; level: number; nature: number; shiny: boolean;
  gender: 'male' | 'female' | 'genderless';
  ability: number; abilitySlot: number;
  ivs: StatValues; moves: readonly { id: number; pp: number }[]; name: string;
  /** From the species' personal data. */
  genderRatio: number; baseFriendship: number;
  personal: { baseStats: readonly [number, number, number, number, number, number]; growthRate: number; growthThresholds: readonly number[] };
}
/** Build a fresh party record. Trainer data (OT ID/name, language, origin game, met
 * location, ribbon/mail tail) is copied from `template`, an existing party member,
 * so the new Pokémon belongs to this save's player. PID is chosen to match nature
 * and gender without being naturally shiny; shiny uses Origin's override bit. */
export function createPokemon(template: Uint8Array, spec: NewPokemon, random: () => number = Math.random, now = new Date()): Uint8Array {
  if (template.length !== 236) throw new EditorError('invalid-pokemon', 'A party Pokémon is needed as the trainer template.');
  const integer = (v: number, min: number, max: number, label: string) => {
    if (!Number.isInteger(v) || v < min || v > max) throw new EditorError('invalid-input', `${label} must be ${min}–${max}.`);
  };
  integer(spec.speciesId, 1, 1025, 'Species'); integer(spec.level, 1, 100, 'Level'); integer(spec.nature, 0, 24, 'Nature');
  integer(spec.ability, 1, ABILITY_MAX, 'Ability'); integer(spec.abilitySlot, 0, 2, 'Ability slot');
  validateStatValues(spec.ivs, 'IV');
  if (!spec.moves.length || spec.moves.length > 4) throw new EditorError('invalid-input', 'Choose one to four moves.');
  for (const m of spec.moves) { integer(m.id, 1, 920, 'Move'); integer(m.pp, 0, 255, 'PP'); }
  const r = spec.genderRatio;
  const allowed = r === 255 ? 'genderless' : r === 254 ? 'female' : r === 0 ? 'male' : undefined;
  if (allowed ? spec.gender !== allowed : spec.gender === 'genderless') throw new EditorError('invalid-input', 'That gender is not possible for this species.');

  const source = unpack(template);
  const sourceView = view(source.payload);
  const otId = sourceView.getUint32(source.a + 4, true);
  let pid = 0;
  for (let tries = 0; ; tries++) {
    if (tries > 1_000_000) throw new EditorError('invalid-pokemon', 'Could not find a matching personality value.');
    pid = Math.floor(random() * 0x100000000) >>> 0;
    if (pid % 25 !== spec.nature) continue;
    if (((otId >>> 16) ^ (otId & 0xffff) ^ (pid >>> 16) ^ (pid & 0xffff)) < 8) continue;
    if (!allowed) { const female = (pid & 0xff) < r; if (female !== (spec.gender === 'female')) continue; }
    break;
  }
  const [a, b, c, d] = BLOCKS[(pid >>> 13) & 31]!;
  const payload = new Uint8Array(128); const data = view(payload);
  // Block A
  data.setUint16(a, spec.speciesId, true);
  data.setUint32(a + 4, otId, true);
  data.setUint32(a + 8, experienceForLevel(spec.level, spec.personal.growthRate, spec.personal.growthThresholds), true);
  payload[a + 12] = spec.baseFriendship;
  payload[a + 13] = spec.abilitySlot;
  payload[a + 15] = source.payload[source.a + 15]!;
  // Block B
  spec.moves.forEach((m, i) => { data.setUint16(b + i * 2, m.id, true); payload[b + 8 + i] = m.pp; });
  let ivWord = 0;
  STAT_KEYS.forEach((key, i) => { ivWord |= spec.ivs[key] << (i * 5); });
  data.setUint32(b + 16, ivWord >>> 0, true);
  data.setUint32(b + 20, spec.shiny ? 0x80000000 : 0, true);
  payload[b + 24] = spec.gender === 'female' ? 2 : spec.gender === 'genderless' ? 4 : 0;
  data.setUint16(b + 26, spec.ability, true);
  payload.set(source.payload.subarray(source.b + 28, source.b + 32), b + 28);
  // Block C
  payload.set(encodeName(spec.name), c);
  payload[c + 23] = source.payload[source.c + 23]!;
  // Block D
  payload.set(source.payload.subarray(source.d, source.d + 32), d);
  payload.fill(0, d + 16, d + 19);
  payload[d + 19] = now.getFullYear() % 100; payload[d + 20] = now.getMonth() + 1; payload[d + 21] = now.getDate();
  payload[d + 22] = 0; payload[d + 23] = 0; payload[d + 26] = 0;
  payload[d + 27] = 4; payload[d + 30] = 4; // Poké Ball
  payload[d + 28] = (spec.level & 0x7f) | (source.payload[source.d + 28]! & 0x80);
  payload[d + 31] = 0;
  // Party tail: battle stats, then the template's mail/capsule bytes.
  const evs = mapStats(() => 0);
  const stats = calculateStats(spec.personal.baseStats, spec.ivs, evs, spec.level, spec.nature, spec.speciesId);
  const tail = new Uint8Array(100); const tv = view(tail);
  tail[4] = spec.level;
  tv.setUint16(6, stats.hp, true);
  STAT_KEYS.forEach((key, i) => tv.setUint16(8 + i * 2, stats[key], true));
  tail.set(crypt(template.subarray(136), source.pid).subarray(20), 20);

  const result = new Uint8Array(236); const rv = view(result);
  const sum = checksum(payload);
  rv.setUint32(0, pid, true); rv.setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  result.set(crypt(tail, pid), 136);
  decodePokemon(result);
  return result;
}

/** Update this Pokémon's original trainer fields, preserving PID and party battle data. */
export function patchPokemonOT(record: Uint8Array, changes: {name?: string; tid?: number; sid?: number}): Uint8Array {
  const {payload, a, d} = unpack(record);
  const dv = view(payload);
  for (const key of ['tid', 'sid'] as const) {
    const value = changes[key];
    if (value !== undefined) {
      if (!Number.isInteger(value) || value < 0 || value > 65535) throw new EditorError('invalid-input', `${key === 'tid' ? 'Trainer ID' : 'Secret ID'} must be 0–65535.`);
      dv.setUint16(a + (key === 'tid' ? 4 : 6), value, true);
    }
  }
  if (changes.name !== undefined) {
    const name = changes.name;
    if (typeof name !== 'string' || !name.trim() || [...name].length > 7) throw new EditorError('invalid-input', 'OT name must contain 1–7 characters.');
    const encoded = encodeName(name).slice(0, 16);
    if (decodeName(view(encoded), 0, 8) !== name) throw new EditorError('invalid-input', 'OT name contains unsupported characters or surrounding spaces.');
    payload.set(encoded, d);
  }
  const result = Uint8Array.from(record), sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}
