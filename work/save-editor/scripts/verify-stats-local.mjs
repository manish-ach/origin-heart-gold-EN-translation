// User-owned ROM/save integration tests; no game fixtures are bundled.
import assert from 'node:assert/strict';
import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { readSave, patchPartyRecord } from '../dist/save.js';
import { decodePokemon, patchPokemonStats } from '../dist/pokemon.js';
import { loadOriginData } from '../dist/rom.js';
import { loadBundledOriginData } from '../dist/bundled-data.js';
const [romPath, directory, output] = process.argv.slice(2);
if (!romPath || !directory || !output) throw Error('Usage: node work/save-editor/scripts/verify-stats-local.mjs ROM SAVE_DIRECTORY NEW_OUTPUT_DIRECTORY');
const out = resolve(output);
if (!out.startsWith(resolve('work/save-editor/local') + '/')) throw Error('Output must be below ignored work/save-editor/local');
await mkdir(out, {recursive: false});
const data = process.env.ORIGIN_REFERENCE === 'bundled' ? loadBundledOriginData() : await loadOriginData(await readFile(romPath));
const hash = b => createHash('sha256').update(b).digest('hex');
const fields = ['hp','attack','defense','speed','spAttack','spDefense'];
const ivs = {hp:31,attack:31,defense:31,speed:0,spAttack:30,spDefense:31};
const evs = {hp:252,attack:0,defense:0,speed:252,spAttack:4,spDefense:0};
const reports = [];
for (const name of (await readdir(directory)).filter(n => n.endsWith('.sav')).sort()) {
  const path = resolve(directory, name);
  const input = await readFile(path); const originalHash = hash(input);
  const save = readSave(input);
  let combined = Uint8Array.from(input);
  for (let slot = 0; slot < save.partyCount; slot++) {
    const record = save.partyRecords[slot]; const before = decodePokemon(record);
    const personal = data.getPersonal(before.speciesId, before.form);
    assert.deepEqual(patchPokemonStats(record, {}, personal), record);
    const ivEdit = decodePokemon(patchPokemonStats(record, {ivs}, personal));
    assert.deepEqual(ivEdit.ivs, ivs); assert.deepEqual(ivEdit.evs, before.evs);
    const evEdit = decodePokemon(patchPokemonStats(record, {evs}, personal));
    assert.deepEqual(evEdit.evs, evs); assert.deepEqual(evEdit.ivs, before.ivs);
    assert.deepEqual(ivEdit.moves, before.moves); assert.deepEqual(evEdit.moves, before.moves);
    // Mix independent operations across the runtime party: IV, EV, level, nature, combined, control.
    const changes = [{ivs}, {evs}, {level:50}, {nature:3}, {ivs,evs,level:35,nature:10}, {}][slot % 6];
    const patched = patchPokemonStats(record, changes, personal, personal.growthThresholds);
    const after = decodePokemon(patched);
    for (const key of ['pid','speciesId','form','isEgg']) assert.equal(after[key], before[key]);
    assert.deepEqual(after.moves, before.moves); assert.equal(after.party.status, before.party.status);
    assert.deepEqual(patched.slice(156), record.slice(156), 'Unrelated party tail survives');
    assert.equal(patched[141], record[141], 'Capsule byte survives');
    const edited = patchPartyRecord(input, slot, patched);
    const start = save.generalOffset + 0x98 + slot * 236;
    const crc = save.generalOffset + 0xf7ca;
    for (let i = 0; i < input.length; i++) {
      if (edited[i] !== input[i]) assert.ok((i >= start && i < start + 236) || i === crc || i === crc + 1);
    }
    assert.deepEqual(readSave(edited).partyRecords[slot], patched);
    combined = patchPartyRecord(combined, slot, patched);
  }
  const expected = readSave(combined).partyRecords.map(record => {
    const {moves,isEgg,...stats} = decodePokemon(record); return stats;
  });
  await writeFile(resolve(out,name),combined);
  await writeFile(resolve(out,name+'.stats.json'),JSON.stringify(expected,null,2));
  await writeFile(resolve(out,name+'.moves.json'),JSON.stringify(readSave(combined).party.map(r=>decodePokemon(r).moves.map(m=>m.id))));
  assert.equal(hash(await readFile(path)), originalHash);
  reports.push({name,partyCount:save.partyCount,sha256:originalHash,status:'passed'});
}
assert.ok(reports.length);
await writeFile(resolve(out,'report.json'),JSON.stringify(reports,null,2)+'\n');
console.log(JSON.stringify(reports,null,2));
