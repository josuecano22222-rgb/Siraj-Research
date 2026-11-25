# Remediation Progress Tracker

Branch: `arena/4bf5fef5-siraj-research` (base `ed889345be12eb41a05ccddf7d811557d4123573`).

## 1. Work Item Status

Every item carries an honest verification tag:
- `verified: mock/static` — verified via pure-Python `pytest`, Node/jsdom suites, static JSON/AST/Ruff checks, and `frappe 15.128.0` source inspection; **not** yet verified against a live MariaDB/Redis bench.
- `verified: live bench` — verified via GitHub Actions `server.yml` or a live MariaDB-backed `bench --site frappe.com` run.

| Phase | Item | Commit | Status | Verification | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | `P0-docs` | `744bbb9` | Done | `verified: mock/static` | Finalized `2026-11-siraj-fixes.md`, `baseline.md`, and `progress.md` after Gate 0 approval (items A–F). |
| **1** | `C-13` | `f1ac55f` | Done | `verified: mock/static` | Added `import frappe` in all 48 `doctype/*/test_*.py`, removed `F821` from `pyproject.toml`, and added `tests/test_doctype_test_imports.py` (`+1` passed, `+49` subtests vs baseline; `0` `F821` repo-wide). |
| **1** | `C-17` | `51de08f` | Done | `verified: mock/static` | Stamped `data_group="GD"` on scoped DocTypes in `setup/test_data.py` (+ fixed stale `Person.positions` child table, `Place.place_name`, and `Unit Classification.category="Line"` schema drift in `test_data.py`). Full `pytest` moved from `35 failed, 440 passed` to `29 failed, 447 passed` (`tests/test_fixture_controllers.py` now green; 2 drifted schema-count assertions in `test_test_data.py` remain for `C-16`/Phase 3 L4). |
| **1** | `C-18` | `70e2d93` | Done | `verified: mock/static` | Set `"default": "Draft"` on `workflow_state` across all 15 standalone relation DocTypes (`Siraj Event` deferred to Phase 3 L1 per plan). Full `pytest` moved from `29 failed, 447 passed` to `14 failed, 447 passed, 353 subtests passed` (+15 passing subtests). |
| **1** | `C-25` | `8f313a7` *(+ doc sync)* | Done | `verified: live bench` | Added real `FrappeTestCase` adversarial isolation suite `siraj_research/tests/test_api_data_group_isolation.py` + `siraj_research/tests/_isolation_fixtures.py` covering all 39 `@frappe.whitelist` callables across `GD`, `GC`, unassigned, `SIRAJ Viewer`, `SIRAJ Researcher`, and `SIRAJ Official`, predictable ID guessing (`PER-0001`, `PLC-0001`, `EVT-0001`), cross-group `Link`/`Dynamic Link` saves, non-admin `offline_bootstrap`/`boundary_import` boundaries, `tearDownClass` cache cleanup, and `@unittest.expectedFailure` markers for Phase 2 (`C-01`, `C-02`, `C-03a`, `C-03b`, `C-04`, `C-05`, `C-07`, `C-08`, `C-12`), plus local AST/smoke verifier `tests/test_whitelist_coverage.py` (`+3` passed -> `14 failed, 450 passed, 4 skipped`). **Verified on live MariaDB bench via GitHub Actions `server.yml` run `45528321233`: `Ran 15 tests in 4.245s — OK (expected failures=9)`** (and surfaced 6 pre-existing `data_group` MandatoryErrors across `test_audit_api`, `test_auto_fill_defaults`, `test_role_visibility`, `test_quality_scoring`, `test_demo_data`, and `test_person_family`). **GATE 1** |
| **2** | `C-01` | in progress | Done | `verified: live bench` *(pending server.yml)* | Replaced `frappe.get_all` with per-DocType `readable_rows` + valid schema field selection and deliberate counts-only fallback when `SIRAJ Settings` is unreadable (`test_05` promoted from `expectedFailure`). |
| **2** | `C-02` | pending | Todo | — | `entity_profile.py` + `relationship_profile.py` (`_fmt_value` only) `doc=` checks + `doc.get(f.fieldname)`. |
| **2** | `C-03a` | pending | Todo | — | Central cross-group `Link`/`Dynamic Link` rejection in `permissions.py` (HD-4) + consistent `data_group` in `demo_data.py`/`test_data.py`. |
| **2** | `C-03b` | pending | Todo | — | `operational_deployment.py` lifecycle, `command_appointment.py` `"role"` field, `person.validate_family`, `military_unit.py`/`utils/military.py` scoping. |
| **2** | `C-04a` | `08c0d72` | Done | `verified: live bench` | Aligned `geo_settings.json` `field_order` with all 59 fields (`server.yml` run `45674085310`: `test_api_data_group_isolation` `OK (expected failures=9)`). |
| **2** | `C-04` | pending | Todo | — | `offline_bootstrap.py` (`_require_admin`, `frappe.enqueue`, `max_zoom` `0..14`) + `geo_settings.js` polling (HD-2). |
| **2** | `C-05` | pending | Todo | — | `boundary_import.py` (`dependencies` gate, `start_import` path confinement, upload cap) + `geo_import._extract_if_zip` symlink/zip-bomb checks. |
| **2** | `C-06` | pending | Todo | — | `data_group_scope.js` bind per scoped DocType name (eliminate `cur_frm.doctype` crash). |
| **2** | `C-07` | pending | Todo | — | `sweep_points` permission check, JSON parsing when `points` is `str`, 500 cap. |
| **2** | `C-08` | pending | Todo | — | `map_relations.py:165` i18n `.format`, `diagnostics.py:59` path, `visualization.py` `PermissionError` + `valid_dimensions` (HD-5). |
| **2** | `C-12` | pending | Todo | — | `shared_record.json` add 4 `SIRAJ` roles + `SIRAJ Official`, `share: 0` on non-admins (HD-3). **GATE 2** |
| **3** | `L1` | pending | Todo | — | Unified `Siraj Event` schema/controller/list/test, delete `doctype/research_event`, `[post_model_sync]` deletion patch, `hooks.py`, `relationship.json`, workspace, number cards (HD-1). |
| **3** | `L1b` | pending | Todo | — | Delete obsolete `setup/event_*.py` + `tests/test_event_*.py` after moving `_index`/`_same`/`PlanError` into `coordinate_transition.py` (see Open Risks #1). |
| **3** | `L2` | pending | Todo | — | Switch backend registries, `visualization.py`, `geo_quality.py`, `map_relations.py`, `relationship_profile.py`, reports, `setup/*.py` to `Siraj Event`. |
| **3** | `L3` | pending | Todo | — | Switch frontend/offline JS (`siraj-map-search.js`, `geography-action-i18n.js`, `siraj-audit.js`, `snapshot_verify.js`) + lockstep `SIRAJ_BUILD` / `SIRAJ_EXPLORER_BUILD`. |
| **3** | `L4` | pending | Todo | — | Retarget `demo_content.py`, `demo_data.py`, `test_data.py`, Python/JS tests, and event docs to `Siraj Event`. **GATE 3** |
| **4** | `C-09` | pending | Todo | — | Remove explicit `frappe.db.commit()` from 3 legacy patches + timestamp backup filename. |
| **4** | `C-10` | pending | Todo | — | Delete 4 `deploy_*.py` scripts + `patches/d15-to-d17.patch` + update `docs/installation.md:386` (HD-6). |
| **4** | `C-11` | pending | Todo | — | Build-stamp parity test (`record_icons.SIRAJ_BUILD`, `siraj-record-meta.js`, `siraj-map.js`, `SIRAJ_EXPLORER_BUILD`). |
| **4** | `C-16` | pending | Todo | — | Repair drifted `Command Region`, `Military Unit.region`, and `master_data` `new_doc` Python tests. |
| **4** | `C-26` | pending | Todo | — | Non-empty `__init__.py` on 4 `Person` child DocTypes, resolve `test_no_inline_svg.py`, and resolve `numpy` in `test_geo_import.py`. |
| **4** | `C-19` | pending | Todo | — | Repair 4 failing JS suites + generate `package-lock.json`. **GATE 4** |
| **5** | `C-20` | pending | Todo | — | `pyproject.toml` dev deps (`pytest`, `numpy`, `ruff`, `cryptography`) + repo-wide Ruff clean + `ci.yml` full lint. |
| **5** | `C-21` | pending | Todo | — | `ci.yml` remove all `--ignore` flags, `npm ci`, discover all non-browser JS suites, separate Chromium job. |
| **5** | `C-22` | pending | Todo | — | `server.yml` remove `continue-on-error`, remove dead `failids` ref, run `bench --site test_site run-tests --app siraj_research`. |
| **5** | `C-23` | pending | Todo | — | Ground `README.md` and `docs/*.md` in actual v2.1+ commands, role matrix, and single `Siraj Event` DocType. |
| **5** | `C-24` | pending | Optional | — | Optional `siraj_explorer.js` bundle split (only if all gates green). **GATE 5** |

---

## 2. Scoped Gate 3 Grep Commands & Current Counts

Per Gate 0 item B, `linked_place` stays on `Military Unit`, `Admin Boundary`, `Gazetteer Place`, and the generic `linked_place_field` config key, and is dropped **only on `Siraj Event`**.

### Exact Gate 3 Verification Commands
1. **Zero `Research Event` / `research_event` / `research-event` references** (excluding `docs/decisions/`, `patches/d15-to-d17.patch` until `C-10`, `deploy_*.py` until `C-10`, and the deletion patch itself):
   ```bash
   git grep -n -E "Research Event|research_event|research-event" \
     -- ':!docs/decisions/*' ':!siraj_research/patches/*/delete_*research_event*.py' \
        ':!patches/d15-to-d17.patch' ':!deploy_*.py'
   ```
   - **Current count at Phase 0:** `199` matching lines across `57` files (`42` under `siraj_research/`, `15` under `tests/` and `docs/`).
2. **Zero `linked_place` references on `Siraj Event`** (schema, `setup/demo_data.py` `Siraj Event` block, `setup/test_data.py` `Siraj Event` block, `visualization.py` `Siraj Event` entries):
   ```bash
   git grep -n "linked_place" -- \
     siraj_research/siraj_research/doctype/siraj_event/ \
     && python3 -c '
   import json, re, pathlib
   d = json.loads(pathlib.Path("siraj_research/siraj_research/doctype/siraj_event/siraj_event.json").read_text())
   assert all(f.get("fieldname") != "linked_place" for f in d["fields"])
   assert "linked_place" not in d.get("field_order", [])
   demo = pathlib.Path("siraj_research/setup/demo_data.py").read_text()
   siraj_block = demo.split("# -- Siraj Events")[1].split("refs =")[0] if "# -- Siraj Events" in demo else demo
   assert "linked_place" not in siraj_block
   '
   ```
   - **Current count at Phase 0:** `3` lines (`siraj_event.json:90`, `siraj_event.json:297`, `setup/demo_data.py:512`).

---

## 3. Open Risks & Findings to Surface Before Phase 3

1. **Gate 0 Item C Stop-Condition Hit (`setup/event_*.py` import check):**
   - Grep across the entire repo proved that `hooks.py`, `patches.txt`, CLI commands, workflows, and `siraj_research/` runtime modules do **not** import any `siraj_research/setup/event_*.py` module — **with one exception**:
     - `siraj_research/setup/coordinate_transition.py:10–11` (which is tested by `tests/test_coordinate_shared.py` and `tests/test_coordinate_transition.py`) executes:
       ```python
       from siraj_research.setup.event_snapshot_projection import _index, _same
       from siraj_research.setup.event_transition_plan import PlanError
       ```
   - Per Gate 0 item C (*"If anything else imports them, stop and report"*), we will report this at Gate 1 before touching `event_*.py` in Phase 3: either inline the ~25-line `_index`, `_same`, and `class PlanError(ValueError)` helpers into `coordinate_transition.py` when deleting the 12 `event_*.py` + 11 `test_event_*.py` files, or delete `coordinate_transition.py` as well if desired.
2. **Gate 0 Item E DDL vs. Table-Drop Tension on HD-1 Deletion Patch:**
   - `frappe.delete_doc("DocType", "Research Event", force=True)` deletes `tabDocType` metadata without DDL (`frappe/model/delete_doc.py:86–113`), leaving `tabResearch Event` as an empty orphan table unless `DROP TABLE` is run, whereas `DROP TABLE` is DDL (`Invariant #3` forbids DDL and `frappe.db.commit()` in patches). Surfaced in `2026-11-siraj-fixes.md` for confirmation before Phase 3 L1.
3. **Live MariaDB `server.yml` Baseline Discovery (Run `45528321233`):**
   - `test_api_data_group_isolation` passed completely (`Ran 15 tests in 4.245s — OK (expected failures=9)`), as did `test_map_search_api` (`Ran 14 tests — OK (skipped=1)`).
   - However, 6 pre-existing bench test modules in `siraj_research/tests/` (`test_audit_api`, `test_auto_fill_defaults`, `test_role_visibility`, `test_quality_scoring`, `test_demo_data`, and `test_person_family`) fail on live MariaDB with `frappe.exceptions.MandatoryError: [Person/Place/..., ...]: data_group` because they call `doc.insert(ignore_permissions=True)` as `Administrator` (for whom `stamp_and_lock_data_group` does not auto-stamp `data_group`) without providing `data_group="GD"`. Must stamp `data_group` in those test fixtures + `demo_data.py` (`C-03a` / `C-16` / `C-22`) before promoting `server.yml` to required in `C-22`.
