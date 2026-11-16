# Event identity transition — non-mutating specification

**Review status: PROPOSAL; further review required, incomplete for the actual site and not executable.** This specifies the proposed categories and gates but cannot list the owner's actual records, custom fields, hooks or integrations because the agent cannot access the site. No data was read from it here. No migration, metadata reload, schema change, SQL update, cleanup or rollback command is authorized by this specification. Previously reported zero Event rows and zero counts for a fixed subset of references were point-in-time observations, not a complete dependency or rollback inventory.

## Identities and source of truth

At committed app revision `4cf349b`, SIRAJ's standard metadata defines global `Event`, module `Siraj Research`, in `siraj_research/siraj_research/doctype/event/event.json`. Frappe v15.126.1 defines the same global `Event` in module `Desk` as its calendar DocType. Its `event_type` is a calendar Select (`Private`/`Public`), whereas SIRAJ's is a Link to `Event Type`; the semantics conflict. The recommended architecture is Frappe-owned `Event` for calendars and a distinct **proposed** `SIRAJ Research Event` (module `Siraj Research`) for historical research. The destination definition exists only as an incomplete, uncommitted worktree prototype; it is not a shipped DocType and actual destination availability/custom collisions are unknown. Do not globally rename `Event`, as unrelated calendar references may be rewritten.

## Field mapping — committed source, proposed same-name destination

The table below enumerates all 46 DocField entries in the committed SIRAJ source, including presentation fields. The proposal is same-named research fields with their full DocField attributes preserved unless a separately reviewed compatibility change is necessary. This is **not** a mapping to core calendar `Event`; no calendar field is inferred from a research field. The source JSON is the complete reference for metadata attributes not displayed in this table. Layout entries are metadata, not data columns; `Table` entries represent child collections. Actual effective source/custom fields, overrides, data types, precision, defaults and DB columns must be inventoried separately. In particular, the unreleased coordinate Data prototype must not be folded into this migration without its own reviewed conversion and rollback.

| Source field | Type | Options / target | Proposed destination | Permlevel |
| --- | --- | --- | --- | --- |
| `tab_identity` | Tab Break | — | `tab_identity` | 0 |
| `sb_identity` | Section Break | — | `sb_identity` | 0 |
| `naming_series` | Select | EVT-.####, EVT-.YY.-.#### | `naming_series` | 0 |
| `display_name` | Data | — | `display_name` | 0 |
| `cb_identity` | Column Break | — | `cb_identity` | 0 |
| `title_ar` | Data | — | `title_ar` | 0 |
| `title_en` | Data | — | `title_en` | 0 |
| `event_type` | Link | Event Type | `event_type` | 0 |
| `image` | Attach Image | — | `image` | 0 |
| `image_url` | Data | URL | `image_url` | 0 |
| `image_alt` | Data | — | `image_alt` | 0 |
| `tab_timing` | Tab Break | — | `tab_timing` | 0 |
| `sb_timing` | Section Break | — | `sb_timing` | 0 |
| `start_date_as_stated` | Data | — | `start_date_as_stated` | 0 |
| `start_date` | Datetime | — | `start_date` | 0 |
| `start_date_precision` | Select | exact, minute, day, month, year, decade, approximate, uncertain, range, unknown | `start_date_precision` | 0 |
| `end_date_as_stated` | Data | — | `end_date_as_stated` | 0 |
| `end_date` | Datetime | — | `end_date` | 0 |
| `end_date_precision` | Select | exact, minute, day, month, year, decade, approximate, uncertain, range, unknown | `end_date_precision` | 0 |
| `sb_place` | Section Break | — | `sb_place` | 0 |
| `place` | Link | Place | `place` | 0 |
| `cb_place` | Column Break | — | `cb_place` | 0 |
| `place_as_stated` | Data | — | `place_as_stated` | 0 |
| `sb_detail` | Section Break | — | `sb_detail` | 0 |
| `description` | Text Editor | — | `description` | 0 |
| `significance` | Text Editor | — | `significance` | 0 |
| `tab_evidence` | Tab Break | — | `tab_evidence` | 0 |
| `sb_geo` | Section Break | — | `sb_geo` | 0 |
| `latitude` | Float | — | `latitude` | 0 |
| `longitude` | Float | — | `longitude` | 0 |
| `geo_precision` | Select | exact, approximate, centroid, uncertain | `geo_precision` | 0 |
| `geocoding_method` | Select | manual, map_pick, coordinate_entry, gazetteer, administrative, city_centroid, geocoder, historical_map, inherited | `geocoding_method` | 0 |
| `geo_uncertainty_m` | Float | — | `geo_uncertainty_m` | 0 |
| `geometry_source` | Data | — | `geometry_source` | 0 |
| `tab_provenance` | Tab Break | — | `tab_provenance` | 0 |
| `sb_evidence` | Section Break | — | `sb_evidence` | 0 |
| `primary_source` | Link | Source | `primary_source` | 0 |
| `documentation_level` | Link | Documentation Level | `documentation_level` | 0 |
| `authentication_level` | Link | Authentication Level | `authentication_level` | 0 |
| `cb_provenance` | Column Break | — | `cb_provenance` | 0 |
| `workflow_state` | Link | Workflow State | `workflow_state` | 0 |
| `researcher_notes` | Text | — | `researcher_notes` | 1 |
| `sb_evidence_table` | Section Break | — | `sb_evidence_table` | 0 |
| `evidence` | Table | Evidence | `evidence` | 0 |
| `sb_identifiers` | Section Break | — | `sb_identifiers` | 0 |
| `external_identifiers` | Table | External Identifier | `external_identifiers` | 0 |

