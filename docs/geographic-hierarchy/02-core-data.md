# 2. Core data: countries, level definitions, per-country configuration

Core data is what turns "a governorate" into a country-specific concept. SIRAJ
stores geography in up to **six levels (0–5)**. Level `0` is always the country;
levels `1–5` are optional _in depth_ and _in name_. A country may use three
levels, skip the middle one entirely, or call level 1 `Region` instead of
`Governorate`.

Three DocTypes describe that contract:

* `Admin Level` — the global catalogue of the six levels (one row per level).
* `Country Level Config` — one document per country, always six child rows.
* `Country Level Row` — the child row (active flag, English/Arabic labels, order, skip reason).

## 2.1 The level catalogue

| Level | Key | Link field / DocType | Code prefix | Default EN | Default AR |
|---|---|---|---|---|---|
| 0 | `country` | `country` → **Country** | `C` | Country | الدولة |
| 1 | `governorate` | `governorate` → **Governorate** | `G` | Governorate | المحافظة |
| 2 | `district` | `district` → **District** | `D` | District | القضاء |
| 3 | `municipality` | `municipality` → **Municipality** | `M` | Municipality | البلدية |
| 4 | `village` | `village` → **Village** | `V` | Village | القرية |
| 5 | `community` | `community` → **Community** | `Q` | Community | الحي |

`Admin Level` is seeded from `siraj_research/geo_levels.DEFAULT_LEVELS` and is
read-only in normal operation. It exists so that list views, reports and the
Explorer can translate `level → doctype/label/prefix` without hard-coding the
mapping. `is_optional` is `true` for levels 1–5.

## 2.2 Creating a country

`Country` is the framework DocType; SIRAJ uses two of its fields:

* `name` — the English label shown in the hierarchy and in `ancestry_labels`
  (e.g. `Iraq`). It is also the `Country Level Config` document name.
* `code` — ISO 3166-1 alpha-2, uppercase (`IQ`, `SA`, `LB`, `JO`, `PS`, `IL`).
  SIRAJ builds every code as `<country code>-<…>`, so this field must be set.

The reference seed inserts `249` countries from
`siraj_research/setup/reference_data/countries.json` and never overwrites an
existing row (`_insert` → "exists, skipped"). To add a country manually:

```bash
bench --site research.local execute frappe.get_doc \
  --kwargs '{"doctype":"Country","country_name":"Yemen","code":"YE"}'   # does NOT save
```

In practice use the Desk (**Country → New**) or the seeding command, which
commits correctly:

```bash
bench --site research.local execute siraj_research.geo_seeding.seed_admin_levels
```

`seed_admin_levels()` upserts the six `Admin Level` rows only. Countries are
seeded by `seed_core` / `after_install` (chapter 3 uses the same helpers).

## 2.3 `Country Level Config` schema

| Field | Type | Rules |
|---|---|---|
| `country` | Link → Country | required, unique; document name = country name |
| `hierarchy_depth` | Int 0–5 | deepest active level; rows above it are forced inactive |
| `levels` | Table → Country Level Row | exactly six rows, sorted by `level` |
| `notes` | Small Text | free text |
| `source_reference` | Data | provenance, e.g. `level_configs.json v1` |
| `reset_levels` | Button | replaces rows with catalogue defaults |

`Country Level Row`:

| Field | Type | Meaning |
|---|---|---|
| `level` | Int 0–5 | unique inside the document |
| `level_key` | Data | copied from the catalogue (`governorate`, …) |
| `is_active` | Check | `1` = this level exists in the country |
| `label_en`, `label_ar` | Data | English required; Arabic falls back to English |
| `sort_order` | Int | display order in pickers/cascade (`level * 10` default) |
| `skip_reason` | Small Text | why the level is inactive (shown in the UI) |

Validation (`country_level_config.py`):

