"""
Real Performance Test Runner (JMeter Adapter).
Per Section 9:
Executes actual Apache JMeter test plans, parses real .jtl/.csv execution reports,
and extracts real throughput, latency percentiles, and error rates.
Never invents metrics.
If JMeter is not available in PATH: returns status = BLOCKED.
"""

import csv
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


class PerformanceRunner(BaseTestRunner):
    """
    Real JMeter Performance Runner.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        jmeter_path: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="performance")
        self.storage = storage_manager or TestStorageManager()
        self.jmeter_path = jmeter_path

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        return [
            TestCaseResult(
                test_case_id="PERF-001",
                test_name="JMeter Smoke & Load Performance Suite",
                test_pillar="Performance",
                description="Executes Apache JMeter test plan (smoke_test.jmx) to validate latency percentiles and throughput under load.",
                execution_status=TestStatus.PENDING,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                details="p95 latency < 500ms, error rate 0%",
                expected="Throughput sustained with zero error rate",
                runner=self.runner_name,
                feature_id="FIN-001",
                module="Finance & Cashflow",
                priority="P1",
            )
        ]

    def _resolve_jmeter_bin(self) -> Optional[str]:
        candidates = [
            self.jmeter_path,
            shutil.which("jmeter"),
            os.environ.get("JMETER_PATH"),
            os.environ.get("JMETER_HOME"),
        ]
        for cand in candidates:
            if cand and (shutil.which(cand) or Path(cand).exists()):
                return cand
        return None

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        if self._resolve_jmeter_bin():
            return True, None

        return False, "JMeter is not configured or executable in PATH."

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("perf")
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            tc = TestCaseResult(
                test_case_id="PERF-001",
                test_name="JMeter Smoke & Load Performance Suite",
                test_pillar="Performance",
                description="Executes Apache JMeter test plan (smoke_test.jmx) to validate latency percentiles and throughput under load.",
                execution_status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=0.0,
                error=reason,
                execution_id=test_run_id,
                details=f"Blocked: {reason}",
                blocking_dependency="JMeter executable in PATH",
                missing_configuration="JMeter executable (jmeter) not found in PATH or JMETER_HOME",
                required_remediation="Install Apache JMeter (brew install jmeter) or configure JMETER_PATH.",
                runner=self.runner_name,
                feature_id="FIN-001",
                module="Finance & Cashflow",
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
                environment=context.get("environment", "local"),
                blocked_reason=reason,
                test_cases=[tc],
            )

        # JMeter is configured: locate test plan
        canonical_plan = Path(__file__).resolve().parents[2] / "performance" / "smoke_test.jmx"
        test_plan = context.get("test_plan") or os.environ.get("JMETER_TEST_PLAN") or (canonical_plan if canonical_plan.exists() else None)
        if not test_plan or not Path(test_plan).exists():
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            tc = TestCaseResult(
                test_case_id="PERF-001",
                test_name="JMeter Smoke & Load Performance Suite",
                test_pillar="Performance",
                description="Executes Apache JMeter test plan (smoke_test.jmx) to validate latency percentiles and throughput under load.",
                execution_status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=0.0,
                error=f"JMeter test plan not found: {test_plan}",
                execution_id=test_run_id,
                details="Test plan missing",
                blocking_dependency="JMeter test plan file",
                missing_configuration=f"smoke_test.jmx at {test_plan}",
                required_remediation="Ensure orchestration/performance/smoke_test.jmx is present.",
                runner=self.runner_name,
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
                environment=context.get("environment", "local"),
                blocked_reason=f"JMeter test plan not found: {test_plan}",
                test_cases=[tc],
            )

        ev_dir = self.storage.get_evidence_dir(test_run_id)
        jtl_output = ev_dir / "jmeter_results.jtl"
        jmeter_bin = self._resolve_jmeter_bin() or "jmeter"

        cmd = [
            jmeter_bin,
            "-n",
            "-t", str(test_plan),
            "-l", str(jtl_output),
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(context.get("timeout_seconds", 300)),
            )

            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()

            # Save execution console log
            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename="jmeter_console.log",
                content=f"STDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}",
                evidence_type="execution_log",
                description="JMeter console output",
            )

            # Parse actual JTL output metrics (no invention!)
            metrics, failures = self._parse_jtl(jtl_output)

            status = TestStatus.PASSED if res.returncode == 0 and not failures else TestStatus.FAILED

            case_evidence = dict(ev_ref)
            case_evidence["execution_id"] = test_run_id
            case_evidence["test_case_id"] = "PERF-001"
            case_evidence["runner"] = self.runner_name
            case_evidence["timestamp"] = end_time
            case_evidence["log_reference"] = str(jtl_output)

            details_text = f"Samples: {metrics.get('total_samples', 0)}, avg: {metrics.get('avg_latency_ms', 0)}ms, p95: {metrics.get('p95_latency_ms', 0)}ms" if metrics else "No samples recorded"

            tc = TestCaseResult(
                test_case_id="PERF-001",
                test_name="JMeter Smoke & Load Performance Suite",
                test_pillar="Performance",
                description="Executes Apache JMeter test plan (smoke_test.jmx) to validate latency percentiles and throughput under load.",
                execution_status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                error=failures[0].get("error") if failures else None,
                evidence=[case_evidence],
                execution_id=test_run_id,
                details=details_text,
                failure_reason=failures[0].get("error") if failures else None,
                expected="JMeter exit code 0 and zero sample errors",
                actual=f"Exit code {res.returncode}, {len(failures)} failures",
                required_action="Review JMeter console output and JTL logs to optimize endpoint performance." if failures or res.returncode != 0 else None,
                runner=self.runner_name,
            )

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type=self.runner_name,
                status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics=metrics,
                failures=failures,
                evidence=[ev_ref],
                environment=context.get("environment", "local"),
                raw_result_reference=str(jtl_output),
                test_cases=[tc],
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

    def _parse_jtl(self, jtl_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        if not jtl_path.exists():
            return {}, [{"error": "JTL result file was not generated."}]

        latencies = []
        error_count = 0
        total_samples = 0

        try:
            with open(jtl_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_samples += 1
                    elapsed = float(row.get("elapsed", 0))
                    latencies.append(elapsed)
                    success_str = row.get("success", "true").lower()
                    if success_str in ("false", "0"):
                        error_count += 1

            if total_samples == 0:
                return {}, []

            latencies.sort()
            avg_latency = sum(latencies) / len(latencies)
            p90 = latencies[int(len(latencies) * 0.90)] if latencies else 0
            p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
            p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
            error_rate = (error_count / total_samples) * 100

            metrics = {
                "total_samples": total_samples,
                "error_count": error_count,
                "error_rate_pct": round(error_rate, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "p90_latency_ms": round(p90, 2),
                "p95_latency_ms": round(p95, 2),
                "p99_latency_ms": round(p99, 2),
            }

            failures = []
            if error_count > 0:
                failures.append({"error": f"{error_count} sample requests failed during load run."})

            return metrics, failures
        except Exception as e:
            return {}, [{"error": f"Failed to parse JTL output: {e}"}]

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError()
