# SIRAJ Research — geographic hierarchy, offline maps and demo data

This folder is the **implementation handbook** for the parts of the `Siraj Research`
Frappe v15 app that store administrative geography, resolve coordinates to that
geography, and keep the whole stack working with no external network.

The six chapters follow the order of the specification:

| # | Chapter | What it answers |
|---|---------|-----------------|
| 1 | [Installation & setup](01-installation.md) | Exact commands to install, migrate, build, verify and remove the app |
| 2 | [Core data](02-core-data.md) | Countries, level definitions, per-country active labels and ordering |
| 3 | [Demo data](03-demo-data.md) | The interconnected `[DEMO]` dataset and how to seed / tear it down |
| 4 | [Hierarchy & DocTypes](04-hierarchy-and-doctypes.md) | Schemas, ancestry, validation, `Geographic Administration`, seeding |
| 5 | [Offline operation](05-offline-operation.md) | Local tiles, local assets, boundary storage, zero-network verification |
| 6 | [Verification & deliverables](06-verification.md) | Architecture, data model, file map, test matrix, troubleshooting |

## Scope and assumptions

**In scope:** the custom app only — DocTypes, controllers, patches, seeding
commands, JS widgets, local assets, tests, documentation.

**Out of scope (assumed to exist and assumed correct):** operating system, Python
runtime, MariaDB/PostgreSQL server, Redis, Node, the `frappe` framework checkout,
the bench directory, DNS/TLS, and the site itself. Every command below is
`bench …`; nothing in this guide asks you to install a database or a bench.

Working assumptions, stated once so the commands are reproducible:

1. Bench root is `~/frappe-bench`; site name is `research.local`; app is installed
   from a Git checkout of this repository. Replace both freely — nothing in the
   app hard-codes either.
2. **MariaDB is the default, fully exercised backend.** Frappe v15's PostgreSQL
   support is used as-is; the optional PostGIS acceleration path
   (`spatial_backend = "postgis"`) requires a PostgreSQL database with the
   `postgis` extension. The app degrades to the pure-Python Shapely path when
   PostGIS is absent, so a MariaDB site is never blocked.
3. Coordinate order everywhere is **latitude, longitude** in the UI and APIs,
   and **longitude, latitude (x, y)** in GeoJSON and PostGIS. This is stated in
   every field label and in the API docstrings.
4. Boundary polygons and gazetteer files are **administrator-supplied local
   files**. Nothing is downloaded during `install-app` or `migrate`.
5. The reference tree ships `249` countries, `4011` governorates/regions,
   `1411` districts, `80` municipality/village/community units and six country
   level configurations. Counts are data, not code: the seeding reports always
   print the actual numbers for your copy.
6. "Offline" means **no external hosts**. Users still reach their own Frappe
   server over the LAN; the browser only requests same-origin URLs.

## Status of this drop (v1.2)

New in this version, all additive and idempotent:

* `Country Level Config` + `Country Level Row` + `Admin Level` — variable-depth
  hierarchy with skipped levels and per-country English/Arabic labels.
* Denormalised `ancestry_path` / `ancestry_labels` on all five level DocTypes,
  maintained by `validate()` and by a resumable backfill patch.
* `Geographic Administration` — one document per resolved place, written by a
  whitelisted API and linked from seven coordinate-bearing DocTypes.
* `PostGIS` geometry table + GiST index, chunked backfill, cache invalidation.
* `bench geo …` command family (13 subcommands) for seeding, auditing,
  benchmarking and offline verification.
* PostGIS-aware resolver with a hard `source="online"` provenance marker and
  per-user rate limiting on every public geo endpoint.
* Seven new pytest modules (282 pure tests) plus an offline verifier that blocks
  sockets in-process before resolving.

Verification status is stated per feature in chapter 6; anything that needs a
live bench is labelled **bench-verified** vs **unit-verified**.

## Five-minute smoke test

```bash
cd ~/frappe-bench
bench --site research.local execute siraj_research.geo_postgis.health
bench --site research.local geo audit
bench --site research.local geo resolve --lat 33.3152 --lon 44.3661
bench --site research.local geo verify-offline --lat 33.3152 --lon 44.3661
```

`geo audit` is read-only. `geo resolve` returns a JSON hierarchy only when an
active boundary dataset is installed; before that it returns
`{"resolved": false, "reason": "no_dataset"}` rather than inventing a place.
