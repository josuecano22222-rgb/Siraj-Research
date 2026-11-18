"""Frappe v15 Event compatibility contract on caller-supplied metadata.

No Frappe import, hooks, endpoint, metadata writes or migration. These selected
fields cannot certify a site or its installed framework version.
"""

from siraj_research.setup.event_transition_plan import PlanError

CORE_TYPE = "Event"
RESEARCH_TYPE = "Research Event"
# Selected requirements from Frappe v15.126.1; not a complete core schema.
CORE_FIELDS = {
	"subject": ("Small Text", None),
	"event_type": ("Select", "Private\nPublic"),
	"starts_on": ("Datetime", None),
	"event_participants": ("Table", "Event Participants"),
	"sync_with_google_calendar": ("Check", None),
	"google_calendar": ("Link", "Google Calendar"),
}
RESEARCH_FIELDS = {
	"title_ar": ("Data", None),
	"event_type": ("Link", "Event Type"),
	"evidence": ("Table", "Evidence"),
	"external_identifiers": ("Table", "External Identifier"),
}


def _check(meta, name, module, requirements):
	issues = []
	if (
		not isinstance(meta, dict)
		or meta.get("name") != name
		or meta.get("module") != module
		or not isinstance(meta.get("fields"), list)
	):
		return [{"kind": "identity_or_owner_mismatch", "doctype": name}]
	fields = {}
	for row in meta["fields"]:
		if (
			not isinstance(row, dict)
			or not isinstance(row.get("fieldname"), str)
			or not row["fieldname"]
			or row["fieldname"] in fields
		):
			raise PlanError("Invalid or duplicate DocField in compatibility metadata")
		fields[row["fieldname"]] = row
	for field, (kind, options) in requirements.items():
		current = fields.get(field)
		if not current:
			issues.append({"kind": "missing_contract_field", "doctype": name, "field": field})
		elif current.get("fieldtype") != kind or (options is not None and current.get("options") != options):
			issues.append({"kind": "incompatible_contract_field", "doctype": name, "field": field})
	return issues


def inspect(core, research):
	"""Report selected identity and hook-sensitive contract conflicts, no I/O."""
	issues = _check(core, CORE_TYPE, "Desk", CORE_FIELDS) + _check(
		research, RESEARCH_TYPE, "Siraj Research", RESEARCH_FIELDS
	)
	return {
		"core_type": CORE_TYPE,
		"research_type": RESEARCH_TYPE,
		"issues": issues,
		"selected_contracts_match": not issues,
		"execution_ready": False,
		"warning": "Selected v15 metadata only. Installed versions, hook overrides, schemas, records, permissions and integrations remain unverified.",
	}


def research_identity(core, research):
	"""Return distinct type only if selected metadata contracts match.

	       Candidate adapter for future integration
	never silently aliases research
	       records to framework Event. It cannot authorize a migration or records.
	"""
	if inspect(core, research)["issues"]:
		raise PlanError("Event metadata compatibility contract failed")
	return RESEARCH_TYPE
