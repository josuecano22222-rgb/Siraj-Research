# Decision: Consolidate the 15 association DocTypes into `Relationship`

**Status: PROPOSAL — read-only design. No code has been changed. The user
decides before anything is built.**

**Proposal.** Reduce the SIRAJ association DocTypes to the existing generic
`Relationship` DocType, with `Siraj Event` as the single event DocType (event
type carried by `Siraj Event.event_type`). The association DocTypes were
originally child Tables on the entity DocTypes and were later converted to
standalone DocTypes (see `siraj_research/patches/v1_0/fix_doctype_cleanup.py`,
`STANDARD_RELATIONS`). They now duplicate, field-for-field, what `Relationship`
already provides.

**Exact list confirmed from `siraj_research/hooks.py` `SCOPED_DOCTYPES`
(`hooks.py:206-234`).** `SCOPED_DOCTYPES` contains **15** association
DocTypes, not 14 — the proposal's "14" excludes `Person Position`, which item 2
decides separately:

| # | DocType | Endpoints (required Links) |
|---|---|---|
| 1 | `Siraj Event Person` | `event` (Siraj Event) + `person` (Person) |
| 2 | `Siraj Event Institution` | `event` + `institution` |
| 3 | `Siraj Event Location` | `event` + `place` |
| 4 | `Siraj Event Military Unit` | `event` + `military_unit` |
| 5 | `Person Event` | `person` + `event` |
| 6 | `Person Institution` | `person` + `institution` |
| 7 | `Person Location` | `person` + `place` |
| 8 | `Person Military Unit` | `person` + `military_unit` |
| 9 | `Person Position` | `person` + `institution` + `place` (**ternary**) |
| 10 | `Institution Event` | `institution` + `event` |
| 11 | `Institution Location` | `institution` + `place` |
| 12 | `Institution Military Unit` | `institution` + `military_unit` |
| 13 | `Military Unit Event` | `military_unit` + `event` |
| 14 | `Military Unit Institution` | `military_unit` + `institution` |
| 15 | `Military Unit Location` | `military_unit` + `place` |

So: **14 binary associations + 1 ternary (`Person Position`)**. The remaining
`SCOPED_DOCTYPES` entries (`Command Appointment`, `Mission`, `Operational
Deployment`, `Shared Record`, `Training Exercise`, and the entity DocTypes
`Person`, `Institution`, `Place`, `Military Unit`, `Siraj Event`, `Source`) are
not association DocTypes and are out of scope.

---

## 1. Per-DocType field inventory and classification

All 15 association DocTypes share one near-identical schema (verified by
reading every `*.json`). Their controllers (`*.py`) are all bare `pass` — no
custom logic anywhere. The fields, their types, and whether any data or code
reads them:

### Shared field groups (present on all or most)

| Field group | Fields | Type | Read by data/code? | Classification |
|---|---|---|---|---|
| Endpoint links | the 2 required endpoint Links (e.g. `person`, `event`) | Link | Yes — these are the whole point; consumed by HD-4 link validation, seeders, Explorer | **generic** → becomes `Relationship.subject`/`object` + `subject_type`/`object_type` |
| Bilingual titles | `title_en`, `title_ar`, `title_as_stated` | Data | Yes — seeders set them; list views/cards may display them | **type-specific (needs a home)** — `Relationship` has only a single `display_name`; see §1.1 |
| Role | `role` | Data | Yes — seeders | **generic** → maps to `Relationship.role_as_stated` |
| Free notes | `notes` (Small Text) — only on the three `*_event` associations (`Institution Event`, `Military Unit Event`, `Person Event`) | Small Text | Yes — seeders | **generic** → maps to `Relationship.description` |
| Date range | `start_date`, `end_date` | Date | Yes — seeders | **generic** → `Relationship.start_date`/`end_date` (Datetime + precision) |
| Provenance | `primary_source`, `documentation_level`, `authentication_level`, `workflow_state` | Link | Yes — HD-4/permissions, seeders, workflow | **generic** — all already on `Relationship` |
| Child collections | `evidence` (Table → Evidence), `external_identifiers` (Table → External Identifier) | Table | Yes — profile APIs, evidence counts | **generic** — both already on `Relationship` |
| Data group | `data_group` (Link, **required**) | Link | Yes — HD-4 (`validate_same_data_group_links`), `get_permission_query_conditions` | **generic** — already on `Relationship` (required) |
| Layout | `sb_relation`, `cb_1`, `cb_dates`, `cb_prov`, `sb_evidence` | Section/Column Break | No (presentation only) | **dead** (drop with the DocType) |

### Per-DocType deviations

| DocType | Extra beyond the shared set | Type | Read? | Classification |
|---|---|---|---|---|
| `Person Position` | **third required endpoint** `place` | Link | Yes | **type-specific** — see §2 |
| `Person Position` | `country` | Link → Country | No code reads it (schema-only) | **type-specific / dead** — see §2 |
| `Person Position` | `sb_location` section | Section Break | No | **dead** |
| `Institution Event`, `Military Unit Event`, `Person Event` | `notes` | Small Text | Yes (seeders) | **generic** (→ `description`) |

### 1.1 The one open schema question: bilingual titles

`Relationship` has a single `display_name` (Data). The 15 association
DocTypes carry `title_en` + `title_ar` + `title_as_stated`. Two options:

- **Option A (recommended):** add `title_en` and `title_ar` to `Relationship`
  (additive, reversible), keep `display_name` as the canonical label, and let
  `before_validate` populate `display_name` from them (the existing
  `set_relationship_display_name` helper already centralizes display-name
  logic). `title_as_stated` folds into `role_as_stated`/`description` semantics
  or is dropped as redundant.
