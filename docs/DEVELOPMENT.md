# Development

How to change the engine safely. Read [ARCHITECTURE.md](ARCHITECTURE.md) first.

## Ground rules

- **Python 3.9 standard library only.** No pip dependencies without a strong reason (and then add a `requirements.txt` and update SETUP).
- **`make check` must stay green.** Run it before every commit.
- **Never resolve engine files from `WORKSPACE_ROOT`.** Use `Path(__file__)` or `OrchestrationConfig.engine_root`. `WORKSPACE_ROOT` is only for the sibling repos.
- **Write output only under `config.results_dir`.**
- **No secrets, real phone numbers or customer data in code or tests.** Use env vars and obvious placeholders ([SECURITY.md](SECURITY.md)).
- **BLOCKED, not FAILED,** when a precondition is missing. Always fill `blocking_dependency`, `missing_configuration` and `required_remediation`.

## Code map

```
orchestration/
├── cli.py                 commands and argument parsing
├── config.py              settings, path roots, BASIC-tenant id helpers
├── core_types.py          shared enums/dataclasses (TestPillar, ThinkingLevel, …)
├── test_engine/
│   ├── engine.py          TestEngine: runner registry, sequential/parallel execution
│   ├── contract.py        BaseTestRunner, TestCaseResult, TestExecutionResult, TestStatus
│   ├── dependency_engine.py, release_gate.py, storage.py, reporting.py, preflight.py
│   ├── runners/           one runner per suite
│   ├── security/provider.py   security-suite providers
│   ├── catalog/           features, test cases, coverage
│   └── pillars/           legacy static checks (don't extend)
├── master_agent/, orchestrator.py, escalation/, review/, models/   optional Gemini layer
├── security/              command policy + sanitizer
├── tools/                 workspace-bounded tools for the agent
├── audit/                 audit logger
├── dashboard/             local results UI
├── performance/           JMeter plan
├── ui_tests/              Playwright specs
└── tests/                 unit tests (unittest)
```

## Add an API test case

1. **Pick or add the feature** in `test_engine/catalog/functionality_catalog.py` (`feature_id`, module, criticality).
2. **Add the case** to `STANDARD_API_CASES` in `test_engine/runners/api_runner.py` (illustrative example):
   ```python
   {
       "id": "API-FIN-006",
       "name": "Cashflow summary returns totals for the current month",
       "endpoint": "/api/cashflow/summary?month=2026-11",
       "method": "GET",
       "expected_status": 200,               # or a list: [200, 404]
       "description": "…",
       "feature_id": "FIN-002",
       "module": "Finance & Cashflow",
       "priority": "P1",
       "headers": {},                        # the runner adds the Authorization header
       "data": None,
       # optional: "business_validation": {"type": "…"}, "requires_feature": "payroll",
       #           "requires_platform_admin": True
   }
   ```
3. **Add the catalog entry** with the same `test_case_id` to `test_engine/catalog/test_catalog.py` (steps, expected result, runner `api_integration`, status `IMPLEMENTED`).
4. **Keep it portable.** Don't hard-code record IDs from one database. Create what the case needs in an earlier case, or extend `fixtures/test-identities.js`.
5. **Prefer reads.** If the case must write, add it to the table in [SECURITY.md](SECURITY.md#the-api-pillar-writes-data).
6. Run `make check`. `test_catalog_and_coverage` fails if a runner case has no catalog metadata, or a feature has no test. Then run `make pillar P=api` against your local stack.

A new `business_validation` type needs a handler in `api_runner.py`. Look at how the existing types (`vehicle_creation`, `status_filter`, …) are dispatched, and add a unit test with a stub response.

## Add a security check

Add the tuple to the case list in `LocalApplicationSecurityProvider` (`test_engine/security/provider.py`, `("SEC-…", name, "METHOD /path", expected)`), implement its check method, add the catalog entry, and extend `tests/test_security_provider.py` with a stub response.

## Add a runner (new suite)

1. Subclass `BaseTestRunner` in `test_engine/runners/<name>_runner.py`. Implement `discover_test_cases()`, `validate_configuration()` (return `(False, reason)` when a tool or setting is missing) and `execute()`.
2. Save evidence through `self.storage.save_evidence_file(...)`.
3. Register it in `TestEngine.__init__` (`engine.py`), and map it to a pillar in `run_all`'s `pillar_mapping` and in the CLI's `--pillar` choices.
4. If it needs the backend, add `"<name>": ["api_connectivity"]` to `DependencyEngine`.
5. Decide whether it's **required** for the gate (`ReleaseGateEvaluator.required_test_types`). The default is optional.
6. Add catalog entries, a preflight check if it needs a tool, unit tests with a stub, and docs (ARCHITECTURE, TESTING, CONFIGURATION).

## Unit-test conventions

- `unittest`, files `orchestration/tests/test_*.py`; run one module with `python3 -m unittest orchestration.tests.test_release_gate_authoritative -v`.
- Build configs with `OrchestrationConfig.load(workspace_root=tmp, results_dir=tmp, audit_dir=…)`. Never write into the real `results/`.
- Use local `http.server` stubs instead of a real backend; tests must not need the network.
- Don't read the developer's `.env` (the test package sets `AUTOMATION_SKIP_ENV_FILE=1`).

## Docs

When behavior changes, update the doc that describes it in the same commit, and add a line to `CHANGELOG.md`.
