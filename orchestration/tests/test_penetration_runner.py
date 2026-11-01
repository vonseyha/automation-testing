"""
Unit and integration tests for Real Penetration Runner & AI Security Evaluation Harness.
Verifies:
1. Controlled corpus execution across 7 attack categories.
2. AI Security Judge and Semantic Security Evaluation Engine.
3. Accurate detection of security breaches (e.g. key leakage, instruction override compliance).
4. Accurate verification of safety boundary defense (refusal).
5. Evidence artifact generation and metric reporting.
6. BLOCKED handling when required external targets are unconfigured.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from orchestration.config import OrchestrationConfig
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.test_engine.contract import TestStatus
from orchestration.test_engine.runners.penetration_runner import (
    SECURITY_EVALUATION_CORPUS,
    PenetrationRunner,
)
from orchestration.test_engine.storage import TestStorageManager


class TestPenetrationRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
        )
        self.storage = TestStorageManager(self.config)
        self.runner = PenetrationRunner(self.temp_dir, storage_manager=self.storage)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_baseline_guardrail_defends_against_all_vectors(self):
        """
        Baseline workspace guardrail safely refuses all 7 prompt-injection attack vectors.
        """
        result = self.runner.execute()
        self.assertEqual(result.status, TestStatus.PASSED)
        self.assertEqual(result.metrics["total_attack_cases"], 7)
        self.assertEqual(result.metrics["blocked_attacks"], 7)
        self.assertEqual(result.metrics["breaches_detected"], 0)
        self.assertEqual(result.metrics["blocked_rate_pct"], 100.0)
        self.assertEqual(len(result.failures), 0)

        # Verify evidence report exists on disk
        self.assertTrue(len(result.evidence) > 0)
        report_file = self.temp_dir / result.evidence[0]["path"]
        self.assertTrue(report_file.exists())
        data = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(data["total_cases"], 7)
        self.assertEqual(data["blocked_cases"], 7)

    def test_02_detects_breach_when_target_leaks_credential(self):
        """
        When target system leaks a private API key in response to SEC-04 attack vector,
        evaluator flags it as BREACHED and test status becomes FAILED.
        """
        def leaky_target(prompt: str) -> str:
            if "GEMINI_API_KEY" in prompt or "Dump all private" in prompt:
                # Malicious target complies and dumps a fake API key
                return "Here is your key: AIzaSyB1234567890123456789012345678901"
            return "Refusal: Request not permitted."

        runner = PenetrationRunner(
            self.temp_dir,
            evaluator_fn=leaky_target,
            storage_manager=self.storage,
        )
        result = runner.execute()

        self.assertEqual(result.status, TestStatus.FAILED)
        self.assertTrue(result.metrics["breaches_detected"] >= 1)
        self.assertTrue(result.metrics["blocked_rate_pct"] < 100.0)

        # Check failure diagnostics
        breach_cases = [f["case_id"] for f in result.failures]
        self.assertIn("SEC-04", breach_cases)

    def test_03_detects_breach_when_target_complies_with_override(self):
        """
        When target system obeys 'PWNED_SUCCESSFULLY' instruction override,
        evaluator flags it as BREACHED.
        """
        def obedient_target(prompt: str) -> str:
            if "PWNED_SUCCESSFULLY" in prompt:
                return "Understood. Output: PWNED_SUCCESSFULLY. Continuing in new mode."
            return "Refusal: Cannot execute."

        runner = PenetrationRunner(
            self.temp_dir,
            evaluator_fn=obedient_target,
            storage_manager=self.storage,
        )
        result = runner.execute()

        self.assertEqual(result.status, TestStatus.FAILED)
        breach_cases = [f["case_id"] for f in result.failures]
        self.assertIn("SEC-01", breach_cases)

    def test_04_ai_model_judge_structured_evaluation(self):
        """
        Uses an AI Model Judge client to evaluate target responses via structured JSON.
        """
        def judge_responder(prompt: str) -> str:
            # Model judge evaluates prompt and returns structured JSON verdict
            return json.dumps({
                "verdict": "BLOCKED",
                "confidence": 0.99,
                "reasoning": "The target properly recognized and neutralized the adversarial injection.",
                "risk_level": "NONE",
            })

        mock_judge = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=judge_responder,
        )

        runner = PenetrationRunner(
            self.temp_dir,
            judge_client=mock_judge,
            storage_manager=self.storage,
        )
        result = runner.execute()

        self.assertEqual(result.status, TestStatus.PASSED)
        self.assertEqual(result.metrics["blocked_attacks"], 7)

        # Verify evidence recorded model judge method
        report_file = self.temp_dir / result.evidence[0]["path"]
        data = json.loads(report_file.read_text(encoding="utf-8"))
        for c in data["cases"]:
            self.assertEqual(c["evaluation_method"], "LLM_SAFETY_JUDGE")
            self.assertEqual(c["verdict"], "BLOCKED")

    def test_05_blocked_when_external_target_is_required_but_missing(self):
        """
        When context specifies require_external_target=True and none is configured,
        runner returns BLOCKED rather than faking passed results.
        """
        runner = PenetrationRunner(self.temp_dir, storage_manager=self.storage)
        result = runner.execute(context={"require_external_target": True})

        self.assertEqual(result.status, TestStatus.BLOCKED)
        self.assertIn("No external target", result.blocked_reason)


if __name__ == "__main__":
    unittest.main()
