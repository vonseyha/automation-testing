# Changelog

All notable changes to this repo. Newest first.

## Unreleased

### Added
- **Remote-target guard:** a non-local `API_BASE_URL` / `SECURITY_BASE_URL` makes the backend suites BLOCKED (no request sent) unless `ALLOW_REMOTE_TARGET=1`; new required preflight check "Target is a local backend" (preflight now has 13 checks, 8 required). 9 unit tests.
- Full documentation set in `docs/`: SETUP, USER_GUIDE, ARCHITECTURE, CONFIGURATION, TESTING, DEVELOPMENT, OPERATIONS, SECURITY, TROUBLESHOOTING, DEPLOYMENT_READINESS, plus an index. `CONTRIBUTING.md` and this changelog.

### Changed
- `README.md` is now a short entry page; the end-to-end steps moved to `docs/SETUP.md`.
- The long-form `ENGINE_REFERENCE.md` and the original `USER_GUIDE.md` moved to `docs/history/`.

## 2026-11-01: standalone repo

### Added
- The engine moved out of the TopAuto workspace into its own repo.
- `fixtures/test-identities.js`: creates BASIC, STANDARD and platform-admin test identities in a local database (dry run by default, refuses remote hosts).
- `env.example`, `Makefile`, `bin/orchestrator`, `AGENTS.md`.

### Changed
- Settings split into `ENGINE_ROOT`, `WORKSPACE_ROOT` (sibling repos, default: parent folder) and `RESULTS_DIR` (default `results/`, previously `.antigravity/`); plus `ADMIN_WORKSPACE`.
- `.env` is read from this repo; unit tests ignore it.
- `UI_TEST_COMMAND` supports `{ADMIN_WORKSPACE}`; machine-specific tool paths removed from `config.json`.
- BASIC tenant ids configurable via `TEST_BASIC_COMPANY_ID` / `TEST_BASIC_EMPLOYEE_ID`.

### Fixed
- `make check` passes on a bare clone (a legacy test that needs the backend repo now skips).

## 2026-09 – 2026-10: inside the workspace

The engine was built in phases (catalog, real runners, release gate, preflight, dashboard). See [docs/history/](docs/history/README.md).
