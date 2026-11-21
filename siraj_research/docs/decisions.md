# SIRAJ Research — decision log

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
