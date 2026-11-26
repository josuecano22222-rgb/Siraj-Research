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

### 3.1 Schema change

The single-DocType Links must become **multi-DocType** to express pairs.
Recommended: convert both to a multi-select of DocType names.

- `applies_to_subject`: `Select` (or Checkbox) listing allowed **subject**
  DocTypes.
- `applies_to_object`: `Select` (or Checkbox) listing allowed **object**
  DocTypes.

(Alternative: a child table `applies_to(DocType)` with a `role` column
distinguishing subject/object. More flexible but heavier; the two multi-selects
are sufficient for the fixed endpoint set and far simpler to validate.)

### 3.2 What the controller must enforce

On `Relationship.validate()` (extending the existing
`relationship.py:validate`), after the type is resolved:

1. **Pair membership.** Load the `Relationship Type`; require
   `subject_type ∈ applies_to_subject` **and** `object_type ∈ applies_to_object`.
   Throw `ValidationError` otherwise. This is the single enforcement point and
   replaces the implicit "the DocType exists, so the link is fine" behavior the
   15 association DocTypes get for free from their typed Link fields.
2. **Symmetric types.** If `is_symmetric` is true, the pair is unordered:
   require that the pair is allowed in *either* orientation — i.e. accept
   `(A, B)` if `A ∈ subject ∧ B ∈ object` **or** `B ∈ subject ∧ A ∈ object`.
   The existing `relationship.py:validate` already forces `direction =
   "Symmetric"` from `is_symmetric`; add the orientation-tolerant pair check.
   Optionally enforce `applies_to_subject == applies_to_object` for symmetric
   types at the type-definition level (a `Relationship Type` validate hook).
3. **Directional types.** Enforce the ordered pair strictly: subject must be in
   `applies_to_subject`, object in `applies_to_object`, no reversal.
4. **Self-links.** Reject `subject == object` for non-hierarchical types
   (the Explorer already guards this client-side at
   `siraj_explorer.js:209`; move it server-side).
5. **`inverse_type` / `is_hierarchical`.** Keep `inverse_type` for UI
   (inverse label) and reserve `is_hierarchical` for future tree semantics;
   they do not change pair enforcement.

### 3.3 Seed / migration of `Relationship Type` rows

The 15 association DocTypes imply a set of allowed pairs. Seed
`Relationship Type` rows (or extend existing ones) with
`applies_to_subject`/`applies_to_object` populated so every currently-legal
edge remains legal after consolidation. The existing seeders
(`setup/master_data.py`, `setup/test_data.py`, `tests/_isolation_fixtures.py`)
already create `Relationship Type` rows with `is_symmetric`; they gain the two
new fields.

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

**Indexes recommended (additive, via a patch or the JSON):**

| Index | Columns | Serves |
|---|---|---|
| `idx_rel_subject` | `(subject_type, subject)` | `get_entity_network` subject batches |
| `idx_rel_object` | `(object_type, object)` | `get_entity_network` object batches |
| `idx_rel_data_group` | `(data_group)` | HD-4 batch checks, permission query conditions |
| `idx_rel_type` | `(relationship_type)` | type filtering, `relationship_data` |

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
each of the **14** consolidated DocTypes (`Person Position` is excluded per §2).

**Per DocType, in a `[post_model_sync]` patch (one patch module, or one
executed per DocType in a loop):**

1. **Raise if rows exist (J1 strict guard).** Before deleting, run
   `SELECT COUNT(*) FROM \`tab<DocType>\``. If `row_count > 0`, `frappe.throw`
   with a message that names the DocType and row count and shows the exact
   remediation (never auto-delete rows in a migration patch).
2. **`delete_doc("DocType", <name>, force=True)`** — removes metadata, Custom
   Fields, permissions, and the `tabDocType`/child rows. Per the verified
   Frappe v15 behavior, `delete_doc` on a `DocType` whose files are gone does
   **not** drop the SQL table and does **not** import the deleted controller
   (`frappe/model/delete_doc.py:86-113`; `developer_mode` is `0` during
   migrate per `frappe/modules/patch_handler.py:161`, and
   `frappe.flags.in_migrate` is set per `frappe/migrate.py:89`).
