# Common commands. Run `make help` for the list.
PYTHON ?= python3
ORCH   := bin/orchestrator
UI_DIR := orchestration/ui_tests

.DEFAULT_GOAL := help
.PHONY: help setup check unit status preflight catalog test test-parallel pillar runs ui-specs dashboard fixtures fixtures-apply fixtures-cleanup

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-17s %s\n", $$1, $$2}'

setup: ## First-time setup: create .env, install Playwright deps + Chromium
	@if [ ! -f .env ]; then cp env.example .env && echo "created .env from env.example (edit it)"; else echo ".env already exists (left unchanged)"; fi
	cd $(UI_DIR) && npm ci && npx playwright install chromium
	@mkdir -p results
	@echo "next: make check, then make preflight"

check: ## Offline self-check: compile all Python + run the engine's unit tests
	$(PYTHON) -m compileall -q orchestration
	@node --check fixtures/test-identities.js
	$(PYTHON) orchestration/tests/run_all_tests.py

unit: check ## Alias for check

status: ## Show resolved configuration (paths, URLs, tools)
	$(ORCH) status

preflight: ## Check the environment before a real run (stack, DB, tools, fixtures)
	$(ORCH) preflight

catalog: ## Show the functionality catalog and test coverage
	$(ORCH) catalog

test: ## Run the real 6-pillar test engine (sequential)
	$(ORCH) test

test-parallel: ## Run the real test engine with pillars in parallel
	$(ORCH) test --mode parallel

pillar: ## Run one pillar: make pillar P=api   (ui|api|perf|security|pen|grounding)
	$(ORCH) test --pillar $(P)

runs: ## List recent test runs
	$(ORCH) test --runs

ui-specs: ## Run the Playwright E2E specs against the admin UI (BASE_URL)
	cd $(UI_DIR) && npx playwright test

dashboard: ## Serve the results dashboard on http://localhost:8470 (Ctrl+C to stop)
	$(PYTHON) orchestration/dashboard/serve.py

fixtures: ## Dry run: show which test identities exist in MONGODB_URI
	node fixtures/test-identities.js

fixtures-apply: ## Create the test identities in the LOCAL test DB (idempotent)
	node fixtures/test-identities.js --apply

fixtures-cleanup: ## Remove the test identities (keeps the platform company)
	node fixtures/test-identities.js --cleanup
