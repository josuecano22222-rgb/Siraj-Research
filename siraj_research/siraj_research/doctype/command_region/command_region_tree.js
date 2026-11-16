// Copyright (c) 2026, SIRAJ and contributors
// Read-only hierarchy: keep the real document name separate from its title.
frappe.provide("frappe.treeview_settings");
frappe.treeview_settings["Command Region"] = {
	get_tree_root: false,
	get_tree_nodes: "siraj_research.treeview.get_children",
	disable_add_node: true,
	onload(view) {
		view.root_label = __("Command Region");
		view.root_value = "";
		view.make_tree();
	},
	toolbar: [{
		label: __("Open record"),
		condition: (node) => !node.is_root && frappe.model.can_read("Command Region"),
		click: (node) => frappe.set_route("Form", "Command Region", node.data.value),
	}],
};
