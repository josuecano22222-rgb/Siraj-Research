// Shared read-only tree navigation. A virtual root handles an empty registry
// without inventing a database record or relying on a single real root.
frappe.provide("frappe.treeview_settings");
["Place", "Military Unit", "Command Region"].forEach((doctype) => {
	frappe.treeview_settings[doctype] = {
		get_tree_root: false,
		get_tree_nodes: "siraj_research.treeview.get_children",
		disable_add_node: true,
		onload(view) {
			view.root_label = __(doctype);
			view.root_value = "";
			view.make_tree();
		},
		// Create or change records through the normal form, not treeview's
		// generic add_node which assumes a different parent-field name.
		toolbar: [{
			label: __("Open record"),
			condition: (node) => !node.is_root && frappe.model.can_read(doctype),
			click: (node) => frappe.set_route("Form", doctype, node.data.value),
		}],
	};
});
