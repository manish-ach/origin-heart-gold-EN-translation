import test from 'node:test';
import assert from 'node:assert/strict';
import {crc16} from '../dist/save.js';

// Minimal DOM adapter executes the actual app event handlers. It is not a browser
// replacement: native validity, file-picker events and downloads need browser QA.
class Element {
  children=[];listeners={};attributes={};value='';textContent='';disabled=false;
  constructor(tag='div'){this.tagName=tag.toUpperCase();}
  append(...nodes){for(const node of nodes){this.children.push(node);if(node instanceof Element)node.parentElement=this;}}
  prepend(...nodes){for(const node of nodes)if(node instanceof Element)node.parentElement=this;this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(name,value){this.attributes[name]=value;}
  getAttribute(name){return this.attributes[name]??null;}
  addEventListener(name,callback){(this.listeners[name]??=[]).push(callback);}
  fire(name){for(const callback of this.listeners[name]??[])callback({preventDefault(){}});}
  querySelectorAll(tag){return descendants(this).filter(node=>node.tagName===tag.toUpperCase());}
  reportValidity(){return true;}
}
class Input extends Element{constructor(){super('input');} files=[];}
class Button extends Element{constructor(){super('button');}}
const descendants=node=>node.children.flatMap(child=>child instanceof Element?[child,...descendants(child)]:[]);
const wait=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}

function fixture(money=100){
  const bytes=new Uint8Array(524288),view=new DataView(bytes.buffer);
  // Independent invented Pokemon: species5, valid checksum/ciphertext and tail.
  const record=new Uint8Array(236),rv=new DataView(record.buffer),plain=new Uint8Array(128);
  new DataView(plain.buffer).setUint16(0,5,true);rv.setUint32(0,123,true);rv.setUint16(6,5,true);
  function encrypt(start,payload,seed){const pv=new DataView(payload.buffer);let state=BigInt(seed);for(let i=0;i<payload.length;i+=2){state=(state*1103515245n+24691n)&0xffffffffn;rv.setUint16(start+i,pv.getUint16(i,true)^Number(state>>16n),true);}}
  encrypt(8,plain,5);const tail=new Uint8Array(100),tv=new DataView(tail.buffer);tail[4]=9;tv.setUint16(6,28,true);
  [28,18,13,17,19,14].forEach((n,i)=>tv.setUint16(8+i*2,n,true));encrypt(136,tail,123);
  for(const [index,base] of [0,0x40000].entries()){
    view.setUint32(base+0x78,money,true);view.setUint32(base+0x90,6,true);view.setUint32(base+0x94,1,true);bytes.set(record,base+0x98);
    for(const [offset,size,id] of [[0,0xf7cc,0],[0xf800,0x18408,1]]){
      const footer=base+offset+size-16;view.setUint32(footer,10-index,true);view.setUint32(footer+4,size,true);view.setUint32(footer+8,0x20060623,true);view.setUint16(footer+12,id,true);view.setUint16(footer+14,crc16(bytes.subarray(base+offset,footer)),true);
    }
  }
  return bytes;
}
const file=(name,bytes=fixture())=>({name,size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(0)});
let instance=0;
async function setup(){
  const root=new Element(),ids=new Map();
  for(const id of ['file-input','status','save-details','party-list','editor','inventory-editor','export-original','export-edited']){
    const node=id==='file-input'?new Input():id.startsWith('export-')?new Button():new Element();node.id=id;ids.set(id,node);root.append(node);
  }
  let failRender=false;
  globalThis.HTMLElement=Element;globalThis.HTMLInputElement=Input;globalThis.HTMLButtonElement=Button;
  globalThis.document={getElementById:id=>ids.get(id)??descendants(root).find(node=>node.id===id),createElement:tag=>{if(failRender&&tag==='h3'){failRender=false;throw Error('injected render failure');}return tag==='input'?new Input():tag==='button'?new Button():new Element(tag);}};
  await import(`../dist/app.js?session-test=${++instance}`);
  const get=id=>globalThis.document.getElementById(id);
  const labelled=label=>descendants(root).find(node=>node.getAttribute('aria-label')===label);
  const money=()=>labelled('Money').querySelectorAll('input')[0];
  const click=text=>{const button=descendants(root).find(node=>node.tagName==='BUTTON'&&node.textContent===text);assert.ok(button,`Missing ${text}`);button.fire('click');};
  const submit=label=>labelled(label).fire('submit');
  const pick=async input=>{get('file-input').files=[input];get('file-input').value=input.name;get('file-input').fire('change');await wait();};
  return {get,labelled,money,click,submit,pick,failNextRender:()=>{failRender=true;}};
}
function cleanup(){delete globalThis.document;delete globalThis.HTMLElement;delete globalThis.HTMLInputElement;delete globalThis.HTMLButtonElement;}
async function editedSession(){const ui=await setup();await ui.pick(file('original.sav'));ui.money().value='55555';ui.money().fire('input');ui.submit('Money');ui.labelled('EV HP').value='200';ui.labelled('EV HP').fire('input');return ui;}
function assertPreserved(ui){assert.match(ui.get('save-details').textContent,/original.sav/);assert.equal(ui.money().value,'55555');assert.equal(ui.labelled('EV HP').value,'200');assert.equal(ui.get('export-edited').disabled,true);}

