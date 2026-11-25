# Baseline Test & Environment Audit (`ed88934` / `v2.1.0`)

Recorded during **PHASE 0** (read-only code state; zero source files modified).
Requested scratch site name: `frappe.com`.

## 0. Sandbox Environment Fact (Honest Bench Constraint)

- **Runtime present:** Python `3.11.2`, Node `v22.22.3`, npm `10.9.8`, `frappe 15.128.0` source wheel (`version-15` @ `fd94443`) installed into an isolated scratch virtualenv `/tmp/siraj-venv` alongside `pytest 9.2.0`, `cryptography`, and `ruff 0.8.1`.
- **Database / Redis daemons:** Neither `mariadb-server`/`mysqld` nor `redis-server` nor Docker is installed or listening in this container (`ss -tlnp` shows only system RPC/SSH ports; `/var/cache/apt/archives` is empty; outbound egress is restricted by sandbox policy to `github.com`, `codeload.github.com`, `api.github.com`, `registry.npmjs.org`, `pypi.org`, and `files.pythonhosted.org` — Debian `apt` mirrors are unreachable).
- **Consequence for `bench --site frappe.com run-tests --app siraj_research`:** A live MariaDB-backed Frappe site (`frappe.com`) cannot be provisioned inside this container because `mariadbd` and `redis-server` binaries cannot be fetched from `apt`. Every pure-Python test, static AST/JSON/Ruff check, Frappe source inspection (`frappe 15.128.0` installed in `/tmp/siraj-venv`), and non-Chromium Node/jsdom suite **can and has been executed directly**; full live-MariaDB `bench --site frappe.com` execution is documented in `server.yml` and in the exact reproduction runbook for a MariaDB-equipped bench. (Zero bench tables exist in this environment, consistent with `<data_fact>`.)

---

## 1. Suite Summary Table

| Suite | Command | Passed | Failed | Skipped / Blocked | Status |
| :--- | :--- | ---: | ---: | ---: | :--- |
| **CI Pure-Python (`ci.yml` with 8 `--ignore`s)** | `PYTHONPATH=. pytest tests/ --ignore=... (x8) -q` | 399 (+131 subtests) | 0 | 3 skipped | Green |
| **Full Pure-Python (`tests/` unfiltered)** | `PYTHONPATH=. pytest tests/ -q` | 439 (+289 subtests) | 35 (across the 8 ignored files) | 4 skipped | **Red (35 failures)** |
| **Static App Tests (`siraj_research/tests/` no-DB subset)** | `PYTHONPATH=. pytest siraj_research/tests/test_{api_static,doctype_integrity,map_relations_args,no_inline_svg}.py` | 18 (+842 subtests) | 6 (5 subtests + 1 test) | 0 | **Red (6 failures)** |
| **Bench-coupled App & DocType Tests (`bench --site frappe.com run-tests --app siraj_research`)** | `bench --site frappe.com run-tests --app siraj_research` | — | — | 8 `siraj_research/tests/*` + 49 `doctype/*/test_*.py` blocked on `mariadbd`/`redis-server` | **Env-blocked** (additionally, 48 of 49 `doctype/*/test_*.py` fail `ruff F821` due to missing `import frappe`) |
| **CI Node Unit Tests (`ci.yml` 11 files)** | `for f in <11 ci.yml files>; do node "$f"; done` | 11 files | 0 | 0 | Green |
| **`npm ci` (clean checkout)** | `npm ci` | 0 | 1 (`EUSAGE`) | — | **Red (`package-lock.json` missing)** |
| **`npm run test:js` (clean checkout, no `node_modules`)** | `npm run test:js` | 6 files | 1 (`test_offline_viewer.js`) | 9 not reached | **Red (`Cannot find module 'jsdom'`)** |
| **`npm run test:js` (with `jsdom` + `jquery` installed)** | `NODE_PATH=/tmp/siraj-js/node_modules npm run test:js` | 16 files | 0 | 0 | Green |
| **All `tests/test_*.js` (all 23 files, with `jsdom` + `jquery`)** | `for f in tests/test_*.js; do node "$f"; done` | 17 files | 4 non-browser + 2 Chromium | — | **Red (4 non-browser failures + 2 Chromium-only)** |
| **Static JSON & AST (`ci.yml`)** | `json.load` (`siraj_research/**/*.json`) + `ast.parse` (`**/*.py`) | All | 0 | 0 | Green |
| **Repo-wide Ruff (`ruff==0.8.1`)** | `ruff check siraj_research tests` | — | 23 violations (+ 48 `F821` when `--select F821` isolated) | — | **Red (23 lint errors + 48 hidden `F821`)** |

