# Decisions — 2026-11 SIRAJ Security & Remediation Plan

Recorded against `siraj_research` commit `ed88934` (`v2.1.0`). All human decision gates (`HD-1` through `HD-6`) are finalized below.

> **Data fact:** There is no data on any bench, including `Person`. Sites may be recreated freely on scratch sites.

---

## HD-1 — Event DocTypes

**DECIDED.** `Siraj Event` is the single event DocType. `Research Event` is deleted. No data migration, because both event tables are empty. Because `bench migrate` does NOT delete a DocType whose files were removed, add a small patch that deletes the `Research Event` DocType record (and its table) if present and empty, and fails loudly if it holds rows.

Schema (clean design):
- `naming_series` `EVT-.####`; `title_field` `display_name`
- `title_ar` / `title_en`, `display_name` computed; at least one of `title_ar`/`title_en` required (controller-enforced)
- the old `"title"` field is removed; `autoname` `field:title` is removed
- `start_date` / `end_date` `Datetime`, with `*_as_stated` and `*_precision`
- one `Place` link field named `"place"` (drop `linked_place`); keep `place_as_stated`; fix every reference
- `status` (`Planned` / `Ongoing` / `Concluded` / `Cancelled`) kept
- `significance`, `image`, `image_url`, `image_alt` ported
- `researcher_notes` at `permlevel` `1`; `DocPerm` rows for `SIRAJ Reviewer`, `SIRAJ Administrator`, `System Manager`
- `workflow_state` default `"Draft"`; `share: 0` on every non-admin role
- the seven association DocTypes keep pointing at `Siraj Event`

**Consequences:** `Siraj Event` adopts a clean unified schema with zero legacy `"title"` / `"linked_place"` shims or row-migration code; every `Siraj Event` / `Research Event` reference across backend registries, reports, seeders, JS modules, and tests is updated to `Siraj Event` (`display_name`, `place`), while an idempotent patch removes the empty `Research Event` DocType record (aborting loudly if `tabResearch Event` has rows) and scratch sites validate both fresh install and migrate paths.

### Frappe v15.128 Source Verification for the HD-1 Deletion Patch
Inspected directly in `frappe 15.128.0` (`version-15` @ `fd94443`):
1. **`[pre_model_sync]` vs `[post_model_sync]` ordering:** Yes — `SiteMigration.run_schema_updates` (`frappe/migrate.py:113–122`) runs `patch_handler.run_all(..., PatchType.pre_model_sync)`, then `frappe.model.sync.sync_all()`, then `patch_handler.run_all(..., PatchType.post_model_sync)` (also documented in `frappe/modules/patch_handler.py:16–31`; an unsectioned `patches.txt` defaults to `pre_model_sync` at `patch_handler.py:124–129`). Placing the deletion patch in **`[post_model_sync]`** ensures `relationship.json`, `workspace`, and `onboarding_step` are synced first so no stale metadata references `Research Event` when it is deleted.
2. **Are patches skipped on `new-site` / `install-app`?** Yes — `install_app` (`frappe/installer.py:293–319`) calls `set_all_patches_as_completed(name)` when `set_as_patched=True` (the default), logging every entry in `patches.txt` into `Patch Log` without executing it.
3. **What does `frappe.delete_doc("DocType", "Research Event", ...)` do when files are gone and `developer_mode` is off?** In `frappe/model/delete_doc.py:86–113`, `doctype == "DocType"` takes a dedicated branch: it allows deletion when `frappe.flags.in_patch` or `force=True` even with `developer_mode=0` (`patch_handler.py:157` sets `conf.developer_mode = 0`), deletes `Custom Field` / `__global_search` entries and `tabDocType` + child `DocField`/`DocPerm` rows via `delete_from_table`, and **never imports the deleted Python controller** (`delete_controllers` is skipped when `developer_mode` is falsy or `in_migrate` is set; `DocType.after_delete` at `frappe/core/doctype/doctype/doctype.py:684–686` only calls `clear_controller_cache`). Note also that `SiteMigration.post_schema_updates` (`frappe/migrate.py:143`, `frappe/model/sync.py:145–176`) runs `remove_orphan_doctypes()` *after* `post_model_sync`, so checking row counts in `[post_model_sync]` runs *before* `remove_orphan_doctypes()` can touch `tabDocType`.
4. **Does `frappe.delete_doc("DocType", ...)` drop the SQL table?** **No** — verified in `frappe/model/delete_doc.py:86–113`, `frappe/model/sync.py:149` (*"Deleting the entry doesn't delete any data"*), and `frappe/patches/v14_0/drop_data_import_legacy.py:10–23`: `delete_doc("DocType", ...)` deletes only metadata rows (`tabDocType`, `tabDocField`, `tabDocPerm`, etc.) and leaves `tabResearch Event` on disk. Furthermore, in MariaDB, `DROP TABLE` is DDL (`frappe/database/database.py:422–426, 451–456`: `sql_ddl` calls `self.commit()`, and running `DROP TABLE` via `frappe.db.sql` after any DML write raises `ImplicitCommitError`). Under **Invariant #3** (*"No DDL and no `frappe.db.commit()` in request paths or patches"*), dropping `tabResearch Event` via SQL DDL inside the patch would violate Invariant #3 (and trigger MariaDB's implicit commit); this tension is flagged explicitly before Phase 3 L1 so the patch either checks `tabResearch Event` emptiness + deletes the `DocType` metadata record without DDL, or receives an explicit owner waiver if `DROP TABLE IF EXISTS` before any DML (`transaction_writes == 0`) is desired.

