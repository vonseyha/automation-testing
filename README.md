# automation-testing

Pre-release test engine for the TopAuto (Auto360) stack. It runs **101 test cases in six pillars** against your locally running backend and admin UI, saves evidence for each case, and ends with a release-gate verdict: **READY FOR ROLLOUT**, **NOT READY** or **VALIDATION INCOMPLETE**.

| Pillar | Cases | What it checks | Needs |
|---|---:|---|---|
| API & Integration | 73 | TCP probe + real HTTP calls: auth, tenancy, entitlements, cars, finance, HR, payroll… | backend on `API_BASE_URL`, MongoDB, `JWT_SECRET`, test identities |
| Security & Access | 16 | missing/malformed tokens, authz/RBAC, NoSQL injection, SSRF, security headers | backend, `JWT_SECRET` |
| Penetration | 7 | prompt-injection / jailbreak / data-exfiltration probes (offline guardrail + optional AI judge) | nothing extra |
| UI & Channel | 3 | the admin's Angular unit suite (`npm run test:ci`, headless Chrome) | admin repo with `node_modules`, Chrome |
| Performance | 1 | JMeter smoke/load plan (`orchestration/performance/smoke_test.jmx`) | backend, JMeter |
| AI Grounding | 1 | Agentforce Testing Center batch | optional; BLOCKED unless configured |

The engine itself is **pure Python 3.9+ standard library**: no `pip install`. Node is only needed for the Playwright specs and the fixture script.

---

## Repository layout

```
automation-testing/
├── README.md               ← you are here (setup end to end)
├── env.example             ← copy to .env (make setup)
├── Makefile                ← every common command (make help)
├── bin/orchestrator        ← CLI wrapper, works from any directory
├── fixtures/
│   └── test-identities.js  ← creates the synthetic test tenant + platform admin in the LOCAL DB
├── orchestration/          ← the Python package
│   ├── cli.py, config.py, config.json
│   ├── test_engine/        ← runners, catalogs, release gate, preflight, reporting
│   ├── ui_tests/           ← Playwright E2E specs against the admin UI
│   ├── performance/        ← JMeter plan
│   ├── dashboard/          ← local read-only results dashboard
│   └── tests/              ← the engine's own unit tests (168)
├── docs/
│   ├── USER_GUIDE.md           ← pillars, execution modes, scenarios, daily usage
│   ├── ENGINE_REFERENCE.md     ← architecture, config reference, troubleshooting, server deployment
│   ├── ORCHESTRATION_GUIDE.md  ← Master Agent + reviewer (Gemini) loop
│   └── rules/                  ← model-selection and escalation rules for the Master Agent
└── results/                ← test runs, evidence, audit logs (gitignored, created on first run)
```

---

## End-to-end setup

### 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| Node.js + npm | 18+ | `node --version` |
| MongoDB | replica set `rs0` on `localhost:27017` (the backend needs transactions) | `mongosh --eval 'rs.status().ok'` |
| Google Chrome | any recent | used by Karma and Playwright |
| Apache JMeter | optional (performance pillar) | `jmeter --version`, macOS: `brew install jmeter` |
| GNU make | optional (every target is a plain command) | `make --version` |

### 1. Clone the repos side by side

The engine finds the other repos next to itself by default:

```
workspace/
├── automation-testing/          ← this repo
├── topautokh-api/               ← backend (BACKEND_WORKSPACE)
└── top-auto-1653-admin-page/    ← Angular admin (ADMIN_WORKSPACE)
```

```bash
mkdir -p ~/workspace && cd ~/workspace
git clone https://github.com/vonseyha/automation-testing.git
git clone <topautokh-api repo URL> topautokh-api
git clone <admin repo URL> top-auto-1653-admin-page
```

Already have the repos somewhere else? Keep them there and set `WORKSPACE_ROOT`, `BACKEND_WORKSPACE` or `ADMIN_WORKSPACE` in `.env` (step 3).

### 2. Prepare the backend and admin repos

Follow each repo's own README. In short:

```bash
cd ~/workspace/topautokh-api && npm install     # then create its .env (MONGO_URI, JWT_SECRET, …)
cd ~/workspace/top-auto-1653-admin-page && npm install
```

