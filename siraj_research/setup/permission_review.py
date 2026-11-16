"""Owner-operated, read-only permission probe; not an HTTP endpoint.

This probes effective permissions, not actual CRUD operations. It must only be
run via an authorized bench CLI against a reviewed site and account. Custom
permission hooks may themselves have effects beyond this module's control.
"""
import frappe

DOCTYPES = ("Person", "Institution", "Place", "Event", "Relationship", "Source", "Military Unit", "Operational Deployment")
OPERATIONS = ("read", "write", "create", "delete", "submit", "cancel", "report", "export", "share", "print", "email")
DOCUMENT_OPERATIONS = ("read", "write", "delete", "submit", "cancel", "share", "print", "email")


def inspect_permissions(user, doctype=None, record_name=None):
    """Check one existing user's permissions; return no user or record values.

    Optional document/list checks are confined to one explicit existing record.
    Permission checks do not attempt to create, modify, submit, cancel or delete.
    This non-whitelisted helper is not a substitute for real API/CRUD tests.
    """
    if not isinstance(user, str) or not user.strip() or not frappe.db.exists("User", user):
        raise ValueError("An existing user is required")
    if doctype is not None and doctype not in DOCTYPES:
        raise ValueError("Unsupported DocType")
    if record_name is not None and (not doctype or not isinstance(record_name, str) or not record_name.strip()):
        raise ValueError("Specify an allowed DocType and existing record name")
    if record_name is not None and not frappe.db.exists(doctype, record_name):
        raise ValueError("Specified record does not exist")
    # Load without output before impersonation; checks themselves run as user.
    doc = frappe.get_doc(doctype, record_name) if record_name is not None else None
    original = frappe.session.user
    try:
        frappe.set_user(user)
        output = {"roles": sorted(frappe.get_roles(user)), "doctypes": {}}
        for dt in ((doctype,) if doctype else DOCTYPES):
            if not frappe.db.exists("DocType", dt):
                output["doctypes"][dt] = {"status": "doctype_missing"}
                continue
            meta = frappe.get_meta(dt)
            entry = {"status": "checked", "module": meta.module, "is_submittable": bool(meta.is_submittable),
                     "doctype_permissions": {op: bool(frappe.has_permission(dt, ptype=op, user=user, throw=False)) for op in OPERATIONS}}
            if doc is not None:
                entry["document_permissions"] = {op: bool(frappe.has_permission(dt, ptype=op, doc=doc, user=user, throw=False)) for op in DOCUMENT_OPERATIONS}
                # One exact-match query; return only inclusion, not the result.
                if entry["doctype_permissions"]["read"]:
                    try:
                        rows = frappe.get_list(dt, fields=["name"], filters={"name": record_name}, limit_page_length=1)
                        entry["list_contains_record"] = bool(rows)
                    except frappe.PermissionError:
                        entry["list_contains_record"] = False
                else:
                    entry["list_contains_record"] = None
            output["doctypes"][dt] = entry
        return output
    finally:
        frappe.set_user(original)
