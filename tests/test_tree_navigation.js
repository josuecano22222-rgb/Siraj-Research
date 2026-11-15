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
            model: { can_read: () => true, can_create: () => true },
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
    const view = { can_create: true, page: { set_primary_action(label, action, icon) { this.action = action; this.label = label; this.icon = icon; } }, make_tree() { this.made = true; } };
    settings.onload(view);
    assert.strictEqual(view.root_value, '');
    assert.strictEqual(view.root_label, type);
    assert.strictEqual(view.made, true);
    assert.strictEqual(settings.toolbar[0].condition({ is_root: true }), false);
    assert.strictEqual(settings.toolbar[0].condition({ is_root: false }), true);
    settings.toolbar[0].click({ data: { value: 'record-id' } });
    assert.deepStrictEqual(route.pop(), ['Form', type, 'record-id']);
    if (type === 'Military Unit') {
        assert.strictEqual(view.page.label, 'New Military Unit');
        assert.strictEqual(view.page.icon, 'add');
        view.page.action();
        assert.deepStrictEqual(route.pop(), ['Form', type, 'new-military-unit']);
        assert.strictEqual(context.frappe.route_options, null);
        const child = settings.toolbar[1];
        assert.strictEqual(child.condition({is_root: true, expandable: true}), false);
        assert.strictEqual(child.condition({is_root: false, expandable: false}), false);
        assert.strictEqual(child.condition({is_root: false, expandable: true}), true);
        child.click({data: {value: 'unit-id'}});
        assert.strictEqual(context.frappe.route_options.parent_unit, 'unit-id');
        assert.deepStrictEqual(route.pop(), ['Form', type, 'new-military-unit']);
        context.frappe.model.can_create = () => false;
        assert.strictEqual(child.condition({is_root: false, expandable: true}), false);
        const denied = {can_create: false, page: {set_primary_action() { throw new Error('create exposed'); }}, make_tree() {}};
        settings.onload(denied);
    }
}
console.log('Per-DocType tree settings and navigation passed.');
