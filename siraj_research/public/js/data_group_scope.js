// Keep section membership server-controlled for members while allowing an
// official to choose a section on a brand-new record.
frappe.ui.form.on(cur_frm.doctype, {
	refresh(frm) {
		const isOfficial = frappe.user_roles.includes("SIRAJ Official");
		frm.set_df_property("data_group", "read_only", !(isOfficial && frm.is_new()));
	},
});
