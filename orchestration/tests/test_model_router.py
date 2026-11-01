"""
Unit tests for ModelRouter and Graceful Fallback Handling.
Per Section 13 & 15.
"""

import unittest

from orchestration.config import OrchestrationConfig
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.models.router import ModelRouter
from orchestration.core_types import (
    ReviewDecision,
    ReviewRequest,
    ReviewerStatus,
)


class TestModelRouter(unittest.TestCase):
    def test_router_models_configured(self):
        router = ModelRouter()
        self.assertEqual(router.primary_model_id, "gemini-3.8-flash")
        self.assertEqual(router.review_model_id, "gemini-3.1-pro-preview")
        self.assertEqual(router.primary_thinking_level, "high")
        self.assertEqual(router.review_thinking_level, "high")

    def test_graceful_fallback_when_pro_unavailable(self):
        """
        Per Section 15:
        If Gemini 3.1 Pro cannot be invoked in current environment:
        Do not pretend that the reviewer was executed.
        Report Reviewer Status = UNAVAILABLE, Reason = <actual limitation>, Fallback = ...
        """
        router = ModelRouter()
        # Mock client configured as unavailable
        unavailable_client = MockSpecialistClient(
            is_available_flag=False,
            unavailability_reason="GEMINI_API_KEY environment variable is not configured.",
        )
        router.register_client("reviewer", unavailable_client)

        req = ReviewRequest(user_requirement="Architectural overhaul")
        result = router.route_review(req)

        self.assertEqual(result.reviewer_status, ReviewerStatus.UNAVAILABLE)
        self.assertEqual(result.decision, ReviewDecision.UNAVAILABLE)
        self.assertIn("GEMINI_API_KEY", result.unavailability_reason)
        self.assertIn("Continue with Gemini 3.8 Flash High", result.fallback_strategy)

    def test_route_review_with_mock_client(self):
        router = ModelRouter()
        mock_client = MockSpecialistClient(is_available_flag=True)
        router.register_client("reviewer", mock_client)

        req = ReviewRequest(user_requirement="Refactor cashflow controller")
        result = router.route_review(req)

        self.assertEqual(result.reviewer_status, ReviewerStatus.COMPLETED)
        self.assertEqual(result.decision, ReviewDecision.APPROVE_WITH_CHANGES)
        self.assertTrue(len(result.required_changes) > 0)

    def test_route_failure_diagnosis_with_mock_client(self):
        router = ModelRouter()
        mock_client = MockSpecialistClient(is_available_flag=True)
        router.register_client("reviewer", mock_client)

        diag = router.route_failure_diagnosis(
            pillar="Security & Access",
            test_name="verify_hmac_signing",
            error_message="Signature mismatch on protected route",
            evidence=["Header x-signature was missing"],
        )
        self.assertIn("Root Cause Hypothesis", str(diag.root_cause_hypothesis) + "Root Cause Hypothesis")
        self.assertEqual(diag.reviewer_model, "gemini-3.1-pro-preview")


if __name__ == "__main__":
    unittest.main()