1. **All six rows are always present.** Missing rows are appended from the
   defaults, inactive when above `hierarchy_depth`. This keeps skips explicit and
   reversible instead of "absent means active".
2. `level` must be unique and within `0–5`; latitude/longitude are not involved.
3. `label_en` is mandatory. `label_ar` may be empty → the API falls back to
   `label_en`, then to the catalogue, never to the fieldname.
4. `hierarchy_depth` outside `0–5` is rejected.
5. Saving clears the Redis key `siraj:geo_levels:<country>` (TTL 3600 s), so
   labels and skips take effect on the next request.

## 2.4 Shipped configurations

`setup/reference_data/level_configs.json` (**"SIRAJ level configs v1"**) seeds
six countries. Labels are the ones users actually see; inactive levels keep a
`skip_reason`.

| Country | Depth | Active labels (EN / AR) | Skipped |
|---|---|---|---|
| **IQ** Iraq | 5 | Governorate / المحافظة · District / القضاء · Subdistrict / الناحية · Village / القرية · Community / المحلة | — |
| **SA** Saudi Arabia | 4 | Region / المنطقة · Governorate / المحافظة · Municipality / البلدية · District / Neighbourhood / الحي | Community |
| **LB** Lebanon | 3 | Governorate / المحافظة · District / القضاء · Municipality / البلدية | Village, Community |
| **JO** Jordan | 4 | Governorate / المحافظة · District (Liwa) / اللواء · Subdistrict (Qada) / القضاء · Village / القرية | Community |
| **PS** Palestine | 5 | Governorate / المحافظة · District / المنطقة · Municipality / البلدية · Village / Neighbourhood / القرية · Community / المجتمع | — |
| **IL** Israel | 4 | District / اللواء · Subdistrict / القضاء · Municipality / البلدية · Locality / القرية | Community |

Every other country falls back to the catalogue defaults at depth 5 (all levels
active, default labels), so a country can be used before anyone configures it.

Resolve a configuration in Python or over the API:

```bash
bench --site research.local execute siraj_research.geo_levels.get_level_config \
  --kwargs '{"country":"Lebanon"}'
```

```json
{"country": "Lebanon", "source": "override", "depth": 3,
 "levels": [
   {"level": 0, "key": "country", "field": "country", "doctype": "Country",
    "is_active": true, "label_en": "Country", "label_ar": "الدولة",
    "sort_order": 0, "parent_field": null, "ancestor_fields": [], "skip_reason": ""},
   {"level": 1, "key": "governorate", "field": "governorate", "doctype": "Governorate",
    "is_active": true, "label_en": "Governorate", "label_ar": "المحافظة",
    "sort_order": 10, "parent_field": "country", "ancestor_fields": ["country"], "skip_reason": ""},
   {"level": 3, "key": "municipality", "field": "municipality", "doctype": "Municipality",
    "is_active": true, "label_en": "Municipality", "label_ar": "البلدية",
    "sort_order": 30, "parent_field": "district", "ancestor_fields": ["country","governorate","district"], "skip_reason": ""},
   {"level": 4, "key": "village", "field": "village", "doctype": "Village",
    "is_active": false, "label_en": "Village", "label_ar": "القرية",
    "sort_order": 40, "parent_field": null, "ancestor_fields": [], "skip_reason": "Lebanese municipalities cover settlements"}
 ],
 "labels_en": {"country": "Country", "governorate": "Governorate", "...": "..."},
 "labels_ar": {"country": "الدولة", "governorate": "المحافظة", "...": "..."},
 "active_fields": ["country", "governorate", "district", "municipality"],
 "inactive_fields": ["village", "community"]}
```

(`levels` above is abridged; the real payload always contains six entries.)

### Editing a configuration

Desk path: **Country Level Config → Iraq**. Change `hierarchy_depth`, tick/untick
`is_active`, edit `label_en` / `label_ar`, set a `skip_reason`, save. The form's
**Reset to defaults** button restores the catalogue.

