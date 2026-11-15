# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
frappe.ui.form.on("Military Unit", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Order of battle"), () => {
			frappe.route_options = { unit: frm.doc.name };
			frappe.set_route("query-report", "Order of Battle");
		}, __("View"));
	},
});
