// Exercise the shared virtual-root configuration without a Frappe bench.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const route = [];
const context = {
    frappe: {
        treeview_settings: {},
        provide() {},
        model: { can_read: () => true },
        set_route: (...args) => route.push(args),
    },
    __: value => value,
};
vm.runInNewContext(fs.readFileSync('siraj_research/public/js/tree_navigation.js', 'utf8'), context);
for (const type of ['Place', 'Military Unit', 'Command Region']) {
    const settings = context.frappe.treeview_settings[type];
    assert.strictEqual(settings.get_tree_root, false);
    assert.strictEqual(settings.get_tree_nodes, 'siraj_research.treeview.get_children');
    assert.strictEqual(settings.disable_add_node, true);
    const view = { make_tree() { this.made = true; } };
    settings.onload(view);
    assert.strictEqual(view.root_value, '');
    assert.strictEqual(view.made, true);
    assert.strictEqual(settings.toolbar[0].condition({ is_root: true }), false);
    settings.toolbar[0].click({ data: { value: 'record-id' } });
    assert.deepStrictEqual(route.pop(), ['Form', type, 'record-id']);
}
console.log('Tree virtual roots and navigation passed.');
