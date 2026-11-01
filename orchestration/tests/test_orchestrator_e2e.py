"""
End-to-End integration tests for MasterAgentOrchestrator.
Per Section 1, 3, 8, 9, 17, 19.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from orchestration.config import OrchestrationConfig
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.orchestrator import MasterAgentOrchestrator
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestExecutionResult,
    TestStatus,
)


class MockPassRunner(BaseTestRunner):
    """Mock runner for testing orchestrator state transitions in unit tests."""

    def __init__(self, workspace_root: Path, runner_name: str):
        super().__init__(workspace_root=workspace_root, runner_name=runner_name)

    def validate_configuration(self):
        return True, None

    def execute(self, context=None):
        return TestExecutionResult(
            test_run_id=context.get("test_run_id", "run_mock") if context else "run_mock",
            test_type=self.runner_name,
            status=TestStatus.PASSED,
            started_at="",
            completed_at="",
            duration_ms=1.0,
            evidence=[{"path": f"evidence_{self.runner_name}.json", "evidence_type": "log"}],
        )

    def normalize_result(self, raw_result):
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError()


class TestOrchestratorE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            audit_dir=self.temp_dir / ".antigravity" / "audit",
            audit_jsonl_file=self.temp_dir / ".antigravity" / "audit" / "e2e_audit.jsonl",
            audit_md_file=self.temp_dir / ".antigravity" / "audit" / "e2e_audit.md",
        )
        self.orchestrator = MasterAgentOrchestrator(self.config)
        # Register mock passing test runners so E2E orchestrator state transitions are tested in isolation
        for r_name in [
            "api_connectivity",
            "ui_channel",
            "api_integration",
            "performance",
            "security_access",
            "penetration",
            "ai_grounding",
        ]:
            self.orchestrator.test_engine.register_runner(r_name, MockPassRunner(self.temp_dir, r_name))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_e2e_normal_task_flow(self):
        """
        Normal tasks must run entirely on Gemini 3.8 Flash High without calling Pro Reviewer.
        """
        output = self.orchestrator.orchestrate_task(
            task_description="Fix minor typo in comments and documentation",
            changed_files=["README.md"],
            run_tests=True,
        )

        self.assertEqual(output["complexity"], "NORMAL")
        self.assertEqual(output["reviewer_used"], "NO")
        self.assertEqual(output["reviewer_result"], "N/A")
        self.assertEqual(output["status"], "SUCCESS")
        self.assertTrue(len(output["tests"]) >= 6)

        # Verify audit trail recorded event
        records = self.orchestrator.audit_logger.get_recent_records(1)
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["review_requested"])
        self.assertEqual(records[0]["primary_model"], "gemini-3.8-flash")

    def test_e2e_complex_architecture_task_flow(self):
        """
        Complex architecture tasks must escalate to Gemini 3.1 Pro High and include Section 19 outputs.
        """
        # Register available mock reviewer that approves after iteration 1 fixes
        def response_generator(prompt: str) -> str:
            if "Iteration 2" in prompt:
                return """REVIEW RESULT

Decision:
APPROVE

Architecture Assessment:
Previous findings have been resolved. The subsystem architecture is approved.

Critical Findings:
- None

High-Risk Issues:
- None

Recommended Changes:
- None

Testing Requirements:
- Verify 6 pillars.

Reasoning Summary:
All required changes have been verified.
"""
            return """REVIEW RESULT

Decision:
APPROVE WITH CHANGES

Architecture Assessment:
The architecture is sound but requires query bounding.

Critical Findings:
- None

High-Risk Issues:
- Potential unhandled null reference.

Recommended Changes:
- Required: Enforce IsVoided filter on queries.
- Recommended: Batch related collections.

Testing Requirements:
- Run all test suites.

Reasoning Summary:
Applying required fixes resolves risks.
"""

        mock_reviewer = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=response_generator,
        )
        self.orchestrator.model_router.register_client("reviewer", mock_reviewer)

        output = self.orchestrator.orchestrate_task(
            task_description="Design new subsystem architecture for event-driven async reconciliation",
            changed_files=["cashflow.service.ts", "ledger.service.ts", "worker.service.ts", "queue.service.ts"],
            run_tests=True,
        )

        self.assertEqual(output["complexity"], "COMPLEX")
        self.assertEqual(output["reviewer_used"], "YES")
        self.assertEqual(output["reviewer_result"], "APPROVE")
        self.assertEqual(output["status"], "SUCCESS")
        self.assertIn("architecture_decision", output)
        self.assertIn("why_review_was_triggered", output)
        self.assertIn("reviewer_findings", output)

        # Verify audit trail
        records = self.orchestrator.audit_logger.get_recent_records(1)
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["review_requested"])
        self.assertEqual(records[0]["reviewer_model"], "gemini-3.1-pro-preview")
        self.assertEqual(records[0]["reviewer_decision"], "APPROVE")

    def test_e2e_escalation_required_when_unresolved_after_3_rounds(self):
        """
        Per Section 9: If 3 review iterations cannot resolve issues, status must be ESCALATION_REQUIRED.
        """
        stubborn_reviewer = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=lambda p: """REVIEW RESULT

Decision:
REJECT

Architecture Assessment:
Architecture has unresolved fatal flaws.

Critical Findings:
- Severe regression risk in billing pipeline.

Recommended Changes:
- Required: Rewrite queue handler.

Testing Requirements:
- Run all tests.

Reasoning Summary:
Not approved.
""",
        )
        self.orchestrator.model_router.register_client("reviewer", stubborn_reviewer)

        output = self.orchestrator.orchestrate_task(
            task_description="Rewrite core microservice queue architecture",
            changed_files=["worker.service.ts", "queue.service.ts", "gateway.service.ts", "event.service.ts"],
            run_tests=False,
        )

        self.assertEqual(output["status"], "ESCALATION_REQUIRED")
        self.assertEqual(output["complexity"], "COMPLEX")

    def test_e2e_unavailable_reviewer_graceful_fallback(self):
        """
        Per Section 15: If Pro is unavailable, do not pretend it executed. Report status UNAVAILABLE.
        """
        unavailable_reviewer = MockSpecialistClient(
            is_available_flag=False,
            unavailability_reason="API key not present in environment.",
        )
        self.orchestrator.model_router.register_client("reviewer", unavailable_reviewer)

        output = self.orchestrator.orchestrate_task(
            task_description="Implement new authentication architecture",
            run_tests=True,
        )

        self.assertEqual(output["complexity"], "COMPLEX")
        self.assertEqual(output["reviewer_used"], "YES")
        self.assertEqual(output["reviewer_result"], "UNAVAILABLE")
        self.assertEqual(output["status"], "COMPLETED_WITH_REVIEWER_FALLBACK")


if __name__ == "__main__":
    unittest.main()
