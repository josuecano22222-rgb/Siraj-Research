# 5. Offline operation

"Offline" here means **no external host is contacted**: no CDN, no
`tile.openstreetmap.org`, no Esri, no Nominatim, no GeoNames. The Frappe server,
its database and the LAN remain, because that is where the records live.

Three independent layers must each be local, and each is verified separately:

| Layer | Source of truth | Verified by |
|---|---|---|
| **Data** — hierarchy, boundaries, gazetteer | PostgreSQL/MariaDB on the bench | `geo_resolve` with `socket` blocked |
| **Tiles** — raster basemap | `private/siraj_tile_cache` and/or `private/siraj_maps/*.mbtiles` | cache file count + `tile_report` |
| **Assets** — Leaflet, MapLibre, fonts, icons, viewer | `public/vendor/**`, bundled by `bench build` | required-file + CDN-marker scan |

## 5.1 Local static assets (zero CDN)

`bench build --app siraj_research` copies `siraj_research/public/**` to
`sites/assets/siraj_research/**`. Everything the map UI needs is inside:

| Asset | Path | Size |
|---|---|---|
| Leaflet 1.9 | `public/vendor/leaflet/{leaflet.js,leaflet.css,images/}` | ~192 KB |
| MapLibre GL | `public/vendor/maplibre-gl/` | ~1.8 MB |
| D3 | `public/vendor/d3/d3.min.js` | ~408 KB |
| JSZip | `public/vendor/jszip/` | ~132 KB |
| TopoJSON | `public/vendor/topojson/` | ~12 KB |
| vis-network | `public/vendor/vis-network/` | ~692 KB |
| Natural Earth world atlas | `public/vendor/world-atlas/` | ~112 KB |
| Marker cluster | `public/vendor/leaflet-markercluster/` | ~40 KB |
| Offline viewer | `public/offline_map/{index.html,viewer.js,records.js,snapshot_verify.js}` | small |

Total ≈ **3.4 MB**, served from `/assets/siraj_research/…`. No `@import
url(https://…)`, no `<script src="https://…">`, no Google Fonts.

Prove it on any machine (no bench needed):

```bash
cd apps/siraj_research
grep -RInE "//(unpkg|cdn\\.jsdelivr|cdnjs|fonts\\.googleapis|fonts\\.gstatic)\\.com|tile\\.openstreetmap\\.org|arcgisonline\\.com|cartocdn\\.com" \
  siraj_research/public --include='*.js' --include='*.css' --include='*.html' \
  | grep -v '/vendor/'
```

Expected: no output. Vendor bundles may contain provider URLs in comments or
attribution strings; those are inert text, not requests. `offline_verify`
performs the same scan with the same exclusion and reports any hit as a failure.

The only "online" URLs left in the app are in `tile_cache.LAYERS` and
`geo_online.PROVIDERS`; both are gated by settings that are disabled by the
offline lock (§5.6) and neither is used at page load.

## 5.2 Tile serving

Two same-origin endpoints, both login + `Place:read`:

```
/api/method/siraj_research.tile_cache.tile?layer=standard&z=11&x=1218&y=790
/api/method/siraj_research.local_maps.tile?pack=standard&z=11&x=1218&y=790
```

**Disk cache** (`tile_cache.py`):

* root `sites/<site>/private/siraj_tile_cache/<layer>/<variant>/<z>/<x>/<y>.<ext>`,
* per-tile cap **2 MiB**, HTTP timeout **4 s**, upstream `User-Agent`
  `SIRAJ-Research/1.0`,
* serves a cached tile regardless of upstream availability; a stale tile is
  served while revalidation fails,
* `allow_tile_fetch = 0` → a miss returns **HTTP 503 with an empty PNG**, and
  the Leaflet layer silently keeps the previous/transparent tile. It never
  blocks the form and never calls out,
* `cache_days` (default 90) controls freshness; a prewarmed pack therefore
  survives three months of offline use untouched.

**MBTiles packs** (`local_maps.py`, `utils/offline_tiles.py`):

