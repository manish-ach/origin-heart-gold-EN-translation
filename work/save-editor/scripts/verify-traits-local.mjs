// Local fixtures only: originals are read, never overwritten. No ROM required.
import assert from 'node:assert/strict';
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {readSave,patchPartyRecord} from '../dist/save.js';
import {decodePokemon,patchPokemonShiny,patchPokemonPokerus} from '../dist/pokemon.js';
const [directory,output]=process.argv.slice(2);
if(!directory||!output) throw Error('Usage: node work/save-editor/scripts/verify-traits-local.mjs SAVE_DIRECTORY NEW_OUTPUT_DIRECTORY');
const out=resolve(output);
if(!out.startsWith(resolve('work/save-editor/local')+'/')) throw Error('Output must be below ignored work/save-editor/local');
await mkdir(out,{recursive:false});
const hash=b=>createHash('sha256').update(b).digest('hex');
const report=[];
for(const name of (await readdir(directory)).filter(n=>n.endsWith('.sav')).sort()) {
 const path=resolve(directory,name),input=await readFile(path),sourceHash=hash(input),save=readSave(input);
 let edited=Uint8Array.from(input);
 for(let slot=0;slot<save.partyCount;slot++) {
  const record=save.partyRecords[slot],before=decodePokemon(record);
  assert.deepEqual(patchPokemonShiny(record,before.shiny),record);
  assert.deepEqual(patchPokemonPokerus(record,before.pokerus.status),record);
  for(const status of ['none','infected','cured']) {
   const changed=patchPokemonPokerus(record,status),after=decodePokemon(changed);
   assert.equal(after.pokerus.status,status);assert.deepEqual({...after,pokerus:before.pokerus},before);
   assert.deepEqual(changed.slice(136),record.slice(136));
  }
  const shiny=patchPokemonShiny(record,true);
  if(!before.naturalShiny) assert.equal(decodePokemon(patchPokemonShiny(shiny,false)).shiny,false);
  // Six-party fixture includes on/off, infected/cured/none and unchanged control.
  const status=['infected','cured','none','infected','cured',before.pokerus.status][slot%6];
  let changed=slot===5?record:patchPokemonPokerus(record,status);
  if(slot===0||slot===2) changed=patchPokemonShiny(changed,true);
  if(slot===1&&!before.naturalShiny) changed=patchPokemonShiny(patchPokemonShiny(changed,true),false);
  const after=decodePokemon(changed);
  assert.deepEqual({...after,shiny:before.shiny,shinyOverride:before.shinyOverride,pokerus:before.pokerus},before);
  const single=patchPartyRecord(input,slot,changed),start=save.generalOffset+0x98+slot*236,crc=save.generalOffset+0xf7ca;
  for(let i=0;i<input.length;i++) if(single[i]!==input[i]) assert.ok((i>=start+6&&i<start+136)||i===crc||i===crc+1,`Unexpected changed byte ${i}`);
  edited=patchPartyRecord(edited,slot,changed);
 }
 const pokemon=readSave(edited).partyRecords.map(decodePokemon);
 await writeFile(resolve(out,name),edited);
 await writeFile(resolve(out,name+'.traits.json'),JSON.stringify(pokemon.map(({shiny,naturalShiny,shinyOverride,pokerus})=>({shiny,naturalShiny,shinyOverride,pokerus})),null,2));
 await writeFile(resolve(out,name+'.stats.json'),JSON.stringify(pokemon,null,2));
 await writeFile(resolve(out,name+'.moves.json'),JSON.stringify(pokemon.map(p=>p.moves.map(m=>m.id))));
 assert.equal(hash(await readFile(path)),sourceHash);
 report.push({name,partyCount:save.partyCount,sha256:sourceHash,status:'passed'});
}
assert.ok(report.length);await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