Additionally preserve and independently verify `name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx` and any applicable optional system fields (`_user_tags`, `_assign`, `_liked_by`, `_seen`) without assuming every field is physically present. `doctype` is identity metadata rather than necessarily a physical SQL column. Child `parent`, `parenttype`, `parentfield`, `idx`, name, owner/timestamps and all child values require separate verification. The source has 31 non-layout fields; `researcher_notes` has permlevel 1. Source role rows and field permissions are **not** evidence of the site's effective permissions; map and review them for the new research DocType and restore the matching core calendar permissions separately.

## Known code, metadata and reference dependencies

These are reviewed source-code examples, **not an exhaustive search of the installed site or integrations**:

- SIRAJ `visualization.py` entity/geo/graph/structure lists and Event detail fields; Explorer page JS and translations; Entity Relationship Graph and data-quality reports; Events by Type chart, Total Events number card and workspace links. Workspace JSON is locally modified on the owner's machine and must not be overwritten.
- `Relationship.subject_type`/`subject` and `object_type`/`object`: pair each selector and Dynamic Link target, classifying **each** reference; change only a reviewed research reference to the new type. Preserve calendar references; missing targets or ambiguous semantics stop. Type selectors and endpoint names must be checked together.
- Metadata links in Place, Event Type, Authentication Level and Documentation Level, and parent metadata in Source and External ID Scheme; distinguish link metadata from record values and customize individually. Guarded sample fixture and permission/coordinate diagnostics still reference legacy Event; neither is migration authorization.
- `Evidence` and `External Identifier` child rows (`parenttype`, `parentfield`, `parent`); `File.attached_to_doctype`/`attached_to_name`, `Comment.reference_doctype`/`reference_name`, assignments/ToDo, shares, Versions and other audit/notification/activity records. Preserve private/public files and paths, comments and history; decide explicitly whether historical `Version` payloads remain historical references or require a separate compliant representation. Do not globally replace type strings or edit opaque history blindly.
- Frappe v15.126.1 registers Event calendar/email routes, query/document permission hooks and Google Calendar insert/update/trash handlers. ERPNext v15.125.0 registers an Event form script and `after_insert` CRM prospect-linking hook. Core calendar fields, participants, reminders and integrations must work after restoration. Validate the actual installed versions, enabled integrations, server scripts and any local app/wildcard overrides.
- Inspect all metadata direct Links, Dynamic Link selectors/values and child parent types, plus report SQL, fixtures, custom scripts, workflows, DocPerm/Custom DocPerm, Custom Fields, Property Setters, background jobs, webhooks, API clients, File storage and external systems. A metadata scan, grep, zero count or sample marker cannot prove exhaustive coverage. Treat each unknown/unscannable area as a blocker.