---

## HD-2 — `run_online_setup`

**DECIDED.** `frappe.enqueue`, admin-gated via a module-local `_require_admin()` helper in `siraj_research/offline_bootstrap.py` calling `frappe.only_for(("System Manager", "SIRAJ Administrator"))` (verified after opening `offline_bootstrap.py:92–105, 389–401`; does not import private `_assert_admin` from `boundary_import.py`), `max_zoom` clamped `0..14`, `request_stop` and `clear_stop` gated identically, and `geo_settings.js` updated to poll `bootstrap_running` / `bootstrap_last_status` in the same commit.

**Consequences:** `siraj_research/offline_bootstrap.py` enforces `_require_admin()` (`frappe.only_for(("System Manager", "SIRAJ Administrator"))`) on `run_online_setup`, `request_stop`, and `clear_stop`, clamps `max_zoom` to `[0, 14]`, and dispatches `prepare_offline_site` onto Frappe's `"long"` background queue via `frappe.enqueue`, while `siraj_research/public/js/geo_settings.js` polls `Geo Settings` (`bootstrap_running` / `bootstrap_last_status`) in the same commit (`C-04`, preceded by `C-04a` fixing `geo_settings.json` `field_order`).

---

## HD-3 — `Shared Record`

**DECIDED.** Add the four `SIRAJ` roles and `SIRAJ Official` alongside `Group Member` and `System Manager`; `share: 0` on non-admin roles; existing `test_shared_record.py` assertions keep passing.

**Consequences:** `siraj_research/siraj_research/doctype/shared_record/shared_record.json` grants level-appropriate permissions to `SIRAJ Viewer`, `SIRAJ Researcher`, `SIRAJ Reviewer`, `SIRAJ Administrator`, and `SIRAJ Official` (with `share: 0` on non-admin roles) while preserving `Group Member` and `System Manager` so `test_shared_record.py` continues to pass unchanged alongside full `SIRAJ` role isolation tests.

---

## HD-4 — Cross-group links

**DECIDED.** Reject a `Link` or `Dynamic Link` to a scoped record in a different `data_group` on every save, for every role including `SIRAJ Official`, implemented once in `permissions.py`.

**Consequences:** Cross-group link isolation is enforced centrally in `siraj_research/permissions.py` across all `SCOPED_DOCTYPES` (and their child tables) on every document save for every role including `SIRAJ Official`, with zero per-controller copies, and `setup/demo_data.py` + `setup/test_data.py` stamp consistent `data_group` values in the same commit (`C-03a`) so seeding never creates cross-group links.

### Frappe v15.128.0 Hook Order & Bypass Matrix (`C-03a`)

