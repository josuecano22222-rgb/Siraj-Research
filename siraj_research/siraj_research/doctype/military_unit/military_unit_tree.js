// Copyright (c) 2026, SIRAJ and contributors
// Navigate the hierarchy by document ID; create through the standard form.
frappe.provide("frappe.treeview_settings");
frappe.treeview_settings["Military Unit"] = {
	get_tree_root: false,
	get_tree_nodes: "siraj_research.treeview.get_children",
	disable_add_node: true,
	onload(view) {
		view.root_label = __("Military Unit");
		view.root_value = "";
		view.make_tree();
		if (view.can_create) {
			view.page.set_primary_action(__("New Military Unit"), () => {
				frappe.route_options = null;
				frappe.set_route("Form", "Military Unit", "new-military-unit");
			}, "add");
		}
	},
	toolbar: [{
		label: __("Open record"),
		condition: (node) => !node.is_root && frappe.model.can_read("Military Unit"),
		click: (node) => frappe.set_route("Form", "Military Unit", node.data.value),
	}, {
		label: __("Add child"),
		condition: (node) => !node.is_root && node.expandable && frappe.model.can_create("Military Unit"),
		click: (node) => {
			frappe.route_options = { parent_unit: node.data.value };
			frappe.set_route("Form", "Military Unit", "new-military-unit");
		},
	}],
};
