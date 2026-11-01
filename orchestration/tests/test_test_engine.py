"""
Unit and integration tests for TestEngine and the 6 Pillars.
Per Section 10 & 11.
"""

import unittest

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.failure_escalation import TestFailureEscalator
from orchestration.core_types import TestPillar, TestResult


class TestTestEngine(unittest.TestCase):
    def setUp(self):
        self.config = OrchestrationConfig.load()
        self.engine = TestEngine(self.config)

    def test_run_all_six_pillars(self):
        scorecard = self.engine.run_all()
        self.assertEqual(len(scorecard.pillar_summaries), 6)
        expected_pillars = [
            TestPillar.UI_CHANNEL,
            TestPillar.API_INTEGRATION,
            TestPillar.PERFORMANCE,
            TestPillar.SECURITY_ACCESS,
            TestPillar.PENETRATION,
            TestPillar.AI_GROUNDING,
        ]
        for p in expected_pillars:
            self.assertIn(p, scorecard.pillar_summaries)
            summary = scorecard.pillar_summaries[p]
            self.assertTrue(summary.total_tests > 0)

        # Confirm release scorecard invariants
        self.assertEqual(
            scorecard.total_tests,
            scorecard.passed_tests + scorecard.failed_tests + scorecard.blocked_tests + scorecard.skipped_tests + scorecard.pending_tests,
        )
        self.assertIn("Release Gate:", scorecard.summary)

    def test_individual_pillar_execution(self):
        # The legacy static Performance pillar greps the backend source.
        if not (self.config.backend_workspace / "package.json").exists():
            self.skipTest(f"backend repo not found at {self.config.backend_workspace} (clone it next to this repo)")
        summary = self.engine.run_pillar(TestPillar.PERFORMANCE)
        self.assertEqual(summary.pillar, TestPillar.PERFORMANCE)
        self.assertTrue(summary.passed)
        self.assertEqual(summary.failed_tests, 0)

    def test_failure_escalator_identifies_security_failure(self):
        escalator = TestFailureEscalator()
        sec_failure = TestResult(
            pillar=TestPillar.SECURITY_ACCESS,
            suite_name="SecurityAccess_HMAC",
            test_name="validate_hmac_request_signing_protocol",
            passed=False,
            error="HMAC signature invalid",
        )
        should_escalate = escalator.should_escalate_failure(sec_failure, attempts=1)
        self.assertTrue(should_escalate)

    def test_failure_escalator_identifies_recurring_failure(self):
        escalator = TestFailureEscalator()
        perf_failure = TestResult(
            pillar=TestPillar.PERFORMANCE,
            suite_name="Performance_QueryBounding",
            test_name="verify_query_bounding",
            passed=False,
            error="Latency exceeded",
        )
        # 1 attempt -> normal (Flash)
        self.assertFalse(escalator.should_escalate_failure(perf_failure, attempts=1))
        # 2 attempts -> recurring failure (escalates to Pro)
        self.assertTrue(escalator.should_escalate_failure(perf_failure, attempts=2))


if __name__ == "__main__":
    unittest.main()
