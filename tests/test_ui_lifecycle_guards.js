// Dependency-free guards against repeated map mounts and hidden-modal focus.
const assert = require('assert');
const fs = require('fs');

const coordinates = fs.readFileSync('siraj_research/public/js/coordinate_map.js', 'utf8');
const compat = fs.readFileSync('siraj_research/public/js/siraj-compat.js', 'utf8');

assert(coordinates.includes('const mounting = new Map()'));
assert(coordinates.includes('if (!mounting.has(key))'));
assert(coordinates.includes('.finally(() => mounting.delete(key))'));
assert(coordinates.includes('state.frm === frm'));
assert(coordinates.includes('removeState(state)'));

assert(compat.includes('hide.bs.modal.sirajA11y'));
assert(compat.includes('this.contains(active)'));
assert(compat.includes('active.blur()'));

// F4: Explorer Network summary badge must handle int-or-"N+" inbound_count without string concatenation ("2200+").
const explorer = fs.readFileSync('siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.js', 'utf8');
assert(explorer.includes('formatNetworkTotal'), 'siraj_explorer.js must format network_summary totals via formatNetworkTotal');
const fnMatch = explorer.match(/function formatNetworkTotal\(ns\)\s*\{[\s\S]*?\n\}/);
assert(fnMatch, 'formatNetworkTotal helper must be defined at top level of siraj_explorer.js');
const formatNetworkTotal = new Function('return ' + fnMatch[0])();
assert.strictEqual(formatNetworkTotal({relationship_count: 1, outbound_count: 1, inbound_count: 3}), '5');
assert.strictEqual(formatNetworkTotal({relationship_count: 1, outbound_count: 1, inbound_count: '200+'}), '202+');
assert.strictEqual(formatNetworkTotal({}), '0');

console.log('UI lifecycle guards: map mounts are deduplicated, hidden modals release focus, and network totals handle N+ caps.');