## Required classification and integrity contract

Build a protected, versioned inventory of **every** source Event row and target-name collision, each polymorphic/direct reference, children, files, comments, ownership and audit records, customizations and external dependencies. Use authoritative ownership evidence to assign research, calendar or ambiguous; do not infer solely from IDs, an Event type or zero table count. Record orphan references, duplicates, mismatched type/value pairs, conflicting target names and schema/customization conflicts. Require explicit decisions for each ambiguous and orphaned item. All actual identifiers, field values and manifests are sensitive; don't publish them in Git or chat.

Before mutation, require documented review of exact metadata, physical types/indexes/defaults/nullability, schema version, hooks, app versions, shares/permissions, record and reference mappings, external dependencies, fresh backup and successful isolated restore. Establish immutable, access-controlled source/target fingerprints and per-record values/child counts; hashes can leak information about low-entropy values and must be protected. Revalidate under an approved write/job/integration freeze immediately before each change. Any changed fingerprint, incomplete/unsupported inventory, unclassified record, collision, missing target, unknown field/DDL or failed backup/restore stops execution.

A future transition must be idempotent with a durable, protected journal and explicit phase checks; repeated, partially completed or interrupted states must be classified and fail closed rather than replaying writes blindly. Restore core metadata/controller from the **matching installed Frappe version** only using a separately implemented and rehearsed mechanism. Preserve content and explicitly approved references, customizations and standard fields; do not disable core hooks. Afterward compare the protected manifests, every mapped field/value and child relationship, attachments/comments/audit/ownership/timestamps, permissions, schema/indexes, app consumers, references and external integrations. Verify both calendar and research CRUD as appropriate on a separately authorized isolated copy. Aggregate equality alone is insufficient.

## Rollback and stop conditions

No database rollback implementation exists. The current in-memory `rollback_projection` is not a site rollback. The candidate recovery strategy is a rehearsed whole-site database/config/files/app-version restore from a fresh verified backup, under a separate approved maintenance window. It reverts unrelated app writes since the backup; freeze and preserve/reconcile those changes before a restore. DDL and external effects may not be transactionally reversible, and restoring DB alone is insufficient for files, queues and integrations. Test partial/interrupted DDL, recovery, repeat and post-restore integrity in an approved isolated environment first. Never delete records or identify them for cleanup solely by a prefix or sample marker.

`event_transition_review.review` provides a fixture-only in-memory issue report for supplied metadata, classifications, polymorphic reference entries, target names and coverage declarations. Coverage is a user assertion, not verified by the tool; the output includes identifiers and `execution_ready` is always false. It cannot inventory the site or establish that any mutation is safe. The complete real-site inventory, migration executor and tested database rollback remain open.

## Fixture discovery and gate framework (proposal, not authorization)

`event_reference_review.discover(files)` accepts caller-supplied `{path,text}` entries, not paths to fetch or execute. It emits unclassified line candidates in app code, hooks, reports/dashboards, integration code and other files, plus metadata Link/Select and **all** Dynamic Link definitions, including those whose selectors contain no literal Event. Invalid metadata/missing Dynamic Link selectors are blockers. `classify` accepts a separate explicit evidence-bearing research/calendar/shared/unrelated/ambiguous decision for each zero-based finding; unreviewed and ambiguous entries remain blockers. These decisions are claims, not proof. Inputs/outputs can contain confidential paths, snippets and record identifiers; protect them and never commit site-derived manifests.

Static lexical matching is a candidate-discovery framework, **not a complete reference inventory**: aliases, translated strings, computed names, raw SQL, binary assets, indirect calls, metadata overrides and external systems can evade it; unrelated lines can match. A full app-code review must enumerate all tracked/relevant app and framework files at the exact installed revisions, record skipped/binary files, manually review every candidate and investigate nonliteral construction, scripts, reports, background jobs and network consumers. The scanner does not itself read Git, inspect Frappe or assert a supplied corpus is complete. Tests include a committed-code smoke check and synthetic hook/report/integration/metadata examples, not the real site.

