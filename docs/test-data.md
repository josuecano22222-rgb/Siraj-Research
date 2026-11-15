# Isolated synthetic test dataset

The fixture in `siraj_research.setup.test_data` creates fictional, visibly `TEST`-labelled records on a **separate, newly created Frappe site with its own empty database**. It is not installed automatically, is not a web endpoint and must never be run on production, a production clone, a database shared with another site, or an existing site containing real data. It does not alter or delete production records. It is a small functional fixture, not a scale, security, migration, localization or production-data substitute.

It covers all **50 bundled SIRAJ DocTypes**: synthetic lookup and geographic rows, connected people, organization, place, event, source and relationships, the command hierarchy and operations, and each child-table DocType as a row on its parent. The **SIRAJ Settings** singleton already exists by Frappe's single-DocType semantics; the fixture leaves its settings unchanged rather than attempting to create a second copy. It also uses the standard `Iraq` Country, `Military` Person Category and `Draft` Workflow State installed on the test site. These Frappe/site prerequisites are not production data.

The graph includes an isolated-by-filter relationship, a symmetric ended relationship without evidence, and evidenced directed relationships; the military view contains a region hierarchy, parent and child unit, and operations. These are fictitious examples and coordinates, not claims about actual people or organizations.

## Create and populate a disposable site

An administrator should first verify the bench has sufficient capacity and that `new-site` creates a **new database**, not an alias, restore or clone of any real site. Obtain backups of important sites before administering the bench. Use a site name ending in `.test.localhost`; the name below is an example, not an existing production site. `new-site` prompts for database and Administrator credentials locally; do not paste them into chat or scripts.

```bash
cd /home/frappe/frappe-bench
bench new-site siraj.test.localhost
bench --site siraj.test.localhost install-app siraj_research
bench --site siraj.test.localhost set-config siraj_test_fixture_site siraj.test.localhost
bench --site siraj.test.localhost execute siraj_research.setup.test_data.seed_test_data
bench --site siraj.test.localhost set-config siraj_test_fixture_site disabled
bench --site siraj.test.localhost clear-cache
```

Only proceed if installation succeeded and the test site's database is separate. Configure local DNS or the bench proxy for the test hostname, and restrict access to authorized testers; `.localhost` alone does not secure a deployment. App assets are shared by sites on a bench, while databases, records and site configuration must remain separate. The normal install adds reference/master data to the test database as well; the synthetic fixture adds its own `TEST` reference values and operational records. It reports created counts by DocType and does not print record contents.

The fixture requires both the matching site-specific opt-in and suffix, checks the installed prerequisites, and refuses to run if **any** of its operational DocTypes already contains records, regardless of list permissions. These checks reduce mistakes but cannot prove that two site configurations do not point to the same database or that a database was not cloned; the operator must independently ensure isolation. Do not run concurrently with any other test-site writes. A second run is rejected; to start over, create a new isolated site/database rather than attempting bulk deletion. If an insertion fails, the fixture requests a transaction rollback and raises the error. Frappe's bench command commits after a successful return. Never use a skip-failing migration or bypass the guard.

The test dataset has passed schema-aware simulated tests, including coverage, links, child rows, refusal and rollback. **It has not yet been executed on a live Frappe bench**; if installation or seeding fails, preserve the error (redact secrets) and do not try it on production. After successful creation, verify the Explorer, record forms, counts and role-specific access on this test site; do not assume synthetic tests establish real permissions or full original-app parity.
