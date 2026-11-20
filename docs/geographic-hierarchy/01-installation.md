# 1. Installation & setup commands

Everything below is a `bench` command against an existing Frappe v15 bench. The
app never installs the framework, the database server or an OS package; that is
outside this document's scope by design.

```bash
export BENCH=~/frappe-bench
export SITE=research.local
export APP=siraj_research
export REPO=https://github.com/josuecano22222-rgb/Siraj-Research.git
```

## 1.1 Pre-flight (read-only)

```bash
cd "$BENCH"
bench version                          # frappe 15.x, plus your other apps
./env/bin/python --version             # 3.10 – 3.12
bench --site "$SITE" list-apps         # confirm the site exists
bench --site "$SITE" execute frappe.db.get_value \
  --kwargs '{"doctype":"DocType","filters":{"name":"DocType"},"fieldname":"name"}'
```

The last command is a cheap "site boots" check. If it fails, fix the bench
before installing anything.

## 1.2 Get the app

```bash
cd "$BENCH"

# Fresh install from the repository
bench get-app "$REPO" --branch main

# Already present? Update instead (never delete the app folder)
bench update --apps "$APP" --no-backup   # only after reviewing the changelog
```

`get-app` clones into `apps/siraj_research` and links
`apps/siraj_research/siraj_research` into the site's Python path. It also runs
`bench setup requirements --app siraj_research` when the app declares a
`requirements.txt` (this repository does).

**Pinned Python dependencies** (`requirements.txt`, installed into `env/`):

| Package | Pin | Used for | Optional? |
|---|---|---|---|
| `shapely` | `2.0.6` | WKB parsing, `STRtree` point-in-polygon when PostGIS is absent | yes |
| `pyproj` | `3.6.1` | CRS handling / reprojection of imported boundaries | yes |
| `pyogrio` | `0.9.0` | fast GDAL vector reads (falls back to `fiona`/GeoJSON when absent) | yes |

The app imports these lazily: `siraj_research/geo_import.deps_ok()` reports
what is missing, and the resolver chooses PostGIS → Shapely → `unresolved`.
Install them explicitly if `get-app` skipped requirements (offline benches,
`--no-requirements`):

```bash
./env/bin/pip install -r apps/siraj_research/requirements.txt
# equivalently
bench setup requirements --app siraj_research
```

Offline reinstall from a wheel directory:

```bash
./env/bin/pip install --no-index \
  --find-links=sites/$SITE/private/offline-cache/wheels \
  -r apps/siraj_research/requirements.txt
```

The wheel set is produced while online by
`bench --site "$SITE" execute siraj_research.offline_bootstrap.download_python_wheels`
(chapter 5). Pins match `siraj_research/requirements-offline.txt` exactly, so
`pip download` and `pip install --no-index` resolve the same versions.

## 1.3 Install the app on the site

```bash
cd "$BENCH"
bench --site "$SITE" install-app siraj_research
```

`install-app` runs, in order:

1. Frappe creates the app's DocTypes and tables (including
   `tabAdmin Boundary Geom` when `spatial_backend="postgis"` is selected later —
   the table itself is created by `geo_postgis.init_schema`).
2. `siraj_research.hooks.after_install` (`siraj_research/setup/install.py`)
   creates the four SIRAJ roles, the `Draft` Workflow State if missing, and runs
   the additive reference seed:
   `249` countries, `17` lookup domains, `4011` governorates/regions,
   `1411` districts, `80` municipality/village/community units, the
   `SIRAJ-REFERENCE` Boundary Dataset, the six `Admin Level` rows and the six
   country configurations (IQ 5, SA 4, LB 3, JO 4, PS 5, IL 4).
3. `patches.txt` is applied in order, including `v1_2` which adds the level
   configuration, the ancestry fields and the `Geographic Administration`
   DocType.

`after_install` is **idempotent**. If it is interrupted, rerun it directly:

```bash
bench --site "$SITE" execute siraj_research.setup.install.after_install
```

Nothing in the install path downloads a polygon, a tile or a place name.

