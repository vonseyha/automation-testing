"""
Unit tests for Review Loop Controller.
Per Section 8 & 9.
"""

import unittest

from orchestration.config import OrchestrationConfig
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.models.router import ModelRouter
from orchestration.review.loop import ReviewLoopController
from orchestration.core_types import ReviewDecision, ReviewRequest


class TestReviewLoop(unittest.TestCase):
    def test_loop_terminates_on_clean_approve(self):
        config = OrchestrationConfig.load()
        router = ModelRouter(config)

        # Mock reviewer returning APPROVE immediately
        clean_approve_response = """REVIEW RESULT

Decision:
APPROVE

Architecture Assessment:
Architecture is sound and conforms with specifications.

Critical Findings:
- None

High-Risk Issues:
- None

Recommended Changes:
- None

Testing Requirements:
- None

Reasoning Summary:
Everything looks clean.
"""
        mock = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=lambda prompt: clean_approve_response,
        )
        router.register_client("reviewer", mock)

        controller = ReviewLoopController(config, router)
        req = ReviewRequest(user_requirement="Verify endpoint")
        result = controller.execute_loop(req)

        self.assertEqual(result.decision, ReviewDecision.APPROVE)
        self.assertEqual(len(mock.call_history), 1)

    def test_loop_enforces_max_3_iterations_and_escalates(self):
        """
        Per Section 9:
        Default maximum: 3 review iterations for the same architectural decision.
        If the issue remains unresolved after three iterations:
        ESCALATION REQUIRED and clearly report the unresolved decision.
        """
        config = OrchestrationConfig.load(review_max_iterations=3)
        router = ModelRouter(config)

        # Reviewer that repeatedly rejects or asks for changes
        stubborn_response = """REVIEW RESULT

Decision:
REJECT

Architecture Assessment:
Data integrity risk persists.

Critical Findings:
- Cash ledger balance does not account for voided transactions.

High-Risk Issues:
- Replay attack possible due to lack of nonce validation.

Recommended Changes:
- Required: Fix ledger reconciliation invariant.

Testing Requirements:
- Run Security test suite.

Reasoning Summary:
Issue remains unresolved.
"""
        mock = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=lambda prompt: stubborn_response,
        )
        router.register_client("reviewer", mock)

        controller = ReviewLoopController(config, router)
        req = ReviewRequest(user_requirement="Complex refactoring")

        fix_attempts = []
        def mock_apply_fixes(res, iter_num):
            fix_attempts.append(iter_num)
            return [f"Attempted fix in iteration {iter_num}"]

        result = controller.execute_loop(
            req,
            apply_fixes_callback=mock_apply_fixes,
        )

        # Loop must stop at 3 iterations
        self.assertEqual(len(mock.call_history), 3)
        self.assertEqual(len(fix_attempts), 2)  # Applied fixes on iter 1 and 2, iter 3 is final exit
        self.assertIn("ESCALATION REQUIRED", result.reasoning_summary)
        self.assertIn("3 review iterations", result.reasoning_summary)


if __name__ == "__main__":
    unittest.main()
