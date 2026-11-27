// Keep section membership server-controlled for members while allowing an
// official to choose a section on a brand-new record.
(function () {
	if (typeof frappe !== "undefined" && frappe._sirajDataGroupScopeBound) {
		return;
	}
	if (typeof frappe !== "undefined") {
		frappe._sirajDataGroupScopeBound = true;
	}

	const SCOPED_DOCTYPES = [
		"Command Appointment",
		"Institution",
		"Institution Event",
		"Institution Location",
		"Institution Military Unit",
		"Military Unit",
		"Military Unit Event",
		"Military Unit Institution",
		"Military Unit Location",
		"Mission",
		"Operational Deployment",
		"Person",
		"Person Event",
		"Person Institution",
		"Person Location",
		"Person Military Unit",
		"Person Position",
		"Place",
		"Relationship",
		"Shared Record",
		"Siraj Event",
		"Siraj Event Institution",
		"Siraj Event Location",
		"Siraj Event Military Unit",
		"Siraj Event Person",
		"Source",
		"Training Exercise",
	];

	function syncDataGroupReadOnly(frm) {
		const roles = Array.isArray(frappe.user_roles) ? frappe.user_roles : [];
		const isOfficial = roles.includes("SIRAJ Official");
		frm.set_df_property("data_group", "read_only", !(isOfficial && frm.is_new()));
	}

	for (const doctype of SCOPED_DOCTYPES) {
		frappe.ui.form.on(doctype, {
			refresh: syncDataGroupReadOnly,
		});
	}
})();
