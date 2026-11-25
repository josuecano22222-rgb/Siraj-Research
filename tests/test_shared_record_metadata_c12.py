"""Metadata tests for C-12 (HD-3): Shared Record DocType permissions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_RECORD_JSON = ROOT / "siraj_research/siraj_research/doctype/shared_record/shared_record.json"


def test_shared_record_permissions_follow_hd3():
	spec = json.loads(SHARED_RECORD_JSON.read_text(encoding="utf-8"))
	perms = {row["role"]: row for row in spec["permissions"] if not row.get("permlevel")}

	expected_roles = {
		"SIRAJ Viewer",
		"SIRAJ Researcher",
		"SIRAJ Reviewer",
		"SIRAJ Administrator",
		"SIRAJ Official",
		"Group Member",
		"System Manager",
	}
	assert set(perms.keys()) == expected_roles

	# Viewer is strictly read-only within their Data Group.
	viewer = perms["SIRAJ Viewer"]
	assert viewer.get("read") == 1
	assert not viewer.get("write")
	assert not viewer.get("create")
	assert not viewer.get("delete")
	assert viewer.get("share") == 0

	# Researcher and Reviewer can read/write/create within their Data Group, no delete, share=0.
	for role in ("SIRAJ Researcher", "SIRAJ Reviewer"):
		p = perms[role]
		assert p.get("read") == 1
		assert p.get("write") == 1
		assert p.get("create") == 1
		assert not p.get("delete")
		assert p.get("share") == 0

	# SIRAJ Official has read/write/create across visible groups, share=0 (non-admin role).
	official = perms["SIRAJ Official"]
	assert official.get("read") == 1
	assert official.get("write") == 1
	assert official.get("create") == 1
	assert official.get("share") == 0

	# Group Member preserved for test_shared_record.py compatibility, share=0.
	gm = perms["Group Member"]
	assert gm.get("read") == 1
	assert gm.get("write") == 1
	assert gm.get("create") == 1
	assert gm.get("delete") == 1
	assert gm.get("share") == 0

	# Every non-admin role has share: 0 so Frappe DocShare cannot bypass Data Group isolation.
	admin_roles = {"SIRAJ Administrator", "System Manager"}
	for role, row in perms.items():
		if role not in admin_roles:
			assert row.get("share", 0) == 0, f"{role} must have share: 0"
