# Changelog

All notable changes to `siraj_research`. Dates are UTC. Tags follow the
release-notes table in [`docs/installation.md`](docs/installation.md).

## [Unreleased]

### Added

- Optional Person profile fields for gender and current residence, with
  optional identity, birth, nationality, marital-status, mobile, and accounts
  data; repeatable accounts may be recorded partially.
- Per-Person custom label/value rows for user-defined information (case-
  insensitive unique labels; values may be blank). ID, mobile, and current-
  residence fields use permission level 1.
- ID and mobile fields on Person and related spouse, parent, child, sibling,
  and grandchild records; enter one mobile number per line.

## [2.0.0] — 2026-11-18

### Added

- **Family tab on Person** (Phase 0) — exclusive embedded spouse,
  children and grandchildren rows (no hollow Person records), the
  sibling-link exception, marital-status UI gating (hidden ≠ cleared),
  grandchild `through_child` lineage, server validation
  (`Person.validate_family`), derived `is_grandparent` +
  `family_summary` (in `search_fields`), Explorer Family section, and
  `docs/person-family.md`. 18 pure + bench-side controller tests.
- **Advanced map search** (Phase 1) — one widget on the Explorer map:
  exact coordinate answers (decimal verbatim, exact-fraction DMS, no
  rounding ever), regions (Admin Boundary + Country→Community registry),
  gazetteer places, permission-aware records; `search_bbox` viewport
  search with antimeridian wrapping; `region_children` cascade with
  pcode/exact centroids; coordinate hierarchy/missing-levels/nearby
  rendering; "Search this area" passes bounds verbatim.
- **Bilingual onboarding tutorial** (Phase 2) — 13 files
  (`docs/onboarding/01`–`10` + README + common-errors + quick-reference),
  English then العربية in every file, mirrored by the in-app checklist;
  IL/PS-only coverage prominently stated in README, step 2 and step 10.
- **Demo data lifecycle** (Phase 3) — `load-demo-data` /
  `remove-demo-data` bench commands, demo markers, workspace links.
- **Auto-fill defaults + coordinate audit history** (Phase 4) —
  auto-fill default settings, coordinate audit trail with full-precision
  coordinates (never rounded or shortened).
- **Quality scoring** (Phase 4/5) — deterministic presentation scores
  (`completeness`, `quality_score`, `confidence`) in the profile payload;
  the Quality section documents its weights in UI help text and marks
  evidence-derived confidence **(derived)** vs recorded, in the desk
  profile and the Explorer (shared renderer).
- **Permission matrix tests** — 4-role suite (Viewer / Researcher /
  Reviewer / Administrator) green in CI; `docs/qa/permission-test-report.md`.
- **Release-gate CI** — `.github/workflows/server.yml` runs the eight
  release-gate bench modules on a fresh site (advisory until one week of
  green runs); `.github/workflows/ci.yml` node job runs the pure-Node
  suites including `test_map_search_ui.js`.
- **Release artifacts** — `CHANGELOG.md`, `RELEASE_NOTES_V2.0.0.md`,
  `docs/qa/v2.0.0-runbooks.md` (migration safety, fresh-install
  integration, permissions quick reference).

### Changed

- **Version** — `0.0.1` → **`2.0.0`** (`siraj_research/__init__.py`,
  `package.json`; `pyproject.toml` takes the version dynamically from the
  package).
- **`npm run test:js`** — now runs all 13 pure-Node suites (superset of
  the CI node list): added `test_load_probe`, `test_map_search_ui`,
  `test_siraj_cascade_core`, `test_siraj_geopoint_core`.
- **`siraj_research/translations/ar.csv`** — 1827 rows (quality help,
  `(derived)` badge and tooltip added); round-trip validated, LF endings.
- **`docs/installation.md`** — release-tag table gains `V2.0.0` and an
  upgrade recipe; README states the current release.

### Fixed

- Quality tests: Source Type registry lookup (Link to registry, not
  Select); `unittest.SkipTest` in `setUpClass` (F821).
- Role-visibility matrix honours permlevel-0 row semantics (two Reviewer
  rows previously shadowed the base row).
- `@frappe.whitelisted()` TypeError → `frappe.whitelist()` (guarded by
  test); Explorer `layerGroup` stub for section tests; bundle-order pins;
  history probes pass `ignore_version=False` (frappe suppresses Version
  rows during tests).
- Registered the audit script at its actual public asset URL
  (`/assets/siraj_research/js/siraj-audit.js`) instead of the unresolved
  bare filename, preventing the Desk-wide `/siraj-audit.js` 404.

### Migration notes

- `bench --site <site> migrate` is the only data step. New patch
  **`siraj_research.patches.v2_0.backfill_family_derived`** recomputes
  *only* the derived `Person.is_grandparent` and `Person.family_summary`
  columns from stored family rows — user-entered data is never written.
  Idempotent (second run changes nothing); fresh installs mark it
  completed at install time like every other patch.
- **Removed four phantom `patches.txt` entries** (`v1_0.set_naming_counters`,
  `v1_0.fold_commanders`, `v1_0.migrate_person_traits`,
  `v1_0.map_notes_to_comments`) — the modules never existed in this
  repository, so they could never execute; any site that had not already
  logged them would fail the next migrate with an ImportError. The three
  real patches (`fix_doctype_cleanup`, `remove_duplicate_custom_fields`,
  `add_pcode_and_admin_boundary_fields`) are unchanged, and all four
  surviving entries resolve to a file with `def execute`.
- No schema changes require data repair beyond the family backfill:
  hierarchy/gazetteer seeding is exists-guarded (`seed_master_data`
  skips existing rows — no duplicate registry rows on re-run), and
  `DefaultValue` / geo hierarchy rows are untouched by any patch.

## [1.x]

Pre-2.0.0 history lives in the decision log
([`siraj_research/docs/decisions.md`](siraj_research/docs/decisions.md))
and the release-tag table in `docs/installation.md`.
