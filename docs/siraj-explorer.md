# SIRAJ Explorer

Open **SIRAJ Explorer** from the workspace or `/app/siraj-explorer`. On an existing site, migrate the app, build assets and clear the site cache after updating; restart web processes if they still serve old Python modules. The previous HTTP 500 errors require the server traceback if they continue: these map changes do not diagnose site-specific backend failures.

## Geographic map

The map starts with a locally hosted **Natural Earth 1:110m** country basemap. It is a generalized, low-detail world overview, not a street map or authoritative boundary dataset. Leaflet, marker clustering, TopoJSON and the dataset are bundled with licenses under `siraj_research/public/vendor`. No third-party requests are made in local mode. The Frappe server and the user's authorized session must remain reachable: this is offline **from the public Internet**, not an offline-first application or a saved copy of research data. No offline street tiles, download pack, or background cache is included.

Choose **Online: OpenStreetMap** to request public OSM raster tiles. This sends the browser IP address and viewed area to OpenStreetMap; it does not send research records. Attribution is displayed. If tiles fail, select the local basemap. The public tile service is subject to its usage policy; production sites should assess their own provider requirements. The existing SIRAJ Settings map provider, download, overlays and other map preferences are not currently wired to the explorer.

Marker shapes and colors identify Person, Institution, Place, Event, Military Unit and Operational Deployment. Select a marker for its record-owned coordinates, uncertainty and source; circles visualize positive recorded uncertainty up to 1,000 km. Cluster counts, type filtering, text search, fit, metric scale, two-point distance measurement and export of the filtered visible points as GeoJSON are available. Exported files can contain sensitive research data and should be handled accordingly. Record-owned coordinates are never replaced with a linked Place's coordinates. Unset, invalid, and ambiguous (0, 0) pairs are excluded. A single zero may also be an unset Frappe Float field; review the record before drawing conclusions.

If the geographic-data endpoint fails, the basemap can still load and the page says record data is unavailable. It does not fabricate markers. If the local basemap asset itself fails, the status message reports that as well.

## Relationship map

The graph contains visible Person, Institution, Place, Event and Source records, including isolated nodes. It shows a relationship only if the relationship and both endpoints are readable. Click a node or edge for details; the inspector lists visible connections and clickable neighboring records. Use **Back** to retrace node navigation, or drag, zoom, search, filter and fit the network. Search and type filters remove nonmatching nodes and their edges from the current view. For more than 500 nodes the graph uses a draggable grid rather than force simulation. This is not a complete replacement for the original application's full atlas and layouts.

## Structures and security

Structures group people, institutions, places, events, relationships, sources and military units. The current modes are an expandable tree and first-level distribution bars; a tree branch displays its child-group count. The original six-renderer structure deck and cross-module military explorer remain unimplemented.

All explorer data uses Frappe list and per-document permission checks. The server returns at most the first 1,500 list-visible records per type, ordered by name, and warns when truncated. Counts and graph coverage are for the loaded, permitted subset, **not necessarily the whole database**. User permissions may also remove records from that subset. The app does not persist exported data or offline record caches.

## Checks

Run `python3 -m unittest discover -s tests -v`, `node tests/test_explorer_assets.js`, and `node --check siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.js`. The mocked UI smoke test can be run without modifying the app's dependency tree:

```bash
npm install --prefix /tmp/siraj-ui-test --no-save jsdom@24.1.3 jquery@3.7.1
NODE_PATH=/tmp/siraj-ui-test/node_modules node tests/test_explorer_ui.js
```

These are not a substitute for testing on an actual Frappe v15 site and browser with different roles, restricted records, more than 1,500 records, offline Internet access, tile failures, keyboard use and mobile layout.