Verified directly against `frappe 15.128.0` (`version-15` @ `fd94443`):
1. **Why `validate` (not `before_save`), and exact execution order relative to `_validate_links` and `stamp_and_lock_data_group`:**
   - **On `Document.insert()` (`frappe/model/document.py:420–434`):**
     1. `self.check_permission("create")` (`document.py:421`) — calls `siraj_research.permissions.has_permission` (`permissions.py:57`), rewriting `doc.data_group` for group members before native `User Permission` link checks.
     2. `self._validate_links()` (`document.py:423`, defined at `document.py:1114–1130`) — validates parent and child-table `Link` / `Dynamic Link` target existence (`get_invalid_links()`) before hooks run.
     3. `self.run_method("before_insert")` (`document.py:424`).
     4. `self.run_before_save_methods()` (`document.py:430`, defined at `document.py:1280–1311`):
        - `self.run_method("before_validate")` (`document.py:1294`) -> runs `stamp_and_lock_data_group` (`permissions.py:92`), guaranteeing `doc.data_group` is authoritatively stamped on new records and locked against mutation on existing records.
        - `if self.flags.ignore_validate: return` (`document.py:1296–1297`).
        - `self.run_method("validate")` (`document.py:1300` on `"save"`, and `document.py:1303` on `"submit"`) -> runs controller `validate()` first (`Document.hook` at `document.py:1512–1533`), then `doc_events[doctype]["validate"]` (`validate_same_data_group_links`).
        - `self.run_method("before_save")` (`document.py:1301` — **only** when `self._action == "save"`, skipped on `"submit"` where `before_submit` runs at `1304`).
     5. `self._validate()` (`document.py:431`, defined at `document.py:748–778`) — runs `_validate_mandatory()`, etc.
   - **On `Document.save()` for existing docs (`frappe/model/document.py:527–545`):**
     1. `self.check_permission("write", "save")` (`document.py:527`).
     2. `self._validate_links()` (`document.py:536`, defined at `document.py:1114–1130`).
     3. `self.run_before_save_methods()` (`document.py:537`) -> `before_validate` (`stamp_and_lock_data_group` at `1294`) -> `validate` (`validate_same_data_group_links` at `1300` / `1303`).
   - **Choice of `validate` over `before_save`:** `validate` runs on **both** `"save"` and `"submit"` (`document.py:1300, 1303`), always executes strictly **after** `before_validate` (`stamp_and_lock_data_group`, `document.py:1294`) and **after** `_validate_links` (`document.py:423, 536`), and runs **before** any `before_save` / `on_update` side-effects.
2. **Single justified exception to Invariant 1:** `validate_same_data_group_links` (`siraj_research/permissions.py`) executes **one** batched `frappe.get_all(target_dt, filters={"name": ["in", ...]}, fields=["name", "data_group"])` per referenced scoped target DocType. Permission-scoped `get_list` cannot be used here because `SIRAJ Official` and `Administrator` legitimately have read access across groups (`get_list` would return the foreign row without distinguishing groups), whereas reading `(name, data_group)` in one batch per target DocType rejects both cross-group and blank-group targets for every role while keeping error text strictly generic (`"Linked records must belong to the same Data Group."`, containing zero target names or titles).
3. **Documented validation bypasses (verified & tested in `test_23`):**
   - **`doc.db_set(...)` (`frappe/model/document.py:1394–1453`):** Updates column(s) via `frappe.db.set_value` and runs only `before_change` / `notify_update` — **bypasses `validate`**. Repo audit (`grep -rn '\.db_set(' siraj_research/`): used only on unscoped `Boundary Dataset` progress fields (`boundary_import.py:60–62`, `geo_import.py:664–670`); zero scoped link fields use `db_set`. Tested in `test_23` (subsequent normal `.save()` catches any cross-group link written via `db_set`).
   - **`frappe.db.set_value(...)` (`frappe/database/database.py:945–995`):** Direct SQL `UPDATE` without ORM events — **bypasses `validate`**. Repo audit: production code uses `db.set_value` only on `Geo Settings`, `Boundary Dataset`, `Admin Boundary`/hierarchy `country` repair (`geo_import.py`), `Person` derived scalar columns (`patches/v2_0/backfill_family_derived.py:45`), `Military Unit.subtree_personnel` (`military_unit.py:88`), and `Operational Deployment` -> `Military Unit.current_deployment` (`operational_deployment.py`, where `OperationalDeployment.unit` is already validated in the same `data_group` during `validate` before `on_update` runs in `C-03b`). Tested in `test_23`.
   - **`doc.flags.ignore_validate = True` (`frappe/model/document.py:1296–1297`):** Returns early from `run_before_save_methods()` after `before_validate`, so `stamp_and_lock_data_group` still runs (`1294`) while `validate` hooks are skipped. Repo audit: zero occurrences of `ignore_validate` in `siraj_research/`. Tested in `test_23`.
   - **Data Import (`frappe/core/doctype/data_import/importer.py:256–296`) vs fixture file import (`frappe/modules/import_file.py:234–238`):** Standard Desk `Data Import` calls `new_doc.insert()` / `updated_doc.save()` **with validation ON** (so `validate_same_data_group_links` is enforced on every CSV/XLSX user import). Only internal schema/fixture sync `import_file_by_path(..., data_import=False)` sets `doc.flags.ignore_validate = True` and `doc.flags.ignore_links = True` when syncing app JSON metadata.

