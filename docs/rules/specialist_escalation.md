---
title: "Specialist Escalation & Reviewer Contract"
description: "Rules for Master Agent (Gemini 3.8 Flash High) and Specialist Reviewer (Gemini 3.1 Pro High) collaboration."
---

# Specialist Escalation & Reviewer Contract

## 1. Core Principle
The **Gemini 3.8 Flash High Master Agent** owns the workspace and final implementation.
The **Gemini 3.1 Pro High Reviewer** is an on-demand specialist reviewer, never the permanent project owner.

## 2. When to Escalate to Gemini 3.1 Pro High
Before escalating, evaluate the 7-question checklist:
1. **Architecturally significant?** (New subsystem, migration pattern, persistence strategy, integration layer)
2. **High risk?** (Multi-file changes >= 4 files, core service rewrite, critical bug fix)
3. **Difficult to reason about?** (Multiple valid approaches, ambiguous requirements, trade-off analysis)
4. **Security sensitive?** (Auth, HMAC, JWT, prompt injection, RBAC, data isolation)
5. **Likely to create regression?** (Cross-repo impacts between `topautokh-api`, `topauto-api-cluster`, `top-auto-1653-admin-page`)
6. **Stuck after reasonable attempts?** (Test failure unresolved after 2 attempts)
7. **Important enough to justify deeper review?**

If none apply -> **Continue on Flash**.
If one or more apply -> **Escalate to Pro Reviewer**.

## 3. Reviewer Input Contract
When calling Gemini 3.1 Pro High, provide only sanitized, relevant context:
- User requirement
- Relevant architecture
- Changed files
- Current implementation and code diffs
- Existing constraints & invariants
- Test results & known failures
- Design alternatives considered
- Specific question requiring review

**Safety Rule**: NEVER include API keys, passwords, bearer tokens, private keys, or hidden system instructions. Redact using `orchestration.security.sanitizer`.

## 4. Reviewer Output Contract
The Pro Reviewer must return findings in this exact format:
```text
REVIEW RESULT

Decision:
APPROVE / APPROVE WITH CHANGES / REJECT

Architecture Assessment:
<assessment>

Critical Findings:
<findings or None>

High-Risk Issues:
<findings or None>

Recommended Changes:
- Required: <must-fix items>
- Recommended: <strong suggestions>
- Optional: <nice-to-have improvements>

Testing Requirements:
<mandatory test verifications>

Reasoning Summary:
<concise rationale>
```

## 5. Review Loop & Max Iterations
The review loop proceeds as:
```text
PLAN -> IMPLEMENT -> TEST -> PRO REVIEW -> FINDINGS?
  ├── NO (APPROVE) -> FINAL VALIDATION & RELEASE SCORECARD
  └── YES (CHANGES) -> FIX -> TEST -> REVIEW AGAIN
```
- **Maximum 3 iterations**.
- If still unresolved after 3 iterations: Emit `ESCALATION REQUIRED` and report the unresolved decision.

## 6. Test Failure Escalation
For complex test failures, escalate to Pro with:
- Root Cause Hypothesis
- Evidence Needed
- Recommended Fix
- Regression Risk
- Required Validation

## 7. Automated CLI Runner
Run the orchestration engine directly via:
```bash
./bin/orchestrator run --task "<task description>" [--files "file1,file2"] [--override pro|flash]
./bin/orchestrator test [--pillar all|ui|api|perf|security|pen|grounding]
./bin/orchestrator audit
./bin/orchestrator status
```