## 1.4 Migrate, build, clear cache

Every install and every upgrade needs all three:

```bash
cd "$BENCH"
bench --site "$SITE" migrate
bench build --app siraj_research
bench --site "$SITE" clear-cache
bench restart
```

What each one does for this app:

* `migrate` — applies schema changes (new fields, new DocTypes), executes
  `patches.txt`, reloads DocType metadata and fixtures. Fixtures include the
  four roles, the SIRAJ Review workflow, the dossier Print Format and workflow
  states.
* `build --app siraj_research` — copies `siraj_research/public/**` to
  `sites/assets/siraj_research/**`. This is mandatory for the offline stack:
  Leaflet, MapLibre, D3, JSZip, TopoJSON, vis-network and the `world-atlas`
  bundle are served from `/assets/siraj_research/vendor/…`, and the offline
  viewer lives at `/assets/siraj_research/offline_map/index.html`.
* `clear-cache` — drops Redis keys, including the level-configuration cache
  (`siraj:geo_levels:<country>`, TTL 3600 s) and the resolver caches.
* `restart` — recycles web workers so new Python modules are importable.

If you changed only Python and not assets, `bench --site "$SITE" clear-cache`
plus `bench restart` is enough. If you changed JS/CSS, always rebuild.

## 1.5 Verify the installation

```bash
cd "$BENCH"

# a) DocTypes and patches are present
bench --site "$SITE" execute siraj_research.geo_levels.config_payload \
  --kwargs '{"country":"IQ"}' | head -40

# b) PostGIS availability (safe on MariaDB — reports postgis_available=false)
bench --site "$SITE" execute siraj_research.geo_postgis.health

# c) Reference data counts (read-only; exits 1 when the hierarchy is broken)
bench --site "$SITE" geo audit
```

Expected shape of `geo audit` on a fresh install:

```json
{"passed": true, "country": null,
 "counts": {"Governorate": 4011, "District": 1411, "Municipality": 8,
            "Village": 69, "Community": 3},
 "issues": [], "level_configs": 6}
```

The exact numbers follow your reference files; `issues: []` and
`passed: true` are the contract.

Smoke-test the resolver. Without a boundary dataset it must answer honestly:

```bash
bench --site "$SITE" geo resolve --lat 33.3152 --lon 44.3661
# {"resolved": false, "reason": "no_dataset", "warnings": ["no active boundary dataset"]}
```

After importing boundaries (chapter 4), the same command returns a full chain
(chapter 6, §6.4).

## 1.6 Optional: enable PostGIS

Skip this on MariaDB. On PostgreSQL, the extension is created **once per
database**, by a superuser or a role allowed to `CREATE EXTENSION`:

```bash
psql -d "$(bench --site "$SITE" execute frappe.conf.db_name 2>/dev/null | tr -d '\"')" \
     -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Then point the app at it and materialise the geometry column:

```bash
bench --site "$SITE" execute frappe.client.set_value \
  --kwargs '{"doctype":"Geo Settings","name":"Geo Settings","fieldname":"spatial_backend","value":"postgis"}'

bench --site "$SITE" geo postgis-init
bench --site "$SITE" geo postgis-health
bench --site "$SITE" geo postgis-backfill --dataset SIRAJ-REFERENCE --batch-size 500
```

`postgis-init` is idempotent: it creates `tabAdmin Boundary Geom`
(`geom geometry(Geometry, 4326)`), the GiST index
`idx_siraj_admin_boundary_geom`, and a dataset-version column used to invalidate
the resolver cache. `postgis-backfill` copies `Admin Boundary`, `Admin Boundary
Geom` and `District` polygons into that table in chunks, logs progress, and can
be resumed (it skips rows whose geometry hash is unchanged).

Rollback if you want the Shapely path back:

```bash
bench --site "$SITE" execute frappe.client.set_value \
  --kwargs '{"doctype":"Geo Settings","name":"Geo Settings","fieldname":"spatial_backend","value":"shapely"}'
