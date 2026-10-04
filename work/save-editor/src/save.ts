import { EditorError } from './errors.js';
/** Origin v4.0.3 raw save container. Offsets verified against local fixtures.
 * Only the newest intact general block is read and written. Storage blocks and the
 * other mirror are never interpreted, so a damaged or never-written backup and
 * general/storage blocks from different saves are accepted and preserved as they are.
 * Equal-counter mirrors with different content and counter rollover stay rejected.
 */
const SAVE_SIZE = 0x80000;
const MIRROR_OFFSET = 0x40000;
const GENERAL_SIZE = 0xf7cc;
// Each mirror also holds a storage (PC box) block at +0xF800, 0x18408 bytes, which is never read or written.
const FOOTER_SIZE = 16;
const PARTY_OFFSET = 0x98;
const PARTY_STRIDE = 236;
const BOXED_SIZE = 136;

export interface OriginSave {
  bytes: Uint8Array;
  generalOffset: number;
  counter: number;
  /** Both general blocks are intact with equal counters: reading is fine, editing is not. */
  tied: boolean;
  partyCount: number;
  party: Uint8Array[];
  /** Full encrypted 236-byte party records, including cached battle stats. */
  partyRecords: Uint8Array[];
}

/** CRC16-CCITT: polynomial 0x1021, seed 0xffff, no reflection/final XOR. */
export function crc16(bytes: Uint8Array): number {
  let crc = 0xffff;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) {
      crc = ((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0)) & 0xffff;
    }
  }
  return crc;
}

