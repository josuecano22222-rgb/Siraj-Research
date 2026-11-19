# Point picking, the Geolocation field and zero coordinates

## Why some forms had no visible map

The old picker was not a real DocType field. `coordinate_map.js` injected a
`<div>` immediately after the `longitude` control. It only mounted when both
coordinate controls existed, were not permission-hidden, were wide enough to
measure, and the injected wrapper survived every Frappe layout refresh. A
collapsed section, hidden tab, stale asset bundle or a single JS exception in
that setup path could therefore leave an otherwise valid form with no map.

The picker is now a **native field**:

```text
fieldname: geo_point
fieldtype: Geolocation
label:     Map (point)
```

This field has been added additively to every SIRAJ DocType that has
`latitude`/`longitude`, including Person, Institution, Place, Research Event,
Siraj Event, Military Unit, Operational Deployment and the six administrative
level DocTypes. `bench migrate` adds its column; no existing data is changed.

## Why `latitude`/`longitude` are still Float fields

The agreed long-term type for the *coordinate fields* is `Data` (exact decimal
text), because binary Float storage can round values that a researcher typed.
The repository's [coordinate migration plan](qa/coordinate-migration.md) still
marks that conversion **blocked**: changing the field metadata alone would ask
Frappe to alter the physical SQL columns on `bench migrate`, and existing
values, defaults, customisations and recovery have not been rehearsed for this
site. That is why the screenshots still show Float.

The native `Geolocation` field is different from those mirrors:

- Frappe renders it as an interactive Leaflet map.
- Its stored value is a **GeoJSON FeatureCollection**, not a decimal number.
- GeoJSON orders a point `[longitude, latitude]`; SIRAJ coordinate fields store
  latitude first. `siraj-geopoint-core.js` performs that conversion without
  rounding.

So the division of responsibility is:

```text
Geolocation field  → interactive point selection and map rendering
Data/Float fields  → research values, exact text when migrated, reports, imports
Hierarchy links    → Country … Community, resolved from the selected point
```

## Automatic population bridge

`siraj-geopoint.js` listens to the native map's draw events and to the
coordinate fields:

1. A point drawn on the map is read from the GeoJSON FeatureCollection and
   written into `latitude` and `longitude` (with `geocoding_method=map_pick`
   and an initial `geometry_source` when available).
2. Typed or pasted latitude/longitude is converted into a point FeatureCollection
   so the native map shows the same location.
3. `SirajHierarchy.resolveAndApply` fills empty hierarchy fields with the
   existing diff-aware Keep/Replace behaviour; human-entered values are never
   silently replaced.
4. `SirajHierarchy.refreshForm` displays the full bilingual chain, gaps and
   provenance.

`coordinate_map.js` detects the native Geolocation field and mounts the
enhanced SIRAJ map **inside that field**. `siraj-geopoint.js` suppresses the
stock Geolocation `make_map()` for `geo_point` fields entirely, so Frappe
never tries to instantiate Leaflet.Draw/Locate plugins that are not present
on this bench. Other Geolocation fields are untouched.
That is why the visible map has the SIRAJ dock: navigation, basemap switching,
measure tools, hierarchy and the shared server-cached tiles. The native
field remains the stored DocType field; the bridge stands down when the
enhanced map is active, so there is only one writer.

`siraj-geopoint.js` remains the fallback for DocTypes that expose only the two
coordinate fields.

## Shared server-side layer cache

Every raster tile in Standard, Satellite/Aerial and Hybrid now comes from:

```text
/api/method/siraj_research.tile_cache.tile?layer=<layer>&z={z}&x={x}&y={y}
```

Hybrid labels use `layer=hybrid_labels`. No browser talks directly to OSM or
Esri. The server fetches a missing tile once, writes it atomically to
`site/private/siraj_tile_cache/`, and serves subsequent requests from disk with
long-lived browser caching headers. If the upstream provider is offline, a
cached tile is still served (stale-while-revalidate), so any user of the same
site sees previously viewed areas.

Enable the three shared layers once:

```bash
cd ~/frappe-bench
bench --site frappe.com execute siraj_research.tile_cache.enable_shared_basemaps
```

This enables Standard, Aerial and Hybrid, allows upstream fetches and keeps
tiles for at least 90 days. Optional layers that need Stadia/NASA credentials
are not enabled by that helper.

## Why `0,0` used to show a pin

A Float pair of `0.0` was historically used both for a real origin and for an
unset field. The old code plotted any numerically valid pair, so legacy
`(0,0)` records showed a pin in the Gulf of Guinea and were then resolved to a
misleading hierarchy.

The zero pair is now treated as **unset until confirmed**:

- no pin is drawn for `(0,0)` by the fallback map;
- no GeoJSON point is written into the map field for an unconfirmed zero pair;
- the form shows a warning and a **Confirm 0,0 as a real point** action;
- the additive Check field `coordinate_origin_confirmed` persists that decision;
- clicking the fallback map exactly on the origin is an explicit pick and sets
  the confirmation automatically.

This preserves genuine origin points without inventing a location for blank
legacy records.

## Deployment

Because this commit adds DocType fields, deployment needs a migration:

```bash
cd ~/frappe-bench/apps/siraj_research
git fetch origin arena/55527e79-siraj-research
git merge --no-ff FETCH_HEAD

cd ~/frappe-bench
bench --site frappe.com migrate
bench build --app siraj_research
bench --site frappe.com clear-cache
sudo supervisorctl restart frappe-bench-web:frappe-bench-frappe-web
```

The Float-to-Data conversion is **not** part of this merge. It needs its own
approved maintenance window, independent typed-value backup and rehearsal.
