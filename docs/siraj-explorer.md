# SIRAJ Explorer

Open **SIRAJ Explorer** from the workspace or `/app/siraj-explorer`. On an existing site where this Page is already installed, update the app, build assets, clear the site cache and restart the web processes. Test first on a backup/staging site: these changes have not yet been validated against a live Frappe v15 installation. This Explorer update does not itself require a schema migration. The repository's existing `patches.txt` references missing patch modules; investigate that separately before running `bench migrate` on any site. For the differences from the source application, see [original-feature-parity.md](original-feature-parity.md).

## Geographic map

The three-zone map has a filterable, incrementally displayed record list, a map and an inspector; both side panels can be hidden. Points are the records' **own** coordinates; linked Place coordinates are never silently substituted. Click a marker or list entry for details. Invalid, unset and ambiguous `(0, 0)` coordinates are excluded; a single zero may also be an unset Frappe Float field and should be reviewed. The coordinate-entry control navigates temporarily without writing a record; the inspector shows decimal and DMS coordinates.

The map starts with a locally hosted **Natural Earth 1:110m** country basemap. It is a generalized, low-detail world overview, not a street map or authoritative boundary dataset. Leaflet, marker clustering, TopoJSON and the dataset are bundled with licenses under `siraj_research/public/vendor`. Local mode makes no public Internet requests, but the Frappe server and authenticated session must remain reachable. No offline street pack or offline record cache is included. **Online: OpenStreetMap** sends the browser IP address and viewed area to the public tile service; attribution is displayed. Assess the provider's usage policy before production use. SIRAJ Settings' map provider and download settings are not yet wired to the Explorer.

Clusters, search/type filtering, fit, uncertainty circles (up to 1,000 km), distance and approximate spherical polygon area, and GeoJSON export are available. Measurements are estimates, not survey-grade results; self-intersecting polygons are not validated. **Show relationship lines** requests the permission-filtered relationship graph and draws lines only when both endpoints have visible, valid points in the current filtered view; selecting a line shows its relationship. Exported files can contain sensitive research data. If the data endpoint fails the local basemap can still load with an error; it does not fabricate markers.

## Relationship map

The graph includes visible Person, Institution, Place, Event and Source records, including isolated records, and relationships only when both endpoints and the relationship are readable. Select a record or edge to inspect fields and connections in place. Neighbor and relationship buttons remain in the inspector; an explicit **Open record** button is optional navigation. Search, entity type, relationship type and hide-ended filters apply to the displayed graph. Hide-ended means a stored end date is present, including future dates, matching the source application's convention.

Choose **Force**, **Orbit**, or **Matrix**. A centered orbit places neighbors into rings by shortest relationship distance, with a choice of one, two or three degrees. With no center, it places all filtered nodes on one ring. A person or institution can be selected from the center picker, or any selected node can be centered with **Center on selected record**. Set the relationship depth to include one, two or three degrees. **Show all records** restores the filtered graph. Filtering by entity type removes other types and their edges; changing the search or entity filter exits centered mode. **Back** retraces inspector neighbor navigation first, then previous centers. **Only relationships with evidence** loads readable Evidence-row counts on demand; relationships whose evidence field is inaccessible have an unknown count and are excluded while the filter is active, with a warning. Counting evidence loads each visible relationship document and can be costly. Matrix cells and row/column labels are selectable; parallel edges in the same cell may overlap, but each is available in the inspector's connection list. Above 500 nodes force mode uses a grid instead of a physics simulation. **Export SVG** saves the currently filtered graph or matrix. Force and orbit exports reconstruct a vector diagram from the current node positions rather than copying the canvas exactly; the matrix export preserves the rendered cells. The file contains sensitive record labels and relationship information.

## Structures

