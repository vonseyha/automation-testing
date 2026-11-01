# Security

What this repo touches, what it must never contain, and how to run it safely.

## This repository is public

Never commit any of these:
- `.env` or any real secret: `JWT_SECRET`, API keys, database credentials, tokens.
- `results/`: run documents and evidence contain API responses with tenant data.
- Real customer or staff data: phone numbers, names, emails, IDs from a production database.
- Internal security findings about the TopAuto application (open vulnerabilities, unpatched endpoints). Keep those in the team's private notes.

`.gitignore` covers `.env*` (except `env.example`), `results/`, `node_modules/`, Playwright reports and logs. Unit-test fixtures use obviously fake values (`AIzaSyD123…`, the jwt.io sample token, `012000000`).

## Secrets the engine uses

| Secret | Where it comes from | How it's handled |
|---|---|---|
| `JWT_SECRET` | `.env`, the shell, or `$BACKEND_WORKSPACE/.env` | used in memory to sign test JWTs; preflight reports only "available (value redacted)" |
| `GEMINI_API_KEY` | `.env` / shell | optional; sent only to `GEMINI_API_ENDPOINT` |
| `AGENTFORCE_API_TOKEN` | `.env` / shell | optional; `status` shows only whether it is configured |
| Test passwords (`TEST_*_PASSWORD`) | `.env` | optional; the fixture accounts get a random password that's never stored or shown |

`security/sanitizer.py` redacts keys, JWTs, Mongo URIs with credentials and HMAC secrets from evidence and audit records.

## The API pillar writes data

55 of the 72 API cases are GETs. Of the 17 POST/PUT cases, 11 create or change records in the database behind `API_BASE_URL` (the rest are logins and requests that must be rejected):

| Case | Effect |
|---|---|
| API-CAR-001 | creates a car (`POST /api/car/add`) |
| API-CAR-004, API-CAR-006 | updates a car / its images |
| API-CONT-003 | changes a container's status |
| API-SALE-001 | creates a sale letter |
| API-SALE-002, API-SALE-003 | bulk review / bulk payment confirmation on close-sale letters |
| API-FIN-003 | reconciles a cashflow report |
| API-FIN-004 | **posts a cashflow transaction** (money data) |
| API-AUTH-003 | triggers a password-reset request |
| API-AUTH-005 | writes an attendance record |

Several of them target fixed record IDs from the team's dev database. **Rules:**
- Run the engine only against a **local, disposable** database: a fresh one, or a copy you can throw away.
- **Never** point `API_BASE_URL` at staging or production.
- After a run, expect test cars, sale letters and a cashflow transaction in the local DB. Restore your DB copy if you need clean data.

## Fixture script safety

`fixtures/test-identities.js`:
- is a dry run unless you pass `--apply` or `--cleanup`;
- refuses non-localhost MongoDB hosts unless `ALLOW_REMOTE_FIXTURES=1`;
- only touches its fixed `aaa…` ObjectIds;
- keeps the platform company on cleanup unless you pass `--include-platform`, because the app may depend on it.

## Penetration suite content

The penetration suite sends **prompt-injection and jailbreak test prompts** (instruction override, prompt extraction, data-exfiltration requests…) to a guardrail baseline or an AI judge. They are evaluation inputs, not exploits against the application. The suite passes when the system refuses.

## Agent command guardrails

Commands that the optional Master Agent runs go through `security/command_policy.py`:
- **ALLOWED:** read-only diagnostics inside `WORKSPACE_ROOT`.
- **REQUIRES_CONFIRMATION:** installs, mutations, anything disruptive.
- **DENIED:** destructive commands, credential reads or exfiltration, privilege escalation, and any working directory outside the workspace.

Every decision is logged to `results/audit/command_execution_audit.jsonl`, without secrets.

## Reporting a problem

If you find a secret or personal data in this repo, don't open a public issue. Tell the maintainers directly, rotate the secret, and remove it from history.
