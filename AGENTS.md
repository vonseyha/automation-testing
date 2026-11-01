# automation-testing: notes for AI coding tools

- Setup and usage: `README.md`. Engine internals: `docs/ENGINE_REFERENCE.md`.
- Python 3.9+ standard library only. Don't add pip dependencies without a strong reason.
- Verify every change with `make check` (compile + 168 unit tests, ~30 s, no services needed).
- Paths: `ENGINE_ROOT` = this repo; `WORKSPACE_ROOT` = folder with the sibling repos (default: parent dir); `RESULTS_DIR` = run output (default `results/`, gitignored). Engine-owned files (`orchestration/performance`, `orchestration/ui_tests`) resolve from the package, never from `WORKSPACE_ROOT`.
- Unit tests set `AUTOMATION_SKIP_ENV_FILE=1`, and tests that build a config pass `results_dir=<tmp>`. Keep it that way so tests never depend on a local `.env` or write into a real results folder.
- Never start the backend, admin UI or MongoDB; the user runs them. `fixtures/test-identities.js --apply` writes to the DB: run it only when asked, and only against a local test DB.
- **Public repo:** no secrets, `.env`, real phone numbers / customer data, `results/` or internal security findings in commits.
