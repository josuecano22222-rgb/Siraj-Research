# Governorate Geo-Data Fill — Design Note

Status: **PROPOSED — awaiting approval** (step 2 of the Governorate geo-data task).
No implementation until this design is approved.

## Goal

Complete `Governorate.latitude`, `Governorate.longitude`, and `Governorate.bbox`
(W,S,E,N) for every Governorate row, **derived from geometry** — never
hand-written coordinates. This makes map-click auto-fill of `country` and
`governorate` possible (the map's `admin_fields` already include
`governorate`).

## Scope (what is filled, what is not)

Filled by this command:
- `latitude`, `longitude` — the representative point of the governorate polygon.
- `bbox` — string `"W,S,E,N"` (West, South, East, North), `W <= E`.
- `source_kind` — tagged `"Imported"` (from Admin Boundary) or `"Online"`
  (from Natural Earth admin-1).
- `source_dataset` — linked to the Boundary Dataset used, where applicable.

**Not** filled / not touched by this command:
- `boundary` (Link to Admin Boundary) — left to the boundary-import flow; this
  command only reads Admin Boundary geometry when a link already exists.
- `geojson`, `geo_point`, `pcode`, `parent_pcode`, `admin_level_type` — out of
  scope for this fill.
- `country` — already populated (4006/4006 in the seed); the command only
  *uses* `country` for matching, never writes it.

## Matching key — code, not name

Matching is **always on the stable code**, never on `label_en`/`label_ar`/name.
Names are locale-dependent, ambiguous, and not stable across sources.

- **Governorate side:** `code` is an ISO 3166-2 first-level code
  (e.g. `JO-AM`, `AD-07`). `country` holds the ISO 3166-1 alpha-2 country
  (e.g. `JO`, `AD`).
- **Admin Boundary side (imported):** match on `pcode == governorate.code`
  (case-insensitive, trimmed) **and** `level == 1`. `Admin Boundary` rows carry
  `pcode`, `country`, `level`, `bbox_min_lon/lat`, `bbox_max_lon/lat`, and a
  `geometries` table.
- **Natural Earth admin-1 side (fallback):** verified against the real bundled
  `110m/ne_110m_admin_1_states_provinces.geojson` - every feature carries
  `iso_3166_2` (e.g. `US-MN`) **directly equal to the Governorate `code`**,
  plus `iso_a2` (country). Matching key is therefore
  `feature.iso_3166_2 == governorate.code` (normalized, case-insensitive),
  with `iso_a2` used only as a country-consistency check. **If a feature
  lacks `iso_3166_2`, or a code has no matching feature, it is reported
  unmatched** - there is no name fallback and no suffix guessing. (The
  original design proposed a `(iso_a2, admin_1_code)` vs
  `(country, suffix(code))` key; real-schema inspection showed `iso_3166_2`
  already carries the full code, so the direct comparison is used.)

Normalization rules:
- Trim + uppercase codes on both sides.
- Longitudes normalized to `[-180, 180]` before any comparison.
- A governorate is **unmatched** (reported, never filled) when no Admin
  Boundary row and no NE feature matches its code. We do not fall back to name
  matching or nearest-name.

## Source precedence — imported Admin Boundary first, Natural Earth fallback

1. **Imported Admin Boundary first.** If the Governorate already has a
   `boundary` Link (or an Admin Boundary row matches its `pcode` at `level==1`),
   derive lat/long/bbox from that Admin Boundary's geometry. This is the
   full-resolution, site-authoritative source.
2. **Natural Earth admin-1 fallback.** Only when no Admin Boundary match exists,
   derive from the NE `admin_1_states_provinces` layer — preferring the finest
   **available** scale (10m > 50m > 110m; 110m is always bundled).

**Never overwrite a more detailed imported boundary result with a Natural Earth
one.** Concretely: a row that already has coordinates tagged `Imported` is
skipped entirely; NE never writes to it. Imported is strictly more detailed.

## Representative point — not centroid

Use **`shapely.geometry.shape(geom).representative_point()`**, which is
guaranteed to lie *inside* the polygon. Do **not** use the centroid: for
concave polygons, islands, and multi-part shapes the centroid can fall outside
the polygon (or in the sea), which would put the map marker off the
governorate. This matches the existing `geo_resolve.resolve_area` convention
(already uses `representative_point()`).

- Admin Boundary: representative point of the row's `geometries` geometry.
- Natural Earth: representative point of the NE feature geometry.

## Antimeridian handling

