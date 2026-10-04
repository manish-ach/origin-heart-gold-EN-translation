import test from 'node:test';
import assert from 'node:assert/strict';
import { searchChoices, createNamePicker } from '../dist/name-picker.js';
const choices = [{id:501,name:'Poké Ball'}, {id:9,name:'King’s Rock'}, {id:73,name:'Fire Punch'}, {id:92,name:'Fire Punch'}];
test('name search ignores accents, case and apostrophe style; preserves native IDs and duplicate names', () => {
  assert.deepEqual(searchChoices(choices,'POKE'),[choices[0]]);
  assert.deepEqual(searchChoices(choices,"king's"),[choices[1]]);
  assert.deepEqual(searchChoices(choices,'punch fire').map(c=>c.id),[73,92]);
  assert.deepEqual(searchChoices(choices,'501'),[]);
  assert.deepEqual(searchChoices(choices,'no match'),[]);
});
class Element {
  children=[]; listeners={}; value=''; textContent='';
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=[...nodes]}
  setAttribute(key,value){this[key]=value}
  addEventListener(name,callback){this.listeners[name]=callback}
  fire(name){this.listeners[name]?.({})}
}
test('searching never changes selection; explicit selection emits IDs; unknown and setValue preserve IDs', () => {
  globalThis.document={createElement:()=>new Element()};
  const calls=[];
  const picker=createNamePicker({label:'Move 1',choices,value:900,onChange:id=>calls.push(id)});
  const [search,select,current]=picker.root.children;
  assert.equal(picker.value(),900); assert.equal(current.textContent,'Selected: Name unavailable');
  search.value='fire'; search.fire('input');
  assert.equal(picker.value(),900); assert.deepEqual(calls,[]);
  assert.deepEqual(select.children.slice(1).map(o=>o.value),['73','92']);
  select.value='92'; select.fire('change'); assert.equal(picker.value(),92); assert.deepEqual(calls,[92]);
  select.value='92'; select.fire('change'); assert.deepEqual(calls,[92]);
  picker.setValue(501); assert.equal(picker.value(),501); assert.deepEqual(calls,[92]);
  search.value='<script>'; search.fire('input'); assert.equal(picker.value(),501); assert.equal(select.children.length,1);
  delete globalThis.document;
});
