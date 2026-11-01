# Model Selection Guidelines: Master Agent & Specialist Reviewer

This workspace operates on a dual-model orchestration architecture:

- **Primary Master Agent**: **Gemini 3.8 Flash High**
  - **Role**: Primary worker and orchestrator. Owns planning, inspecting, editing code, executing tools, running tests, debugging, and maintaining documentation.
  - **Thinking Level**: High.
  - **Scope**: Used autonomously for all normal tasks, including feature implementation, routine bug fixes, test execution, CRUD endpoints, and UI refinements.

- **Specialist Reviewer**: **Gemini 3.1 Pro High**
  - **Role**: Specialist Architecture & Code Reviewer. Consulted strictly when deeper reasoning, high-risk trade-offs, or complex architecture decisions are required.
  - **Thinking Level**: High.
  - **Scope**: Used for major subsystem designs, strangler-fig migration architecture, security/auth modifications, financial ledger invariants, complex refactoring, multi-file changes (>=4 files), and recurring test failures.

## Escalation Policy Rules

1. **Normal Tasks (Stay on Gemini 3.8 Flash High)**:
   - Small formatting and lint fixes.
   - Simple CRUD changes and schema additions.
   - Minor UI/styling adjustments.
   - Straightforward configuration updates.
   - Simple documentation edits.
   - Routine test execution.

2. **Specialist Escalation (Call Gemini 3.1 Pro High)**:
   - **Architecture**: New subsystems, cross-repo contracts, persistence changes, migration patterns.
   - **Security**: Authentication, authorization, HMAC, JWT, prompt injection, data isolation.
   - **Financial Invariants**: GeneralLedger reconciliation, cashflow cash_bank closing balance, IsVoided filters.
   - **Multi-File Scope**: Changes spanning 4 or more files across packages.
   - **Failures**: Security test failures, or failures unresolved after 2 attempts.

3. **User Overrides**:
   - Explicit prompt requests like `"review this architecture"` or `"use the pro reviewer"` trigger escalation.
   - Explicit prompt requests like `"do not escalate"` or `"flash only"` keep execution on Gemini 3.8 Flash High.
