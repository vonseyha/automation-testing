"""
Comprehensive unit and integration test suite for Test Engine Reporting, Dashboards,
and Complete Test-Case Accounting.

Validates all 14 acceptance criteria:
1. TestCaseResult structured model & normalization
2. TestRunSummary metrics & mathematical invariants
3. Pillar Summary breakdown table formatting
4. Test-Case Details tables under each pillar
5. Top-level Pre-Production Validation markdown dashboard
6. Dedicated Failed Test Cases section
7. Dedicated Blocked Test Cases section
8. Discovery vs. Execution distinction (Available, Selected, Executed, Blocked, Skipped)
9. Real evidence tracking without fabrication
10. Historical runs formatting for CLI history
11. Pipeline integrity: Real Execution -> Test Case Results -> Test Run -> Scorecard -> Release Gate -> Dashboard
12. Improved CLI terminal output with per-pillar accounting blocks
13. Runner normalization: granular runner cases vs aggregate fallback note
14. Invariant enforcement: BLOCKED is never PASSED; SKIPPED is never EXECUTED
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure workplace is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.reporting import TestDashboard, TestRunSummary
from orchestration.test_engine.storage import TestStorageManager
from orchestration.core_types import TestPillar


class TestReportingAndDashboard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
        )
        self.storage = TestStorageManager(self.config)
        self.engine = TestEngine(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_test_case_result_model_and_normalization(self):
        """1. Structured test-case identity with required fields and status normalization."""
        tc = TestCaseResult(
            test_case_id="API-001",
            test_name="Health check probe",
            test_pillar="API & Integration",
            description="Verifies GET /api/health returns 200 OK",
            execution_status="PASSED",
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=12.5,
            error=None,
            evidence=[{"path": ".antigravity/evidence/run_1/ev.json", "uri": "file:///path/ev.json"}],
            execution_id="run_101",
        )
        self.assertEqual(tc.execution_status, TestStatus.PASSED)
        self.assertEqual(tc.duration_ms, 12.5)
        d = tc.to_dict()
        self.assertEqual(d["execution_status"], "PASSED")
        self.assertEqual(d["test_case_id"], "API-001")

        # Verify from_dict roundtrip
        tc2 = TestCaseResult.from_dict(d)
        self.assertEqual(tc2.test_case_id, "API-001")
        self.assertEqual(tc2.execution_status, TestStatus.PASSED)

    def test_02_summary_metrics_and_invariants(self):
        """2. Summary metrics and strict mathematical invariants."""
        # Construct a synthetic runner result with mixed statuses
        cases = [
            TestCaseResult("TC-1", "T1", "API", "d1", TestStatus.PASSED, "", "", 10.0),
            TestCaseResult("TC-2", "T2", "API", "d2", TestStatus.PASSED, "", "", 15.0),
            TestCaseResult("TC-3", "T3", "API", "d3", TestStatus.FAILED, "", "", 20.0, error="Status 500"),
            TestCaseResult("TC-4", "T4", "API", "d4", TestStatus.BLOCKED, "", "", 0.0, blocking_dependency="dep"),
            TestCaseResult("TC-5", "T5", "API", "d5", TestStatus.SKIPPED, "", "", 0.0),
        ]
        res = TestExecutionResult(
            test_run_id="run_mix",
            test_type="api_integration",
            status=TestStatus.FAILED,
            started_at="",
            completed_at="",
            duration_ms=45.0,
            test_cases=cases,
        )

        summary = TestDashboard.calculate_summary([res], available_test_cases=10)

        # Invariant 1: Executed = Passed + Failed
        self.assertEqual(summary.executed_test_cases, summary.passed_test_cases + summary.failed_test_cases)
        self.assertEqual(summary.executed_test_cases, 3)

        # Invariant 2: Selected = Executed + Blocked + Skipped + Pending
        self.assertEqual(
            summary.selected_test_cases,
            summary.executed_test_cases + summary.blocked_test_cases + summary.skipped_test_cases + summary.pending_test_cases,
        )
        self.assertEqual(summary.selected_test_cases, 5)

        # Invariant 3: Blocked and Skipped are not counted as Executed
        self.assertEqual(summary.blocked_test_cases, 1)
        self.assertEqual(summary.skipped_test_cases, 1)

        # Invariant 4: Rates
        # Pass Rate = Passed / Executed = 2 / 3 = 66.7%
        self.assertEqual(summary.pass_rate, 66.7)
        # Execution Rate = Executed / Selected = 3 / 5 = 60.0%
        self.assertEqual(summary.execution_rate, 60.0)
        # Failure Rate = Failed / Executed = 1 / 3 = 33.3%
        self.assertEqual(summary.failure_rate, 33.3)

    def test_03_markdown_dashboard_pillar_summary_table(self):
        """3. Pillar Summary breakdown table with columns: Pillar | Total | Executed | Passed | Failed | Blocked | Skipped | Duration."""
        cases = [
            TestCaseResult("SEC-01", "SQLi check", "Security & Access", "Test SQLi", TestStatus.PASSED, "", "", 5.0),
            TestCaseResult("SEC-02", "XSS check", "Security & Access", "Test XSS", TestStatus.PASSED, "", "", 5.0),
        ]
        res = TestExecutionResult(
            test_run_id="run_tbl",
            test_type="security_access",
            status=TestStatus.PASSED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=10.0,
            test_cases=cases,
        )

        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="run_tbl",
            environment="test",
            started_at="2026-09-20T10:00:00Z",
            duration_ms=10.0,
            runner_results=[res],
            gate_status="NOT READY",
            available_test_cases=29,
        )

        self.assertIn("### Pillar Summary", md)
        self.assertIn("| Pillar | Total | Executed | Passed | Failed | Blocked | Skipped | Duration |", md)
        self.assertIn("| **SECURITY_ACCESS** | 2 | 2 | 2 | 0 | 0 | 0 |", md)

    def test_04_markdown_dashboard_test_case_details_table(self):
        """4. Test-Case Details table under each pillar with ID, Test Case, Status, Duration, Details, Evidence."""
        cases = [
            TestCaseResult(
                test_case_id="CONN-001",
                test_name="API Port Socket Reachability",
                test_pillar="API & Integration",
                description="Checks socket connectivity",
                execution_status=TestStatus.PASSED,
                started_at="2026-09-20T10:00:00Z",
                completed_at="2026-09-20T10:00:01Z",
                duration_ms=4.2,
                evidence=[{"path": ".antigravity/evidence/ev.json", "uri": "file:///ev.json"}],
                details="Port 3000 open",
            )
        ]
        res = TestExecutionResult(
            test_run_id="run_details",
            test_type="api_connectivity",
            status=TestStatus.PASSED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=4.2,
            test_cases=cases,
        )

        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="run_details",
            environment="local",
            started_at="2026-09-20T10:00:00Z",
            duration_ms=4.2,
            runner_results=[res],
            gate_status="NOT READY",
        )

        self.assertIn("### Test-Case Details", md)
        self.assertIn("| ID | Test Case | Status | Duration | Details | Evidence |", md)
        self.assertIn("| `CONN-001` | API Port Socket Reachability | PASSED | 4.2ms | Port 3000 open | [View](file:///ev.json) |", md)

    def test_05_failed_test_cases_section(self):
        """6. Dedicated Failed Test Cases section with all required diagnostic fields."""
        fail_case = TestCaseResult(
            test_case_id="API-003",
            test_name="Unauthorized access rejection",
            test_pillar="API & Integration",
            description="Rejection check",
            execution_status=TestStatus.FAILED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=25.0,
            failure_reason="Expected HTTP 401, got 200",
            expected="HTTP 401 Unauthorized",
            actual="HTTP 200 OK",
            required_action="Enable auth middleware on /api/cashflow",
            evidence=[{"path": ".antigravity/evidence/ev_fail.json", "uri": "file:///ev_fail.json"}],
        )
        res = TestExecutionResult(
            test_run_id="run_fail",
            test_type="api_integration",
            status=TestStatus.FAILED,
            started_at="",
            completed_at="",
            duration_ms=25.0,
            test_cases=[fail_case],
        )

        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="run_fail",
            environment="staging",
            started_at="2026-09-20T10:00:00Z",
            duration_ms=25.0,
            runner_results=[res],
            gate_status="NOT READY",
        )

        self.assertIn("## Failed Test Cases", md)
        self.assertIn("API-003`: Unauthorized access rejection", md)
        self.assertIn("* **Pillar:** API & Integration", md)
        self.assertIn("* **Failure reason:** Expected HTTP 401, got 200", md)
        self.assertIn("* **Expected:** HTTP 401 Unauthorized", md)
        self.assertIn("* **Actual:** HTTP 200 OK", md)
        self.assertIn("* **Required action:** Enable auth middleware on /api/cashflow", md)

    def test_06_blocked_test_cases_section(self):
        """7. Dedicated Blocked Test Cases section with blocking dependency and exact remediation."""
        blocked_case = TestCaseResult(
            test_case_id="UI-001",
            test_name="Autonomous UI Flow Verification",
            test_pillar="UI & Channel",
            description="Executes UI test runner",
            execution_status=TestStatus.BLOCKED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:00Z",
            duration_ms=0.0,
            blocking_dependency="UI test runner / framework",
            exact_missing_configuration="UI test command not configured",
            required_remediation="Set UI_TEST_COMMAND in environment or configure Angular testing suite",
        )
        res = TestExecutionResult(
            test_run_id="run_blk",
            test_type="ui_channel",
            status=TestStatus.BLOCKED,
            started_at="",
            completed_at="",
            duration_ms=0.0,
            test_cases=[blocked_case],
        )

        md = TestDashboard.generate_markdown_dashboard(
            test_run_id="run_blk",
            environment="local",
            started_at="2026-09-20T10:00:00Z",
            duration_ms=0.0,
            runner_results=[res],
            gate_status="NOT READY",
        )

        self.assertIn("## Blocked Test Cases", md)
        self.assertIn("UI-001`: Autonomous UI Flow Verification", md)
        self.assertIn("* **Blocking dependency:** UI test runner / framework", md)
        self.assertIn("* **Exact missing configuration:** UI test command not configured", md)
        self.assertIn("* **Required remediation:** Set UI_TEST_COMMAND in environment or configure Angular testing suite", md)

    def test_07_discovery_vs_execution_accounting(self):
        """8. Clear distinction between Available, Selected, Executed, Blocked, and Skipped."""
        # When user runs only a subset of runners (e.g. only api_connectivity)
        conn_runner = self.engine.get_runner("api_connectivity")
        self.assertIsNotNone(conn_runner)
        res = conn_runner.execute()

        summary = TestDashboard.calculate_summary([res], available_test_cases=29)
        self.assertEqual(summary.available_test_cases, 29)
        self.assertEqual(summary.selected_test_cases, 1)
        self.assertEqual(summary.executed_test_cases, 1)

    def test_08_test_history_formatting(self):
        """10. History entry formatting matching the specified compact layout."""
        run_doc = {
            "test_run_id": "test_engine_20260920_100000_abc123",
            "overall_status": "NOT READY",
            "summary": {
                "total_test_cases": 47,
                "executed_test_cases": 43,
                "passed_test_cases": 40,
                "failed_test_cases": 1,
                "blocked_test_cases": 4,
            },
        }

        formatted = TestDashboard.format_history_run(run_doc, index=105)
        expected = (
            "Run #105\n"
            "47 total\n"
            "43 executed\n"
            "40 passed\n"
            "1 failed\n"
            "4 blocked\n"
            "NOT READY"
        )
        self.assertEqual(formatted, expected)

    def test_08b_history_formatting_legacy_test_run_summary_key(self):
        """10b. Legacy files using 'test_run_summary' key are still loaded correctly."""
        run_doc = {
            "test_run_id": "legacy_run_001",
            "overall_status": "READY FOR ROLLOUT",
            "test_run_summary": {
                "total_test_cases": 30,
                "executed_test_cases": 28,
                "passed_test_cases": 28,
                "failed_test_cases": 0,
                "blocked_test_cases": 2,
            },
        }

        formatted = TestDashboard.format_history_run(run_doc, index=1)
        self.assertIn("30 total", formatted)
        self.assertIn("28 executed", formatted)
        self.assertIn("28 passed", formatted)
        self.assertIn("0 failed", formatted)
        self.assertIn("2 blocked", formatted)
        self.assertIn("READY", formatted)

    def test_08c_history_formatting_missing_summary_reconstructs(self):
        """10c. Missing summary key triggers reconstruction from runner results."""
        run_doc = {
            "test_run_id": "no_summary_run",
            "overall_status": "NOT READY",
            "results": [
                {
                    "test_type": "api_connectivity",
                    "status": "PASSED",
                    "started_at": "2026-09-20T10:00:00Z",
                    "completed_at": "2026-09-20T10:00:01Z",
                    "duration_ms": 5.0,
                    "failures": [],
                    "evidence": [],
                    "test_cases": [
                        {
                            "test_case_id": "CONN-001",
                            "test_name": "Port probe",
                            "test_pillar": "API & Integration",
                            "description": "Socket check",
                            "execution_status": "PASSED",
                            "started_at": "",
                            "completed_at": "",
                            "duration_ms": 5.0,
                        }
                    ],
                }
            ],
        }

        formatted = TestDashboard.format_history_run(run_doc, index=42)
        self.assertIn("Run #42", formatted)
        self.assertIn("1 total", formatted)
        self.assertIn("1 executed", formatted)
        self.assertIn("1 passed", formatted)
        self.assertIn("0 failed", formatted)
        self.assertIn("0 blocked", formatted)
        self.assertIn("NOT READY", formatted)

    def test_08d_history_formatting_malformed_summary_fails_gracefully(self):
        """10d. Malformed summary (wrong types, missing fields) fails gracefully."""
        run_doc = {
            "test_run_id": "malformed_run",
            "overall_status": "NOT READY",
            "summary": "this is not a dict",
        }
        formatted = TestDashboard.format_history_run(run_doc, index=99)
        self.assertIn("Run #99", formatted)
        self.assertIn("0 total", formatted)
        self.assertIn("NOT READY", formatted)

    def test_08e_history_formatting_canonical_key_preferred_over_legacy(self):
        """10e. When both 'summary' and 'test_run_summary' exist, 'summary' is preferred."""
        run_doc = {
            "test_run_id": "both_keys_run",
            "overall_status": "NOT READY",
            "summary": {
                "total_test_cases": 10,
                "executed_test_cases": 8,
                "passed_test_cases": 7,
                "failed_test_cases": 1,
                "blocked_test_cases": 2,
            },
            "test_run_summary": {
                "total_test_cases": 999,
                "executed_test_cases": 999,
                "passed_test_cases": 999,
                "failed_test_cases": 999,
                "blocked_test_cases": 999,
            },
        }

        formatted = TestDashboard.format_history_run(run_doc, index=50)
        self.assertIn("10 total", formatted)
        self.assertIn("8 executed", formatted)
        self.assertIn("7 passed", formatted)

    def test_08f_history_consistency_with_storage(self):
        """10f. Verifies save_test_run and format_history_run use consistent keys."""
        cases = [
            TestCaseResult("TC-A", "Test A", "API", "desc", TestStatus.PASSED, "", "", 10.0),
            TestCaseResult("TC-B", "Test B", "API", "desc", TestStatus.FAILED, "", "", 5.0, error="Err"),
        ]
        res = TestExecutionResult(
            test_run_id="consistency_run",
            test_type="api_integration",
            status=TestStatus.FAILED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=15.0,
            test_cases=cases,
        )

        run_file = self.storage.save_test_run(
            test_run_id="consistency_run",
            runner_results=[res],
            overall_status="NOT READY",
            execution_mode="sequential",
        )

        import json
        with open(run_file, "r") as f:
            saved_doc = json.load(f)

        self.assertIn("summary", saved_doc)

        formatted = TestDashboard.format_history_run(saved_doc, index=1)
        self.assertIn("2 total", formatted)
        self.assertIn("2 executed", formatted)
        self.assertIn("1 passed", formatted)
        self.assertIn("1 failed", formatted)
        self.assertIn("NOT READY", formatted)

    def test_09_cli_summary_generation(self):
        """12. Terminal-friendly CLI output format."""
        tc = TestCaseResult("API-001", "Health check", "API_INTEGRATION", "desc", TestStatus.PASSED, "", "", 5.0)
        res = TestExecutionResult(
            test_run_id="run_cli",
            test_type="api_integration",
            status=TestStatus.PASSED,
            started_at="",
            completed_at="",
            duration_ms=5.0,
            test_cases=[tc],
        )

        cli_out = TestDashboard.generate_cli_summary(
            test_run_id="run_cli",
            runner_results=[res],
            gate_status="READY FOR ROLLOUT",
            available_test_cases=29,
        )

        self.assertIn("PRE-PRODUCTION VALIDATION: run_cli", cli_out)
        self.assertIn("API_INTEGRATION", cli_out)
        self.assertIn("Total:    1", cli_out)
        self.assertIn("FULL VALIDATION SUMMARY", cli_out)
        self.assertIn("Pass Rate:        100.0%", cli_out)
        self.assertIn("Release Gate:     READY FOR ROLLOUT", cli_out)

    def test_10_aggregate_runner_normalization(self):
        """13. Aggregate runners without itemized test cases are marked with the explicit note."""
        agg_res = TestExecutionResult(
            test_run_id="run_agg",
            test_type="performance",
            status=TestStatus.PASSED,
            started_at="2026-09-20T10:00:00Z",
            completed_at="2026-09-20T10:00:01Z",
            duration_ms=500.0,
            metrics={"throughput_rps": 120.0},
            evidence=[{"path": ".antigravity/evidence/perf.jtl"}],
            test_cases=[],  # Empty to test extraction normalization
        )

        extracted = TestDashboard.extract_test_cases_from_runner_result(agg_res)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].test_case_id, "PERFORMANCE-AGGREGATE")
        self.assertEqual(extracted[0].details, "Individual test-case detail unavailable from runner.")

    def test_11_end_to_end_test_engine_accounting(self):
        """11. Complete TestEngine run populates scorecard, summary, dashboard, and storage."""
        # Execute real test engine sequential run
        scorecard = self.engine.run_all(mode="sequential")

        # Invariant checks on ReleaseScorecard
        self.assertEqual(
            scorecard.total_tests,
            scorecard.passed_tests + scorecard.failed_tests + scorecard.blocked_tests + scorecard.skipped_tests + scorecard.pending_tests,
        )
        self.assertEqual(scorecard.executed_tests, scorecard.passed_tests + scorecard.failed_tests)
        self.assertIsNotNone(scorecard.test_run_summary)
        self.assertIsNotNone(scorecard.dashboard_markdown)

        # Check that dashboard file was saved in evidence directory
        self.assertIn("## Pre-Production Validation", scorecard.dashboard_markdown)
        self.assertIn("### Pillar Summary", scorecard.dashboard_markdown)
        self.assertIn("### Test-Case Details", scorecard.dashboard_markdown)

        # Storage persistence check
        last_run = self.storage.get_test_run(self.engine.last_real_run["test_run_id"])
        self.assertIsNotNone(last_run)
        self.assertIn("summary", last_run)
        self.assertIn("dashboard_markdown", last_run)


if __name__ == "__main__":
    unittest.main()