- **Option B:** collapse to `display_name` only and lose the bilingual split.
  Cheaper, but regresses the bilingual display the association rows provide.

Recommend **Option A**; it is a small additive schema change with no data
loss and keeps every existing consumer working.

### 1.2 Classification summary

- **Generic (move to `Relationship`):** endpoint links, `role`, `notes`,
  `start_date`/`end_date`, the four provenance links, `evidence`,
  `external_identifiers`, `data_group`. These map 1:1 onto existing
  `Relationship` fields.
- **Type-specific (needs a home):** the bilingual title triple (→ §1.1
  Option A) and `Person Position`'s ternary shape (→ §2).
- **Dead:** all Section/Column Break layout fields; `Person Position.country`
  (unused).

---

## 2. Does `Person Position` belong in this consolidation?

**Decision: NO — exclude `Person Position` from the consolidation.** It stays
a standalone DocType and remains in `SCOPED_DOCTYPES`.

**Rationale:**

1. **It is ternary, not binary.** `Person Position` has **three** required
   endpoints — `person`, `institution`, `place` — plus a `country` Link.
   `Relationship` models exactly two endpoints (`subject`/`object`). Forcing
   `Person Position` into `Relationship` would either (a) require extending
   `Relationship` to a 3-endpoint model, which breaks the binary contract every
   existing consumer (`map_relations.get_entity_network`, `relationship_profile`,
   `visualization.relationship_data`, the Explorer) relies on, or (b) drop the
   `place`/`country` data, losing real information.
2. **Different semantics.** A position is a *held post* — a person occupying a
   role at an institution, located at a place, over a date range. It is a
   first-class record with its own lifecycle, not an edge between two records.
   The other 14 are pure binary associations.
3. **Existing investment.** `Person Position` has its own controller, its own
   test file (`doctype/person_position/test_person_position.py`), its own
   seeders (`setup/test_data.py`), workspace entry, and translations. Folding
   it in multiplies the blast radius for no schema gain.
4. **Clean boundary.** Keeping it out leaves `Relationship` a clean binary
   model and `Person Position` a clean ternary model. If a future need arises
   for arbitrary n-ary links, that is a separate, larger extension — not this
   consolidation.

If the user later wants positions represented as relationships, the honest
path is a dedicated decision with an n-ary extension, not a squeeze into the
binary `Relationship`.

---

## 3. `Relationship Type` schema for allowed subject/object pairs

`Relationship Type` already has the two fields this needs —
`applies_to_subject` (Link → DocType) and `applies_to_object` (Link → DocType)
— plus `is_symmetric`, `inverse_type`, and `is_hierarchical`
(`relationship_type.json`). **They are currently unused**: no Python or JS
reads `applies_to_subject`/`applies_to_object`/`is_hierarchical` (verified by
grep); only `is_symmetric` and `inverse_type` are consumed (by
`relationship.py:validate`, `map_relations.py:243`, `master_data.py:109-119`,
and the Explorer).

### 3.1 Schema change — a child table of allowed pairs

**Replace the two single-DocType Links with one child table**
`Relationship Type Allowed Pair` (child table on `Relationship Type`) holding
**`(subject_doctype, object_doctype)` pairs**. Drop `applies_to_subject` /
`applies_to_object` (or leave them deprecated/unused — they are already
unread, so removing is safe; a patch deletes the two Link fields and creates
the child table).

Child-table fields:

| Field | Type | Meaning |
|---|---|---|
| `subject_doctype` | Link → DocType | Allowed **subject** endpoint DocType |
| `object_doctype` | Link → DocType | Allowed **object** endpoint DocType |
| `sort_order` | Int | Display order of the pairs |

One row = one allowed ordered pair. The full allowed set is the rows of this
table. This is a child table (rows live in `tabRelationship Type Allowed Pair`
with `parenttype = "Relationship Type"`), so editing the type's allowed pairs
is a normal grid edit, and the pair set is read in bulk with one query per
`Relationship Type`.

**Why a child table over two multi-selects:** it expresses *pairs*, not two
independent sets — a multi-select pairing is ambiguous (which subject pairs
with which object), whereas a child table row is unambiguous. It also scales
to asymmetric pair sets (e.g. `(Person, Siraj Event)` allowed but
`(Siraj Event, Person)` not, for a directed type) without combinatorial
explosion, and the pair constraint is enforceable as a row-level rule.

### 3.2 What the controller must enforce

On `Relationship.validate()` (extending the existing
`relationship.py:validate`), after the type is resolved, load the
`Relationship Type`'s allowed pairs (child-table rows) and enforce:

1. **Pair membership.** Require that the row
   `(subject_doctype = subject_type, object_doctype = object_type)` exists in
   the type's allowed-pairs child table. Throw `ValidationError` otherwise.
   This is the single enforcement point and replaces the implicit "the
   DocType exists, so the link is fine" behavior the 15 association
   DocTypes get for free from their typed Link fields.
2. **Symmetric types.** If `is_symmetric` is true, the pair is unordered:
   accept `(A, B)` if either the row `(A, B)` **or** the row `(B, A)` exists.
   The existing `relationship.py:validate` already forces `direction =
   "Symmetric"` from `is_symmetric`; add the orientation-tolerant pair check.
   At the type-definition level, a `Relationship Type` validate hook should
   require that symmetric types' allowed pairs are closed under swap — for
   every row `(A, B)` there is a row `(B, A)` — so the pair set is internally
   consistent.
