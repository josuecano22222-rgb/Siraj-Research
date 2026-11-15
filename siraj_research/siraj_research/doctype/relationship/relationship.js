// Copyright (c) 2026, SIRAJ and contributors
// For license information, please see license.txt

frappe.ui.form.on("Relationship", {
	refresh(frm) {
		if (!frm.is_new() || (frm.doc.source_docname && frm.doc.target_docname)) {
			frm.add_custom_button(__("Swap Source & Target"), () => {
				const src_dt = frm.doc.source_doctype;
				const src_dn = frm.doc.source_docname;
				frm.set_value("source_doctype", frm.doc.target_doctype);
				frm.set_value("source_docname", frm.doc.target_docname);
				frm.set_value("target_doctype", src_dt);
				frm.set_value("target_docname", src_dn);
			});
		}
	},
});
