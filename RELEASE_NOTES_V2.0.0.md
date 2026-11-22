# SIRAJ Research V2.0.0 — Release Notes

**Tag:** `V2.0.0` (annotated, created on `main` after the release PR merges)
**Date:** 2026-11-18
**Previous line:** v1.x (hierarchy foundation → cascading + bootstrap stop control)

V2.0.0 turns the platform from a hierarchy foundation into a complete
research workstation: family dossiers, one-box map search, a bilingual
onboarding tour, demo data you can load and remove cleanly, auditable
coordinates, deterministic quality scores, and a release-gated CI.

## Highlights

### 1. Family tab on Person
Spouse, children, grandchildren and siblings live on the person's own
record (no hollow Person records); siblings may optionally link to a real
Person. Marital status gates the UI without ever clearing stored data.
Grandchildren record which child they descend from (`through_child`).
A derived `family_summary` line joins desk search. Server validation
enforces dates, birth order and lineage on every save.
Full rules: `siraj_research/docs/person-family.md`.

### 2. Advanced map search (Explorer)
One box answers four questions — **coordinates** (decimal passed through
verbatim, exact-fraction DMS, Arabic digits/hemisphere letters; stored
coordinates are never rounded or shortened), **regions** (boundary
dataset + Country→Community registry with pcode ranking), **places**
(gazetteer) and **records** (permission-aware, type-filterable). Plus:
*Search this area* (bounds verbatim, antimeridian-safe), a six-select
region cascade, and coordinate hierarchy/missing-level/nearby answers.
Contract: `siraj_research/docs/map-search.md`.

### 3. Bilingual onboarding tutorial
Thirteen files under `siraj_research/docs/onboarding/` — every step in
English then العربية — mirrored by the in-app *Getting started*
checklist. **Coverage limit, stated prominently:** bundled hierarchy,
boundary and gazetteer data covers **Israel and Palestine (IL/PS) only**;
coordinates anywhere on Earth are stored and shown exactly as entered,
but matches outside IL/PS appear only after you import your region's data.

### 4. Demo data you can trust
`bench --site <site> execute siraj_research.demo_data.load` seeds marked
demo records; `...remove` takes them out again. Demo rows carry a visible
badge so they can never be mistaken for archive data.

### 5. Coordinates: exact, audited, auto-filled
Coordinate auto-fill defaults + an audit history that stores the full
precision as entered. **No rounding or shortening of coordinates anywhere
— ever.**

### 6. Quality scores you can explain
The profile payload ships `completeness_score`, `quality_score` and
`confidence`. The Quality section's UI help text documents the weights
(**60%** completeness + **25%** evidence rows, saturating at 5 + **15%**
primary source, rounded and clamped to 0–100) and marks evidence-derived
confidence **(derived)** so it is never confused with a recorded
authentication level — in the desk profile and the Explorer alike.

### 7. Permissions, tested
A 4-role matrix (SIRAJ Viewer / Researcher / Reviewer / Administrator)
runs in CI; results: `docs/qa/permission-test-report.md`. Guest access,
link-restricted fields, submit/cancel and custom-role combinations have
ready-to-run commands in `docs/qa/v2.0.0-runbooks.md` — run them on your
bench before declaring the release verified.

## Upgrade (v1.x → V2.0.0)

```bash
cd $PATH_TO_YOUR_BENCH
git -C apps/siraj_research fetch origin main
git -C apps/siraj_research reset --hard origin/main   # or: git checkout V2.0.0
bench --site $SITE migrate      # applies v2_0 family backfill (derived columns only)
bench build --app siraj_research
bench --site $SITE clear-cache
bench restart
```

Then optionally: `bench --site $SITE execute siraj_research.demo_data.load`
→ walk `docs/onboarding/README.md` → try the map search →
`...remove` when done. Details: `docs/qa/v2.0.0-runbooks.md`.

**Migration safety:** the only new patch recomputes two derived Person
columns (`is_grandparent`, `family_summary`) from stored rows; it never
writes user-entered data and is idempotent. Hierarchy/gazetteer seeding
remains exists-guarded — no duplicate registry rows on re-run. Four
phantom `patches.txt` entries whose modules never existed were removed
(see CHANGELOG) so no migrate can hit a missing-module ImportError.

## Verification gates (this tag)

| Gate | Result |
|---|---|
| pytest (CI ignore list) | 396+ passed, 131 subtests (pre-release run) |
| `npm run test:js` | 13/13 pure-Node suites |
| ruff + F821 on changed files | clean |
| `ar.csv` round-trip + locale audits | 1827 rows, LF, no findings |
| `git diff --check` | clean |
| CI workflow (required) | Linters, CI green on the release commit |
| Server workflow (release-gate modules) | 8/8 modules green — **advisory** |

**Server workflow status:** `server.yml` is currently an **advisory**
(non-required) check: it has been green for consecutive runs but has not
yet met the one-week-of-green stability bar stated in its header. It does
not block the `V2.0.0` tag; promote it to a required check after a week of
green runs on `main`.

## Known limitations

- IL/PS-only bundled geo coverage (extensible via the documented import
  pipeline; ODbL attribution applies to OSM-derived data).
- The four non-matrix permission scenarios (guest, custom role
  combinations, link-restricted fields, submit/cancel) must be executed
  on a bench with the commands in `docs/qa/v2.0.0-runbooks.md`.
- Full multi-app `bench build` still fails on the historical BigInt
  issue — build per-app (`bench build --app siraj_research`).

## Post-merge tagging (run on `main`, never on the arena branch)

```bash
git checkout main
git pull --ff-only origin main
git tag -a V2.0.0 -m "SIRAJ Research V2.0.0 — family, map search, onboarding, demo data, quality scoring, permission matrix"
git push origin V2.0.0
gh release create V2.0.0 --title "V2.0.0" --notes-file RELEASE_NOTES_V2.0.0.md
```