The `bbox` field stores `"W,S,E,N"`. The invariant is **`W <= E`**.

- Longitudes are normalized to `[-180, 180]`.
- For a polygon that **crosses the antimeridian** (its longitude extent
  exceeds 180°, e.g. a feature spanning 179°E to -179°W), a naive
  `min/max` would produce `W > E` (e.g. `W=179, E=-179`), which is malformed.
- **Handling:** detect the crossing (max_lon - min_lon > 180). When detected,
  normalize the polygon's longitudes into a continuous frame (shift the
  western-wrapped part by +360, or the eastern part by -360) so the bbox is
  well-formed, compute `W,S,E,N` with `W <= E`, then map the representative
  point back to `[-180, 180]`. This is the "explicit antimeridian flag" case:
  the crossing is detected and handled explicitly, and the stored bbox always
  satisfies `W <= E`. **No new schema field is added.**

## Idempotency — fill-only-empty

The command is **idempotent** and **fill-only-empty**:

- For each Governorate, a field is written **only if it is currently empty**
  (`latitude`/`longitude`/`bbox` is `None`/blank).
- Rows that already have coordinates are counted `already_set` and skipped —
  a second run changes nothing (the canonical idempotency test).
- `source_kind` is set only on rows this run actually fills.
- The command performs **no `frappe.db.commit()`** in patches (per standing
  rules); the idempotency comes from the fill-only-empty guard, not from
  committing.

Result: re-running yields the same coverage report with `filled=0` and the
same `already_set`/`unmatched` counts.

## Resolver (for the live map-click test and future re-resolution)

Reuse the existing bbox/shapely helpers (`map_search.point_in_bbox`,
`geo_resolve` tree/representative-point machinery) with this precedence:

1. **Bbox prefilter** — narrow candidate polygons by the click point's
   neighborhood (bbox intersect), using the Admin Boundary `bbox_min/max`
   columns and the NE layer's per-feature bbox.
2. **Point-in-polygon** — exact `shapely.geometry.points`/`contains` test on
   the prefiltered candidates.
3. **Nearest within a configurable distance** — if no candidate contains the
   point (e.g. offshore, or on a border vertex), fall back to the nearest
   polygon within a configurable max distance (default e.g. 0 km = strict,
   configurable via Geo Settings or a command arg). Offshore points with no
   candidate within the threshold resolve to **no governorate** (reported),
   never to a guessed nearest.

This resolver is exercised by the live test (click inside, on a border,
offshore) in step 5.

## Report format

The command prints a single coverage report to stdout and returns it as a dict:

```
[governorate-geo-fill] total=<N>
[governorate-geo-fill] filled=<A>  (imported=<I>, natural_earth=<NE>)
[governorate-geo-fill] already_set=<B>
[governorate-geo-fill] unmatched=<U>
[governorate-geo-fill] unmatched codes: <code1, code2, ...>   (if any)
```

- `filled` — rows that had empty coords and were filled this run, split by
  source (`imported` vs `natural_earth`).
- `already_set` — rows that already had coordinates (skipped).
- `unmatched` — rows with no matching geometry in either source; their `code`
  values are listed explicitly. **Unmatched rows are reported, never filled.**

No claim of "full coverage" is made unless the report shows `unmatched=0`.

## Tests first (step 3, stub — no bench)

Pure-Python stub tests (CI pure-Python gate) assert:
1. bbox contains the representative point (`W <= lon <= E`, `S <= lat <= N`).
2. `W <= E` (or the explicit antimeridian-handled normalization).
3. fill-only-empty: a row with pre-existing coords is not overwritten.
4. idempotency: a second run changes nothing.
5. unmatched rows are reported, not filled.
6. source tag (`Imported` vs `Online`) is recorded on filled rows.

Live resolver tests (step 5, bench): click inside a governorate, on a border,
and offshore — assert correct resolution / no-resolution behavior.

## Implementation shape (step 4, after approval)

- One idempotent `bench execute` command, e.g.
  `bench --site <site> execute siraj_research.api.governorate_geo.fill_governorate_geo`
  (new module), reading geometry from Admin Boundary first, NE admin-1
  fallback, writing only empty fields, printing the coverage report.
- Admin button: deferred to a later step (step 4 notes "and an admin button
  later").
- No `frappe.db.commit()` in the command body (documented DDL exceptions only,
  and none are needed here).
- Reuse `natural_earth_vector.read_layer` / `available_scales` for NE access;
  reuse `boundary_import`-produced Admin Boundary rows for imported access.