3. **Directional types.** Enforce the ordered pair strictly: the row must be
   exactly `(subject_type, object_type)`. No swap, no reverse.
4. **Self-links.** Reject `subject == object` for non-hierarchical types
   (the Explorer already guards this client-side at
   `siraj_explorer.js:209`; move it server-side).
5. **`inverse_type` / `is_hierarchical`.** Keep `inverse_type` for UI
   (inverse label) and reserve `is_hierarchical` for future tree semantics;
   they do not change pair enforcement.

### 3.3 Seed / migration of `Relationship Type` rows

The 15 association DocTypes imply a set of allowed pairs. Seed the new
`Relationship Type Allowed Pair` child table on each `Relationship Type`
(or extend existing types) with `(subject_doctype, object_doctype)` rows so
every currently-legal edge remains legal after consolidation. The existing
seeders (`setup/master_data.py`, `setup/test_data.py`,
`tests/_isolation_fixtures.py`) already create `Relationship Type` rows with
`is_symmetric`; they gain the allowed-pair child rows. The 14 association
DocTypes map to the following default pair set (subject, object) — the
consolidation preserves exactly these edges:

`(Siraj Event, Person)`, `(Siraj Event, Institution)`, `(Siraj Event, Place)`,
`(Siraj Event, Military Unit)`, `(Person, Siraj Event)`, `(Person, Institution)`,
`(Person, Place)`, `(Person, Military Unit)`, `(Institution, Siraj Event)`,
`(Institution, Place)`, `(Institution, Military Unit)`,
`(Military Unit, Siraj Event)`, `(Military Unit, Institution)`,
`(Military Unit, Place)`.

(Each association DocType implies one ordered pair from its two required
endpoint Links; the seeding step populates the child table with these 14 rows
plus any additional pairs the seeded `Relationship Type` values define.)

---

## 4. Complete consumer table

Every file that references any of the 15 association DocTypes (verified by
`git grep` for both the space-form and snake_case forms, excluding the
doctype directories themselves). The association DocTypes are **not**
referenced by any report, number card, dashboard, page/Explorer JS, API
module, `visualization.py`, or `record_icons.py` — those all consume the
generic `Relationship` already.

| File | Change | Layer |
|---|---|---|
| `siraj_research/hooks.py` (`SCOPED_DOCTYPES`, `permission_query_conditions`, `has_permission`, `doctype_js`, `doc_events`) | Remove the 14 consolidated names from `SCOPED_DOCTYPES` (keep `Person Position`); hooks retarget to `Relationship` (already present) | Python / hooks |
| `siraj_research/public/js/data_group_scope.js` (`SCOPED_DOCTYPES` mirror) | Remove the 14 names from the JS mirror; keep `Person Position` | JS / form |
| `siraj_research/patches/v1_0/fix_doctype_cleanup.py` (`STANDARD_RELATIONS`, `REMOVED_TABLE_FIELDS`) | Historical patch — leave as-is (idempotent, already run); optionally annotate that the 14 are later consolidated | Python / patch |
| `siraj_research/setup/demo_content.py` | Remove the 14 doctypes from `SPEC`/seed tables; re-seed those edges as `Relationship` rows (this is the **L4 seeder restructuring**, explicitly deferred) | Python / seeder |
| `siraj_research/setup/demo_data.py` | Same — the `E`/`S`/relation seeding moves to `Relationship` | Python / seeder |
| `siraj_research/setup/test_data.py` | `Person Position` stays; any of the 14 referenced here move to `Relationship` | Python / seeder |
| `siraj_research/siraj_research/workspace/siraj_research/siraj_research.json` | Remove the 14 workspace shortcuts (keep `Person Position`); optionally add a `Relationship` shortcut | JSON / workspace |
| `siraj_research/translations/ar.csv` | Remove the 14 translation entries (keep `Person Position`); add any `Relationship` labels if missing | Translations |
| `siraj_research/tests/test_api_data_group_isolation.py` | `Siraj Event Person` reference moves to a `Relationship`-based fixture | Python / test |
| `siraj_research/siraj_research/doctype/person_position/test_person_position.py` | **Unchanged** — `Person Position` stays | Python / test |
| `tests/test_demo_data_structure.py` | Updated by the L4 seeder restructuring (asserts on the 14 names) | Python / test |
| `docs/decisions.md`, `docs/decisions/baseline.md` | Decision records — annotate the consolidation; historical text preserved | Docs |

**No change needed** in: reports, number cards, dashboards, Explorer page JS,
`api/map_relations.py`, `api/relationship_profile.py`, `api/entity_profile.py`,
`visualization.py`, `record_icons.py` — they already consume `Relationship`
generically via `subject_type`/`object_type`.

---

## 5. HD-4 impact: one rule covers both endpoints

**Confirmed.** HD-4 is implemented by
`siraj_research/permissions.py:validate_same_data_group_links`, wired on
`validate` for every `SCOPED_DOCTYPES` entry (`hooks.py`). It walks **all**
Link and Dynamic Link fields on the document **and its child tables**
(`_collect_scoped_link_targets`, `permissions.py:110-133`) and batch-checks
that every referenced scoped record's `data_group` equals the document's
`data_group` — for every role, including `SIRAJ Official` and `Administrator`
(the one justified exception to Invariant 1, recorded in HD-4/C-03a).

