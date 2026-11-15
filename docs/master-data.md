# Installation reference data

The original `researchers-db` source branch `arena/d114ff02-researchers-db`,
commit `e6796de67daa717eaccd2285a8034302735a4334`, supplies the bilingual
lookup values and geographical reference files under `app/seed.py`,
`app/resources/`, and migrations 019/020. The files in
`siraj_research/setup/reference_data/` retain that source data for inspection.
This installer contains no fictional military or research demo records.

## When it runs

`after_install` inserts missing data using Frappe documents after the DocTypes
are installed. It may take several minutes because the geographical dataset
contains over 5,500 rows. Existing sites do **not** rerun this on every migration:
a site administrator can back up the site and run once from the bench directory:

```sh
bench --site YOUR-SITE backup
bench --site YOUR-SITE execute siraj_research.setup.master_data.seed_master_data
bench --site YOUR-SITE clear-cache
```

The output reports created, already existing, and skipped counts, with up to
25 examples of skipped records. Save this output; resolve any missing or
ambiguous country codes and parent conflicts before rerunning. The operation is
additive and rerunnable: same-code existing values are never overwritten,
re-enabled or renamed; an existing name with another code is reported rather
than replaced. Existing geographic records whose parent does not match are not
used as parents for seeded children. Deleting a seeded record and explicitly
running the installer again will recreate it. Frappe controls the enclosing
transaction; this code does not commit independently. Avoid concurrent seed
runs and take a backup before populating an existing site.

## What maps to Frappe

* Seventeen SIRAJ vocabulary DocTypes receive the original codes, bilingual
  labels and sort order: authentication and documentation levels; person status,
  classification and category; military branch and service status; place,
  institution, institution subcategory, relationship, source and event types;
  source reliability; governance system; leadership quality and level.
  Original color tokens are mapped to hexadecimal colors. Newly inserted
  Relationship Types receive the source's symmetric and inverse semantics;
  pre-existing types are not modified, even if their semantics differ.
* The eight original review labels are mapped to the app's standard Frappe
  Workflow State names. This creates **states only**, not a workflow or
  transition permissions. Existing states are not edited.
* Geographic parents are matched to Frappe's existing `Country` records by
  case-insensitive ISO code. Missing or ambiguous countries are not fabricated.
  The installer adds the original 4,011 governorates, 1,416 distinct districts
  (including legacy districts), 8 municipalities, 69 villages and 3 communities,
  where their parents resolve, carrying English and Arabic labels and direct
  and inherited parent links. No coordinates are assigned or copied to entities.
  Counts are source counts, not a guarantee that every row can be inserted on a
  customised site.

## Explicit limitations and dispositions

* Frappe's `Country` is framework-managed and has no SIRAJ bilingual or
  historical-date fields. The 249 source country labels, aliases, ISO3/region
  metadata and seven historical country entries remain in the bundled source
  files, but are **not** imported as modified or duplicate `Country` records.
  Historical validity and successor data require a separate, reviewed model.
* Original `date_precision`, `geo_precision`, `geocoding_method`,
  `relation_direction` and `evidence_support_type` are represented by app
  Select fields, not lookup records. Their option sets and translations are not
  made equivalent by this installer. Original `entity_type` is represented
  partly by native DocTypes/Dynamic Links; `language` and `locale` are Frappe
  facilities. Original `external_party_type` and `indicator_area` have no
  equivalent seeded DocType here; their values remain in `lookups.json`.
* Original app users, numbering counters, system settings and demo/sample data
  are not imported. Frappe users, roles, naming and site settings are managed
  through their respective native mechanisms. Social Platform, External ID
  Scheme, Specialization and Expertise Area remain unseeded: the source's
  reference initializer did not provide a corresponding authoritative master
  list (example/sample values are not treated as facts).
* Geographic source `type`/aliases and historical metadata do not have matching
  fields in these DocTypes. The originals remain in the bundled files but are
  not written into misleading fields. This is not a full migration of an
  existing source database, a geographic data audit, or complete feature parity.
* The source repository does not include a license file; provenance is kept
  here rather than asserting an unverified license. Confirm redistribution rights
  for the source data before distributing it independently.

Tests: `python3 -m unittest discover -s tests -p 'test_master_data.py' -v`.
Mocks cover the full reference set, idempotence, conflicting parents, existing
records and relationship links. An actual fresh installation and existing-site
run must still be verified on Frappe v15, including install duration and the
operator's returned skip report.
