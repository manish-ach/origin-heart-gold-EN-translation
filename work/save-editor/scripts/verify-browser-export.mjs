// Audit actual UI downloads for the documented six-party browser scenario.
// This script reads saves, but never creates or patches a save file.
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {readSave} from '../dist/save.js';
import {decodePokemon} from '../dist/pokemon.js';
import {readInventory} from '../dist/inventory.js';
const [sourcePath, unchangedPath, editedPath, output, runtimePath] = process.argv.slice(2);
if (!sourcePath || !unchangedPath || !editedPath || !output) throw Error('Usage: node work/save-editor/scripts/verify-browser-export.mjs SOURCE UNCHANGED_DOWNLOAD EDITED_DOWNLOAD NEW_OUTPUT [RUNTIME_REPORT]');
const out=resolve(output);
assert.ok(out.startsWith(resolve('work/save-editor/local')+'/'), 'Evidence must stay in ignored local/');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const source=await readFile(sourcePath), unchanged=await readFile(unchangedPath), edited=await readFile(editedPath);
assert.deepEqual(unchanged,source,'Browser unchanged download must match the source exactly');
const before=readSave(source), after=readSave(edited);
const expected=before.partyRecords.map(decodePokemon);
assert.equal(expected.length,6); assert.equal(expected[0].speciesId,5,'Use the documented Charmeleon fixture');
assert.equal(expected[0].party.level,9);
assert.deepEqual(expected[0].moves.map(m=>m.id),[9,14,27,40]);
assert.equal(expected[0].naturalShiny,false); assert.equal(expected[0].pokerus.status,'none');
// Expectations come from the documented UI choices and observed preview, never
// from decoding edited bytes to declare themselves correct.
Object.assign(expected[0],{nature:15,experience:11735,shiny:true,shinyOverride:true,pokerus:{raw:16,strain:1,days:0,status:'cured'}});
expected[0].moves[0]={id:53,pp:12,ppUps:1};
Object.assign(expected[0].ivs,{attack:31,defense:31});
Object.assign(expected[0].evs,{hp:200,speed:100});
Object.assign(expected[0].party,{level:25,currentHp:84,stats:{hp:84,attack:44,defense:41,speed:59,spAttack:57,spDefense:39}});
assert.deepEqual(after.partyRecords.map(decodePokemon),expected,'Downloaded party must match independent UI choices');
const inventory=readInventory(source);
assert.equal(inventory.pockets.items[0].id,232,'First Items stack must be Scope Lens');
inventory.money=123456;inventory.pockets.items[0].quantity=7;
assert.deepEqual(readInventory(edited),inventory);
assert.equal(after.counter,before.counter);assert.equal(after.generalOffset,before.generalOffset);
const g=before.generalOffset;
let changed=0;
for(let i=0;i<source.length;i++) if(source[i]!==edited[i]) {
 changed++;
 assert.ok((i>=g+0x98+6&&i<g+0x98+236)||(i>=g+0x78&&i<g+0x7c)||(i>=g+0x646&&i<g+0x648)||(i>=g+0xf7ca&&i<g+0xf7cc),`Unexpected changed byte 0x${i.toString(16)}`);
}
assert.ok(changed>0);
const artifacts=await Promise.all([sourcePath,unchangedPath,editedPath].map(async path=>{const b=await readFile(path);return {path:resolve(path),bytes:b.length,sha256:hash(b)};}));
let native='not_requested';
if(runtimePath) {
 const runtime=JSON.parse(await readFile(runtimePath,'utf8'));
 assert.equal(runtime.status,'passed');assert.deepEqual(runtime.gaps,[]);
 assert.equal(runtime.inputs_before.save.sha256,hash(edited));
 assert.deepEqual(runtime.inputs_after,runtime.inputs_before);
 // Native copied records must retain PP/PP Ups too, beyond move-ID assertions.
 const snapshots=[];
 const walk=value=>{if(!value||typeof value!=='object')return;if(value.stats?.slots?.length===6)snapshots.push(value.stats.slots);for(const item of Object.values(value))if(item&&typeof item==='object')walk(item);};
 walk(runtime.runtime);
 assert.ok(snapshots.length>=2,'Need native load and reset/reload records');
 for(const slots of snapshots) assert.deepEqual(slots.map(row=>decodePokemon(Buffer.from(row.record_hex,'hex'))),expected);
 native='passed: full decoded party, including PP/PP Ups, at load and reload';
}
await mkdir(out,{recursive:false});
await writeFile(resolve(out,'moves.json'),JSON.stringify(expected.map(p=>p.moves.map(m=>m.id)),null,2));
await writeFile(resolve(out,'stats.json'),JSON.stringify(expected,null,2));
await writeFile(resolve(out,'traits.json'),JSON.stringify(expected.map(({shiny,naturalShiny,shinyOverride,pokerus})=>({shiny,naturalShiny,shinyOverride,pokerus})),null,2));
await writeFile(resolve(out,'inventory.json'),JSON.stringify(inventory,null,2));
const report={status:'passed',scenario:'verification-export.md',artifacts,changed_bytes:changed,unchanged_download:'byte-identical',edited_download:'matches UI choices; unrelated bytes preserved',native};
await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
