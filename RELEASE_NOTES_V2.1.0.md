# SIRAJ Research v2.1.0 — Release Notes

**Tag:** `v2.1.0` (annotated on `main`)
**Date:** 2026-11-23
**Previous release:** `V2.0.0`

v2.1.0 adds strict section-level research-data isolation, quieter geographic
assistance, complete Arabic coverage for Desk map/help controls, and lifecycle
fixes for maps and modals.

## Highlights

### 1. GD/GC section isolation

Core user-entered SIRAJ records now carry an immutable `data_group`. Members of
GD can collaborate on all GD records, and members of GC can collaborate on all
GC records, while neither section can list, open, edit, delete, print, export,
search, link to, or count the other section's records.

The boundary is enforced by native User Permissions plus server-side list
conditions, direct-document checks, and server stamping/locking. Blank-group
legacy records fail closed and remain Administrator-only. Document sharing is
disabled because shares can bypass User Permissions.

The idempotent setup provisions GD/GC, ten users, roles, User Permissions, and
the SIRAJ Official role profile:

```bash
bench --site SITE execute siraj_research.setup.install.setup \
  --kwargs '{"password":"REPLACE-WITH-A-STRONG-PASSWORD"}'
```

Ordinary section users receive full SIRAJ research and app-configuration access
without Frappe System Manager access. A user assigned the SIRAJ Official profile
can oversee both populated sections.

### 2. Core SIRAJ records protected

Isolation applies to people, institutions, places, sources, relationships,
events and their associations, military units and associations, deployments,
missions, appointments, and training exercises. Shared geography, taxonomy,
lookup masters, and SIRAJ settings remain common to both sections.

### 3. Quiet boundary review

Administrative boundary conflicts never open a modal automatically during
create, edit, save, refresh, map movement, or coordinate resolution. Empty
fields are filled safely; unresolved differences expose a highlighted
**Geography → Review boundary suggestions** action. The comparison opens only
when the user asks for it.

### 4. Arabic Desk controls

Arabic translations now cover all literal SIRAJ Desk `t()` help text, tooltips,
map controls, hierarchy prompts, boundary-review actions, and offline setup
messages. CI audits both standard Frappe translation calls and SIRAJ's Desk
translation wrapper. A Frappe-v15 compatibility safeguard also localizes the
Geography action group after asynchronous toolbar rendering.

### 5. UI lifecycle and accessibility

Concurrent map mounts are deduplicated, stale temporary-document maps are torn
down after save, and Bootstrap modals release focus before becoming hidden.
This reduces repeated scroll-listener warnings and removes the hidden-focused
modal accessibility violation.

## Upgrade from V2.0.0

```bash
cd $PATH_TO_YOUR_BENCH
git -C apps/siraj_research fetch origin
git -C apps/siraj_research checkout v2.1.0
bench --site $SITE migrate
bench build --app siraj_research
bench --site $SITE clear-cache
bench restart
```

Then run the idempotent isolation setup command shown above. Existing protected
records have no inferred section and remain Administrator-only until they are
assigned to GD or GC through a controlled migration.

## Verification

```bash
bench --site $SITE set-config allow_tests true
bench --site $SITE run-tests --app siraj_research \
  --module siraj_research.siraj_research.doctype.shared_record.test_shared_record
```

The repository CI additionally validates Python/JSON syntax, pure-Python and
Node suites, Arabic translation completeness, workspace coverage, and changed
Python files with Ruff.
