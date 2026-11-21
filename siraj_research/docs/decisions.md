# SIRAJ Research — decision log

## 2026-11-18 — Advanced map search (coordinates, regions, places, records)

**Decision.** A single whitelisted endpoint (`api.map_search.search`) classifies each query four ways — exact coordinates (decimal verbatim, DMS via exact fractions with a one-click swap suggestion instead of silent guessing), admin regions (active boundary dataset first, hierarchy registry as fallback, deduped by pcode), gazetteer places, and the record pins the map already draws — ranked deterministically (pcode > exact > prefix > word > contains, coarser level first) with Arabic folding that mirrors the client filter rule-for-rule. The Explorer app panel hosts the widget; every jump popup shows stored coordinate strings, never a rounded rendering.

**Why.** Map search for this project is a precision instrument: a researcher pasting a coordinate needs the exact digits back, and a bilingual region query must not depend on which orthography the source used. One endpoint keeps scope/level/type filtering, ranking and permission checks in one testable place instead of four client-side lookups.

**Trade-offs.** Full folded scans of the gazetteer (~16k rows) run per debounced query — accepted at this data scale for correctness (SQL LIKE cannot fold both sides without schema changes); a `name_norm` column is the upgrade path if the atlas grows. The widget ships in its own JS file loaded by the Explorer rather than the bundle, so the app-scoped build stays BigInt-safe. Records are searched server-side even though the client already holds them, so the same endpoint serves list views later.

## 2026-11-18 — Person family fields (exclusive embedded rows)

**Decision.** Spouse, children, and grandchildren live as embedded fields and child tables on the Person record (`tab_family`); they never create or link to other Person DocTypes. Siblings alone may optionally link to an existing Person, because siblings are often subjects in their own right. A `Marital status` Select gates visibility: `Single` hides spouse/children/grandchildren sections (values are kept, not cleared), `Married` reveals them, and the Grandchildren section additionally requires the derived `is_grandparent` flag. A computed, stored `family_summary` line is added to `search_fields` so desk search reaches family names.

**Why.** Research notes are per-subject files; a family member with no dossier of their own must not force a hollow Person record, and hollow records would pollute search, tree, and coverage surfaces. Conditional display keeps the form quiet for single subjects without destroying evidence when status changes. The sibling link is opt-in so it can never break the rule for the other relations.

**Trade-offs.** Family members are invisible as Person records — cross-referencing a spouse who is themselves a subject requires typing their name into the parent's row (the optional sibling link covers only siblings). Conditional hiding can surprise users, mitigated by the dashboard comment and by server-side data preservation. The derived `family_summary` is a stored translation snapshot — it re-computes on every save, so its language follows the site at write time, not read time.

## 2026-11-17 — Settlement fallback: nearest Community, then village label

**Decision.** When the gazetteer chain has no settlement-level hit, the resolver falls back to the nearest **Community**-category locality within 5 km, returning its village-level label (`level = "village"`), `settlement_fallback = True`, `source = "gazetteer_community"`, `confidence = "low"`, `pcode = None`.

**Why.** The gazetteer's Community entries are often the only named settlement within reach; refusing them left points with only district hierarchy. The label and level are demoted honestly (a village-grade answer on low confidence, no pcode) so downstream consumers never mistake it for a confirmed settlement match.

**Trade-offs.** A Community nearest-neighbor can name a different village than a resident would — accepted at `low` confidence; the alternative (no settlement label at all) is worse for research notes. Fallback never fires when any chain rung already matched, and the gate asserts `settlement_fallback` is False whenever `settlement` is set the normal way.

## 2026-11-16 — Representing connections for DocTypes not in Relationship endpoints

**Decision:** Use **option (b) — derive structural connections from ordinary Link fields**
(`parent_unit`, `unit_of_deployment`, `mission_of_deployment`, `place_of_event`,
`commander`, `linked_place`, etc.) and keep Relationship endpoint DocTypes as-is
(Person, Institution, Place, Research Event, Source). We do **not** extend
Relationship.subject_type/object_type Select options in this turn.

**Why:**
- Military Unit (including Division-level rows via `echelon='Division'`),
  Operational Deployment, Mission, Training Exercise, and the Place hierarchy
  (Governorate → District → Municipality → Village/Community, plus command areas
  represented as Place records with `place_type="Command Region"`) already encode
  their connections through ordinary Link fields (`parent_unit`, `linked_place`,
  `parent_place`). Adding them as Relationship endpoints would duplicate
  information that already has a single source of truth.
- Derived edges are computed on-the-fly in `get_entity_network` and in the new
  `get_entity_profile` endpoint by walking DocType meta (the `fields` list).
  They are marked `structural: true` and rendered with a muted dashed style
  distinct from authored Relationships.
