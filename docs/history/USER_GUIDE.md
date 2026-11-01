# Agentic Test Engine — User Guide

> **Historical document** (written inside the TopAuto workspace, Sept–Oct 2026). The current docs are in [docs/](../README.md) and win where they disagree. Paths were updated for this repo; counts and examples are from that period.

## 1. What This Project Does

The project is a reusable test orchestration system with two AI layers:

```text
User
  ↓
Gemini 3.8 Flash — Master Agent
  ↓
Plans / selects tools / executes / observes
  ↓
Real Test Engine
  ├── UI & Channel
  ├── API & Integration
  ├── Performance
  ├── Security & Access
  ├── Prompt-Injection Evaluation
  └── AI Grounding
  ↓
Results + Evidence
  ↓
Release Scorecard
  ↓
READY / NOT READY / VALIDATION INCOMPLETE

For complex or high-risk decisions:

Gemini 3.8 Flash
        ↓
Gemini 3.1 Pro Reviewer
        ↓
Review Findings
        ↓
Remediation
        ↓
Retest
```

The important distinction is that the Test Engine executes **real tests**. It does not treat static code inspection or simulated results as production test results.

---

# 2. Before Your First Real Run

Configure the environment before running tests.

At minimum, verify:

* Gemini API access for the Master Agent (`GEMINI_API_KEY`).
* Gemini API access for the Pro Reviewer.
* Canonical Backend Workspace (`BACKEND_WORKSPACE` defaulting to `topautokh-api`).
* Target host and port (`API_BASE_URL` defaulting to `http://localhost:3000`).
* Health check endpoint (`API_HEALTH_ENDPOINT` defaulting to `/health`).
* Backend service startup (when explicitly permitted, run inside `topautokh-api` via `npm run start` or `node index.js`; never start `topauto-api-cluster`).
* Credentials/configuration for external test systems.
* UI automation configuration (UTAM / Provar).
* JMeter installation/configuration.
* Security/access configuration (Salesforce CLI `sf` / `sfdx`).
* Agentforce Testing Center configuration (`TESTING_CENTER_API_URL`, `AGENTFORCE_REGRESSION_BATCH_ID`).
* Required environment variables/secrets.

Never put API keys or passwords directly into source code.

The command execution environment is intentionally restricted by the `CommandSecurityPolicy`.

---

# 3. Start With a Safe Diagnostic

Before running a complete production validation, run a basic diagnostic.

The project already demonstrated a CLI execution pattern:

```bash
python3 -m orchestration test --real
```

Use this as the primary real-test execution entry point when running the project's Test Engine CLI.

You can also use the existing orchestration shell wrapper where appropriate:

```bash
bin/orchestrator test
```

or:

```bash
bin/orchestrator test
```

The exact available subcommands should be checked with:

```bash
python3 -m orchestration --help
```

and:

```bash
bin/orchestrator --help
```

Do not assume a command exists until the CLI confirms it.

---

# 4. Run the Real Test Engine

For a real validation run:

```bash
python3 -m orchestration test --real
```

or via the wrapper:

```bash
bin/orchestrator test --real
```

The engine should then:

1. Initialize the execution.
2. Load the available test runners.
3. Validate dependencies.
4. Execute the applicable real runners.
5. Collect results.
6. Store evidence.
7. Generate the scorecard.
8. Calculate the release gate.

The expected result states are:

```text
PASSED
FAILED
BLOCKED
PENDING
```

A test that cannot execute because its environment/dependency is unavailable should be `BLOCKED`, not falsely marked `PASSED`.

---

# 5. Understand the Six Test Pillars

### UI & Channel

Used for UI and end-to-end channel validation.

* **Configuration**:
  * `UI_TEST_COMMAND`: Custom execution command (e.g. `utam`, `provar`, or test script).
  * `ENABLE_ANGULAR_HEADLESS_TEST`: Set to `true` to run Angular headless unit/UI tests in `top-auto-1653-admin-page`.
* **Prerequisites**:
  * For UTAM: Node.js, npm, WebdriverIO (`wdio-utam-service`), UTAM page objects, browser.
  * For Provar: Provar CLI, Provar license, test project.
  * For Angular: `node_modules` installed in `top-auto-1653-admin-page`, Headless Chrome (`/Applications/Google Chrome.app`).
