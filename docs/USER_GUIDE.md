# User guide

How to use the engine once it's set up ([SETUP.md](SETUP.md)). It's for developers and QA who want to know "can we release this build?".

## The one command

```bash
make test
```

It runs the 101 checks, prints a scorecard and ends with one of three verdicts:

| Verdict | Meaning | What to do |
|---|---|---|
| **READY FOR ROLLOUT** | API, Security and Penetration suites all passed, with evidence | release; keep the run ID |
| **NOT READY** | a required suite failed or was blocked | read the blocking reasons; fix the app or the environment |
| **VALIDATION INCOMPLETE** | a required suite didn't run or has no evidence | run the full set (`make test`, no `--pillar` filter) |

The exit code is `0` only for READY FOR ROLLOUT.

## The six pillars, in plain words

| Pillar | Question it answers | Decides the gate? |
|---|---|---|
| **API & Integration** | Do the backend's endpoints behave correctly for each tenant and plan (cars, sales, finance, HR, payroll, entitlements)? | yes |
| **Security & Access** | Are unauthenticated, forged or under-privileged requests rejected? Are injection and SSRF attempts blocked? | yes |
| **Penetration** | Do the guardrails refuse prompt-injection, jailbreak and data-exfiltration attempts? | yes |
| **UI & Channel** | Do the admin portal's automated UI specs pass? | no (warning only) |
| **Performance** | Do key endpoints stay within latency/throughput limits under a small load? | no (warning only) |
| **AI Grounding** | Do AI answers stay grounded (Agentforce)? Usually not configured | no (warning only) |

## Pass, fail, blocked

- **PASSED:** the check ran and the app behaved as expected.
- **FAILED:** the check ran and the app did **not** behave as expected. This is a defect, or the expectation is out of date. Open its evidence.
- **BLOCKED:** the check **could not run**: the backend is down, a tool is missing, a test identity isn't configured, or a prerequisite failed. It's never counted as passed or failed. Its `required_remediation` says how to unblock it.

The pass rate counts executed checks only. 10/11 passed with 90 blocked means "almost nothing ran", not "91 % good".

## Typical outcomes

**Healthy stack**
```
API & Integration   PASSED      Security & Access  PASSED     Penetration  PASSED
UI & Channel        PASSED      Performance        PASSED     AI Grounding BLOCKED (not configured)
Release Gate: READY FOR ROLLOUT   (warning: ai_grounding BLOCKED)
```

**Backend not running**
```
CONN-001 FAILED (connection refused) → API, Security, Performance BLOCKED
Penetration PASSED, UI PASSED
Release Gate: NOT READY   → start the backend, run again
```

**A real defect**
```
API & Integration   FAILED  (API-FIN-002: expected 200, got 500)
Release Gate: NOT READY   → open results/evidence/<run>/api_test_results.json, fix the backend
```

**Only one pillar run**
```
make pillar P=ui → Release Gate: VALIDATION INCOMPLETE (required suites not executed)
```
This is expected for a partial run. Use partial runs while developing and a full run before release.

## Everyday commands

| I want to… | Command |
|---|---|
| check my setup | `make status`, `make preflight` |
| run everything | `make test` (or `make test-parallel`) |
| run one area | `make pillar P=api` · `ui` · `perf` · `security` · `pen` · `grounding` |
| see past runs | `make runs` |
| browse results | `make dashboard` → http://localhost:8470 |
| see what is covered | `make catalog` |
| drive the real admin UI | `make ui-specs` (admin must be running) |
| create test logins in my local DB | `make fixtures-apply` |

## Reading one failed check

On the dashboard or in `results/test_runs/<run_id>.json`, every check has:
- `test_case_id`, `test_name`, `module`, `priority` (P0 = critical);
- `expected` and `actual`;
- `failure_reason` (FAILED) or `blocking_dependency` + `required_remediation` (BLOCKED);
- `evidence`: the file(s) under `results/evidence/<run_id>/` with the raw request/response or log.

Find which feature it belongs to with `bin/orchestrator catalog --traceability`.

## Good practice

- Run against a **local, disposable** database; the API suite creates test data ([SECURITY.md](SECURITY.md)).
- Run a full `make test` on the exact branches you're about to release.
- Treat a new BLOCKED as seriously as a FAILED until you know why it happened.
- Keep the run ID of the release run (the `results/` evidence is your audit trail).

## The optional Master Agent

`bin/orchestrator run --task "…"` gives a task to a Gemini-driven agent that can read the workspace, run allowed commands and the test engine, and ask a stronger reviewer model for high-risk changes. It needs `GEMINI_API_KEY` and isn't needed for testing. See [ORCHESTRATION_GUIDE.md](ORCHESTRATION_GUIDE.md).