* only two fixed names: `sites/<site>/private/siraj_maps/standard.mbtiles` and
  `aerial.mbtiles`; arbitrary paths/URLs are rejected,
* symlinked packs or a symlinked directory are refused (real-path check),
* raster PNG/JPEG/WebP only, TMS rows, real `tiles` table, non-partial unique
  index; vector tiles and `tiles` views are refused,
* served with `private, no-store`; missing coverage reports an error instead of
  falling back online.

**Vector fallback** (`siraj-basemap.js` + `world-atlas`): the **Offline** layer
draws Natural Earth countries from the bundled TopoJSON at any zoom and issues
zero tile requests. It is the default for air-gapped installs.

## 5.3 Prewarming tiles, and what it costs

Run once while the bench still has network:

```bash
bench --site research.local execute siraj_research.offline_bootstrap.prewarm_tiles \
  --kwargs '{"dataset":"GADM-IQ","max_zoom":11}'
```

It:

1. reads the dataset bbox from `Admin Boundary` (no bbox → refuses),
2. enables the shared basemap layers it intends to cache,
3. walks every tile for each enabled layer, writing misses and counting
   `written`, `cached`, `failed`, `skipped_layers`,
4. honours the cooperative stop flag (checked every 32 tiles) and keeps what it
   wrote,
5. reports failure if any tile genuinely failed; only then is the offline lock
   skipped.

Tile count depends on the bbox, not on your data density. `n(z) =
(⌊xmax⌋−⌊xmin⌋+1) × (⌊ymax⌋−⌊ymin⌋+1)`; at ~15 KB per PNG tile the footprint is:

| Area | z10 | z11 | z12 | z13 | z15 |
|---|---|---|---|---|---|
| Lebanon | 42 tiles · 0.6 MB | 120 · 1.8 MB | 432 · 6 MB | 1 656 · 24 MB | 25 521 · 374 MB |
| Jordan | 195 · 3 MB | 754 · 11 MB | 2 907 · 43 MB | 11 300 · 166 MB | 177 408 · 2.5 GB |
| Iraq | 841 · 12 MB | 3 306 · 48 MB | 12 995 · 190 MB | 51 300 · 751 MB | 815 384 · 11.7 GB |

Values are **per layer**; `standard`, `aerial` and `hybrid` each multiply the
number. Practical defaults: `max_zoom=11` for country-scale work, `12`–`13` for
a governorate, `15` only for a city and only with a licensed local pack. The
`max_zoom=19` maximum would be terabytes — the command does not guard against
that, the operator must choose.

`Geo Settings → Offline Bootstrap` exposes **Run Online Setup** and **Stop
Offline Bootstrap**; progress is printed and appended to
`sites/<site>/private/offline-cache/bootstrap-progress.json`.

## 5.4 Local boundary storage and footprint

| Storage | Contents | Size rule of thumb |
|---|---|---|
| `Admin Boundary` | one row per feature: code, names, level, parent, bbox, `geom_wkb_hex` | WKB ≈ 16 bytes per coordinate pair + 40; a GADM admin-1 polygon is typically 50–500 KB |
| `Admin Boundary Geom` | `geom_wkb_hex` + optional PostGIS `geom` | same bytes again in PostGIS, plus ~20–30 % for the GiST index |
| Level DocTypes | one row per unit (code, names, ancestry) | ~1–2 KB/row; 6 000 units < 15 MB |
| `Gazetteer Place` | GeoNames cities (names, coords, population) | ~0.5 KB/row; `cities500` ≈ 200 k rows ≈ 100 MB |
| `public/data/geo-package.json` | simplified polygons for the browser worker | 5–20 % of the WKB (coordinates rounded to 4–5 dp) |
| tile cache / packs | raster imagery | see §5.3 |

Check the real numbers instead of estimating:

```bash
bench --site research.local geo postgis-health        # table_bytes, rows with geometry
bench --site research.local geo verify-offline        # storage: boundaries {rows, wkb_mb}, gazetteer, level counts
```