* **Execution Command**: `bin/orchestrator test --real --pillar ui`
* **Evidence**: `results/evidence/<test_run_id>/ui_execution.log`

---

## API & Integration

Used to validate API and external gateway connectivity.

* **Configuration**:
  * `BACKEND_WORKSPACE`: Path to backend service (default: `topautokh-api`).
  * `API_BASE_URL`: Base URL (default: `http://localhost:3000`).
  * `API_HEALTH_ENDPOINT`: Health check endpoint (default: `/health`).
* **Prerequisites**:
  * Backend service running on port 3000 (`npm run start` inside `topautokh-api`).
* **Execution Command**: `bin/orchestrator test --real --pillar api`
* **Evidence**:
  * `results/evidence/<test_run_id>/connectivity_probe.json`
  * `results/evidence/<test_run_id>/api_response.json`

---

## Performance

Used for actual load/performance testing using Apache JMeter.

* **Configuration**:
  * `JMETER_PATH` / `JMETER_HOME`: Path to JMeter executable (or binary in `PATH`).
  * `JMETER_TEST_PLAN`: Path to JMX test plan (default: `orchestration/performance/smoke_test.jmx`).
* **Prerequisites**:
  * Java Runtime Environment (JRE).
  * Apache JMeter 5.x (`jmeter -v`).
* **Execution Command**: `bin/orchestrator test --real --pillar perf`
* **Evidence**:
  * `results/evidence/<test_run_id>/jmeter_results.jtl`
  * `results/evidence/<test_run_id>/jmeter_console.log`

---

## Security & Access

Used to validate access controls, profiles, and permission sets against Salesforce / IAM environments.

* **Configuration**:
  * `SF_TARGET_ORG` / `SALESFORCE_ORG_ALIAS`: Salesforce Sandbox/Test organization alias or username.
  * `SF_CLI_PATH`: Path to Salesforce CLI (`sf` / `sfdx`).
  * `SECURITY_VALIDATION_COMMAND`: Optional custom security audit command.
* **Prerequisites**:
  * Salesforce CLI installed (`sf --version`).
  * Authenticated Sandbox/Scratch org session (`sf org list`).
* **Execution Command**: `bin/orchestrator test --real --pillar security`
* **Evidence**: `results/evidence/<test_run_id>/security_audit.json`

---

## Prompt-Injection Evaluation

This is the AI security pillar. It executes dynamic adversarial evaluation against controlled attack vectors.

* **Configuration**:
  * Default workspace guardrail evaluation harness.
  * Custom evaluation prompt suites.
* **Execution Command**: `bin/orchestrator test --real --pillar pen`
* **Evidence**: `results/evidence/<test_run_id>/penetration_evaluation_report.json`

---

## AI Grounding

Used for Agentforce / AI regression validation against Agentforce Testing Center.

* **Configuration**:
  * `TESTING_CENTER_API_URL` / `AGENTFORCE_TESTING_CENTER_URL`: Testing Center API endpoint.
  * `AGENTFORCE_REGRESSION_BATCH_ID`: Regression batch identifier.
  * `AGENTFORCE_API_TOKEN`: Bearer authorization token.
* **Prerequisites**:
  * Configured Agentforce Testing Center instance and regression batch.
* **Execution Command**: `bin/orchestrator test --real --pillar grounding`
* **Evidence**: `results/evidence/<test_run_id>/testing_center_batch_result.json`

---

# 6. Sequential vs Parallel Execution

The system supports the two orchestration styles.

### Sequential

Use when test dependencies matter:

```text
UI
 ↓
API
 ↓
Performance
 ↓
Security
 ↓
Pen Test
 ↓
AI Grounding
```

This is useful when you want a controlled validation chain:

```bash
bin/orchestrator test --mode sequential
```

### Parallel

Use when tests are independent:

```text
UI ───────────────┐
API ──────────────┤
Performance ──────┤
Security ─────────┤
Pen Test ─────────┤
AI Grounding ─────┘
```

```bash
bin/orchestrator test --mode parallel
```

Parallel execution reduces unnecessary waiting, but only use it when the underlying systems can safely run concurrently.

---

