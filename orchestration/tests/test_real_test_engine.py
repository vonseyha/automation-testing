"""
Comprehensive Verification of Real Executable Test Engine.
Per Section 20:
At minimum verifies:
1. Normal task -> Flash.
2. Complex task -> Pro Reviewer.
3. Pro reviewer response returns correctly.
4. Reviewer unavailable -> correct fallback.
5. API test executes a real request.
6. Failed test becomes FAILED.
7. Unavailable tool becomes BLOCKED.
8. Dependent test becomes BLOCKED when prerequisite fails.
9. Parallel execution works.
10. Sequential execution works.
11. Release gate blocks failed tests.
12. Evidence is retained.
13. Test history can be retrieved.
"""

import http.server
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from orchestration.config import OrchestrationConfig
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.models.router import ModelRouter
from orchestration.test_engine.contract import TestExecutionResult, TestStatus
from orchestration.test_engine.dependency_engine import DependencyEngine
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.release_gate import ReleaseGateEvaluator, ReleaseStatus
from orchestration.test_engine.runners.api_runner import APIRunner
from orchestration.test_engine.runners.penetration_runner import PenetrationRunner
from orchestration.test_engine.runners.performance_runner import PerformanceRunner
from orchestration.test_engine.runners.ui_runner import UIRunner
from orchestration.test_engine.storage import TestStorageManager
from orchestration.tools.workspace_tools import WorkspaceTools


class MockHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "api-gateway"}')
        elif self.path == "/api/error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Internal Server Error"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress console noise during test runs


class TestRealTestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start local test HTTP server on an ephemeral port
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockHttpHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
            audit_jsonl_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.jsonl",
            audit_md_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.md",
        )
        self.storage = TestStorageManager(self.config)
        self.engine = TestEngine(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Normal task -> Flash
    def test_01_normal_task_routes_to_flash(self):
        decision = self.engine.failure_escalator.router.config.primary_model
        self.assertEqual(decision, "gemini-3.8-flash")
        # Evaluate simple task
        from orchestration.escalation.policy import EscalationPolicy
        policy = EscalationPolicy(self.config)
        eval_res = policy.evaluate("Fix typo in documentation", changed_files=["README.md"])
        self.assertFalse(eval_res.should_escalate)
        self.assertEqual(eval_res.task_complexity, "NORMAL")

    # 2. Complex task -> Pro Reviewer
    def test_02_complex_task_escalates_to_pro(self):
        from orchestration.escalation.policy import EscalationPolicy
        policy = EscalationPolicy(self.config)
        eval_res = policy.evaluate(
            "Design new subsystem architecture for event-driven async ledger reconciliation",
            changed_files=["a.ts", "b.ts", "c.ts", "d.ts"],
        )
        self.assertTrue(eval_res.should_escalate)
        self.assertEqual(eval_res.task_complexity, "COMPLEX")

    # 3. Pro reviewer response returns correctly
    def test_03_pro_reviewer_returns_structured_response(self):
        router = ModelRouter(self.config)
        mock_reviewer = MockSpecialistClient(is_available_flag=True)
        router.register_client("reviewer", mock_reviewer)

        from orchestration.core_types import ReviewRequest
        req = ReviewRequest(user_requirement="Verify auth boundary")
        res = router.route_review(req)
        self.assertEqual(res.reviewer_status.value, "COMPLETED")
        self.assertIn(res.decision.value, ["APPROVE", "APPROVE WITH CHANGES"])
        self.assertTrue(len(res.testing_requirements) > 0)

    # 4. Reviewer unavailable -> correct fallback
    def test_04_reviewer_unavailable_fallback(self):
        router = ModelRouter(self.config)
        unavailable_reviewer = MockSpecialistClient(
            is_available_flag=False,
            unavailability_reason="API key not configured in environment.",
        )
        router.register_client("reviewer", unavailable_reviewer)

        from orchestration.core_types import ReviewRequest
        req = ReviewRequest(user_requirement="Refactor system")
        res = router.route_review(req)
        self.assertEqual(res.reviewer_status.value, "UNAVAILABLE")
        self.assertEqual(res.decision.value, "UNAVAILABLE")
        self.assertIn("API key not configured", res.unavailability_reason)
        self.assertIn("Continue with Gemini 3.8 Flash High", res.fallback_strategy)

    # 5. API test executes a real request
    def test_05_api_test_executes_real_request(self):
        api_runner = APIRunner(self.temp_dir, self.storage)
        res = api_runner.execute(context={
            "base_url": self.base_url,
            "endpoint": "/api/health",
            "expected_status": 200,
        })
        self.assertEqual(res.status, TestStatus.PASSED)
        self.assertEqual(res.metrics["status_code"], 200)
        self.assertTrue(res.metrics["measured_latency_ms"] >= 0)
        self.assertTrue(len(res.evidence) > 0)
        # Verify evidence file exists on disk
        ev_file = self.temp_dir / res.evidence[0]["path"]
        self.assertTrue(ev_file.exists())
        content = json.loads(ev_file.read_text(encoding="utf-8"))
        self.assertEqual(content["response"]["status_code"], 200)

    # 6. Failed test becomes FAILED
    def test_06_failed_test_becomes_failed(self):
        api_runner = APIRunner(self.temp_dir, self.storage)
        # Request non-existent or error endpoint
        res = api_runner.execute(context={
            "base_url": self.base_url,
            "endpoint": "/api/error",
            "expected_status": 200,  # Expect 200, but server returns 500
        })
        self.assertEqual(res.status, TestStatus.FAILED)
        self.assertEqual(res.metrics["status_code"], 500)
        self.assertEqual(len(res.failures), 1)
        self.assertIn("500", res.failures[0]["error"])

    # 7. Unavailable tool becomes BLOCKED
    def test_07_unavailable_tool_becomes_blocked(self):
        with patch("orchestration.test_engine.runners.ui_runner.shutil.which", return_value=None):
            ui_runner = UIRunner(self.temp_dir, self.storage)
            res = ui_runner.execute()
            # In this clean test environment, UTAM/Playwright is not in PATH
            self.assertEqual(res.status, TestStatus.BLOCKED)
            self.assertIn("not configured", res.blocked_reason)

        with patch("shutil.which", return_value=None):
            perf_runner = PerformanceRunner(self.temp_dir, self.storage)
            res_perf = perf_runner.execute()
            # JMeter is not in PATH
            self.assertEqual(res_perf.status, TestStatus.BLOCKED)
            self.assertIn("JMeter is not configured", res_perf.blocked_reason)

    # 8. Dependent test becomes BLOCKED when prerequisite fails
    def test_08_dependent_test_becomes_blocked_when_prereq_fails(self):
        dep_engine = DependencyEngine({
            "integration_suite": ["connectivity_prereq"],
        })
        completed = {
            "connectivity_prereq": TestExecutionResult(
                test_run_id="run_1",
                test_type="connectivity_prereq",
                status=TestStatus.FAILED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                failures=[{"error": "Connection refused"}],
            )
        }
        can_run, reason = dep_engine.can_execute("integration_suite", completed)
        self.assertFalse(can_run)
        self.assertIn("Prerequisite 'connectivity_prereq' ended with status FAILED", reason)

    # 9. Parallel execution works
    def test_09_parallel_execution_works(self):
        # Register runners targeting our local mock HTTP server
        api_runner = APIRunner(self.temp_dir, self.storage)
        pen_runner = PenetrationRunner(self.temp_dir, storage_manager=self.storage)
        self.engine.register_runner("api_integration", api_runner)
        self.engine.register_runner("penetration", pen_runner)

        context = {
            "base_url": self.base_url,
            "endpoint": "/api/health",
            "expected_status": 200,
        }
        run_res = self.engine.run_real_suites(
            runner_names=["api_integration", "penetration"],
            mode="parallel",
            context=context,
        )
        self.assertEqual(run_res["mode"], "parallel")
        self.assertIn("api_integration", run_res["results"])
        self.assertIn("penetration", run_res["results"])
        self.assertEqual(run_res["results"]["api_integration"]["status"], "PASSED")
        self.assertEqual(run_res["results"]["penetration"]["status"], "PASSED")

    # 10. Sequential execution works
    def test_10_sequential_execution_works(self):
        api_runner = APIRunner(self.temp_dir, self.storage)
        pen_runner = PenetrationRunner(self.temp_dir, storage_manager=self.storage)
        self.engine.register_runner("api_integration", api_runner)
        self.engine.register_runner("penetration", pen_runner)

        context = {
            "base_url": self.base_url,
            "endpoint": "/api/health",
            "expected_status": 200,
        }
        run_res = self.engine.run_real_suites(
            runner_names=["api_connectivity", "api_integration", "penetration"],
            mode="sequential",
            context=context,
        )
        self.assertEqual(run_res["mode"], "sequential")
        self.assertEqual(run_res["results"]["api_connectivity"]["status"], "PASSED")
        self.assertEqual(run_res["results"]["api_integration"]["status"], "PASSED")
        self.assertEqual(run_res["results"]["penetration"]["status"], "PASSED")

    # 11. Release gate blocks failed tests
    def test_11_release_gate_blocks_failed_or_blocked(self):
        gate = ReleaseGateEvaluator(required_test_types=["api_integration", "security_access"])

        # Case A: One required test failed
        results_fail = [
            TestExecutionResult("r1", "api_integration", TestStatus.PASSED, "", "", 10.0),
            TestExecutionResult("r1", "security_access", TestStatus.FAILED, "", "", 10.0, failures=[{"error": "Failed"}]),
        ]
        eval_fail = gate.evaluate(results_fail)
        self.assertEqual(eval_fail["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(eval_fail["ready_for_rollout"])

        # Case B: One required test blocked
        results_blocked = [
            TestExecutionResult("r1", "api_integration", TestStatus.PASSED, "", "", 10.0),
            TestExecutionResult("r1", "security_access", TestStatus.BLOCKED, "", "", 0.0, blocked_reason="Not configured"),
        ]
        eval_blocked = gate.evaluate(results_blocked)
        self.assertEqual(eval_blocked["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(eval_blocked["ready_for_rollout"])

        # Case C: All required tests passed
        results_pass = [
            TestExecutionResult("r1", "api_integration", TestStatus.PASSED, "", "", 10.0, evidence=[{"path": "api.json"}]),
            TestExecutionResult("r1", "security_access", TestStatus.PASSED, "", "", 10.0, evidence=[{"path": "sec.json"}]),
        ]
        eval_pass = gate.evaluate(results_pass)
        self.assertEqual(eval_pass["status"], ReleaseStatus.READY_FOR_ROLLOUT.value)
        self.assertTrue(eval_pass["ready_for_rollout"])

    # 12. Evidence is retained
    def test_12_evidence_is_retained(self):
        ref = self.storage.save_evidence_file(
            test_run_id="test_run_ev_123",
            filename="execution_trace.txt",
            content="Real execution logs 12345",
            evidence_type="log",
            description="Test trace log",
        )
        self.assertIn("path", ref)
        ev_file = self.temp_dir / ref["path"]
        self.assertTrue(ev_file.exists())
        self.assertEqual(ev_file.read_text(encoding="utf-8"), "Real execution logs 12345")

    # 13. Test history can be retrieved
    def test_13_test_history_can_be_retrieved(self):
        # Save two runs
        self.storage.save_test_run(
            test_run_id="run_alpha",
            runner_results=[TestExecutionResult("run_alpha", "api", TestStatus.PASSED, "", "", 5.0)],
            overall_status="READY FOR ROLLOUT",
            execution_mode="sequential",
        )
        self.storage.save_test_run(
            test_run_id="run_beta",
            runner_results=[TestExecutionResult("run_beta", "api", TestStatus.FAILED, "", "", 8.0)],
            overall_status="NOT READY",
            execution_mode="parallel",
        )

        history = self.storage.list_recent_runs(limit=5)
        self.assertTrue(len(history) >= 2)
        run_ids = [h["test_run_id"] for h in history]
        self.assertIn("run_alpha", run_ids)
        self.assertIn("run_beta", run_ids)

        # Retrieve specific run
        alpha = self.storage.get_test_run("run_alpha")
        self.assertIsNotNone(alpha)
        self.assertEqual(alpha["overall_status"], "READY FOR ROLLOUT")

    # 14. Canonical backend workspace recorded in metrics and evidence
    def test_14_canonical_backend_workspace_integration(self):
        backend_dir = self.temp_dir / "topautokh-api"
        backend_dir.mkdir(parents=True, exist_ok=True)
        (backend_dir / "package.json").write_text('{"name": "server"}', encoding="utf-8")

        api_runner = APIRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            backend_workspace=backend_dir,
            base_url=self.base_url,
            health_endpoint="/health",
        )
        # Validation succeeds because backend_dir exists
        valid, err = api_runner.validate_configuration()
        self.assertTrue(valid)
        self.assertIsNone(err)

        res = api_runner.execute(context={"endpoint": "/health"})
        self.assertIn("backend_workspace", res.metrics)
        self.assertEqual(res.metrics["backend_workspace"], str(backend_dir))
        self.assertNotIn("topauto-api-cluster", str(res.metrics["backend_workspace"]))

        # Evidence file contains backend_workspace
        ev_file = self.temp_dir / res.evidence[0]["path"]
        ev_data = json.loads(ev_file.read_text(encoding="utf-8"))
        self.assertEqual(ev_data["backend_workspace"], str(backend_dir))
        self.assertTrue(ev_data["backend_exists"])

    # 15. Validation fails when backend workspace is missing
    def test_15_backend_validation_failure_when_missing(self):
        non_existent_backend = self.temp_dir / "non_existent_api"
        api_runner = APIRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            backend_workspace=non_existent_backend,
        )
        valid, err = api_runner.validate_configuration()
        self.assertFalse(valid)
        self.assertIn("Configured backend workspace does not exist", err)


if __name__ == "__main__":
    unittest.main()