`rehearsal` is a fixture-only wrapper around the projection and rollback primitives. It reports separate gates: supplied coverage claims; all scanner findings classified and no parse errors; selected source/target metadata comparison; preflight requiring those gates plus a valid projection; an explicitly supplied post-state matching every model row; and guarded in-memory reversal matching the initial state. Missing post-state is not a pass. It catches ambiguous or missing references, duplicate source/target identities, schema discrepancies, conflicting changed rows and orphaned snapshots. It carries forward attachments, comments, child rows and arbitrary custom values in synthetic rows. The low-level `rollback_projection` returns a restored list for backward compatibility; it is an in-memory primitive, not an executable rollback; the rehearsal wrapper always returns `execution_ready: false`. Planner, projection and integrity report likewise return `execution_ready: false`.

Actual preflight requires, on a separately authorized isolated copy, effective metadata and physical schema/index comparison (including custom fields and property setters), installed app/hook versions, every source/target row and attachment/comment/child/audit reference, polymorphic selectors and targets, permissions/workflows/scripts/integrations, external consumers, duplicate/orphan decisions and a fresh independently restore-tested backup. Coverage claims passed to the fixture framework do not verify any of these. Freeze concurrent writers and compare protected preflight fingerprints immediately before a separately approved operation. Stop on unknown, mismatch, ambiguity, failed restore or changing input. Post-migration gates must compare all mapped values and identities, owner/timestamps, child order/links, files/comments/audit, schema and permissions against a protected baseline; exercise research and core calendar behavior and external integrations, then validate restoration from backup. There is no such implementation or database rehearsal yet; the hypothetical fixture post-state cannot establish these site gates.

A reproducible **committed app text candidate scan** is `python3 tests/scan_committed_event_fixture.py` from the repository root. It reads `git archive HEAD` without extracting it and emits aggregate counts only; the scanner implementation itself is imported from the worktree. It scans only UTF-8 app files with the listed extensions, not untracked files, binary formats, Frappe/framework/other apps, site customizations, data, or external systems. Local scanner edits could affect results. A sandbox run at `ea14b18ee6ce3427c6574be900b768297907d31b` found 332 files, 232 unclassified candidates, 0 metadata parse issues and 0 UTF-8 skips: 228 text candidates, 2 Dynamic Links and 2 Event selectors. This is an inventory of matches, **not** 232 actual references or evidence that any site is safe. All candidates still need human classification and the unscanned areas remain unknown.

## Guarded whole-snapshot journal model

`event_rehearsal_journal.py` prepares a complete synthetic before/after snapshot and recomputes the narrow projection on every transition. It returns an in-memory projected/reversed copy, accepts exact repeat calls idempotently, and rejects partial, added, missing or edited rows and inconsistent journals. It tests research/calendar Events and attachments, comments, child records, relationship links, custom fields and timestamps in supplied fixtures. Its restrictive whole-snapshot comparison treats unrelated new rows as a conflict instead of deleting them. **This is not a Frappe migration or database rollback**: the manifest is not authenticated or independently complete, the research Event copy model retains the conflicting old Event, and direct Links, hooks, core restoration, file contents, DDL, external effects and actual database recovery are unimplemented. `execution_ready` is always false. A future DB implementation still requires an approved isolated copy, independently verified inventory, physical backup and restore rehearsal, concurrency controls and separate owner authorization.

## Integrated stale-state fixture bundle

`event_integrity_bundle.py` composes supplied text discovery and explicit classifications, selected custom-field schema comparison, pre/post fixture checks and the whole-snapshot journal. It produces no bundle when its fixture gates fail. A domain-separated SHA-256 fingerprint binds the supplied corpus, decisions, coverage assertions, metadata and journal; subsequent projection/reversal recomputes gates and checks fresh code, metadata, classifications, references and full before/after rows. Changed source or destination, partial state or stale attachments/children reject. A separately protected expected fingerprint is required: this is a checksum, **not** a signature, trusted inventory, site identity or protection if both bundle and checksum are replaced. `execution_ready` is always false; source/target field comparison remains limited and coverage claims are unverified.

