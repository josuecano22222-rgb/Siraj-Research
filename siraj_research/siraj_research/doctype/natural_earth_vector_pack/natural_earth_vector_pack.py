"""Controller for the Natural Earth Vector Pack admin DocType.

The DocType is the operational surface for the Natural Earth Vector pack:
administrators select the provisioning source and scale tiers, run
provisioning (or trigger it as a background job), and inspect the resulting
pack, manifest and offline ZIP archive.
"""

from __future__ import annotations

import json

import frappe

from siraj_research import natural_earth_vector as nev
from siraj_research.natural_earth_catalog import (
    SCALES,
    all_layers,
    catalog_summary,
)


def _scales_from_doc(doc) -> list:
    scales = []
    for field, code in (("scale_110m", "110m"), ("scale_50m", "50m"),
                        ("scale_10m", "10m")):
        if getattr(doc, field, None):
            scales.append(code)
    return scales


@frappe.whitelist()
def get_catalog_layers(scale: str | None = None) -> list:
    """Catalog layers for the UI picker (optionally filtered by scale)."""
    if scale and scale not in SCALES:
        frappe.throw("Unknown scale", frappe.ValidationError)
    layers = []
    for entry in all_layers():
        if scale and entry["scale"] != scale:
            continue
        layers.append({
            "name": entry["file"],
            "scale": entry["scale"],
            "category": entry["category"],
            "kind": entry["kind"],
            "description": entry["description"],
            "bytes": entry["bytes"],
        })
    return layers


@frappe.whitelist()
def refresh_status(docname: str | None = None) -> dict:
    """Re-read the pack manifest and refresh the doc's statistics."""
    if not frappe.has_permission("Natural Earth Vector Pack", "write"):
        frappe.throw("Administrator role required", frappe.PermissionError)
    doc = frappe.get_doc("Natural Earth Vector Pack", docname) if docname \
        else frappe.get_doc("Natural Earth Vector Pack", frappe.form_dict.name)
    stats = nev.pack_stats()
    doc.file_count = stats["pack_layers"]
    doc.total_bytes = stats["pack_bytes"]
    doc.zip_ready = 1 if stats["zip_ready"] else 0
    doc.pack_location = str(nev.pack_root())
    if stats["pack_ready"]:
        doc.status = "Ready"
        doc.message = ""
    else:
        doc.status = "Empty"
    doc.save(ignore_permissions=True)
    return {
        "status": doc.status,
        "file_count": doc.file_count,
        "total_bytes": doc.total_bytes,
        "zip_ready": bool(doc.zip_ready),
        "available_scales": stats["available_scales"],
    }


@frappe.whitelist()
def run_provision(docname: str | None = None) -> dict:
    """Provision the Natural Earth Vector pack.

    Runs synchronously; for the 1:10m tier (~1.1 GB) prefer triggering this
    from a background job (the admin UI wraps it in ``enqueue`` when the
    ``run_in_background`` flag is set).
    """
    if not frappe.has_permission("Natural Earth Vector Pack", "write"):
        frappe.throw("Administrator role required", frappe.PermissionError)

    doc = frappe.get_doc("Natural Earth Vector Pack", docname) if docname \
        else frappe.get_doc("Natural Earth Vector Pack", frappe.form_dict.name)

    scales = _scales_from_doc(doc)
    if not scales:
        frappe.throw("Select at least one scale tier", frappe.ValidationError)

    layers = None
    if doc.layers_json:
        try:
            layers = json.loads(doc.layers_json)
            if not isinstance(layers, list):
                layers = None
        except ValueError:
            frappe.throw("Layers JSON is invalid", frappe.ValidationError)

    doc.status = "Provisioning"
    doc.message = ""
    doc.provision_log = ""
    doc.save(ignore_permissions=True)

    log_lines = [f"Provisioning source={doc.source} scales={scales}"]
    try:
        manifest = nev.provision_pack(
            scales,
            layers=layers,
            source=doc.source,
            mirror_path=doc.mirror_path or None,
        )
    except nev.NaturalEarthPackError as exc:
        doc.status = "Failed"
        doc.message = str(exc)
        doc.provision_log = "\n".join([*log_lines, f"ERROR: {exc}"])
        doc.save(ignore_permissions=True)
        frappe.throw(f"Provisioning failed: {exc}", frappe.ValidationError)

    log_lines.append(
        f"Done: {manifest['stats']['file_count']} files, "
        f"{manifest['stats']['total_bytes']} bytes"
    )
    if manifest.get("missing"):
        log_lines.append(f"Missing: {len(manifest['missing'])} layers")

    doc.status = "Ready"
    doc.last_provisioned = frappe.utils.now()
    doc.provision_log = "\n".join(log_lines)
    doc.save(ignore_permissions=True)
    frappe.clear_cache()

    return {
        "ok": True,
        "status": doc.status,
        "file_count": doc.file_count or manifest["stats"]["file_count"],
        "total_bytes": doc.total_bytes or manifest["stats"]["total_bytes"],
        "missing": manifest.get("missing", []),
        "zip": str(nev.zip_path()) if nev.zip_path().is_file() else None,
        "catalog": catalog_summary(),
    }
