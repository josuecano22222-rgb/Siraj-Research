# Optional synthetic sample data

The fictional sample dataset is **not added by installation or migration**. After installing the app, an administrator may explicitly run one command on the desired existing site:

```bash
bench --site frappe.com execute siraj_research.setup.test_data.seed_test_data
```

The command above targets the live site's database. It adds real Frappe documents: samples appear in ordinary lists, charts, counts, exports, searches and reports, and normal hooks, integrations or notifications may run. They use the site's database, naming series, permission rules and backups. **They are not isolated from production data**. Do not run it if those effects are unacceptable. Back up the site, including files, and verify a restore before adding data to production. First rehearse on an independently provisioned non-production environment if one is available. The command has not yet been executed on a live Frappe bench.

There is no automatic insertion during `install-app`, `migrate` or `reinstall`, no public API, and no automatic deletion. The normal installer separately creates reference/master data; those values are not this fictional sample dataset. Do not confuse a database reset with a safe sample-only cleanup. After a reset, samples are absent unless the explicit command is run again.

## Coverage and identification

The dataset covers all **50 bundled SIRAJ DocTypes**: synthetic lookups and geographic records, connected people, an organization, place, event, source and relationships, command hierarchy and operations, and each child-table DocType as a row on its parent. **SIRAJ Settings** is a Frappe singleton: it already exists conceptually and is not modified. The fixture uses existing standard `Iraq` Country, `Military` Person Category and `Draft` Workflow State records as shared references. It does not create an independent copy of those references or of the singleton.

Top-level sample records use `TEST` in their labels/codes where the schema permits; each operational record also has `TEST SAMPLE — fictional data, not a real record.` in its researcher notes. Child rows are identified through their sample parents and links; they do not all have a visible TEST label. The command reports counts and the newly created **parent** document IDs by DocType; retain that report securely for review. This is a convenient marker, **not an access-control boundary, unique ownership proof, or reliable automatic deletion rule**. Samples remain visible wherever the user's ordinary permissions permit. Do not delete records based only on a prefix or marker; records may later be edited or linked to real data. There is no sample-only cleanup command.

The graph contains both evidenced directed relationships and a symmetric ended relationship without evidence; the military records include a region hierarchy, parent and child unit, and operations. All names, descriptions and coordinates are fictional examples, not claims about actual people or organizations. The fixture is small and is not a substitute for scale, security or migration testing.

## Safety checks and failures

Before inserting, the command verifies SIRAJ is installed, checks prerequisites and checks fixed TEST names and codes for collisions without relying on the user's list permissions. Existing non-sample operational records do **not** block it. If a fixed sample identifier already exists, it stops without intentional updates; a second run is therefore rejected rather than duplicating the fixture. It never knowingly overwrites an existing record with a conflicting identifier. Do not run concurrent seed commands or other writes while it runs: the preflight is not a database-wide lock.

Insertion uses Frappe documents and their normal validations/hooks, with create permission bypassed because this is an administrator-run bench command. It requests a database rollback on an exception; `bench execute` commits after successful return. Custom hooks, external effects, concurrent changes and nontransactional operations may not be undone by rollback. A restore-tested backup and an operational review are essential. If insertion fails, inspect the complete error (the first exception may be followed by a misleading Frappe `NameError`), redact secrets, and verify the site state before any retry. No live Frappe verification has been performed yet; mock tests cover schema, links, sample markers, collision refusal and rollback only.
