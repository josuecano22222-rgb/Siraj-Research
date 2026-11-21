# From scratch — full runbook (fresh reinstall)

This is the **complete chronological procedure** for a wiped bench, written
against what actually runs on `siraj_research`. Only this app is touched:
never `bench update --reset`, never other apps unless you choose to.

**Rule:** `bench --site … execute --kwargs` is Python `eval`, not JSON.
Booleans are `True` / `False`. Paths must be absolute (`~` is not expanded).

---

## Phase 0 — Starting point (already done on this bench)

```text
✓ bench reinstall (frappe, erpnext, hrms, siraj_research, business_theme)
✓ SIRAJ reference data seeded (249 countries, 4011 governorates, …)
✓ PR branch checked out: arena/2348f69a-siraj-research
✓ migrate + build (siraj.bundle.LXDV5NLR.js) + clear-cache + restart
✓ setup_region imported OSM-IL-PS (1130 boundaries after worker finished)
✓ package exported: OSM-IL-PS:1.2 (1130 polygons)
✓ wheels cached (6), standard + aerial tiles cached
```

Verify code is on the feature branch:

```bash
grep -n "def setup_region" ~/frappe-bench/apps/siraj_research/siraj_research/geo_bulk.py
grep -n SIRAJ_BUILD ~/frappe-bench/apps/siraj_research/siraj_research/record_icons.py
# expect: line 679-ish setup_region, SIRAJ_BUILD = "...hierarchy-ui.d.19"
```

`main` stays unmerged until local testing passes.

---

## Phase 1 — App install / update (siraj_research only)

### 1.1 First install (fresh clone)

```bash
cd ~/frappe-bench/apps
git clone https://github.com/josuecano22222-rgb/Siraj-Research.git siraj_research
cd ~/frappe-bench
bench get-app ./apps/siraj_research
bench --site frappe.com install-app siraj_research
```

### 1.2 Update to a feature branch (test before merge)

```bash
git -C ~/frappe-bench/apps/siraj_research fetch origin arena/2348f69a-siraj-research
git -C ~/frappe-bench/apps/siraj_research checkout -B arena/2348f69a-siraj-research \
  origin/arena/2348f69a-siraj-research

cd ~/frappe-bench
bench --site frappe.com migrate
bench build --app siraj_research
bench --site frappe.com clear-cache
bench restart
```

### 1.3 Update to `main` (after you merge)

```bash
git -C ~/frappe-bench/apps/siraj_research fetch origin main
git -C ~/frappe-bench/apps/siraj_research reset --hard origin/main

cd ~/frappe-bench
bench --site frappe.com migrate
bench build --app siraj_research
bench --site frappe.com clear-cache
bench restart
```

**Expected after every update**

```bash
grep -n SIRAJ_BUILD apps/siraj_research/siraj_research/record_icons.py
# SIRAJ_BUILD = "2026-11-20.hierarchy-ui.d.19" (or newer)
```

Browser: hard reload once → console `offline geo index ready: …`.

---

## Phase 2 — Geography data (online)

### 2.1 List datasets

```bash
bench --site frappe.com execute frappe.client.get_list \
  --kwargs '{"doctype":"Boundary Dataset","fields":["name","import_status","feature_count"]}'
```

Fresh reinstall typically shows only `SIRAJ-REFERENCE` until you import OSM.

### 2.2 Add a region (Israel/Palestine example)

PBF must already exist under `~/frappe-bench/geodata/osm/`.

```bash
bench --site frappe.com execute siraj_research.geo_bulk.setup_region \
  --kwargs '{
    "dataset_code":"OSM-IL-PS",
    "source_path":"/home/frappe/frappe-bench/geodata/osm/israel-and-palestine-latest.osm.pbf",
    "label_en":"Israel + Palestine (OSM)",
    "activate":True,
    "export_package":True
  }'
```

What it does:

1. Creates Boundary Dataset if missing
2. Runs `osmium` → `…-boundaries.geojson`
3. **Queues** polygon import on the long worker (`queued: true`)
4. Activates the dataset
5. If **not** queued, exports the package; if queued, returns
   `package.skipped = import_queued` (exporting now would be empty)

**Wait for the worker**, then confirm:

```bash
bench --site frappe.com execute frappe.client.get_list \
  --kwargs '{"doctype":"Boundary Dataset","filters":{"name":"OSM-IL-PS"},"fields":["name","import_status","feature_count"]}'
# want: import_status = Complete, feature_count > 0
```

### 2.3 Export the offline package (after Complete)

```bash
bench --site frappe.com execute siraj_research.api.geo_package.export_offline_package
```

Expected shape:

```json
{"written": true, "dataset": "OSM-IL-PS", "polygons": 1130, "etag": "OSM-IL-PS:1.2"}
```

(Version/polygon count grow with re-exports.)

### 2.4 Other regions (Lebanon, Iraq, Egypt, …)

Same pattern; put the Geofabrik PBF on disk first:

