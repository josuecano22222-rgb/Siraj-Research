# SIRAJ Research — decision log

## 2026-11-16 — Representing connections for DocTypes not in Relationship endpoints

**Decision:** Use **option (b) — derive structural connections from ordinary Link fields**
(`parent_unit`, `unit_of_deployment`, `mission_of_deployment`, `place_of_event`,
`commander`, `linked_place`, etc.) and keep Relationship endpoint DocTypes as-is
(Person, Institution, Place, Research Event, Source). We do **not** extend
Relationship.subject_type/object_type Select options in this turn.

**Why:**
- Military Unit, Operational Deployment, Mission, Training Exercise, Command
  Region, Military Division and the administrative hierarchy (Governorate →
  District → Municipality → Village/Community) already encode their connections
  through ordinary Link fields. Adding them as Relationship endpoints would
  duplicate information that already has a single source of truth.
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