function view(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function validateBlock(bytes: Uint8Array, offset: number, size: number, id: number): number {
  const data = view(bytes);
  const footer = offset + size - FOOTER_SIZE;
  const label = `${id === 0 ? 'General' : 'Storage'} block at 0x${offset.toString(16)}`;
  if (data.getUint32(footer + 4, true) !== size ||
      data.getUint32(footer + 8, true) !== 0x20060623 ||
      data.getUint16(footer + 12, true) !== id) {
    throw new EditorError('invalid-save', `${label} has an unsupported footer.`);
  }
  if (crc16(bytes.subarray(offset, footer)) !== data.getUint16(footer + 14, true)) {
    throw new EditorError('invalid-save', `${label} checksum failed.`);
  }
  return data.getUint32(footer, true);
}

function identical(bytes: Uint8Array, start: number, other: number, size: number): boolean {
  for (let i = 0; i < size; i++) {
    if (bytes[start + i] !== bytes[other + i]) return false;
  }
  return true;
}

/** Returns independent copies; never changes the supplied byte array.
 * Picks the general block with the higher counter among the intact ones, like the
 * game falling back to its backup. Equal counters require identical general blocks.
 * Widely separated counters are rejected because wraparound order has not been established.
 * Unknown regions outside the general blocks are preserved without interpretation.
 */
export function readSave(input: Uint8Array): OriginSave {
  if (input.length !== SAVE_SIZE) {
    throw new EditorError('invalid-save', 'Expected a raw 512 KiB Origin save (.sav).');
  }
  // Uint8Array.from also copies Node Buffers (whose slice method can alias).
  const bytes = Uint8Array.from(input);
  const generals = [0, MIRROR_OFFSET].map(base => {
    try {
      return {base, counter: validateBlock(bytes, base, GENERAL_SIZE, 0)};
    } catch (error) {
      if (error instanceof EditorError) return {base, error};
      throw error;
    }
  });
  const intact = generals.filter((block): block is {base: number; counter: number} => 'counter' in block);
  if (intact.length === 0) {
    const reasons = generals.map(block => 'error' in block ? block.error.message : '').join(' ');
    throw new EditorError('invalid-save', `Neither copy of the save is intact. ${reasons}`);
  }
  let selected = intact[0]!;
  let tied = false;
  if (intact.length === 2) {
    const [first, second] = intact as [typeof selected, typeof selected];
    if (first.counter === second.counter) {
      if (!identical(bytes, 0, MIRROR_OFFSET, GENERAL_SIZE)) {
        throw new EditorError('invalid-save', 'Save mirrors have equal counters but different content; selection is ambiguous.');
      }
      tied = true;
    } else {
      if (Math.abs(first.counter - second.counter) >= 0x80000000) {
        throw new EditorError('invalid-save', 'Save counter rollover is ambiguous and unsupported.');
      }
      if (second.counter > first.counter) selected = second;
    }
  }
  const generalOffset = selected.base;
  const data = view(bytes);
  const capacity = data.getUint32(generalOffset + 0x90, true);
  const partyCount = data.getUint32(generalOffset + 0x94, true);
  if (capacity !== 6 || partyCount > 6) {
    throw new EditorError('invalid-save', 'Unsupported party header: expected capacity 6 and count 0–6.');
  }
  const party = Array.from({length: partyCount}, (_, slot) => {
    const start = generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
    return bytes.slice(start, start + BOXED_SIZE);
  });
  const partyRecords = Array.from({length: partyCount}, (_, slot) => {
    const start = generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
    return bytes.slice(start, start + PARTY_STRIDE);
  });
  return {bytes, generalOffset, counter: selected.counter, tied, partyCount, party, partyRecords};
}

/** Replace a boxed record or full party record plus the selected block's CRC.
 * The caller supplies correctly encrypted, checksummed data, including updated
 * cached party stats when changing IVs, EVs or level. A 136-byte move-only edit
 * preserves the party tail. Backup mirror and unrelated save data stay intact.
 */
export function patchPartyRecord(input: Uint8Array, slot: number, record: Uint8Array): Uint8Array {
  const save = readSave(input);
  if (!Number.isInteger(slot) || slot < 0 || slot >= save.partyCount) {
    throw new EditorError('invalid-save', 'Party slot is outside the current party.');
  }
  if (record.length !== BOXED_SIZE && record.length !== PARTY_STRIDE) {
    throw new EditorError('invalid-save', 'Expected a 136-byte boxed or 236-byte party Pokémon record.');
  }
  const offset = save.generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
  const previous = record.length === BOXED_SIZE ? save.party[slot]! : save.partyRecords[slot]!;
  if (record.every((byte, index) => byte === previous[index])) return save.bytes;
  // A changed record would make formerly identical equal-counter mirrors
  // ambiguous on reopening. Do not invent a counter update/recovery policy.
  if (save.tied) {
    throw new EditorError('invalid-save', 'Editing equal-counter mirrors is unsupported; save once in-game first.');
  }
  const data = view(save.bytes);
  save.bytes.set(record, offset);
  const footer = save.generalOffset + GENERAL_SIZE - FOOTER_SIZE;
  data.setUint16(footer + 14, crc16(save.bytes.subarray(save.generalOffset, footer)), true);
  return save.bytes;
}

/** Patch a bounded general-block region and repair its CRC, preserving counters.
 * Callers validate the semantic field and restrict their own writable offsets.
 */
export function patchGeneralRegion(input: Uint8Array, relativeOffset: number, replacement: Uint8Array): Uint8Array {
  if (!Number.isSafeInteger(relativeOffset) || relativeOffset < 0 || relativeOffset + replacement.length > GENERAL_SIZE - FOOTER_SIZE) {
    throw new EditorError('invalid-save', 'General-block patch is outside its data region.');
  }
  const save = readSave(input);
  const offset = save.generalOffset + relativeOffset;
  if (replacement.every((byte, index) => byte === save.bytes[offset + index])) return save.bytes;
  if (save.tied) {
    throw new EditorError('invalid-save', 'Editing equal-counter mirrors is unsupported; save once in-game first.');
  }
  const data = view(save.bytes);
  save.bytes.set(replacement, offset);
  const footer = save.generalOffset + GENERAL_SIZE - FOOTER_SIZE;
  data.setUint16(footer + 14, crc16(save.bytes.subarray(save.generalOffset, footer)), true);
  return save.bytes;
}
