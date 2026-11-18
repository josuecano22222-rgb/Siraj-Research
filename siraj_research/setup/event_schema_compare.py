"""Pure metadata comparison prototype; never queries or changes a Frappe site."""

from siraj_research.setup.event_transition_plan import PlanError

LAYOUT = {"Tab Break", "Section Break", "Column Break", "HTML", "Button", "Heading", "Fold"}
ATTRIBUTES = (
	"fieldtype",
	"options",
	"length",
	"precision",
	"permlevel",
	"read_only",
	"reqd",
	"unique",
	"default",
)
STANDARD = ("doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx")
CHILD_STANDARD = ("parent", "parentfield", "parenttype")
OPTIONAL_STANDARD = ("_user_tags", "_assign", "_liked_by", "_seen")


def _fields(meta):
	if not isinstance(meta, dict) or not isinstance(meta.get("fields"), list):
		raise PlanError("Invalid metadata")
	result = {}
	for field in meta["fields"]:
		if not isinstance(field, dict):
			raise PlanError("Invalid field")
		name, kind = field.get("fieldname"), field.get("fieldtype")
		if kind in LAYOUT:
			continue
		if not isinstance(name, str) or not name or not isinstance(kind, str) or not kind:
			raise PlanError("Invalid persisted or child field")
		if name in result:
			raise PlanError("Duplicate field name")
		result[name] = field
	return result


def compare_metadata(source, target):
	"""Compare proposed field mapping from supplied metadata, not database columns.

	Reports matching/missing/changed fields, new fields and reserved-name
	collisions. Equality of metadata does not establish data mapping or migration
	safety: actual columns, customization, constraints, links and ownership need
	independent inspection. Returns field metadata names but no record data.
	"""
	if (
		not isinstance(source, dict)
		or not isinstance(target, dict)
		or source.get("name") != "Event"
		or target.get("name") != "Research Event"
	):
		raise PlanError("Unexpected DocType identity")
	if source.get("module") != "Siraj Research" or target.get("module") != "Siraj Research":
		raise PlanError("Unexpected DocType ownership")
	a, b = _fields(source), _fields(target)
	mappings, target_only, reserved = (
		[],
		sorted(b.keys() - a.keys()),
		sorted((a.keys() | b.keys()) & set(STANDARD + CHILD_STANDARD + OPTIONAL_STANDARD)),
	)
	for name in sorted(a):
		if name not in b:
			mappings.append({"source": name, "target": None, "status": "missing", "differences": []})
			continue
		differences = [key for key in ATTRIBUTES if a[name].get(key) != b[name].get(key)]
		mappings.append(
			{
				"source": name,
				"target": name,
				"status": "changed" if differences else "same",
				"differences": differences,
			}
		)
	return {
		"mappings": mappings,
		"target_only_fields": target_only,
		"reserved_name_conflicts": reserved,
		"standard_fields_to_preserve": list(STANDARD),
		"selected_attributes_match": not target_only
		and not reserved
		and all(x["status"] == "same" for x in mappings),
		"warning": "Only selected metadata attributes compared; physical schema, rows, references and rollback were not inspected.",
	}