---

## 2. Detailed Failure Catalog & Root-Cause Attribution

### 2A. Full `tests/` Python Suite (35 failures across the 8 `ci.yml`-ignored files)

| File | Failing Test(s) | Count | One-Line Root Cause | Tag |
| :--- | :--- | ---: | :--- | :--- |
| `tests/test_coordinate_audit.py` | `CoordinateAuditTest.test_read_only_pagination_and_fixed_bound_schema_query` | 1 | `coordinate_audit.py:15` already switched `TYPES` to `"Siraj Event"`, while test line 94 still asserts `report["doctypes"]["Research Event"]` (`KeyError`). | `fixed by merge` (HD-1 / Phase 3 L4) |
| `tests/test_default_workflow_state.py` | `DefaultWorkflowStateTest.test_doctype_defaults_match_installed_state` | 16 subtests | `workflow_state` lacks `"default": "Draft"` on `Siraj Event` and all 15 standalone relation DocTypes (`Institution Event`, `Institution Location`, `Institution Military Unit`, `Military Unit Event`, `Military Unit Institution`, `Military Unit Location`, `Person Event`, `Person Institution`, `Person Location`, `Person Military Unit`, `Person Position`, `Siraj Event Institution`, `Siraj Event Location`, `Siraj Event Military Unit`, `Siraj Event Person`). | `fixed by C-18` (15 relations) + `fixed by merge` (`Siraj Event` in Phase 3 L1) |
| `tests/test_test_data.py` | `FixtureTest.test_coverage_links_and_repeat_guard`, `test_existing_operational_data_is_preserved_and_samples_are_marked`, `test_failure_rolls_back`, `test_fictional_narrative_and_disputed_evidence_are_connected`, `test_fixture_exercises_folded_group_and_record_counts`, `test_fixture_explorer_graph_and_coordinate_cases`, `test_multilingual_sparse_and_relationship_scenarios` | 7 | `siraj_research/setup/test_data.py` inserts scoped DocTypes (`Source`, `Person`, etc.) without stamping required `data_group` (`AssertionError: Source: missing data_group`); also references `"Research Event"` once `data_group` is stamped. | `fixed by C-17` (+ `fixed by merge` in Phase 3 L4) |
| `tests/test_fixture_controllers.py` | `ControllerFixtureTest.test_fixture_against_bundled_controller_validations` | 1 | Calls `seed_test_data()`, failing first on `Source: missing data_group` and referencing `("research_event", "ResearchEvent")` in controller list. | `fixed by C-17` (+ `fixed by merge` in Phase 3 L4) |
| `tests/test_geo_import.py` | `test_iter_features_reads_new_pyogrio_four_tuple` | 1 | Imports `numpy` (`ModuleNotFoundError: No module named 'numpy'`) because `numpy` is undeclared in `ci.yml` / `pyproject.toml` dev dependencies (and test lacks `pytest.importorskip` or dev-dep declaration). | `fixed by C-20` / `fixed by C-16` |
| `tests/test_master_data.py` | `MasterDataTest.test_complete_fresh_install_and_repeat_preserve_existing`, `test_missing_and_conflicting_parents_never_create_wrong_hierarchy` | 2 | `master_data.py:156` calls `frappe.new_doc("Boundary Dataset")`, which `FakeFrappe` in `tests/test_master_data.py` never stubbed (`AttributeError: module 'frappe' has no attribute 'new_doc'`). | `fixed by C-16` |
| `tests/test_treeview.py` | `TreeTest.test_denied_and_other_doctypes_are_not_exposed`, `test_pagination_is_not_limited_to_twenty` | 2 | Tests still call `get_children("Command Region")`, a DocType removed in v2.0 when `treeview.TREE_SPECS` was narrowed to `Place` and `Military Unit`. | `fixed by C-16` |
| `tests/test_visualization.py` | `test_region_hierarchy_respects_parent_and_permissions`, `test_regions_units_composite_counts_and_does_not_expose_private_parents`, `test_selected_fields_exist_and_are_public` (`Command Region.parent_region`, `Military Unit.region`) | 4 (2 tests + 2 subtests) | Tests assert removed `"regions"` / `"regions-units"` structure sources, deleted `Command Region` DocType, and renamed `Military Unit.region` → `linked_place`. | `fixed by C-16` |
| `tests/test_visualization.py` | `test_structure_refuses_unreadable_dimension_instead_of_false_missing_data` | 1 | `visualization.py:517–524` silently filters unreadable `permlevel` dimensions into `valid_dimensions` (and passes raw `dimensions` to `_bucket_tree`) instead of raising `frappe.PermissionError` per HD-5. | `fixed by C-08` (HD-5) |

