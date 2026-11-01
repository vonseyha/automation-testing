"""
Real AI Grounding Test Runner (Agentforce Testing Center Adapter).
Per Section 12:
Connects to the actual Agentforce Testing Center regression mechanism where configured.
Triggers regression batch, polls for completion, retrieves actual results, and captures regression failures.
If Agentforce Testing Center is not configured: returns status = BLOCKED.
Never simulates regression results.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.security.sanitizer import sanitize_data
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.storage import TestStorageManager


class AIGroundingRunner(BaseTestRunner):
    """
    Real AI Grounding Test Runner (Agentforce Testing Center Adapter).
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        testing_center_api_url: Optional[str] = None,
        agentforce_regression_batch_id: Optional[str] = None,
        agentforce_api_token: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="ai_grounding")
        self.storage = storage_manager or TestStorageManager()
        self.testing_center_api_url = testing_center_api_url
        self.agentforce_regression_batch_id = agentforce_regression_batch_id
        self.agentforce_api_token = agentforce_api_token

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        return [
            TestCaseResult(
                test_case_id="AIG-001",
                test_name="Agentforce Grounding & Regression Batch",
                test_pillar="AI Grounding",
                description="Executes Agentforce Testing Center regression batch to verify AI grounding and intent accuracy.",
                execution_status=TestStatus.PENDING,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                details="Individual test-case detail unavailable from runner.",
                expected="Agentforce regression batch executes with all_passed=true",
                runner=self.runner_name,
                feature_id="SYS-004",
                module="System & Integrations",
                priority="P1",
            )
        ]

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """
        Validates whether Agentforce Testing Center endpoint or regression batch ID is configured.
        """
        endpoint = (
            self.testing_center_api_url
            or os.environ.get("AGENTFORCE_TESTING_CENTER_URL")
            or os.environ.get("TESTING_CENTER_API_URL")
        )
        batch_id = self.agentforce_regression_batch_id or os.environ.get("AGENTFORCE_REGRESSION_BATCH_ID")

        if endpoint and batch_id:
            return True, None

        return False, "Agentforce Testing Center integration is not configured in current environment (missing TESTING_CENTER_API_URL or AGENTFORCE_REGRESSION_BATCH_ID)."

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("ai_grounding")
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            tc = TestCaseResult(
                test_case_id="AIG-001",
                test_name="Agentforce Grounding & Regression Batch",
                test_pillar="AI Grounding",
                description="Executes Agentforce Testing Center regression batch to verify AI grounding and intent accuracy.",
                execution_status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=0.0,
                error=reason,
                execution_id=test_run_id,
                details=f"Blocked: {reason}",
                blocking_dependency="Agentforce Testing Center integration",
                missing_configuration="TESTING_CENTER_API_URL or AGENTFORCE_REGRESSION_BATCH_ID",
                required_remediation="Configure TESTING_CENTER_API_URL and AGENTFORCE_REGRESSION_BATCH_ID in environment or config.json.",
                runner=self.runner_name,
                feature_id="SYS-004",
                module="System & Integrations",
                priority="P1",
            )
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={},
                failures=[],
                evidence=[],
                environment=context.get("environment", "agentforce_testing_center"),
                blocked_reason=reason,
                test_cases=[tc],
            )

        # Trigger real execution against Testing Center API
        endpoint = (
            context.get("endpoint")
            or self.testing_center_api_url
            or os.environ.get("TESTING_CENTER_API_URL")
            or os.environ.get("AGENTFORCE_TESTING_CENTER_URL")
        )
        batch_id = (
            context.get("batch_id")
            or self.agentforce_regression_batch_id
            or os.environ.get("AGENTFORCE_REGRESSION_BATCH_ID")
        )
        token = (
            context.get("token")
            or self.agentforce_api_token
            or os.environ.get("AGENTFORCE_API_TOKEN", "")
        )

        url = f"{endpoint.rstrip('/')}/batches/{batch_id}/execute"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_body = resp.read().decode("utf-8")
                res_data = json.loads(res_body)

            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()

            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename="testing_center_batch_result.json",
                content=json.dumps(sanitize_data(res_data), indent=2),
                evidence_type="regression_result",
                description="Agentforce Testing Center batch execution report",
            )

            passed_all = res_data.get("all_passed", False)
            failures = res_data.get("failures", [])

            case_evidence = dict(ev_ref)
            case_evidence["execution_id"] = test_run_id
            case_evidence["test_case_id"] = "AIG-001"
            case_evidence["runner"] = self.runner_name
            case_evidence["timestamp"] = end_time
            case_evidence["log_reference"] = ev_ref.get("path")

            tc = TestCaseResult(
                test_case_id="AIG-001",
                test_name="Agentforce Grounding & Regression Batch",
                test_pillar="AI Grounding",
                description="Executes Agentforce Testing Center regression batch to verify AI grounding and intent accuracy.",
                execution_status=TestStatus.PASSED if passed_all else TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                error=failures[0].get("error") if failures else None,
                evidence=[case_evidence],
                execution_id=test_run_id,
                details=f"Passed: {res_data.get('passed_tests', 0)}/{res_data.get('total_tests', 0)}" if res_data.get("total_tests") else "Individual test-case detail unavailable from runner.",
                failure_reason=failures[0].get("error") if failures else None,
                expected="Agentforce regression batch all_passed=true",
                actual=f"{len(failures)} regression failures detected" if failures else "All tests passed",
                required_action="Review Agentforce prompt grounding and knowledge center articles." if failures else None,
                runner=self.runner_name,
            )

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=TestStatus.PASSED if passed_all else TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={
                    "total_tests": res_data.get("total_tests", 0),
                    "passed_tests": res_data.get("passed_tests", 0),
                    "failed_tests": len(failures),
                },
                failures=failures,
                evidence=[ev_ref],
                environment=context.get("environment", "agentforce_testing_center"),
                raw_result_reference=ev_ref["path"],
                test_cases=[tc],
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            tc = TestCaseResult(
                test_case_id="AIG-001",
                test_name="Agentforce Grounding & Regression Batch",
                test_pillar="AI Grounding",
                description="Executes Agentforce Testing Center regression batch to verify AI grounding and intent accuracy.",
                execution_status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                error=f"Testing Center API error: {str(e)}",
                execution_id=test_run_id,
                details="API request exception",
                failure_reason=str(e),
                expected="HTTP 200 from Agentforce API",
                actual=f"Exception: {str(e)}",
                required_action="Verify Testing Center API connectivity and token authorization.",
                runner=self.runner_name,
            )
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={
                    "total_tests": 0,
                    "passed_tests": 0,
                    "failed_tests": 1,
                },
                failures=[{"error": f"Testing Center API error: {str(e)}"}],
                evidence=[],
                environment=context.get("environment", "agentforce_testing_center"),
                test_cases=[tc],
            )

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError()