# 7. How Dependencies Work

The Test Engine understands that some tests depend on prerequisites.

Example:

```text
API connectivity
      ↓
FAILED
      ↓
Integration tests
      ↓
BLOCKED
```

This is intentional.

A `BLOCKED` result means:

> The test could not meaningfully execute because a prerequisite was unavailable.

That is different from:

```text
FAILED = the test actually executed and failed
```

This distinction is important when interpreting the release gate.

---

# 8. How the Master Agent Works

You do not need to manually tell the agent every implementation step.

The Master Agent uses Gemini 3.8 Flash to reason about the request and select available tools.

Conceptually:

```text
User Request
   ↓
Gemini 3.8 Flash
   ↓
Plan
   ↓
Select Tool
   ↓
Execute
   ↓
Observe Result
   ↓
Gemini 3.8 Flash
   ↓
Next Decision
   ↓
Finish / Continue / Escalate
```

This is now an actual model-driven loop rather than the old hardcoded planner.

To run a task via the Master Agent:

```bash
bin/orchestrator run -t "Audit security boundaries"
```

---

# 9. When Gemini 3.1 Pro Is Used

The Pro Reviewer is a specialist rather than the default model.

The Master Agent can escalate difficult work such as:

* Architecture changes
* Security-sensitive changes
* Complex failures
* Persistent failures
* High-risk remediation
* Difficult implementation decisions

Typical flow:

```text
Gemini 3.8 Flash
      ↓
Detect complex issue
      ↓
Gemini 3.1 Pro
      ↓
Review
      ↓
Findings
      ↓
Flash evaluates
      ↓
Fix
      ↓
Retest
```

You normally do not need to manually select Pro for every test run.

To force model selection override:

```bash
bin/orchestrator run -t "Refactor architecture" --override pro
```

---

# 10. Running a Full Pre-Production Validation

A typical release-validation workflow is:

### Step 1 — Verify environment

Confirm:

* Target environment is reachable.
* Required test services are available.
* Required credentials are configured.

Check configuration status with:

```bash
bin/orchestrator status
```

### Step 2 — Run the real Test Engine

```bash
python3 -m orchestration test --real
```

### Step 3 — Review the results

Look for:

```text
PASSED
FAILED
BLOCKED
PENDING
```

Pay particular attention to:

* Failed dependencies
* External-service failures
* Security findings
* Performance threshold violations
* AI regression failures

### Step 4 — Review evidence

Inspect the generated execution logs/reports in `results/evidence/<test_run_id>/` rather than relying only on the summary.

### Step 5 — Check the release gate

The production Release Gate now uses the **real test scorecard**, not the deprecated mock pillars.

---

# 11. Release-Gate Interpretation

The current release gate should be interpreted as:

### READY FOR ROLLOUT

Required real tests passed and sufficient evidence exists.

### NOT READY

At least one required real test failed or is blocked.

### VALIDATION INCOMPLETE

Required validation remains pending or required results/evidence are missing.

Do not interpret `READY FOR ROLLOUT` as a guarantee that the production deployment will have zero defects. It means the configured release validation criteria passed.

---

# 12. Example Scenarios

## Scenario A — Healthy Environment

```text
UI                 PASSED
API                PASSED
Performance        PASSED
Security           PASSED
Pen Test           PASSED
AI Grounding       PASSED

Release Gate:
READY FOR ROLLOUT
```

---

## Scenario B — API Gateway Down

```text
UI                 PASSED
API                FAILED
Performance        BLOCKED
Security           PASSED
Pen Test           PASSED
AI Grounding       PASSED

Release Gate:
NOT READY
```

The performance test may be blocked because its prerequisite is unavailable.

---

## Scenario C — Incomplete Validation

```text
UI                 PASSED
API                PASSED
Performance        PENDING
Security           PASSED
Pen Test           PASSED
AI Grounding       PASSED

Release Gate:
VALIDATION INCOMPLETE
```

---

# 13. Using the Command Tool Safely

The Master Agent has access to command execution, but it is protected by `CommandSecurityPolicy`.

The policy distinguishes between:

```text
ALLOWED
REQUIRES CONFIRMATION
DENIED
```

Examples from your verified implementation:

```text
ls -la
→ Allowed

npm install
→ Confirmation required

rm -rf ...
→ Denied

cat .env
→ Denied / protected
```

This security boundary should not be bypassed.

Purpose-built tools should be preferred over arbitrary shell commands.

Audit trail is preserved in `results/audit/command_execution_audit.jsonl`.

---

# 14. Legacy Mock Pillars

The old static-analysis/mock pillars may still exist for compatibility.

They are now isolated in the deprecated registry:

```text
_deprecated_legacy_pillars
```

They should NOT be used for production validation.

When operating the system, always use the real Test Engine path.

The production Release Gate must never use the legacy results.

To run legacy static code scanning for diagnostic reference only:

```bash
bin/orchestrator test --static
```

---

# 15. Evidence and Audit Trail

Each real execution should have an associated execution identity and evidence.

Useful information includes:

* Execution ID
* Test type
* Environment
* Start time
* Completion time
* Duration
* Status
* Metrics
* Failure information
* Evidence
* Reviewer involvement
* Remediation
* Final release decision

Inspect past test runs and audit trails with:

```bash
bin/orchestrator test --runs
```

and:

```bash
bin/orchestrator audit -n 10
```

This gives you traceability when somebody asks:

> "Why did the system say NOT READY?"

or:

> "What exactly passed before this release?"

---

# 16. Recommended Daily Usage

For development:

```text
Make change
    ↓
Run targeted test
    ↓
Review failure
    ↓
Fix
    ↓
Retest
```

Run a targeted pillar:

```bash
bin/orchestrator test -p pen
```

For a release candidate:

```text
Environment check
    ↓
Full real Test Engine
    ↓
Review failures/blockers
    ↓
Remediation
    ↓
Full validation again
    ↓
Release Gate
```

For a major architecture/security change:

```text
Implement
    ↓
Test
    ↓
Gemini 3.1 Pro review
    ↓
Remediation
    ↓
Retest
    ↓
Full validation
```

---

# 17. Recommended First Real-Environment Rollout

Before connecting everything to a production environment, use a dedicated test/staging environment.

Start with:

```text
1. API / Integration
2. UI
3. Security
4. AI Grounding
5. Prompt-Injection Evaluation
6. Performance
```

Then establish real acceptance thresholds for each pillar.

For example:

```text
API:
HTTP success rate ≥ configured threshold

Performance:
P95 response time < configured threshold

Security:
No critical authorization findings

Prompt Injection:
All mandatory security cases pass

AI Grounding:
All mandatory regression scenarios pass
```

The actual thresholds should come from your project's requirements rather than being invented by the agent.

---

# 18. Operational Principle

Treat the system as a **test orchestration platform**, not just an AI assistant.

The AI decides:

```text
What should I do next?
```

The Test Engine determines:

```text
What actually happened?
```

The Release Gate determines:

```text
Do the real results satisfy the release criteria?
```

This separation is important because the LLM should not be able to simply say:

> "Everything looks good."

and turn that into a production-ready result.

The release decision must come from actual test evidence.

---

# 19. Basic Command Checklist

The first commands to learn are:

```bash
python3 -m orchestration --help
```

```bash
python3 -m orchestration test --real
```

```bash
bin/orchestrator --help
```

Use the help output to discover the exact commands implemented in your current version rather than guessing additional CLI syntax:

```bash
# Run orchestration task with Master Agent
bin/orchestrator run -t "Task description"

# Run authoritative Real Test Engine
bin/orchestrator test --real

# Run specific pillar (e.g. penetration, api, ui, perf, security, grounding)
bin/orchestrator test -p pen

# List recent real test runs
bin/orchestrator test --runs

# View recent orchestration audit log
bin/orchestrator audit -n 10

# Show orchestration system status
bin/orchestrator status
```

---

# 20. Recommended Operating Model

Use the models like this:

```text
Gemini 3.8 Flash High
    = everyday Master Agent
    = orchestration
    = tool execution
    = test execution
    = remediation

Gemini 3.1 Pro High
    = architecture reviewer
    = difficult failure analysis
    = security-sensitive review
    = high-risk decisions
```

Do not use the Pro model as the default engine for every operation. The current architecture is designed so the faster model handles normal work and the deeper model is used selectively.