A 100 k-feature OSM boundary import is the point where PostgreSQL becomes the
sensible backend: the GiST index answers `ST_Contains` in single-digit
milliseconds, whereas the Shapely fallback must build a 100 k-entry `STRtree`
once per worker (a few hundred MB RAM, ~10–20 s cold start).

Backups: `bench --site <site> backup --with-files` covers the database and
`private/` (tile cache, packs, wheels). Exclude the tile cache from nightly
backups if it is reproducible from the source packs; keep the MBTiles packs in
your normal file backup because they cannot be regenerated.

## 5.5 Browser package (polygons for the offline worker)

```bash
bench --site research.local execute siraj_research.api.geo_package.export_offline_package
bench build --app siraj_research
```

Writes `siraj_research/public/data/geo-package.json` (served at
`/assets/siraj_research/data/geo-package.json`) with:

* `polygons`: `[level, pcode, parent_pcode, name_en, name_ar, area, linked_name,
  country, coordinates…]`, coordinates rounded,
* `places`: gazetteer subset for nearest-place hints,
* dataset metadata (`code`, `version`, `generated_at`, licence).

The offline Web Worker (`siraj-geo-worker.js`) loads it on first use and answers
point → chain locally, so a Desk form whose API call fails still fills its
links. The package is generated output: do not commit it; add it to `.gitignore`
if your deployment builds it in CI.

## 5.6 The offline lock

`geo_settings` and `offline_bootstrap.lock_offline_mode()` provide a single
switch that disables every external call:

```bash
bench --site research.local execute siraj_research.offline_bootstrap.lock_offline_mode
# {"allow_tile_fetch": 0, "online_geocoder_enabled": 0}
```

`prepare_offline_site` runs the whole sequence (wheels → tiles → hierarchy →
package → lock) in one command:

```bash
bench --site research.local execute siraj_research.offline_bootstrap.prepare_offline_site \
  --kwargs '{"dataset":"GADM-IQ","max_zoom":11}'
```

* If wheels or tiles were incomplete, the lock is **skipped** unless
  `force_lock=True` — you are told, not silently cut off.
* `Geo Settings → Allow online setup downloads` unchecked → wheels/tiles are
  skipped, hierarchy and package are rebuilt from local data, and no external
  host is contacted at all. That is the correct mode for an air-gapped bench
  refreshed from a USB stick.
* Re-enable temporarily for an update: set `allow_tile_fetch=1` and
  `online_geocoder_enabled=1`, prewarm, then lock again.

## 5.7 End-to-end verification with networking disabled

Two levels of proof, both shipped:

### A. Server-side, in-process (works even on a machine that still has network)

```bash
bench --site research.local geo verify-offline --lat 33.3152 --lon 44.3661
```

`siraj_research.offline_verify.run()` monkey-patches
`socket.create_connection`, `socket.socket.connect` and
`http.client.HTTPConnection.connect` to raise for every non-loopback address,
then resolves the point, scans assets and tiles, and returns a report. Nothing
leaks: if any code path tried to reach a provider, the call would raise instead
of succeeding.

Report shape:

