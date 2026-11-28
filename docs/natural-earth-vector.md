# Natural Earth Vector

SIRAJ now integrates the full **Natural Earth Vector** dataset — the
public-domain world geographic database of cultural and physical layers
(points, lines and polygons) at three scales — as a true *vector* basemap
and analysis layer set, packaged for offline use.

Source: `nvkelso/natural-earth-vector` (version 5.2.0-pre), **public domain**.
See `siraj_research/public/natural_earth/LICENSE.md` for the full license text.

## What the dataset provides

206 GeoJSON layers across three scales, covering the full Natural Earth
cultural + physical catalogue:

| Scale | Nominal | Layers | Size | Availability |
|-------|---------|--------|------|--------------|
| 110m | 1:110 million | 32 | ~20 MB | **Bundled in the app** — works offline out of the box |
| 50m | 1:50 million | 45 | ~60 MB | Provisioned pack (admin tool) |
| 10m | 1:10 million | 129 | ~1.1 GB | Provisioned pack (admin tool) |

Cultural layers (144): country/admin boundaries, map units, populated places,
ports/airports, roads/railways/pipelines. Physical layers (62): ocean, land,
lakes, rivers, coastline, glaciated areas, physiography, marine/regional
polygons, graticules.

The authoritative metadata for every layer lives in
`siraj_research/natural_earth_catalog.py` (scale, category, rendering kind,
description, byte size).

## Architecture

```
natural_earth_catalog.py      full 206-layer catalog + scale/zoom-tier logic
natural_earth_vector.py       pack provision / manifest / validate / serve
api/natural_earth_vector.py   public endpoints + admin provision endpoint
doctype/natural_earth_vector_pack/   admin DocType + controller + UI
public/natural_earth/110m/    bundled 1:110m GeoJSON (public assets)
public/js/siraj-nevector.js   MapLibre + Leaflet vector basemap controller
siraj-basemap.js / siraj-map.js   basemap switcher integration
offline_map/viewer.js         offline viewer: raster ↔ Natural Earth Vector toggle
```

### Serving

- The bundled 110m tier is served as static app assets.
- Provisioned 50m/10m tiers live in **site private storage**
  (`private/natural_earth_vector/`) — matching the existing MBTiles /
  Boundary-pack pattern. They are never fetched at map render time.
- `GET /api/method/siraj_research.api.natural_earth_vector.layer?layer=<name>`
  serves raw GeoJSON (`application/geo+json`, ETag + 304, one-hour cache).
- `GET /api/method/siraj_research.api.natural_earth_vector.manifest` returns
  the combined manifest (bundle + pack, zoom tiers, available scales).
- `GET /api/method/siraj_research.api.natural_earth_vector.catalog` and
  `.index?scale=` expose the catalog and per-scale availability.

### Provisioning (admin)

The **Natural Earth Vector Pack** DocType provisions the 50m and 10m tiers
into private storage and compiles the offline ZIP archive
(`natural_earth_vector.zip`) from the pack. Two sources are supported:

1. **git_clone** (default): a blob-filtered sparse clone of the canonical
   GitHub mirror (git protocol — no API rate limits), so the full 1:10m
   tier (~1.1 GB) provisions reliably.
2. **local_mirror**: copy from an administrator-supplied directory inside the
   site, for air-gapped provisioning.

Provisioning writes a validated `manifest.json` (per-layer sha256, byte
counts, scales, provenance) and rebuilds the ZIP archive.

## Advanced map capabilities

`SirajNeVector.attach(map, opts)` builds the vector basemap on either engine:

1. **Scale-tiered basemap** — world zoom renders the 1:110m tier, mid-zoom
   the 1:50m tier, detailed views the 1:10m tier, automatically falling back
   to the finest *available* tier when a tier has not been provisioned.
2. **Choropleth** — `setChoropleth(field, valueByKey)` colours the
   admin-0 countries layer by any feature property with a sequential palette
   and returns a ready-to-render legend.
3. **Click-to-country** — `onCountryClick(cb)` resolves map clicks to the
   country feature under the cursor (MapLibre `queryRenderedFeatures` /
   Leaflet feature clicks) and invokes the callback with the full feature
   properties (ISO codes, name, continent, population, …).
4. **Full layer set** — ocean, land, lakes, country boundaries, state/
   province lines, rivers, populated places (with labels), with a
   choropleth-safe countries layer.

The basemap switchers expose **Natural Earth Vector** as a mode:
`siraj-basemap.js` (Leaflet surfaces) and `siraj-map.js` (MapLibre Explorer).
The offline viewer gains a **Raster / Natural Earth Vector** toggle that
renders the bundled 110m vector layers, so offline packages show vector
basemaps, not only raster imagery.

## Security & licensing

- All data is public-domain world map data — no privacy-sensitive content,
  unauthenticated serving (mirroring the existing tile cache).
- Layer names are validated against the catalog before any file access
  (path-traversal guard); pack files are written only inside the pack root
  and the mirror directory must live inside the site.
- Provisioning endpoints require administrator permission.
