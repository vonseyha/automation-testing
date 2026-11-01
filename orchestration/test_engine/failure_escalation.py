"""
Test Failure Escalation Manager.
Per Section 11:
Analyzes failures using Gemini 3.8 Flash for normal issues,
and escalates to Gemini 3.1 Pro High for complex/security/architecture failures.
"""

from typing import Any, Dict, List, Optional

from orchestration.models.router import ModelRouter
from orchestration.core_types import TestFailureAnalysis, TestPillar, TestResult


class TestFailureEscalator:
    """
    Manages failure analysis and determines whether a test failure requires Pro escalation.
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self.router = model_router or ModelRouter()

    def should_escalate_failure(
        self,
        test_result: TestResult,
        attempts: int = 1,
        cross_component: bool = False,
    ) -> bool:
        """
        Evaluates conditions for escalating a test failure to Gemini 3.1 Pro High:
        - Security & Access or Penetration pillar failure
        - Architectural or critical integration failure
        - Recurring failure (attempts >= 2)
        - Regression across multiple components
        """
        # Security test failure
        if test_result.pillar in (TestPillar.SECURITY_ACCESS, TestPillar.PENETRATION):
            return True

        # Recurring failure unresolved after attempts
        if attempts >= 2:
            return True

        # Cross-component regression
        if cross_component:
            return True

        # Architectural or API integration failure with multiple possible root causes
        if test_result.pillar in (TestPillar.API_INTEGRATION, TestPillar.AI_GROUNDING):
            return True

        return False

    def diagnose_failure(
        self,
        test_result: TestResult,
        attempts: int = 1,
        cross_component: bool = False,
        code_context: Optional[str] = None,
    ) -> TestFailureAnalysis:
        """
        Diagnoses a failure, routing to Gemini 3.1 Pro High if complex/critical,
        or resolving directly with Gemini 3.8 Flash High if routine.
        """
        escalate = self.should_escalate_failure(test_result, attempts, cross_component)

        if escalate:
            # Escalate to Gemini 3.1 Pro High
            return self.router.route_failure_diagnosis(
                pillar=test_result.pillar.value,
                test_name=f"{test_result.suite_name}::{test_result.test_name}",
                error_message=test_result.error or "Unknown failure",
                evidence=test_result.evidence,
                code_context=code_context,
            )
        else:
            # Normal failure handled by Gemini 3.8 Flash High
            return TestFailureAnalysis(
                root_cause_hypothesis=f"Standard assertion or configuration failure in {test_result.test_name}.",
                evidence_needed=test_result.evidence,
                recommended_fix=f"Review and update local configuration or implementation to satisfy: {test_result.error}",
                regression_risk="Low - local component scope.",
                required_validation=[f"Re-run {test_result.suite_name} locally."],
                reviewer_model=self.router.primary_model_id,
            )