3. **`DROP TABLE IF EXISTS \`tab<DocType>\``** — per Decision E, after the
   row-count guard passes (the table is empty by construction).
4. **Idempotent** — safe to re-run (mirrors `delete_research_event.py`).

**Ordering note:** run after `remove_orphan_doctypes()` considerations — the
`delete_research_event.py` precedent checks row counts in `[post_model_sync]`
*before* `SiteMigration.post_schema_updates` runs
`remove_orphan_doctypes()` (`frappe/migrate.py:143`); the same ordering holds
here.

**Demo-data precondition:** `frappe.com` holds demo rows — the demo seeders
(`setup/demo_content.py`, `setup/demo_data.py`) create rows in these 14
DocTypes. **`remove-demo-data` must run before the deletion patch**, or the
row-count guard will (correctly) refuse. This is the same precondition the
`delete_research_event.py` patch documented. The L4 seeder restructuring
(deferred) is what re-seeds those edges as `Relationship` rows; the deletion
patch should be sequenced after that re-seeding on any site that wants the
demo edges preserved in `Relationship`.

---

## 10. Commit sequence, blast radius, and unverified items

**Principle: one concern per commit, tests before implementation, live-bench
verification at each phase boundary (per the standing constraints).**

| Step | Concern | Blast radius | Verification |
|---|---|---|---|
| 1 | **Tests first** — add HD-4 consolidation tests (§5), pair-enforcement tests (§3.2), duplicate-handling tests (§8), and index/perf smoke tests (§6) against the *current* 14-DocType schema (tests describe the target `Relationship` behavior) | None (tests only) | `pytest` green; `bench --site frappe.com run-tests` |
| 2 | **Schema: `Relationship` gains `title_en`/`title_ar`** (§1.1 Option A) + `Relationship Type` `applies_to_subject`/`applies_to_object` → multi-select + pair-enforcement in `Relationship.validate` (§3) | Additive only; existing `Relationship` rows unaffected | Migrate on a scratch site; existing relationship tests green |
| 3 | **Seed `Relationship Type` pairs** (§3.3) so all currently-legal edges stay legal | Data (new type metadata) | Seed on scratch; pair-enforcement tests green |
| 4 | **Seeder restructuring (the deferred L4 work)** — move the 14 associations' demo/test edges from the 14 DocTypes to `Relationship` rows in `demo_content.py`/`demo_data.py`/`test_data.py`; update `test_demo_data_structure.py` | Data (demo/test rows) | `pytest` green; demo re-seed on scratch |
| 5 | **Remove the 14 from `SCOPED_DOCTYPES`** (`hooks.py` + `data_group_scope.js` mirror) — HD-4 now runs on `Relationship` alone for these edges | Hooks/JS; permission surface shrinks to one DocType | HD-4 isolation suite green; permission review |
| 6 | **Workspace + translations cleanup** — remove the 14 workspace shortcuts and `ar.csv` entries | UI/translations only | Spot-check workspace, Arabic labels |
| 7 | **Strict-guard deletion patch** (§9) for the 14 DocTypes | **Destructive** — drops 14 tables | `remove-demo-data` first; patch on scratch with rows present (must refuse) and absent (must drop); then live bench |
| 8 | **Indexes** (§6) via patch/JSON | Additive | `bench --site frappe.com execute` query timing spot-check (not a measured benchmark) |

**Blast radius summary:** steps 1–4 and 6–8 are low-risk (additive, tests,
metadata, or data-movement with guards). Step 5 changes the permission/hook
surface (one DocType instead of 14 for these edges — the intended consolidation).
Step 7 is the only destructive step and is guarded by the J1 row-count refusal.

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
