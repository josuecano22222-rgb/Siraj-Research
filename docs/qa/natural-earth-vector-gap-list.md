# Natural Earth Vector — Gap List

**Status: NOT complete.** This is an honest per-spec-item status for the
Natural Earth Vector feature, derived from `docs/natural-earth-vector.md`.
The Python / API / DocType / serving / provisioning / security side is
**implemented and locally verified green**. The JS map capabilities now have a
**dedicated jsdom browser test** (`tests/test_nevector_browser.js`, commit
`e76bc45`) covering the Leaflet attach path, scale selection, choropleth,
click-to-country and the country-intelligence fetch helpers. The **Server job
is green on `main`** (PR #12 merged `1985202`→`00d8f8e`, PR #13 merged
`f86ae79`→`1687d7c`; both Server jobs passed, 3m21s–3m23s). Phase R steps 3–9
are therefore unblocked. The MapLibre attach path remains **not browser-
verified**.

**Verification basis (2026-11-28, branch `arena/4bf5fef5-siraj-research`,
commits `7565b23`+`042f105`+`23e28b6`+`045b1f1`+`f86ae79`+`e76bc45`, all merged
to `main` = `1687d7c`):**
- `bench migrate` — **no** `Orphaned DocType(s) found: Natural Earth Vector Pack`
  and **no** `Deleting orphaned DocTypes` (orphan-delete defect fixed).
- `test_natural_earth_vector` — `Ran 30 tests ... OK`.
- `test_api_data_group_isolation` — green (incl. `test_20` NE endpoints; the
  whitelisted-endpoint count assertion updated 48→51 in `f86ae79`).
- Pure-Python CI command — `387 passed, 6 skipped`.
- `tests/test_nevector_browser.js` (jsdom) — legend, country-intelligence
  fetch, engine dispatch, scale selection, choropleth, click-to-country,
  site-data choropleth all pass.
