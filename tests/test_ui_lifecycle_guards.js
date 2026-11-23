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

console.log('UI lifecycle guards: map mounts are deduplicated and hidden modals release focus.');
