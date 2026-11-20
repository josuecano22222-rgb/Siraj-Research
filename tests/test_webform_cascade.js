/* Web Form cascade adapter regression test — Node only, mocked Frappe. */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'siraj_research/public/js/siraj-cascade-webform.js'),
  'utf8'
);

function makeForm(values) {
  const field = () => ({ df: { fieldtype: 'Link' }, refresh() {} });
  return {
    fields_dict: {
      country: field(), governorate: field(), district: field(), village: field(),
    },
    doc: { ...values },
    values: { ...values },
    queries: {},
    props: [],
    handlers: {},
    get_value(name) { return this.values[name] || ''; },
    set_value(name, value) { this.values[name] = value; },
    set_query(name, getter) { this.queries[name] = getter(); },
    set_df_property(name, prop, value) { this.props.push([name, prop, value]); },
    on(name, handler) { this.handlers[name] = handler; },
  };
}

function load(frm, message) {
  const frappe = {
    web_form: frm,
    call(opts) { opts.callback({ message }); },
  };
  const sandbox = { window: { frappe }, frappe, console, setTimeout };
  vm.runInNewContext(source, sandbox, { filename: 'siraj-cascade-webform.js' });
  return sandbox;
}

// --- attach: ancestor filters, not empty dropdowns -------------------------
let frm = makeForm({ country: 'IQ' });
load(frm, { levels: [{ field: 'country', is_active: true }, { field: 'village', is_active: false }] });

assert.strictEqual(JSON.stringify(frm.queries.governorate.filters), JSON.stringify({ country: 'IQ' }));
assert.strictEqual(JSON.stringify(frm.queries.district.filters), JSON.stringify({ country: 'IQ' }));
assert.ok(frm.handlers.governorate, 'governorate change handler registered');

// Inactive village is hidden and cleared.
assert.strictEqual(JSON.stringify(frm.props.find(p => p[0] === 'village' && p[1] === 'hidden')), JSON.stringify(['village', 'hidden', 1]));
assert.strictEqual(frm.values.village || '', '');

// --- changing a parent clears its descendants -----------------------------
frm = makeForm({ country: 'IQ', governorate: 'IQ-BG', district: 'IQ-BG-KR', village: 'Al-Karrada' });
load(frm, { levels: [] });
frm.handlers.governorate('governorate', 'IQ-BG');
assert.strictEqual(frm.values.district, '', 'district cleared with its parent');
assert.strictEqual(frm.values.village, '', 'village cleared with its parent');
assert.strictEqual(frm.values.governorate, 'IQ-BG', 'changed level preserved');

// Changing country clears everything below it, including the governorate.
frm = makeForm({ country: 'IQ', governorate: 'IQ-BG', district: 'IQ-BG-KR' });
load(frm, { levels: [] });
frm.handlers.country('country', 'JO');
assert.strictEqual(frm.values.governorate, '');
assert.strictEqual(frm.values.district, '');

// --- filters stay scoped after a change -----------------------------------
frm = makeForm({ country: 'IQ', governorate: 'IQ-BG' });
load(frm, { levels: [] });
assert.strictEqual(frm.queries.municipality, undefined, 'absent field ignored');
assert.strictEqual(JSON.stringify(frm.queries.district.filters), JSON.stringify({ country: 'IQ', governorate: 'IQ-BG' }));

// --- no fields / no web form: adapter stays inert but importable ---------
const sandbox = load(makeForm({}), { levels: [] });
assert.strictEqual(typeof sandbox.window.SirajWebFormCascade, 'object');
assert.strictEqual(typeof sandbox.window.SirajWebFormCascade.attach, 'function');
const noForm = { call() {} };
const inert = { window: { frappe: noForm }, frappe: noForm, console, setTimeout };
vm.runInNewContext(source, inert, { filename: 'siraj-cascade-webform.js' });
assert.strictEqual(typeof inert.window.SirajWebFormCascade.apply, 'function');

console.log('Web Form cascade: filters, descendant clearing, inactive levels passed.');
