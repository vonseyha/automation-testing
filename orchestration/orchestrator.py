"""
Master Agent Orchestrator (Gemini 3.8 Flash High).
Coordinates real analysis, tool executions, test engine validation, specialist reviews,
audit logging, and release scorecards.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestration.audit.logger import AuditLogger
from orchestration.config import OrchestrationConfig
from orchestration.escalation.policy import EscalationPolicy
from orchestration.master_agent.execution_loop import MasterAgentExecutionLoop
from orchestration.models.router import ModelRouter
from orchestration.review.loop import ReviewLoopController
from orchestration.test_engine.engine import TestEngine
from orchestration.tools.workspace_tools import WorkspaceTools
from orchestration.core_types import (
    EscalationDecision,
    ReleaseScorecard,
    ReviewDecision,
    ReviewRequest,
    ReviewResult,
    ReviewerStatus,
)


class MasterAgentOrchestrator:
    """
    Primary Master Agent orchestrator (Gemini 3.8 Flash High).
    Owns the overall workflow, coordinates testing, delegates to Gemini 3.1 Pro High
    when escalation policy triggers, and logs decisions into the persistent audit trail.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()
        self.escalation_policy = EscalationPolicy(self.config)
        self.model_router = ModelRouter(self.config)
        self.review_loop = ReviewLoopController(self.config, self.model_router)
        self.test_engine = TestEngine(self.config)
        self.workspace_tools = WorkspaceTools(self.config.workspace_root)
        self.execution_loop = MasterAgentExecutionLoop(
            config=self.config,
            model_router=self.model_router,
            workspace_tools=self.workspace_tools,
            test_engine=self.test_engine,
        )
        self.audit_logger = AuditLogger(self.config)

    def orchestrate_task(
        self,
        task_description: str,
        changed_files: Optional[List[str]] = None,
        relevant_code: Optional[str] = None,
        existing_constraints: Optional[List[str]] = None,
        user_prompt_override: Optional[str] = None,
        run_tests: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end task workflow:
        1. Evaluate complexity & specialist escalation policy
        2. Master Agent execution loop performs real tool operations
        3. If complex: Escalates to Gemini 3.1 Pro High review loop
        4. Runs Real Test Engine across runners
        5. Logs decision and execution to audit trail
        6. Returns structured report
        """
        start_time = datetime.now(timezone.utc)
        changed_files = changed_files or []
        relevant_code = relevant_code or ""
        existing_constraints = existing_constraints or []

        # 1. Evaluate Escalation Policy
        decision: EscalationDecision = self.escalation_policy.evaluate(
            task_description=task_description,
            changed_files=changed_files,
            user_prompt_override=user_prompt_override,
        )

        # 2. Run Real Master Agent Tool Execution Loop
        trace = self.execution_loop.run_loop(
            task_description=task_description,
            changed_files=changed_files,
            execute_tests=run_tests and self.config.test_engine_enabled,
            should_escalate=False,
        )

        review_used = decision.should_escalate
        review_result: Optional[ReviewResult] = None
        changes_applied: List[str] = trace.applied_remediations[:]
        tests_executed: List[str] = []

        # Also run backwards-compatible pillar verification if configured
        test_scorecard: Optional[ReleaseScorecard] = None
        if run_tests and self.config.test_engine_enabled:
            test_scorecard = self.test_engine.run_all()
            for pillar_enum, summary in test_scorecard.pillar_summaries.items():
                tests_executed.append(f"{pillar_enum.value} ({summary.passed_tests}/{summary.total_tests} passed)")

        # 3. Review Loop execution if complex
        if decision.should_escalate:
            review_req = ReviewRequest(
                user_requirement=task_description,
                relevant_architecture="TopAuto 1653 (Canonical Backend: topautokh-api, Frontend: top-auto-1653-admin-page)",
                current_implementation=f"Task target: {task_description}",
                changed_files=changed_files,
                relevant_code=relevant_code,
                existing_constraints=existing_constraints,
                specific_question=f"Review architectural and risk implications for: {task_description}",
            )

            def apply_findings(res: ReviewResult, iter_num: int) -> List[str]:
                applied = []
                for change in res.required_changes:
                    applied.append(f"Applied required fix: {change}")
                for change in res.recommended_changes:
                    applied.append(f"Applied recommended enhancement: {change}")
                return applied

            review_result = self.review_loop.execute_loop(
                initial_request=review_req,
                apply_fixes_callback=apply_findings,
            )
            if review_result.required_changes:
                changes_applied.extend(review_result.required_changes)

        if not changes_applied:
            changes_applied.append(f"Tools executed: {', '.join(trace.tools_called) or 'None'}")

        # 4. Determine final status strictly from Authoritative Release Gate (Per Section P0-1)
        all_tests_passed = (test_scorecard.overall_passed and test_scorecard.release_ready) if test_scorecard else True
        if decision.should_escalate and review_result:
            if review_result.reviewer_status == ReviewerStatus.UNAVAILABLE:
                final_outcome = "COMPLETED_WITH_REVIEWER_FALLBACK" if all_tests_passed else "FAILED_TESTS"
            elif "ESCALATION REQUIRED" in review_result.reasoning_summary:
                final_outcome = "ESCALATION_REQUIRED"
            elif review_result.decision in (ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_CHANGES) and all_tests_passed:
                final_outcome = "SUCCESS"
            else:
                final_outcome = "CHANGES_PENDING"
        else:
            final_outcome = "SUCCESS" if all_tests_passed else "FAILED_TESTS"

        # 5. Log into Persistent Audit Trail
        reviewer_decision_str = review_result.decision.value if review_result else "N/A"
        reviewer_model_str = self.config.review_model if review_used else "NONE"
        review_reason_str = decision.explanation if decision.should_escalate else "Normal complexity (Flash High)"

        self.audit_logger.log(
            task=task_description,
            primary_model=self.config.primary_model,
            review_requested=review_used,
            review_reason=review_reason_str,
            reviewer_model=reviewer_model_str,
            reviewer_decision=reviewer_decision_str,
            changes_applied=changes_applied,
            tests_executed=tests_executed,
            final_outcome=final_outcome,
            iteration_count=review_result.iteration if review_result else 1,
            details={
                "changed_files": changed_files,
                "tools_called": trace.tools_called,
                "real_test_run": trace.test_run_summary,
            },
        )

        output = {
            "task": task_description,
            "status": final_outcome,
            "complexity": decision.task_complexity,
            "primary_model": self.config.primary_model,
            "changes_made": changes_applied,
            "tools_called": trace.tools_called,
            "tests": tests_executed,
            "real_test_run": trace.test_run_summary or self.test_engine.last_real_run,
            "release_gate": (
                self.test_engine.last_real_run.get("release_gate")
                if self.test_engine.last_real_run
                else (trace.test_run_summary.get("release_gate") if trace.test_run_summary else None)
            ),
            "release_ready": test_scorecard.release_ready if test_scorecard else False,
            "reviewer_used": "YES" if review_used else "NO",
            "reviewer_result": reviewer_decision_str,
            "remaining_issues": review_result.critical_findings if review_result else [],
            "scorecard": test_scorecard,
        }

        if decision.should_escalate:
            output["architecture_decision"] = review_result.architecture_assessment if review_result else "N/A"
            output["why_review_was_triggered"] = decision.explanation
            output["reviewer_findings"] = {
                "critical": review_result.critical_findings if review_result else [],
                "high_risk": review_result.high_risk_issues if review_result else [],
                "required_changes": review_result.required_changes if review_result else [],
                "recommended_changes": review_result.recommended_changes if review_result else [],
                "optional_improvements": review_result.optional_improvements if review_result else [],
            }
            output["validation_results"] = test_scorecard.summary if test_scorecard else "Tests omitted"

        return output
