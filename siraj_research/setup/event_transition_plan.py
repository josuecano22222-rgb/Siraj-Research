"""Pure Event transition planning prototype. Not a Frappe migration or endpoint.

Inputs are a manually reviewed inventory, not a site scan. Results can contain
sensitive record identifiers and must stay protected. This module performs no
I/O and never changes a database, files, DocTypes or the inputs.
"""
from collections import Counter

OLD_TYPE = "Event"
NEW_TYPE = "SIRAJ Research Event"


class PlanError(ValueError):
    """An incomplete, ambiguous or conflicting candidate must not be planned."""


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def prepare_transition(events, references, existing_target_names):
    """Plan name-preserving research copies and polymorphic-reference changes.

    `events`: list of {name, classification} where classification is explicitly
    'research' or 'calendar'. `references`: list of {doctype, name, type_field,
    name_field, type_value, target, classification}; each models one observed
    type/name pair already pointing to Event. `existing_target_names`: full set
    of names already present in the proposed target DocType (including orphans).

    This is deliberately a limited mechanical prototype. It does not inspect
    Frappe, prove inventory completeness, transform/copy rows, handle direct
    Links, scripts, property setters, attachments or children automatically,
    generate SQL, restore core metadata, perform rollback, or authorize a run.
    A supplied reference may model a child or attachment only after its actual
    field pair and ownership have independently been reviewed. The caller must
    inventory *all* other dependencies separately; zero planned entries means
    only that the supplied inputs had none.
    """
    if not isinstance(events, list) or not isinstance(references, list) or not isinstance(existing_target_names, (list, tuple, set)):
        raise PlanError("Invalid inventory container")
    if any(not _text(name) for name in existing_target_names):
        raise PlanError("Invalid existing target name")
    target_names = set(existing_target_names)
    classes = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != {"name", "classification"}:
            raise PlanError("Invalid event inventory entry")
        name, classification = event["name"], event["classification"]
        if not _text(name) or classification not in ("research", "calendar"):
            raise PlanError("Unclassified or invalid event")
        if name in classes:
            raise PlanError("Duplicate event name")
        if classification == "research" and name in target_names:
            raise PlanError("Research target name already exists")
        classes[name] = classification

    required = {"doctype", "name", "type_field", "name_field", "type_value", "target", "classification"}
    references_seen, fields_seen, changes = set(), set(), []
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != required:
            raise PlanError("Invalid reference inventory entry")
        if any(not _text(ref[key]) for key in required):
            raise PlanError("Invalid reference value")
        if ref["type_value"] != OLD_TYPE or ref["type_field"] == ref["name_field"]:
            raise PlanError("Unsupported reference shape")
        key = (ref["doctype"], ref["name"], ref["type_field"])
        if key in references_seen:
            raise PlanError("Duplicate or conflicting reference field")
        references_seen.add(key)
        fields = {(ref["doctype"], ref["name"], ref["type_field"]),
                  (ref["doctype"], ref["name"], ref["name_field"])}
        if fields_seen.intersection(fields):
            raise PlanError("Reference fields overlap")
        fields_seen.update(fields)
        if ref["target"] not in classes or ref["classification"] != classes[ref["target"]]:
            raise PlanError("Orphaned or ambiguously classified reference")
        if ref["classification"] == "research":
            changes.append({"doctype": ref["doctype"], "name": ref["name"],
                            "type_field": ref["type_field"], "name_field": ref["name_field"],
                            "expected_type": OLD_TYPE, "expected_target": ref["target"],
                            "new_type": NEW_TYPE})

    copies = [{"source_type": OLD_TYPE, "source_name": name,
               "target_type": NEW_TYPE, "target_name": name}
              for name in sorted(classes) if classes[name] == "research"]
    changes.sort(key=lambda x: (x["doctype"], x["name"], x["type_field"]))
    counts = Counter(classes.values())
    return {"candidate_copies": copies, "candidate_reference_changes": changes,
            "counts": {"research_events": counts["research"], "calendar_events": counts["calendar"],
                       "references_reviewed": len(references), "reference_changes": len(changes)},
            "warning": ("Partial candidate only: supplied inventory and ownership are not verified. "
                        "No records, references or metadata were changed; this is not migration approval.")}
