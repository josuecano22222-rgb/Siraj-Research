# The Installation Odyssey

> **Fresh wipe / full session log:** see
> [`from-scratch-runbook.md`](from-scratch-runbook.md) for the complete
> chronological procedure (reinstall → feature branch → import → bootstrap →
> verify → merge), written against real bench output.

> A complete system has just been reformatted. Nothing exists yet — no bench,
> no apps, no geography, no memory of the hierarchy. This guide walks the whole
> journey from bare metal to a fully offline-capable Siraj Research station,
> in the exact order the commands must run. Read it once end-to-end; execute it
> one act at a time.

---

## Prologue — What you are building

Three layers arrive in order, and each one depends on the last:

| Layer | What it gives you |
| --- | --- |
| **Bench** | Frappe + ERPNext skeleton, MariaDB, Redis, worker |
| **Apps** | `siraj_research` only (research core, hierarchy, maps, offline) |
| **Geography** | OSM boundary imports, offline tile packs, geo package, permanent network lock |

The site runs **fully offline** once Act IV finishes. Online access is only
required during preparation.

---

## Act I — Foundations

### 1. System packages

```bash
sudo apt-get update
sudo apt-get install -y \
  git python3-dev python3-pip python3-venv \
  mariadb-server redis-server nodejs npm yarn \
  cron curl wget software-properties-common
```

Enable and start services:

```bash
sudo systemctl enable --now mariadb redis-server cron
```

### 2. Database root (if MariaDB was freshly installed)

```bash
sudo mysql_secure_installation
```

Or set a known root password for local development:

```bash
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'root'; FLUSH PRIVILEGES;"
```

### 3. Bench CLI

```bash
pip install frappe-bench
bench --version
```

### 4. Initialise the bench

```bash
cd ~
bench init frappe-bench --frappe-branch version-15
cd frappe-bench
```

### 5. Create the site

```bash
bench new-site frappe.com \
  --db-root-password root \
  --admin-password admin
bench --site frappe.com install-app frappe
bench --site frappe.com install-app erpnext
```

---

## Act II — The Apps arrive

Both custom apps track **`main`**. Only merges into `main` should ever reach
the bench.

### 6. Get the apps

```bash
cd ~/frappe-bench/apps
git clone https://github.com/josuecano22222-rgb/Siraj-Research.git siraj_research
git -C siraj_research checkout main
git -C siraj_research pull --ff-only origin main
```

This guide updates **only** `siraj_research`. Other apps on the bench are left alone.

> **Rule:** never `reset --hard` to `main` while a feature branch is still
> unmerged. Check first:
>
> ```bash
> git -C ~/frappe-bench/apps/siraj_research log --oneline -3
> ```
>
> If the top commit is older than the release you expect, merge the open PR
> first, then pull.

### 7. Register and install

```bash
cd ~/frappe-bench
bench get-app ./apps/siraj_research
bench --site frappe.com install-app siraj_research
```

---

## Act III — First breath (schema, assets, cache)

Every time code changes on `main`, this is the ritual. Run it in order —
never out of sequence.

Updates touch **only** `siraj_research`. Do **not** run `bench update --reset`
here — that pulls Frappe/ERPNext/HRMS/themes and is unrelated to this app.

**Legacy servers — remove demo data first.** If this site ever ran a
pre-v2 demo build (records without the `siraj_demo_manifest.json`
manifest, or tagged only via legacy sweeps), run the cleanup **once,
before step 1**, so old demo rows cannot block migrations or mix with
fresh content:

```bash
bench --site frappe.com siraj-research remove-demo-data
```

Sites that never loaded demo data skip this and start at step 1.

```bash
cd ~/frappe-bench

# 1. pull latest main for siraj_research only
git -C apps/siraj_research fetch origin main
git -C apps/siraj_research reset --hard origin/main

# 2. migrate this app's DocTypes/patches (site migrate is safe; it only
#    applies pending changes — it does not upgrade other apps' code)
bench --site frappe.com migrate

# 3. rebuild this app's JS/CSS bundle
bench build --app siraj_research

# 4. clear caches and restart workers
bench --site frappe.com clear-cache
bench restart
```

**Verify Act III:**

```bash
grep -n SIRAJ_BUILD apps/siraj_research/siraj_research/record_icons.py
# expect: SIRAJ_BUILD = "2026-11-20.hierarchy-ui.d.19" (or newer)
```

Reload the browser once. DevTools console should show:

```text
offline geo index ready: OSM-IL-PS:2.2 ...
```

---

## Act IV — Geography awakens (online preparation)

This act needs **internet**. After it completes, the site never calls an
external host again.

### 8. Activate a boundary dataset