- Server JOB on `main` (PR #12 + PR #13) — **pass** (3m21s / 3m23s).

Legend: **DONE** = implemented + verified · **PARTIAL** = implemented, not fully verified · **NOT STARTED** = absent.

---

## 1. Dataset & catalog

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| Full Natural Earth Vector dataset (206 GeoJSON layers, 3 scales, public domain) | **DONE** | `nvkelso/natural-earth-vector` 5.2.0-pre, public domain. Catalog enumerates all 206 layers. |
| `natural_earth_catalog.py` — full 206-layer catalog + scale/zoom-tier logic | **DONE** | Present; `SCALES`, `all_layers()`, `catalog_summary()`. |
| LICENSE text at `siraj_research/public/natural_earth/LICENSE.md` | **DONE** | File present (4.6 KB). |

## 2. Bundled 110m tier

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| 1:110m tier bundled in the app, works offline out of the box | **DONE** | 32 GeoJSON files, ~20 MB at `siraj_research/public/natural_earth/110m/`; served as static app assets. |

## 3. Serving endpoints

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `layer?layer=<name>` serves raw GeoJSON as `application/geo+json`, ETag + 304, one-hour cache | **DONE** | `api/natural_earth_vector.py::layer` — `Content-Type: application/geo+json`, `ETag`/304 handling, `Cache-Control: public, max-age=3600`. |
| `manifest` returns combined manifest (bundle + pack, zoom tiers, available scales) | **DONE** | `manifest()` — combined bundle + pack manifest. |
| `catalog` exposes the catalog | **DONE** | `catalog()` whitelisted GET. |
| `index?scale=` exposes per-scale availability | **DONE** | `index(scale)` whitelisted GET; tested (index count 32 for 110m). |
| Provisioned 50m/10m tiers in site private storage (`private/natural_earth_vector/`) | **DONE** | `provision_pack` writes into site-private path; never fetched at render time. |

## 4. Provisioning (admin)

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `Natural Earth Vector Pack` admin DocType (controller + UI) | **DONE** | DocType JSON + controller (now with `NaturalEarthVectorPack(Document)` class so it survives orphan cleanup) + list JS. |
| `git_clone` source — blob-filtered sparse clone of canonical GitHub mirror (no API rate limits) | **DONE** | `_clone_mirror()` uses `git clone --sparse --no-checkout` + blob filter. |
| `local_mirror` source — copy from admin-supplied directory inside the site (air-gapped) | **DONE** | `source == "local_mirror"` branch; mirror-path confined to site (`_is_within`). |
| Validated `manifest.json` (per-layer sha256, byte counts, scales, provenance) | **DONE** | `empty_manifest`/`validate_manifest`; per-layer `sha256`, `stats.file_count`/`total_bytes`, provenance. |
| Rebuilds offline ZIP archive (`natural_earth_vector.zip`) | **DONE** | `build_zip()` — `zipfile.ZIP_DEFLATED`. |
| Provisioning endpoints require administrator permission | **DONE** | `_require_admin()` on `status`/`provision`; `refresh_status`/`run_provision` gate on `has_permission(..., "write")`; tested (Guest rejected). |

## 5. Advanced map capabilities (`SirajNeVector`)

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `SirajNeVector.attach(map, opts)` on MapLibre + Leaflet | **PARTIAL** | Implemented in `public/js/siraj-nevector.js` (`attachMapLibre`, `attachLeaflet`, `window.SirajNeVector.attach`). **Leaflet path browser-verified** by `tests/test_nevector_browser.js` (engine dispatch, layer build, scale). **MapLibre path not browser-verified.** |
| Scale-tiered basemap (110m/50m/10m + fallback to finest available) | **PARTIAL** | Logic present in `siraj-nevector.js` (`_selectScale`). **Leaflet scale selection browser-verified** (zoom 2 → 110m). MapLibre not browser-verified. |
| Choropleth `setChoropleth(field, valueByKey)` + legend | **PARTIAL** | `setChoropleth` in both engines. **Leaflet legend min/max + clearChoropleth browser-verified.** MapLibre not browser-verified. |
| Click-to-country `onCountryClick(cb)` (ISO codes, name, …) | **PARTIAL** | `onCountryClick` in both engines (MapLibre `queryRenderedFeatures`, Leaflet feature clicks). **Leaflet click-to-country browser-verified.** MapLibre not browser-verified. |
| Full layer set (ocean, land, lakes, boundaries, rivers, places, choropleth-safe countries) | **PARTIAL** | Layer construction present. **Leaflet layer-set build browser-verified.** MapLibre not browser-verified. |
| Data-driven site choropleth `setChoroplethFromSite` (Leaflet) | **PARTIAL** | Recolours countries from server aggregation. **Leaflet path browser-verified** (per-feature style fn from server payload). MapLibre not browser-verified. |

## 6. Basemap switcher integration

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `siraj-basemap.js` (Leaflet) exposes Natural Earth Vector as a mode | **PARTIAL** | `nevector` mode present (label/icon/tooltip, lazy `SirajNeVector` build). **Not browser-verified.** |
| `siraj-map.js` (MapLibre Explorer) exposes Natural Earth Vector as a mode | **PARTIAL** | `nevector` mode present with lazy `SirajNeVector.attach`, hide-on-switch. **Not browser-verified.** |

## 7. Offline viewer

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `offline_map/viewer.js` Raster / Natural Earth Vector toggle | **PARTIAL** | Toggle present; renders bundled 110m vector layers (`/assets/siraj_research/natural_earth/110m`), attribution "Natural Earth Vector (public domain)". **Not browser-verified.** |

## 8. Security & licensing

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| Public-domain data, unauthenticated serving (mirrors tile-cache pattern) | **DONE** | Static + whitelisted GET endpoints, no auth on reads. |
| Layer names validated against catalog before file access (path-traversal guard) | **DONE** | `layer()` validates against catalog before any file access. |
| Pack files written only inside the pack root | **DONE** | Path-confinement guard in `provision_pack`; tested. |
| Mirror directory must live inside the site | **DONE** | `_is_within(mirror_path, _site_root())`; tested (`TestLocalMirrorProvisioning`). |

## 9. Tests

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `test_natural_earth_vector` (pack/manifest/serve/security) | **DONE** | 30 tests, green locally. |
| NE endpoints registered & gated (in isolation suite) | **DONE** | `test_20_natural_earth_vector_endpoints_registered_and_gated`, green; whitelisted count assertion updated 48→51 (`f86ae79`). |
| Dedicated JS test for `SirajNeVector` / map capabilities | **PARTIAL** | `tests/test_nevector_browser.js` (jsdom, commit `e76bc45`) covers the **Leaflet** attach path, scale selection, choropleth, click-to-country, site-data choropleth and the country-intelligence fetch helpers. The **MapLibre** attach path (`attachMapLibre`) is **not** covered by a browser/jsdom test yet. |
| Static `search_fields` DocType-JSON gate (pure-Python) | **DONE** | `siraj_research/tests/test_doctype_json_static.py` (commit `23e28b6`) — catches the list-typed `search_fields` defect class in the pure-Python gate. |

## 10. CI / Server job

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `test_natural_earth_vector` wired into `server.yml` | **DONE** | Present in the module loop (commit `f1bd122`). |
| Server job green on `main` (post-orphan-fix + NE work) | **DONE** | PR #12 (`00d8f8e`) and PR #13 (`1687d7c`) both merged with **Server JOB = pass** (3m21s / 3m23s). The search_fields + orphan fixes, the server.yml exception-line echo, the static `search_fields` gate, the whitelist-registry/count fixes and the ruff UP038 fix are all on `main`. Phase R steps 3–9 are unblocked. |
| `server.yml` failure diagnostics (exception line) | **DONE** | On failure, echoes the first ERROR block's exception LINE (`grep -m1 -E '^[A-Za-z_.]+(Error|Exception):'`) alongside the `head -80` traceback head and full-log artifact (commit `23e28b6`). |

---

## Summary

- **DONE:** dataset/catalog, bundled 110m, all serving endpoints, all
  provisioning (both sources, manifest, ZIP, admin gating), security &
  licensing, Python tests, the static `search_fields` gate, the Server job
  green on `main`, and the `server.yml` exception-line diagnostics.
- **PARTIAL:** the JS map capabilities. The **Leaflet** path of
  `SirajNeVector` is now browser-verified by `tests/test_nevector_browser.js`.
  The **MapLibre** path, the basemap-switcher integration, and the
  offline-viewer toggle are implemented and wired in but **not browser-
  verified**.
- **NOT STARTED:** MapLibre-path browser test; basemap-switcher / offline-
  viewer browser tests.

**This feature is not complete.** The Python/API/DocType/serving/provisioning
layer is solid and locally green, and the Server job is green on `main`. The
map-rendering layer's Leaflet path is browser-tested; the MapLibre path and
the integration surfaces still need browser verification.

---

## Prioritized gap list (item 5 of the directive)

The Server job is green on `main`, so Phase R steps 3–9 resume. This is the
priority-ordered gap list; it is **not** a completion claim. Priority 1 is
done (the JS/browser test for the map layer, Leaflet path); the rest remain.

| Priority | Gap | Status | Notes |
|----------|-----|--------|-------|
| **1** | JS/browser test for the map layer (Leaflet `SirajNeVector` attach, scale, choropleth, click-to-country, site choropleth, country-intelligence fetch) | **DONE** | `tests/test_nevector_browser.js` (jsdom, commit `e76bc45`). Added to the local `test:js` runner. Negative-control verified. |
| **2** | JS/browser test for the **MapLibre** attach path (`attachMapLibre`: sources, fill/line/circle/symbol layers, `queryRenderedFeatures` click-to-country, choropleth paint) | **NOT STARTED** | `siraj-nevector.js` exposes `attach(map,{engine:'maplibre'})`. No browser test covers it. Needs a MapLibre-GL mock (or a real-GL jsdom shim) — the `attachMapLibre` path uses `map.addSource`/`addLayer`/`on('click', queryRenderedFeatures)`. |
| **3** | Browser test for basemap-switcher integration (`siraj-basemap.js` Leaflet `nevector` mode; `siraj-map.js` MapLibre Explorer `nevector` mode) | **NOT STARTED** | Both switcher files wire `SirajNeVector.attach` lazily. No browser test covers mode selection / lazy build / hide-on-switch. |
| **4** | Browser test for the offline-viewer NE Vector toggle (`offline_map/viewer.js`) | **NOT STARTED** | Toggle + bundled-110m rendering present; no browser test. |
| **5** | Extend `server.yml` failure diagnostics coverage (verify the exception-line echo fires on a real bench failure) | **PARTIAL** | Echo added (`23e28b6`); only observable when a Server test actually fails. Not yet observed firing on a real failure. |
| **6** | Bench-side re-verification of the hierarchical cascade + NE country-intelligence end-to-end on the user's bench | **PARTIAL** | Sandbox-pure-Python green; the frappe-dependent endpoints need a bench run to confirm the full cascade + choropleth on a real site. |
| **7** | Re-run the full pure-Python + Node + Server CI matrix on `main` post-merge to confirm all gates stay green | **PARTIAL** | PR #12 + PR #13 Server jobs green; a clean `main` CI run is the final confirmation. |

**Standing note:** the feature is **not** to be called complete. Priority 2
(MapLibre browser test) is the next item to attack after Priority 1.