test('actual app rejects replacement sizes/checksums without losing applied edits or pending drafts',async()=>{
  try{const ui=await editedSession();
    for(const bad of [file('bad-size.sav',new Uint8Array(10)),file('bad-crc.sav',new Uint8Array(524288))]){
      await ui.pick(bad);assertPreserved(ui);assert.equal(ui.get('file-input').value,'');assert.equal(ui.get('status').className,'status error');
    }
    // The exact same selected File can be retried after the input is reset.
    const bad=file('same.sav',new Uint8Array(10));await ui.pick(bad);await ui.pick(bad);assertPreserved(ui);
    ui.labelled('Effort values').querySelectorAll('button').find(b=>b.textContent==='Discard').fire('click');
    assert.equal(ui.get('export-edited').disabled,false);assert.equal(ui.money().value,'55555');
    await ui.pick(file('replacement.sav',fixture(200)));assert.match(ui.get('save-details').textContent,/replacement.sav/);assert.equal(ui.money().value,'200');assert.equal(ui.labelled('EV HP').value,'0');assert.equal(ui.get('export-edited').disabled,true);
  }finally{cleanup();}
});
test('actual app preserves session on asynchronous file-read rejection',async()=>{
  try{const ui=await editedSession();await ui.pick({name:'unreadable.sav',size:524288,arrayBuffer:async()=>{throw Error('private OS detail');}});assertPreserved(ui);assert.match(ui.get('status').textContent,/Could not read/);assert.doesNotMatch(ui.get('status').textContent,/private/);}finally{cleanup();}
});
test('actual app latest request wins over an older successful read',async()=>{
  try{const ui=await setup(),old=deferred();await ui.pick({name:'old.sav',size:524288,arrayBuffer:()=>old.promise});await ui.pick(file('latest.sav',fixture(222)));old.resolve(fixture(111).buffer);await wait();assert.match(ui.get('save-details').textContent,/latest.sav/);assert.equal(ui.money().value,'222');assert.equal(ui.get('status').className,'status success');}finally{cleanup();}
});
test('actual app stale read rejection cannot overwrite a newer success',async()=>{
  try{const ui=await setup(),old=deferred();await ui.pick({name:'old.sav',size:524288,arrayBuffer:()=>old.promise});await ui.pick(file('latest.sav',fixture(222)));old.reject(Error('stale'));await wait();assert.match(ui.get('save-details').textContent,/latest.sav/);assert.equal(ui.get('status').className,'status success');}finally{cleanup();}
});
test('actual app rolls back applied edits and pending drafts if new-session rendering fails',async()=>{
  try{const ui=await editedSession();ui.failNextRender();await ui.pick(file('render-fails.sav',fixture(333)));assertPreserved(ui);assert.match(ui.get('status').textContent,/Something went wrong/);await ui.pick(file('recovered.sav',fixture(444)));assert.equal(ui.money().value,'444');}finally{cleanup();}
});
