// Copyright (c) 2026, SIRAJ and contributors
// For license information, please see license.txt
frappe.ui.form.on("Person", {
	// The military section is shown by `depends_on` in metadata; this only keeps the
	// tab title honest, because a hidden section still leaves a tab behind.
	refresh(frm) {
		frm.toggle_display("sb_military", frm.doc.category === "Military");
	},
});
