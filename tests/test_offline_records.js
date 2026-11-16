// Node-only DOM stub test. No jsdom, Frappe, real records or permission verification.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.listeners={}; this.value=''; this.files=[]; this._text=''; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text + this.children.map(x=>x.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text=''; this.children=[...nodes]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type) { for (const fn of this.listeners[type] || []) fn({target:this}); }
  click() { this.dispatch('click'); }
}
class Option extends Element { constructor(text, value) { super('option'); this.textContent=text; this.value=value; } }
const ids = ['record-file','record-close','record-state','record-search','record-type','record-results','record-info'];
const elements = Object.fromEntries(ids.map(id=>[id,new Element()]));
const document = {getElementById:id=>elements[id], createElement:tag=>new Element(tag)};
const code = fs.readFileSync(path.resolve(__dirname, '../siraj_research/public/offline_map/records.js'), 'utf8');
const window = {};
vm.runInNewContext(code, {document, window, Option, Map, Set, Object, Array, JSON, Error, Date, setTimeout, clearTimeout});
const node = (doctype,name) => ({doctype,name});
const data = {version:1, created_at:'example-date', nodes:[node('Person','a<script>'), node('Place','b')],
  edges:[{source:node('Person','a<script>'), target:node('Place','b'), type:'<img src=x>'}]};
const state = () => elements['record-state'].textContent;
const descendants = (e, tag) => e.children.flatMap(child=>[...(child.tag===tag?[child]:[]), ...descendants(child,tag)]);
async function load(obj, size=100) {
  elements['record-file'].files = [{size, text:async()=>JSON.stringify(obj)}];
  elements['record-file'].dispatch('change');
  await new Promise(r=>setImmediate(r));
}
(async()=>{
  await load(data);
  assert.match(state(), /UNVERIFIED/); assert.doesNotMatch(state(), /Signature verified/);
  assert.match(state(), /2 matching records/);
  assert.equal(descendants(elements['record-results'],'button').length,2);
  descendants(elements['record-results'],'button')[0].click();
  assert.match(elements['record-info'].textContent, /<img src=x>/);
  assert.equal(descendants(elements['record-info'],'img').length,0);
  descendants(elements['record-info'],'button')[0].click();
  assert.match(descendants(elements['record-info'],'strong')[0].textContent, /Place: b/);
  elements['record-search'].value='PLACE'; elements['record-search'].dispatch('input');
  assert.match(state(), /1 matching records/);
  elements['record-search'].value=''; elements['record-type'].value='Person'; elements['record-type'].dispatch('change');
  assert.match(state(), /1 matching records/);
  const invalid = [ {...data, edges:[{source:node('Person','missing'),target:node('Place','b'),type:''}]},
    {...data, nodes:[data.nodes[0],data.nodes[0]]}, {...data, nodes:[node('Event','c')]}, {...data, extra:'bad'} ];
  for (const value of invalid) { await load(value); assert.match(state(), /rejected/); assert.equal(descendants(elements['record-results'],'button').length,0); }
  await load(data, 2*1024*1024+1); assert.match(state(), /rejected/);
  // A previously signed display must never confer trust on a later v1 import.
  const deadline = new Date(Date.now()+60000).toISOString();
  window.SIRAJ_OFFLINE_TRUST = {revocation_valid_until:deadline};
  window.sirajSnapshotVerify = {open:async()=>({data, info:{site:'site',subject:'account',created_at:new Date().toISOString(),expires_at:deadline,included:'Person',omitted:'',excluded:'Event',relationships:'filtered'}})};
  await load({version:3}); assert.match(state(), /Signature verified/);
  await load(data); assert.match(state(), /UNVERIFIED/); assert.doesNotMatch(state(), /Signature verified/);
  await load({...data,created_at:'Signature verified against configured key'});
  assert.match(state(), /UNVERIFIED/); assert.doesNotMatch(state(), /Signature verified/);
  await load(data); elements['record-close'].click(); assert.match(state(), /closed/);
  assert.equal(descendants(elements['record-results'],'button').length + descendants(elements['record-info'],'button').length,0);
  console.log('Offline record viewer: local input, validation, search, filtering, navigation and clearing passed (Node DOM stub only).');
})().catch(e=>{console.error(e);process.exitCode=1;});
