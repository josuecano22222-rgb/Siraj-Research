# Original application: explorer parity and known gaps

Reference: `researchers-db` branch `arena/d114ff02-researchers-db`, including `app/static/js/views/geomap.js`, `map.js`, `structures.js`, `app/static/js/lib/maplib.js`, and `app/structures.py`. This is a feature comparison, not a claim that the original has been completely ported.

| Area | Original | Current Frappe app |
| --- | --- | --- |
| Geography | MapLibre, offline detailed Natural Earth pack, configurable online providers, three-zone workspace, filters, measurement and coordinate tools | Leaflet, local low-detail Natural Earth countries, opt-in OpenStreetMap, type icons, clustering, search, inspector, distance measurement, GeoJSON export |
| Offline | Local world pack, local vector/street packs and map-library features | No external internet needed for the local basemap; the Frappe server must be reachable. No offline street pack, persistent data cache or full offline client |
| Relationship atlas | Inspector and drill-in trail, orbit, force and matrix layouts, type/evidence/date filters | Force or large-graph grid, inspector, neighbor traversal, one-hop centered view and back, type/search filters; permissions enforced on server |
| Structures | Treemap, sunburst, sankey, matrix, circles and tree, fold-aware accounting and accessible table | Expandable tree and distribution bars with permission-visible counts and folded tails; the six original renderers and full controls are not yet implemented |
| Registry/military workflows | Source app's forms, imports, exports, workflows, maps and military modules | Native Frappe records, roles, reports and partial controllers; many source features remain to be implemented and validated |

Geographic and relationship results currently cap at 1,500 list-visible records per type. A truncation warning indicates that those diagrams do not describe the whole registry. Structure counts scan all permitted rows and fold wide tails without discarding their counts, but the synchronous scan can be slow on large datasets and is not a cross-request snapshot. All counts and diagrams are limited to what the current user may read.

## Tree navigation repair

The standard Frappe v15 tree view assumes a returned root and fails when the list is empty. SIRAJ's Place, Military Unit and Command Region tree views use a virtual root and a read-only, permission-checked child query over the explicitly declared parent fields. The view supports empty and multiple roots. Military Unit's New and Add child actions open the normal form, with the latter setting the parent ID; Place and Command Region remain navigation-only. Military Unit calculations now traverse parent links rather than nested-set indexes and reject cycles on save. Existing totals are not globally rebuilt, and concurrent hierarchy edits are not serialized. The views do **not** repair historic nested-set indices. A separately tested, backed-up migration is required before using nested-set calculations or rebuilding indices.

## Diagnostics still requiring site context

Socket.IO 502 is a bench realtime/proxy issue and cannot be diagnosed from browser status alone. Moment's warning requires identifying the malformed timestamp and its source. The `toTitle` error occurs inside Frappe's Create Card dialog and can occur if its numeric field is missing; the exact report and interaction should be verified before applying a targeted change. Modal `aria-hidden` focus warnings originate in framework modal behavior and also need a reproducible interaction. Do not edit Frappe framework files or disable security controls as a workaround.
