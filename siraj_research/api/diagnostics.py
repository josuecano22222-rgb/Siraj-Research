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
		"assets_json_keys": _bundled_asset_keys(),
	}


@frappe.whitelist()
def asset_hashes() -> dict:
	"""Return SHA-256 (first 16 hex) of the SIRAJ source and bundle files the
	server will serve.

	The diagnostics page compares the hash of the JS it fetches (with
	cache:no-store) against this table to prove the server file matches.
	For hashed esbuild bundles we report whichever dist/ file is
	registered in sites/assets/assets.json for ``siraj.bundle.js`` —
	that is the exact URL the HTML emits, so a source change there
	implies a different URL and a guaranteed cache miss.
	"""
	import hashlib
	from pathlib import Path

	out = {}
	public_root = Path(__file__).resolve().parent.parent.parent / "public"
	# Source files (used when the bundle cannot be resolved — e.g. before
	# the first bench build on a fresh checkout, or when ?v= cache-bust
	# is used instead of hashed filenames).
	source_paths = [
		"js/siraj-record-meta.js",
		"js/coordinate_map.js",
		"js/siraj-compat.js",
		"js/siraj-map/siraj-map.js",
		"js/siraj-map/siraj-graph.js",
		"js/siraj-map/siraj-filters.js",
		"js/siraj-map-kit.js",
		"js/siraj-map-toolbar.js",
		"js/siraj-list-icons.js",
		"js/siraj-icons.js",
		"js/siraj.bundle.js",
		"css/siraj-icons.css",
		"css/siraj-map-toolbar.css",
		"css/siraj_explorer.css",
	]
	for rel in source_paths:
		p = public_root / rel
		if p.exists():
			data = p.read_bytes()
			out["/assets/siraj_research/" + rel] = hashlib.sha256(data).hexdigest()[:16]
		else:
			out["/assets/siraj_research/" + rel] = None

	# If esbuild has emitted hashed bundles, include the actual served file
	# (sites/assets/siraj_research/dist/js/siraj.bundle.<HASH>.js). The
	# diagnostics page reads this so it can verify the hashed file on disk
	# matches the URL the HTML is pointing to.
	# JS is bundled; CSS is served with ?v= (see hooks.py comment) so we only
	# report the JS bundle hash here.
	dist_js, _dist_css = _bundled_asset_paths()
	for label, rel in [("dist_js", dist_js)]:
		if rel:
			# rel is like /assets/siraj_research/dist/js/siraj.bundle.AB12CD.js
			# Convert to filesystem path under sites/assets.
			fs_path = _sites_assets_path(rel)
			if fs_path and fs_path.exists():
				out["__" + label + "__"] = {
					"url": rel,
					"sha256_16": hashlib.sha256(fs_path.read_bytes()).hexdigest()[:16],
					"size": fs_path.stat().st_size,
				}
			else:
				out["__" + label + "__"] = {"url": rel, "on_disk": False}
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


def _bundled_asset_keys():
	"""Return any keys for our bundles that appear in sites/assets/assets.json."""
	try:
		from frappe.utils import get_assets_json
		aj = get_assets_json() or {}
		return {k: v for k, v in aj.items() if "siraj" in k}
	except Exception:
		return {}


def _bundled_asset_paths():
	"""Return the resolved hashed URLs for siraj.bundle.{js,css} or None."""
	try:
		from frappe.utils.jinja_globals import bundled_asset
		return bundled_asset("siraj.bundle.js"), bundled_asset("siraj.bundle.css")
	except Exception:
		return None, None


def _sites_assets_path(url_path):
	"""Map an /assets/... URL to a filesystem path under sites/assets."""
	try:
		sites_root = Path(frappe.local.sites_path)
		# /assets/siraj_research/foo.js → sites/assets/siraj_research/foo.js
		# (bench build symlinks/copies them there.)
		rel = url_path[len("/assets/"):] if url_path.startswith("/assets/") else url_path.lstrip("/")
		return sites_root / "assets" / rel
	except Exception:
		return None


def _asset_snapshot() -> dict:
	"""Mirror of app_include_js/app_include_css from hooks.py — listed so the
	diagnostics page can report which URLs the server intends to serve.

	After switching to hashed esbuild bundles, the Jinja bundled_asset()
	helper resolves ``siraj.bundle.js`` to
	/assets/siraj_research/dist/js/siraj.bundle.<HASH>.js at render time.
	We return the logical hook entries here (not the hashed URLs) so a
	missing entry is obvious.
	"""
	return {
		"js": ["siraj.bundle.js"],
		"css": [
			"/assets/siraj_research/css/siraj-map-toolbar.css?v=" + SIRAJ_BUILD,
			"/assets/siraj_research/css/siraj-icons.css?v=" + SIRAJ_BUILD,
		],
		"legacy_source_files": [
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
	}
