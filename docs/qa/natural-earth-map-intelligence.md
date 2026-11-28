# Natural Earth Vector — Country Intelligence & Data-Driven Choropleth

**Status: implemented + locally verified (core).** This closes the core
under-leveraged map capability identified in the engagement brief: Siraj's
Natural Earth Vector basemap was a **static reference basemap** — its
choropleth took caller-supplied per-country values with no server-side join
of Siraj site data onto country geometries. That gap is now filled, taking
Siraj's map from a reference basemap to a **data-driven, site-aware map
system**.

## What was built

### 1. Country intelligence (`siraj_research/natural_earth_geography.py`)

A framework-independent layer over the bundled 1:110m pack (`public/natural_earth/110m`).

- **`find_country(lon, lat)`** — point-in-polygon country lookup (bbox
  pre-filtered; Shapely fast-path with a manual ray-casting fallback so it
  works without the optional Shapely dependency). Reuses Siraj's existing
  `utils.map_search.point_in_bbox` / `haversine_m`.
- **`country_profile(code | lon, lat)`** — normalized country facts: ISO code,
  Arabic name, capital (from the populated-places layer), population, GDP,
  geodesic area, continent/region/income group, and label coordinates.
- **`iso_code` vs `adm0_code`** — Natural Earth stores `ISO_A3 = "-99"` for
  5 countries (e.g. France). `adm0_code` (`ADM0_A3`) is valid for **all 177**
  and is the canonical choropleth join key, so every country renders.
- **`classify` / `class_index`** — quantile and equal-interval choropleth
  class breaks (pure, testable).
- **`aggregate_site_data` / `resolve_site_country` / `choropleth_from_values`**
  — pure site-data aggregation: resolves Siraj records to countries by
  coordinate (preferred) or name, aggregates count/sum/mean, and builds a
  complete choropleth payload (breaks + `valueByKey` + `classByKey`).

### 2. API endpoints (`siraj_research/api/natural_earth_vector.py`)

- **`GET country_profile`** — public, cacheable country facts by ISO code or
  coordinate. No Siraj site data, no privacy-sensitive content.
- **`GET country_choropleth`** — data-driven choropleth. Accepts a Siraj
  `doctype` (validated to be a Siraj module doctype with `latitude`/
  `longitude`), an aggregation (`count`/`sum`/`mean`), a numeric
  `value_field`, and a classification `method`/`classes`. Aggregates only the
  records the caller can read (data-group isolation via the doctype's normal
  read permissions). **Fail-closed**: a caller without read access receives an
  empty choropleth (`source: "no_access"`), never site data.

### 3. JS map hooks (`siraj_research/public/js/siraj-nevector.js`)

Both the MapLibre GL and Leaflet (offline viewer) controllers gained:

- **`setChoroplethFromSite(doctype, opts)`** — fetches the server-side
  aggregation and colours the countries layer by `ADM0_A3`, so the choropleth
  is driven by Siraj's own data instead of caller-supplied values.
- **`countryProfile(feature)`** — fetches normalized country facts for a
  clicked country feature.
- Module-level **`fetchCountryProfile`** / **`fetchSiteChoropleth`** exposed
  on `window.SirajNeVector`, plus `CHOROPLETH_JOIN_FIELD`.

## Verification

- **Framework-independent (runs in this sandbox):** `siraj_research.tests.test_natural_earth_geography`
  — **23 tests, all green.** Covers country lookup, the `-99` ISO fallback,
  `adm0_code` validity for all 177 countries, profiles (incl. Arabic names +
  capitals), geodesic area (holes/multipolygons), choropleth classification,
  and site-data aggregation (count/sum/mean, name + coordinate joins,
  unmatched bucket).
- **Frappe-facing (needs the user's bench):** `siraj_research.tests.test_natural_earth_geography_api`
  — profile lookups, endpoint validation (non-Siraj doctype rejected,
  no-coordinate doctype rejected, bad agg rejected), aggregation wiring
  (mocked `frappe.get_list`), and the fail-closed no-access path.
- **Static:** `ruff check` clean on all new Python; `node --check` and
  `eslint` clean for the new JS (the 2 pre-existing `no-empty` empty-catch
  errors in the file are unchanged).

## Commands (run on the local bench)

```bash
# Core (framework-independent — runs anywhere Python + the bundled pack exist):
cd /home/user/Siraj-Research
python3 -m unittest siraj_research.tests.test_natural_earth_geography -v

# Frappe-facing API tests (requires a live bench/site):
bench --site frappe.com run-tests --module siraj_research.tests.test_natural_earth_geography_api

# Lint:
pip install ruff --break-system-packages -q
ruff check siraj_research/natural_earth_geography.py \
          siraj_research/api/natural_earth_vector.py \
          siraj_research/tests/test_natural_earth_geography.py \
          siraj_research/tests/test_natural_earth_geography_api.py
```

## What this adds over the Camera Archive model

Camera Archive exposed `get_country_profile` + `get_country_choropleth`. Siraj
now has the equivalent **plus**: a framework-independent core (testable without
a site), the `ADM0_A3` join key that guarantees every country renders (vs the
`-99` ISO trap), a fail-closed no-access path that never leaks site data, and
a dual-engine JS hook (MapLibre + Leaflet offline viewer) so the data-driven
choropleth works in both the online map and the offline snapshot viewer.
