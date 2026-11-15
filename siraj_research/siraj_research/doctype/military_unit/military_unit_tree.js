// Copyright (c) 2026, SIRAJ and contributors
// Navigate the hierarchy by document ID; create through the standard form.
frappe.provide("frappe.treeview_settings");
frappe.treeview_settings["Military Unit"] = {
	get_tree_root: false,
	get_tree_nodes: "siraj_research.treeview.get_children",
	disable_add_node: true,
	get_label(node) {
		const escape = (value) => frappe.utils.escape_html(String(value));
		if (node.is_root) return escape(node.label || __("Military Unit"));
		const data = node.data || {};
		const name = data.title || data.value || node.label || "";
		const details = [];
		const add = (label, value) => {
			if (value !== null && value !== undefined && value !== "") {
				details.push(`${escape(label)}: ${escape(value)}`);
			}
		};
		add(__("Echelon"), data.echelon ? __(data.echelon) : null);
		add(__("Status"), data.status ? __(data.status) : null);
		add(__("Business code"), data.unit_code);
		add(__("Direct personnel"), data.direct_personnel);
		if (data.value && data.value !== name) add(__("ID"), data.value);
		return `<strong dir="auto">${escape(name)}</strong>` +
			(details.length ? ` <span class="text-muted small" dir="auto"> · ${details.join(" · ")}</span>` : "");
	},
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
