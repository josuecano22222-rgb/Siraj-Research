# Event collision: assessment and proposed remediation

**Status: unresolved.** The fictional-data command deliberately refuses before writing. Do not use this document as an operational migration procedure. Do not run `migrate`, `reinstall`, force a metadata reload, delete records, or disable the calendar hooks to work around this issue. A migration must first be implemented, reviewed and rehearsed against a restore-tested copy appropriate to the site's actual app versions and customizations.

## Observed site state

The operator's read-only diagnostic on `frappe.com` reported `Event` metadata owned by `Siraj Research`; SIRAJ fields `title_ar`, `display_name`, and `event_type` were present in both metadata and table. The Frappe calendar fields `subject`, `starts_on`, `sync_with_google_calendar`, and `google_calendar` were absent from metadata but present as table columns. The table had zero Event rows. All reported operational `TEST SAMPLE` note-marker counts were zero. These are point-in-time observations, not proof that the earlier failure had no nontransactional side effects, or that there are no dependent references, customizations, files, or other affected records. Counts do not establish ownership. The subsequent seed attempt was rejected by the guard before fixture writes; the following `NameError` comes from Frappe's `bench execute` exception fallback, not a second fixture failure.

A second read-only inventory reported zero for every one of its listed reference and customization fields. Its fixed scope does not establish that all site or external dependencies are absent.

The original failure was in Frappe’s `insert_event_in_google_calendar`: the hook reads `doc.sync_with_google_calendar`, a calendar field missing from the active SIRAJ Event metadata. This is not a missing linked record error; Frappe registers that lifecycle hook on the globally named `Event` DocType. The schemas are incompatible even where names overlap: for example both define `event_type`, but with different meanings and options. Simply adding a calendar field or suppressing a hook does not restore the core controller, permissions, calendar functionality, or integration semantics.

## Design direction to evaluate

Separate SIRAJ historical events into a distinct global DocType (for example `SIRAJ Research Event`), restore the standard Frappe `Event` to the correct version of core metadata and controller, and update SIRAJ's links, dynamic-link type values, Explorer, reports, cards, charts, workspace, translations, and form scripts to use the new identity. This is a compatibility change, not merely a display label change; integrations and client code using the old DocType name require explicit review. Avoid globally renaming the existing `Event` DocType without understanding Frappe's rename behavior, because that name is also core's identity and a rename can rewrite references belonging to unrelated apps.

Before implementing an automated transition, inventory installed apps and their exact versions, `Event` custom fields, property setters, permissions and workflows, calendar integrations, dynamic and ordinary links, child rows, attachments, comments, assignments, notifications, audit history, custom scripts, reports, APIs and any external references. An empty Event table does not imply these references do not exist. Establish a policy for ambiguous historical references instead of automatically reclassifying all `Event` references as SIRAJ or calendar. Back up the database, files and configuration and prove a restore. Coordinate downtime and stop background jobs/integrations for any eventual change; DDL and external operations may not roll back with an ordinary transaction.

The implementation must support clean installations as well as explicit safe handling of existing sites, preserve and reconcile applicable customizations and records, and stop on unrecognized or ambiguous states. Verify ordering and Frappe's actual schema-sync and patch behavior for each supported version; do not assume a database transaction can undo DDL. Four old SIRAJ patches are marked completed on this site despite missing modules; that fact does not establish their transformations ran.

## Acceptance before lifting the guard

- A reproducible, version-specific rehearsal on a restored copy covering backup/restore, rollback/recovery, repeat execution, mixed core and SIRAJ references, and both empty and populated legacy Event states.
- Independently verify normal Frappe calendar create, update, delete, permissions, and integrations, and SIRAJ event create, edit, linked records, Explorer, reports and counts. Verify permissions and field-level access for affected roles.
- Validate every fixture document through real Frappe controllers and hooks, verify sample linkage and counts, and review any custom side effects. Preserve the explicit opt-in command; no install-time samples.
- Review the actual production inventory and rehearse its transition. Only then agree a backup-backed maintenance plan and obtain explicit approval for any production migration or reset. A future `reinstall` would destroy data for all apps on the site and is not authorized by this design note.

## Additional limited inventory

The administrator may run the following **read-only** diagnostic after updating the app code, without migration or reinstall:

```bash
bench --site frappe.com execute siraj_research.setup.event_diagnostics.inspect_known_event_references
```

It counts `Event` type values in a fixed selection of Relationship endpoints, child tables, attachments, comments, assignments, versions, shares, and customization records. It returns only field and DocType names and aggregate counts, not record contents or IDs. `null` means the table or column is absent; counts for different fields can overlap. A nonzero count does not determine which event type owns a reference; zero counts do not prove safety. The list does not discover arbitrary custom fields, app-specific references, external systems, free text, or all dependencies. It performs database count queries, so schedule it appropriately for large sites and treat the results as potentially sensitive operational metadata. It does not fix or authorize any migration.

## Fixture dependency-order checks

The local stub fixture tests require each explicit Link, Dynamic Link and child Link target to exist at insertion time. They also invoke the bundled Person, Institution, Place, Source, Event, Relationship, Military Unit, Operational Deployment, Mission, Training Exercise and Command Appointment controller methods against a fake database and check the unit rollup, training duration and relationship direction. They deliberately bypass the guard only within the simulation. These checks help detect missing or wrongly ordered fixture prerequisites and selected controller validation failures; they do **not** exercise Frappe's real insertion lifecycle, database, permissions, hooks, customizations, integrations or restored core Event. The collision and live verification remain blockers.
