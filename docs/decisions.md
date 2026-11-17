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

## D-07  Geo-resolve (auto-fill on click)

Single whitelisted server method `siraj_research.api.geo_resolve.resolve_point(lat, lon)`
returns `{country, governorate, district, municipality, village, community, place_name, place_distance_m, place_bearing_deg, elevation_m, confidence, sources:[...]}`,
served from an in-memory STRtree built on startup (boundary GeoJSON
bundled with the app, augmented by any `Offline Map Package` flagged as
boundaries). Reverse geocode is offline-only by default. A small
client-side shim debounces clicks, fills fields, and shows the
provenance chip + diff dialog on conflict with user-entered values.
