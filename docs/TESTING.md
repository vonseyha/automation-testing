# Testing

This repo has two kinds of tests. Keep them apart:

| | **Application test catalog** | **Engine unit tests** |
|---|---|---|
| What | 101 checks against the TopAuto stack | 177 tests of this engine's own code |
| Command | `make test` / `make pillar P=…` | `make check` |
| Needs | running backend, MongoDB, fixtures, tools | Python only |
| Result | release-gate verdict + `results/` evidence | pass/fail (CI gate for this repo) |

## 1. Application test catalog

The source of truth is `orchestration/test_engine/catalog/test_catalog.py` (test cases) and `functionality_catalog.py` (63 features). Each case maps to one feature and one runner, so coverage is traceable in both directions:

```bash
make catalog                                        # coverage per module and priority
bin/orchestrator catalog --tests --module "Finance & Cashflow"
bin/orchestrator catalog --traceability             # feature ↔ test matrix
bin/orchestrator catalog --priority P0 --json
```

> The `*.json` files next to the catalogs are old snapshots (95 cases). No code reads them, and they're out of date; trust the `.py` catalogs.

### By suite

| Runner | Cases | ID prefixes |
|---|---:|---|
| `api_integration` | 72 | `API-*` (`API-AUTH`, `API-CAR`, `API-FIN`, `API-PAY`, `API-HR`, `API-ENT-*`, `API-SALE`, …) |
| `security_access` | 16 | `SEC-AUTH`, `SEC-AUTHZ`, `SEC-API`, `SEC-RBAC` |
| `penetration` | 7 | `SEC-01`…`SEC-07` |
| `ui_channel` | 3 | `UI-AUTH-001`, `UI-CASHFLOW-001`, `UI-FILTER-001` |
| `api_connectivity` | 1 | `CONN-001` |
| `performance` | 1 | `PERF-001` |
| `ai_grounding` | 1 | `AIG-001` |

### By module

| Module | Cases | | Module | Cases |
|---|---:|---|---|---:|
| Authentication & Identity | 17 | | HR & Attendance | 7 |
| System & Integrations | 16 | | Sales & Invoicing | 7 |
| Finance & Cashflow | 11 | | Payroll & Compensation | 6 |
| Car Inventory Management | 8 | | Entitlement Enforcement | 5 |
| Access Control & RBAC | 7 | | Reports & Analytics | 4 |
| Container & Logistics | 3 | | Customer & Vendor | 3 |
| Preparation & Spare Parts | 3 | | Technical Inspection & QC | 3 |
| Security & Rate Limiting | 1 | | | |

Priorities: **P0 57**, P1 28, P2 14, P3 2.

### What a case checks

An API case (in `STANDARD_API_CASES`, `test_engine/runners/api_runner.py`) defines `endpoint`, `method`, `headers`, `data` and `expected_status` (one code or a list). Optional fields:
- `business_validation`: an extra assertion on the response body, e.g. `vehicle_creation`, `status_filter`, `state_transition`, `duplicate_rejection`, `sale_letter_created`;
- `requires_feature`: needs the STANDARD/PREMIUM identity (entitlement checks);
- `requires_platform_admin`: needs the platform-admin identity.

Every result records `expected`, `actual`, `evidence` and, when it isn't PASSED, `failure_reason` or `blocking_dependency` + `required_remediation`.

### Playwright E2E specs (separate)

`orchestration/ui_tests/` has 14 Playwright specs (auth, dashboard, cashflow, car sales) that drive the real admin UI on `BASE_URL`. Run them with `make ui-specs`. They're not in the 101-case catalog; the UI pillar uses the admin's Karma suite by default (`UI_TEST_COMMAND`).

### Reading a run

1. Gate verdict first ([ARCHITECTURE.md › Release gate](ARCHITECTURE.md#release-gate)).
2. FAILED cases are application defects or wrong expectations. Open their evidence file.
3. BLOCKED cases are environment problems. Their `required_remediation` says what to fix ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)).
4. Compare with the previous run: `make runs`, or the dashboard's history view.

## 2. Engine unit tests

```bash
make check      # python -m compileall + node --check fixtures + orchestration/tests/run_all_tests.py
```

Around 30 s, no services needed. They're isolated from your machine: `AUTOMATION_SKIP_ENV_FILE=1`, and tests that build a config pass `workspace_root`/`results_dir` pointing at a temp dir. Local HTTP stubs replace the backend.

| Module | Tests | Covers |
|---|---:|---|
| `test_dashboard_data` | 24 | dashboard parsing, status counts, pass-rate denominator, legacy formats |
| `test_reporting_and_dashboard` | 16 | scorecard and Markdown dashboard rendering |
| `test_real_test_engine` | 15 | runners against local stub servers, evidence on disk, backend workspace resolution |
| `test_command_security_policy` | 12 | allow / confirm / deny decisions, workspace boundary, audit |
| `test_remediation_regression` | 12 | regressions fixed in earlier phases |
| `test_release_gate_authoritative` | 9 | every gate outcome |
| `test_preflight` | 9 | preflight checks and verdicts |
| `test_escalation` | 8 | when the Master Agent escalates to the reviewer |
| `test_catalog_and_coverage` | 6 | catalog scope, accounting, traceability, CLI catalog |
| `test_ai_grounding_runner` | 6 | Agentforce runner against a stub |
| `test_ollama_client` | 6 | local model client |
| `test_penetration_runner` | 5 | guardrail baseline, judge evaluation, evidence |
| `test_security_provider` | 5 | security provider against a stub |
| `test_target_guard` | 9 | local/remote host detection, opt-in, preflight check, engine blocks backend suites without sending requests |
| others (10 modules) | 35 | config, sanitizer, contracts, model router, review loop, audit logger, Master Agent loop, orchestrator e2e, scorecard integrity, legacy pillar engine |

Two tests skip on a fresh clone: the dashboard-history checks need a saved run. One more skips when the backend repo isn't next to this one: the legacy static performance check greps its source.

### CI

`make check` is the gate for changes to this repo. A full `make test` needs a running stack. In CI, run it only in a job that starts the backend and a disposable MongoDB first; see [OPERATIONS.md](OPERATIONS.md#ci-and-scheduled-runs).
