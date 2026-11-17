# SIRAJ Mapping — Architecture Decisions

Status: DRAFT — being locked in incrementally. Each section records a
decision, alternatives considered and rationale. Decisions are additive: a
newer entry supersedes an older one only when noted.

---

## D-01  Rendering engine

**Decision:** Standardise on **Leaflet 1.9.x** as the only map engine for all
surfaces. Retain and finish the `window.SirajMap` adapter (`public/js/siraj-map/`)
as the sole public API — UI code never touches `L.*` directly. MapLibre GL
code in the repo is removed from the active bundle but kept in
`public/vendor/maplibre-gl/` for future experimental work; it is NOT shipped
in production in this release.

**Alternatives considered:**

| Option | Pros | Cons |
| --- | --- | --- |
| Leaflet (chosen) | Already integrated everywhere; works in Frappe's native MapView; tiny footprint; raster+vector (via PMTiles plugin) for offline; easy print snapshot; stable API. | No built-in 3D terrain; vector-tile styling is less powerful. |
| MapLibre GL | Smooth vector styling, 3D terrain, hybrid label compositing is native. | Large bundle; Frappe's native MapView still uses Leaflet so two engines would remain; WebGL issues in older Air-gapped browsers; print-to-PDF harder. |
| Hybrid (Leaflet 2D + MapLibre globe) | Best of both. | Two engines to maintain doubles test/bug surface — conflicts with owner's "ONE engine" requirement. |

**Rationale:** Owner's hard constraint is reliable offline + print +
integration with Frappe's native MapView + single-engine inheritance
architecture. Leaflet delivers all three today. Vector tiles (PMTiles via
`protomaps-leaflet`) give us the Standard / Hybrid layer quality we need,
and raster PMTiles/COG deliver aerial at the resolutions available to us
(10 m Sentinel-2 cloudless + licensed imagery). This is the fastest, most
testable path to Workstreams 1–5.

**Revisit:** MapLibre can be reintroduced behind the `SirajMap` adapter
without any UI-code changes in a future release; the adapter is the
seam.

---

## D-02  Tile / package format

**Decision:** **PMTiles v3** for both raster (aerial, terrain) and vector
(streets/topo, labels) offline packages, served via HTTP Range requests
from `/api/method/siraj_research.local_maps.tile?kind=…&z={z}&x={x}&y={y}`
(the existing route is extended to accept `?source=packages/<name>` for
uploaded packages). No MBtiles writes on the server's filesystem —
everything is a single immutable PMTiles file with a checksum record on
the `Offline Map Package` DocType.

**Why PMTiles:** single file (easier to upload/validate/distribute),
Range-request reads (no server-side tile database needed), works
offline in the browser via the Cache API/IndexedDB, supports both raster
and vector, actively maintained by Protomaps.

---

## D-03  Basemap sources, licences and resolution (Iraq + Afghanistan/Pakistan)

We do **not** bulk-cache Google, Bing or Esri World Imagery (forbidden by
their terms). Online aerial is an **explicit per-session opt-in** using
Esri World Imagery's public XYZ endpoint, which is permitted for
on-the-fly viewing but NOT for offline storage.

Shipped offline layers (admin-curated packages):

| Layer | Source | Licence | Iraq / Af-Pak resolution | Offline |
| --- | --- | --- | --- | --- |
| Standard (vector streets/topo) | OpenMapTiles schema, built via Planetiler from an OSM + Daylight extract | ODbL (© OpenStreetMap contributors) | z0–z14 built-in (street-level for cities); admin can build z0–z16 packages per region | yes (PMTiles) |
| Aerial (satellite) | Sentinel-2 L2A cloudless mosaic (EOX / Sentinel-2 Cloudless) + Copernicus DEM-derived hillshade | CC-BY (Sentinel-2) / CC-BY-4.0 (Copernicus) | ~10 m / px (no street-level detail; this is honest) | yes (raster PMTiles, z0–z13) |
| Hybrid | Aerial + transparent vector label/boundary overlay (composed client-side from the Standard style) | same as components | same | yes |
| Hillshade / contours | Copernicus GLO-30 DEM (30 m) + viewfinderpanoramas where allowed | CC-BY-4.0 / free for non-commercial | 30 m DEM → contours to z14 | yes |
| Admin boundaries | geoBoundaries v5 (CC-BY 4.0) + OCHA COD-AB for IQ + AFG | CC-BY 4.0 | ADM0–ADM4 (country → community/village) | yes (GeoJSON in bundle, spatial index) |
| Place names / gazetteer | GeoNames (CC-BY 4.0) + OSM overpass for transliteration variants | CC-BY 4.0 / ODbL | all populated places in IQ + AF-PK | yes (IndexedDB + server STRtree) |
| Online opt-in aerial | Esri World Imagery (labelled, on-the-fly only) | Esri ToS — view-only, no caching | sub-metre in cities, ~1 m rural | no (live, opt-in) |
| Online opt-in labels | OSM Carto/OSM-de raster | ODbL/CC-BY-SA | street-level | no (live, opt-in) |