Scripted path — the same document API, with validation:

```python
# bench --site research.local console
import frappe
doc = frappe.get_doc("Country Level Config", "Iraq")
doc.hierarchy_depth = 4                      # drop Community, keep Village
for row in doc.levels:
    if row.level == 5:
        row.is_active = 0
        row.skip_reason = "Not used for reporting in Iraq"
doc.save()                                   # validates + clears cache
```

### Skipped levels in practice

A skipped level is **not** a hole in the data; it is a level that does not
exist. Two consequences, enforced by `geo_levels.validate_chain` and
`geo_lineage`:

1. The field of a skipped level must stay empty. Writing a value into it raises
   `inactive_level_populated` (warnings during bulk import, hard error on form
   save).
2. A record below a skipped level links to the **nearest active ancestor**. In
   Lebanon, a `Municipality` has `country`, `governorate` and `district` set,
   `village`/`community` empty, and its ancestry path stops at the
   municipality: `Lebanon/LB-BA/LB-BA-ZH/…`.

A chain is reported as a **gap** only when the nearest active ancestor is empty
*and* another active ancestor strictly between the country and the record is
populated — that is a genuinely broken chain, not a short one. Chains attached
to the country alone are "incomplete but allowed" and are surfaced as gaps in
`display_resolution`, never as fabricated records.

## 2.5 Seeding commands

```bash
cd ~/frappe-bench

# Catalogue + shipped country configurations; idempotent
bench --site research.local geo seed-levels

# Countries + lookups + reference hierarchy (never touches demo data)
bench --site research.local geo seed-core --country IQ
bench --site research.local geo seed-core                # all reference countries

# Level configurations from setup/reference_data/level_configs.json
bench --site research.local execute siraj_research.geo_seeding.seed_country_level_configs
bench --site research.local execute siraj_research.geo_seeding.seed_country_level_configs \
  --kwargs '{"overwrite":True}'                          # replace operator edits explicitly
```

`seed_country_level_configs` never overwrites an existing configuration unless
`overwrite=True`; unknown country codes are written to
`private/offline-cache/country-level-configs-rejections.csv`, not silently
dropped.

## 2.6 Using the configuration at runtime

The configuration drives four surfaces:

* **Forms** — link field labels are replaced at render time
  (`geo_hierarchy_ui.level_labels`), so a Saudi user sees *Region*, an Iraqi user
  sees *Governorate*.
* **Cascade widget** — `geo_cascade.cascade` returns
  `{field, value, label, chain, chain_list, filters, options, level_config}`;
  filters only include active ancestor fields, and clearing a level clears every
  descendant (`geo_levels.clear_descendants`).
* **Resolver** — `display_resolution` emits one entry per level with
  `status ∈ {linked, resolved, gap}`, plus `level_config` so the map popup can
  label a gap as *Community (not used in Lebanon)* rather than showing an error.
* **Reports / list views** — `Country Level Config.level_labels()` returns
  `{field: {"en": …, "ar": …}}` for column headers.

`ancestry_labels` is always the English chain (`Iraq › Baghdad › Karkh`), and the
API exposes `ancestry_labels_ar` equivalents through `text_ar` in
`display_resolution`. Storage stays language-neutral; translation happens on
read.

## 2.7 Cache and invalidation contract

| Key | Value | TTL | Invalidated by |
|---|---|---|---|
| `siraj:geo_levels:<country>` | full `config_payload` | 3600 s | config save/delete, `clear_cache()`, `bench clear-cache` |
| resolver LRU (per worker) | last 1 024 results | until restart | dataset switch (`index_version`) invalidates the PostGIS index cache |
| `index_version` (`Boundary Dataset`) | geometry cache version | persistent | bump after import/backfill |

Nothing is cached across sites: the keys are namespaced by Frappe's site-aware
Redis database. A second site on the same bench is unaffected.