In Desk: **Boundary Datasets** → confirm status `Complete`, then set it active
in **Geo Settings → Active boundary dataset** (e.g. `OSM-IL-PS`).

From CLI, the equivalent:

`Geo Settings` is a **Single**, so `frappe.client.set_value` requires `name`:

```bash
bench --site frappe.com execute frappe.client.set_value \
  --kwargs '{"doctype":"Geo Settings","name":"Geo Settings","fieldname":"active_boundary_dataset","value":"OSM-IL-PS"}'
```

Or set it from Desk: **Geo Settings → Active boundary dataset**.

Verify:

```bash
bench --site frappe.com execute frappe.client.get_value \
  --kwargs '{"doctype":"Geo Settings","fieldname":"active_boundary_dataset"}'
```

### 9. Import boundaries (per region)

Download a Geofabrik extract while online, then:

If the dataset row already shows **Complete**, skip to step 10.

To (re)build hierarchy from an already-imported boundary dataset:

```bash
bench --site frappe.com execute siraj_research.geo_bulk.sync_boundary_hierarchy \
  --kwargs '{"dataset_code":"OSM-IL-PS","create_missing":True}'
```

`bench --kwargs` is evaluated as **Python**: booleans are `True` / `False`,
never JSON `true` / `false`.

To convert a raw Geofabrik PBF first (requires `osmium-tool`):

```bash
bench --site frappe.com execute siraj_research.geo_bulk.prepare_osm \
  --kwargs '{"input_path":"/home/frappe/frappe-bench/geodata/osm/ile-rus.osm.pbf","output_dir":"/home/frappe/frappe-bench/geodata/osm","run":True}'

# then import the GeoJSON that prepare_osm printed as "output"
bench --site frappe.com execute siraj_research.geo_bulk.import_osm \
  --kwargs '{"dataset_code":"OSM-IL-PS","file_path":"/home/frappe/frappe-bench/geodata/osm/ile-rus-boundaries.geojson","level":0}'
```

For a whole new country in one shot, use **Act IV-b** (`setup_region`).

Expected status on Boundary Dataset: **Complete** with a non-zero boundary count.
A `Failed / 0` row means the PBF was missing — do not leave it behind:

```bash
bench --site frappe.com execute \
  frappe.delete_doc \
  --args '["Boundary Dataset", "OSM-LB"]'
```

### 10. Export the offline geo package

```bash
bench --site frappe.com execute \
  siraj_research.api.geo_package.export_offline_package
```

Expected JSON:

```json
{"written": true, "dataset": "OSM-IL-PS", "version": 2,
 "polygons": 1128, "etag": "OSM-IL-PS:2.2"}
```

### 11. Bootstrap wheels, tiles, hierarchy — then lock offline

```bash
bench --site frappe.com execute \
  siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset": "OSM-IL-PS", "max_zoom": 11}'
```

Watch progress from another terminal:

```bash
tail -f ~/frappe-bench/logs/web.log | grep -i bootstrap
```

If it runs long, open **Geo Settings → Offline Bootstrap** and press
**Stop Offline Bootstrap**. Cached tiles are kept; the offline lock is not
applied on a stopped run.

A run is complete when the summary shows `failed: 0`. Incomplete runs skip
the lock (`skipped: incomplete_downloads`) — rerun while online to finish.

**What the lock does** (`lock_offline_mode`):

```text
allow_tile_fetch = 0
online_geocoder_enabled = 0
```

From that moment the live site uses only local bench / same-origin assets.

---

## Act V — Verification (the station is ready)

Walk this checklist after every install or sync.

```bash
cd ~/frappe-bench

# 1. build stamp
grep -n SIRAJ_BUILD apps/siraj_research/siraj_research/record_icons.py

# 2. package on disk
python3 -c "import json; p=json.load(open('apps/siraj_research/siraj_research/public/data/geo-package.json')); print(p['dataset'], p['etag'], len(p['rows']))"

# 3. stop control present
grep -n stop_bootstrap apps/siraj_research/siraj_research/doctype/geo_settings/geo_settings.json

# 4. cascade helper wired
grep -n siraj-cascade apps/siraj_research/siraj_research/public/js/siraj.bundle.js
```

Browser smoke test:

1. Hard reload once.
2. Console: `offline geo index ready: ...` — no `geo_package.current` error.
3. Open any form with a **Location** section (Person, Place, Institution, …).
4. Select **Country** → move to the next field → options are that country’s
   Governorates only.
5. Select a **Village** → District / Governorate / Country backfill upward.
6. Map → **Offline basemap** renders; DevTools Network shows no requests to
   `tile.openstreetmap.org`, `server.arcgisonline.com`, or geocoders.
7. Geo Settings shows **Stop Offline Bootstrap**.

---

