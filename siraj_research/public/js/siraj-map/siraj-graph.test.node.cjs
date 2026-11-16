/* Node-only unit test for siraj-graph pure functions.
 * Run: node public/js/siraj-map/siraj-graph.test.node.cjs */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const metaSrc = fs.readFileSync(path.join(__dirname, '../siraj-record-meta.js'), 'utf8');
const kitSrc  = fs.readFileSync(path.join(__dirname, '../siraj-map-kit.js'), 'utf8');
const graphSrc = fs.readFileSync(path.join(__dirname, 'siraj-graph.js'), 'utf8');

const sandbox = { window:{}, console, setTimeout,
  document:{ createElement:()=>({style:{},classList:{add(){},remove(){}},setAttribute(){},appendChild(){},addEventListener(){}}),body:{appendChild(){}} },
  frappe:{_:s=>s}, L:{} };
sandbox.__ = s=>s;
vm.createContext(sandbox);
vm.runInContext(metaSrc, sandbox);
vm.runInContext(kitSrc, sandbox);
vm.runInContext(graphSrc, sandbox);

const S = sandbox.window.SirajGraph;
function assert(c,m){ if(!c){console.error('FAIL:',m);process.exit(1);} console.log(' ok -',m); }

// Graph expressed with string IDs (matches graph module signature).
const edges = [
  { name:'e1', source:'a', target:'b', type:'knows' },
  { name:'e2', source:'b', target:'c', type:'knows' },
  { name:'e3', source:'c', target:'d', type:'knows' },
  { name:'e4', source:'b', target:'e', type:'knows' },
];
const adj = S.buildAdjacency(edges);
assert(adj.get('a').length === 1 && adj.get('a')[0].other === 'b', 'a is adjacent to b');
assert(adj.get('b').length === 3, 'b has 3 neighbours');

const ego1 = S.egoNetwork(adj, 'a', 1);
assert(ego1.nodes.size === 2, 'depth-1 ego contains 2 nodes (a+b), got '+ego1.nodes.size);
assert(ego1.edges.size === 1, 'depth-1 ego contains 1 edge');
assert(ego1.truncated === false, 'no truncation');

const ego2 = S.egoNetwork(adj, 'a', 2);
assert(ego2.nodes.size === 4, 'depth-2 ego contains 4 nodes (a,b,c,e), got '+ego2.nodes.size);

const capped = S.egoNetwork(adj, 'a', 3, {maxNodes:3});
assert(capped.truncated, 'ego caps when maxNodes exceeded');

const sp = S.shortestPath(adj, 'a', 'e');
assert(Array.isArray(sp) && sp.length === 2 && sp[0].name==='e1' && sp[1].name==='e4', 'shortestPath a->e = e1,e4');

assert(S.nodeId({doctype:'Person',name:'X'}) === S.nodeId({doctype:'Person',name:'X'}), 'nodeId stable');
assert(S.nodeId({doctype:'Person',name:'X'}) !== S.nodeId({doctype:'Person',name:'Y'}), 'nodeId distinguishes names');

const mid = S.offsetEdge({lat:0,lng:0},{lat:1,lng:1},0,2);
assert(typeof mid.lat === 'number' && typeof mid.lng === 'number', 'offsetEdge returns numeric control point');
assert(S.offsetEdge({lat:0,lng:0},{lat:1,lng:1},0,1) === null, 'offsetEdge returns null for single edge');

// Registry coverage: every TOOL_SPEC icon key resolves.
const tools = sandbox.window.sirajIcons.tools;
let missing = 0;
sandbox.window.SirajMapKit.TOOL_SPEC.forEach(spec => { if (!tools[spec.icon]) { console.error('  missing icon:', spec.key, spec.icon); missing++; } });
assert(missing === 0, 'every TOOL_SPEC icon resolves in the tool registry ('+sandbox.window.SirajMapKit.TOOL_SPEC.length+' tools)');

console.log('\nAll siraj-graph tests passed.');
