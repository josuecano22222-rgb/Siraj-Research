### Siraj Research

Research platform with a global administrative hierarchy
(Country → Governorate → District → Municipality → Village → Community),
bilingual fields, deterministic P-Codes, offline-first maps, and fully local
operation after setup.

**Current release: [`V2.0.0`](RELEASE_NOTES_V2.0.0.md)** — highlights,
upgrade steps and gates; full history in [`CHANGELOG.md`](CHANGELOG.md).
Shipped geo data covers **Israel and Palestine (IL/PS) only**; coordinates
are stored exactly as entered, never rounded.

### Installation

**Read [`docs/from-scratch-runbook.md`](docs/from-scratch-runbook.md)** (fresh wipe, step-by-step) or [`docs/installation.md`](docs/installation.md)** — the full
install-from-bare-metal guide (bench → apps → migrate → geography → offline
lock), written as one continuous sequence of commands.

Short version, once a bench already exists:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench --site $SITE install-app siraj_research
bench --site $SITE migrate
bench build --app siraj_research
bench --site $SITE clear-cache
```

Then complete **Act IV** of the installation guide (dataset import → geo
package → `prepare_offline_site`) while online, and the site runs offline.

### Sync after a merge to main

Updates touch **only** `siraj_research` (no `bench update --reset`):

```bash
git -C apps/siraj_research fetch origin main
git -C apps/siraj_research reset --hard origin/main
bench --site $SITE migrate
bench build --app siraj_research
bench --site $SITE clear-cache
bench restart
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please
[install pre-commit](https://pre-commit.com/#installation) and enable it:

```bash
cd apps/siraj_research
pre-commit install
```

### CI

GitHub Actions runs on every pull request:

- **CI** — pure-Python unit tests, pure-Node unit tests, JSON/syntax/diff
  validation, ruff on changed files (required gate).
- **Linters** — JSON, syntax, `pip-audit`.
- **Server (advisory)** — full bench integration; non-blocking until stable.

Required checks must be green before a PR merges to `main`.

### License

mit

### Strict Data Group isolation

The app includes a group-scoped demo DocType, **Shared Record**, and an
idempotent setup command for two five-member sections:

```bash
# For a new app/bench (skip new-app/get-app when using this repository):
bench new-app siraj_research
bench --site SITE install-app siraj_research
bench --site SITE migrate
bench --site SITE execute siraj_research.setup.install.setup \
  --kwargs '{"password":"REPLACE-WITH-A-STRONG-PASSWORD"}'
bench --site SITE run-tests --app siraj_research \
  --doctype "Shared Record"
```

The setup creates `GD` and `GC`, users `gd1@example.com` … `gd5@example.com`
and `gc1@example.com` … `gc5@example.com`, the **Group Member** role, and one
native Data Group User Permission per user. It is safe to rerun. Keep **Apply
Strict User Permissions** off. Turn **Disable Document Sharing** on in System
Settings: Frappe shares can otherwise grant access across the group boundary.

Isolation is enforced in three server layers: permission query conditions for
collection/search/count/report/export paths, a deny-only document permission
hook for direct access/print/API paths, and a `before_validate` event that
server-stamps and locks `data_group`. Administrator remains unrestricted;
missing memberships and blank groups fail closed.

#### Protecting another DocType

1. Add a required, read-only Link field named `data_group`, with options
   `Data Group` (also mark it `no_copy` and `search_index`).
2. Grant the ordinary role-level operations needed by **Group Member** and
   leave **If Owner** disabled. Do not grant Share.
3. Add the DocType name to the single `SCOPED_DOCTYPES` list in
   `siraj_research/hooks.py`; that registers all three enforcement layers.
4. Run `bench --site SITE migrate`, clear cache, and add cross-group tests.
5. Ensure custom reports/APIs use Frappe permission-aware document/query APIs;
   never use raw SQL, `frappe.get_all`, or `ignore_permissions=True` in request
   paths.
