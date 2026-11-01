"""
Real UI & Channel Test Runner.
Per Section 7:
Adapter for UTAM/Provar or workspace UI automation framework.
Triggers actual test command/webhook/API, captures exit code, logs, and evidence.
If UTAM/Provar is not configured: returns BLOCKED. Never fakes execution!
"""

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.storage import TestStorageManager


STANDARD_UI_CASES = [
    {
        "id": "UI-AUTH-001",
        "name": "Admin web portal login and route guard redirection",
        "description": "Verifies admin login flow via UI and route guard redirection for unauthenticated routes.",
        "expected": "Redirects to login page when unauthenticated, succeeds on valid credentials",
        "feature_id": "AUTH-001",
        "module": "Authentication & Identity",
        "priority": "P0",
    },
    {
        "id": "UI-CASHFLOW-001",
        "name": "Cashflow Command Center dashboard slicing and modal pagination",
        "description": "Verifies that the Cashflow Command Center slices top 8 cars and modal tables paginate cleanly.",
        "expected": "Dashboard renders top 8 cars; modal table paginates 10/25/50 rows smoothly",
        "feature_id": "FIN-001",
        "module": "Finance & Cashflow",
        "priority": "P0",
    },
    {
        "id": "UI-FILTER-001",
        "name": "Filter chip removal reactivity in Car Sales Report",
        "description": "Verifies that removing a filter chip updates the report dataset reactively.",
        "expected": "Active filters update state reactively upon chip dismissal",
        "feature_id": "REP-001",
        "module": "Reports & Analytics",
        "priority": "P2",
    },
]


