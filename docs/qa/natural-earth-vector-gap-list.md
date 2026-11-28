# Natural Earth Vector — Gap List

**Status: NOT complete.** This is an honest per-spec-item status for the
Natural Earth Vector feature, derived from `docs/natural-earth-vector.md`.
The Python / API / DocType / serving / provisioning / security side is
**implemented and locally verified green**. The JS map capabilities are
**implemented but not runtime-verified** (no dedicated browser/JS test).
The Server job on `main` has **not** been re-run green since the orphan-fix
(step 5 of the directive holds Phase R 3–9 until that happens).

**Local verification basis (2026-11-24, branch `arena/4bf5fef5-siraj-research`,
commit `042f105`):**
- `bench migrate` — **no** `Orphaned DocType(s) found: Natural Earth Vector Pack`
  and **no** `Deleting orphaned DocTypes` (orphan-delete defect fixed).
- `test_natural_earth_vector` — `Ran 28 tests ... OK`.
- `test_api_data_group_isolation` — `Ran 27 tests ... OK` (incl. `test_20`
  NE endpoints registered & gated; was `errors=1` before the orphan fix).

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
| `SirajNeVector.attach(map, opts)` on MapLibre + Leaflet | **PARTIAL** | Implemented in `public/js/siraj-nevector.js` (`attachMapLibre`, `attachLeaflet`, `window.SirajNeVector.attach`). **Not browser-verified; no dedicated JS test.** |
| Scale-tiered basemap (110m/50m/10m + fallback to finest available) | **PARTIAL** | Logic present in `siraj-nevector.js`. **Not browser-verified.** |
| Choropleth `setChoropleth(field, valueByKey)` + legend | **PARTIAL** | `setChoropleth` in both engines. **Not browser-verified.** |
| Click-to-country `onCountryClick(cb)` (ISO codes, name, …) | **PARTIAL** | `onCountryClick` in both engines (MapLibre `queryRenderedFeatures`, Leaflet feature clicks). **Not browser-verified.** |
| Full layer set (ocean, land, lakes, boundaries, rivers, places, choropleth-safe countries) | **PARTIAL** | Layer construction present. **Not browser-verified.** |

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
| `test_natural_earth_vector` (pack/manifest/serve/security) | **DONE** | 28 tests, green locally. |
| NE endpoints registered & gated (in isolation suite) | **DONE** | `test_20_natural_earth_vector_endpoints_registered_and_gated`, green after orphan fix. |
| Dedicated JS test for `SirajNeVector` / map capabilities | **NOT STARTED** | No JS test references `SirajNeVector`/`nevector`. Map capabilities rely on manual/browser verification. |

## 10. CI / Server job

| Spec item | Status | Notes / evidence |
|-----------|--------|------------------|
| `test_natural_earth_vector` wired into `server.yml` | **DONE** | Present in the module loop (commit `f1bd122`). |
| Server job green on `main` (post-orphan-fix) | **NOT STARTED** | Directive step 5: Phase R 3–9 held until the Server job is green on `main`. The local bench is green; the CI Server job has not been re-dispatched/re-run since the orphan fix. |

---

## Summary

- **DONE:** dataset/catalog, bundled 110m, all serving endpoints, all
  provisioning (both sources, manifest, ZIP, admin gating), security &
  licensing, Python tests. This is the bulk of the spec and it is locally
  verified green.
- **PARTIAL:** all JS map capabilities (`SirajNeVector` attach,
  scale-tiered basemap, choropleth, click-to-country, full layer set,
  basemap-switcher modes, offline-viewer toggle). Implemented and wired in,
  but **not runtime-verified** — no dedicated JS/browser test exists.
- **NOT STARTED:** dedicated JS test for the map capabilities; re-running the
  Server job on `main` post-orphan-fix.

**This feature is not complete.** The Python/API/DocType/serving/provisioning
layer is solid and locally green, but the map-rendering layer needs browser
verification (and ideally a JS test), and the Server job on `main` must be
confirmed green before Phase R steps 3–9 resume.
