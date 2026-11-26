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
const ids = ['record-file','record-close','record-state','record-search','record-type','record-results','record-info','record-tree-root','record-tree-state','record-tree-results'];
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
    {...data, nodes:[data.nodes[0],data.nodes[0]]}, {...data, nodes:[node('Event','c')]},
    {...data, nodes:[node('Siraj Event','c')], edges:[]}, {...data, extra:'bad'} ];
  for (const value of invalid) { await load(value); assert.match(state(), /rejected/); assert.equal(descendants(elements['record-results'],'button').length,0); }
  // Bounded adjacency, incoming/outgoing navigation and self links, all local.
  const hub = node('Person','hub'), places = Array.from({length:150},(_,i)=>node('Place','p'+i));
  const network = {version:1,created_at:'fixture',nodes:[hub,...places],
    edges:places.map((p,i)=>({source:i%2 ? p : hub,target:i%2 ? hub : p,type:'related'}))};
  await load(network); descendants(elements['record-results'],'button')[0].click();
  assert.match(elements['record-info'].textContent,/150 relationships.*showing 1–100/);
  assert.equal(descendants(elements['record-info'],'button').length,101);
  descendants(elements['record-info'],'button').find(b=>b.textContent==='Next relationships').click();
  assert.match(elements['record-info'].textContent,/showing 101–150/);
  assert.equal(descendants(elements['record-info'],'button').length,51);
  descendants(elements['record-info'],'button').find(b=>b.textContent==='Previous relationships').click();
  assert.match(elements['record-info'].textContent,/showing 1–100/);
  assert.match(elements['record-info'].textContent,/→ related/); assert.match(elements['record-info'].textContent,/← related/);
  descendants(elements['record-info'],'button')[0].click();
  assert.match(elements['record-info'].textContent,/1 relationship/);
  const loop = {version:1,created_at:'fixture',nodes:[hub],edges:[{source:hub,target:hub,type:'self'}]};
  await load(loop); descendants(elements['record-results'],'button')[0].click();
  assert.equal(descendants(elements['record-info'],'button').length,1);
  await load({...loop,edges:[{source:hub,target:node('Place','absent'),type:''}]});
  assert.match(state(), /rejected/); assert.equal(descendants(elements['record-info'],'button').length,0);
  // V4 is a synthetic, unsigned local-detail format; it never implies trust.
  const extended = (doctype,name,label,parent=null,details={}) => ({doctype,name,label,parent,details});
  const root=extended('Place','root','Region',null,{source:'<img src=x>'});
  const children=Array.from({length:125},(_,i)=>extended('Place','c'+i,'Child '+i,'root'));
  const person=extended('Person','p','Researcher',null,{note:'<script>not executable</script>'});
  const full={version:4,created_at:'untrusted',nodes:[root,...children,person],
    edges:[{source:node('Person','p'),target:node('Place','c0'),type:'visited'}]};
  elements['record-type'].value=''; await load(full); assert.match(state(),/UNVERIFIED/); assert.doesNotMatch(state(),/Signature verified/);
  elements['record-tree-root'].click(); assert.match(elements['record-tree-state'].textContent,/Top-level places: 1/);
  let treeButtons=descendants(elements['record-tree-results'],'button');
  treeButtons.find(b=>b.textContent==='Show children of Region').click();
  assert.match(elements['record-tree-state'].textContent,/Children of Region: 125/);
  treeButtons=descendants(elements['record-tree-results'],'button'); assert(treeButtons.some(b=>b.textContent==='Next places'));
  treeButtons.find(b=>b.textContent==='Next places').click();
  assert(descendants(elements['record-tree-results'],'button').some(b=>b.textContent==='Previous places'));
  descendants(elements['record-tree-results'],'button').find(b=>b.textContent==='Up one level').click();
  descendants(elements['record-tree-results'],'button').find(b=>b.textContent==='Region').click();
  assert.match(elements['record-info'].textContent,/<img src=x>/); assert.equal(descendants(elements['record-info'],'img').length,0);
  elements['record-search'].value='Researcher'; elements['record-search'].dispatch('input');
  assert.match(state(),/1 matching records/); descendants(elements['record-results'],'button')[0].click();
  assert.match(elements['record-info'].textContent,/<script>not executable<\/script>/);
  assert.equal(descendants(elements['record-info'],'script').length,0);
  descendants(elements['record-info'],'button')[0].click(); assert.match(elements['record-info'].textContent,/Place: Child 0/);
  elements['record-search'].value=''; elements['record-search'].dispatch('input');
  const orphan={...full,nodes:[{...root,parent:'missing'},...children,person]};
  const cycle={...full,nodes:[{...root,parent:'c0'},...children,person]};
  for (const bad of [orphan,cycle,{...full,nodes:[{...root,details:{note:{nested:'bad'}}},...children,person]}]) {
    await load(bad); assert.match(state(),/rejected/); assert.equal(descendants(elements['record-tree-results'],'button').length,0);
  }
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