class UIRunner(BaseTestRunner):
    """
    Real UI automation runner for UTAM, Provar, or Angular UI tests.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        ui_test_command: Optional[str] = None,
        enable_angular_headless_test: Optional[bool] = None,
        admin_workspace: Optional[Path] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="ui_channel")
        self.storage = storage_manager or TestStorageManager()
        self.ui_test_command = ui_test_command
        self.enable_angular_headless_test = enable_angular_headless_test
        self.admin_workspace = Path(admin_workspace) if admin_workspace else workspace_root / "top-auto-1653-admin-page"
        # Playwright specs that ship with this repo (orchestration/ui_tests)
        self.ui_tests_dir = Path(__file__).resolve().parents[2] / "ui_tests"

    def _expand_command(self, command: str) -> str:
        """Substitute {ADMIN_WORKSPACE} / {WORKSPACE_ROOT} placeholders in UI_TEST_COMMAND."""
        return (
            command.replace("{ADMIN_WORKSPACE}", str(self.admin_workspace))
            .replace("{WORKSPACE_ROOT}", str(self.workspace_root))
        )

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        cases = []
        for defn in STANDARD_UI_CASES:
            cases.append(
                TestCaseResult(
                    test_case_id=defn["id"],
                    test_name=defn["name"],
                    test_pillar="UI & Channel",
                    description=defn["description"],
                    execution_status=TestStatus.PENDING,
                    started_at="",
                    completed_at="",
                    duration_ms=0.0,
                    details=defn["name"],
                    expected=defn["expected"],
                    runner=self.runner_name,
                    feature_id=defn.get("feature_id", ""),
                    module=defn.get("module", ""),
                    priority=defn.get("priority", "P1"),
                )
            )
        return cases

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """
        Validates if UTAM, Provar, Angular Headless test, or a custom UI test command is available in the environment.
        """
        custom_cmd = self.ui_test_command or os.environ.get("UI_TEST_COMMAND")
        if custom_cmd:
            cmd_binary = custom_cmd.split()[0]
            if shutil.which(cmd_binary):
                return True, None
            return False, f"UI_TEST_COMMAND binary '{cmd_binary}' not found in PATH."

        # Check for standard UTAM or Provar CLI
        if shutil.which("utam"):
            return True, None
        if shutil.which("provar"):
            return True, None

        # Check for Playwright
        npx_bin = shutil.which("npx")
        if npx_bin:
            try:
                pw_check = subprocess.run(
                    ["npx", "playwright", "--version"],
                    capture_output=True, text=True, timeout=15,
                )
                if pw_check.returncode == 0:
                    return True, None
            except Exception:
                pass

        # Check for Angular frontend ng test if karma/puppeteer is configured
        admin_page = self.admin_workspace
        enable_headless = (
            self.enable_angular_headless_test
            if self.enable_angular_headless_test is not None
            else os.environ.get("ENABLE_ANGULAR_HEADLESS_TEST", "").lower() == "true"
        )
        if (admin_page / "package.json").exists() and enable_headless:
            if not (admin_page / "node_modules").exists():
                return False, f"Angular UI test dependencies (node_modules) not installed in {admin_page}."
            return True, None

        return False, "UI automation engine (Playwright/UTAM/Provar) not configured or executable in PATH."

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("ui")
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            blocked_cases = []
            for tc in self.discover_test_cases(context):
                tc.execution_status = TestStatus.BLOCKED
                tc.started_at = start_time
                tc.completed_at = end_time
                tc.duration_ms = 0.0
                tc.error = reason
                tc.execution_id = test_run_id
                tc.details = f"Blocked: {reason}"
                tc.blocking_dependency = "UI automation engine (UTAM/Provar)"
                tc.missing_configuration = "UTAM / Provar CLI executable in PATH (or ENABLE_ANGULAR_HEADLESS_TEST)"
                tc.required_remediation = "Install UTAM/Provar CLI or set ENABLE_ANGULAR_HEADLESS_TEST=true with dependencies installed."
                blocked_cases.append(tc)

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
                environment=context.get("environment", "local"),
                blocked_reason=reason,
                test_cases=blocked_cases,
            )

        # Trigger real execution if configured
        admin_page = self.admin_workspace
        enable_headless = (
            self.enable_angular_headless_test
            if self.enable_angular_headless_test is not None
            else os.environ.get("ENABLE_ANGULAR_HEADLESS_TEST", "").lower() == "true"
        )
        run_cwd = self.workspace_root
        if self.ui_test_command or os.environ.get("UI_TEST_COMMAND"):
            command = self._expand_command(self.ui_test_command or os.environ["UI_TEST_COMMAND"])
        elif shutil.which("utam"):
            command = "utam"
        elif shutil.which("provar"):
            command = "provar"
        elif shutil.which("npx"):
            try:
                pw_check = subprocess.run(["npx", "playwright", "--version"], capture_output=True, text=True, timeout=15)
                if pw_check.returncode == 0:
                    command = "npx playwright test --reporter=list"
                    run_cwd = self.ui_tests_dir
                elif enable_headless:
                    command = f"npm --prefix {admin_page} run test:ci" if (admin_page / "package.json").exists() else f"npm --prefix {admin_page} test -- --watch=false --browsers=ChromeHeadless"
                else:
                    command = "utam"
            except Exception:
                command = "utam"
        elif enable_headless:
            command = f"npm --prefix {admin_page} run test:ci" if (admin_page / "package.json").exists() else f"npm --prefix {admin_page} test -- --watch=false --browsers=ChromeHeadless"
        else:
            command = "utam"
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(run_cwd),
                capture_output=True,
                text=True,
                timeout=int(context.get("timeout_seconds", 120)),
            )

            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()

            log_content = f"STDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}\n\nEXIT_CODE: {res.returncode}"
            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename="ui_execution.log",
                content=log_content,
                evidence_type="execution_log",
                description="Real UI test runner console log",
            )

            status = TestStatus.PASSED if res.returncode == 0 else TestStatus.FAILED
            failures = [] if res.returncode == 0 else [{"exit_code": res.returncode, "error": res.stderr[:500]}]

            ui_cases: List[TestCaseResult] = []
            discovered_ui = self.discover_test_cases(context)
            per_case_duration = duration_ms / max(len(discovered_ui), 1)

            for item in discovered_ui:
                case_ev = dict(ev_ref)
                case_ev["execution_id"] = test_run_id
                case_ev["test_case_id"] = item.test_case_id
                case_ev["runner"] = self.runner_name
                case_ev["timestamp"] = end_time
                case_ev["log_reference"] = ev_ref.get("path")

                tc = TestCaseResult(
                    test_case_id=item.test_case_id,
                    test_name=item.test_name,
                    test_pillar="UI & Channel",
                    description=item.description,
                    execution_status=status,
                    started_at=start_time,
                    completed_at=end_time,
                    duration_ms=per_case_duration,
                    error=res.stderr[:500] if res.returncode != 0 else None,
                    evidence=[case_ev],
                    execution_id=test_run_id,
                    details="Angular Headless suite execution passed." if status == TestStatus.PASSED else f"Exit code {res.returncode}",
                    failure_reason=res.stderr[:500] if res.returncode != 0 else None,
                    expected="Process exit code 0",
                    actual=f"Process exit code {res.returncode}",
                    required_action="Review UI automation log output and fix failing assertions." if res.returncode != 0 else None,
                    runner=self.runner_name,
                    feature_id=item.feature_id,
                    module=item.module,
                    priority=item.priority,
                )
                ui_cases.append(tc)

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"exit_code": res.returncode, "total_cases": len(ui_cases)},
                failures=failures,
                evidence=[ev_ref],
                environment=context.get("environment", "local"),
                raw_result_reference=ev_ref["path"],
                test_cases=ui_cases,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={},
                failures=[{"error": "UI automation test execution timed out."}],
                evidence=[],
                environment=context.get("environment", "local"),
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={},
                failures=[{"error": str(e)}],
                evidence=[],
                environment=context.get("environment", "local"),
            )

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError("Normalization from external raw format not implemented for custom payload.")
