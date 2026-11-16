# Optional synthetic sample data

**Sample insertion is currently paused. Do not retry it.** SIRAJ defines a DocType named `Event`, which conflicts with Frappe's built-in calendar `Event`. The attempted fixture insert failed in Frappe's Google Calendar hook. A safe resolution requires diagnosing and preserving existing site data, separating the DocTypes, and validating the migration and calendar functionality on a real Frappe site. The fixture now refuses before any inserts until that work is complete.

The fictional sample dataset is **not added by installation or migration**. Once the Event collision is safely resolved and the fixture validated, the intended explicit command is `bench --site frappe.com execute siraj_research.setup.test_data.seed_test_data`. Do not run it yet. That command targets the live site's database. It adds real Frappe documents: samples appear in ordinary lists, charts, counts, exports, searches and reports, and normal hooks, integrations or notifications may run. They use the site's database, naming series, permission rules and backups. **They are not isolated from production data**. Do not run it if those effects are unacceptable. Back up the site, including files, and verify a restore before adding data to production. First rehearse on an independently provisioned non-production environment if one is available. The first live attempt failed; it did not establish that the dataset can be inserted safely.

There is no automatic insertion during `install-app`, `migrate` or `reinstall`, no public API, and no automatic deletion. The normal installer separately creates reference/master data; those values are not this fictional sample dataset. Do not confuse a database reset with a safe sample-only cleanup. After a reset, samples are absent unless the explicit command is run again.

## Coverage and identification

The intended dataset covers all **50 currently bundled SIRAJ DocTypes**: synthetic lookups and geographic records, connected people, an organization, place, event, source and relationships, command hierarchy and operations, and each child-table DocType as a row on its parent. **SIRAJ Settings** is a Frappe singleton: it already exists conceptually and is not modified. The fixture uses existing standard `Iraq` Country, `Military` Person Category and `Draft` Workflow State records as shared references. It does not create an independent copy of those references or of the singleton.

Top-level sample records use `TEST` in their labels/codes where the schema permits; each operational record also has `TEST SAMPLE — fictional data, not a real record.` in its researcher notes. Child rows are identified through their sample parents and links; they do not all have a visible TEST label. The command reports counts and the newly created **parent** document IDs by DocType; retain that report securely for review. This is a convenient marker, **not an access-control boundary, unique ownership proof, or reliable automatic deletion rule**. Samples remain visible wherever the user's ordinary permissions permit. Do not delete records based only on a prefix or marker; records may later be edited or linked to real data. There is no sample-only cleanup command.

### Scenario inventory

| Scenario | Included examples |
| --- | --- |
| Languages and scripts | Arabic-only records, bilingual Arabic/English records, French accents, Kurdish/Persian text, Japanese, Cyrillic and Devanagari. Other-language samples use original-name text; the fixture does not assign a Frappe Language link or claim complete language/locale coverage. Lookup labels have Arabic and English text. |
| Completeness | An evidence-backed Person, Institution, Place and Event, plus sparse but schema-valid Person, Institution, Place, Event and Source records with optional fields omitted. Mandatory Arabic names are retained where the schema requires them. “Incomplete” does not mean deliberately inserting invalid records. |
| Dates and geography | Approximate and year-precision dates; missing coordinates, `(0, 0)`, one zero coordinate, an uncertainty radius, and a point in the southern and western hemispheres. The map deliberately excludes `(0, 0)` as ambiguous. Coordinates are illustrative, not claims about real places. |
| Relationships | Directed and symmetric, ongoing and ended; evidenced and without evidence; supporting, contradicting and contextualizing evidence; parallel links, a self-link and isolated records. |
| Structures | Parent/child region and unit hierarchies, an unassigned unit, operations with differing statuses, 16 synthetic person classifications, and 52 additional records in one classification. The latter exercise folded group counts and the 48-record leaf limit. |

With the current definitions, a successful run would create approximately **146 parent records plus 19 child rows** (including 74 People), alongside the existing settings singleton. Counts can change as the fixture evolves. All values are fictional examples, not claims about actual people or organizations. The fixture is not a substitute for permission/role, large-scale, migration, translation-quality, accessibility, invalid-input or concurrency testing. Test those separately; it does not create users or grant roles.

## Safety checks and failures

After the Event blocker is resolved, the command will verify SIRAJ is installed, check prerequisites and checks fixed TEST names and codes for collisions without relying on the user's list permissions. Existing non-sample operational records do **not** block it. If a fixed sample identifier already exists, it stops without intentional updates; a second run is therefore rejected rather than duplicating the fixture. It never knowingly overwrites an existing record with a conflicting identifier. Do not run concurrent seed commands or other writes while it runs: the preflight is not a database-wide lock.

Insertion uses Frappe documents and their normal validations/hooks, with create permission bypassed because this is an administrator-run bench command. It requests a database rollback on an exception; `bench execute` commits after successful return. Custom hooks, external effects, concurrent changes and nontransactional operations may not be undone by rollback. A restore-tested backup and an operational review are essential. If insertion fails, inspect the complete error (the first exception may be followed by a misleading Frappe `NameError`), redact secrets, and verify the site state before any retry. No live Frappe verification has been performed yet; mock tests cover schema, links, sample markers, collision refusal and rollback only.

## Event collision diagnostic

After updating to the version containing `siraj_research.setup.event_diagnostics`, an administrator can run the read-only diagnostic:

```bash
bench --site frappe.com execute siraj_research.setup.event_diagnostics.inspect_event_collision
```

It reports Event metadata/column presence, the total Event row count, and aggregate counts of records bearing the fixture's `TEST SAMPLE` notes marker. It does not return record IDs or contents. The marker counts alone do not prove the failed transaction rolled back completely: markers can pre-exist or have been edited, and hooks may have nontransactional side effects. Review backups and site-specific integrations; do not delete rows or run `reinstall`, `migrate`, metadata reloads or SQL workarounds as a response to this error without a tested plan.
