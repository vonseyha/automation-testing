"""
Real Release Gate Evaluation.
Per Section 17:
Strictly determines release readiness based on actual execution results.
- READY FOR ROLLOUT: only when all required tests PASSED.
- NOT READY: when any required tests FAILED or BLOCKED.
- VALIDATION INCOMPLETE: when required tests remain PENDING.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from orchestration.test_engine.contract import TestExecutionResult, TestStatus


class ReleaseStatus(str, Enum):
    READY_FOR_ROLLOUT = "READY FOR ROLLOUT"
    NOT_READY = "NOT READY"
    VALIDATION_INCOMPLETE = "VALIDATION INCOMPLETE"


class ReleaseGateEvaluator:
    """
    Evaluates whether a test run satisfies production release criteria.
    """

    def __init__(self, required_test_types: Optional[List[str]] = None):
        # Default required pillars
        self.required_test_types = required_test_types or [
            "api_integration",
            "security_access",
            "penetration",
        ]

    def evaluate(self, results: List[TestExecutionResult]) -> Dict[str, Any]:
        result_map = {r.test_type: r for r in results}

        passed_count = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_count = sum(1 for r in results if r.status == TestStatus.FAILED)
        blocked_count = sum(1 for r in results if r.status == TestStatus.BLOCKED)
        pending_count = sum(1 for r in results if r.status == TestStatus.PENDING)
        skipped_count = sum(1 for r in results if r.status == TestStatus.SKIPPED)

        has_failed_or_blocked = False
        has_pending_or_missing = False
        has_missing_evidence = False
        blocking_reasons = []
        informational_warnings = []

        for req_type in self.required_test_types:
            if req_type not in result_map:
                has_pending_or_missing = True
                blocking_reasons.append(f"Required test '{req_type}' was not executed.")
                continue

            r = result_map[req_type]
            if r.status in (TestStatus.FAILED, TestStatus.BLOCKED):
                has_failed_or_blocked = True
                reason = r.blocked_reason or (r.failures[0].get("error") if r.failures and "error" in r.failures[0] else (r.failures[0].get("message") if r.failures else "Failed assertions"))
                blocking_reasons.append(f"Required test '{req_type}' is {r.status.value}: {reason}")
            elif r.status == TestStatus.PENDING:
                has_pending_or_missing = True
                blocking_reasons.append(f"Required test '{req_type}' is PENDING.")
            elif r.status == TestStatus.PASSED:
                if not r.evidence or len(r.evidence) == 0:
                    has_missing_evidence = True
                    blocking_reasons.append(f"Required test '{req_type}' has no evidence artifacts recorded.")

        for r in results:
            if r.test_type in self.required_test_types:
                continue
            if r.status in (TestStatus.FAILED, TestStatus.BLOCKED):
                reason = r.blocked_reason or (r.failures[0].get("error") if r.failures and "error" in r.failures[0] else (r.failures[0].get("message") if r.failures else "Failed assertions"))
                informational_warnings.append(f"Optional test '{r.test_type}' is {r.status.value}: {reason}")

        required_pending = sum(
            1 for rt in self.required_test_types
            if rt in result_map and result_map[rt].status == TestStatus.PENDING
        )

        if has_failed_or_blocked:
            status = ReleaseStatus.NOT_READY
        elif has_pending_or_missing or has_missing_evidence or required_pending > 0:
            status = ReleaseStatus.VALIDATION_INCOMPLETE
        elif all(
            req in result_map and result_map[req].status == TestStatus.PASSED
            for req in self.required_test_types
        ) and not has_missing_evidence:
            status = ReleaseStatus.READY_FOR_ROLLOUT
        else:
            status = ReleaseStatus.NOT_READY

        return {
            "status": status.value,
            "ready_for_rollout": status == ReleaseStatus.READY_FOR_ROLLOUT,
            "total_tests": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "blocked": blocked_count,
            "pending": pending_count,
            "skipped": skipped_count,
            "blocking_reasons": blocking_reasons,
            "informational_warnings": informational_warnings,
        }