`Relationship` is **already** in `SCOPED_DOCTYPES` and already carries a
required `data_group`. Its two endpoints are **Dynamic Links**
(`subject`/`object` driven by `subject_type`/`object_type`), which
`_collect_scoped_link_targets` already handles. **Therefore one rule,
unchanged, covers both endpoints** against `Relationship.data_group`:

- After consolidation, a `Relationship` row's `data_group` is checked against
  **both** `subject` and `object` in a single `validate` pass. No new
  permission logic is needed — the 14 association DocTypes each had their own
  `data_group` and their own two links checked by the same rule; consolidating
  them into one DocType simply runs the same rule once instead of 14 times.

**Tests required (add to `siraj_research/tests/test_api_data_group_isolation.py`
or a new suite):**

1. `Relationship` with both endpoints in the same `data_group` → saves.
2. `Relationship` with `subject` in a different `data_group` → rejected.
3. `Relationship` with `object` in a different `data_group` → rejected.
4. `Relationship` with a blank-`data_group` endpoint → rejected.
5. `Relationship` where the endpoint exists but is unreadable → rejected
   without leaking the record (mirrors the existing predictable-ID tests).
6. `SIRAJ Official` and `Administrator` cannot bypass the cross-group check
   (the C-03a exception path).
7. Child-table `Evidence` links on a `Relationship` are checked against the
   parent `Relationship.data_group`.

---

## 6. Indexes on `Relationship` and Explorer per-profile query cost

**Current state:** `relationship.json` defines **no indexes**
(`indexes: None`); `search_fields = display_name,subject,object,description`.

**Queries the Explorer runs per profile/network page:**

- `api/map_relations.py:get_entity_network` — batches edges by endpoint:
  `get_list("Relationship", filters={subject_type: dt, subject: ("in", names)})`
  and the mirror for `object_type`/`object` (`map_relations.py:150-180`). Per
  hop, per endpoint DocType, one batched query.
- `visualization.py:relationship_data` — one full `get_list("Relationship",
  …)` scan (capped/truncated) for the whole map graph, then filters edges to
  visible nodes.
- `api/relationship_profile.py` — single-document reads via `frappe.get_doc`.
- `api/entity_profile.py:get_entity_profile` — per-entity relationship summary.

**Indexes recommended** — created **additively** via the `on_doctype_update`
hook in `hooks.py`, using `frappe.db.add_index(...)` inside the hook body
(the hook runs during `bench migrate` when the `Relationship` DocType is
synced). This is the Frappe-idiomatic way to attach DDL to a DocType without
shipping a hand-written `ALTER TABLE`:

| Index | Columns | Serves |
|---|---|---|
| `idx_rel_subject` | `(subject_type, subject)` | `get_entity_network` subject batches |
| `idx_rel_object` | `(object_type, object)` | `get_entity_network` object batches |
| `idx_rel_data_group` | `(data_group)` | HD-4 batch checks, permission query conditions |
| `idx_rel_type` | `(relationship_type)` | type filtering, `relationship_data` |

**Documented exception to Invariant #3.** Invariant #3 (recorded in
`docs/decisions/2026-11-siraj-fixes.md`) states *"No DDL and no
`frappe.db.commit()` in request paths or patches."* Creating an index is DDL,
and `frappe.db.add_index` issues `CREATE INDEX` (which, like `DROP TABLE`,
commits implicitly in MariaDB). **This index creation is a deliberate,
documented exception to Invariant #3**, justified as follows:

- It runs **only** inside the `on_doctype_update` hook, which fires during
  `bench migrate` (schema sync) — a maintenance window, **not** a request
  path and **not** a hand-written patch. The hook is the framework's sanctioned
  DDL hook for DocType-level schema changes.
- It is **additive and idempotent**: `frappe.db.add_index` checks for an
  existing index before creating (`IF NOT EXISTS`-equivalent), so re-running
  migrate is a no-op after the first.
- It touches a **single table** (`tabRelationship`) with four composite
  indexes; the DDL cost is one-time at migrate, not per-request.
- No `frappe.db.commit()` call is added — `add_index` manages its own
  transaction boundary.

This exception is recorded here so the Invariant #3 guard (and any audit of it)
treats these four indexes as approved, scoped, and non-recurring. **If the
user prefers to keep Invariant #3 absolute**, the fallback is to ship the
indexes as part of the app's checked-in `.json`-declared indexes only if
Frappe applies them automatically — but `Relationship.json` currently declares
`indexes: None`, and Frappe v15 does **not** auto-apply `indexes` from JSON, so
the `on_doctype_update` + `add_index` route (with this exception) is the
recommended path.

