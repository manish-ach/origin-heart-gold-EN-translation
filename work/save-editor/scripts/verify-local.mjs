// Optional integration check against user-owned saves. No fixtures are bundled.
import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { resolve, basename } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { readSave, patchPartyRecord } from '../dist/save.js';
import { decodePokemon, patchPokemonMoves } from '../dist/pokemon.js';

const [directory, output] = process.argv.slice(2);
if (!directory || !output) throw new Error('Usage: node work/save-editor/scripts/verify-local.mjs SAVE_DIRECTORY OUTPUT_DIRECTORY');
const out = resolve(output);
const local = resolve('work/save-editor/local');
if (!out.startsWith(local + '/')) throw new Error('Output must be below work/save-editor/local');
await mkdir(out, { recursive: false });
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const reports = [];
for (const name of (await readdir(directory)).filter(name => name.endsWith('.sav')).sort()) {
  const input = await readFile(resolve(directory, name));
  const before = hash(input);
  const save = readSave(input);
  assert.deepEqual(save.bytes, Uint8Array.from(input));
  const decoded = save.party.map(decodePokemon);
  for (let slot = 0; slot < save.partyCount; slot++) {
    const pokemon = decoded[slot];
    const noOp = patchPokemonMoves(save.party[slot], pokemon.moves);
    assert.deepEqual(patchPartyRecord(input, slot, noOp), Uint8Array.from(input));
    const moves = pokemon.moves.map(move => ({ ...move }));
    [moves[0], moves[1]] = [moves[1], moves[0]];
    const edited = patchPartyRecord(input, slot, patchPokemonMoves(save.party[slot], moves));
    const reopened = readSave(edited);
    assert.deepEqual(decodePokemon(reopened.party[slot]).moves, moves);
    const start = save.generalOffset + 0x98 + 236 * slot;
    const crc = save.generalOffset + 0xf7ca;
    for (let i = 0; i < input.length; i++) {
      if (edited[i] !== input[i]) assert.ok((i >= start && i < start + 136) || i === crc || i === crc + 1);
    }
    const reversed = patchPartyRecord(edited, slot, patchPokemonMoves(reopened.party[slot], pokemon.moves));
    assert.deepEqual(reversed, Uint8Array.from(input));
    if (slot === 0) {
      await writeFile(resolve(out, basename(name)), edited);
      const expected = decoded.map(p => p.moves.map(m => m.id));
      expected[0] = moves.map(move => move.id);
      await writeFile(resolve(out, name + '.expected.json'), JSON.stringify(expected));
    }
  }
  assert.equal(hash(await readFile(resolve(directory, name))), before);
  reports.push({ name, sha256: before, partyCount: save.partyCount, generalOffset: save.generalOffset,
    counter: save.counter, roundTrip: 'byte-identical', allPartySwaps: 'passed', originalPreserved: true });
}
assert.ok(reports.length, 'No saves found');
await writeFile(resolve(out, 'report.json'), JSON.stringify(reports, null, 2) + '\n');
console.log(JSON.stringify(reports, null, 2));
