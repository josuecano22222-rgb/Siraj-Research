# Hierarchical Location Cascade — Auto-Population Across All Tiers

**Status: implemented + core locally verified; Frappe-facing tests written for
the bench.** This delivers the comprehensive, integrated auto-population of
the administrative hierarchy for **any DocType** that carries location data,
covering **Country → Governorate → District → Municipality → Village →
Community** (countries = tier 1, governorates/provinces = tier 2,
districts/cities/sub-districts = tier 3 and below), triggered **whenever
location data is entered OR a location is selected**.

Siraj already had a mature six-level resolver (`geo_hierarchy`) and a save-time
`auto_fill_hierarchy` hook for six coordinate doctypes. This work closes the
gaps that kept it from being fully comprehensive and integrated.

## The four integrated additions

### 1. Natural Earth country enrichment + global fallback
- `natural_earth_geography.enrich_country(name_or_code)` — pure helper returning
  NE facts (name, Arabic name, ISO_A2/A3, ADM0 code, population) for a country
  name or code, in English **and Arabic**.
- `natural_earth_geography.enrich_chain_country(result)` — attaches NE
  enrichment to a resolved chain; when the country is a gap (a coordinate
  outside Siraj's scoped reference countries), it **globally falls back** to
  identifying the country straight from the coordinate via the bundled Natural
  Earth pack, so every coordinate yields a country even outside Siraj's data.

### 2. Unified cascade API (`api/location_cascade.py`)
`GET resolve_location_chain` — one authoritative endpoint that accepts either
**coordinates** (`latitude`/`longitude`, location data entered) **or** a
**selected Place** (`place_doctype`/`place_name`, a location selected), plus an
optional target `doctype`. Returns the bilingual chain (`levels`, `by_field`,
`gaps`), the `country_enrichment`, and `field_values` mapped onto that
DocType's location fields. Reuses `geo_hierarchy_ui.display_resolution` +
`field_values`; permission-gated on Place read.

### 3. Save-time cascade extended (`geo_doc_events.auto_fill_hierarchy`)
- **Place-selection cascade**: when a linked Place is selected but its
  coordinates haven't been copied onto the record yet, the hook fetches the
  Place's coordinates and resolves the full chain from them.
- **NE country fallback**: after local polygon resolution, if the country Link
  is still empty (out-of-scope coordinate), the country is resolved from NE and
  mapped to a real Frappe Country record so the Link validates on save.
- **Meta-driven coverage**: any DocType with the location field group
  (latitude/longitude + the standard administrative Link fields) auto-populates,
  not only the six registered in `COORDINATE_DOCS`.

### 4. Live frontend cascade (`public/js/siraj-geopoint.js`)
- **`resolveFromPlace(frm, cfg)`**: when a linked Place is picked, fetches its
  coordinates and resolves the hierarchy live — so selecting a location
  auto-populates country/province/city just like typing coordinates. Wired as a
  field handler on every coordinate doctype.
- **`configFor`** now defaults to the standard admin-field names, so the live
  cascade also covers custom DocTypes using the conventional field group.

## Verification
- **Framework-independent (runs in this sandbox):**
  `siraj_research.tests.test_natural_earth_geography` — **30 tests, green**,
  including `enrich_country` (code/English/Arabic), `enrich_chain_country`
  (resolved-name, coordinate fallback, ocean).
- **Frappe-facing (needs the user's bench):**
  - `siraj_research.tests.test_location_cascade_api` — coordinate + place
    paths, country enrichment, `field_values` mapping, permission gating,
    `build_cfg_from_meta` (registered / derived / non-coordinate).
  - `siraj_research.tests.test_geo_doc_events` — linked-Place coordinate
    fetch, NE country fallback, meta-driven helper.
- **Static:** `ruff check` clean on all new Python; `node --check` + `eslint`
  clean for the modified JS.

## Commands (run on the local bench)

```bash
cd ~/frappe-bench/apps/siraj_research

# Framework-independent core (runs anywhere Python + the bundled pack exist):
python3 -m unittest siraj_research.tests.test_natural_earth_geography -v

# Frappe-facing cascade tests (requires a live bench/site):
bench --site frappe.com run-tests --module siraj_research.tests.test_location_cascade_api
bench --site frappe.com run-tests --module siraj_research.tests.test_geo_doc_events

# Lint:
pip install ruff --break-system-packages -q
ruff check siraj_research/natural_earth_geography.py \
          siraj_research/api/location_cascade.py \
          siraj_research/geo_doc_events.py \
          siraj_research/geo_hierarchy_ui.py \
          siraj_research/tests/test_natural_earth_geography.py \
          siraj_research/tests/test_location_cascade_api.py \
          siraj_research/tests/test_geo_doc_events.py
```
