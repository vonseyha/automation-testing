"""
Automated Tests for Authoritative Release Gate (Per Section P0-1).
Verifies:
- Case 1: Real test runners ALL PASSED (with evidence), Legacy mock runners ALL FAILED -> READY FOR ROLLOUT.
- Case 2: Real test runners have 1 FAILED, Legacy mock runners ALL PASSED -> NOT READY.
- Case 3: Real test runners have 1 BLOCKED -> NOT READY.
- Case 4: Real test runners have 1 PENDING -> VALIDATION INCOMPLETE.
- Case 5: Real test runners missing required test -> VALIDATION INCOMPLETE.
- Additional: Required test PASSED but missing evidence -> VALIDATION INCOMPLETE.
- Legacy mock pillars are quarantined and never influence the release gate.
"""

import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

workspace_root = Path(__file__).resolve().parent.parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.pillars.base import BasePillar
from orchestration.test_engine.release_gate import ReleaseGateEvaluator, ReleaseStatus
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class StubRunner(BaseTestRunner):
    """Configurable runner for testing authoritative release gate."""

    def __init__(
        self,
        workspace_root: Path,
        runner_name: str,
        status: TestStatus,
        evidence: Optional[List[Dict[str, Any]]] = None,
        blocked_reason: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name=runner_name)
        self.status = status
        self.evidence = evidence if evidence is not None else ([{"path": f"{runner_name}.json", "evidence_type": "log"}] if status == TestStatus.PASSED else [])
        self.blocked_reason = blocked_reason

    def validate_configuration(self):
        return True, None

    def execute(self, context=None):
        return TestExecutionResult(
            test_run_id=context.get("test_run_id", "test_run") if context else "test_run",
            test_type=self.runner_name,
            status=self.status,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=10.0,
            evidence=self.evidence,
            blocked_reason=self.blocked_reason,
            failures=[{"error": f"{self.runner_name} failed"}] if self.status == TestStatus.FAILED else [],
        )

    def normalize_result(self, raw_result):
        return raw_result


class FailingLegacyPillar(BasePillar):
    """Mock legacy pillar that always fails."""

    def __init__(self, workspace_root: Path, pillar_enum: TestPillar):
        super().__init__(workspace_root)
        self._pillar_enum = pillar_enum

    @property
    def pillar_name(self) -> TestPillar:
        return self._pillar_enum

    def execute(self) -> PillarSummary:
        return PillarSummary(
            pillar=self._pillar_enum,
            total_tests=5,
            passed_tests=0,
            failed_tests=5,
            results=[
                TestResult(
                    pillar=self._pillar_enum,
                    suite_name="MockSuite",
                    test_name="mock_test",
                    passed=False,
                    error="Legacy mock failure",
                )
            ],
        )


class PassingLegacyPillar(BasePillar):
    """Mock legacy pillar that always passes."""

    def __init__(self, workspace_root: Path, pillar_enum: TestPillar):
        super().__init__(workspace_root)
        self._pillar_enum = pillar_enum

    @property
    def pillar_name(self) -> TestPillar:
        return self._pillar_enum

    def execute(self) -> PillarSummary:
        return PillarSummary(
            pillar=self._pillar_enum,
            total_tests=5,
            passed_tests=5,
            failed_tests=0,
            results=[
                TestResult(
                    pillar=self._pillar_enum,
                    suite_name="MockSuite",
                    test_name="mock_test",
                    passed=True,
                )
            ],
        )


class TestAuthoritativeReleaseGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
        )
        self.engine = TestEngine(self.config)
        self.evaluator = ReleaseGateEvaluator(
            required_test_types=["api_integration", "security_access", "penetration"]
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_case_1_real_all_passed_legacy_all_failed(self):
        """
        P0-1C Case 1:
        Real test runners ALL PASSED (with evidence), Legacy mock runners ALL FAILED.
        Release gate MUST evaluate to READY FOR ROLLOUT.
        Legacy mock failures must NOT affect release gate.
        """
        # Register failing legacy pillars
        for pillar_enum in TestPillar:
            self.engine.register_pillar(pillar_enum, FailingLegacyPillar(self.temp_dir, pillar_enum))

        # Register passing real runners with evidence
        for r_name in ["api_connectivity", "ui_channel", "api_integration", "performance", "security_access", "penetration", "ai_grounding"]:
            self.engine.register_runner(r_name, StubRunner(self.temp_dir, r_name, TestStatus.PASSED))

        scorecard = self.engine.run_all()

        self.assertTrue(scorecard.release_ready)
        self.assertTrue(scorecard.overall_passed)
        self.assertEqual(scorecard.failed_tests, 0)
        self.assertIn("READY FOR ROLLOUT", scorecard.summary)

        # Direct evaluation of real runner results
        gate_res = self.engine.evaluate_release_gate()
        self.assertEqual(gate_res["status"], ReleaseStatus.READY_FOR_ROLLOUT.value)
        self.assertTrue(gate_res["ready_for_rollout"])

    def test_case_2_real_one_failed_legacy_all_passed(self):
        """
        P0-1C Case 2:
        Real test runners have 1 FAILED, Legacy mock runners ALL PASSED.
        Release gate MUST evaluate to NOT READY.
        Legacy mock passes must NOT grant release readiness.
        """
        # Register passing legacy pillars
        for pillar_enum in TestPillar:
            self.engine.register_pillar(pillar_enum, PassingLegacyPillar(self.temp_dir, pillar_enum))

        # Real runners: security_access FAILS
        for r_name in ["api_connectivity", "ui_channel", "api_integration", "performance", "penetration", "ai_grounding"]:
            self.engine.register_runner(r_name, StubRunner(self.temp_dir, r_name, TestStatus.PASSED))
        self.engine.register_runner("security_access", StubRunner(self.temp_dir, "security_access", TestStatus.FAILED))

        scorecard = self.engine.run_all()

        self.assertFalse(scorecard.release_ready)
        self.assertFalse(scorecard.overall_passed)
        self.assertIn("NOT READY", scorecard.summary)

        gate_res = self.engine.evaluate_release_gate()
        self.assertEqual(gate_res["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(gate_res["ready_for_rollout"])

    def test_case_3_real_one_blocked(self):
        """
        P0-1C Case 3:
        Real test runners have 1 BLOCKED.
        Release gate MUST evaluate to NOT READY.
        """
        for r_name in ["api_connectivity", "ui_channel", "api_integration", "performance", "penetration", "ai_grounding"]:
            self.engine.register_runner(r_name, StubRunner(self.temp_dir, r_name, TestStatus.PASSED))
        self.engine.register_runner(
            "penetration",
            StubRunner(self.temp_dir, "penetration", TestStatus.BLOCKED, blocked_reason="Target environment unreachable"),
        )

        scorecard = self.engine.run_all()

        self.assertFalse(scorecard.release_ready)
        self.assertFalse(scorecard.overall_passed)
        self.assertIn("NOT READY", scorecard.summary)

        gate_res = self.engine.evaluate_release_gate()
        self.assertEqual(gate_res["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(gate_res["ready_for_rollout"])

    def test_case_4_real_one_pending(self):
        """
        P0-1C Case 4:
        Real test runners have 1 PENDING (and none failed/blocked).
        Release gate MUST evaluate to VALIDATION INCOMPLETE.
        """
        results = [
            TestExecutionResult(
                test_run_id="run_1",
                test_type="api_integration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "api.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_1",
                test_type="security_access",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "sec.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_1",
                test_type="penetration",
                status=TestStatus.PENDING,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                evidence=[],
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.VALIDATION_INCOMPLETE.value)
        self.assertFalse(gate_res["ready_for_rollout"])
        self.assertTrue(any("PENDING" in reason for reason in gate_res["blocking_reasons"]))

    def test_case_5_real_missing_required_test(self):
        """
        P0-1C Case 5:
        Real test runners missing required test from execution run.
        Release gate MUST evaluate to VALIDATION INCOMPLETE.
        """
        # Only api_integration and security_access executed; penetration missing
        results = [
            TestExecutionResult(
                test_run_id="run_2",
                test_type="api_integration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "api.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_2",
                test_type="security_access",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "sec.json"}],
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.VALIDATION_INCOMPLETE.value)
        self.assertFalse(gate_res["ready_for_rollout"])
        self.assertTrue(any("penetration" in reason and "not executed" in reason for reason in gate_res["blocking_reasons"]))

    def test_case_6_passed_required_test_missing_evidence(self):
        """
        Additional requirement (Section P0-1B):
        Evidence artifacts exist for all required test results.
        If a required test PASSED but has empty evidence, evaluate to VALIDATION INCOMPLETE.
        """
        results = [
            TestExecutionResult(
                test_run_id="run_3",
                test_type="api_integration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "api.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_3",
                test_type="security_access",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "sec.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_3",
                test_type="penetration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[],  # MISSING EVIDENCE
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.VALIDATION_INCOMPLETE.value)
        self.assertFalse(gate_res["ready_for_rollout"])
        self.assertTrue(any("no evidence artifacts" in reason for reason in gate_res["blocking_reasons"]))

    def test_case_7_failure_takes_precedence_over_pending_or_missing_evidence(self):
        """
        If one required test FAILED and another is PENDING or missing evidence,
        the status must be NOT READY (failure trumps incomplete).
        """
        results = [
            TestExecutionResult(
                test_run_id="run_4",
                test_type="api_integration",
                status=TestStatus.FAILED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                failures=[{"error": "500 Server Error"}],
            ),
            TestExecutionResult(
                test_run_id="run_4",
                test_type="penetration",
                status=TestStatus.PENDING,
                started_at="",
                completed_at="",
                duration_ms=0.0,
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(gate_res["ready_for_rollout"])

    def test_case_8_optional_blocked_does_not_block_gate(self):
        """
        Optional suites (ai_grounding, ui_channel) BLOCKED while all required
        suites PASS with evidence. Gate should be READY FOR ROLLOUT.
        Optional failures appear in informational_warnings, not blocking_reasons.
        """
        results = [
            TestExecutionResult(
                test_run_id="run_5",
                test_type="api_integration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "api.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_5",
                test_type="security_access",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "sec.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_5",
                test_type="penetration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "pen.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_5",
                test_type="ai_grounding",
                status=TestStatus.BLOCKED,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                blocked_reason="Agentforce Testing Center not configured",
            ),
            TestExecutionResult(
                test_run_id="run_5",
                test_type="ui_channel",
                status=TestStatus.FAILED,
                started_at="",
                completed_at="",
                duration_ms=10.0,
                failures=[{"error": "Playwright dependency conflict"}],
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.READY_FOR_ROLLOUT.value)
        self.assertTrue(gate_res["ready_for_rollout"])
        self.assertEqual(len(gate_res["blocking_reasons"]), 0)
        self.assertEqual(len(gate_res["informational_warnings"]), 2)
        self.assertTrue(any("ai_grounding" in w for w in gate_res["informational_warnings"]))
        self.assertTrue(any("ui_channel" in w for w in gate_res["informational_warnings"]))

    def test_case_9_required_blocked_still_blocks_even_with_optional_ok(self):
        """
        A required suite BLOCKED blocks the gate even if optional suites pass.
        """
        results = [
            TestExecutionResult(
                test_run_id="run_6",
                test_type="api_integration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "api.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_6",
                test_type="security_access",
                status=TestStatus.BLOCKED,
                started_at="",
                completed_at="",
                duration_ms=0.0,
                blocked_reason="Backend unreachable",
            ),
            TestExecutionResult(
                test_run_id="run_6",
                test_type="penetration",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "pen.json"}],
            ),
            TestExecutionResult(
                test_run_id="run_6",
                test_type="ui_channel",
                status=TestStatus.PASSED,
                started_at="",
                completed_at="",
                duration_ms=5.0,
                evidence=[{"path": "ui.json"}],
            ),
        ]

        gate_res = self.evaluator.evaluate(results)
        self.assertEqual(gate_res["status"], ReleaseStatus.NOT_READY.value)
        self.assertFalse(gate_res["ready_for_rollout"])
        self.assertTrue(any("security_access" in r for r in gate_res["blocking_reasons"]))


if __name__ == "__main__":
    unittest.main()
