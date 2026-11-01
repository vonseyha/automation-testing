# Deployment readiness

Where the engine stands today: what's verified, what isn't, and what's known to be weak. Update this page when that changes.

_Last reviewed: 2026-11-01_

## Verified

| Check | Result | When |
|---|---|---|
| `make check` (engine unit tests) | 168 pass (2 skip without run history) | 2026-11-01, local and on a fresh clone |
| `make preflight` | READY (7/7 required) with MongoDB up and the backend down | 2026-11-01 |
| Real engine run, backend down | 101 cases: 10 PASS, 1 FAIL (`CONN-001`, expected), 90 BLOCKED; gate NOT READY; evidence written | 2026-11-01 |
| UI suite | admin `test:ci`: 40 Karma specs passed (headless Chrome) | 2026-11-01 |
| Playwright specs | 14 listed (`--list`); not executed against a running admin | 2026-11-01 |
| Fixture script | dry run / apply / idempotent rerun / cleanup on a throwaway DB | 2026-11-01 |
| Full run with the backend up | **100 PASS, 0 FAIL, 1 BLOCKED (AIG-001)**, recorded before the move to this repo | 2026-10-15 |

## Not yet verified (after the move)

- A full green run from this repo **with the backend running**. Next step: `make preflight && make test` with the stack up.
- `make ui-specs` against a running admin.
- Linux server operation (documented, not re-tested).

## Readiness by use

| Use | Ready? | Notes |
|---|---|---|
| Developer pre-release check on a local stack | **Yes** | follow [SETUP.md](SETUP.md) |
| Gate for this repo's own changes (`make check`) | **Yes** | fast, no services |
| CI gate for TopAuto releases | **Partly** | needs a CI job that provisions MongoDB + backend ([OPERATIONS.md](OPERATIONS.md#ci-and-scheduled-runs)), and portable test data (below) |
| Against staging / production | **No** | the API suite writes data ([SECURITY.md](SECURITY.md#the-api-pillar-writes-data)) |

## Known limitations

| # | Limitation | Impact | Suggested fix |
|---|---|---|---|
| 1 | 10 API cases use 6 hard-coded record IDs (cars, containers, attendance) from the team dev DB | those cases fail on any other database | create the records in earlier cases or in `fixtures/`, and read their IDs at run time |
| 2 | 11 API cases create or change data, including a cashflow transaction | local DB fills with test data; unsafe on shared environments | a guard that refuses non-localhost `API_BASE_URL` unless explicitly allowed; cleanup step |
| 3 | `TEST_BASIC_*` defaults to team dev-DB ids | fresh DBs need `make fixtures-apply` + `.env` | done via fixtures; consider failing fast when the default ids don't exist |
| 4 | `catalog/*.json` snapshots are stale (95 vs 101 cases) and unused | confusion | delete them or regenerate from the `.py` catalogs |
| 5 | Results grow without limit (~1 MB per full run) | disk use on servers | retention job ([OPERATIONS.md](OPERATIONS.md#retention)) |
| 6 | Dashboard has no authentication | can't be exposed directly | reverse proxy with TLS + auth |
| 7 | Some unit tests still write sample runs into `results/` | noise in the dashboard after `make check` | route every test through a temp `results_dir` |
| 8 | Penetration suite tests a guardrail baseline unless a Gemini key is set | the AI-judge path is rarely exercised | configure a key in CI, or document as baseline-only |
| 9 | Windows untested | — | — |
