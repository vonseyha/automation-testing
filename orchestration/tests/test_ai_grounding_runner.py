"""
Unit tests for AIGroundingRunner (Agentforce Testing Center Adapter).
Verifies:
1. Configuration validation (blocked when unconfigured, valid when configured).
2. Blocked status when credentials/endpoints are missing.
3. Successful batch execution against mock server (HTTP POST /batches/{batch_id}/execute).
4. Failure batch execution handling.
5. Network error handling.
6. Sanitization of evidence data and prevention of token leakage.
"""

import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from orchestration.test_engine.contract import TestStatus
from orchestration.test_engine.runners.ai_grounding_runner import AIGroundingRunner
from orchestration.test_engine.storage import TestStorageManager


class MockAgentforceServer(http.server.BaseHTTPRequestHandler):
    received_auth_header = None
    received_path = None
    response_payload = {
        "batch_id": "batch-topauto-reg-001",
        "all_passed": True,
        "total_tests": 12,
        "passed_tests": 12,
        "failures": [],
    }

    def do_POST(self):
        MockAgentforceServer.received_path = self.path
        MockAgentforceServer.received_auth_header = self.headers.get("Authorization")

        if self.path == "/batches/batch-topauto-reg-001/execute":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(MockAgentforceServer.response_payload).encode("utf-8"))
        elif self.path == "/batches/batch-fail/execute":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            fail_payload = {
                "batch_id": "batch-fail",
                "all_passed": False,
                "total_tests": 12,
                "passed_tests": 10,
                "failures": [{"test": "grounding_test_3", "error": "Hallucination detected"}],
            }
            self.wfile.write(json.dumps(fail_payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')

    def log_message(self, format, *args):
        pass


class TestAIGroundingRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockAgentforceServer)
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
        from orchestration.config import OrchestrationConfig
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
            audit_jsonl_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.jsonl",
            audit_md_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.md",
        )
        self.storage = TestStorageManager(self.config)
        # Clear env vars for clean baseline
        for k in ["TESTING_CENTER_API_URL", "AGENTFORCE_TESTING_CENTER_URL", "AGENTFORCE_REGRESSION_BATCH_ID", "AGENTFORCE_API_TOKEN"]:
            if k in os.environ:
                del os.environ[k]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_unconfigured_returns_blocked(self):
        runner = AIGroundingRunner(workspace_root=self.temp_dir, storage_manager=self.storage)
        is_configured, reason = runner.validate_configuration()
        self.assertFalse(is_configured)
        self.assertIn("missing TESTING_CENTER_API_URL or AGENTFORCE_REGRESSION_BATCH_ID", reason)

        res = runner.execute()
        self.assertEqual(res.status, TestStatus.BLOCKED)
        self.assertIn("missing TESTING_CENTER_API_URL", res.blocked_reason)

    def test_02_validation_succeeds_with_constructor_args(self):
        runner = AIGroundingRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            testing_center_api_url=self.base_url,
            agentforce_regression_batch_id="batch-topauto-reg-001",
            agentforce_api_token="test-secret-token",
        )
        is_configured, reason = runner.validate_configuration()
        self.assertTrue(is_configured)
        self.assertIsNone(reason)

    def test_03_validation_succeeds_with_env_vars(self):
        os.environ["TESTING_CENTER_API_URL"] = self.base_url
        os.environ["AGENTFORCE_REGRESSION_BATCH_ID"] = "batch-topauto-reg-001"
        os.environ["AGENTFORCE_API_TOKEN"] = "test-secret-token"

        runner = AIGroundingRunner(workspace_root=self.temp_dir, storage_manager=self.storage)
        is_configured, reason = runner.validate_configuration()
        self.assertTrue(is_configured)
        self.assertIsNone(reason)

    def test_04_execute_successful_batch(self):
        runner = AIGroundingRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            testing_center_api_url=self.base_url,
            agentforce_regression_batch_id="batch-topauto-reg-001",
            agentforce_api_token="test-secret-token-12345",
        )
        res = runner.execute()
        self.assertEqual(res.status, TestStatus.PASSED)
        self.assertEqual(res.metrics["total_tests"], 12)
        self.assertEqual(res.metrics["passed_tests"], 12)
        self.assertEqual(res.metrics["failed_tests"], 0)
        self.assertEqual(len(res.evidence), 1)

        # Verify Authorization header and URL path were received by server
        self.assertEqual(MockAgentforceServer.received_path, "/batches/batch-topauto-reg-001/execute")
        self.assertEqual(MockAgentforceServer.received_auth_header, "Bearer test-secret-token-12345")

        # Verify evidence does not leak the secret token
        ev_file = self.temp_dir / res.evidence[0]["path"]
        self.assertTrue(ev_file.exists())
        ev_text = ev_file.read_text(encoding="utf-8")
        self.assertNotIn("test-secret-token-12345", ev_text)

    def test_05_execute_failed_batch(self):
        runner = AIGroundingRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            testing_center_api_url=self.base_url,
            agentforce_regression_batch_id="batch-fail",
            agentforce_api_token="token",
        )
        res = runner.execute()
        self.assertEqual(res.status, TestStatus.FAILED)
        self.assertEqual(res.metrics["passed_tests"], 10)
        self.assertEqual(res.metrics["failed_tests"], 1)
        self.assertEqual(len(res.failures), 1)

    def test_06_execute_handles_http_error(self):
        runner = AIGroundingRunner(
            workspace_root=self.temp_dir,
            storage_manager=self.storage,
            testing_center_api_url=self.base_url,
            agentforce_regression_batch_id="non-existent-batch",
            agentforce_api_token="token",
        )
        res = runner.execute()
        self.assertEqual(res.status, TestStatus.FAILED)
        self.assertTrue(any("Testing Center API error" in f.get("error", "") for f in res.failures))


if __name__ == "__main__":
    unittest.main()
