// Read-only parity against local English ROM and saves. Emits no game text/save files.
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {loadOriginData} from '../dist/rom.js';
import {loadBundledOriginData} from '../dist/bundled-data.js';
import {readSave,patchPartyRecord} from '../dist/save.js';
import {decodePokemon,patchPokemonMoves,patchPokemonStats} from '../dist/pokemon.js';
import {readInventory,patchInventoryPocket,patchMoney,POCKETS} from '../dist/inventory.js';
const [romPath,directory]=process.argv.slice(2);
if(!romPath||!directory)throw Error('Usage: node work/save-editor/scripts/verify-bundled-local.mjs EN_ROM SAVE_DIRECTORY');
const hash=b=>createHash('sha256').update(b).digest('hex');
const rom=await readFile(romPath),romHash=hash(rom),old=await loadOriginData(rom),bundled=loadBundledOriginData();
let saves=0,partyRecords=0,pockets=0;
for(const file of (await readdir(directory)).filter(f=>f.endsWith('.sav'))) {
 const path=resolve(directory,file),input=await readFile(path),inputHash=hash(input),save=readSave(input),inventory=readInventory(input);
 assert.deepEqual(save.bytes,new Uint8Array(input));
 for(let slot=0;slot<save.partyCount;slot++) {
  const record=save.partyRecords[slot],pokemon=decodePokemon(record);
  const changes=[{ivs:{hp:31,attack:30,defense:29,speed:28,spAttack:27,spDefense:26}},{evs:{hp:252,attack:252,defense:4,speed:0,spAttack:0,spDefense:0}},{level:50,nature:3}];
  for(const change of changes) {
   function edit(data){const personal=data.getPersonal(pokemon.speciesId,pokemon.form);return patchPartyRecord(input,slot,patchPokemonStats(record,change,personal,personal.growthThresholds));}
   assert.deepEqual(edit(old),edit(bundled));
  }
  function moves(data){const choices=pokemon.moves.map(m=>({...m})),move=data.catalog.moves.find(m=>m.name==='Flamethrower');choices[0]={id:move.id,pp:move.basePp,ppUps:0};return patchPartyRecord(input,slot,patchPokemonMoves(record,choices));}
  assert.deepEqual(moves(old),moves(bundled));partyRecords++;
 }
 for(const pocket of POCKETS){const stacks=inventory.pockets[pocket.id].map(s=>({...s}));assert.deepEqual(patchInventoryPocket(input,pocket.id,stacks,bundled.inventory),new Uint8Array(input));if(stacks.length)stacks[0].quantity=7;else stacks.push({id:bundled.inventory.items.find(i=>i.pocket===pocket.id).id,quantity:7});assert.deepEqual(patchInventoryPocket(input,pocket.id,stacks,old.inventory),patchInventoryPocket(input,pocket.id,stacks,bundled.inventory));pockets++;}
 assert.equal(readInventory(patchMoney(input,9999999)).money,9999999);
 assert.equal(hash(await readFile(path)),inputHash);saves++;
}
assert.ok(saves);assert.equal(hash(await readFile(romPath)),romHash);
console.log(JSON.stringify({status:'passed',saves,partyRecords,pockets,checks:['stat/move/item edit exact parity','money cap','byte-identical no-op','source hashes unchanged']}));
