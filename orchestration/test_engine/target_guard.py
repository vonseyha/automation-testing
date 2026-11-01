"""
Remote-target guard.

Several API cases create or change data (cars, sale letters, a cashflow
transaction, ...). Running them against a shared or production backend would
pollute real data, so the engine refuses non-local targets unless the operator
explicitly opts in with ALLOW_REMOTE_TARGET=1 (for a disposable test
environment only).

When the guard trips, every suite that talks to the backend is reported as
BLOCKED with a clear remediation, and no request is sent.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)

# Runners that send requests to API_BASE_URL / SECURITY_BASE_URL.
GUARDED_RUNNERS = ("api_connectivity", "api_integration", "security_access", "performance")

ALLOW_ENV = "ALLOW_REMOTE_TARGET"


def is_local_host(host: str) -> bool:
    host = (host or "").strip().lower().strip("[]")
    if not host:
        return False
    return (
        host in ("localhost", "::1", "0.0.0.0")
        or host.endswith(".localhost")
        or host.startswith("127.")
    )


def remote_targets(urls: Dict[str, Optional[str]]) -> List[str]:
    """Returns 'NAME=url' entries whose host is not local."""
    bad = []
    for name, url in urls.items():
        if not url:
            continue
        host = urlparse(url if "://" in url else f"http://{url}").hostname or ""
        if not is_local_host(host):
            bad.append(f"{name}={url}")
    return bad


def remote_target_violation(config: Any) -> Optional[str]:
    """Returns a reason string when the configured targets are remote and not allowed."""
    if os.environ.get(ALLOW_ENV, "").strip().lower() in ("1", "true", "yes"):
        return None
    bad = remote_targets({
        "API_BASE_URL": getattr(config, "api_base_url", None),
        "SECURITY_BASE_URL": getattr(config, "security_base_url", None),
    })
    if not bad:
        return None
    return (
        "Remote target refused: " + ", ".join(bad) + ". The API suite creates and changes data "
        "(cars, sale letters, a cashflow transaction), so the engine only targets a local backend. "
        f"Use a local stack, or set {ALLOW_ENV}=1 for a disposable test environment."
    )


class RemoteTargetBlockedRunner(BaseTestRunner):
    """Stands in for a guarded runner: reports all of its cases as BLOCKED without sending requests."""

    def __init__(self, wrapped: BaseTestRunner, reason: str):
        super().__init__(workspace_root=wrapped.workspace_root, runner_name=wrapped.runner_name)
        self.wrapped = wrapped
        self.reason = reason

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        return self.wrapped.discover_test_cases(context)

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        return False, self.reason

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        return self.wrapped.normalize_result(raw_result)

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        run_id = context.get("test_run_id", "run")
        now = datetime.now(timezone.utc).isoformat()
        cases = []
        for tc in self.discover_test_cases(context):
            tc.execution_status = TestStatus.BLOCKED
            tc.started_at = now
            tc.completed_at = now
            tc.duration_ms = 0.0
            tc.execution_id = run_id
            tc.error = self.reason
            tc.details = f"Blocked: {self.reason}"
            tc.blocking_dependency = "Remote target guard"
            tc.missing_configuration = f"{ALLOW_ENV}=1 (only for a disposable test environment)"
            tc.required_remediation = f"Point API_BASE_URL at a local backend, or set {ALLOW_ENV}=1 for a disposable test environment."
            cases.append(tc)
        return TestExecutionResult(
            test_run_id=run_id,
            test_type=self.runner_name,
            status=TestStatus.BLOCKED,
            started_at=now,
            completed_at=now,
            duration_ms=0.0,
            metrics={},
            failures=[],
            evidence=[],
            environment=context.get("environment", "local"),
            blocked_reason=self.reason,
            test_cases=cases,
        )
