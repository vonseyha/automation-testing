"""
API Connectivity and Environment Health Runner.
Per Section 14:
Checks environment health and basic API reachability before running dependent integration tests.
If this fails, downstream integration tests are BLOCKED.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
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


class APIConnectivityRunner(BaseTestRunner):
    """
    Validates host and port connectivity for target API environment.
    Acts as the prerequisite for integration and performance test suites.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        backend_workspace: Optional[Path] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="api_connectivity")
        self.storage = storage_manager or TestStorageManager()
        self.backend_workspace = backend_workspace or (workspace_root / "topautokh-api")
        self.base_url = base_url or os.environ.get("API_BASE_URL") or "http://localhost:3000"

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        context = context or {}
        target_url = context.get("base_url") or self.base_url
        parsed = urllib.parse.urlparse(target_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return [
            TestCaseResult(
                test_case_id="CONN-001",
                test_name="TCP Socket Reachability Probe",
                test_pillar="API & Integration",
                description=f"Validates direct TCP socket connection to target host and port ({host}:{port}).",
                execution_status=TestStatus.PENDING,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                details=f"Target: {host}:{port}",
                expected=f"TCP connection established to {host}:{port}",
                runner=self.runner_name,
                feature_id="SYS-004",
                module="System & Integrations",
                priority="P0",
            )
        ]

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        if not self.backend_workspace.exists():
            return False, f"Configured backend workspace does not exist: {self.backend_workspace}"
        return True, None

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("conn")
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        backend_ws = Path(context.get("backend_workspace") or self.backend_workspace)
        target_url = context.get("base_url") or self.base_url
        parsed = urllib.parse.urlparse(target_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        timeout = float(context.get("timeout_seconds", 3.0))

        # Real TCP socket connection attempt
        socket_open = False
        error_msg = None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            socket_open = True
            s.close()
        except Exception as e:
            error_msg = f"Failed to connect to {host}:{port} - {str(e)}"
        finally:
            s.close()

        duration_ms = (time.perf_counter() - t_start) * 1000
        end_time = datetime.now(timezone.utc).isoformat()

        status = TestStatus.PASSED if socket_open else TestStatus.FAILED
        failures = [] if socket_open else [{
            "error": error_msg,
            "host": host,
            "port": port,
            "backend_workspace": str(backend_ws),
            "backend_exists": backend_ws.exists(),
        }]

        probe_doc = {
            "backend_workspace": str(backend_ws),
            "backend_exists": backend_ws.exists(),
            "host": host,
            "port": port,
            "target_url": target_url,
            "socket_open": socket_open,
            "duration_ms": duration_ms,
            "error": error_msg or "",
        }

        ev_ref = self.storage.save_evidence_file(
            test_run_id=test_run_id,
            filename="connectivity_probe.json",
            content=json.dumps(probe_doc, indent=2),
            evidence_type="connectivity_probe",
            description=f"Real socket probe against {host}:{port} (backend: {backend_ws.name})",
        )

        case_evidence = dict(ev_ref)
        case_evidence["execution_id"] = test_run_id
        case_evidence["test_case_id"] = "CONN-001"
        case_evidence["runner"] = self.runner_name
        case_evidence["timestamp"] = end_time
        case_evidence["log_reference"] = ev_ref.get("path")

        tc = TestCaseResult(
            test_case_id="CONN-001",
            test_name="TCP Socket Reachability Probe",
            test_pillar="API & Integration",
            description=f"Validates direct TCP socket connection to target host and port ({host}:{port}).",
            execution_status=status,
            started_at=start_time,
            completed_at=end_time,
            duration_ms=duration_ms,
            error=error_msg,
            evidence=[case_evidence],
            execution_id=test_run_id,
            details=f"Connected to {host}:{port}" if socket_open else (error_msg or "Connection failed"),
            failure_reason=error_msg,
            expected=f"TCP connection established to {host}:{port}",
            actual="Connection established" if socket_open else (error_msg or "Connection refused"),
            required_action="Start the backend service on port 3000 (topautokh-api) or verify network reachability." if not socket_open else None,
            runner=self.runner_name,
            feature_id="SYS-004",
            module="System & Integrations",
            priority="P0",
        )

        return TestExecutionResult(
            test_run_id=test_run_id,
            test_type=self.runner_name,
            status=status,
            started_at=start_time,
            completed_at=end_time,
            duration_ms=duration_ms,
            metrics={
                "socket_open": socket_open,
                "host": host,
                "port": port,
                "backend_workspace": str(backend_ws),
                "backend_exists": backend_ws.exists(),
            },
            failures=failures,
            evidence=[ev_ref],
            environment=context.get("environment", "local"),
            raw_result_reference=ev_ref["path"],
            test_cases=[tc],
        )

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError()

