# Offline-first geography (no external internet)

SIRAJ Desk already runs from your own Frappe bench. "No internet" therefore
means **no external hosts** (OpenStreetMap, Esri, Nominatim, GeoNames). All
data must come from the bench or from a same-origin static asset.

## What works without any external network

- **Coordinates → Country / Governorate / State / deeper levels** from local
  polygons in the browser Web Worker.
- **Map display** using the built-in `Offline` (Natural Earth) vector basemap.
- **Saved records** with valid hierarchy Links, provided the linked documents
  were created once from local data.


## Full online-to-offline bootstrap (recommended)

Run this **once while online**. It downloads the optional Python wheels,
pre-caches tiles for the active dataset, creates hierarchy records, exports the
static geo package, and then permanently disables external calls:

```bash
cd ~/frappe-bench
bench --site frappe.com execute siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset":"OSM-IL-PS","max_zoom":11}'
```

If you prefer to do each step manually, use the commands below. Remember that
`bench --kwargs` is evaluated as Python: use `True`, not `true`.

## One-time bootstrap on the bench

1. Import your boundary and gazetteer files from local disk (GeoJSON/GPKG/OSM
   PBF). Example:

   ```bash
   bench --site frappe.com execute siraj_research.geo_bulk.import_osm \
     --kwargs '{"dataset_code":"OSM-IL-PS","file_path":"/home/frappe/frappe-bench/geodata/osm/israel-and-palestine-latest.osm-boundaries.geojson","level":5}'
   ```

2. Activate the dataset and enable hierarchy creation in `Geo Settings`
   (`active_boundary_dataset`, `auto_create_missing`). The first completed
   import now activates itself automatically when no dataset was selected.

3. Materialise the hierarchy records from those polygons so Link fields have
   real documents:

   ```bash
   bench --site frappe.com execute siraj_research.geo_hierarchy.sync_boundary_hierarchy \
     --kwargs '{"dataset":"OSM-IL-PS","create_missing":True}'
   ```

4. Export the browser package as a same-origin static file:

   ```bash
   bench --site frappe.com execute siraj_research.api.geo_package.export_offline_package
   bench --site frappe.com build --app siraj_research
   ```

   This writes `siraj_research/public/data/geo-package.json`, served at
   `/assets/siraj_research/data/geo-package.json`. The browser loads it when
   the API is unavailable, so no remote host is contacted.

5. Disable upstream tile fetching and choose the offline basemap:

   ```bash
   bench --site frappe.com execute frappe.client.set_value \
     --kwargs '{"doctype":"Geo Settings","name":"Geo Settings","fieldname":"allow_tile_fetch","value":0}'
   ```

   In the map toolbar, choose **Offline**. It draws Natural Earth country
   polygons from the bundled `world-atlas` asset and issues zero tile requests.

## What still needs local data

Satellite and hybrid basemaps are raster images. They can only be offline if
their tiles were pre-cached from a local XYZ tile archive. With
`allow_tile_fetch = 0`, uncached tiles return a transparent placeholder
instead of blocking the form.

Country/Governorate links can only be written offline when those hierarchy
documents already exist. Step 3 creates them from the local polygons. Levels
with no polygon remain visible as gaps and are never fabricated.
