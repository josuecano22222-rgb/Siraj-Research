# Frappe permission test report

**Status: BLOCKED — no running Frappe site, test accounts, database or authorized destructive testing environment is available in this workspace.** No real permission result is asserted here. Static JSON, code review and stubs are not evidence of the effective site permissions.

## Scope and static observations

The Page permits System Manager and SIRAJ Viewer, Researcher, Reviewer and Administrator in metadata. Committed DocTypes specify role and permlevel rules; the worktree also contains unreleased metadata changes. User permissions, shares, owner-only rules, workflow states, Custom DocPerm, property setters, overrides, Frappe/ERPNext hooks, custom scripts and field permlevels on the actual site can change effective access. Administrator's effective access is not inferred from role JSON. None of the current checkout's 50 DocType definitions declares `is_submittable`; verify actual site customizations before marking submit/cancel not applicable.

The Explorer and reports use `frappe.get_list` followed by document-level checks; relationship edges require both endpoint nodes visible. Tree navigation validates parent access. Local maps require Place read permission but distribute the entire provisioned pack to any such reader. Their UI download opt-in does **not** prevent saving individual tiles. Code review still needs real verification of field restrictions, readable linked identifiers in dossier/grouping fields, derived `display_name` values, direct API calls, custom permission hooks, shares, and the race where access changes during a scan. Do not treat permitted access to a parent as proof that every referenced record should be disclosed. A role with no read permission may encounter an empty map/graph rather than an explicit denial: verify this UX and direct APIs.

## Accounts and scenarios

No accounts were created or used in this audit. On an authorized isolated environment with appropriate, legitimate records and separately approved write tests, record anonymized test identity, exact roles/user permissions, record state, request, expected and observed result, timestamp, deployment revision and logs. Do not include credentials or sensitive record contents in this report.

| Test identity / scenario | Expected | Actual |
| --- | --- | --- |
| Guest and authenticated user without SIRAJ/Place access | No restricted records or local map tiles via UI or direct API | NOT RUN |
| SIRAJ Viewer | Read only where explicitly allowed; cannot perform prohibited write/create/delete/submit/cancel via direct API | NOT RUN |
| SIRAJ Researcher | Each operation follows effective permissions, owner/user restrictions and workflow; level-1 fields denied unless granted | NOT RUN |
| SIRAJ Reviewer | Permitted review actions and fields work; unrelated blocked actions remain denied | NOT RUN |
| SIRAJ Administrator and System Manager | Allowed actions work without exposing documents forbidden by effective custom rules | NOT RUN |
| Administrator | Verify bypass semantics and baseline; not a substitute for other roles | NOT RUN |
| Custom role / user-permission / ownership / share combinations | Query and per-document checks agree, no leaks through lists, reports, linked values, structure counts, tile metadata, downloads or direct methods | NOT RUN |
| Field restricted with source title/relationship/link | No restricted values or derivable leaks according to approved policy | NOT RUN |
| Submit/cancel and other operations | Not applicable only when actual effective DocType is not submittable; otherwise allowed and denied cases | NOT RUN |

Use production records read-only only if explicitly permitted and with access controls. Write/delete/submit/cancel/concurrency testing requires an authorized safe environment and backup/recovery plan; never manipulate real records to manufacture test cases. Record actual HTTP status and sanitized response shapes for direct APIs, including `siraj_research.visualization.*`, `siraj_research.treeview.get_children`, `siraj_research.local_maps.*` and relevant reports. Fail the release gate on any unexpected disclosure or inconsistent denial.
