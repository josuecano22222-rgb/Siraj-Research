"""Pure formatting for SIRAJ document history (the audit view).

Frappe's ``Version`` rows carry a JSON payload: an insert marker
(``creation``/``created_by``) or a diff (``changed`` / ``added`` /
``removed`` / ``row_changed``). This module turns those payloads into
stable, human-readable entries **without touching Frappe** — permission
checks and field labels are the API layer's job (``api/audit.py``), which
decides which fields a caller may see before this formatting is exposed.

Internal framework bookkeeping fields (``modified``, ``idx``, ``docstatus``,
…) are always dropped: analysts care about research data, not row plumbing.
"""
from __future__ import annotations

import json
from typing import Any

#: Framework/structural fields that never belong in an audit diff.
NOISE_FIELDS = frozenset(
	{
		"modified",
		"modified_by",
		"idx",
		"docstatus",
		"owner",
		"creation",
		"name",
		"doctype",
		"__islocal",
		"__unsaved",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
	}
)


def _payload(data: Any) -> dict:
	"""Parse a Version ``data`` column (JSON string or already-decoded dict)."""
	if isinstance(data, dict):
		return data
	if not data:
		return {}
	try:
		parsed = json.loads(data)
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "1" if value else "0"
	if isinstance(value, str):
		return value
	if isinstance(value, int | float):
		return str(value)
	try:
		return json.dumps(value, ensure_ascii=False, sort_keys=True)
	except (TypeError, ValueError):  # pragma: no cover - exotic values
		return str(value)


def _rows_label(count: int) -> str:
	# Deliberately language-neutral: the API layer attaches labels, and a
	# row count is rendered by the client through __() with this shape.
	return f"{count} rows"


def _child_row_changes(table: Any, index: Any, sub: Any) -> list[dict]:
	out: list[dict] = []
	try:
		position = int(index) + 1
	except (TypeError, ValueError):
		position = 0
	for item in sub or []:
		if not isinstance(item, list | tuple) or len(item) < 3:
			continue
		field, old, new = str(item[0]), item[1], item[2]
		if field in NOISE_FIELDS or _text(old) == _text(new):
			continue
		out.append(
			{
				"field": f"{table}[{position}].{field}",
				"old": _text(old),
				"new": _text(new),
			}
		)
	return out


def _table_items(section: Any) -> list[tuple[str, int]]:
	out: list[tuple[str, int]] = []
	for item in section or []:
		if not isinstance(item, list | tuple) or not item:
			continue
		table = str(item[0])
		if table in NOISE_FIELDS:
			continue
		second = item[1] if len(item) > 1 else None
		try:
			count = len(second) if isinstance(second, list | tuple) else int(second)
		except (TypeError, ValueError):
			count = 0
		out.append((table, count))
	return out


def build_entries(rows: list[dict]) -> list[dict]:
	"""Turn raw Version rows (newest-first) into formatted audit entries.

	Each entry: ``{name, when, by, action, changes}`` where ``action`` is
	``created``/``updated`` and ``changes`` is a list of
	``{field, old, new}`` (child-table diffs are flattened to
	``table[i].field``). Entries whose payload is empty — or whose only
	changes are framework noise — are dropped entirely.
	"""
	entries: list[dict] = []
	for row in rows or []:
		data = _payload((row or {}).get("data"))
		if not data:
			continue
		changes: list[dict] = []
		action = "updated"
		if "created_by" in data or ("creation" in data and "updater_reference" in data):
			action = "created"
		for item in data.get("changed") or []:
			if not isinstance(item, list | tuple) or len(item) < 3:
				continue
			field, old, new = str(item[0]), item[1], item[2]
			if field in NOISE_FIELDS or _text(old) == _text(new):
				continue
			changes.append({"field": field, "old": _text(old), "new": _text(new)})
		for table, count in _table_items(data.get("added")):
			changes.append({"field": table, "old": "", "new": _rows_label(count)})
		for table, count in _table_items(data.get("removed")):
			changes.append({"field": table, "old": _rows_label(count), "new": ""})
		for item in data.get("row_changed") or []:
			if not isinstance(item, list | tuple) or len(item) < 4:
				continue
			changes.extend(_child_row_changes(item[0], item[2], item[3]))
		if action == "updated" and not changes:
			# Nothing but noise (or an unreadable payload): not an audit event.
			continue
		if action == "created":
			# The insert marker names the actual creator; the Version row's
			# owner is only the saving session (imports, background saves).
			by = data.get("created_by") or row.get("owner") or ""
		else:
			by = row.get("owner") or ""
		entries.append(
			{
				"name": str(row.get("name") or ""),
				"when": row.get("creation"),
				"by": by,
				"action": action,
				"changes": changes,
			}
		)
	return entries


def filter_visible(entries: list[dict], can_read_field) -> list[dict]:
	"""Drop changes (and whole entries) the caller may not read.

	``can_read_field(fieldname) -> bool`` is supplied by the API layer from
	the DocType's field-level permissions. ``created`` entries carry no
	field data and survive when the record itself is readable.
	"""
	out: list[dict] = []
	for entry in entries or []:
		if entry.get("action") == "created":
			out.append(dict(entry))
			continue
		visible = [c for c in entry.get("changes") or [] if can_read_field(c.get("field", ""))]
		if not visible:
			continue
		cloned = dict(entry)
		cloned["changes"] = visible
		out.append(cloned)
	return out
