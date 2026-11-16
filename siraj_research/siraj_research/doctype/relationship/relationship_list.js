// Copyright (c) 2026, SIRAJ and contributors
// Presentation only; permissions and workflow rules remain server-side.
frappe.provide("frappe.listview_settings");
frappe.listview_settings["Relationship"] = {
	add_fields: ["workflow_state"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray", "In Review": "orange", "Verified": "green",
			"Published": "blue", "Needs Update": "orange", "Disputed": "red",
			"Archived": "gray", "Rejected": "red",
		};
		const state = doc.workflow_state;
		if (!Object.prototype.hasOwnProperty.call(colors, state)) return;
		return [__(state), colors[state], "workflow_state,=," + state];
	},
};
