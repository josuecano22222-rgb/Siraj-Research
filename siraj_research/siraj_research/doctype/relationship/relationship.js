// Copyright (c) 2026, SIRAJ and contributors
// For license information, please see license.txt
frappe.ui.form.on("Relationship", {
	refresh(frm) {
		if (!frm.doc.subject || !frm.doc.object || !frm.perm[0].write) return;
		frm.add_custom_button(__("Swap Source & Target"), async () => {
			const subjectType = frm.doc.subject_type;
			const subject = frm.doc.subject;
			const objectType = frm.doc.object_type;
			const object = frm.doc.object;
			await frm.set_value("subject_type", objectType);
			await frm.set_value("object_type", subjectType);
			await frm.set_value("subject", object);
			await frm.set_value("object", subject);
		});
	},
});
