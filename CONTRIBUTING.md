# Contributing

Thanks for improving the TopAuto test engine. This repo is **public**: read [docs/SECURITY.md](docs/SECURITY.md) before your first commit.

## Workflow

1. Branch from `main`: `git checkout -b feat/<short-name>` (or `fix/…`, `docs/…`).
2. Make the change. Engine internals: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Recipes for new test cases and runners: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
3. Run `make check`; it must pass. If you changed test cases or runners, also run the affected pillar against your local stack (`make pillar P=…`).
4. Update the docs that describe the behavior, and add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. Open a pull request. Say what changed, how you verified it (commands + results), and whether it changes the release gate.

## Checklist before you push

- [ ] `make check` passes
- [ ] no `.env`, `results/`, secrets, real phone numbers, customer data or internal security findings in the diff
- [ ] new API cases avoid hard-coded record IDs and are added to the catalog
- [ ] cases that write data are listed in `docs/SECURITY.md`
- [ ] docs and CHANGELOG updated

## Style

- Python 3.9, standard library only, type hints, small functions.
- BLOCKED (with a remediation) when a precondition is missing; FAILED only when the application misbehaved.
- Commit messages: imperative subject line (≤ 72 chars), body explaining *why*.
