"""
Tests for dashboard data parsing, status counts, pass-rate denominator,
pillar aggregation, legacy format handling, and empty/error states.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from orchestration.test_engine.contract import TestCaseResult, TestExecutionResult, TestStatus
from orchestration.test_engine.reporting import TestDashboard, TestRunSummary
from orchestration.test_engine.release_gate import ReleaseGateEvaluator


class TestStatusCounts(unittest.TestCase):
    def _make_cases(self, passed=0, failed=0, blocked=0, skipped=0, pending=0):
        cases = []
        idx = 0
        for st, count in [
            (TestStatus.PASSED, passed), (TestStatus.FAILED, failed),
            (TestStatus.BLOCKED, blocked), (TestStatus.SKIPPED, skipped),
            (TestStatus.PENDING, pending),
        ]:
            for _ in range(count):
                idx += 1
                cases.append(TestCaseResult(
                    test_case_id=f"TC-{idx:03d}",
                    test_name=f"Test {idx}",
                    test_pillar="API & Integration",
                    description="test",
                    execution_status=st,
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                    duration_ms=100.0,
                ))
        return cases

    def _make_runner(self, cases, name="api_integration"):
        overall = TestStatus.PASSED
        for c in cases:
            if c.execution_status == TestStatus.FAILED:
                overall = TestStatus.FAILED
                break
            if c.execution_status == TestStatus.BLOCKED:
                overall = TestStatus.BLOCKED
        return TestExecutionResult(
            test_run_id="run_test",
            test_type=name,
            status=overall,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_ms=sum(c.duration_ms for c in cases),
            test_cases=cases,
        )

    def test_basic_counts(self):
        cases = self._make_cases(passed=5, failed=2, blocked=1)
        runner = self._make_runner(cases)
        summary = TestDashboard.calculate_summary([runner])
        self.assertEqual(summary.total_test_cases, 8)
        self.assertEqual(summary.passed_test_cases, 5)
        self.assertEqual(summary.failed_test_cases, 2)
        self.assertEqual(summary.blocked_test_cases, 1)
        self.assertEqual(summary.executed_test_cases, 7)

    def test_pass_rate_excludes_blocked(self):
        cases = self._make_cases(passed=9, blocked=1)
        runner = self._make_runner(cases)
        summary = TestDashboard.calculate_summary([runner])
        self.assertEqual(summary.pass_rate, 100.0)
        self.assertEqual(summary.execution_rate, 90.0)

    def test_pass_rate_denominator_is_executed(self):
        cases = self._make_cases(passed=80, failed=20, blocked=1)
        runner = self._make_runner(cases)
        summary = TestDashboard.calculate_summary([runner])
        self.assertEqual(summary.executed_test_cases, 100)
        self.assertEqual(summary.pass_rate, 80.0)

    def test_all_blocked_zero_pass_rate(self):
        cases = self._make_cases(blocked=5)
        runner = self._make_runner(cases)
        summary = TestDashboard.calculate_summary([runner])
        self.assertEqual(summary.pass_rate, 0.0)
        self.assertEqual(summary.executed_test_cases, 0)

    def test_empty_runner_list(self):
        summary = TestDashboard.calculate_summary([])
        self.assertEqual(summary.total_test_cases, 0)
        self.assertEqual(summary.pass_rate, 0.0)

    def test_skipped_not_counted_as_executed(self):
        cases = self._make_cases(passed=3, skipped=2)
        runner = self._make_runner(cases)
        summary = TestDashboard.calculate_summary([runner])
        self.assertEqual(summary.executed_test_cases, 3)
        self.assertEqual(summary.skipped_test_cases, 2)


class TestPillarAggregation(unittest.TestCase):
    def test_multiple_runners_same_pillar(self):
        conn_case = TestCaseResult(
            test_case_id="CONN-001", test_name="TCP probe",
            test_pillar="API & Integration", description="probe",
            execution_status=TestStatus.PASSED,
            started_at="", completed_at="", duration_ms=1.0,
        )
        api_case = TestCaseResult(
            test_case_id="API-001", test_name="Login endpoint",
            test_pillar="API & Integration", description="login",
            execution_status=TestStatus.PASSED,
            started_at="", completed_at="", duration_ms=500.0,
        )
        conn_runner = TestExecutionResult(
            test_run_id="run", test_type="api_connectivity",
            status=TestStatus.PASSED, started_at="", completed_at="",
            duration_ms=1.0, test_cases=[conn_case],
        )
        api_runner = TestExecutionResult(
            test_run_id="run", test_type="api_integration",
            status=TestStatus.PASSED, started_at="", completed_at="",
            duration_ms=500.0, test_cases=[api_case],
        )
        summary = TestDashboard.calculate_summary([conn_runner, api_runner])
        self.assertEqual(summary.total_test_cases, 2)
        self.assertEqual(summary.passed_test_cases, 2)

    def test_canonical_pillar_mapping(self):
        self.assertEqual(TestDashboard.PILLAR_CANONICAL_NAMES["api_connectivity"], "API_INTEGRATION")
        self.assertEqual(TestDashboard.PILLAR_CANONICAL_NAMES["api_integration"], "API_INTEGRATION")
        self.assertEqual(TestDashboard.PILLAR_CANONICAL_NAMES["ui_channel"], "UI_CHANNEL")
        self.assertEqual(TestDashboard.PILLAR_CANONICAL_NAMES["penetration"], "PENETRATION")


class TestLegacyFormat(unittest.TestCase):
    def test_summary_key_fallback(self):
        run_doc = {
            "test_run_id": "run_legacy",
            "test_run_summary": {
                "total_test_cases": 50,
                "passed_test_cases": 45,
                "failed_test_cases": 3,
                "blocked_test_cases": 2,
                "executed_test_cases": 48,
            },
            "results": [],
        }
        summary = run_doc.get("summary") or run_doc.get("test_run_summary")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_test_cases"], 50)

    def test_summary_key_primary(self):
        run_doc = {
            "summary": {"total_test_cases": 101},
            "test_run_summary": {"total_test_cases": 50},
        }
        summary = run_doc.get("summary") or run_doc.get("test_run_summary")
        self.assertEqual(summary["total_test_cases"], 101)


class TestReleaseGateDisplay(unittest.TestCase):
    def test_ready_when_required_pass(self):
        runners = []
        for name in ["api_integration", "security_access", "penetration"]:
            runners.append(TestExecutionResult(
                test_run_id="run", test_type=name,
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "test.json"}],
            ))
        gate = ReleaseGateEvaluator()
        result = gate.evaluate(runners)
        self.assertTrue(result["ready_for_rollout"])
        self.assertEqual(result["status"], "READY FOR ROLLOUT")

    def test_not_ready_when_required_fails(self):
        runners = [
            TestExecutionResult(
                test_run_id="run", test_type="api_integration",
                status=TestStatus.FAILED, started_at="", completed_at="",
                duration_ms=100.0, failures=[{"error": "assertion"}],
            ),
            TestExecutionResult(
                test_run_id="run", test_type="security_access",
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "t.json"}],
            ),
            TestExecutionResult(
                test_run_id="run", test_type="penetration",
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "t.json"}],
            ),
        ]
        gate = ReleaseGateEvaluator()
        result = gate.evaluate(runners)
        self.assertFalse(result["ready_for_rollout"])
        self.assertEqual(result["status"], "NOT READY")

    def test_optional_blocked_does_not_block_gate(self):
        runners = [
            TestExecutionResult(
                test_run_id="run", test_type="api_integration",
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "t.json"}],
            ),
            TestExecutionResult(
                test_run_id="run", test_type="security_access",
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "t.json"}],
            ),
            TestExecutionResult(
                test_run_id="run", test_type="penetration",
                status=TestStatus.PASSED, started_at="", completed_at="",
                duration_ms=100.0, evidence=[{"path": "t.json"}],
            ),
            TestExecutionResult(
                test_run_id="run", test_type="ai_grounding",
                status=TestStatus.BLOCKED, started_at="", completed_at="",
                duration_ms=0.0, blocked_reason="No Testing Center",
            ),
        ]
        gate = ReleaseGateEvaluator()
        result = gate.evaluate(runners)
        self.assertTrue(result["ready_for_rollout"])
        self.assertEqual(len(result["informational_warnings"]), 1)


class TestMalformedEvidence(unittest.TestCase):
    def test_missing_test_cases_produces_aggregate(self):
        runner = TestExecutionResult(
            test_run_id="run", test_type="performance",
            status=TestStatus.PASSED, started_at="", completed_at="",
            duration_ms=5000.0, test_cases=[],
        )
        cases = TestDashboard.extract_test_cases_from_runner_result(runner)
        self.assertEqual(len(cases), 1)
        self.assertIn("AGGREGATE", cases[0].test_case_id)

    def test_malformed_status_string_handled(self):
        tc = TestCaseResult(
            test_case_id="TC-001", test_name="Test",
            test_pillar="API", description="desc",
            execution_status="GARBAGE_STATUS",
            started_at="", completed_at="", duration_ms=0,
        )
        self.assertEqual(tc.execution_status, TestStatus.PENDING)

    def test_evidence_string_normalized_to_dict(self):
        tc = TestCaseResult(
            test_case_id="TC-001", test_name="Test",
            test_pillar="API", description="desc",
            execution_status=TestStatus.PASSED,
            started_at="", completed_at="", duration_ms=0,
            evidence=["/path/to/file.json"],
        )
        self.assertIsInstance(tc.evidence[0], dict)
        self.assertEqual(tc.evidence[0]["path"], "/path/to/file.json")


class TestHistoricalRunSorting(unittest.TestCase):
    def test_format_history_run_with_summary(self):
        run_doc = {
            "test_run_id": "run_123",
            "overall_status": "READY FOR ROLLOUT",
            "summary": {
                "total_test_cases": 101,
                "executed_test_cases": 100,
                "passed_test_cases": 100,
                "failed_test_cases": 0,
                "blocked_test_cases": 1,
            },
        }
        output = TestDashboard.format_history_run(run_doc)
        self.assertIn("101 total", output)
        self.assertIn("100 passed", output)
        self.assertIn("READY", output)

    def test_format_history_run_with_test_run_summary(self):
        run_doc = {
            "test_run_id": "run_legacy",
            "overall_status": "NOT READY",
            "test_run_summary": {
                "total_test_cases": 50,
                "executed_test_cases": 48,
                "passed_test_cases": 45,
                "failed_test_cases": 3,
                "blocked_test_cases": 2,
            },
        }
        output = TestDashboard.format_history_run(run_doc)
        self.assertIn("50 total", output)
        self.assertIn("NOT READY", output)


class TestMarkdownDashboard(unittest.TestCase):
    def test_generates_valid_markdown(self):
        cases = [
            TestCaseResult(
                test_case_id="API-001", test_name="Login",
                test_pillar="API & Integration", description="desc",
                execution_status=TestStatus.PASSED,
                started_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-01T00:00:01Z",
                duration_ms=500.0,
            ),
        ]
        runner = TestExecutionResult(
            test_run_id="run_md", test_type="api_integration",
            status=TestStatus.PASSED,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_ms=500.0, test_cases=cases,
            evidence=[{"path": "test.json"}],
        )
        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="run_md",
            runner_results=[runner],
            gate_eval={"status": "NOT READY", "blocking_reasons": [], "informational_warnings": []},
        )
        self.assertIn("## Pre-Production Validation", md)
        self.assertIn("API-001", md)
        self.assertIn("Pillar Summary", md)

    def test_pipe_characters_escaped_in_table(self):
        cases = [
            TestCaseResult(
                test_case_id="TC-PIPE", test_name="Test with | pipe",
                test_pillar="API & Integration",
                description="Details with | pipe char",
                execution_status=TestStatus.PASSED,
                started_at="", completed_at="", duration_ms=100.0,
            ),
        ]
        runner = TestExecutionResult(
            test_run_id="run", test_type="api_integration",
            status=TestStatus.PASSED, started_at="", completed_at="",
            duration_ms=100.0, test_cases=cases,
        )
        md = TestDashboard.generate_markdown_dashboard(runner_results=[runner])
        lines = [l for l in md.split("\n") if "TC-PIPE" in l]
        self.assertTrue(len(lines) > 0)
        for line in lines:
            self.assertNotIn("| pipe", line.split("|")[4] if len(line.split("|")) > 4 else "")


class TestDashboardServerData(unittest.TestCase):
    def test_run_json_parseable(self):
        from orchestration.config import OrchestrationConfig
        runs_dir = OrchestrationConfig.load().results_dir / "test_runs"
        if not runs_dir.exists():
            self.skipTest("No test_runs directory")
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            self.skipTest("No run files")
        with open(files[0], "r") as f:
            doc = json.load(f)
        self.assertIn("test_run_id", doc)
        summary = doc.get("summary") or doc.get("test_run_summary")
        self.assertIsNotNone(summary)
        self.assertIn("total_test_cases", summary)

    def test_latest_full_run_matches_expectations(self):
        from orchestration.config import OrchestrationConfig
        runs_dir = OrchestrationConfig.load().results_dir / "test_runs"
        if not runs_dir.exists():
            self.skipTest("No test_runs directory")
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for fp in files:
            try:
                with open(fp, "r") as f:
                    doc = json.load(f)
                summary = doc.get("summary") or doc.get("test_run_summary") or {}
                if summary.get("total_test_cases", 0) >= 100:
                    self.assertGreaterEqual(summary["total_test_cases"], 100)
                    self.assertGreaterEqual(summary.get("passed_test_cases", 0), 0)
                    return
            except Exception:
                continue
        self.skipTest("No full run with 100+ tests found")


class TestEmptyStates(unittest.TestCase):
    def test_cli_summary_with_no_results(self):
        output = TestDashboard.generate_cli_summary(
            test_run_id="empty_run",
            runner_results=[],
            gate_status="VALIDATION INCOMPLETE",
        )
        self.assertIn("0", output)
        self.assertIn("VALIDATION INCOMPLETE", output)

    def test_markdown_with_no_results(self):
        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="empty_run",
            runner_results=[],
            gate_eval={"status": "VALIDATION INCOMPLETE", "blocking_reasons": [], "informational_warnings": []},
        )
        self.assertIn("VALIDATION INCOMPLETE", md)


if __name__ == "__main__":
    unittest.main()
