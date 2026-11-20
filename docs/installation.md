# The Installation Odyssey

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
| **Apps** | `business_theme` (presentation) and `siraj_research` (research core, hierarchy, maps) |
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

# business_theme (if it lives in the same organisation)
git clone <BUSINESS_THEME_URL> business_theme
git -C business_theme checkout main
git -C business_theme pull --ff-only origin main
```

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
bench get-app ./apps/business_theme
bench --site frappe.com install-app siraj_research
bench --site frappe.com install-app business_theme
```

---

## Act III — First breath (schema, assets, cache)

Every time code changes on `main`, this is the ritual. Run it in order —
never out of sequence.

```bash
cd ~/frappe-bench

# 1. pull latest main into both apps
git -C apps/business_theme fetch origin main
git -C apps/business_theme reset --hard origin/main
git -C apps/siraj_research fetch origin main
git -C apps/siraj_research reset --hard origin/main

# 2. sync frappe + requirements
bench update --reset

# 3. database migrations (DocTypes, patches)
bench --site frappe.com migrate

# 4. rebuild JS/CSS bundles
bench build --app siraj_research
bench build --app business_theme

# 5. clear caches
bench --site frappe.com clear-cache
bench --site frappe.com clear-website-cache

# 6. restart workers
bench restart
```

**Verify Act III:**

```bash
grep -n SIRAJ_BUILD apps/siraj_research/siraj_research/record_icons.py
# expect: SIRAJ_BUILD = "2026-11-20.hierarchy-ui.d.18" (or newer)
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

```bash
bench --site frappe.com execute \
  frappe.client.set_value \
  --kwargs '{
    "doctype": "Geo Settings",
    "fieldname": "active_boundary_dataset",
    "value": "OSM-IL-PS"
  }'
```

### 9. Import boundaries (per region)

Download a Geofabrik extract while online, then:

```bash
# place the PBF where the app expects it, e.g.
# ~/frappe-bench/geodata/osm/ile-rus.pbf

bench --site frappe.com execute \
  siraj_research.geo_bulk.prepare_osm \
  --kwargs '{"dataset": "OSM-IL-PS"}'

bench --site frappe.com execute \
  siraj_research.geo_bulk.sync_boundary_hierarchy \
  --kwargs '{"dataset_code": "OSM-IL-PS", "create_missing": true}'
```

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

## Epilogue — The ongoing ritual

After each PR merges to `main`:

```bash
git -C ~/frappe-bench/apps/business_theme fetch origin main
git -C ~/frappe-bench/apps/business_theme reset --hard origin/main

git -C ~/frappe-bench/apps/siraj_research fetch origin main
git -C ~/frappe-bench/apps/siraj_research reset --hard origin/main

cd ~/frappe-bench
bench update --reset
bench --site frappe.com migrate
bench build --app siraj_research
bench --site frappe.com clear-cache
bench --site frappe.com execute siraj_research.api.geo_package.export_offline_package
bench restart
```

Then run **Act V** again. If DNS is down, use the offline installers instead
of git (`deploy_all_d18.py` and friends restore the tree without network).

### Release tags

| Tag | Meaning |
| --- | --- |
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
