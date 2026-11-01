# Operations

Running the engine day to day, keeping results, and scheduling it. First-time setup is in [SETUP.md](SETUP.md).

## Daily routine

```bash
cd automation-testing && git pull
make check                 # engine still healthy (30 s)
# start MongoDB, backend (and admin for UI specs) in your own terminals
make preflight             # environment OK?
make test                  # full run → gate verdict
make dashboard             # look at it: http://localhost:8470
```

Before a release, run against the **branch being released** (check out the backend/admin branches first), and keep the run ID in the release notes.

| Situation | Command |
|---|---|
| Changed only backend finance code | `make pillar P=api` (then a full run before release) |
| Security-sensitive change (auth, RBAC, JWT) | `make pillar P=security` and `make pillar P=pen` |
| Faster full run | `make test-parallel` (up to 4 suites at once) |
| Admin UI change | `make pillar P=ui` and `make ui-specs` (admin must be running for the specs) |
| Something looks off | `make status` → `make preflight` → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

## Reading results

- **Console:** the scorecard, then `Release Gate: …` with blocking reasons and warnings. Exit code `0` = READY FOR ROLLOUT.
- **Run history:** `make runs` (`bin/orchestrator test --runs`).
- **Dashboard:** `make dashboard`. It's read-only and binds to `127.0.0.1:${DASHBOARD_PORT:-8470}`. It shows runs, pillar breakdown, the gate, findings, and per-case evidence links.
- **Files:** `results/test_runs/<run_id>.json` (whole run) and `results/evidence/<run_id>/` (one file per evidence item, plus `dashboard.md`).
- **Audit trail:** `bin/orchestrator audit -n 10` (Master Agent decisions), `results/audit/command_execution_audit.jsonl` (agent commands).

To browse the history recorded before the move to this repo, point the dashboard at it: `RESULTS_DIR=/path/to/old/.antigravity make dashboard`.

## Retention

Nothing is deleted automatically, and evidence grows by roughly 1 MB per full run. Clean up now and then:

```bash
find results/test_runs -name '*.json' -mtime +90 -delete
find results/evidence -mindepth 1 -maxdepth 1 -type d -mtime +90 -exec rm -rf {} +
```

Back up `results/` (or `RESULTS_DIR`) if you need to keep release evidence: `tar czf results-$(date +%Y%m%d).tar.gz results/`.

## Local database hygiene

The API suite writes test data ([SECURITY.md](SECURITY.md#the-api-pillar-writes-data)). Keep a dump of your clean dev database and restore it when the test cars, sale letters and cashflow rows get in the way. After a restore, rerun `make fixtures-apply`.

## CI and scheduled runs

**Every change to this repo:** run `make check`. It needs only Python 3.9 and Node, with no services.

**Full engine in CI:** the job has to provide the stack:
1. Check out `automation-testing`, `topautokh-api` and `top-auto-1653-admin-page` side by side.
2. Start a **disposable** MongoDB replica set and seed it from a dev dump.
3. `npm ci` in the backend and admin; start the backend in the background and wait for `/health`.
4. Provide `JWT_SECRET` and the `TEST_*` ids as CI secrets (never commit them). Run `node fixtures/test-identities.js --apply`.
5. `make preflight && make test`; the exit code is the gate. Archive `results/` as a build artifact.

The workspace's Harness pipeline (`.harness/pipeline.yaml`, outside this repo) has a stage for this; it assumes the side-by-side layout.

**Nightly (cron on a dev server):**

```cron
0 2 * * * cd /opt/autopilot/workspace/automation-testing && make test >> /opt/autopilot/logs/test-$(date +\%Y\%m\%d).log 2>&1
```

## Running on a server

The engine runs on Linux as well as macOS (Windows is untested). Minimal recipe:

1. Python 3.9+, Node 18+, JMeter (optional), Chrome/Chromium for the UI suite.
2. A dedicated user, with the repos cloned side by side under one folder (e.g. `/opt/autopilot/workspace`).
3. `.env` readable only by that user (`chmod 600`).
4. Batch runs via cron as above; the dashboard as a systemd service running `python3 orchestration/dashboard/serve.py` in the repo.
5. To expose the dashboard, put it behind a reverse proxy with TLS and authentication. It has no auth of its own and listens on localhost only.

The full server guide (systemd unit, nginx example, containerization notes, deploy/rollback) is kept in [history/ENGINE_REFERENCE.md](history/ENGINE_REFERENCE.md#server-deployment-guide).

## Updating the engine

```bash
git pull && make check && make preflight
```

If you run the dashboard as a service, restart it after pulling.