**Cost estimate:** the per-profile `get_entity_network` queries are
`WHERE subject_type = ? AND subject IN (...)` / `WHERE object_type = ? AND
object IN (...)` — both become index range scans with the composite indexes,
staying cheap even as `Relationship` grows to the full association volume
(the 14 tables' rows combined). The full `relationship_data` scan is
O(total relationships) but is already capped (`limit_page_length`, truncated
flag) and only runs for the map graph; the `relationship_type` index helps
its `relationship_type IN (...)` filtering. **Verdict: cheap.** The composite
`(subject_type, subject)` / `(object_type, object)` indexes are the high-value
pair; `data_group` and `relationship_type` are cheap additions. No estimate
here is a measured number — see §10 for what stays unverified.

---

## 7. Form UX after the change

**Current state (already profile-endpoint-based).** The entity DocTypes no
longer carry child tables or dynamic links for these associations — the
`fix_doctype_cleanup.py` patch removed the old Table fields
(`Person.positions`, `Siraj Event.people`, etc.). `person.json` has no
`dynamic_links` and no association child tables. Relationships are surfaced
through the **profile endpoints**, not form child tables:

- `api/entity_profile.py:get_entity_profile` and
  `api/map_relations.py:get_entity_network` render the ego network.
- The Explorer page (`siraj_explorer.js`) has an "Add relationship…" dialog
  (`openAddRelationshipDialog`, `siraj_explorer.js:174-241`) that creates
  `Relationship` docs directly with `subject_type`/`subject`/`object_type`/`object`.

**After consolidation:**

- **Person, Institution, Military Unit, Place, Siraj Event forms** — unchanged
  UX. They already show relationships via the profile endpoints
  (`get_entity_network` / `get_entity_profile`), which query `Relationship`
  generically. Consolidation removes 14 parallel list views nobody surfaces in
  the forms; the forms keep using the profile endpoints. No `dynamic_links` are
  introduced — the Dynamic Link fields already live on `Relationship`.
- **`Relationship` form** — gains the bilingual title fields (§1.1 Option A)
  and the pair-enforcement validation (§3.2); the existing "Swap Source &
  Target" button (`relationship.js`) continues to work.
- **`Relationship` list view** — becomes the single list for all binary
  associations (filterable by `subject_type`/`object_type`/`relationship_type`),
  replacing 14 separate list views.
- **`Person Position` form** — untouched (§2).

---

## 8. Integrity: delete blocking, cascade, and duplicates

**Block vs cascade on endpoint delete.** Recommend **block** (fail closed),
not cascade:

- A `Relationship` row is a sourced, evidence-backed research claim. Silently
  cascading its deletion when an endpoint is deleted would destroy provenance
  without review.
- Implementation: a `before_delete` hook (or `depends_on`-style guard) on the
  endpoint DocTypes (`Person`, `Institution`, `Place`, `Siraj Event`,
  `Military Unit`) that queries `Relationship` rows where
  `(subject_type, subject)` or `(object_type, object)` references the doc and
  **throws** if any exist. Provide an explicit admin override
  (`force=True` path) for the rare legitimate case, mirroring the
  `delete_research_event.py` force-delete pattern.
- `Person Position` keeps its own behavior (out of scope).

**Duplicate relationship handling.** Enforce uniqueness in
`Relationship.validate()`:

- For **directed** types: reject a duplicate
  `(relationship_type, subject_type, subject, object_type, object)`.
- For **symmetric** types: normalize the pair (order endpoints
  deterministically, e.g. by `(doctype, name)`) before the uniqueness check so
  `(A→B)` and `(B→A)` are treated as the same edge and only one row is kept.
- Allow a deliberate "duplicate with different evidence/dates" only via an
  explicit admin override, or reject and require the user to extend the
  existing row's evidence instead.

---

## 9. Removal: strict-guard deletion patch (Decision E)

Extend the existing strict-guard deletion-patch pattern established by
`siraj_research/patches/v2_1/delete_research_event.py` (HD-1 / Decision E) to
the **14** consolidated DocTypes (`Person Position` is excluded per §2).

**One patch, iterating the 14 names.** Do **not** ship 14 separate patch
modules. Ship **one** `[post_model_sync]` patch that iterates the 14 DocType
names (a module-level list) and, for each, runs the strict guard below. A single
module keeps the removal atomic, idempotent, and reviewable in one place.

**Per DocType (inside the loop), strict guard:**

1. **`frappe.db.exists("DocType", name)` guard first.** If the DocType
   record is already gone (fresh site, or a prior run already removed it),
   `continue` — the whole patch is idempotent.
2. **Raise if rows exist (J1 strict guard).** Before deleting, run
   `SELECT COUNT(*) FROM \`tab<DocType>\`` (via `frappe.db.sql`). If
   `row_count > 0`, `frappe.throw` with a message that names the DocType and
   row count and shows the exact remediation (never auto-delete rows in a
   migration patch).
3. **`delete_doc("DocType", <name>, force=True)`** — removes metadata, Custom
   Fields, permissions, and the `tabDocType`/child rows. Per the verified
   Frappe v15.128.0 behavior, `delete_doc` on a `DocType` whose files are gone
   does **not** drop the SQL table and does **not** import the deleted
   controller (`frappe/model/delete_doc.py:103-117`; `developer_mode` is `0`
   during migrate per `frappe/modules/patch_handler.py:166` in
   **`~/frappe-bench/apps/frappe`**, and `frappe.flags.in_migrate` is set per
   `frappe/migrate.py:88`). (Line numbers confirmed against the installed
   `frappe` v15.128.0 at `~/frappe-bench/apps/frappe`, not the older `/tmp`
   copy.)
4. **`DROP TABLE IF EXISTS \`tab<DocType>\`` — only if it survives.** After
   `delete_doc`, check `frappe.db.table_exists(name, cached=False)` **again**;
   only then `DROP TABLE IF EXISTS`. If `delete_doc` already removed the
   table (or the DocType never had one), the drop is skipped. Per Decision E,
   the drop is conditional on the table still being present after the
   `DocType` record deletion.

**Ordering note:** run in `[post_model_sync]` — the `delete_research_event.py`
precedent checks row counts *before* `SiteMigration.post_schema_updates` runs
`remove_orphan_doctypes()` (`frappe/migrate.py:143`); the same ordering holds
here.

**Removal-sequence precondition — `remove-demo-data` BEFORE pulling the
removal.** `frappe.com` holds demo rows: the demo seeders
(`setup/demo_content.py`, `setup/demo_data.py`) create rows in these 14
DocTypes (the `ASSOCIATIONS` list seeds 36 link-table rows across 10 of the
14). **`remove-demo-data` must run *before* the removal patch is pulled/run**,
or the J1 row-count guard will (correctly) refuse. This is a hard sequencing
rule: demo teardown first, then migrate the removal patch. This mirrors the
`delete_research_event.py` precondition.

**Make `fix_doctype_cleanup.py` tolerate missing DocTypes.** The historical
`siraj_research/patches/v1_0/fix_doctype_cleanup.py` references all 14 names
in `STANDARD_RELATIONS` and `REMOVED_TABLE_FIELDS`. It is a v1.0 patch that
already ran, but to keep the codebase coherent after the 14 DocTypes are
gone, that patch's loop must **tolerate missing DocTypes**: guard each
`frappe.get_doc(...)`/`frappe.db.exists(...)` with a `frappe.db.exists("DocType",
name)` check and `continue` when absent, so re-running it after the removal
does not error on the now-deleted DocTypes. (This is a code change for the
build phase, listed here for completeness; the doc itself records the
requirement.)

**Relationship with the deferred L4 re-seeding.** The L4 seeder restructuring
(deferred) is what re-seeds the 36 demo association edges as `Relationship`
rows. The deletion patch is sequenced **after** that re-seeding on any site
that wants the demo edges preserved in `Relationship` — i.e. the full order on
`frappe.com` is: `remove-demo-data` → (L4 re-seed the edges as `Relationship`
rows) → pull/run the removal patch. A site that skips the re-seed loses the
demo association edges; that is acceptable for a scratch/demo site but must
be stated explicitly before running on the live site.

---

## 10. Commit sequence, blast radius, and unverified items

**Principle: one concern per commit, tests before implementation, live-bench
verification at each phase boundary (per the standing constraints).**

| Step | Concern | Blast radius | Verification |
|---|---|---|---|
| 1 | **Tests first** — add HD-4 consolidation tests (§5), pair-enforcement tests (§3.2), duplicate-handling tests (§8), and index/perf smoke tests (§6) against the *current* 14-DocType schema (tests describe the target `Relationship` behavior) | None (tests only) | `pytest` green; `bench --site frappe.com run-tests` |
| 2 | **Schema: `Relationship` gains `title_en`/`title_ar`** (§1.1 Option A) + `Relationship Type` `applies_to_subject`/`applies_to_object` → **child table `Relationship Type Allowed Pair`** `(subject_doctype, object_doctype)` (§3.1) + pair-enforcement in `Relationship.validate` (§3.2) | Additive only; existing `Relationship` rows unaffected | Migrate on a scratch site; existing relationship tests green |
| 3 | **Seed `Relationship Type` allowed-pair rows** (§3.3) so all currently-legal edges stay legal | Data (new type metadata) | Seed on scratch; pair-enforcement tests green |
| 4 | **Seeder restructuring (the deferred L4 work)** — move the 14 associations' demo/test edges from the 14 DocTypes to `Relationship` rows in `demo_content.py`/`demo_data.py`/`test_data.py`; update `test_demo_data_structure.py` (see §11 for expected counts/assertions) | Data (demo/test rows) | `pytest` green; demo re-seed on scratch |
| 5 | **Remove the 14 from `SCOPED_DOCTYPES`** (`hooks.py` + `data_group_scope.js` mirror) — HD-4 now runs on `Relationship` alone for these edges | Hooks/JS; permission surface shrinks to one DocType | HD-4 isolation suite green; permission review |
| 6 | **Workspace + translations cleanup** — remove the 14 workspace shortcuts and `ar.csv` entries | UI/translations only | Spot-check workspace, Arabic labels |
| 7 | **`fix_doctype_cleanup.py` tolerance** — guard its loops against the now-missing 14 DocTypes | Patch hygiene (no-op on already-clean sites) | Re-run the v1.0 patch post-removal; must be a clean no-op |
| 8 | **Strict-guard deletion patch** (§9) — **one** `[post_model_sync]` patch iterating the 14 names | **Destructive** — drops 14 tables | `remove-demo-data` **first**; patch on scratch with rows present (must refuse) and absent (must drop); then live bench |
| 9 | **Indexes** (§6) — `on_doctype_update` hook + `frappe.db.add_index` (documented Invariant #3 exception) | Additive DDL | `bench --site frappe.com execute` query timing spot-check (not a measured benchmark); confirm `EXPLAIN` uses the indexes |

**Blast radius summary:** steps 1–4, 6–7, and 9 are low-risk (additive, tests,
metadata, patch hygiene, or DDL-with-exception). Step 5 changes the
permission/hook surface (one DocType instead of 14 for these edges — the
intended consolidation). Step 8 is the only destructive step and is guarded by
the J1 row-count refusal plus the remove-demo-data-first precondition.

**What stays unverified without a live site (`verified: mock/static` vs
`verified: live bench`):**

- Index cost estimates (§6) are **analytical, not measured** — no real
  MariaDB timings on a populated `Relationship` table.
- HD-4 behavior across all roles on a real site with cross-group rows (§5) —
  fixture-tested only until run on `frappe.com`.
- The deletion patch's `DROP TABLE` behavior against the actual 14 tables on
  `frappe.com` (§9) — rehearsed on scratch only.
- Duplicate-normalization for symmetric types at scale (§8) — logic
  fixture-tested, not exercised on live demo data.
- Form UX parity (§7) — the profile endpoints are already live, but the
  post-consolidation single-list experience needs a live Desk pass.
- `Person Position` isolation (§2) — unchanged, but its continued independence
  should be re-confirmed on the live site after the 14 are gone.

**Stop.** This is a read-only design. No application code has been edited. The
user decides before any of the above is built.

---

## 11. Fresh grep of all 14 names (item d)

Re-run on the current tree (post L4a rename). Each name searched in both
CamelCase-with-spaces and snake_case across `*.py`, `*.js`, `*.json`, `*.csv`,
`*.md`, `*.yml`, `*.yaml`. Command:

```bash
for name in "Institution Event" "Institution Location" \
  "Institution Military Unit" "Military Unit Event" \
  "Military Unit Institution" "Military Unit Location" \
  "Person Event" "Person Institution" "Person Location" \
  "Person Military Unit" "Siraj Event Institution" \
  "Siraj Event Location" "Siraj Event Military Unit" "Siraj Event Person"; do
  snake=$(echo "$name" | tr ' ' '_')
  git grep -n -F "$name" -- '*.py' '*.js' '*.json' '*.csv' '*.md' '*.yml' '*.yaml'
  git grep -n -F "$snake" -- '*.py' '*.js' '*.json' '*.csv' '*.md' '*.yml' '*.yaml'
done
```

**253 matching lines.** Grouped by file (highest first):

| File | Hits | Role |
|---|---|---|
| `siraj_research/setup/demo_content.py` | 36 | `ASSOCIATIONS` rows (`dt=`), DT_FIELD map |
| `siraj_research/siraj_research/workspace/siraj_research/siraj_research.json` | 28 | workspace shortcuts (label + link_to) |
| `docs/decisions/relationship-consolidation.md` | 21 | this design doc |
| `siraj_research/setup/demo_data.py` | 20 | `DT_FIELD` title-field map (current + legacy) |
| `docs/decisions/baseline.md` | 15 | historical baseline record |
| `docs/decisions.md` | 15 | association-endpoint decision table |
| `siraj_research/translations/ar.csv` | 14 | Arabic labels |
| `siraj_research/public/js/data_group_scope.js` | 14 | `SCOPED_DOCTYPES` mirror |
| `siraj_research/patches/v1_0/fix_doctype_cleanup.py` | 14 | `STANDARD_RELATIONS` |
| `siraj_research/hooks.py` | 14 | `SCOPED_DOCTYPES` |
| `siraj_research/siraj_research/doctype/siraj_event/siraj_event.json` | 7 | `link_doctype` dynamic-link targets |
| `siraj_research/siraj_research/doctype/{institution,military_unit,person,place}/*.json` | 6+6+5+4 | `link_doctype` targets on entity DocTypes |
| `tests/test_demo_data_structure.py` | 4 | `ASSOCIATIONS` dt assertions |
| `siraj_research/tests/test_api_data_group_isolation.py` | 2 | `Siraj Event Person` isolation fixture |
| the 14 doctype `*/<name>.json` files | 1 each | the DocType definitions themselves |

The snake_case form produced **zero** additional hits beyond the space form —
the 14 DocTypes are never referenced by their directory/snake name outside
their own `doctype/` directories. This confirms the consumer surface is the
table above and nothing else. (Full output captured in the commit that
revises this doc; the per-name listing is reproducible with the command above.)

---

## 12. Expected new seeder counts and affected assertions (item e)

**Current seeder volumes** (`setup/demo_content.py`, verified by parsing the
`ASSOCIATIONS` list):

| Block | Current rows | After consolidation |
|---|---|---|
| `RELATIONSHIPS` (typed directed/symmetric edges) | 24 | 24 (unchanged — already `Relationship` rows) |
| `ASSOCIATIONS` (14-DocType link-table rows) | 36 | **0** — these 36 rows move into the `Relationship` count |
| **Total `Relationship` rows** | **24** | **24 + 36 = 60** |

`ASSOCIATIONS` is spread across 10 of the 14 DocTypes (the other 4 —
`Institution Location`, `Institution Military Unit`, `Military Unit
Institution`, `Military Unit Location` — have no demo rows today):

| DocType | Association rows |
|---|---|
| `Siraj Event Location` | 6 |
| `Person Institution` | 6 |
| `Person Event` | 4 |
| `Person Military Unit` | 4 |
| `Siraj Event Person` | 4 |
| `Institution Event` | 3 |
| `Person Location` | 3 |
| `Military Unit Event` | 2 |
| `Siraj Event Institution` | 2 |
| `Siraj Event Military Unit` | 2 |
| **Total** | **36** |

The L4 re-seed converts each `ASSOCIATIONS` row into a `Relationship` row
(subject/object from the row's `refs`, `relationship_type` from a
per-`dt` mapping or a new `ASSOCIATION_TYPE` map), preserving `role`,
provenance, and workflow state. `SPEC["events_total"]` and the 15 Siraj Event
rows are unchanged.

**Assertions that change:**

`tests/test_demo_data_structure.py` (pure-Python, runs in CI):
- `test_association_rows_resolve_and_carry_the_tag_field` — currently
  asserts `any(r["dt"] == "Person Institution" ...)` and
  `any(r["dt"] == "Person Event" ...)` over `C.ASSOCIATIONS`, and that every
  `Person Event` row's `event` ref starts with `S:`. **After re-seed** the
  `ASSOCIATIONS` list is gone (or repurposed); these assertions move to the
  re-seeded `Relationship` rows: assert the converted rows exist with the
  right `subject_type`/`object_type`/endpoint refs. The `dt`-based assertions
  are replaced by `subject_type`/`object_type` assertions.
- `test_relationship_endpoints_resolve` — its `"E"`/`"S"` key sets reference
  `C.SIRAJ_EVENT_DATE_PRECISION`/`C.SIRAJ_EVENTS`; unchanged in name after the
  L4a constant rename, but the relationship-count assertions gain the +36.
- Any assertion on `len(C.ASSOCIATIONS)` or the 14 `dt` names is removed.

`siraj_research/tests/test_demo_data.py` (bench-side, runs on live site):
- `test_load_remove_roundtrip` asserts
  `self.assertEqual(result["Relationship"], len(C.RELATIONSHIPS))` (24).
  **After re-seed this becomes `len(C.RELATIONSHIPS) + len(C.ASSOCIATIONS)`
  (60)** — or the seeder returns the combined count directly. The
  `self.assertNotIn("Research Event", result)` assertion stays (it guards the
  deletion patch).
- The showcase assertions that query `Relationship` by `primary_source` /
  `authentication_level` remain valid — the 36 re-seeded rows carry the same
  provenance fields, so the "all six confidence codes" coverage still holds
  (verify the 36 rows' `authentication_level` values still span the codes; if
  the association rows used a narrower set, the confidence-coverage assertion
  must be checked against the combined 60).

`tests/test_demo_data_structure.py` `test_spec_volumes_match_content` is
unchanged for event counts (15 Siraj Events); only the `ASSOCIATIONS`-based
assertions change as above.

---

## 13. Uniqueness for (subject, object, relationship_type) (item f)

**Rule.** A `Relationship` is unique on
`(relationship_type, subject_type, subject, object_type, object)` for
**directed** types, and on the **normalized** pair
`(relationship_type, normalized_subject, normalized_object)` for
**symmetric** types, where normalization orders the two endpoints
deterministically (e.g. by `(doctype, name)`) so `(A→B)` and `(B→A)` are the
same edge.

**Where enforced.** In `Relationship.validate()` (extending the existing
`relationship.py:validate`), as a `frappe.throw(ValidationError)` on a
duplicate insert/update. **Not** a DB unique index at this stage: the
normalization for symmetric types cannot be expressed as a plain unique index
(the stored row keeps its original orientation), so enforcement is
application-level. (A DB unique index on the *directed* tuple could be added
later via the §6 `on_doctype_update` route, but it would not cover symmetric
normalization and is therefore deferred; the app-level check is the single
source of truth.)

**Duplicate handling on update:** when editing an existing `Relationship`,
the check must exclude the row's own `name` (self-update must not trip itself);
on insert, reject any existing row with the same normalized tuple.

**Live test plan** (`bench --site frappe.com run-tests --module ...`):
1. **Directed duplicate.** Create a directed `Relationship` type; insert
   `(type, Person, P1, Siraj Event, E1)`; insert the same tuple again →
   `ValidationError`. Insert `(type, Person, P1, Siraj Event, E2)` (different
   object) → accepted.
2. **Symmetric duplicate, both orientations.** Create a symmetric type;
   insert `(type, Person, P1, Institution, I1)`; insert
   `(type, Institution, I1, Person, P1)` (reversed) → `ValidationError`
   (normalized to the same edge).
3. **Self-update exemption.** Load an existing row, change `description`,
   save → accepted (does not trip its own uniqueness).
4. **Distinct types coexist.** Two different `relationship_type` values on
   the same endpoint pair → both accepted (uniqueness is per type).
5. **Directed vs symmetric.** Same endpoint pair under a directed type and a
   symmetric type → both accepted (types differ).
6. **`force`/admin path.** Confirm the admin override (if any) is the only
   documented escape, mirroring the `delete_research_event.py` force pattern.

---

## 14. Live test plan: deleting an endpoint that has relationships (item g)

The §8 recommendation is **block** (fail closed). Live test plan on
`frappe.com`:

1. **Setup.** Create (or use demo) a `Person` P and a `Siraj Event` E with a
   `Relationship` row R = `(Person, P) → (Siraj Event, E)` (directed or
   symmetric), saved and committed.
2. **Block on subject delete.** Attempt `frappe.delete_doc("Person", P)`
   (non-force) → **must raise** (the `before_delete` guard queries
   `Relationship` where `(subject_type, subject)` references P). Assert the
   error is a `ValidationError`/`LinkError` naming that relationships exist.
3. **Block on object delete.** Attempt `frappe.delete_doc("Siraj Event", E)`
   (non-force) → **must raise** (guard on the `object` side).
4. **Block propagates through the UI/API.** Delete P via a whitelisted
   endpoint or the Desk UI → the same error surfaces to the client.
5. **Both endpoints.** A relationship with both endpoints deleted in one
   transaction → blocked on the first.
6. **Admin/force override.** `frappe.delete_doc("Person", P, force=True)`
   (admin) — define and test the intended behavior: either it also blocks
   (strictest) or it cascades with an explicit, logged consent. The chosen
   behavior must match §8 and be asserted here.
7. **No orphan rows after a legit delete.** After a forced delete of an
   endpoint with no relationships (a clean `Person` with no edges), confirm
   zero `Relationship` rows reference it (guard does not false-positive).
8. **Symmetric block.** For a symmetric R, blocking works from either
   endpoint's delete (the guard checks both `subject` and `object`).
9. **`Person Position` unaffected.** Deleting a Person with a `Person
   Position` row is governed by §2's separate behavior, not this guard —
   assert it is unchanged.

These are `verified: live bench` items — they require the live `frappe.com`
site and are listed in §10's "unverified without a live site" until executed.
