import test from 'node:test';
import assert from 'node:assert/strict';
import {crc16, readSave, patchPartyRecord} from '../dist/save.js';

const MIRROR = 0x40000;
const GENERAL = 0xf7cc;
const STORAGE = 0xf800;
const STORAGE_SIZE = 0x18408;
const blocks = [[0, GENERAL, 0], [STORAGE, STORAGE_SIZE, 1]];
const dataView = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
function updateCrc(bytes, base, offset = 0, size = GENERAL) {
  const footer = base + offset + size - 16;
  dataView(bytes).setUint16(footer + 14, crc16(bytes.subarray(base + offset, footer)), true);
}
function fixture(counters = [10, 9]) {
  // Deliberately invented bytes, not game content or a playable save.
  const bytes = new Uint8Array(0x80000);
  for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 13 + 71) & 255;
  const view = dataView(bytes);
  [0, MIRROR].forEach((base, index) => {
    view.setUint32(base + 0x90, 6, true);
    view.setUint32(base + 0x94, 2, true);
    for (const [offset, size, id] of blocks) {
      const footer = base + offset + size - 16;
      view.setUint32(footer, counters[index], true);
      view.setUint32(footer + 4, size, true);
      view.setUint32(footer + 8, 0x20060623, true);
      view.setUint16(footer + 12, id, true);
      updateCrc(bytes, base, offset, size);
    }
  });
  return bytes;
}

test('CRC matches the independent standard check vector', () => {
  assert.equal(crc16(new TextEncoder().encode('123456789')), 0x29b1);
  assert.equal(crc16(new Uint8Array()), 0xffff);
});

for (const counters of [[10, 9], [9, 10]]) {
  const active = counters[0] > counters[1] ? 0 : MIRROR;
  test(`selects higher coherent counter at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    const save = readSave(bytes);
    assert.equal(save.generalOffset, active);
    assert.equal(save.counter, 10);
    assert.equal(save.tied, false);
    assert.equal(save.partyCount, 2);
    assert.deepEqual(save.party[1], bytes.slice(active + 0x98 + 236, active + 0x98 + 236 + 136));
    assert.deepEqual(save.bytes, bytes);
    assert.deepEqual(patchPartyRecord(bytes, 1, save.party[1]), bytes);
  });

  test(`party edit preserves backup, tail and every unrelated byte at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    const original = bytes.slice();
    const record = readSave(bytes).party[1];
    record[0] ^= 0x55;
    record[135] ^= 0xaa;
    const edited = patchPartyRecord(bytes, 1, record);
    const offset = active + 0x98 + 236;
    const crcOffset = active + GENERAL - 2;
    let changes = 0;
    for (let i = 0; i < bytes.length; i++) {
      if (edited[i] === bytes[i]) continue;
      changes++;
      assert.ok((i >= offset && i < offset + 136) || i === crcOffset || i === crcOffset + 1,
        `Unexpected change at ${i.toString(16)}`);
    }
    assert.ok(changes >= 2);
    assert.deepEqual(bytes, original, 'caller input unchanged');
    assert.deepEqual(edited.slice(offset + 136, offset + 236), bytes.slice(offset + 136, offset + 236));
    const backup = active === 0 ? MIRROR : 0;
    assert.deepEqual(edited.slice(backup, backup + MIRROR), bytes.slice(backup, backup + MIRROR));
    const reparsed = readSave(edited);
    assert.equal(reparsed.counter, 10);
    assert.deepEqual(reparsed.party[1], record);
  });
}

test('copies input and party records, including Buffer and nonzero-offset views', () => {
  for (const input of [fixture(), Buffer.from(fixture()), Buffer.concat([Buffer.alloc(7), Buffer.from(fixture())]).subarray(7)]) {
    const save = readSave(input);
    const original = input[0x98];
    save.party[0][0] ^= 255;
    assert.equal(save.bytes[0x98], original);
    assert.equal(input[0x98], original);
    save.bytes[0x98] ^= 127;
    assert.equal(input[0x98], original);
    const noop = patchPartyRecord(input, 0, readSave(input).party[0]);
    noop[0] ^= 255;
    assert.notEqual(noop[0], input[0]);
  }
});

test('rejects unsupported length and saves with no intact general block', () => {
  assert.throws(() => readSave(new Uint8Array(0x80001)), /512 KiB/);
  const both = fixture();
  both[42] ^= 1;
  both[MIRROR + 42] ^= 1;
  assert.throws(() => readSave(both), /Neither copy.*checksum failed/);
  for (const field of [4, 8, 12]) {
    const badFooters = fixture();
    badFooters[GENERAL - 16 + field] ^= 1;
    badFooters[MIRROR + GENERAL - 16 + field] ^= 1;
    assert.throws(() => readSave(badFooters), /Neither copy.*unsupported footer/);
  }
  assert.throws(() => readSave(new Uint8Array(0x80000).fill(0xff)), /Neither copy/);
});

