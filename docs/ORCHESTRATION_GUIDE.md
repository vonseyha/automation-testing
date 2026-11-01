# Master Agent + Specialist Reviewer Orchestration Guide

> **automation-testing repo:** setup is in [SETUP.md](SETUP.md); the engine architecture is in [ARCHITECTURE.md](ARCHITECTURE.md). Commands below run from the repo root (`bin/orchestrator <cmd>` = `python3 -m orchestration <cmd>`). Results go to `results/` (or `RESULTS_DIR`), not `.antigravity/`.

## 1. Overview & Mission

This document defines the architecture, operation, and usage of the persistent AI development and test-engine orchestration system built for the **TopAuto 1653** workspace.

The system enforces a dual-model pair-programming and verification workflow:
* **Primary Master Agent**: **Gemini 3.8 Flash High**  
  Owns the overall workflow: planning, repo inspection, code editing, test execution, tool invocation, debugging, and project maintenance.
* **Specialist Reviewer**: **Gemini 3.1 Pro High**  
  Specialist architecture, security, and trade-off reviewer invoked on-demand when complex reasoning or deep architectural review is required.

---

## 2. Core Architecture

```text
                         MASTER AGENT
                     Gemini 3.8 Flash High
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
             ANALYZE       BUILD/EDIT     TEST/VALIDATE
                |             |             |
                +-------------+-------------+
                              |
                    COMPLEXITY / QUALITY
                         DECISION
                              |
                 +------------+------------+
                 |                         |
              NORMAL                    COMPLEX
                 |                         |
                 v                         v
          Flash continues         PRO REVIEWER
                              Gemini 3.1 Pro High
                                      |
                                      v
                              Review / Findings
                                      |
                                      v
                              Master Agent
                                      |
                                      v
                              Fix / Improve
                                      |
                                      v
                              Re-test / Verify
```

The Master Agent remains accountable for the final implementation. The Pro Reviewer provides analysis and recommendations, but does not become the permanent owner of the project.

---

## 3. Specialist Escalation Policy

The Master Agent does **not** call the Pro Reviewer for routine tasks. It applies an automated 7-question decision tree before escalating:

```text
Is this task:
1. Architecturally significant? (New subsystems, migration patterns, persistence strategy)
2. High risk? (Changes across >= 4 files, core service rewrites, high-impact fixes)
3. Difficult to reason about? (Ambiguous requirements, deep trade-off analysis)
4. Security sensitive? (HMAC signing, JWT auth, RBAC, prompt injection, data isolation)
5. Likely to create regression? (Cross-repo impacts between Express, Cluster, and Angular)
6. Stuck after reasonable implementation attempts? (Recurring test failures after 2 attempts)
7. Important enough to justify deeper review?
```

* **If none apply**: The task continues autonomously with **Gemini 3.8 Flash High**.
* **If one or more apply**: The task escalates to **Gemini 3.1 Pro High**.

### Explicit User Overrides
- Prompt phrases like `"review this architecture"`, `"use the pro reviewer"`, `"deep review"` force escalation.
- Prompt phrases like `"do not escalate"`, `"flash only"` bypass escalation.

---

## 4. Reviewer Input & Output Contracts

### Scoped & Sanitized Input (Section 6 & 16)
Context sent to the Pro Reviewer is automatically stripped of credentials, passwords, tokens, and private keys via `orchestration.security.sanitizer`.

### Structured Output Contract (Section 7)
The Pro Reviewer responds strictly in this structured format:

```text
REVIEW RESULT

Decision:
APPROVE / APPROVE WITH CHANGES / REJECT

Architecture Assessment:
<assessment>

Critical Findings:
- <finding or None>

High-Risk Issues:
- <finding or None>

Recommended Changes:
- Required: <must-fix change>
- Recommended: <strong suggestion>
- Optional: <nice-to-have improvement>

Testing Requirements:
- <mandatory test or validation check>

Reasoning Summary:
<concise rationale>
```

---

## 5. Review Loop & Iteration Bounds (Section 9)

```text
PLAN -> IMPLEMENT -> TEST -> PRO REVIEW -> FINDINGS?
  ├── NO (APPROVE) -> FINAL VALIDATION & RELEASE SCORECARD
  └── YES (CHANGES) -> FIX -> TEST -> REVIEW AGAIN
```

- **Maximum Iterations**: Default is **3 iterations**.
- If still unresolved after 3 iterations, the engine halts the loop and emits:
  `ESCALATION REQUIRED`
  documenting the unresolved architectural decision for human review.

---

## 6. The Real 6-Pillar Test Engine (Sections 6-17)

The Test Engine provides real execution adapters across the 6 pillars with un-faked result normalization:

| Pillar / Runner | Real Execution Mechanism | Fallback When Unconfigured |
| :--- | :--- | :--- |
| **API Connectivity** | Real TCP socket probe to target host & port | `FAILED` with real connection error (e.g. `[Errno 61] Connection refused`) |
| **API & Integration** | Real HTTP request execution, measured network latency, status code & payload validation | `FAILED` or `BLOCKED` (cascades from `api_connectivity` prerequisite) |
| **UI & Channel** | Real UTAM / Provar / Angular UI automation adapter (`ui_runner.py`) | `BLOCKED` (`reason: UI automation engine (UTAM/Provar) not configured in PATH`) |
| **Performance** | Real Apache JMeter adapter (`performance_runner.py`) with real .jtl/.csv metrics | `BLOCKED` (`reason: JMeter is not configured or executable in PATH`) |
| **Security & Access** | Real Salesforce CLI / IAM authorization boundary validator (`security_runner.py`) | `BLOCKED` (`reason: Salesforce security provider not configured`) |
| **Penetration Check** | Real prompt-injection & attack vector evaluation harness across 7 categories | Evaluates blocking and records evidence report |
| **AI Grounding** | Real Agentforce Testing Center regression adapter (`ai_grounding_runner.py`) | `BLOCKED` (`reason: Agentforce Testing Center integration not configured`) |

