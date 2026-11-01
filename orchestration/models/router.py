"""
Model Router Abstraction.
Per Section 13 & 15:
Decouples the Master Agent from hardcoded model implementations.
Coordinates PrimaryAgent (Gemini 3.8 Flash High), ArchitectureReviewer (Gemini 3.1 Pro High),
and optional specialist reviewers. Gracefully handles model unavailability.
"""

from typing import Dict, Optional

from orchestration.config import OrchestrationConfig
from orchestration.models.base import BaseModelClient
from orchestration.models.gemini_client import GeminiApiClient
from orchestration.review.contract import ReviewContractBuilder
from orchestration.review.normalizer import ReviewNormalizer
from orchestration.core_types import (
    ReviewDecision,
    ReviewRequest,
    ReviewResult,
    ReviewerStatus,
    TestFailureAnalysis,
)


class ModelRouter:
    """
    Routes requests to appropriate models and manages client implementations.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()
        self.primary_model_id = self.config.primary_model
        self.primary_thinking_level = self.config.primary_thinking_level.value
        self.review_model_id = self.config.review_model
        self.review_thinking_level = self.config.review_thinking_level.value

        # Registry of specialist clients
        self._clients: Dict[str, BaseModelClient] = {}

        # Default initialization: GeminiApiClient for primary and reviewer
        self._init_default_primary()
        self._init_default_reviewer()

    def _init_default_primary(self) -> None:
        """
        Initializes default Gemini API client for the Primary Master Agent (Gemini 3.8 Flash High).
        """
        gemini_client = GeminiApiClient(
            model_id=self.primary_model_id,
            thinking_level=self.primary_thinking_level,
            api_key=self.config.gemini_api_key,
            endpoint=self.config.gemini_api_endpoint,
        )
        self.register_client("primary", gemini_client)

    def _init_default_reviewer(self) -> None:
        """
        Initializes default Gemini API client for the Pro Reviewer (Gemini 3.1 Pro High).
        """
        gemini_client = GeminiApiClient(
            model_id=self.review_model_id,
            thinking_level=self.review_thinking_level,
            api_key=self.config.gemini_api_key,
            endpoint=self.config.gemini_api_endpoint,
        )
        self.register_client("reviewer", gemini_client)

    def register_client(self, role: str, client: BaseModelClient) -> None:
        """
        Registers or overrides a client for a specific role (e.g. 'reviewer', 'security_specialist').
        """
        self._clients[role] = client

    def get_client(self, role: str = "reviewer") -> Optional[BaseModelClient]:
        return self._clients.get(role)

    def route_review(self, request: ReviewRequest, iteration: int = 1) -> ReviewResult:
        """
        Routes an architectural review request to the Pro Reviewer.
        Handles graceful fallback if the reviewer is unavailable (Section 15).
        """
        reviewer = self.get_client("reviewer")

        if not reviewer or not reviewer.is_available():
            reason = reviewer.get_unavailability_reason() if reviewer else "No reviewer client registered."
            return ReviewResult(
                decision=ReviewDecision.UNAVAILABLE,
                architecture_assessment="Gemini 3.1 Pro High reviewer is currently unavailable in this environment.",
                critical_findings=[],
                high_risk_issues=[],
                required_changes=[],
                recommended_changes=[],
                optional_improvements=[],
                testing_requirements=["Verify behavior with automated test engine before proceeding."],
                reasoning_summary=f"Reviewer unavailable: {reason}. Master Agent should assess risk before proceeding.",
                raw_response="",
                reviewer_status=ReviewerStatus.UNAVAILABLE,
                reviewer_model=self.review_model_id,
                iteration=iteration,
                unavailability_reason=reason,
                fallback_strategy="Continue with Gemini 3.8 Flash High if risk is manageable, or pause for user review.",
            )

        # Build prompt & system instruction
        prompt = ReviewContractBuilder.build_review_prompt(request)
        system_instruction = ReviewContractBuilder.REVIEWER_SYSTEM_INSTRUCTION

        try:
            raw_text = reviewer.generate(prompt=prompt, system_instruction=system_instruction)
            result = ReviewNormalizer.parse_review(
                text=raw_text,
                reviewer_model=self.review_model_id,
                iteration=iteration,
            )
            return result
        except Exception as e:
            return ReviewResult(
                decision=ReviewDecision.UNAVAILABLE,
                architecture_assessment="Reviewer execution failed with an exception.",
                critical_findings=[str(e)],
                reasoning_summary=f"Execution error invoking {self.review_model_id}: {str(e)}",
                raw_response=str(e),
                reviewer_status=ReviewerStatus.UNAVAILABLE,
                reviewer_model=self.review_model_id,
                iteration=iteration,
                unavailability_reason=str(e),
                fallback_strategy="Fallback to primary model analysis.",
            )

    def route_failure_diagnosis(
        self,
        pillar: str,
        test_name: str,
        error_message: str,
        evidence: list,
        code_context: Optional[str] = None,
    ) -> TestFailureAnalysis:
        """
        Routes a complex test failure diagnosis to the Pro Reviewer per Section 11.
        """
        reviewer = self.get_client("reviewer")

        if not reviewer or not reviewer.is_available():
            reason = reviewer.get_unavailability_reason() if reviewer else "No reviewer client registered."
            return TestFailureAnalysis(
                root_cause_hypothesis=f"Diagnostic reviewer unavailable: {reason}",
                evidence_needed=["Review test stack trace and component error logs manually."],
                recommended_fix="Master Agent should inspect local error output.",
                regression_risk="Unknown - manual verification required.",
                required_validation=["Re-run affected test suite."],
                reviewer_model=self.review_model_id,
            )

        prompt = ReviewContractBuilder.build_failure_prompt(
            pillar=pillar,
            test_name=test_name,
            error_message=error_message,
            evidence=evidence,
            code_context=code_context,
        )
        system_instruction = ReviewContractBuilder.FAILURE_REVIEWER_SYSTEM_INSTRUCTION

        try:
            raw_text = reviewer.generate(prompt=prompt, system_instruction=system_instruction)
            return ReviewNormalizer.parse_failure_diagnosis(
                text=raw_text,
                reviewer_model=self.review_model_id,
            )
        except Exception as e:
            return TestFailureAnalysis(
                root_cause_hypothesis=f"Reviewer diagnosis call failed: {str(e)}",
                evidence_needed=[],
                recommended_fix="Analyze local test error output directly.",
                regression_risk="Unassessed due to invocation error.",
                required_validation=["Re-run local test."],
                reviewer_model=self.review_model_id,
            )
