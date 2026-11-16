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

## Owner-reported f44f779 update and new preparation code

The owner applied `f44f779` and passed both inventory stub tests; they did not run the site inventory. This delivery implements a pure in-memory candidate Event planner with fail-closed validation (`event-planner.md`) and adds bounded relationship-report/Place-tree routes to the existing browser probe (`link-query-performance.md`). These are preparation, not a complete Event migration, safe real-site inventory, performance optimization or measured benchmark. All actual site hook/customization reviews and role tests remain outstanding. Offline record export and coordinate conversion/rollback remain unimplemented; owner imagery evidence needs are consolidated in `imagery-owner-input.md`. Delivery state: **IMPLEMENTED and UPLOADED on push, AWAITING LOCAL TESTING**. No migrations, live tests or sensitive data changes were performed.

## Owner-reported 13dd69e tests and new prototypes

The owner applied `13dd69e` and passed six pure planner tests and the synthetic load test; neither exercised a real site. This delivery adds in-memory Event snapshot projection/reversal with comparison guards and an offline read-only local snapshot panel. They are prototypes tested on synthetic fixtures; neither is a database migration, site rollback, authorized record exporter or synchronization mechanism. Viewer files are unencrypted; permission/revocation and local customization remain unresolved. Delivery state: **IMPLEMENTED and UPLOADED on push; AWAITING LOCAL TESTING**. No migration, database operation or actual performance test was performed.

## Owner-reported 1bc767d tests and security components

The owner applied `1bc767d` and passed five Event projection and three offline-package fixture tests. `test_offline_records.js` failed to start because `jsdom` was not installed; no DOM test result was produced. It is replaced with a Node-only DOM stub test in this delivery. No real Frappe test is implied.

This delivery adds a non-whitelisted current-session candidate collector and HMAC/expiry prototype (`offline-snapshot-security.md`), a synthetic Event projection integrity comparison, and an isolated bench-only SQL-call counter (`link-query-performance.md`). They are partial components, not a production offline export, asymmetric offline verification, real migration/rollback or measured performance optimization. The v1 viewer remains unverified; the Event collision, actual site permissions and real environment behavior remain open. **IMPLEMENTED and UPLOADED on push; AWAITING LOCAL TESTING**. No actual records, migration, load test or database change was performed.

## Owner-reported 74b5cf3 tests and connected signature prototype

The owner applied `74b5cf3` and passed 9 snapshot, 6 Event, 4 query-probe stub tests and the Node DOM-stub test. No site record export or Frappe security/load test was reported. This delivery adds a fixture-tested P-256 signing path from the existing candidate collector to offline WebCrypto verification, and a pure Event metadata comparator. Its trust policy must be independently provisioned; the mechanism is not encryption, offline user authentication, full revocation or proof of authorized records. No real-data endpoint is enabled. Event migration, physical rollback, coordinate conversion and real performance measurements are still outstanding. **IMPLEMENTED and UPLOADED on push; AWAITING LOCAL TESTING.**

## Owner-reported 4cf349b fixture evidence and security correction

The owner reported 3/3 signed-snapshot Python fixtures, 3/3 Event schema fixtures, the Node signature fixture and the Node-only offline viewer fixture passing after applying `4cf349b`. These test results are local fixture evidence, not proof of live Frappe authorization or production readiness. See `milestone-4cf349b-results.md`.

This delivery fixes an unsigned-status text spoofing weakness, adds a fixture-tested non-mutating Event review with separate coverage assertions, documents committed-field mapping and unresolved site-specific dependencies, and exercises synthetic report query shapes. The offline threat model identifies remaining trust, encryption, revocation and identity gates. Delivery: **CORRECTIONS UPLOADED / AWAITING LOCAL TESTING** for the status fix and **IMPLEMENTED / UPLOADED on push / AWAITING LOCAL TESTING** for the review additions. Real Event migration/rollback, Frappe role tests, actual exports and real performance measurements remain NOT RUN and are not VERIFIED.

## Owner-reported 6b0daac application and fixture results

The owner supplied a successful fast-forward and fixture results: Event review 5/5, query-scaling 3/3, visualization-permission 2/2 and the Node DOM-stub script passed. Full evidence and limitations are in `milestone-6b0daac-results.md`. This updates the preceding milestone's awaiting-local-testing status for those fixtures only; it does not approve the threat model or Event specification, which remain proposals requiring further review. Real-site authorization, performance, migration/rollback and real-record export remain NOT RUN.

## Event discovery, snapshot hardening and synthetic tree coverage

`410ece9` delivers fixture-only Event reference discovery/classification and model gates; `fcb4144` adds strict experimental signed-body parsing and adversarial fixtures. The accompanying Place-tree suite models non-admin ownership/share/query/document cases and records synthetic stub query shapes and timings in `link-query-performance.md`. **UPLOADED on push / AWAITING OWNER LOCAL FIXTURE TESTS.** All actual site evidence, migrations, restore tests, real export and key provisioning remain NOT RUN; the security and Event documents remain proposals.
