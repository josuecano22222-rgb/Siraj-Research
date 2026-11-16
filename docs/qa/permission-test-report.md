# Frappe permission test report

**Status: IN PROGRESS — the working Frappe environment exists locally on the owner's machine but is not directly accessible to the development agent. Real-environment testing must therefore be coordinated with the owner.** A read-only bench probe is implemented but has only stub tests; no local role results have been reported. No real permission result is asserted here. Static JSON, code review and stubs are not evidence of the effective site permissions.

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

## Owner-operated read-only probe (awaiting local testing)

`siraj_research.setup.permission_review.inspect_permissions` is a **non-whitelisted bench CLI helper**, not a web method. It checks the actual effective Frappe role/permission functions while temporarily setting the CLI process's user; it restores the prior user in `finally`. It accepts only the eight fixed SIRAJ DocTypes and can optionally check one explicit existing record and a single-record `get_list`. It returns roles, booleans and module/submittable metadata—not the chosen user, record name or field values. It does not deliberately insert, update or delete records. Custom permission hooks and framework caches/logs may have their own side effects; review site-specific hooks and obtain operational authorization before running on the owner's working environment. Permission checks are not actual CRUD operations, workflow validation or direct-API tests. They cannot prove that the user can successfully carry out an operation.

The exact command for the existing built-in Administrator account, **only after approval of this release and this diagnostic**, is:

```bash
cd /home/frappe/frappe-bench
bench --site frappe.com execute siraj_research.setup.permission_review.inspect_permissions --kwargs '{"user":"Administrator"}'
```

To probe an existing account and optionally an existing record, substitute locally with correct JSON quoting; do not share credentials, session cookies, record identifiers or document values. Do not create accounts or records solely for this test on the working site. Example syntax (replace values locally; placeholders are not runnable):

```bash
bench --site frappe.com execute siraj_research.setup.permission_review.inspect_permissions --kwargs '{"user":"EXISTING-USER-ID","doctype":"Person","record_name":"EXISTING-PERSON-ID"}'
```

Run only accounts the owner is authorized to inspect. Record an anonymized label, actual assigned role set, test case and output booleans; remove identifying/sensitive content before sharing. A missing record/user, permission-hook exception or unexpected traceback is a failure to investigate—not an authorization success. Frappe's `bench execute` may produce fallback noise after an exception; capture the first relevant error, redact sensitive text, and do not repeat failed tests without analysis.

### Local checklist (no writes)

1. After authorization, probe Administrator, an existing System Manager and existing accounts representing each available SIRAJ role. Confirm `roles` matches actual assignments. The `doctype_permissions` values are framework permission decisions, not proof that writes are permitted under the active workflow. `is_submittable` is actual metadata, not a guarantee that submit/cancel will work. For Administrator, Frappe v15's permission function may return true even for non-submittable types; use the metadata field to judge applicability.
2. With permission to inspect the chosen existing record, repeat for one allowed and one restricted Person or other supported DocType. Compare `document_permissions.read` and `list_contains_record` to the owner’s configured access. `null` for list means the probe skipped the list query because DocType read permission was false; it is not an observed list denial. Owner/share/user-permission cases need appropriate existing records. A mismatch is a finding, not an instruction to change permissions.
3. For an existing user without Place read, while logged into that user's ordinary browser session on the site, inspect only the status of a direct call (do not paste response contents or use another person's session):

   ```js
   fetch('/api/method/siraj_research.local_maps.available_packs', {credentials: 'same-origin'}).then(r => console.log('local-pack status:', r.status));
   ```

   Expected: **403** for a logged-in user without Place read. A Place reader should get **200** even if the pack list is empty. A different status, redirected login, network error, or unexpected access is a finding. This call checks the metadata endpoint only; tile permissions, other APIs and record/field confidentiality still require testing. Use the owner-approved inspection account and site, never a public tile server.
4. In the Explorer screen, verify that the authorized user sees only records they can normally read, that an unprivileged user cannot see restricted records or endpoint details, and that an empty view is reported honestly. Do not change or create records. Save only sanitized observations. Full permission acceptance remains pending direct API tests for record details/reports, field-level and link restrictions, and approved write/delete/submit/cancel scenarios.

Collect the app revision, site name if approved, anonymized account-role labels, expected/actual booleans, HTTP status, and the **first** relevant sanitized traceback or site Error Log entry. Do not share passwords, API keys, cookies, full raw responses, or record data.
