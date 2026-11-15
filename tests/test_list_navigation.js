// Ensure list scripts exist for every standalone DocType with a review state.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '../siraj_research/siraj_research/doctype');
let checked = 0;
for (const slug of fs.readdirSync(root)) {
    const json = path.join(root, slug, `${slug}.json`);
    if (!fs.existsSync(json)) continue;
    const meta = JSON.parse(fs.readFileSync(json, 'utf8'));
    if (meta.istable || meta.issingle || !meta.fields.some(f => f.fieldname === 'workflow_state')) continue;
    const script = path.join(root, slug, `${slug}_list.js`);
    assert(fs.existsSync(script), `${meta.name} is missing its list script`);
    const context = { frappe: { listview_settings: {}, provide() {} }, __: s => s };
    vm.runInNewContext(fs.readFileSync(script, 'utf8'), context, { filename: script });
    const settings = context.frappe.listview_settings[meta.name];
    assert(settings, `${meta.name} settings are not registered`);
    assert(Array.from(settings.add_fields).includes('workflow_state'));
    assert.deepStrictEqual(Array.from(settings.get_indicator({ workflow_state: 'Draft' })),
        ['Draft', 'gray', 'workflow_state,=,Draft']);
    assert.deepStrictEqual(Array.from(settings.get_indicator({ workflow_state: 'Verified' })),
        ['Verified', 'green', 'workflow_state,=,Verified']);
    assert.strictEqual(settings.get_indicator({ workflow_state: '<img onerror=alert(1)>' }), undefined);
    assert.strictEqual(settings.get_indicator({ workflow_state: '__proto__' }), undefined);
    checked++;
}
assert(checked > 0, 'no eligible DocTypes found');
console.log(`Review-state list view settings passed for ${checked} DocTypes.`);
