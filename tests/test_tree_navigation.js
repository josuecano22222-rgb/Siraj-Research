// Verify every tree DocType's standard Frappe *_tree.js configuration.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '..');
const doctypes = [['place', 'Place'], ['military_unit', 'Military Unit'], ['command_region', 'Command Region']];
for (const [slug, type] of doctypes) {
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
    const file = path.join(root, 'siraj_research/siraj_research/doctype', slug, `${slug}_tree.js`);
    vm.runInNewContext(fs.readFileSync(file, 'utf8'), context, { filename: file });
    const settings = context.frappe.treeview_settings[type];
    assert(settings, `missing settings for ${type}`);
    assert.strictEqual(settings.get_tree_root, false);
    assert.strictEqual(settings.get_tree_nodes, 'siraj_research.treeview.get_children');
    assert.strictEqual(settings.disable_add_node, true);
    const view = { make_tree() { this.made = true; } };
    settings.onload(view);
    assert.strictEqual(view.root_value, '');
    assert.strictEqual(view.root_label, type);
    assert.strictEqual(view.made, true);
    assert.strictEqual(settings.toolbar[0].condition({ is_root: true }), false);
    assert.strictEqual(settings.toolbar[0].condition({ is_root: false }), true);
    settings.toolbar[0].click({ data: { value: 'record-id' } });
    assert.deepStrictEqual(route.pop(), ['Form', type, 'record-id']);
}
console.log('Per-DocType tree settings and navigation passed.');
