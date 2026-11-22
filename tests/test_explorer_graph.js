#!/usr/bin/env node
/**
 * Phase 4 relationship-graph contracts (Node only).
 *
 * Asserts, against the shipped Explorer source, that the graph gained:
 *  - relationship-code + confidence-level edge labels (authentication_level),
 *  - a node-limit control (default 400, "All records" option),
 *  - on-demand node expansion via get_entity_network,
 *  - a bumped SIRAJ_EXPLORER_BUILD cache-buster.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(
	path.join(__dirname, '..', 'siraj_research', 'siraj_research', 'page', 'siraj_explorer', 'siraj_explorer.js'),
	'utf8'
);

let failed = 0;
const assert = (cond, msg) => {
	if (cond) {
		console.log('ok - ' + msg);
	} else {
		failed += 1;
		console.error('not ok - ' + msg);
	}
};

assert(
	/src SIRAJ_EXPLORER_BUILD|const SIRAJ_EXPLORER_BUILD = '2026-11-18\.phase4\.graph/.test(src) ||
		/const SIRAJ_EXPLORER_BUILD = '[^']*phase4\.graph/.test(src),
	'SIRAJ_EXPLORER_BUILD carries the phase4.graph marker'
);
assert(
	src.includes("label: [e.type, e.authentication_level].filter(Boolean).join(' · ')"),
	'edge labels combine relationship code with authentication (confidence) level'
);
assert(
	src.includes("aria-label', __('Node limit')") || src.includes("__('Node limit')"),
	'node-limit control is labelled'
);
assert(
	src.includes("[[100, '100'], [250, '250'], [400, '400'], [1000, '1000'], [0, __('All records')]]"),
	'node-limit offers 100/250/400/1000/All options with default 400'
);
assert(
	src.includes('nodeLimit = 400'),
	'node limit defaults to 400'
);
assert(
	src.includes('Node limit reached: showing {0} of {1} records.'),
	'truncation is reported in the status note'
);
assert(
	src.includes("method: 'siraj_research.api.map_relations.get_entity_network'") &&
		src.includes('expandNode'),
	'on-demand expansion calls get_entity_network'
);
assert(
	src.includes('sx-conn-expand'),
	'selected-node panel offers the Expand button'
);
assert(
	src.includes("data.nodes.push(n)") && src.includes("data.edges.push(e)"),
	'expansion merges new records and edges into the loaded graph'
);

if (failed) {
	console.error(`\n${failed} explorer graph contract(s) failed.`);
	process.exit(1);
}
console.log('\nExplorer graph contracts passed (Node only).');
