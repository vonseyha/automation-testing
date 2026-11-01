"""
Review Loop Controller.
Per Section 8 & 9:
Coordinates the Plan -> Implement -> Test -> Pro Review -> Fix -> Re-test loop.
Enforces the maximum 3-iteration limit and raises ESCALATION REQUIRED when stuck.
"""

from typing import Callable, List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.models.router import ModelRouter
from orchestration.core_types import (
    ReviewDecision,
    ReviewRequest,
    ReviewResult,
    ReviewerStatus,
)


class ReviewLoopController:
    """
    Manages iterative review rounds with Gemini 3.1 Pro High,
    preventing infinite loops and enforcing the 3-iteration maximum limit.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None, model_router: Optional[ModelRouter] = None):
        self.config = config or OrchestrationConfig.load()
        self.router = model_router or ModelRouter(self.config)
        self.max_iterations = self.config.review_max_iterations

    def execute_loop(
        self,
        initial_request: ReviewRequest,
        apply_fixes_callback: Optional[Callable[[ReviewResult, int], List[str]]] = None,
        run_tests_callback: Optional[Callable[[], bool]] = None,
    ) -> ReviewResult:
        """
        Executes the review loop up to max_iterations (default: 3).

        Args:
            initial_request: The review context.
            apply_fixes_callback: Callback invoked by Master Agent to apply required/recommended fixes.
            run_tests_callback: Callback to re-run test validation after fixes.

        Returns:
            The final ReviewResult. If still unresolved after max_iterations, marks decision as REJECT
            and flags ESCALATION REQUIRED.
        """
        current_request = initial_request
        iteration = 1
        last_result: Optional[ReviewResult] = None

        while iteration <= self.max_iterations:
            # 1. Route to Specialist Reviewer
            result = self.router.route_review(current_request, iteration=iteration)
            last_result = result

            # If reviewer is unavailable, return immediately so Master Agent can proceed with fallback
            if result.reviewer_status == ReviewerStatus.UNAVAILABLE:
                return result

            # 2. Check Decision
            if result.decision == ReviewDecision.APPROVE and not result.critical_findings and not result.required_changes:
                # Clean approval - loop terminates successfully
                return result

            # If there are changes required or recommended:
            if iteration >= self.max_iterations:
                # Max iterations exceeded - Break loop and signal ESCALATION REQUIRED (Section 9)
                result.reasoning_summary = (
                    f"ESCALATION REQUIRED: Architectural decision or findings remained unresolved after "
                    f"{self.max_iterations} review iterations. Master Agent must escalate to human developer. "
                    f"Remaining unresolved items: {'; '.join(result.required_changes or result.critical_findings)}"
                )
                return result

            # 3. Master Agent applies fixes
            applied_changes: List[str] = []
            if apply_fixes_callback:
                applied_changes = apply_fixes_callback(result, iteration)

            # 4. Master Agent re-runs tests
            tests_passed = True
            if run_tests_callback:
                tests_passed = run_tests_callback()

            # 5. Prepare context for next review iteration
            iteration += 1
            current_request = ReviewRequest(
                user_requirement=current_request.user_requirement,
                relevant_architecture=current_request.relevant_architecture,
                current_implementation=f"{current_request.current_implementation}\nIteration {iteration - 1} fixes applied: {applied_changes}",
                changed_files=current_request.changed_files,
                relevant_code=current_request.relevant_code,
                existing_constraints=current_request.existing_constraints,
                test_results={"iteration": iteration - 1, "tests_passed": tests_passed},
                known_failures=[] if tests_passed else ["Test failure observed in iteration re-validation."],
                design_alternatives_considered=current_request.design_alternatives_considered,
                specific_question=f"Iteration {iteration}: Verify if the applied changes resolved previous findings: {result.required_changes}",
            )

        return last_result or ReviewResult(decision=ReviewDecision.REJECT, reasoning_summary="No review results produced.")