---

## HD-5 — `structure_data`

**DECIDED.** Raise `PermissionError` for unreadable `permlevel` fields; tolerate only genuinely absent schema columns; pass `valid_dimensions` consistently.

**Consequences:** `siraj_research/visualization.py:structure_data` raises `frappe.PermissionError` whenever a caller requests a `dimensions` field present on the DocType meta whose `permlevel` the caller cannot read, tolerates genuinely absent schema columns, and passes `valid_dimensions` into `_bucket_tree` at line 524, restoring `tests/test_visualization.py:432`.

---

## HD-6 — `deploy_*.py` and `patches/d15-to-d17.patch`

**DECIDED.** Delete `deploy_all_d18.py`, `deploy_offline_d17.py`, `deploy_offline_d17_min.py`, `deploy_offline_d18.py`, and `patches/d15-to-d17.patch`, and update `docs/installation.md:386` in the same commit.

**Consequences:** All four root `deploy_*.py` scripts and `patches/d15-to-d17.patch` are deleted and `docs/installation.md` is updated in `C-10` so stale embedded archives can never downgrade `hooks.py` or strip `SCOPED_DOCTYPES`.

---

## Gate 2 Decision — `geo_quality.quality_report` and `SIRAJ Settings` (`C-01`)

**Verified repository fact:** The singleton DocType `SIRAJ Settings` **exists** in the repository at `siraj_research/siraj_research/doctype/siraj_settings/siraj_settings.json` (`issingle: 1`, granting `read: 1` to all four `SIRAJ` roles plus `System Manager`).

**Decision:** Remove the secondary `frappe.has_permission("SIRAJ Settings", "read")` sample gate and remove the bare `try/except Exception` wrappers around `frappe.has_permission(...)` in `siraj_research/geo_quality.py`. `quality_report` already filters every located DocType through `frappe.has_permission(dt, "read")` and `readable_rows(dt, fields)` (which enforces both SQL `permission_query_conditions` and per-row `frappe.has_permission(dt, "read", doc=row["name"])`), so returning up to 50 suspect-coordinate samples directly from the rows `readable_rows` approved is self-contained, never leaks unreadable rows, and avoids silently swallowing unexpected permission errors or suppressing samples for role configurations such as `Group Member`.

---

## Gate 2 Follow-up F3 Decision — Unreadable Link Payload Redaction (`name=None`)

**DECIDED.** Unreadable `Link` and `Dynamic Link` targets in profile APIs return `name: None` (JSON `null`), `title: _("Restricted")`, and `restricted: True` (and `counterpart_name: None`, `counterpart_title: _("Restricted")`, `counterpart_restricted: True` in `_authored_relationships`).

**Rationale & scope:** Several SIRAJ DocTypes use human-meaningful `autoname` (`field:label_en`, `field:title`) or predictable `naming_series` (`PER-0001`, `PLC-0001`), so returning the raw target `name` on an unreadable link leaks either the record's title or its exact series identifier across `Data Group` boundaries. Applied consistently across:
1. `siraj_research/api/entity_profile.py`: `_fmt_value` (`Link` & `Dynamic Link` on parent and child-table fields), `outbound_links` (`Link` & `Dynamic Link`), and `_authored_relationships` (`counterpart_name`),
2. `siraj_research/api/relationship_profile.py`: `_fmt_value` (`Link` & `Dynamic Link` on parent and child-table fields; `_resolve_endpoint` remains untouched until its scheduled item per standing constraint), and
3. `siraj_research/profile_presentation.py`: `normalise_field` preserves `name: None` and `restricted: True` instead of coercing `None` to `""`.

---

## Local Verification Limits (Without Local MariaDB / Redis)

Because the local sandbox lacks `mariadbd` and `redis-server` (outbound egress is restricted to `github.com`, `pypi.org`, and `registry.npmjs.org`), the following behaviors **cannot** be marked `verified: live bench` from local mock/static runs alone and require either GitHub Actions `server.yml` or an operator bench (`frappe.com`):

