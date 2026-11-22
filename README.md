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
