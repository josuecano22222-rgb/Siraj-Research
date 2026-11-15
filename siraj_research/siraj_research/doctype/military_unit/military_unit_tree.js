// Copyright (c) 2026, SIRAJ and contributors
// Read-only hierarchy: keep the real document name separate from its title.
frappe.provide("frappe.treeview_settings");
frappe.treeview_settings["Military Unit"] = {
	get_tree_root: false,
	get_tree_nodes: "siraj_research.treeview.get_children",
	disable_add_node: true,
	onload(view) {
		view.root_label = __("Military Unit");
		view.root_value = "";
		view.make_tree();
	},
	toolbar: [{
		label: __("Open record"),
		condition: (node) => !node.is_root && frappe.model.can_read("Military Unit"),
		click: (node) => frappe.set_route("Form", "Military Unit", node.data.value),
	}],
};
