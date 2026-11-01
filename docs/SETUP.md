# Setup, end to end

From an empty machine to a release-gate verdict. Each step says how to check it worked. Settings: [CONFIGURATION.md](CONFIGURATION.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

> **Use a local, disposable database.** The API pillar creates cars and sale letters, posts a cashflow transaction and changes container and attendance records (see [SECURITY.md](SECURITY.md#the-api-pillar-writes-data)). Never point `API_BASE_URL` at staging or production.

## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| Node.js + npm | 18+ | `node --version` |
| MongoDB | replica set `rs0` on `localhost:27017` (the backend needs transactions) | `mongosh --eval 'rs.status().ok'` |
| Google Chrome | any recent | used by Karma and Playwright |
| Apache JMeter | optional (performance pillar) | `jmeter --version`, macOS: `brew install jmeter` |
| GNU make | optional (every target is a plain command) | `make --version` |

## 1. Clone the repos side by side

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

## 2. Prepare the backend and admin repos

Follow each repo's own README. In short:

```bash
cd ~/workspace/topautokh-api && npm install     # then create its .env (MONGO_URI, JWT_SECRET, …)
cd ~/workspace/top-auto-1653-admin-page && npm install
```

Use the branch you want to validate (today the team's latest are `enhancement-cluster-v1.0` for the API and `enhance-v1.2` for the admin).

## 3. Set up this repo

```bash
cd ~/workspace/automation-testing
make setup        # creates .env from env.example, installs Playwright + Chromium, creates results/
```

Open `.env` and check:

- `API_BASE_URL` (default `http://localhost:3000`), and `BASE_URL` for the admin UI (default `http://localhost:4200`).
- `MONGODB_URI`/`MONGO_URI` for your local database.
- `JWT_SECRET`: leave it empty to read it from the backend's own `.env` at run time. It is never printed.
- Leave the `TEST_*` identity values empty for now; step 7 fills them.

## 4. Offline self-check (no services needed)

```bash
make check        # compiles every module and runs the engine's 177 unit tests (~30 s)
make status       # prints the resolved paths, URLs and tools
make catalog      # 63 features / 101 test cases, coverage per module
```

`make status` must show the right `WORKSPACE_ROOT`, `BACKEND_WORKSPACE` and `ADMIN_WORKSPACE`. If a path is wrong, fix `.env`.

## 5. Start the stack (in your own terminals)

The engine never starts servers. Start them yourself and keep them running:

```bash
# terminal 1: MongoDB replica set (if it isn't already a service)
mongod --replSet rs0 --dbpath <your-db-path>      # first time only: mongosh --eval 'rs.initiate()'

# terminal 2: backend
cd ~/workspace/topautokh-api && npm run dev        # → http://localhost:3000

# terminal 3: admin UI (only needed for the Playwright specs in step 9)
cd ~/workspace/top-auto-1653-admin-page && npm start   # → http://localhost:4200
```

## 6. Preflight

```bash
make preflight
```

You want `VERDICT: READY`, with all 8 required checks passing. Every WARN/FAIL line has a `→` fix underneath. "Backend health endpoint: WARN" means the backend from step 5 isn't reachable on `API_BASE_URL`.

## 7. Create the test identities (once per database)

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

## 8. Run the engine

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

## 9. Optional: Playwright E2E against the running admin UI

```bash
# needs the admin on BASE_URL and TEST_PHONE / TEST_PASSWORD of a user with at least one company
make ui-specs           # 14 specs: auth, dashboard, cashflow, car sales
```

## 10. Read the results

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
