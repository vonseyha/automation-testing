# Changelog

All notable changes to this repo. Newest first.

## Unreleased

### Added
- **Basic-plan test identity** (`TEST_BASIC_PLAN_COMPANY_ID` / `TEST_BASIC_PLAN_EMPLOYEE_ID`) for the 3 `FEATURE_NOT_IN_PLAN` cases, separate from the BASIC tenant (whose default company may be on a higher plan). Unset → those cases are BLOCKED instead of failing. The fixture script prints these lines, and prints `TEST_BASIC_*` only when the team default company is absent. 6 unit tests.
- **Remote-target guard:** a non-local `API_BASE_URL` / `SECURITY_BASE_URL` makes the backend suites BLOCKED (no request sent) unless `ALLOW_REMOTE_TARGET=1`; new required preflight check "Target is a local backend" (preflight now has 13 checks, 8 required). 9 unit tests.
- Full documentation set in `docs/`: SETUP, USER_GUIDE, ARCHITECTURE, CONFIGURATION, TESTING, DEVELOPMENT, OPERATIONS, SECURITY, TROUBLESHOOTING, DEPLOYMENT_READINESS, plus an index. `CONTRIBUTING.md` and this changelog.

### Fixed
- `make check` is now really offline. Two unit tests drove the real runners against `localhost:3000`, so with the backend running they sent live API/login traffic and waited on the rate limiter, and several tests saved stub runs ("READY FOR ROLLOUT") into the real `results/`. The test package now points `API_BASE_URL`/`SECURITY_BASE_URL` at a closed port and `RESULTS_DIR` at a temp folder.

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