bench --site "$SITE" clear-cache
```

## 1.7 Roles and permissions after install

| Role | Geography permissions |
|---|---|
| `SIRAJ Viewer` | read Country/Governorate/District/Municipality/Village/Community, `Geographic Administration`, `Admin Level`, `Country Level Config` |
| `SIRAJ Researcher` | read + create/edit the above; cannot delete |
| `SIRAJ Reviewer` | read + submit/cancel review workflow; no schema changes |
| `SIRAJ Administrator` | full CRUD, can run seeding and change level configuration |

The whitelisted resolver (`siraj_research.api.geo_resolve.resolve_point`)
requires a logged-in session that can read at least one level DocType; it never
returns records the caller cannot read. See §4.7 for the exact permission gate.

## 1.8 Upgrade path

```bash
cd "$BENCH"
git -C apps/siraj_research pull --ff-only
bench --site "$SITE" migrate
bench build --app siraj_research
bench --site "$SITE" clear-cache
bench restart
```

Re-running a single patch is supported and idempotent:

```bash
bench --site "$SITE" execute siraj_research.patches.v1_2.add_level_config_and_ancestry.execute
```

That patch:

1. creates `Admin Level`, `Country Level Config` and `Country Level Row` rows if
   absent (never overwrites an administrator's edited configuration),
2. adds `is_active`, `hierarchy_level`, `ancestry_path`, `ancestry_labels` to the
   five level DocTypes (site custom fields, `depends_on` free),
3. backfills ancestry for existing records in batches with
   `update_modified=False`, so audit trails are untouched.

## 1.9 Clean uninstall

> **Back up first.** `bench --site "$SITE" backup --with-files` and verify a
> restore on a scratch site. Uninstall drops the app's tables; it does not drop
> your other apps' data.

```bash
cd "$BENCH"
bench --site "$SITE" backup --with-files
bench --site "$SITE" uninstall-app siraj_research --yes
bench --site "$SITE" clear-cache
bench restart
rm -rf apps/siraj_research          # optional, only after the backup is verified
```

What the uninstall hooks do (`siraj_research/setup/uninstall.py`, wired as
`before_uninstall` / `after_uninstall`):

* remove the `geographic_administration` Custom Field from `Place`, `Person`,
  `Institution`, `Research Event`, `Siraj Event`, `Military Unit` and
  `Operational Deployment` (otherwise the field survives with a dangling Link),
* clear `siraj:` cache keys (`siraj:geo_levels:*`, `tabAdmin Boundary Geom`
  dataset index),
* leave every standard Frappe table untouched.

Frappe drops the app's DocType tables itself, including
`tabAdmin Boundary Geom`, so the PostGIS geometry column and its GiST index go
with it. Site files under `private/siraj_maps`, `private/siraj_tile_cache` and
`private/offline-cache` are **not** deleted automatically; remove them
manually if they are no longer wanted (they can be large, see chapter 5).

Reinstall in the same site is supported immediately after uninstall:

```bash
bench --site "$SITE" install-app siraj_research
bench --site "$SITE" migrate
```

## 1.10 Common installation problems

| Symptom | Cause | Fix |
|---|---|---|
| `App siraj_research not found` | `get-app` ran in the wrong directory | `cd ~/frappe-bench` and rerun |
| `ModuleNotFoundError: shapely` | requirements skipped | `bench setup requirements --app siraj_research` then `bench restart` |
| Assets 404 (`/assets/siraj_research/...`) | build skipped | `bench build --app siraj_research` |
| Level labels unchanged after editing a config | Redis cache | `bench --site "$SITE" clear-cache` |
| `geo audit` reports `missing_active_ancestor` | data imported before v1.2 | `bench --site "$SITE" geo backfill-ancestry` |
| PostGIS commands report `db_type: mariadb` | wrong backend | expected; use the Shapely resolver or move the site to PostgreSQL |

Installation is complete when §1.5 returns `passed: true`, assets load from
`/assets/siraj_research/`, and `geo resolve` answers with a structured JSON
object. Continue with [core data](02-core-data.md).
