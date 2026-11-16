// DOM fixture test; no Frappe, real records, server or permission verification.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');
const dir = path.resolve(__dirname, '../siraj_research/public/offline_map');
const dom = new JSDOM(fs.readFileSync(path.join(dir, 'index.html'), 'utf8'), {runScripts:'outside-only'});
const w = dom.window, d = w.document;
w.fetch = () => { throw Error('network must not be used'); };
w.eval(fs.readFileSync(path.join(dir, 'records.js'), 'utf8'));
const node = (doctype,name) => ({doctype,name});
const data = {version:1, created_at:'example-date', nodes:[node('Person','a<script>'), node('Place','b')],
  edges:[{source:node('Person','a<script>'), target:node('Place','b'), type:'<img src=x>'}]};
const state = () => d.getElementById('record-state').textContent;
async function load(obj, size=100) {
  Object.defineProperty(d.getElementById('record-file'), 'files', {configurable:true, value:[{size, text:async()=>JSON.stringify(obj)}]});
  d.getElementById('record-file').dispatchEvent(new w.Event('change'));
  await new Promise(r=>setTimeout(r, 0));
}
(async()=>{
  await load(data);
  assert.match(state(), /2 matching records/);
  assert.equal(d.querySelectorAll('#record-results button').length,2);
  d.querySelector('#record-results button').click();
  assert.match(d.getElementById('record-info').textContent, /<img src=x>/);
  assert.equal(d.querySelectorAll('#records script, #records img').length,0);
  d.querySelector('#record-info button').click();
  assert.match(d.querySelector('#record-info strong').textContent, /Place: b/);
  d.getElementById('record-search').value='PLACE'; d.getElementById('record-search').dispatchEvent(new w.Event('input'));
  assert.match(state(), /1 matching records/);
  d.getElementById('record-search').value=''; d.getElementById('record-type').value='Person'; d.getElementById('record-type').dispatchEvent(new w.Event('change'));
  assert.match(state(), /1 matching records/);
  const invalid = [ {...data, edges:[{source:node('Person','missing'),target:node('Place','b'),type:''}]},
    {...data, nodes:[data.nodes[0],data.nodes[0]]}, {...data, nodes:[node('Event','c')]}, {...data, extra:'bad'} ];
  for (const value of invalid) { await load(value); assert.match(state(), /rejected/); assert.equal(d.querySelectorAll('#record-results button').length,0); }
  await load(data, 2*1024*1024+1); assert.match(state(), /rejected/);
  await load(data); d.getElementById('record-close').click(); assert.match(state(), /closed/);
  assert.equal(d.querySelectorAll('#record-results button, #record-info button').length,0);
  console.log('Offline record viewer: local input, validation, search, filtering, navigation and clearing passed (DOM fixtures only).');
})().catch(e=>{console.error(e);process.exitCode=1;});
