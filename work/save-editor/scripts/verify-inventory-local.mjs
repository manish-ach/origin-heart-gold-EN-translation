// Optional tests against user-owned inputs; generated data stays ignored locally.
import assert from 'node:assert/strict';
import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { readSave } from '../dist/save.js';
import { decodePokemon } from '../dist/pokemon.js';
import { loadOriginData } from '../dist/rom.js';
import { loadBundledOriginData } from '../dist/bundled-data.js';
import { readInventory, patchMoney, patchInventoryPocket, POCKETS, MONEY_MAX, MONEY_OFFSET, REGISTERED_OFFSET } from '../dist/inventory.js';
const [romPath,directory,output]=process.argv.slice(2);
if (!romPath || !directory || !output) throw Error('Usage: node work/save-editor/scripts/verify-inventory-local.mjs ROM SAVE_DIRECTORY NEW_OUTPUT_DIRECTORY');
const out=resolve(output);
if (!out.startsWith(resolve('work/save-editor/local')+'/')) throw Error('Output must be below ignored work/save-editor/local');
await mkdir(out,{recursive:false});
const hash=b=>createHash('sha256').update(b).digest('hex');
const rom=await readFile(romPath), romHash=hash(rom), data=(process.env.ORIGIN_REFERENCE === 'bundled' ? loadBundledOriginData() : await loadOriginData(rom)).inventory;
function preservation(before,after,ranges) {
 const base=readSave(before).generalOffset, crc=base+0xf7ca;
 for(let i=0;i<before.length;i++) if(before[i]!==after[i]) assert.ok(i===crc || i===crc+1 || ranges.some(([start,end])=>i>=base+start && i<base+end),`Unexpected change at ${i.toString(16)}`);
 readSave(after); // independently checks all container CRCs and mirror selection
}
const reports=[];
for(const name of (await readdir(directory)).filter(n=>n.endsWith('.sav')).sort()) {
 const path=resolve(directory,name), input=await readFile(path), originalHash=hash(input), original=readInventory(input);
 assert.deepEqual(readSave(input).bytes,new Uint8Array(input));
 assert.deepEqual(patchMoney(input,original.money),new Uint8Array(input));
 let combined=patchMoney(input,MONEY_MAX); preservation(input,combined,[[MONEY_OFFSET,MONEY_OFFSET+4]]);
 assert.equal(readInventory(combined).money,MONEY_MAX);
 const operations=[];
 for(const pocket of POCKETS) {
  const before=original.pockets[pocket.id];
  assert.deepEqual(patchInventoryPocket(input,pocket.id,before,data),new Uint8Array(input));
  const choices=data.items.filter(item=>item.pocket===pocket.id);
  const initial=before.length ? before.map(item=>({...item})) : [{id:choices[0].id,quantity:1}];
  initial[0].quantity=pocket.maxQuantity;
  const changed=patchInventoryPocket(input,pocket.id,initial,data);
  preservation(input,changed,[[pocket.offset,pocket.offset+pocket.capacity*4]]);
  assert.equal(readInventory(changed).pockets[pocket.id].find(i=>i.id===initial[0].id).quantity,pocket.maxQuantity);
  const removed=initial.length>1 ? initial[1].id : initial[0].id;
  const afterRemove=patchInventoryPocket(changed,pocket.id,initial.filter(i=>i.id!==removed),data);
  preservation(changed,afterRemove,[[pocket.offset,pocket.offset+pocket.capacity*4],[REGISTERED_OFFSET,REGISTERED_OFFSET+4]]);
  assert.ok(!readInventory(afterRemove).pockets[pocket.id].some(i=>i.id===removed));
  const list=readInventory(afterRemove).pockets[pocket.id];
  const addition=choices.find(item=>!initial.some(i=>i.id===item.id)) ?? choices.find(item=>item.id===removed);
  list.push({id:addition.id,quantity:Math.min(7,pocket.maxQuantity)});
  const afterAdd=patchInventoryPocket(afterRemove,pocket.id,list,data);
  preservation(afterRemove,afterAdd,[[pocket.offset,pocket.offset+pocket.capacity*4]]);
  assert.equal(readInventory(afterAdd).pockets[pocket.id].find(i=>i.id===addition.id).quantity,7);
  combined=patchInventoryPocket(combined,pocket.id,readInventory(afterAdd).pockets[pocket.id],data);
  operations.push({pocket:pocket.id,quantityItem:initial[0].id,quantity:pocket.maxQuantity,removed,added:addition.id});
 }
 assert.deepEqual(readSave(combined).partyRecords,readSave(input).partyRecords);
 const expected=readInventory(combined);
 await writeFile(resolve(out,name),combined);
 await writeFile(resolve(out,name+'.inventory.json'),JSON.stringify(expected,null,2)+'\n');
 await writeFile(resolve(out,name+'.moves.json'),JSON.stringify(readSave(combined).party.map(r=>decodePokemon(r).moves.map(m=>m.id))));
 assert.equal(hash(await readFile(path)),originalHash);
 reports.push({name,status:'passed',sha256:originalHash,money:expected.money,operations});
}
assert.ok(reports.length); assert.equal(hash(await readFile(romPath)),romHash);
await writeFile(resolve(out,'report.json'),JSON.stringify({romHash,reports},null,2)+'\n');
console.log(JSON.stringify({status:'passed',saves:reports.length,pocketChecks:reports.length*POCKETS.length,output:out}));
