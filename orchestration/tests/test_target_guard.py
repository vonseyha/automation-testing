"""
Unit tests for the remote-target guard.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.contract import TestStatus
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.preflight import PreflightRunner, PreflightStatus
from orchestration.test_engine.target_guard import (
    ALLOW_ENV,
    GUARDED_RUNNERS,
    RemoteTargetBlockedRunner,
    is_local_host,
    remote_target_violation,
)


class TestIsLocalHost(unittest.TestCase):
    def test_local_hosts(self):
        for host in ("localhost", "LOCALHOST", "127.0.0.1", "127.1.2.3", "::1", "[::1]", "0.0.0.0", "api.localhost"):
            self.assertTrue(is_local_host(host), host)

    def test_remote_hosts(self):
        for host in ("", "api.example.com", "10.0.0.5", "192.168.1.20", "localhost.example.com", "staging"):
            self.assertFalse(is_local_host(host), host)


class TestRemoteTargetViolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ALLOW_ENV, None)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _config(self, api_url, security_url=None):
        return OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            api_base_url=api_url,
            security_base_url=security_url,
        )

    def test_local_target_allowed(self):
        self.assertIsNone(remote_target_violation(self._config("http://localhost:3000")))
        self.assertIsNone(remote_target_violation(self._config("http://127.0.0.1:3000", "http://[::1]:3000")))

    def test_remote_api_refused(self):
        reason = remote_target_violation(self._config("https://api.example.com"))
        self.assertIsNotNone(reason)
        self.assertIn("API_BASE_URL=https://api.example.com", reason)
        self.assertIn(ALLOW_ENV, reason)

    def test_remote_security_url_refused(self):
        reason = remote_target_violation(self._config("http://localhost:3000", "https://staging.example.com"))
        self.assertIn("SECURITY_BASE_URL=https://staging.example.com", reason)

    def test_opt_in_allows_remote(self):
        os.environ[ALLOW_ENV] = "1"
        self.assertIsNone(remote_target_violation(self._config("https://api.example.com")))

    def test_preflight_check(self):
        check = PreflightRunner(self._config("https://api.example.com"))._check_target_is_local()
        self.assertTrue(check.required)
        self.assertEqual(check.status, PreflightStatus.FAIL)
        os.environ[ALLOW_ENV] = "1"
        check = PreflightRunner(self._config("https://api.example.com"))._check_target_is_local()
        self.assertEqual(check.status, PreflightStatus.WARN)
        check = PreflightRunner(self._config("http://localhost:3000"))._check_target_is_local()
        self.assertEqual(check.status, PreflightStatus.PASS)


class TestEngineGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ALLOW_ENV, None)
        # Port 9 (discard) on a remote-looking host: nothing may be contacted.
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / "audit",
            api_base_url="http://remote-target.invalid:9",
        )
        self.engine = TestEngine(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_guarded_suites_blocked_without_requests(self):
        executed = []
        for name in GUARDED_RUNNERS:
            runner = self.engine.get_runner(name)
            original_execute = runner.execute

            def spy(context=None, _name=name, _orig=original_execute):
                executed.append(_name)
                return _orig(context)

            runner.execute = spy

        run = self.engine.run_real_suites(runner_names=list(GUARDED_RUNNERS))
        self.assertEqual(executed, [], "guarded runners must not execute against a remote target")

        for name in GUARDED_RUNNERS:
            self.assertEqual(TestStatus(run["results"][name]["status"]), TestStatus.BLOCKED, name)
        self.assertEqual(run["release_gate"]["status"], "NOT READY")
        self.assertTrue(any("Remote target refused" in b for b in run["release_gate"]["blocking_reasons"]))

        # Runners are restored after the run
        for name in GUARDED_RUNNERS:
            self.assertNotIsInstance(self.engine.get_runner(name), RemoteTargetBlockedRunner)

    def test_blocked_cases_carry_remediation(self):
        wrapped = RemoteTargetBlockedRunner(self.engine.get_runner("security_access"), "Remote target refused: X")
        res = wrapped.execute({"test_run_id": "t1"})
        self.assertEqual(res.status, TestStatus.BLOCKED)
        self.assertTrue(res.test_cases)
        for tc in res.test_cases:
            self.assertEqual(tc.blocking_dependency, "Remote target guard")
            self.assertIn(ALLOW_ENV, tc.required_remediation)


if __name__ == "__main__":
    unittest.main()
