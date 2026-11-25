/* Node test for C-06: data_group_scope.js binds per scoped DocType without touching cur_frm at load time. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const scriptPath = path.join(__dirname, '..', 'siraj_research', 'public', 'js', 'data_group_scope.js');
const scriptSource = fs.readFileSync(scriptPath, 'utf8');

const hooksPath = path.join(__dirname, '..', 'siraj_research', 'hooks.py');
const hooksSource = fs.readFileSync(hooksPath, 'utf8');
const match = hooksSource.match(/SCOPED_DOCTYPES\s*=\s*\[([\s\S]*?)\]/);
assert.ok(match, 'SCOPED_DOCTYPES list must exist in siraj_research/hooks.py');
const expectedDoctypes = Array.from(match[1].matchAll(/"([^"]+)"/g), m => m[1]);
assert.ok(expectedDoctypes.length > 0, 'SCOPED_DOCTYPES must be non-empty');

const registered = new Map();
let curFrmAccessed = false;
const context = {
	frappe: {
		user_roles: [],
		ui: {
			form: {
				on(doctype, handlers) {
					registered.set(doctype, handlers);
				},
			},
		},
	},
};

Object.defineProperty(context, 'cur_frm', {
	get() {
		curFrmAccessed = true;
		return undefined;
	},
});

vm.createContext(context);
vm.runInContext(scriptSource, context);

assert.equal(curFrmAccessed, false, 'data_group_scope.js must not access cur_frm at load time');
assert.deepEqual(
	Array.from(registered.keys()).sort(),
	[...expectedDoctypes].sort(),
	'data_group_scope.js must bind every SCOPED_DOCTYPE from hooks.py',
);

for (const dt of expectedDoctypes) {
	const handlers = registered.get(dt);
	assert.equal(typeof handlers.refresh, 'function', `${dt} must register refresh handler`);
}

// Verify read_only toggling semantics across member vs official and new vs saved docs.
function runRefresh(doctype, roles, isNew) {
	context.frappe.user_roles = roles;
	const calls = [];
	registered.get(doctype).refresh({
		doctype,
		is_new: () => isNew,
		set_df_property(fieldname, prop, value) {
			calls.push({ fieldname, prop, value });
		},
	});
	assert.equal(calls.length, 1);
	assert.equal(calls[0].fieldname, 'data_group');
	assert.equal(calls[0].prop, 'read_only');
	return calls[0].value;
}

assert.equal(runRefresh('Person', ['SIRAJ Researcher'], true), true);
assert.equal(runRefresh('Person', ['SIRAJ Researcher'], false), true);
assert.equal(runRefresh('Person', ['SIRAJ Official'], true), false);
assert.equal(runRefresh('Person', ['SIRAJ Official'], false), true);
assert.equal(runRefresh('Shared Record', ['SIRAJ Official'], true), false);

console.log('data_group_scope.js: bound per scoped DocType without cur_frm at load time.');