## Act IV-b — Adding another region (Lebanon, Iraq, Egypt, …)

While still online, download a Geofabrik extract for the country, then run one
command:

```bash
# examples — put PBFs under ~/frappe-bench/geodata/osm/
bench --site frappe.com execute siraj_research.geo_bulk.setup_region \
  --kwargs '{
    "dataset_code": "OSM-LB",
    "source_path": "/home/frappe/frappe-bench/geodata/osm/lbn-latest.osm.pbf",
    "label_en": "Lebanon (OSM)",
    "activate": True,
    "export_package": True
  }'
```

> `--kwargs` is Python `eval`, not JSON — use `True` / `False`, not `true` / `false`.
> Absolute paths only (`~` is not expanded inside `--kwargs`).

Repeat for `OSM-IQ` (Iraq), `OSM-EG` (Egypt), or any other Geofabrik region.
`setup_region` will:

1. create the **Boundary Dataset** row if missing;
2. run `osmium` to extract administrative polygons (needs `osmium-tool`);
3. import polygons and materialise Country → Community rows;
4. optionally activate the dataset and re-export the offline geo package.

A failed import with `0` features almost always means the PBF was missing —
delete the dataset row, fix the path, and rerun. Never leave `Failed / 0`
rows behind.

After every new region, re-run **Act V** verification with the new active
dataset etag.

### CLI rules for `siraj_research` (avoid these failures)

| Wrong | Right |
| --- | --- |
| `--kwargs '{... "true"}'` | Python: `"True"` (`--kwargs` is `eval`, not JSON) |
| `frappe.client.set_value` without `name` on Geo Settings | Include `"name":"Geo Settings"` (Singles need it) |
| `prepare_osm --kwargs '{"dataset": ...}'` | `input_path`, `output_dir`, `run` — or use `setup_region` |
| `bench update --reset` to refresh this app | Only `git -C apps/siraj_research …` + `migrate` + `build --app siraj_research` |
| Running `setup_region` before it exists on the bench | Merge the open PR that adds it, then siraj-only update (Act III) |

`setup_region` ships with the release PR; until it is merged on `main`, the
bench only has the older import helpers (`prepare_osm` + `import_osm` +
`sync_boundary_hierarchy`).

## Epilogue — The ongoing ritual

After each PR merges to `main`, update **only** `siraj_research`.
Never run `bench update --reset` as part of this ritual — it upgrades
Frappe and every other app and is out of scope.

```bash
git -C ~/frappe-bench/apps/siraj_research fetch origin main
git -C ~/frappe-bench/apps/siraj_research reset --hard origin/main

cd ~/frappe-bench
bench --site frappe.com migrate
bench build --app siraj_research
bench --site frappe.com clear-cache
bench --site frappe.com execute siraj_research.api.geo_package.export_offline_package
bench restart
```

Then run **Act V** again. If DNS is down, use the offline installers instead
of git (`deploy_all_d18.py` and friends restore the tree without network).

### Upgrading to V2.0.0

```bash
# 1. Move the app to the release (after the release PR is on main)
git -C apps/siraj_research fetch origin main
git -C apps/siraj_research reset --hard origin/main   # or: git checkout V2.0.0

# 2. Schema + patches (only new patch = derived family-column backfill)
cd ~/frappe-bench
bench --site frappe.com migrate

# 3. Assets + caches
bench build --app siraj_research
bench --site frappe.com clear-cache
bench restart

# 4. Optional: demo data → onboarding walk → map search → cleanup
bench --site frappe.com execute siraj_research.demo_data.load
#    walk siraj_research/docs/onboarding/README.md, try the Explorer map search
bench --site frappe.com execute siraj_research.demo_data.remove
```

Full verification (migration safety, fresh-install integration,
permissions): `docs/qa/v2.0.0-runbooks.md`. Release notes:
`RELEASE_NOTES_V2.0.0.md`.

### Release tags

| Tag | Meaning |
| --- | --- |
| `V2.0.0` | Family · map search · onboarding · demo data · quality scoring (2026-11-18) |
| `v1.0.0` | First hierarchy foundation |
| `v1.1.0` | Cascading + bootstrap stop control |
| `v1.x.0` | Features |
| `v1.0.x` | Fixes only |

### Development loop (every new change)

1. Branch from latest `main`.
2. One feature per PR, tests included.
3. Green required checks: **Pure-Python**, **Node Unit Tests**, **Static
   Validation**, **Ruff (changed files)**.
4. Merge to `main` only through the PR.
5. Tag if it ships.
6. Run the Epilogue ritual on the bench.
7. Smoke-test Act V.

---

*The station is online only while it prepares itself. When preparation ends,
the network door closes — and the hierarchy still cascades.*
