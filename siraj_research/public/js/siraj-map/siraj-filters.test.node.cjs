/* Node unit test for siraj-filters pure module.
 * Run: node public/js/siraj-map/siraj-filters.test.node.cjs */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function run() {
  const sandbox = { window:{}, console, setTimeout,
    btoa: s => Buffer.from(s,'binary').toString('base64'),
    atob: s => Buffer.from(s,'base64').toString('binary'),
    localStorage: { _d:{}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=v;}, removeItem(k){delete this._d[k];} },
    document:{}, frappe:{_:s=>s} };
  sandbox.__ = s=>s;
  sandbox.encodeURIComponent = encodeURIComponent;
  sandbox.decodeURIComponent = decodeURIComponent;
  sandbox.escape = escape; sandbox.unescape = unescape;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../siraj-record-meta.js'),'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../siraj-map-kit.js'),'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'siraj-graph.js'),'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'siraj-filters.js'),'utf8'), sandbox);

  const F = sandbox.window.SirajFilters;
  function assert(c,m){ if(!c){console.error('FAIL:',m);process.exit(1);} console.log(' ok -',m); }

  let s = F.initialState(['Person','Institution','Place','Military Unit','Source']);
  assert(F.visibleTypeCount(s) === 5, 'initial state shows all types');

  s = F.reduce(s, {type:'TOGGLE_TYPE', doctype:'Place'});
  assert(s.types.Place === false, 'toggle hides Place');
  assert(F.isTypeVisible(s,'Place') === false, 'isTypeVisible false for Place');
  assert(F.visibleTypeCount(s) === 4, 'visible count = 4');

  s = F.reduce(s, {type:'SELECT_NONE_TYPES'});
  assert(F.visibleTypeCount(s) === 0, 'select-none hides all');

  s = F.reduce(s, {type:'SELECT_ALL_TYPES'});
  assert(F.visibleTypeCount(s) === 5, 'select-all restores');

  s = F.reduce(s, {type:'INVERT_TYPES'});
  assert(F.visibleTypeCount(s) === 0, 'invert of all-on = all-off');

  // Preset "People"
  s = F.initialState(['Person','Institution','Place','Military Unit','Source']);
  s = F.reduce(s, {type:'APPLY_PRESET', id:'people'});
  assert(F.isTypeVisible(s,'Person') && !F.isTypeVisible(s,'Place') && !F.isTypeVisible(s,'Military Unit'),
    'people preset shows Person only');
  assert(s.activePreset === 'people', 'activePreset tracks');

  // Preset "military"
  s = F.reduce(F.initialState(['Person','Institution','Place','Military Unit','Operational Deployment','Mission','Source']),
    {type:'APPLY_PRESET',id:'military'});
  assert(F.isTypeVisible(s,'Military Unit') && F.isTypeVisible(s,'Mission') && F.isTypeVisible(s,'Operational Deployment'),
    'military preset turns on military types');
  assert(!F.isTypeVisible(s,'Person'), 'people hidden in military preset');

  // Save / delete user preset
  s = F.reduce(s, {type:'SAVE_PRESET', id:'mine', label:'Mine'});
  assert(s.presets.mine && s.activePreset==='mine', 'user preset saved');
  s = F.reduce(s, {type:'DELETE_PRESET', id:'mine'});
  assert(!s.presets.mine, 'user preset deleted');

  // Edge visibility with includeHiddenConnectors default true
  const edge = { type:'knows' };
  s = F.initialState(['Person','Place']);
  s = F.reduce(s, {type:'TOGGLE_TYPE', doctype:'Place'});
  assert(F.isEdgeVisible(s, edge, 'Person', 'Place') === true, 'hidden endpoint but connectors visible → edge shown');
  s = F.reduce(s, {type:'TOGGLE_HIDDEN_CONNECTORS'});
  assert(F.isEdgeVisible(s, edge, 'Person', 'Place') === false, 'connectors hidden → edge hidden');
  assert(F.isEdgeVisible(s, edge, 'Person', 'Person') === true, 'both visible → edge shown');

  // RelType off hides edge
  s = F.reduce(s, {type:'TOGGLE_HIDDEN_CONNECTORS'});
  s.relTypes['knows'] = false;
  assert(F.isEdgeVisible(s, edge, 'Person', 'Person') === false, 'relType off hides edge');

  // URL hash round trip
  s = F.initialState(['Person','Institution','Place']);
  s = F.reduce(s, {type:'APPLY_PRESET',id:'people'});
  const h = F.encodeHash(s);
  const r = F.decodeHash(h);
  assert(r.types.Person === true && r.types.Place !== true, 'round-trip preserves Person, excludes others');

  // Arabic normalisation
  assert(F.normaliseText('أحمد') === 'احمد', 'alef normalised');
  assert(F.normaliseText('مدرسة') === 'مدرسه', 'ta marbuta normalised');
  assert(F.normaliseText('يسرى') === 'يسري', 'ya/alef maqsura normalised');

  // Search match
  s.search = 'احمد';
  assert(F.matchesSearch(s, 'أحمد'), 'search matches normalised Arabic');

  // countByType
  const points = [{doctype:'Person'},{doctype:'Person'},{doctype:'Place'}];
  const counts = F.countByType(points);
  assert(counts.Person === 2 && counts.Place === 1, 'countByType works');

  console.log('\nAll siraj-filters tests passed.');
}
run();
