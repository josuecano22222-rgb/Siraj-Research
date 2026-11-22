// Copyright (c) 2026, SIRAJ and contributors
// For license information, please see license.txt
frappe.ui.form.on("Person", {
	// The military section is shown by `depends_on` in metadata; this only keeps the
	// tab title honest, because a hidden section still leaves a tab behind.
	refresh(frm) {
		frm.toggle_display("sb_military", frm.doc.category === "Military");
		refresh_grandchild_options(frm);
	},
	marital_status(frm) {
		if (frm.doc.marital_status === "Single") {
			// Hidden sections keep their data — say so out loud.
			frm.dashboard.add_comment(
				__("Family details are hidden while Single — they are kept; switch back to Married to review them."),
				null,
				true
			);
		}
		refresh_grandchild_options(frm);
	},
	children_add(frm) {
		refresh_grandchild_options(frm);
	},
	children_remove(frm) {
		refresh_grandchild_options(frm);
	},
});

frappe.ui.form.on("Person Child", {
	child_name(frm) {
		refresh_grandchild_options(frm);
	},
});

// The grandchild "Through" column asks which of this person's children the
// grandchild descends from — options come straight from the Children table.
function refresh_grandchild_options(frm) {
	const df = frappe.meta.get_docfield("Person Grandchild", "through_child", frm.doc.name);
	if (!df) return;
	const names = (frm.doc.children || []).map((row) => row.child_name).filter(Boolean);
	df.options = [""].concat(names).join("\n");
}
