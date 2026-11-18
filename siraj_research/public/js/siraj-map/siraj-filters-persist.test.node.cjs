/* Node tests for SirajFilters persistence + legacy-hash migration.
 * Run: node public/js/siraj-map/siraj-filters-persist.test.node.cjs */
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const ROOT = path.resolve(__dirname, '../../..');
const storage = {};
const fakeWindow = { location: { pathname:'/app/siraj-explorer', search:'', hash:'#sf=UGVyc29uLFBsYWNl', href:'/app/siraj-explorer#sf=UGVyc29uLFBsYWNl' },
  history: { replaceState(_1,_2,u){
    const url = new URL(u, 'http://x');
    fakeWindow.location.href = u;
    fakeWindow.location.pathname = url.pathname;
    fakeWindow.location.search = url.search;
    fakeWindow.location.hash = url.hash;
  } } };
function makeCtx() {
  const sb = { window:fakeWindow, console, setTimeout, document:{createElement:()=>({style:{},classList:{add(){},remove(){}},setAttribute(){},appendChild(){},addEventListener(){}}),body:{appendChild(){}}},
    frappe:{_:s=>s,boot:{siraj_record_meta:{colours:{},glyphs:{}}}}, L:{DomEvent:{on:()=>{}}},
    btoa:s=>Buffer.from(s,'binary').toString('base64'), atob:s=>Buffer.from(s,'base64').toString('binary'),
    localStorage:{_d:storage,getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=v;},removeItem(k){delete this._d[k];}} };
  sb.__=s=>s; sb.encodeURIComponent=encodeURIComponent; sb.decodeURIComponent=decodeURIComponent; sb.escape=escape; sb.unescape=unescape;
  vm.createContext(sb);
  ['public/js/siraj-record-meta.js','public/js/siraj-map/siraj-graph.js','public/js/siraj-map/siraj-filters.js'].forEach(f=>
    vm.runInContext(fs.readFileSync(path.join(ROOT,f),'utf8'),sb));
  return sb;
}
function assert(c,m){ if(!c){console.error('FAIL:',m);process.exit(1);} console.log(' ok -',m); }

function run() {
  const sb = makeCtx();
  const F = sb.window.SirajFilters;
  assert(!F.HASH_KEY, 'HASH_KEY not exported (hash persistence removed)');
  assert(typeof F.saveState === 'function', 'saveState exported');
  assert(typeof F.migrateLegacyHash === 'function', 'migrateLegacyHash exported');

  // Legacy hash migration strips "#sf=Person,Place" without reload.
  fakeWindow.location.pathname='/app/siraj-explorer'; fakeWindow.location.search=''; fakeWindow.location.hash='#sf=UGVyc29uLFBsYWNl';
  F.migrateLegacyHash();
  assert(fakeWindow.location.hash.indexOf('sf=') === -1, 'migrateLegacyHash strips #sf= from URL');

  // localStorage round-trip.
  const types = ['Person','Place','Institution'];
  let s = F.initialState(types, 'geography');
  assert(F.isTypeVisible(s,'Person'), 'initial shows all types');
  s = F.reduce(s, {type:'TOGGLE_TYPE', doctype:'Place'});
  assert(!F.isTypeVisible(s,'Place'), 'Place hidden after toggle');
  F.saveState(s, 'geography');
  const s2 = F.initialState(types, 'geography');
  assert(s2.types.Place === false, 'state restored from localStorage (Place still hidden)');

  // Unknown new DocTypes that appear after save default-on.
  const s3 = F.initialState(['Person','Place','Institution','Military Unit'], 'geography');
  assert(s3.types['Military Unit'] === true, 'new DocType added since save defaults on');

  console.log('\nAll siraj-filters persistence tests passed.');
}
run();