```bash
bench --site frappe.com execute siraj_research.geo_bulk.setup_region \
  --kwargs '{
    "dataset_code":"OSM-LB",
    "source_path":"/home/frappe/frappe-bench/geodata/osm/lbn-latest.osm.pbf",
    "label_en":"Lebanon (OSM)",
    "activate":True,
    "export_package":True
  }'
```

Never leave `Failed / 0` rows:

```bash
bench --site frappe.com execute frappe.delete_doc \
  --args '["Boundary Dataset", "OSM-LB"]'
```

---

## Phase 3 — Online setup → offline lock

### 3.1 Run the full bootstrap

```bash
bench --site frappe.com execute siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset":"OSM-IL-PS","max_zoom":11}'
```

Or from Desk: **Geo Settings → Online Setup → Run Online Setup**.

Progress streams immediately:

```bash
tail -f ~/frappe-bench/logs/web.log | grep -i "SIRAJ offline"
```

Stages:

| Stage | Needs network? | Notes |
| --- | --- | --- |
| wheels | yes | pip download → private offline-cache |
| tiles | yes | standard + aerial + hybrid + hybrid_labels; **enables shared basemaps first** so hybrid is not “Layer disabled” after reinstall |
| hierarchy | no | materialises Country → Community from boundaries |
| package | no | writes `geo-package.json` |
| lock | no | only if `failed: 0` |

Stop mid-run: **Geo Settings → Stop Offline Bootstrap** (keeps cached tiles; does not lock).

**Geo Settings toggle:** *Allow online setup downloads*
- **On** (default): wheels + tiles may hit the network
- **Off**: local-only prep (hierarchy + package), no external hosts

### 3.2 Incomplete tiles

If the summary shows `failed > 0` or `locked.skipped = incomplete_downloads`:

```bash
# run again while online — already-cached tiles are skipped
bench --site frappe.com execute siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset":"OSM-IL-PS","max_zoom":11}'
```

A finished setup has `failed: 0` and applies the lock:

```text
allow_tile_fetch = 0
online_geocoder_enabled = 0
```

### 3.3 Force lock (only if you accept partial tile cache)

```bash
bench --site frappe.com execute siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset":"OSM-IL-PS","max_zoom":11,"force_lock":True}'
```

---

## Phase 4 — Verification checklist

```bash
cd ~/frappe-bench

# code
grep -n SIRAJ_BUILD apps/siraj_research/siraj_research/record_icons.py

# package on disk
python3 -c "import json;p=json.load(open('apps/siraj_research/siraj_research/public/data/geo-package.json'));print(p['dataset'],p.get('etag'),len(p.get('rows') or p.get('polygons') or []))"

# settings controls
grep -n "online_setup_enabled\|stop_bootstrap\|run_online_setup" \
  apps/siraj_research/siraj_research/doctype/geo_settings/geo_settings.json

# cascade wired
grep -n siraj-cascade apps/siraj_research/public/js/siraj.bundle.js
```

Browser:

1. Hard reload once.
2. Console: `offline geo index ready: OSM-IL-PS:…` — no `geo_package.current` error.
3. Any form with **Location**:
   - empty Country → Governorate list shows **all** countries’ governorates
   - pick Country → next field **narrows** to that country
   - pick Village/Community → higher fields **backfill** (Keep/Replace if conflict)
4. Map → offline basemap; Network tab: no OSM/Esri/Nominatim hosts.
5. Geo Settings: **Run Online Setup**, **Stop Offline Bootstrap**, toggle present.

---

## Phase 5 — Merge (only after Phase 4 passes)

In Arena/GitHub, say **merge PR 5** (or merge in the UI), then Phase 1.3
(update to `main`). Tag `v1.2.0` is created at merge time.

---

## Quick reference — commands that must look like this

| Action | Command sketch |
| --- | --- |
| Activate dataset (Single) | `frappe.client.set_value` with `"name":"Geo Settings"` |
| Booleans in kwargs | `True` / `False` |
| Export package | `siraj_research.api.geo_package.export_offline_package` |
| Full online setup | `siraj_research.offline_bootstrap.prepare_offline_site` |
| New region | `siraj_research.geo_bulk.setup_region` |
| App update | git fetch/reset **siraj_research only** → migrate → build → clear-cache → restart |
| Never for app updates | `bench update --reset` |

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Could not find Active boundary dataset: X` | Dataset row deleted / not imported | Phase 2.2 `setup_region` or re-import |
| `package: polygons 0` right after setup_region | Import still queued | Wait for Complete → Phase 2.3 export |
| `PermissionError: Layer disabled` | Hybrid off after reinstall | Fixed in this branch: bootstrap enables shared basemaps; or run `tile_cache.enable_shared_basemaps` |
| `No active boundary dataset` on export | Geo Settings link empty | `set_value` with `name` (Phase 2) |
| `setup_region has no attribute` | Bench on `main` without PR | Phase 1.2 feature branch |
| `NameError: true` in kwargs | JSON boolean | Use `True` |
| tiles `failed > 0` | Network blips | Rerun Phase 3.1 online |
| `locked.skipped incomplete_downloads` | Failures or stop | Finish downloads, rerun |

---

*Everything above is `siraj_research` only. Other apps on the bench are out
of scope unless you deliberately update them yourself.*