The actual installed Frappe/ERPNext versions and hooks, effective custom fields/property setters, physical schema and indexes, all records and polymorphic/direct references, files/comments/children/audit/ownership, external consumers and background jobs, permission behavior, write freeze, fresh backup and successful isolated restore can only be assessed on a separately authorized isolated copy of the owner's site. The current committed research Event collision is not resolved and no core Event restoration, site migration executor or physical rollback exists.

## Selected upstream contracts and combined fixture review

Static source inspection (not site introspection) of Frappe `v15.126.1` commit `2e9ecdc03fa5b5b8d1ba05224a1aff7dad832bd0` found core `Event` in `Desk`, a calendar/email target with Event permission query/document hooks and Google Calendar lifecycle/scheduler integration. Its `event_type` is a `Select` (Private/Public), unlike SIRAJ's Link to Event Type; calendar code also expects `subject`, `starts_on`, participants and Google Calendar fields. ERPNext `v15.125.0` commit `6ad0ff6362db0c672e3706aa0a0d65119b1a34e2` registers an Event client script and prospect-linking `after_insert` handler. Inspect the **actual** installed source, other apps and local hooks/customizations before drawing site conclusions. Upstream references: [Frappe Event metadata](https://github.com/frappe/frappe/blob/v15.126.1/frappe/desk/doctype/event/event.json), [Frappe hooks](https://github.com/frappe/frappe/blob/v15.126.1/frappe/hooks.py), [ERPNext hooks](https://github.com/frappe/erpnext/blob/v15.125.0/erpnext/hooks.py). These selected fields and hooks are not exhaustive.

`event_compatibility.py` compares only selected caller-supplied core/reference and proposed research metadata contracts; it is not a runtime adapter or validation of effective site metadata. `event_reference_matrix.py` inventories supplied metadata/rows for direct Links, Dynamic Links and child parent references, flags missing/ambiguous/orphaned data and requires evidence-bearing decisions. It includes supplied Event-owned fields and records. `event_integrated_review.py` composes these checks with the existing source-discovery and full-snapshot rehearsal, checks that the reference matrix's source Event metadata matches the projection source metadata, and requires every discovered polymorphic reference to be in the projection plan. **Any supplied direct Event Link definition blocks this combined rehearsal**, even with no corresponding rows, because changing its metadata and behavior is not modeled. Event-owned reference projection is unsupported and blocks. Empty or incomplete caller-supplied corpora can still omit entire unknown DocTypes, source code, external consumers or hooks; passing status cannot establish inventory completeness.

The combined fixture bundle binds supplied selected core metadata, reference metadata/decisions, physical-schema and hook claims and the prior journal to a domain-separated checksum. On fixture projection/reversal it compares fresh supplied snapshots/schema/hooks, recomputes review checks, and rejects altered or incomplete planned references. The physical-schema and hook objects are arbitrary supplied claims, not independent compatibility validation. The expected checksum must be protected separately; it is not authentication, a trusted site identity or a verified backup. All bundles/findings may contain sensitive identifiers and values. No network, Frappe connection, site writes, DDL, hook execution or actual rollback occurs. `fixture_ready` is exclusively a narrow in-memory model status; `execution_ready` remains false. The collision and all real-site/permission/recovery blockers remain open.

Fixture-only checks, from the app root, do not require a bench or site:

```sh
python3 -m unittest discover -s tests -p 'test_event_compatibility.py' -v
python3 -m unittest discover -s tests -p 'test_event_reference_matrix.py' -v
python3 -m unittest discover -s tests -p 'test_event_integrated_review.py' -v
```

Expected: 4, 5 and 6 tests respectively, all OK. Failures or missing tests are not acceptance. These commands do not inspect the site, resolve the collision or approve migration; separately reviewed authorization is required for site diagnostics or any operational change.
