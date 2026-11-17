# -*- coding: utf-8 -*-
"""Siraj runtime diagnostics.

Endpoints here are intentionally simple, side-effect free, and reachable
from a logged-in Desk session. They exist so the owner can open a plain
URL in a fresh tab and verify the server is serving the build they
expect, without relying on *any* cached JS (which is the whole point of
the staleness investigation).
"""
from __future__ import annotations

import frappe

from siraj_research.record_icons import SIRAJ_BUILD


@frappe.whitelist()
def build_info() -> dict:
	"""Return server-side build metadata. GET-only, no args.

	Open this in a fresh browser tab (e.g.
	/api/method/siraj_research.api.diagnostics.build_info) after a deploy
	to confirm the server is on the expected commit/build **without**
	loading any of our JS bundles. If the response says one build and the
	browser console prints another, the browser is holding a stale
	bundle.
	"""
	from frappe.utils import get_build_version  # may not exist on all v15 builds
	from frappe import __version__ as frappe_version

	served = _asset_snapshot()
	return {
		"siraj_build": SIRAJ_BUILD,
		"frappe_version": frappe_version,
		"site_name": frappe.local.site,
		"bench_build_version": _safe_call(get_build_version),
		"apps": _app_versions(),
		"served_assets": served,
	}


@frappe.whitelist()
def asset_hashes() -> dict:
	"""Return SHA-256 of the SIRAJ JS/CSS files the server will serve.

	The diagnostics page in the browser fetches this over XHR and compares
	it against the hash of the JS/CSS it actually executed, using
	Resource Timing + fetch() re-requests. A mismatch means caching.
	"""
	import hashlib
	from pathlib import Path
	import os

	out = {}
	public_root = Path(__file__).resolve().parent.parent.parent / "public"
	paths = [
		"js/siraj-record-meta.js",
		"js/coordinate_map.js",
		"js/siraj-compat.js",
		"js/siraj-map/siraj-map.js",
		"js/siraj-map-toolbar.js",
		"js/siraj-map-kit.js",
		"css/siraj-icons.css",
		"css/siraj-map-toolbar.css",
		"css/siraj_explorer.css",
	]
	for rel in paths:
		p = public_root / rel
		if p.exists():
			data = p.read_bytes()
			out["/assets/siraj_research/" + rel] = hashlib.sha256(data).hexdigest()[:16]
		else:
			out["/assets/siraj_research/" + rel] = None
	out["__build__"] = SIRAJ_BUILD
	return out


def _app_versions() -> dict:
	try:
		apps = {}
		for name in (frappe.get_installed_apps() or []):
			try:
				apps[name] = {
					"version": frappe.get_attr(name + ".__version__")
					if hasattr(frappe.get_module(name), "__version__")
					else None,
				}
			except Exception:
				apps[name] = {"version": None}
		return apps
	except Exception:
		return {}


def _safe_call(fn):
	try:
		return fn()
	except Exception:
		return None


def _asset_snapshot() -> dict:
	"""Mirror of app_include_js/app_include_css from hooks.py — listed so the
	diagnostics page can report which URLs the server intends to serve."""
	return {
		"js": [
			"/assets/siraj_research/js/siraj-record-meta.js",
			"/assets/siraj_research/js/siraj-map/siraj-map.js",
			"/assets/siraj_research/js/siraj-map/siraj-graph.js",
			"/assets/siraj_research/js/siraj-map/siraj-filters.js",
			"/assets/siraj_research/js/siraj-map-kit.js",
			"/assets/siraj_research/js/siraj-map-toolbar.js",
			"/assets/siraj_research/js/siraj-list-icons.js",
			"/assets/siraj_research/js/siraj-compat.js",
			"/assets/siraj_research/js/coordinate_map.js",
			"/assets/siraj_research/js/siraj-icons.js",
		],
		"css": [
			"/assets/siraj_research/css/siraj-map-toolbar.css",
			"/assets/siraj_research/css/siraj-icons.css",
		],
	}