- If users later need free-form relationships to structural types (e.g. "Unit X
  informally supports Unit Y" without a parent_unit link), we can extend the
  Select idempotently via a reversible patch. That is deferred.

**Trade-offs:**
- (+) No schema migration now; existing .validate() chains (admin_chain,
  one-current-deployment, mission-deployment) continue to apply.
- (+) Structural edges stay in sync automatically with Link edits.
- (-) Structural edges do not carry Relationship metadata (type, evidence,
  start/end dates). They are presented under their own "Structural links"
  heading so users never confuse them with authored Relationships.

## 2026-11-16 — Filter-state single source of truth

**Decision:** A single engine-neutral `SirajFilters` module holds the filter
state (selected DocTypes, selected relationship types, statuses, date range,
provenance flags, search term, presets). The same reducer powers the Explorer
Geographic map, Relationship map, records panel, ego overlay and native Map
view. Server endpoints accept the same parameter shape so client toggling is
instant on cached data and server fetches use the same semantics.

## 2026-11-18 — v2.0.0 Phase 1: offline-first region & coordinate search

- **Coordinate answers carry the full geography.** `search()` with a parsed
  coordinate now returns `admin_chain` (resolved levels, bilingual, exact
  strings), `missing_levels` (explicit slugs — an ocean point reports all
  six, never an error), `on_land`, `nearest_place`, `provenance` and
  `nearby[]` (haversine, 1 dp, derived only — stored coordinates are never
  rounded or rewritten).
- **Hybrid means local-first.** `use_online=true` opts into the Nominatim
  fallback for the chain; v2.0.0 does not auto-create registry rows from
  external results (auto-fill stays `create_missing` against imported
  gazetteer/boundary data, via the existing `auto_fill_hierarchy` hook).
- **Viewport search is antimeridian-safe.** `search_bbox` accepts wrapping
  boxes (`min_lon > max_lon`) by splitting the SQL prefilter; region hits
  use bbox intersection or centroid containment.
- **The cascade is data, not guesswork.** `region_children` walks the
  registry's Link fields (Country → Community) with P-Code/centroid/bbox
  attached, so each selection flies to the polygon when the active dataset
  has it.

## 2026-11-18 — v2.0.0 Phase 2: onboarding tutorial design

- **Long-form lives in `docs/onboarding/`** — one Markdown file per step
  (README index + 01…10 + common-errors + quick-reference), each step
  bilingual (English then العربية): goal, prerequisites, field-by-field
  (meaning / required / format / common mistakes), worked example,
  validation checkpoint, link to next.
- **`Onboarding Step` records mirror the tutorial** (they are the in-app
  checklist): the existing seven records are kept and re-described to
  match the tutorials; seven new records cover places, organizations,
  military units, events, relationships, supporting data and search —
  14 steps total; the Module Onboarding steps list is reordered to the
  dependency order (workspace → settings → geo → dataset → steps 2–10 →
  quality close-out). `Open the SIRAJ
  workspace` stays as the "before you begin" entry and `Review data
  quality` as the closing loop — both have tutorial sections.
- **Import path (verified in frappe `model/sync.py`):** `bench migrate`
  walks `<app module>/onboarding_step/<slug>/<slug>.json` and
  `module_onboarding/…` through `IMPORTABLE_DOCTYPES` and upserts by name
  — so new/updated step records reach fresh installs and upgrades with
  no fixtures hook and no patch.
- **Language & roles are per-user, not Single fields:** the tutorial's
  step 1 teaches them via user profile (Language) and User → Role Profile
  (the four shipped SIRAJ roles), while `SIRAJ Settings`/`Geo Settings`
  cover defaults, offline data, map data and online-fallback policy.

## 2026-11-18 — v2.0.0 Phase 3: fictional demo dataset

- **Replaced the inherited demo content (PR #5).** The previous
  `setup/demo_data.py` was extensive but non-compliant: real persons
  (historical figures), real events, real institutions, no commands,
  no edge cases, no family showcase, uniform relationship confidence,
  and a teardown bug (Relationship `display_name` embeds series ids,
  never the `[DEMO]` tag — relationships were never removed). The
  spec requires *fictional only*; content was rewritten to match the
  spec volumes exactly (25/8/12/15/10/6 at 3 levels).
- **Split content from execution:** `setup/demo_content.py` is pure
  data (no frappe import) so CI can enforce volumes, the fictional
  guard (banned real names), edge cases, exact unrounded coordinates,
  confidence variety and teardown coverage via AST; `setup/demo_data.py`
  is the executor (idempotent `_add`, registry defence, provenance
  post-pass, manifest bookkeeping).
- **Precise removal:** load writes `siraj_demo_manifest.json` into the
  site folder (every created name); remove deletes the manifest first
  and falls back to a `[DEMO]` tag sweep (which also cleans legacy
  builds). Units are deleted deepest-first because `MilitaryUnit.on_trash`
  refuses parents with subordinates; non-demo dependents block deletion
  and are reported, never force-removed.
- **Bench surface:** `commands.py` exposes the frappe-required
  `commands` iterable → `bench --site <site> siraj-research
  load-demo-data | remove-demo-data | isolate-demo-data`.
- **Showcases:** master source cited by every record + one Evidence row
  per claim-bearing record; 24 relationships exercising all six
  confidence codes; 36 link-table rows (person↔org, person↔event via
  Siraj Events, event↔location incl. the open-water station); 3-level
  unit tree with derived subtree personnel; family tab (married +
  grandchildren + `is_grandparent`, and an explicit Single); edges:
  coords-only auto-fill place, country-only missing-levels place,
  ocean point at exactly `31.6, 33.8`, `circa 1947`/`1960s`/`uncertain`
  dates.
