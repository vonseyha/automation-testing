"""
Unit and integration tests for Release Scorecard Integrity and Legacy Pillar Deprecation.
Verifies:
1. Production Release Scorecard is derived strictly from real test runners.
2. Blocked or failed real runners prevent release readiness (release_ready=False).
3. Legacy static analysis cannot inflate the scorecard or grant release readiness.
4. Scorecard invariants are preserved (total_tests == passed_tests + failed_tests).
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.contract import BaseTestRunner, TestExecutionResult, TestStatus
from orchestration.test_engine.engine import TestEngine
from orchestration.core_types import TestPillar


class ConfigurableRunner(BaseTestRunner):
    def __init__(
        self,
        workspace_root: Path,
        runner_name: str,
        status: TestStatus,
        blocked_reason: str = None,
        evidence: list = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name=runner_name)
        self.target_status = status
        self.target_blocked_reason = blocked_reason
        if evidence is not None:
            self.evidence = evidence
        elif status == TestStatus.PASSED:
            self.evidence = [{"path": f"evidence_{runner_name}.json", "evidence_type": "log"}]
        else:
            self.evidence = []

    def validate_configuration(self):
        return True, None

    def execute(self, context=None):
        return TestExecutionResult(
            test_run_id=context.get("test_run_id", "run_test") if context else "run_test",
            test_type=self.runner_name,
            status=self.target_status,
            started_at="",
            completed_at="",
            duration_ms=1.5,
            evidence=self.evidence,
            blocked_reason=self.target_blocked_reason,
            failures=[{"error": "Failed"}] if self.target_status == TestStatus.FAILED else [],
        )

    def normalize_result(self, raw_result):
        return raw_result


class TestScorecardIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
        )
        self.engine = TestEngine(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_real_runners_block_release_when_prereq_or_tool_fails(self):
        """
        When real test runners have blocked or failed results,
        run_all() accurately reflects NOT READY and release_ready=False.
        """
        # In this clean temp directory, external tools (UTAM, live server) are not running
        scorecard = self.engine.run_all()

        self.assertFalse(scorecard.release_ready)
        self.assertFalse(scorecard.overall_passed)
        self.assertTrue(scorecard.failed_tests > 0 or scorecard.blocked_tests > 0)
        self.assertIn("NOT READY", scorecard.summary)
        self.assertEqual(len(scorecard.pillar_summaries), 6)
        self.assertEqual(
            scorecard.total_tests,
            scorecard.passed_tests + scorecard.failed_tests + scorecard.blocked_tests + scorecard.skipped_tests + scorecard.pending_tests,
        )

    def test_02_all_passed_real_runners_grant_release_readiness(self):
        """
        When all required real runners pass, the release gate grants ready_for_rollout.
        """
        for r_name in [
            "api_connectivity",
            "ui_channel",
            "api_integration",
            "performance",
            "security_access",
            "penetration",
            "ai_grounding",
        ]:
            self.engine.register_runner(r_name, ConfigurableRunner(self.temp_dir, r_name, TestStatus.PASSED))

        scorecard = self.engine.run_all()

        self.assertTrue(scorecard.release_ready)
        self.assertTrue(scorecard.overall_passed)
        self.assertEqual(scorecard.failed_tests, 0)
        self.assertIn("READY FOR ROLLOUT", scorecard.summary)

    def test_03_legacy_static_analysis_never_grants_release_readiness(self):
        """
        Legacy static text search checks cannot grant release readiness or inflate the production gate.
        """
        static_card = self.engine.run_static_analysis()

        # Static checks must NEVER claim release ready
        self.assertFalse(static_card.release_ready)
        self.assertFalse(static_card.overall_passed)
        self.assertIn("NOT VALIDATED FOR PRODUCTION RELEASE", static_card.summary)

    def test_04_single_blocked_required_runner_prevents_release(self):
        """
        Even if 5 pillars pass, a single blocked required runner (e.g. security_access)
        blocks release.
        """
        for r_name in [
            "api_connectivity",
            "ui_channel",
            "api_integration",
            "performance",
            "penetration",
            "ai_grounding",
        ]:
            self.engine.register_runner(r_name, ConfigurableRunner(self.temp_dir, r_name, TestStatus.PASSED))

        # Required security_access is BLOCKED
        self.engine.register_runner(
            "security_access",
            ConfigurableRunner(self.temp_dir, "security_access", TestStatus.BLOCKED, "Salesforce CLI unconfigured"),
        )

        scorecard = self.engine.run_all()

        self.assertFalse(scorecard.release_ready)
        self.assertFalse(scorecard.overall_passed)
        self.assertTrue(scorecard.blocked_tests >= 1)


if __name__ == "__main__":
    unittest.main()
