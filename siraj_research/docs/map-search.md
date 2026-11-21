# Advanced map search

One box on the SIRAJ Explorer geographic map answers four questions at once: **is this text a coordinate, does it name a region, a gazetteer place, or a mapped research record?** The widget sits at the top of the map's app panel (scope + region-level selectors included) and every result flies the map to it with an exact-coordinate popup.

## Precision contract

Coordinates are the point of the feature, so the rules are strict:

* **Decimal input is verbatim.** `31.5900000000000001, 34.47` leaves the server as the same digits it arrived with — never through `float()` on the way out, never `toFixed()` on the way in. The popup shows the string as stored.
* **DMS input is exact rational arithmetic.** `31°35'24.5"N 34°28'11.92"E` converts through `Fraction` (denominator divides 3600·10ᵏ), emitted as a 28-significant-digit decimal **and** the reduced fraction (`227449/7200`) — nothing from the input is lost. Arabic digits (`٣١°٣٥'٢٤٫٥"ش`) and Arabic hemisphere letters (ش/ج/ق/غ) are accepted.
* **Ambiguity is never guessed.** A bare number is not a coordinate. A minus sign that fights the hemisphere letter is an error, not a silent override. `100.2, 34.47` (longitude pasted first) is rejected **with a one-click suggestion** — swapped, flagged, never applied silently.
* **Rendering is the only place floats appear.** Leaflet needs numbers to move the viewport; popups, status lines and exports keep the strings.

Accepted formats: `lat, lon` · `lat lon` · `lat; lon` · hemisphere suffixes (`31.5N, 34.4W`) · full DMS (`d° m' s" H`) · letter forms (`31d35m24.5sN`) · Arabic-Indic digits.

## What each scope searches

| Scope | Source | Matched fields | Jump |
|---|---|---|---|
| **Regions** | Admin Boundary rows (active dataset first) + the hierarchy registry (Country → Community) + ERPNext Country | `name_en`, `name_ar`, `local_name`, `label_en`, `label_ar`, `pcode` | bbox → `fitBounds` with a dashed rectangle; else centroid → fly; popup carries level, pcode, dataset and the parent chain |
| **Places** | Gazetteer Place (active dataset first) | `name_en`, `name_ar`, `asciiname`, `pcode` | fly to point; popup shows bilingual name, feature code, pcode, exact coordinates |
| **Records** | The same GEO_TYPES pins the map already draws (Person, Institution, Place, Research Event, Military Unit, Operational Deployment) | title field (`display_name`/`unit_name`/…) | fly; popup has the exact stored point and an **Open record** button |
| **Coordinates** | Parsed server-side (above) | — | fly to zoom 16, precision dot, exact strings + DMS rendering + a **Resolve hierarchy** button that calls the shipped `geo_resolve.resolve_point` for the full six-level chain |

`levels=0..5` filters regions; `types=` filters records; `limit` caps each group (max 25).

## Ranking (deterministic)

`pcode exact (1000) > name exact (900) > prefix (700) > word-start (600) > contains (400)`, ties broken by **coarser region level first**, then folded name. Name folding mirrors the client filter rule-for-rule: diacritics off, alef variants unified (أ إ ٱ آ → ا), ta marbuta → ha, ya → alef maqsura — so a query typed as `غزه` finds `غزة`.

## Endpoints & files

* `siraj_research.api.map_search.search(query, scope, levels, types, limit)` — whitelisted; permission-aware reads (`get_list` role checks for the geo tables, `readable_rows` document checks for records).
* `siraj_research/utils/map_search.py` — pure core: parsing, folding, ranking (root-testable, no Frappe).
* `siraj_research/public/js/siraj-map-search.js` — widget + pure helpers (Node-testable).
* Explorer integration: `siraj_explorer.js` geographic view, `css/siraj-map-search.css`.

## Testing

* Root: `tests/test_map_search.py` (31 cases: exactness, DMS fractions, errors, folding, ranking) and `tests/test_map_search_ui.js` (widget helpers; wired into CI's node list).
* Bench: `bench --site frappe.com run-tests --module siraj_research.tests.test_map_search_api` — endpoint surface, exact payloads, gazetteer self-match smoke test.