### Dependency Engine & Execution Modes (Sections 13 & 14)
- **Topological DAG**: Downstream runners (e.g. `api_integration`, `performance`, `security_access`) depend on `api_connectivity`. If connectivity fails, dependent suites become `BLOCKED` to eliminate noise.
- **Execution Modes**:
  - `sequential`: Ordered execution honoring prerequisite DAG.
  - `parallel`: Multi-threaded concurrent execution via `ThreadPoolExecutor`.

---

## 7. Model Routing & Graceful Fallback (Section 13 & 15)

The `ModelRouter` decouples the system from hardcoded model clients:
- If `GEMINI_API_KEY` is configured, calls the Google GenAI REST API directly with specified thinking levels (`high`).
- If running inside an agentic runtime supporting subagents, routes to the Pro subagent.
- **Graceful Fallback**: If Gemini 3.1 Pro cannot be invoked in the current environment:
  - It does **not** pretend the reviewer was executed.
  - Returns:
    ```text
    Reviewer Status = UNAVAILABLE
    Reason = <actual limitation>
    Fallback = Continue with primary model or stop based on task risk
    ```

---

## 8. CLI Usage & Commands

The executable runner is `bin/orchestrator` (or `python3 -m orchestration` from the repo root):

### 1. Run a Task through Master Agent Orchestration
```bash
# Normal task (runs real tools: read_file, run_command)
bin/orchestrator run --task "Update readme formatting" --files "README.md"

# Complex architecture task (escalates to Pro Reviewer with real tool remediation)
bin/orchestrator run --task "Design async event queue for general ledger" --files "ledger.service.ts,queue.service.ts"

# Explicit override
bin/orchestrator run --task "Review payment endpoints" --override pro
bin/orchestrator run --task "Quick patch" --override flash
```

### 2. Execute Real Test Engine (Sequential / Parallel)
```bash
# Run real test engine sequentially
bin/orchestrator test --real --mode sequential

# Run real test engine concurrently in parallel
bin/orchestrator test --real --mode parallel

# View recent real test runs from persistent storage
bin/orchestrator test --runs

# Run backwards-compatible workspace pillar checks
bin/orchestrator test --pillar all
```

### 3. Inspect the Audit Trail
```bash
bin/orchestrator audit --limit 10
```

### 4. Check System Configuration & Status
```bash
bin/orchestrator status
```

---

## 9. Persistent Audit Trail (Section 17)

Every run is logged persistently in two synchronized formats:
1. **Machine-Readable**: `results/audit/orchestration_audit.jsonl`
2. **Human-Readable Table**: `results/audit/orchestration_audit.md`

Fields recorded:
- `timestamp`
- `task`
- `primary_model`
- `review_requested`
- `review_reason`
- `reviewer_model`
- `reviewer_decision`
- `changes_applied`
- `tests_executed`
- `final_outcome`

---

## 10. Automated Validation Suite

Run the full orchestration engine test suite (142 unit and integration tests across 22 test modules) anytime:
```bash
python3 orchestration/tests/run_all_tests.py
```

**Test breakdown by category:**

| Category | Test modules | Count |
| :--- | :--- | ---: |
| Reporting, dashboard, history formatting | `test_reporting_and_dashboard.py` | 16 |
| Real test engine execution | `test_real_test_engine.py` | 15 |
| Command security policy | `test_command_security_policy.py` | 12 |
| Remediation regression | `test_remediation_regression.py` | 12 |
| Failure escalation policy | `test_escalation.py` | 8 |
| Release gate evaluation | `test_release_gate_authoritative.py` | 7 |
| AI grounding runner | `test_ai_grounding_runner.py` | 6 |
| Catalog and coverage | `test_catalog_and_coverage.py` | 6 |
| Security providers | `test_security_provider.py` | 5 |
| Penetration runner | `test_penetration_runner.py` | 5 |
| Config loading | `test_config.py` | 4 |
| Model router | `test_model_router.py` | 4 |
| Orchestrator E2E | `test_orchestrator_e2e.py` | 4 |
| Scorecard integrity | `test_scorecard_integrity.py` | 4 |
| Test engine pillars | `test_test_engine.py` | 4 |
| Sanitizer | `test_sanitizer.py` | 4 |
| Master agent loop | `test_master_agent_loop.py` | 4 |
| Contract and normalizer | `test_contract_and_normalizer.py` | 3 |
| Audit logger | `test_audit_logger.py` | 2 |
| Review loop | `test_review_loop.py` | 2 |
| Preflight checks | `test_preflight.py` | 9 |
| Ollama local AI client | `test_ollama_client.py` | 6 |
| **Total** | **22 modules** | **142** |

These are **orchestration engine tests** that verify the test framework itself. They are distinct from the **application test suite** (95 product test cases across 6 pillars) that the engine executes against the running TopAuto application.

**Environment requirements:** Python 3.9+. No API keys, running servers, or external services are required. All tests run locally and deterministically.
