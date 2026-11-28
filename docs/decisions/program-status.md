# SIRAJ Research — Program Status

**Branch:** `arena/4bf5fef5-siraj-research` (base `ed889345be12eb41a05ccddf7d811557d4123573` of `main`).
**Source of truth:** this file is rebuilt from the repo (git log, file contents) each session. Earlier chat summaries are not trusted over the repo.
**Server JOB note:** the `Server` workflow job is advisory (`continue-on-error: true`). The RUN conclusion hides failures. Only the JOB conclusion is reported.

## Status legend
- `todo` — not started
- `in progress` — started, not met
- `done` — acceptance met and recorded

## Program status

| Item | Status | Commit / PR proving it | Evidence |
| :--- | :--- | :--- | :--- |
| **P0a** Close PR #17 (no merge); drop `_fill_missing_mandatory`; revert seed name-guessing; keep `ensure_hierarchy_autoname` | **in progress** | PR #17 closed (this session); `ensure_hierarchy_autoname` = `10ac8c3` | `gh pr close 17`; `install.py` `ensure_hierarchy_autoname` + `hooks.py` after_migrate entry kept |
| **P0b** Read-only `report_schema_drift` diagnostic + unit test (stub) | **todo** | — | — |
| **P0c** User runs `report_schema_drift` on frappe.com; remove stray Custom Fields only on instruction | **todo** | — | awaiting user output |
| **P0d** Acceptance: Server JOB green on main (2 consecutive runs) + `test_api_data_group_isolation` green on bench | **todo** | — | — |
| **P1** Consolidate 14 binary association DocTypes into `Relationship` (Person Position stays) | **todo** | design = `docs/decisions/relationship-consolidation.md` (PROPOSAL, no code) | steps 3–7, 9 first; step 8 only after explicit approval |
| **P2** Natural Earth Vector program (gap list drives work; NOT complete) | **in progress** | gap list = `docs/qa/natural-earth-vector-gap-list.md`; Priority 1 done (`e76bc45`) | Python/API/DocType/serving/provisioning done; Leaflet JS path browser-tested; MapLibre path + integration surfaces NOT browser-verified |
| **P3** Hygiene & CI hardening (C-09, C-10, C-11, C-16, C-19–C-24) | **todo** | — | per original remediation plan |
| **P4** Closure: `docs/decisions/final-report.md` | **todo** | — | — |

## Detailed P2 (Natural Earth Vector) gap status

Source: `docs/qa/natural-earth-vector-gap-list.md` (verification basis 2026-11-28). Feature is **NOT complete**.

- **DONE:** dataset/catalog (206 layers/3 scales), bundled 110m tier, all serving endpoints (`layer`/`manifest`/`catalog`/`index`), provisioning (git_clone + local_mirror, manifest, ZIP, admin gating), security & licensing, Python tests (`test_natural_earth_vector` 30 green), static `search_fields` gate, Server JOB green on main (PR #12 3m23s, PR #13 3m21s), `server.yml` exception-line diagnostics, jsdom Leaflet-path browser test (`tests/test_nevector_browser.js`, `e76bc45`).
- **PARTIAL / NOT STARTED:** MapLibre attach-path browser test (P2 priority 2); basemap-switcher integration browser test; offline-viewer toggle browser test; bench-side re-verification of cascade + NE country-intelligence; clean main CI matrix re-run.

## Detailed P1 (Relationship consolidation) — not started

Design is a read-only PROPOSAL in `docs/decisions/relationship-consolidation.md`. No code changed. 14 binary associations → `Relationship`; `Person Position` stays. Order: steps 3–7, 9 first; step 8 (deletion patch) only after explicit user approval.

## Recent commits on branch (reverse chronological)

```
7700d85 fix(siraj): auto-fill site-specific mandatory fields in seed_test_data   <- REVERTING in P0a
10ac8c3 fix(siraj): root-cause fix for test_23 'Governorate Name is required'  <- keep ensure_hierarchy_autoname
09cdd1d fix(siraj): harden seed_test_data against stale DocType autoname
d03f6ac docs(siraj): update NE gap list — Server green on main, JS map test done
e76bc45 test(siraj): jsdom browser test for the Natural Earth Vector map layer
f86ae79 fix(siraj): update whitelisted-endpoint count 48 -> 51 in test_01
045b1f1 fix(siraj): close whitelist-coverage + ruff gates introduced by NE work
23e28b6 ci(siraj): echo exception line + static search_fields gate
```
