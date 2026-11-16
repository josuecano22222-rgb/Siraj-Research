# Permission and API rehearsal: existing accounts and records

**Status: prepared, not executed.** Read the hook review first. Do not create users, records, permission rules or shares on the working site for this exercise. Select existing accounts and records only with the owner's separate approval; use each user's own authorized browser session, never credentials or another user's session. Avoid changes, public tile requests, production load and side-effecting methods. Read requests can invoke custom code; review active hooks and approve a low-traffic window before any calls. Log only anonymized labels, booleans, status and sanitized errors, never cookies, identifiers, record values or raw responses.

## Static hook review and what remains unknown

At the version tags previously reported by the owner, Frappe v15.126.1 registers `permission_query_conditions` and `has_permission` for `Event` in `frappe/hooks.py`. Its query checks public/owner/participant conditions; its document hook checks public, owner or participants and restricts participant writes. These assume Frappe calendar schema, while the owner's effective `Event` metadata is currently SIRAJ. Errors, missing fields or inappropriate decisions are possible and require controlled testing. Core also hooks File, Comment, Communication, User and other supporting types. ERPNext v15.125.0 declares query/document permission hooks for Asset Activity, Contract and Voice Call Settings, not the eight SIRAJ probe types; HRMS v15.64.8 has no active top-level mappings for these two hook keys in its `hooks.py`. SIRAJ's committed hooks have only commented examples for those keys. This is a **static review of repository tags**, not a review of every installed customization, overridden method, wildcard event hook, Server Script, effective metadata or actual site code. Other installed apps and local changes may differ.

Before non-Administrator testing, the owner must review *all effective* site-installed apps and local app modifications, custom permission/query/document hooks (including wildcard hooks), overrides, Server Scripts, permission managers, user permissions, shares, workflows and relevant field permlevels for the target types and all four Explorer endpoints. Review side effects and data access of called hooks and linked code. Record versions/hashes and whether each case is safe; stop if any code or hook is unknown or unsafe. Do not run the Administrator probe as a substitute for this review. If needed, share only sanitized hook names/behavior for assistance; do not publish code containing secrets. Event testing remains separately gated by its collision.

## Case matrix and procedure

For each already-existing restricted-role account and owner-approved existing record, agree expected access in advance from actual policy, not from the API result. Include if available: (1) list and document visible; (2) list hidden but document permission permitted by custom query; (3) document denied; (4) shared record; (5) field-level restriction; (6) readable Relationship with hidden endpoint and hidden primary Source. If a case does not already exist, mark **not available**. Do not infer such a case from a blank display. Record account role label, ownership/share category and expected list/document/API outcomes, but not identifiers.

After separate authorization and hook review, the existing non-whitelisted `inspect_permissions` bench helper can compare exact-record `list_contains_record` and document decision using the syntax in `permission-test-report.md`. Its checks impersonate the account and Frappe's `bench execute` commits successful transactions; even though the helper makes no intentional writes, custom hooks could write. A permission exception or failed query is an error, not a denial proof. Avoid Event cases until its collision risk is explicitly assessed.

In the same user's browser session, use the normal list/tree and Explorer. Compare an approved record's list presence, detail view and relationship graph against the agreed expectations. A visible relationship must not reveal an unreadable endpoint or primary Source; test Source field, linked detail and grouping values individually, since not all have been hardened. Document a failure as a boolean and sanitized screen/action, not the secret.

For an approved known record, a cautious exact-record API check may be made **only after review** in that same browser console. Replace the two placeholders locally, never paste their values into a report. This shows status only, not the returned body:

```js
const dt = 'Person'; // use an allowed, reviewed DocType
const id = 'REPLACE-LOCALLY-WITH-EXISTING-ID';
const u = new URL('/api/method/siraj_research.visualization.record_detail', location.origin);
u.search = new URLSearchParams({doctype: dt, name: id});
const r = await fetch(u, {credentials: 'same-origin', redirect: 'error', cache: 'no-store'});
console.log('detail HTTP status:', r.status);
```

A visible record should have a successful response with only permitted fields; an inaccessible/list-hidden record should not return its detail. Status alone does not establish field confidentiality: inspect the response privately and report only pass/fail by field category. A non-2xx or redirect/login/network error requires investigation; a 403 is expected for a denied record under this endpoint, but errors must not be classified as secure automatically. Do not save or forward the network response. Repeat only pre-approved cases; never attempt writes through REST.

Review the graph API and report/tree requests in the browser's Network panel after opening the view; privately check the selected test identifiers and field restrictions against the expectation, and send only booleans. Account for caches and concurrent updates. Report separately which cases were unavailable, actual statuses and sanitized first traceback. Current hardening covers graph primary Source and relationship report/tree link checks; it does not prove that linked details, groups, labels, exports or all endpoints are safe.

The pure Event planner does not call Frappe permission hooks or test them. Its unit tests cannot establish any user's Event access. Real non-Administrator tests remain contingent on the site-specific effective-hook review, explicit approval, existing suitable accounts/records, and Event collision risk review above.

The snapshot candidate collector uses Frappe read and export checks at DocType and document level, plus list-query filtering. Its stubs cannot verify the effect of this site's real roles, user permissions, shares, field restrictions, custom hooks or concurrent changes. Event identities are excluded. The collector is not a public endpoint or approved record export.
