# Troubleshooting

Start with `make status` (are the paths and URLs right?) and `make preflight` (is the environment ready?). Every BLOCKED case also carries a `required_remediation` in its result and on the dashboard.

## Setup and environment

| Symptom | Cause | Fix |
|---|---|---|
| `make status` shows the wrong `BACKEND_WORKSPACE` / `ADMIN_WORKSPACE` | repos aren't next to this one | set `WORKSPACE_ROOT` or the specific path in `.env` ([CONFIGURATION.md](CONFIGURATION.md#path-resolution)) |
| preflight FAIL "Backend workspace not found" / "node_modules not installed" | backend repo missing or not installed | clone it / `npm install` in it, or fix `BACKEND_WORKSPACE` |
| preflight FAIL "Backend environment variables" | the backend has no `.env` with `MONGO_URI` and `JWT_SECRET`, and they aren't exported | create the backend's `.env` (see its README) |
| preflight FAIL MongoDB connectivity | `mongod` not running / wrong host | start MongoDB with `--replSet rs0`; check `MONGO_URI` |
| preflight FAIL "Target is a local backend"; API/security/performance BLOCKED with "Remote target refused" | `API_BASE_URL` (or `SECURITY_BASE_URL`) isn't localhost | point it at your local backend; only for a disposable test environment, set `ALLOW_REMOTE_TARGET=1` |
| preflight WARN "Backend health endpoint" | backend not running on `API_BASE_URL` | `npm run dev` in the backend (your terminal), or fix `API_BASE_URL` |
| `make check` fails right after you edited `.env` | it shouldn't: unit tests ignore `.env` | an **exported** variable leaks in: `env \| grep -E 'WORKSPACE\|RESULTS\|API_BASE'` |
| `make check` fails on a bare clone | a test needs a sibling repo | clone the backend next to this repo; that test skips automatically if it's absent |

## Test results

| Symptom | Cause | Fix |
|---|---|---|
| `CONN-001` FAILED; API, security and performance all BLOCKED | backend unreachable | start the backend; BLOCKED is expected here, it isn't a defect |
| `API-ENT-PAY-001` / `-HR-001` / `-SALARY-001` FAILED: expected 403, got 200 | the company they run as isn't on the Basic plan (e.g. `TEST_BASIC_PLAN_*` points at a STANDARD/PREMIUM company) | point `TEST_BASIC_PLAN_*` at the `aaa…020` fixture company (`make fixtures-apply`) |
| API cases BLOCKED with `FIXTURE_MISSING_BASIC_PLAN_TENANT` / `FIXTURE_MISSING_PREMIUM_TENANT` / `FIXTURE_MISSING_PLATFORM_ADMIN` | identity ids not set | `make fixtures-apply`, then copy the printed `TEST_*` lines into `.env` |
| Most API cases 401 "Employee not found" on a fresh DB | `TEST_BASIC_*` not set, so the team dev-DB ids are used | `make fixtures-apply`; set `TEST_BASIC_COMPANY_ID` / `TEST_BASIC_EMPLOYEE_ID` |
| 401s although fixtures exist | `JWT_SECRET` differs from the running backend's, or the DB was reset | align the secret (leave it empty to read the backend's `.env`); rerun `make fixtures-apply` |
| 403 `EMPLOYEE_INACTIVE` | the DB has no `codedefinitions` "Employee Status → Active" row, so the fixture employee has no status | seed the backend's code definitions, run `make fixtures-cleanup` and then `make fixtures-apply` |
| 403 `PLATFORM_COMPANY_REQUIRED` | the platform admin isn't under the DB's `isPlatform` company | `make fixtures` shows which platform company is used; set `TEST_PLATFORM_COMPANY_ID` to it |
| A handful of car / container / sale / attendance cases fail with 404 or 400 | those cases target fixed record IDs from the team dev DB ([known limitation](DEPLOYMENT_READINESS.md#known-limitations)) | use a copy of the team dev DB, or accept these as environment failures |
| Security cases get 429 instead of 401/400 | backend login rate limiter (15-minute window, in memory) | wait 15 minutes or restart the backend; the API runner itself waits up to `RATE_LIMIT_MAX_WAIT` |
| A run seems to hang | the full sequential run takes 10–15 min; the API suite alone 5–10 | `make test-parallel`, or `make pillar P=…` |
| UI suite BLOCKED "node_modules not installed" | admin deps missing | `npm install` in the admin repo, or fix `ADMIN_WORKSPACE` |
| UI suite FAILED | the admin's own Karma specs fail | open `results/evidence/<run>/ui_execution.log`; it's an admin issue, not an engine one |
| `make ui-specs` fails at login | admin not on `BASE_URL`, or `TEST_PHONE`/`TEST_PASSWORD` not a real user with a company | start the admin; set real test credentials in `.env` |
| Playwright "browser not found" | Chromium not installed | `cd orchestration/ui_tests && npx playwright install chromium` (or `make setup`) |
| Performance BLOCKED | JMeter not found | install JMeter (`brew install jmeter`) or set `JMETER_PATH` |
| AI Grounding BLOCKED (`AIG-001`) | no Agentforce Testing Center configured | expected; it's optional and doesn't affect the gate |
| Gate says VALIDATION INCOMPLETE although nothing failed | a required suite didn't run (e.g. `--pillar` filter) or passed without evidence | run the full set: `make test` |

## Dashboard and results

| Symptom | Fix |
|---|---|
| Dashboard empty | no runs in `RESULTS_DIR` yet; run `make test`, or point `RESULTS_DIR` at older results |
| Port 8470 in use | `DASHBOARD_PORT=8471 make dashboard` |
| A run file can't be parsed | a run was interrupted mid-write; delete that `results/test_runs/<id>.json` |
| `results/` is getting big | see [OPERATIONS.md › Retention](OPERATIONS.md#retention) |

## Fixture script

| Symptom | Fix |
|---|---|
| `Refusing to touch non-local MongoDB host` | intended. For a disposable remote test DB only: `ALLOW_REMOTE_FIXTURES=1` |
| `…/node_modules not found` | the script borrows `mongodb` and `bcryptjs` from the backend: `npm install` there, or set `BACKEND_WORKSPACE` |
| `warning: no codedefinitions "Employee Status" → "Active" row` | the DB isn't seeded with the backend's code definitions; seed it first |