### 2B. Static App Tests in `siraj_research/tests/` (6 failures)

| File | Failing Test(s) | Count | One-Line Root Cause | Tag |
| :--- | :--- | ---: | :--- | :--- |
| `siraj_research/tests/test_doctype_integrity.py` | `test_07_field_order_matches_fields` (`Geo Settings`) | 1 subtest | `geo_settings.json` defines 10 offline-bootstrap fields (`sb_online_setup`, `online_setup_enabled`, `run_online_setup`, `stop_bootstrap`, `bootstrap_running`, `bootstrap_stop_requested`, `bootstrap_last_status`, etc.) missing from `field_order`. | `fixed by C-04` (or `C-16` if kept separate) |
| `siraj_research/tests/test_doctype_integrity.py` | `test_08_controller_exists_and_parses` (`Person Additional Field`, `Person Child`, `Person Grandchild`, `Person Sibling`) | 4 subtests | `__init__.py` in those 4 child DocType directories is 0 bytes (`st_size == 0`). | `unrelated` (pre-existing static integrity debt; candidate for Phase 4 hygiene if approved) |
| `siraj_research/tests/test_no_inline_svg.py` | `test` | 1 | `siraj-map-advanced.js` (lines 30, 325, 342) and `siraj-profile-fields.js` (line 30) emit inline `<svg>` strings without being listed in `ALLOWED` or routed via icon helpers. | `unrelated` (pre-existing static test failure outside `server.yml` 8-module list) |

### 2C. Node / JS Suites (`npm ci`, `npm run test:js`, and all 23 `tests/test_*.js`)

| Command / File | Result | One-Line Root Cause | Tag |
| :--- | :--- | :--- | :--- |
| `npm ci` | `FAIL (EUSAGE)` | Repository has `package.json` (`jsdom`, `jquery`) but no committed `package-lock.json`. | `fixed by C-19` |
| `npm run test:js` (clean tree without `npm install`) | `FAIL` at file 7/16 (`test_offline_viewer.js`) | `Cannot find module 'jsdom'` because neither developer runbook nor `ci.yml` runs `npm ci` first; passes 16/16 once `jsdom` + `jquery` are installed. | `fixed by C-19` + `fixed by C-21` |
| `tests/test_coordinate_map.js` | `FAIL (timeout / TypeError)` | `TypeError: Cannot read properties of undefined (reading 'layers')` inside Leaflet/stub initialization (and leaves an open timer handle); also references `'Research Event'` at line 293. | `fixed by C-19` (+ `fixed by merge` in Phase 3 L4) |
| `tests/test_explorer_ui.js` | `FAIL` | `ReferenceError: requestAnimationFrame is not defined` in the jsdom harness (`window.requestAnimationFrame` not shimmed on global scope). | `fixed by C-19` |
| `tests/test_list_navigation.js` | `FAIL` | Asserts `*_list.js` exists for every standalone DocType, failing on `Institution Event` (and the newly converted standalone relation DocTypes lacking list scripts). | `fixed by C-19` |
| `tests/test_tree_navigation.js` | `FAIL` | `ENOENT: .../doctype/command_region/command_region_tree.js` because `Command Region` DocType was deleted in v2.0. | `fixed by C-19` |
| `tests/test_explorer_browser.js` | `FAIL (Chromium)` | Requires `puppeteer-core` and a headless Chromium binary (browser suite). | `fixed by C-21` (separate Chromium job) |
| `tests/test_offline_viewer_browser.js` | `FAIL (Chromium)` | Requires `puppeteer-core` and a headless Chromium binary (browser suite). | `fixed by C-21` (separate Chromium job) |

### 2D. Static Lint Debt (`ruff==0.8.1`)

| Check | Count | One-Line Root Cause | Tag |
| :--- | ---: | :--- | :--- |
| `ruff check --isolated --select F821 siraj_research tests` | 48 | All 48 generated `siraj_research/siraj_research/doctype/*/test_*.py` files (every DocType test except `test_shared_record.py`) call `frappe.get_meta(...)` without `import frappe`, masked by `"F821"` in `pyproject.toml:60`. | `fixed by C-13` |
| `ruff check siraj_research tests` | 23 | Pre-existing `I001`, `UP009`, `UP035`, `UP038`, `B007`, `E701`, `F841`, `RUF005` across 20 untouched files because `ci.yml` only linted PR-diffed files. | `fixed by C-20` |
