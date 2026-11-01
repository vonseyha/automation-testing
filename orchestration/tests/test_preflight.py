"""
Tests for local environment preflight checker.
"""

import unittest
from pathlib import Path

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.preflight import (
    PreflightCheck,
    PreflightRunner,
    PreflightStatus,
    format_preflight_report,
)


class TestPreflightRunner(unittest.TestCase):
    def test_run_all_returns_expected_check_count(self):
        config = OrchestrationConfig.load()
        runner = PreflightRunner(config)
        checks = runner.run_all()
        self.assertEqual(len(checks), 13)
        names = [c.name for c in checks]
        self.assertIn("Python runtime", names)
        self.assertIn("Node.js runtime", names)
        self.assertIn("Backend dependencies", names)
        self.assertIn("Backend environment variables", names)
        self.assertIn("MongoDB connectivity", names)
        self.assertIn("Backend health endpoint", names)
        self.assertIn("UI automation engine", names)
        self.assertIn("JMeter performance engine", names)
        self.assertIn("AI model availability", names)
        self.assertIn("Evidence/test-run write access", names)
        self.assertIn("Test account and fixture readiness", names)

    def test_python_check_passes(self):
        runner = PreflightRunner()
        check = runner._check_python()
        self.assertEqual(check.status, PreflightStatus.PASS)
        self.assertIn("Python", check.detail)

    def test_python_packages_pass(self):
        runner = PreflightRunner()
        check = runner._check_python_packages()
        self.assertEqual(check.status, PreflightStatus.PASS)

    def test_required_vs_optional_classification(self):
        runner = PreflightRunner()
        checks = runner.run_all()
        required = [c for c in checks if c.required]
        optional = [c for c in checks if not c.required]
        self.assertGreaterEqual(len(required), 5)
        self.assertGreaterEqual(len(optional), 3)
        required_names = {c.name for c in required}
        self.assertIn("Python runtime", required_names)
        self.assertIn("Node.js runtime", required_names)
        self.assertIn("Backend dependencies", required_names)
        self.assertIn("Evidence/test-run write access", required_names)
        optional_names = {c.name for c in optional}
        self.assertIn("UI automation engine", optional_names)
        self.assertIn("JMeter performance engine", optional_names)
        self.assertIn("AI model availability", optional_names)

    def test_ai_check_always_passes(self):
        runner = PreflightRunner()
        check = runner._check_ai_config()
        self.assertEqual(check.status, PreflightStatus.PASS)

    def test_write_access_check(self):
        runner = PreflightRunner()
        check = runner._check_write_access()
        self.assertEqual(check.status, PreflightStatus.PASS)

    def test_format_report_text(self):
        checks = [
            PreflightCheck("Test A", "Cat1", True, PreflightStatus.PASS, "ok"),
            PreflightCheck("Test B", "Cat1", False, PreflightStatus.WARN, "missing", "install it"),
        ]
        report = format_preflight_report(checks)
        self.assertIn("PREFLIGHT CHECK", report)
        self.assertIn("REQUIRED", report)
        self.assertIn("OPTIONAL", report)
        self.assertIn("Test A", report)
        self.assertIn("Test B", report)

    def test_format_report_json(self):
        import json
        checks = [
            PreflightCheck("Test A", "Cat1", True, PreflightStatus.PASS, "ok"),
        ]
        report = format_preflight_report(checks, as_json=True)
        data = json.loads(report)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Test A")
        self.assertTrue(data[0]["required"])

    def test_to_dict(self):
        c = PreflightCheck("X", "Y", True, PreflightStatus.FAIL, "bad", "fix it")
        d = c.to_dict()
        self.assertEqual(d["name"], "X")
        self.assertEqual(d["status"], "FAIL")
        self.assertEqual(d["remediation"], "fix it")


if __name__ == "__main__":
    unittest.main()