1. **SQL `permission_query_conditions` execution:** Actual MariaDB `WHERE` clause composition by `DatabaseQuery.build_conditions()` (`frappe.get_list` / `readable_rows` SQL generation for `GD`, `GC`, `SIRAJ Official`, and unassigned users).
2. **Frappe hook dispatch & `doc_events` ordering:** Live invocation of `hooks.py` `has_permission`, `permission_query_conditions`, and `doc_events` (`before_insert`, `validate`, `on_update`, `on_trash`) during `Document.insert()` / `save()` / `delete()`.
3. **`DocPerm` `permlevel` stripping & `frappe.has_permission(..., doc=...)`:** Real Frappe meta/role evaluation for `permlevel: 1` (`researcher_notes`) and `share: 0` enforcement.
4. **`bench migrate`, `patches.txt` section ordering, & DocType schema sync:** Real execution of `[pre_model_sync]` / `sync_all()` / `[post_model_sync]` / `remove_orphan_doctypes()`, MariaDB `ImplicitCommitError` detection (`frappe/database/database.py:451–456`), and `new-site` + `install-app` + `migrate` lifecycle on `frappe.com`.
5. **Redis queue / cache integration:** Live `frappe.enqueue` RQ worker pickup (`offline_bootstrap.run_online_setup`) and Redis permission/user cache invalidation.
6. **Headless Chromium rendering:** Real browser execution of the 2 Puppeteer suites (`tests/test_explorer_browser.js` and `tests/test_offline_viewer_browser.js`).

---

## Corrections to the original report

The following claims from the 16-finding external review report were **refuted or narrowed** during code verification against `ed88934`. Do **not** implement fixes for non-existent bugs or revert already-fixed code:

