frappe.query_reports["Entity Relationship Graph"] = {
	filters: [
		{ fieldname: "subject_type", label: __("Subject type"), fieldtype: "Select", options: "\nPerson\nInstitution\nPlace\nEvent\nSource" },
		{ fieldname: "object_type", label: __("Object type"), fieldtype: "Select", options: "\nPerson\nInstitution\nPlace\nEvent\nSource" },
		{ fieldname: "relationship_type", label: __("Relationship Type"), fieldtype: "Link", options: "Relationship Type" },
	],
};