Use the branch you want to validate (today the team's latest are `enhancement-cluster-v1.0` for the API and `enhance-v1.2` for the admin).

### 3. Set up this repo

```bash
cd ~/workspace/automation-testing
make setup        # creates .env from env.example, installs Playwright + Chromium, creates results/
```

Open `.env` and check:

- `API_BASE_URL` (default `http://localhost:3000`), and `BASE_URL` for the admin UI (default `http://localhost:4200`).
- `MONGODB_URI`/`MONGO_URI` for your local database.
- `JWT_SECRET`: leave it empty to read it from the backend's own `.env` at run time. It is never printed.
- Leave the `TEST_*` identity values empty for now; step 7 fills them.

### 4. Offline self-check (no services needed)

```bash
make check        # compiles every module and runs the engine's 168 unit tests (~30 s)
make status       # prints the resolved paths, URLs and tools
make catalog      # 63 features / 101 test cases, coverage per module
```

`make status` must show the right `WORKSPACE_ROOT`, `BACKEND_WORKSPACE` and `ADMIN_WORKSPACE`. If a path is wrong, fix `.env`.

### 5. Start the stack (in your own terminals)

The engine never starts servers. Start them yourself and keep them running:

```bash
# terminal 1: MongoDB replica set (if it isn't already a service)
mongod --replSet rs0 --dbpath <your-db-path>      # first time only: mongosh --eval 'rs.initiate()'

# terminal 2: backend
cd ~/workspace/topautokh-api && npm run dev        # → http://localhost:3000

# terminal 3: admin UI (only needed for the Playwright specs in step 9)
cd ~/workspace/top-auto-1653-admin-page && npm start   # → http://localhost:4200
```

### 6. Preflight

```bash
make preflight
```

You want `VERDICT: READY`, with all 7 required checks passing. Every WARN/FAIL line has a `→` fix underneath. "Backend health endpoint: WARN" means the backend from step 5 isn't reachable on `API_BASE_URL`.

### 7. Create the test identities (once per database)

The API and security pillars sign JWTs for three identities: a **BASIC tenant** admin, a **STANDARD tenant** admin and a **platform admin**. Create them in your **local** database:

```bash
make fixtures          # dry run: shows which records exist / are missing
make fixtures-apply    # creates the missing ones (idempotent, fixed aaa… ObjectIds)
```

Copy the printed lines into `.env`:

```
TEST_BASIC_COMPANY_ID=aaa000000000000000000020
TEST_BASIC_EMPLOYEE_ID=aaa000000000000000000021
TEST_PREMIUM_COMPANY_ID=aaa000000000000000000001
TEST_PREMIUM_EMPLOYEE_ID=aaa000000000000000000002
TEST_PLATFORM_COMPANY_ID=aaa000000000000000000010   # or your existing isPlatform company
TEST_PLATFORM_ADMIN_ID=aaa000000000000000000011
```

If `TEST_BASIC_*` is left empty, the engine falls back to the "Top Auto Default" company of the team's dev database. That only works if your DB is a copy of it.

The script refuses non-localhost MongoDB URIs unless `ALLOW_REMOTE_FIXTURES=1` is set. `make fixtures-cleanup` removes the records again. It keeps the platform company, because the app may depend on it; add `--include-platform` to delete that too.

### 8. Run the engine

```bash
make test               # all six pillars, sequential (minutes; longer if the API runner waits out the rate limiter)
make test-parallel      # same, pillars in parallel
make pillar P=api       # one pillar: ui | api | perf | security | pen | grounding
```

The command prints the scorecard and the release gate, and exits `0` only for **READY FOR ROLLOUT**.

| Verdict | Meaning |
|---|---|
| READY FOR ROLLOUT | the required suites (API & Integration, Security & Access, Penetration) all PASSED with evidence |
| NOT READY | a required suite FAILED or was BLOCKED. Read its failure / `required_action` |
| VALIDATION INCOMPLETE | a required suite never ran or is still PENDING |

UI, Performance and AI Grounding are informational: their failures show as warnings but don't block the gate.

**Dependencies:** API & Integration, Security & Access and Performance all wait on the TCP probe `CONN-001`. If the backend is down, that probe FAILS and those suites are BLOCKED (not failed). The fix is to start the backend, not to change the tests.

### 9. Optional: Playwright E2E against the running admin UI

```bash
# needs the admin on BASE_URL and TEST_PHONE / TEST_PASSWORD of a user with at least one company
make ui-specs           # 14 specs: auth, dashboard, cashflow, car sales
```

### 10. Read the results

```bash
make runs               # recent runs with pass / fail / blocked counts
make dashboard          # http://localhost:8470: runs, pillars, gate, evidence (Ctrl+C to stop)
```

Everything is in `results/` (or `RESULTS_DIR`):

```
results/
├── test_runs/<run_id>.json        ← full run document (every test case, status, timing)
├── evidence/<run_id>/             ← connectivity_probe.json, api_response.json, ui_execution.log,
│                                    security_audit.json, penetration_evaluation_report.json,
│                                    jmeter_results.jtl, dashboard.md …
└── audit/                         ← command and orchestration audit trail (JSONL + Markdown)
```

---

## Configuration reference

Settings are layered: `orchestration/config.json` < `.env` < exported shell variables. Relative paths in `WORKSPACE_ROOT` and `RESULTS_DIR` resolve against this repo; `BACKEND_WORKSPACE` and `ADMIN_WORKSPACE` resolve against `WORKSPACE_ROOT`.

| Variable | Default | Used for |
|---|---|---|
| `WORKSPACE_ROOT` | parent of this repo | where the sibling repos live |
| `BACKEND_WORKSPACE` | `$WORKSPACE_ROOT/topautokh-api` | preflight, JWT secret fallback, static pillar checks |
| `ADMIN_WORKSPACE` | `$WORKSPACE_ROOT/top-auto-1653-admin-page` | UI pillar (`test:ci`) |
| `RESULTS_DIR` | `./results` | test runs, evidence, audit |
| `API_BASE_URL` | `http://localhost:3000` | API, security and performance pillars |
| `BASE_URL` / `API_URL` | `http://localhost:4200` / `:3000` | Playwright specs |
| `MONGODB_URI` / `MONGO_URI` | local `topauto1653_ecommerce`, `rs0` | fixtures / preflight |
| `JWT_SECRET` | read from the backend's `.env` | signing test JWTs |
| `TEST_BASIC_*`, `TEST_PREMIUM_*`, `TEST_PLATFORM_*` | empty (BASIC falls back to the team dev-DB ids) | test identities (step 7) |
| `TEST_PHONE`, `TEST_PASSWORD` | empty | Playwright login |
| `UI_TEST_COMMAND` | `npm --prefix "{ADMIN_WORKSPACE}" run test:ci` | UI pillar command (`{ADMIN_WORKSPACE}`, `{WORKSPACE_ROOT}` placeholders) |
| `JMETER_PATH`, `JMETER_TEST_PLAN` | `jmeter` on PATH, bundled plan | performance pillar |
| `GEMINI_API_KEY` | empty | only for `bin/orchestrator run` (Master Agent); tests don't need it |
| `AUTOMATION_ENV_FILE` | `.env` | use another settings file |

`env.example` lists every variable with comments. The full table is in [docs/ENGINE_REFERENCE.md](docs/ENGINE_REFERENCE.md).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Everything except UI/penetration is BLOCKED, `CONN-001` FAILED | Backend not reachable on `API_BASE_URL`: start it (step 5) |
| API tests BLOCKED with `FIXTURE_MISSING_PREMIUM_TENANT` / `…PLATFORM_ADMIN` | Step 7: create the identities and put the IDs in `.env` |
| Most API tests fail with 401 `Employee not found` on a fresh DB | `TEST_BASIC_*` not set: run step 7 and copy the `TEST_BASIC_*` lines |
| 401s on tenant tests | `JWT_SECRET` differs from the running backend's, or the DB was reset (rerun `make fixtures-apply`) |
| `EMPLOYEE_INACTIVE` (403) | Your DB has no `codedefinitions` "Employee Status → Active" row; seed the backend's code definitions, then rerun the fixtures |
| UI pillar BLOCKED: `node_modules not installed` | `npm install` in the admin repo, or fix `ADMIN_WORKSPACE` |
| Performance BLOCKED | Install JMeter or set `JMETER_PATH` |
| AI Grounding BLOCKED | Expected unless you use Agentforce Testing Center |
| Rate-limit waits (429) during API tests | Normal; the runner waits up to `RATE_LIMIT_MAX_WAIT` seconds |
| `make check` fails after you edited `.env` | It shouldn't: unit tests ignore `.env`. Check for exported variables (`env \| grep -E 'API_BASE_URL\|WORKSPACE'`) |

More: [docs/ENGINE_REFERENCE.md › Troubleshooting](docs/ENGINE_REFERENCE.md).

---

## Contributing

- Run `make check` before every commit; it must stay green.
- New application test cases go in `orchestration/test_engine/catalog/` and the matching runner; see `docs/ENGINE_REFERENCE.md`.
- **This repo is public.** Never commit `.env`, secrets, real phone numbers / customer data, `results/`, or internal security findings. Use placeholders and environment variables.
