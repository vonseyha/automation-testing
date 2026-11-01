"""
Unit tests for Specialist Escalation Policy.
Per Section 4, 5, 11, 12, 18.
"""

import unittest

from orchestration.config import OrchestrationConfig
from orchestration.escalation.policy import EscalationPolicy
from orchestration.core_types import EscalationReason


class TestEscalationPolicy(unittest.TestCase):
    def setUp(self):
        self.config = OrchestrationConfig.load()
        self.policy = EscalationPolicy(self.config)

    def test_simple_formatting_task_stays_on_flash(self):
        decision = self.policy.evaluate("Fix formatting and typo in comments", changed_files=["readme.md"])
        self.assertFalse(decision.should_escalate)
        self.assertEqual(decision.task_complexity, "NORMAL")
        self.assertIn("Routine task", decision.explanation)

    def test_architecture_review_escalates_to_pro(self):
        decision = self.policy.evaluate("Design new subsystem architecture for event-driven asynchronous processing")
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.task_complexity, "COMPLEX")
        self.assertIn(EscalationReason.ARCHITECTURE_REVIEW, decision.reasons)

    def test_security_auth_change_escalates_to_pro(self):
        decision = self.policy.evaluate("Implement HMAC signature authentication and RBAC guards on protected endpoints")
        self.assertTrue(decision.should_escalate)
        self.assertIn(EscalationReason.CRITICAL_REVIEW, decision.reasons)

    def test_financial_ledger_reconciliation_escalates_to_pro(self):
        decision = self.policy.evaluate("Update GeneralLedger reconciliation logic for cashflow cash_bank closing balance")
        self.assertTrue(decision.should_escalate)
        self.assertIn(EscalationReason.CRITICAL_REVIEW, decision.reasons)

    def test_multi_file_change_escalates_to_pro(self):
        files = [
            "topautokh-api/controllers/cashflow.js",
            "topauto-api-cluster/apps/api-gateway/src/services/cashflow.service.ts",
            "top-auto-1653-admin-page/src/app/components/cashflow/cashflow.component.ts",
            "top-auto-1653-admin-page/src/app/components/cashflow/cashflow.component.html",
        ]
        decision = self.policy.evaluate("Update cashflow service contract across monorepo", changed_files=files)
        self.assertTrue(decision.should_escalate)
        self.assertIn(EscalationReason.CODE_REVIEW, decision.reasons)

    def test_user_override_force_flash(self):
        decision = self.policy.evaluate(
            "Change system architecture and security guards",
            user_prompt_override="Do not escalate; stay on flash",
        )
        self.assertFalse(decision.should_escalate)
        self.assertEqual(decision.user_override, "FORCE_FLASH")

    def test_user_override_force_pro(self):
        decision = self.policy.evaluate(
            "Minor button color change",
            user_prompt_override="Review this architecture using the pro reviewer",
        )
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.user_override, "FORCE_PRO")
        self.assertIn(EscalationReason.USER_EXPLICIT, decision.reasons)

    def test_security_test_failure_escalates(self):
        failures = [{"pillar": "Security & Access", "test_name": "hmac_validation", "critical": True}]
        decision = self.policy.evaluate("Routine maintenance", test_failures=failures)
        self.assertTrue(decision.should_escalate)
        self.assertIn(EscalationReason.CRITICAL_REVIEW, decision.reasons)


if __name__ == "__main__":
    unittest.main()
