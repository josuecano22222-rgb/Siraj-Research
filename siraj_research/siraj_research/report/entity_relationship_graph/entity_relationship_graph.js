frappe.query_reports["Entity Relationship Graph"] = {
	"filters": [
		{
			"fieldname": "source_doctype",
			"label": __("Source Type"),
			"fieldtype": "Select",
			"options": "\nPerson\nInstitution\nPlace\nEvent\nMilitary Unit",
		},
		{
			"fieldname": "target_doctype",
			"label": __("Target Type"),
			"fieldtype": "Select",
			"options": "\nPerson\nInstitution\nPlace\nEvent\nMilitary Unit",
		},
		{
			"fieldname": "relationship_type",
			"label": __("Relationship Type"),
			"fieldtype": "Link",
			"options": "Relationship Type",
		},
	]
};
