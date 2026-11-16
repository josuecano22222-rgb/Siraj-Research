# Original application: explorer parity and known gaps

Reference: `researchers-db` branch `arena/d114ff02-researchers-db`, including `app/static/js/views/geomap.js`, `map.js`, `structures.js`, `app/static/js/lib/maplib.js`, and `app/structures.py`. This is a feature comparison, not a claim that the original has been completely ported.

| Area | Original | Current Frappe app |
| --- | --- | --- |
| Geography | MapLibre, detailed local Natural Earth pack, configurable providers, three-zone workspace, filters, measurement and coordinate tools | Leaflet, low-detail local countries and optional OSM, three zones, clustering, filters, temporary DD coordinate entry, approximate measurement, relationship lines and GeoJSON export; many providers, overlays and coordinate features differ or are missing |
| Offline | Local world pack, local vector/street packs and map-library features | No external internet needed for the local basemap; the Frappe server must be reachable. No offline street pack, persistent data cache or full offline client |
| Relationship atlas | Inspector and drill-in trail, multi-distance orbit, force and matrix layouts, type/evidence/date filters, SVG export | In-place inspector, neighbor traversal, one-to-three-hop centered view, multi-ring orbit, force/grid and matrix, type/end-date/evidence filters back through centers and SVG export; full original dossier and original trail behavior are not implemented |
| Structures | Six layouts, fold-aware accounting, table, drilldown, hierarchy/composite military sources and extensive controls | Six layouts over a common permission-visible tree, folded tails, record leaves, mixed region/unit and unit/operation sources, depth/search/keyboard controls, table, zoom and exports; original controls and some source semantics remain missing, and appearance is not verified as identical |
| Registry/military workflows | Source app's forms, imports, exports, workflows, maps and military modules | Native Frappe records, roles, reports and partial controllers; many source features remain to be implemented and validated |

All three Explorer data sets scan permission-visible records without the old 1,500-record cap. Counts and diagrams are restricted to what the user may read. Large synchronous scans and full client-side graph/map rendering require representative scale testing; concurrent edits can change results during paging. Original and Frappe schemas and permission systems differ. The implementation has passed mock and synthetic Chromium tests but has not been tested in a live Frappe bench or visually verified against the source at matching viewport, language, data and theme. Do not describe it as an identical port.

## Critical Frappe Event collision

SIRAJ's `Event` DocType uses the same global name as Frappe's calendar `Event`. A live sample insert failed in Frappe's Google Calendar hook because the SIRAJ schema lacks its calendar field. Other calendar behavior and existing records may also be affected. Sample insertion is paused before writes; the name conflict requires a non-destructive, separately tested schema/data migration and live verification, not a hidden hook bypass. See [test-data.md](test-data.md) for read-only diagnostics. Do not assume reinstall or migration is safe until this is resolved.

## Tree navigation repair

The standard Frappe v15 tree view assumes a returned root and fails when the list is empty. SIRAJ's Place, Military Unit and Command Region tree views use a virtual root and a read-only, permission-checked child query over the explicitly declared parent fields. The view supports empty and multiple roots. Military Unit's New and Add child actions open the normal form, with the latter setting the parent ID; Place and Command Region remain navigation-only. Military Unit calculations now traverse parent links rather than nested-set indexes and reject cycles on save. Existing totals are not globally rebuilt, and concurrent hierarchy edits are not serialized. The views do **not** repair historic nested-set indices. A separately tested, backed-up migration is required before using nested-set calculations or rebuilding indices.

## Diagnostics still requiring site context

Socket.IO 502 is a bench realtime/proxy issue and cannot be diagnosed from browser status alone. Moment's warning requires identifying the malformed timestamp and its source. The `toTitle` error occurs inside Frappe's Create Card dialog and can occur if its numeric field is missing; the exact report and interaction should be verified before applying a targeted change. Modal `aria-hidden` focus warnings originate in framework modal behavior and also need a reproducible interaction. Do not edit Frappe framework files or disable security controls as a workaround.