for (const counters of [[10, 9], [9, 10]]) {
  const active = counters[0] > counters[1] ? 0 : MIRROR;
  const backup = active === 0 ? MIRROR : 0;

  test(`damaged backup and storage blocks are ignored and preserved at ${active.toString(16)}`, () => {
    const damages = [
      bytes => { bytes[backup + 42] ^= 1; },                          // backup general checksum
      bytes => { bytes[backup + GENERAL - 16 + 8] ^= 1; },            // backup general footer
      bytes => { bytes.fill(0xff, backup, backup + MIRROR); },        // backup never written
      bytes => { bytes[active + STORAGE + 42] ^= 1; },                // active storage checksum
      bytes => { dataView(bytes).setUint32(active + STORAGE + STORAGE_SIZE - 16, 3, true); }, // mixed counters
    ];
    for (const damage of damages) {
      const bytes = fixture(counters);
      damage(bytes);
      const save = readSave(bytes);
      assert.equal(save.generalOffset, active);
      assert.equal(save.tied, false);
      const record = save.party[0].slice();
      record[0] ^= 1;
      const edited = patchPartyRecord(bytes, 0, record);
      assert.deepEqual(edited.slice(backup, backup + MIRROR), bytes.slice(backup, backup + MIRROR));
      assert.deepEqual(edited.slice(active + STORAGE, active + STORAGE + STORAGE_SIZE),
        bytes.slice(active + STORAGE, active + STORAGE + STORAGE_SIZE));
      assert.deepEqual(readSave(edited).party[0], record);
    }
  });

  test(`a damaged newest general block falls back to the older copy at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    bytes[active + 42] ^= 1;
    const save = readSave(bytes);
    assert.equal(save.generalOffset, backup);
    assert.equal(save.counter, 9);
  });
}

test('rejects divergent tied mirrors and ambiguous rollover', () => {
  const tied = fixture([10, 10]);
  tied[0x300] ^= 1;
  updateCrc(tied, 0);
  assert.throws(() => readSave(tied), /equal counters but different content/);
  assert.throws(() => readSave(fixture([0xffffffff, 0])), /rollover/);
  assert.throws(() => readSave(fixture([0, 0x80000000])), /rollover/);
  const tiedDamaged = fixture([10, 10]);
  tiedDamaged[MIRROR + 42] ^= 1;
  const save = readSave(tiedDamaged);
  assert.equal(save.tied, false);
  assert.equal(save.generalOffset, 0);
});

test('identical tied mirrors allow inspection and exact no-op but reject mutation', () => {
  const tied = fixture([10, 10]);
  const save = readSave(tied);
  assert.equal(save.tied, true);
  assert.deepEqual(patchPartyRecord(tied, 0, save.party[0]), tied);
  save.party[0][0] ^= 1;
  assert.throws(() => patchPartyRecord(tied, 0, save.party[0]), /Editing equal-counter/);
});

test('validates active party header and patch arguments', () => {
  for (const [offset, value] of [[0x90, 5], [0x94, 7], [0x94, 0xffffffff]]) {
    const bad = fixture();
    dataView(bad).setUint32(offset, value, true);
    updateCrc(bad, 0);
    assert.throws(() => readSave(bad), /party header/);
  }
  const empty = fixture();
  dataView(empty).setUint32(0x94, 0, true);
  updateCrc(empty, 0);
  assert.deepEqual(readSave(empty).party, []);
  const bytes = fixture();
  for (const slot of [-1, 2, 0.5, NaN, Infinity]) {
    assert.throws(() => patchPartyRecord(bytes, slot, new Uint8Array(136)), /Party slot/);
  }
  assert.throws(() => patchPartyRecord(bytes, 0, new Uint8Array(135)), /136-byte/);
});


test('full party stat edit preserves all other records, mirror, storage and gap bytes', () => {
  for (const active of [0, MIRROR]) {
    const bytes = fixture(active === 0 ? [10, 9] : [9, 10]);
    const before = bytes.slice();
    const save = readSave(bytes);
    assert.equal(save.partyRecords[0].length, 236);
    assert.deepEqual(patchPartyRecord(bytes, 0, save.partyRecords[0]), bytes);
    const record = save.partyRecords[1].slice();
    record[8] ^= 51;
    record[145] ^= 71;
    const edited = patchPartyRecord(bytes, 1, record);
    const start = active + 0x98 + 236;
    const crc = active + GENERAL - 2;
    for (let i = 0; i < bytes.length; i++) {
      if (edited[i] !== bytes[i]) assert.ok((i >= start && i < start + 236) || i === crc || i === crc + 1);
    }
    assert.deepEqual(readSave(edited).partyRecords[1], record);
    assert.deepEqual(bytes, before);
    save.partyRecords[0].fill(0);
    assert.deepEqual(bytes, before);
    assert.deepEqual(save.party[0], readSave(bytes).party[0]);
  }
});