- **#1 (`offline_bootstrap.py`):** The helper invoked by `run_online_setup` is named `download_python_wheels` (not `download_geospatial_wheels`).
- **#2 (`entity_profile.py` & `relationship_profile.py`):** `siraj_research/api/relationship_profile.py:_resolve_endpoint` (line 88) **already** passes the document `name` to `frappe.has_permission(doctype, "read", name)` — do not touch `_resolve_endpoint`. The actual unguarded call site in `relationship_profile.py` is `_fmt_value` (lines 57–73), which calls `frappe.has_permission(df.options, "read")` without `doc=raw` before `frappe.db.get_value`. `siraj_research/api/entity_profile.py` has the same defect across `_fmt_value` (lines 36–74), the inline outbound-link block, inbound `frappe.db.count`, and `File` attachments (plus the `f.get(f.fieldname, None)` bug at line 189 which must read `doc.get(f.fieldname)`); `C-02` covers both files.
- **#3 (`boundary_import.py` & `geo_import.py`):** The extraction helper in `siraj_research/geo_import.py:88–103` is `_extract_if_zip` (not `_resolve_readable_source`). CPython 3.11+ `zipfile.ZipFile.extractall` already sanitizes leading `/` and `..` path segments in `_extract_member`, so the classic `..` Zip-Slip overwrite claim is downgraded to **symlink-member and zip-bomb (uncompressed size / member count)** validation; additionally, `boundary_import.dependencies()` (line 27) is `@frappe.whitelist()` and missing an admin check.
- **#4 (Military & Person controllers):** Verified by opening `siraj_research/siraj_research/doctype/military_unit/military_unit.py` (lines 1–111): the **only** `@frappe.whitelist()` method on `MilitaryUnit` is `get_descendants` (line 104, which already calls `self.check_permission("read")` and filters via `readable_rows`); neither `compute_subtree_personnel` (line 70) nor `update_ancestor_totals` (line 80) is whitelisted (there is no `recompute_personnel` method at all). Meanwhile, `command_appointment.py:40–58` has an additional runtime crash: `frappe.get_all` at line 48 omits `"role"` from `fields`, so formatting the overlap error at line 57 raises `AttributeError` on `other.role`.
- **#5 (`Research Event` vs `Siraj Event`):** `record_icons.boot_session` merges `COLOURS` into `frappe.boot.siraj_record_meta.colours`, which `siraj-record-meta.js` merges at boot — so `Research Event` does receive colour `#d08733` in Desk, though `GLYPHS` in `siraj-record-meta.js` does not merge `boot.glyphs`. Also `COORDINATE_DOCS["Siraj Event"]` in `record_icons.py:271` and `coordinate_map.js:38` (plus `siraj-record-meta.js:178`) already use `'place'` for `linked_place_field`; the schema field `linked_place` on `Siraj Event` (`siraj_event.json`) is what changes to `place` under `HD-1`.
- **#6 (`Shared Record`, `data_group_scope.js`, `Workspace`):** The Workspace coverage claim is **unsupported / already fixed**: `siraj_research/siraj_research/workspace/siraj_research/siraj_research.json` (lines 218–252, 320–365) already exposes the standalone relation DocTypes under `Associations & Link Tables`. Only the `data_group_scope.js:3` `cur_frm.doctype` null-dereference and the `shared_record.json` role split are real.
- **#8 (`pyproject.toml`):** `"F821"` in `[tool.ruff.lint] ignore` is at `pyproject.toml:60` (not line 36).
- **#9 (`deploy_*.py`):** Three of the four scripts (`deploy_all_d18.py`, `deploy_offline_d18.py`, `deploy_offline_d17_min.py`) extract via `tf.extractfile(n).read()` rather than `extractall`, and all four check `startswith("/")` and `".." in PurePosixPath(n).parts` (only `deploy_offline_d17.py:25` calls `archive.extractall(root)` as `.tar.gz` without `filter="data"`). None embed `siraj_explorer.js` or execute `bench` subprocesses, though `deploy_all_d18.py` and `deploy_offline_d18.py` genuinely overwrite `siraj_research/hooks.py` with a pre-`v2.1.0` copy lacking `SCOPED_DOCTYPES`.
- **#10 (`.github/workflows/server.yml`):** `continue-on-error: true` is set at the **job** level (`server.yml:16`), not step line 112. There is no separate `Surface failures if any` step running `base64 -d /tmp/failids-encoded.txt`; rather, `server.yml:119` expands `$(cat /tmp/failids-encoded.txt)` (a file never created) inside the single `Run Frappe server tests` step, which does execute `exit "$status"` at line 122 (masked by job-level `continue-on-error: true`).
- **#11 (`tile_cache.py` & `patches/`):** `tile_cache._ensure_columns`, `ALTER TABLE tabSIRAJ Settings`, and request-path `frappe.db.commit()` **do not exist** in `siraj_research/tile_cache.py` (already fixed: `tile_cache._settings()` reads standard schema fields from `Geo Settings`). Only the explicit `frappe.db.commit()` calls in `siraj_research/patches/` (`v1_0/fix_doctype_cleanup.py:73`, `v1_1/add_pcode_and_admin_boundary_fields.py:97, 116`, and `v2_0/backfill_family_derived.py:47`) are real.
- **#12 (`.github/workflows/ci.yml` & `package.json`):** There are **23** `tests/test_*.js` files (11 in `ci.yml`, 12 excluded; 2 of the 23 are Puppeteer/Chromium suites). `package.json` `test:js` lists 16 files and does **not** include `test_list_navigation.js` or `test_tree_navigation.js` (it fails in a clean checkout only when `node_modules`/`jsdom` is not installed).
- **#14 (`package.json` & `.github/workflows/linter.yml`):** `package.json:9–12` **already** declares `jsdom` and `jquery` in `devDependencies` (what is missing is `package-lock.json` and `npm ci` in `ci.yml`). `.github/workflows/linter.yml` does **not** run `pre-commit`, and its `validators` job **does** run on `push` to `main` (`linter.yml:3–6`); only `deps-vulnerable-check` (`pip-audit`) is gated on `pull_request` (`linter.yml:58`).
- **#16 (`README.md` & `docs/*.md`):** Both `siraj_research/docs/onboarding/README.md` and `RELEASE_NOTES_V2.0.0.md` **exist on disk** (contrary to sub-claim 1), and `README.md:1–57` **already** contains the v2.1.0 overview, install/sync instructions, pre-commit/CI sections, and a link to `docs/installation.md` at line 13 (contrary to sub-claim 5). Only the broken `siraj_research.demo_data.*` module path (`docs/installation.md:404, 406`), unnecessary `install-app erpnext` (`docs/installation.md:77`), stale paths/branch/tag in `docs/from-scratch-runbook.md`, and outdated `patches.txt` / `Command Region` / offline claims in `docs/siraj-explorer.md` should be edited.
