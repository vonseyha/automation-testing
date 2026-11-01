# automation-testing

Pre-release test engine for the TopAuto (Auto360) stack. It runs **101 checks in six pillars** against your locally running backend and admin UI, saves evidence for each one, and ends with a release-gate verdict: **READY FOR ROLLOUT**, **NOT READY** or **VALIDATION INCOMPLETE**.

| Pillar | Cases | What it checks | Gate |
|---|---:|---|---|
| API & Integration | 73 | TCP probe + real HTTP calls: auth, tenancy, entitlements, cars, sales, finance, HR, payroll | required |
| Security & Access | 16 | missing/malformed tokens, authz/RBAC, NoSQL injection, SSRF, security headers | required |
| Penetration | 7 | prompt-injection / jailbreak / exfiltration probes against the guardrails | required |
| UI & Channel | 3 | the admin portal's Angular test suite (headless Chrome) | warning only |
| Performance | 1 | JMeter smoke/load plan | warning only |
| AI Grounding | 1 | Agentforce Testing Center batch (optional) | warning only |

The core is **pure Python 3.9+ standard library** (no `pip install`). Node is used for the Playwright specs and the fixture script.

> ⚠️ The API pillar **creates and changes data** (cars, sale letters, a cashflow transaction). Run it only against a **local, disposable** database. The engine refuses a non-local `API_BASE_URL` unless `ALLOW_REMOTE_TARGET=1`. See [docs/SECURITY.md](docs/SECURITY.md).

## Quick start

```bash
# repos side by side: automation-testing/, topautokh-api/, top-auto-1653-admin-page/
git clone https://github.com/vonseyha/automation-testing.git && cd automation-testing
make setup          # .env from env.example, Playwright + Chromium
make check          # offline self-test: 177 unit tests, ~30 s
# start MongoDB (rs0) and the backend in your own terminals, then:
make preflight      # environment ready?
make fixtures-apply # once per database: test tenants + platform admin → copy the printed ids into .env
make test           # full run → release-gate verdict
make dashboard      # browse results on http://localhost:8470
```

The full walkthrough, with a check after every step, is in **[docs/SETUP.md](docs/SETUP.md)**. Run `make help` for all commands.

## Documentation

| | |
|---|---|
| [Setup, end to end](docs/SETUP.md) | from an empty machine to a verdict |
| [User guide](docs/USER_GUIDE.md) | verdicts, pass/fail/blocked, everyday commands |
| [Architecture](docs/ARCHITECTURE.md) | components, run flow, dependency graph, release gate, storage |
| [Configuration](docs/CONFIGURATION.md) | every setting and how paths resolve |
| [Testing](docs/TESTING.md) | the 101-case catalog and the engine's own unit tests |
| [Development](docs/DEVELOPMENT.md) | adding test cases, security checks and runners |
| [Operations](docs/OPERATIONS.md) | daily routine, results, retention, CI, servers |
| [Security](docs/SECURITY.md) | secrets, data the tests write, what never to commit |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | symptom → cause → fix |
| [Deployment readiness](docs/DEPLOYMENT_READINESS.md) | what's verified, known limitations |
| [Master Agent](docs/ORCHESTRATION_GUIDE.md) | the optional Gemini orchestration layer |

## Repository layout

```
automation-testing/
├── bin/orchestrator        CLI wrapper (works from any directory)
├── fixtures/               test-identity script for a local MongoDB
├── orchestration/          the Python package: engine, runners, catalog, dashboard, Playwright specs, unit tests
├── docs/                   documentation (history/ = original long-form guides)
├── env.example, Makefile, CONTRIBUTING.md, CHANGELOG.md, AGENTS.md
└── results/                run output (gitignored)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: `make check` must pass, update the docs and changelog, and never commit `.env`, `results/`, secrets or real customer data. This repo is public.
