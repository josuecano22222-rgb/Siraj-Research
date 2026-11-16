# Development completion report — audit in progress

This is a living report, not a production readiness certificate. Definition of done is **not met**. The working Frappe environment exists locally on the owner's machine but is not directly accessible to the development agent. Real-environment testing must therefore be coordinated with the owner. The owner reported applying `bf55664`, building assets, clearing cache and restarting services; this is not verification of functionality. The agent has not directly run production migration, reinstall, sample insertion, destructive operations or load tests.

| Work item | Status | Evidence this audit | Remaining blocker / risk |
| --- | --- | --- | --- |
| Permissions | IN PROGRESS | Static metadata and API review; mock tests only. `permission-test-report.md`. | Effective permissions and real direct API behavior need authorized Frappe accounts/environment and controlled operations. Link fields, derived titles and custom rules need particular review. |
| Load/performance | BLOCKED | Candidate scan/N+1/tile paths identified; no measured numbers. `load-test-report.md`. | Authorized representative environment, realistic workload, metrics and post-fix comparison. |
| Imagery | IN PROGRESS | `imagery-register.md`: all five bundled Leaflet PNG hashes match `leaflet@1.9.4`; world atlas hash matches `world-atlas@2.0.2`. Corrected optional coordinate picker OSM tile hostname and attribution link, with mocked regression. | Owner-provided packs, site uploads/URLs, logo/trademark and inline SVG provenance, service policy and full attribution review remain. |
| Explorer | IN PROGRESS | Code trace and synthetic browser/unit tests; see `explorer-verification.md`. | No real record, link or role tests. Offline basemap viewer is not an offline record Explorer. |
| Event | IN PROGRESS | Documented actual past collision and upstream core field/hook comparison; local rename and guard are incomplete prototypes. `../event-collision-remediation.md`. | Reviewed data migration, core metadata restoration, site dependency inventory, real Frappe regression and recovery rehearsal. |
| Coordinates | IN PROGRESS | Found and corrected a Decimal-context rounding bug: very long just-out-of-range values could pass Python bounds checks. Added exact-boundary regression and a read-only aggregate inventory prototype. `coordinate-migration.md`. | No migration patch, physical schema inspection, real site values, Frappe migration/rollback or end-to-end verification. |

## Changes in this audit

- `siraj_research/visualization.py`: exact Decimal bound comparison via context-independent `copy_abs`; does not change stored values or the schema. Regression `tests/test_coordinate_decimal_bounds.py` uses a Frappe stub, not a live site.
- `siraj_research/public/js/coordinate_map.js` and `tests/test_coordinate_map.js`: optional OSM layer uses the policy's canonical hostname and a copyright link. This change alone does not establish complete tile-policy compliance.
- `siraj_research/setup/coordinate_audit.py` and `tests/test_coordinate_audit.py`: non-whitelisted read-only, aggregate-only, fixed-DocType preflight prototype and fake database tests. It has not been run on an actual site and is not a migration.
- `docs/qa/`: outstanding work, permission/load reports, Explorer trace, asset licensing register, this report and coordinate plan. The separate existing worktree Event, coordinate metadata, hooks and form prototypes were not treated as completed or deployed.

## Tests and limitations

In the current **dirty worktree**, `python3 -m unittest discover -s tests -v`: 88 tests passed. JavaScript mock tests passed for coordinate forms, Explorer UI, offline downloader/viewer, list/tree navigation and current prototype form scripts; synthetic Chromium Explorer and `file://` offline viewer smoke tests passed; asset test passed. An isolated archive of the staged changes passed 80 Python tests, coordinate mock, synthetic Chromium Explorer and asset smoke tests; this archive excludes the unrelated worktree prototypes. `compileall`, selected `node --check` and `git diff --check` passed. These do not test real Frappe authorization, production records, database migrations, multi-user load, mobile devices or actual imagery.

## Release and recovery

The owner reported deploying `bf55664`; no further deployment is authorized by this report. Do not run migration/reinstall/seeding as a consequence of this report. Follow the sequencing and gates in `outstanding-work.md`, and the backup/data recovery constraints in `coordinate-migration.md` and `../event-collision-remediation.md`. Any future production deployment or data-changing operation needs a separate explicit authorization, current verified backups, a rehearsed recovery plan and a site-specific maintenance runbook. No test report currently establishes that all critical errors or information leaks are absent.

## Collaborative owner-operated testing milestone

The owner has confirmed that the real Frappe environment is local to them, and reported a successful `bf55664` fetch/build/cache-clear/restart. Service startup is not functional, security or load verification. This milestone adds `siraj_research/setup/permission_review.py` and `tests/test_permission_review.py` for an owner-operated, non-whitelisted permission-decision probe, and `docs/qa/load-probe.js` plus `tests/test_load_probe.js` for bounded, opt-in browser-side HTTP timing. The detailed operating and safety checklists are in `permission-test-report.md` and `load-test-report.md`. Neither helper has been run against the owner's environment; the scripts do not establish real CRUD behavior or performance by themselves.

Delivery state: **IMPLEMENTED; UPLOADED when this commit is pushed; AWAITING LOCAL TESTING after separate deployment and test authorization.** No user accounts or records have been created. No production load test is authorized by these instructions. Other outstanding tasks and their blockers remain as in the register.

## Owner-reported local evidence and focused security corrections

The owner applied `e42ba8f` and ran the Administrator probe. All eight checked DocTypes reported the SIRAJ module and `is_submittable: false`; the all-true permission booleans reflect Administrator bypass and did not perform CRUD. `Event` remains the SIRAJ DocType; the collision is not resolved. The owner had a local workspace JSON modification before the merge; preserve it. Non-Administrator/document/API tests and production load measurements remain pending.

Static review then found two potential link-disclosure paths: an Explorer relationship could return the primary Source identifier even when that Source was absent from the permission-filtered graph; and report/tree link checks did not consult custom list-query restrictions. The focused changes hide such primary Source identifiers and require both document and exact-match list visibility for link checks. Added `tests/test_relationship_source_privacy.py` and `tests/test_link_query_privacy.py` use stubs; no real-site leak has been demonstrated or fully ruled out. These checks add one list query per checked linked record (the relationship report caches repeated links); representative performance testing is still needed. Other linked detail/grouping fields, derived labels and real role behavior remain under review.

For this privacy milestone, the new stub regressions reproduced three failures against the preceding committed baseline and passed after the correction. An isolated staged archive passed 88 Python tests, mock Explorer UI and synthetic Chromium/asset smoke tests. These are not real Frappe permission tests; release requires owner approval and role-specific local verification.

## Owner-reported 60c2809 update and Event inventory milestone

The owner reported fast-forwarding to 60c2809 and restarting web/Socket.IO, scheduler and workers successfully, with the pre-existing workspace JSON modification present. No new permission or functionality acceptance evidence was supplied. The Event identity remains conflicted; no migration has been executed or released.

This milestone adds an aggregate, non-whitelisted metadata-reference inventory with isolated stubs, an Event transition design and controlled security/performance procedures. The inventory does not classify ownership or cover all dependencies and is potentially expensive; run only under separate approval, initially on an isolated copy. Static Frappe v15 review additionally identified core Event permission hooks assuming calendar semantics; actual site's full effective hooks and customizations are not yet reviewed. Offline record export remains unimplemented; imagery intake and coordinate recovery gates remain open. **IMPLEMENTED (inventory/design), UPLOADED on push, AWAITING LOCAL TESTING**; no item is VERIFIED. See the updated completion register for delivery state.