The same counted hierarchy feeds **Treemap, Rings, Flow, Matrix, Discs and Tree**. Source choices include people, institutions, places, events, relationships, sources, the military unit and region command trees, the categorized forces view, Regions × Units, and Units × Operations. The composites count each visible record once, including parent records; they are not distinct-unit-only counts. Units are attached to their visible region and operations to their visible unit. Missing or inaccessible parents are grouped anonymously; cross-region unit parent links are detached. Unreadable component DocTypes are reported and omitted, and an unreadable grouping field causes an error. Pick a mark to inspect its count, then **Explore group** or use the breadcrumb to move through levels. The tree's collapsed branches display their immediate child-group count; an aggregate folded tail carries its record total and the number of folded groups. Unit/region branch counts include the represented unit/region itself plus visible descendants. Inaccessible or broken parents become roots; cycles are detached deterministically for display without changing database records.

The **Records** toggle shows a maximum of 48 named record leaves per terminal group and an explicit aggregate for remaining records. It starts off above 3,000 records to avoid creating an enormous SVG; labels and counts remain available at the grouped levels. The accessible table follows the focused hierarchy, and SVG and CSV exports contain that displayed hierarchy. CSV values are quoted and formula-like cells are prefixed to reduce spreadsheet injection. Handle all exports as sensitive data. The two-level flow and matrix can be drilled into for deeper levels. Rings show at most 12 outer labels; the legend and table carry the remaining names. Depth limits visible group levels relative to the current focus; selecting a collapsed group and exploring it drills deeper. Find searches the loaded (already folded and leaf-limited) tree, so it cannot discover omitted names. The legend can be hidden. With focus in the deck, keys 1–6 switch layouts and Escape moves up a level. The interface does not yet implement all original deck controls.

## Permissions, counts and scale

All endpoints scan Frappe `get_list` in pages and additionally check document-level read permission. Relationship endpoints never return edges whose endpoints are not included in the visible graph. Structures counts are for the current user's permitted records, not all records in the database; hidden grouping fields cause an error rather than a misleading “not recorded” count. There is no former 1,500-record per-type cutoff. A synchronous scan plus a per-document permission check and full in-browser graph/map can be slow or run out of time/memory on large datasets. Concurrent edits during paging can change results; the scan is not a guaranteed cross-request snapshot. Assess scale on a representative staging database before production rollout.

## Checks

Run `python3 -m unittest discover -s tests -v`, `node tests/test_explorer_assets.js`, and `node --check` on both `siraj_research/public/js/structure_deck.js` and `siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.js`. The DOM and Chromium smoke tests use synthetic data and can run without modifying app dependencies:

```bash
npm install --prefix /tmp/siraj-ui-test --no-save jsdom@24.1.3 jquery@3.7.1
NODE_PATH=/tmp/siraj-ui-test/node_modules node tests/test_explorer_ui.js
npm install --prefix /tmp/siraj-browser --no-save puppeteer-core@24.2.0 @sparticuz/chromium@133.0.0 jquery@3.7.1
NODE_PATH=/tmp/siraj-browser/node_modules node tests/test_explorer_browser.js
```

Alternatively point `CHROME_PATH` at an installed Chromium. These tests do not replace a Frappe bench test, role/field-permission checks against the real database, scale testing, or a side-by-side visual and behavioral comparison with the original in Arabic and English.

## Missing legacy patch diagnostics

`patches.txt` references four migration modules that are absent even in the repository's initial commit. On a site with those patches pending, migration can fail; do not use `--skip-failing` or fabricate no-op migrations. On a backed-up site, an administrator can run the read-only diagnostic:

```bash
bench --site YOUR-SITE execute siraj_research.setup.patch_diagnostics.inspect_patch_log
```

This reports whether each named module exists and whether a non-skipped Patch Log entry exists. A completed log entry is **not** proof that its data transformation ran: normal fresh Frappe app installation marks patches completed without executing them. Safe remediation requires the historical schema, intended transformations and a representative backup, none of which are available in this checkout.

## Record titles

On normal saves, Person, Institution and Place derive `display_name` from the English name, falling back to Arabic; Event uses its English then Arabic title, Source uses its title, and Relationship uses the stored endpoint identifiers and type. Titles are trimmed to 140 characters. Existing records are **not** mass-updated by this change; they acquire a derived title on a later normal save, and the Explorer otherwise falls back to the record ID. If a site customizes field-level permissions, treat the derived `display_name` as exposing the corresponding source name/title fields and configure its permissions accordingly.
