# Configuration

Every setting, where it comes from, and how paths resolve. Start from `env.example` (`make setup` copies it to `.env`). Run `make status` at any time to see the resolved values.

## Layering

Later layers win:

1. Defaults in `orchestration/config.py`
2. `orchestration/config.json` (committed team defaults)
3. `<repo>/.env` (your machine; gitignored). Another file can be used via `AUTOMATION_ENV_FILE=path`.
4. Exported shell variables
5. Explicit overrides in code (used by the unit tests)

`.env` never overrides an exported variable. The unit tests set `AUTOMATION_SKIP_ENV_FILE=1`, so a local `.env` can't change their results.

## Path resolution

| Setting | Default | Relative values resolve against |
|---|---|---|
| `ENGINE_ROOT` (fixed) | this repo | — |
| `WORKSPACE_ROOT` | parent of this repo | `ENGINE_ROOT` |
| `BACKEND_WORKSPACE` | `$WORKSPACE_ROOT/topautokh-api` | `WORKSPACE_ROOT` |
| `ADMIN_WORKSPACE` | `$WORKSPACE_ROOT/top-auto-1653-admin-page` | `WORKSPACE_ROOT` |
| `RESULTS_DIR` | `$ENGINE_ROOT/results` | `ENGINE_ROOT` |
| `JMETER_TEST_PLAN` | `orchestration/performance/smoke_test.jmx` | `ENGINE_ROOT` |

`~` is expanded everywhere. Example: to test a backend worktree, set `BACKEND_WORKSPACE=topautokh-api.latest`.

## Target stack

| Variable | Default | Used by |
|---|---|---|
| `API_BASE_URL` | `http://localhost:3000` | connectivity, API, security, performance |
| `API_HEALTH_ENDPOINT` | `/health` | health probes |
| `SECURITY_BASE_URL` | = `API_BASE_URL` | security suite |
| `ALLOW_REMOTE_TARGET` | unset | `1` lets the engine target a non-local backend (disposable test environments only). Without it, backend suites are BLOCKED ([SECURITY.md](SECURITY.md#remote-target-guard)) |
| `BASE_URL` | `http://localhost:4200` | Playwright specs (admin UI) |
| `API_URL` | `http://localhost:3000` | Playwright login helper |
| `MONGODB_URI` | `mongodb://localhost:27017/topauto1653_ecommerce?replicaSet=rs0` | `fixtures/test-identities.js` |
| `MONGO_URI` | read from the backend's `.env` | preflight's MongoDB check |

## Authentication and identities

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | read from `$BACKEND_WORKSPACE/.env` | must match the running backend; never printed |
| `TEST_BASIC_COMPANY_ID`, `TEST_BASIC_EMPLOYEE_ID` | team dev-DB ids | BASIC tenant admin (most API cases) |
| `TEST_PREMIUM_COMPANY_ID`, `TEST_PREMIUM_EMPLOYEE_ID` | empty | STANDARD/PREMIUM tenant (payroll/HR cases) |
| `TEST_PREMIUM_PHONE`, `TEST_PREMIUM_PASSWORD` | empty | optional real login instead of a minted JWT |
| `TEST_PLATFORM_COMPANY_ID`, `TEST_PLATFORM_ADMIN_ID` | empty | platform admin (`admin-auth` token) |
| `TEST_ADMIN_PHONE`, `TEST_ADMIN_PASSWORD` | empty | optional real login for the BASIC admin |
| `TEST_PHONE`, `TEST_PASSWORD` | placeholders | Playwright UI login |
| `RATE_LIMIT_MAX_WAIT` | `920` | seconds the API runner may wait out a 429 |

Create the identities with `make fixtures-apply` ([SETUP.md](SETUP.md#7-create-the-test-identities-once-per-database)). Fixture script options: `ALLOW_REMOTE_FIXTURES=1` permits a non-localhost MongoDB host (disposable test DBs only).

## Tools

| Variable | Default | Notes |
|---|---|---|
| `UI_TEST_COMMAND` | `npm --prefix "{ADMIN_WORKSPACE}" run test:ci` (config.json) | `{ADMIN_WORKSPACE}` and `{WORKSPACE_ROOT}` are substituted; runs with cwd `WORKSPACE_ROOT` |
| `ENABLE_ANGULAR_HEADLESS_TEST` | `true` (config.json) | allows the admin Karma suite as the UI engine |
| `JMETER_PATH` / `JMETER_HOME` | `jmeter` on `PATH` | performance suite |
| `JMETER_TEST_PLAN` | bundled plan | see path resolution |
| `DASHBOARD_PORT` | `8470` | `make dashboard` (binds to localhost only) |

## Optional integrations

| Variable | Used for |
|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Master Agent (`bin/orchestrator run`) and the penetration suite's AI judge |
| `GEMINI_API_ENDPOINT` (config.json only, no env override) | default `https://generativelanguage.googleapis.com/v1beta` |
| `PRIMARY_MODEL`, `REVIEW_MODEL`, `*_THINKING_LEVEL` | Master Agent / reviewer model ids |
| `REVIEW_ENABLED`, `REVIEW_MAX_ITERATIONS`, `REVIEW_ON_*` | escalation policy |
| `OLLAMA_BASE_URL` | optional local model client (`http://localhost:11434`) |
| `TESTING_CENTER_API_URL` (`AGENTFORCE_TESTING_CENTER_URL`), `AGENTFORCE_REGRESSION_BATCH_ID`, `AGENTFORCE_API_TOKEN`, `AGENTFORCE_TEST_RUNNER` | AI grounding suite |
| `SECURITY_PROVIDER` (`local`), `SF_TARGET_ORG`, `SF_CLI_PATH`, `SECURITY_VALIDATION_COMMAND` | alternative security providers |

## `config.json`

Holds the committed team defaults (model ids, review policy, UI command, Angular headless flag, API URL). Keep machine-specific paths and secrets **out** of it; they belong in `.env`.