```json
{
  "passed": true,
  "point": {"lat": 33.3152, "lon": 44.3661},
  "checks": [
    {"check": "spatial_backend", "ok": true, "detail": {"backend": "postgis"}},
    {"check": "dataset_configured", "ok": true,
     "detail": {"dataset": "GADM-IQ", "gazetteer": "GEONAMES-CITIES",
                "online_enabled": false, "allow_tile_fetch": false,
                "spatial_backend": "postgis"}},
    {"check": "online_fallback_disabled", "ok": true, "detail": {"online_geocoder_enabled": false}},
    {"check": "local_assets", "ok": true, "detail": {"missing": [], "cdn_hits": 0}},
    {"check": "local_tiles", "ok": true, "detail": {"ok": true, "cache": {"files": 1240, "mb": 38.2}, "packs": []}},
    {"check": "blocked_network_resolution", "ok": true, "detail": {"error": null}},
    {"check": "chain_non_empty", "ok": true, "detail": {"country": "Iraq", "governorate": "Baghdad"}},
    {"check": "no_online_provenance", "ok": true, "detail": ["postgis"]}
  ],
  "resolution": {"text_en": "Iraq › Baghdad", "text_ar": "العراق › بغداد",
                 "deepest_level": 1, "warnings": [], "provenance": ["postgis"],
                 "levels": [{"field": "country", "label_en": "Iraq", "status": "linked"}]},
  "assets": {"ok": true, "files": 8, "bytes": 3565158, "missing": [], "cdn_reference_count": 0, "external": []},
  "tiles": {"ok": true, "cache": {"files": 1240, "mb": 38.2}, "packs": []},
  "storage": {"boundaries": {"rows": 340, "wkb_mb": 84.2}, "gazetteer": 198400,
              "Governorate": 4011, "District": 1411, "Municipality": 8,
              "Village": 69, "Community": 3},
  "settings": {"dataset": "GADM-IQ", "gazetteer": "GEONAMES-CITIES",
               "online_enabled": false, "allow_tile_fetch": false,
               "spatial_backend": "postgis"}
}
```

`passed:false` with a specific failed check is the expected outcome before a
dataset/tiles exist; the detail says which stage is missing.

Optional exact-level assertion:

```bash
bench --site research.local geo verify-offline --lat 33.3152 --lon 44.3661 \
  --expect country,governorate
```

### B. Client-side, with the network actually off

1. Lock the site (§5.6) and restart.
2. Disable Wi-Fi/ethernet on the client, or in DevTools set **Network →
   Offline** and keep the tab open. (The server is on `localhost`/LAN; if you
   cut all networking, use the browser's offline mode rather than unplugging
   the server.)
3. Open a Place form, click the map: the pin resolves, the six Link fields fill,
   labels come from `Country Level Config`, and the basemap renders from the
   local tile cache or the Natural Earth vector layer.
4. Open `/assets/siraj_research/offline_map/index.html` — it loads Leaflet,
   CSS, icons and its viewer script from the same origin only.
5. In DevTools → Network, filter by "Third-party" or search for `http` requests
   to hosts other than yours: expected **zero**.

If step 5 shows requests, the usual causes are: an old cached bundle (run
`bench build`), a custom Print Format/Web Form that pasted a CDN link, or a
browser extension. `offline_verify` finds the first two server-side.

## 5.8 Licensing and attribution (non-negotiable offline)

| Layer | Licence | Obligation |
|---|---|---|
| OpenStreetMap raster tiles | ODbL 1.0 + tile usage policy | attribution "© OpenStreetMap contributors"; bulk pre-caching must respect the provider's policy — prefer your own tile server or an MBTiles pack for large areas |
| Esri World Imagery | Esri terms | only with a licence that permits offline storage; attribution as supplied |
| Natural Earth | public domain | none legally; attribution good practice |
| GADM | non-commercial | check before redistribution; attribute |
| GeoNames | CC BY 4.0 | attribute |
| OSM boundary extracts | ODbL 1.0 | attribute + share-alike for derived databases |
| OCHA COD | usually CC BY 3.0 IGO | attribute per dataset |

The viewer shows the attribution string of whichever layer is active, from
`tile_cache.LAYERS[...]["attribution"]` or the pack's metadata. Offline does not
remove the obligation — the string is stored locally, which is exactly why it is
baked into the layer spec rather than fetched.

## 5.9 Known limits of the offline stack

* Raster tiles are **snapshots**. There is no delta sync, no expiry beyond
  `cache_days`, no remote wipe, and no per-user tile authorisation beyond
  `Place:read`.
* The browser package contains simplified polygons; sub-metre boundary disputes
  must be resolved against the full geometry in PostGIS, not in the worker.
* MBTiles export caps: 25 000 tiles / 200 MiB per ZIP, 512 tiles / 16 MiB from
  the Explorer UI. These are UI limits, not security quotas.
* Offline packages are unencrypted. Store them only on authorised devices; a
  permission change on the server cannot revoke an already-downloaded ZIP.
