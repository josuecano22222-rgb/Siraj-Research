"""Opt-in aggregate imagery metadata inventory; never an HTTP endpoint.

Reads site metadata only after explicit isolated-site approval. Does not fetch
URLs or read file content. Counts can still be sensitive
 custom hooks and bench
execution may have side effects. This is not proof of rights or exhaustive.
"""

from collections import Counter
from urllib.parse import urlsplit

import frappe

DOCTYPES = ("Person", "Institution", "Place", "Research Event", "Military Unit")
PAGE_SIZE = 200
LIMIT = 5000
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".avif", ".tif", ".tiff"}


def _bucket(value):
	if value is None or value == "":
		return "empty"
	if not isinstance(value, str) or len(value) > 8192:
		return "invalid"
	try:
		parts = urlsplit(value)
		if parts.scheme.lower() in ("http", "https") and parts.netloc:
			return "external_http"
		if not parts.scheme and not parts.netloc and parts.path.startswith("/"):
			return "site_relative"
		return "other"
	except ValueError:
		return "invalid"


def _image_type(value):
	if not isinstance(value, str):
		return "unknown_or_other"
	try:
		name = urlsplit(value).path.lower()
	except ValueError:
		return "unknown_or_other"
	ext = "." + name.rsplit(".", 1)[-1] if "." in name.rsplit("/", 1)[-1] else ""
	return ext[1:] if ext in IMAGE_EXTENSIONS else "unknown_or_other"


def _pages(doctype, fields):
	last = None
	scanned = 0
	while scanned <= LIMIT:
		size = min(PAGE_SIZE, LIMIT - scanned + 1)
		rows = frappe.get_all(
			doctype,
			fields=["name", *fields],
			filters={"name": [">", last]} if last is not None else {},
			order_by="name asc",
			limit_page_length=size,
		)
		if not rows:
			return
		for row in rows:
			if (
				any(field not in row for field in ("name", *fields))
				or not isinstance(row["name"], str)
				or not row["name"]
				or (last is not None and row["name"] <= last)
			):
				raise ValueError("Incomplete or unstable inventory page")
			last = row["name"]
			scanned += 1
			if scanned > LIMIT:
				yield None
				return
			yield row
		if len(rows) < size:
			return


def inspect(confirm=None):
	"""Bounded aggregate File and known image_url field scan, no URL output."""
	if confirm != "ISOLATED-TEST-APPROVED":
		raise ValueError("Explicit isolated test confirmation required")
	if getattr(frappe.session, "user", None) != "Administrator":
		raise PermissionError("Administrator required")
	counts = Counter()
	truncated = False
	for row in _pages("File", ["file_url", "is_private"]):
		if row is None:
			truncated = True
			break
		counts["records"] += 1
		counts["url_" + _bucket(row["file_url"])] += 1
		counts["extension_" + _image_type(row["file_url"])] += 1
		counts[
			"private"
			if row["is_private"] in (1, True, "1")
			else "public"
			if row["is_private"] in (0, False, "0")
			else "privacy_unknown"
		] += 1
	fields = {}
	for dt in DOCTYPES:
		if not frappe.db.exists("DocType", dt):
			fields[dt] = {"status": "doctype_missing"}
			continue
		meta = frappe.get_meta(dt)
		if not meta.get_field("image_url"):
			fields[dt] = {"status": "field_missing"}
			continue
		aggregate = Counter()
		cut = False
		for row in _pages(dt, ["image_url"]):
			if row is None:
				cut = True
				break
			aggregate["records"] += 1
			aggregate["url_" + _bucket(row["image_url"])] += 1
		fields[dt] = {"status": "scanned", "counts": dict(aggregate), "truncated": cut}
	return {
		"file_counts": dict(counts),
		"file_truncated": truncated,
		"image_url_fields": fields,
		"per_doctype_limit": LIMIT,
		"note": "Aggregate metadata only; no URLs or names returned. Custom fields, actual file contents, rights and all other apps are not inventoried.",
	}
