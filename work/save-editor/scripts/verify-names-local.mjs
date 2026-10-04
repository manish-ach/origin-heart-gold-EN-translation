// Read-only integration checks: no ROM/save data or generated saves are emitted.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {loadOriginData} from '../dist/rom.js';
import {validateMoveChoice,maxMovePp} from '../dist/catalog.js';
import {readSave,patchPartyRecord} from '../dist/save.js';
import {decodePokemon,patchPokemonMoves} from '../dist/pokemon.js';
import {readInventory,patchInventoryPocket,POCKETS} from '../dist/inventory.js';
const [englishPath,chinesePath,...savePaths]=process.argv.slice(2);
if(!englishPath||!chinesePath||!savePaths.length)throw Error('Usage: node work/save-editor/scripts/verify-names-local.mjs EN_ROM CN_ROM SAVE [SAVE...]');
const en=await loadOriginData(await readFile(englishPath));
const cn=await loadOriginData(await readFile(chinesePath));
assert.deepEqual(en.catalog.readiness,{moves:902,species:1025,items:768});
assert.deepEqual(cn.catalog.readiness,{moves:0,species:0,items:0});
assert.equal(en.catalog.getSpecies(29).name.endsWith('♀'),true);
assert.equal(en.catalog.getSpecies(32).name.endsWith('♂'),true);
const namedMove=en.catalog.moves.find(m=>m.name==='Withdraw');
const namedItem=en.inventory.items.find(i=>i.name==='Potion');
assert.equal(namedMove?.id,110);assert.equal(namedMove.basePp,40);
assert.equal(namedItem?.id,17);assert.equal(namedItem.pocket,'medicine');
for(let id=0;id<=920;id++){
 const a=en.catalog.getMove(id),b=cn.catalog.getMove(id);
 for(const field of ['id','basePp','type','power','accuracy'])assert.equal(a[field],b[field]);
}
for(let id=1;id<=790;id++)assert.equal(en.inventory.getItem(id)?.pocket,cn.inventory.getItem(id)?.pocket);
for(const path of savePaths){
 const input=Uint8Array.from(await readFile(path)), snapshot=input.slice(), parsed=readSave(input);
 assert.ok(parsed.partyCount>0);assert.deepEqual(parsed.bytes,input);
 const current=decodePokemon(parsed.party[0]).moves;
 assert.deepEqual(patchPartyRecord(input,0,patchPokemonMoves(parsed.party[0],current)),input);
 const inventory=readInventory(input);
 for(const pocket of POCKETS)assert.deepEqual(patchInventoryPocket(input,pocket.id,inventory.pockets[pocket.id],en.inventory),input);
 const pp=maxMovePp(namedMove,3);validateMoveChoice(en.catalog,namedMove.id,pp,3);
 const namedMoves=current.map(m=>({...m}));namedMoves[0]={id:namedMove.id,pp,ppUps:3};
 const numericMoves=current.map(m=>({...m}));numericMoves[0]={id:110,pp:64,ppUps:3};
 let named=patchPartyRecord(input,0,patchPokemonMoves(parsed.party[0],namedMoves));
 let numeric=patchPartyRecord(input,0,patchPokemonMoves(parsed.party[0],numericMoves));
 assert.deepEqual(named,numeric);
 function stacks(id){const list=inventory.pockets.medicine.map(s=>({...s}));const existing=list.find(s=>s.id===id);if(existing)existing.quantity=7;else {if(list.length===POCKETS.find(p=>p.id==='medicine').capacity)list.pop();list.push({id,quantity:7});}return list;}
 named=patchInventoryPocket(named,namedItem.pocket,stacks(namedItem.id),en.inventory);
 numeric=patchInventoryPocket(numeric,'medicine',stacks(17),cn.inventory);
 assert.deepEqual(named,numeric);
 // The download payload is a byte copy; reparse it and verify save and Pokémon CRCs.
 const exported=new Uint8Array(await new Blob([named]).arrayBuffer());
 const reloaded=readSave(exported);assert.deepEqual(decodePokemon(reloaded.party[0]).moves,namedMoves);
 assert.equal(readInventory(exported).pockets.medicine.find(s=>s.id===namedItem.id).quantity,7);
 validateMoveChoice(en.catalog,0,0,0);
 const emptyMoves=namedMoves.map(m=>({...m}));emptyMoves[0]={id:0,pp:0,ppUps:0};
 const cleared=patchPartyRecord(exported,0,patchPokemonMoves(reloaded.party[0],emptyMoves));
 assert.deepEqual(decodePokemon(readSave(cleared).party[0]).moves[0],emptyMoves[0]);
 assert.deepEqual(input,snapshot);assert.deepEqual(new Uint8Array(await readFile(path)),snapshot);
}
console.log(JSON.stringify({status:'passed',saves:savePaths.length,englishNames:en.catalog.readiness,chineseNames:cn.catalog.readiness,metadataMappings:921,itemPocketMappings:790,checks:['name-to-ID byte equivalence','move/item edits','exact no-op','empty move','export reparse','inputs unchanged']}));