Every basemap switcher entry shows its attribution, licence, whether it
uses the network, and (for offline) the package version.

---

## D-04  Offline level delivered

This release delivers **Level B — view + edit + create**, NOT Level C
(full sync of record edits back to a peer). Downloaded packages contain
basemap tiles only; record data is whatever the user has already fetched
or created locally. The form map works fully without the network
(markers, editor, reverse-geocode to admin units + nearest named place
from the bundled gazetteer). Attachments/large imagery are NOT cached
offline in this release (flagged as backlog).

---

## D-05  Client-side vs server-side conversion (import wizard)

- **Client (Web Worker):** CSV / TSV / XLSX (exceljs), GeoJSON / GeoJSONL /
  TopoJSON, KML (text-only, no KMZ), GPX, WKT. Used for files < 20 MB.
- **Server (background job, RQ):** KMZ, Shapefile (.zip), DXF, GeoPackage,
  CRS reprojection (pyproj), files > 20 MB, XLSX with > 50k rows, batch
  geocode against server-side gazetteer.

Conversion libraries are lazy-loaded; initial bundle size does not
change.

---

## D-06  Service worker vs Cache API / OPFS

We do NOT register a service worker in this release (Frappe's asset
paths under `/assets` and `/app` split across sites make SW scope
fragile). Offline packages are stored with the **Cache Storage API**
(keyed by package name + version + checksum) for tile fetches
intercepted via a fetch proxy in the tile-layer factory. Large packages
fall back to IndexedDB/OPFS with streaming range reads. This gives us
offline basemaps without touching SW scope, and works on all Desk
pages.

---

## D-08  Production caching & staleness detection

**Problem:** Frappe v15 serves `/assets/<app>/js/*.js` at fixed URLs with
long `Cache-Control: max-age` headers in most nginx/proxy setups. After
`bench build --app siraj_research` the files on disk are new but the
browser may keep using cached JS for hours/days, producing exactly the
"owner sees old UI after deploy" class of bug.

**Options:**
1. Switch to hashed bundles via Frappe's esbuild pipeline. **Rejected
   for this release**: this sandbox has no bench/esbuild and
   retrofitting would require vendoring esbuild or restructuring the
   app around `public/dist/bundle.*`; possible once we can test against
   a live bench.
2. Append a build-stamp query string to asset URLs (`?v=STAMP`). This
   works iff nginx includes `$args` in `proxy_cache_key`. **Adopted**
   in a future commit; requires an nginx-side change on the owner's
   bench (documented below).
3. **Independent server truth** (adopted now): the whitelisted endpoint
   `api/method/siraj_research.api.diagnostics.build_info` returns the
   server's build stamp and asset manifest from a non-cached URL
   (API responses carry `Cache-Control: no-store`). The SIRAJ
   Diagnostics Desk Page fetches it, re-fetches each JS file with
   `cache:'no-store'`, hashes the body with SHA-256, and compares — so
   staleness is PROVABLE from inside the owner's browser regardless of
   caching. A stale browser is not expected to run new code (which is
   why the in-bundle banner alone is unreliable); instead the
   diagnostics page is opened from a fresh URL or from the Desk
   sidebar and reports the truth.

**Required nginx snippet for the owner's bench** (place in the
`location /assets/` block to include query string in cache key):

```
location /assets/ {
    proxy_cache_key "$scheme$proxy_host$request_uri$args";
    expires 7d;
    add_header Cache-Control "public, max-age=604800, immutable";
    try_files $uri =404;
}
```

After this change, deploying with `?v=BUILD` appended to URLs in
`app_include_js` will bust all caches. Until then, after every deploy
the owner should open the Diagnostics page and verify the hash table
shows PASS — a hard refresh (Ctrl/Cmd+Shift+R) is sufficient to clear
the per-browser asset cache even without the nginx change.

**Shims removed:** earlier versions of siraj-compat monkey-patched
`L.Marker.prototype._initIcon` (private Leaflet API) and hid default
image markers with `display:none !important` in CSS. Both removed in
commit 8e4b532-followup. The default SIRAJ pin is now supplied through
the public options prototype via `Object.defineProperty(L.Marker.prototype.options, 'icon', …)`, and any stray image marker is rendered with a
dashed red outline so QA can see it instead of being masked.

---

## D-07  Geo-resolve (auto-fill on click)

Single whitelisted server method `siraj_research.api.geo_resolve.resolve_point(lat, lon)`
returns `{country, governorate, district, municipality, village, community, place_name, place_distance_m, place_bearing_deg, elevation_m, confidence, sources:[...]}`,
served from an in-memory STRtree built on startup (boundary GeoJSON
bundled with the app, augmented by any `Offline Map Package` flagged as
boundaries). Reverse geocode is offline-only by default. A small
client-side shim debounces clicks, fills fields, and shows the
provenance chip + diff dialog on conflict with user-entered values.
