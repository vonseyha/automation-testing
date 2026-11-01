"""
Unit tests for the identity used by the entitlement-denial API cases.

FEATURE_NOT_IN_PLAN cases must run as a tenant that is really on the Basic plan
(TEST_BASIC_PLAN_*), not as the default BASIC tenant, which may be on a higher plan.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestration.test_engine.runners.api_runner import STANDARD_API_CASES, APIRunner

FEATURE_CASES = [
    c for c in STANDARD_API_CASES
    if (c.get("business_validation") or {}).get("type") == "entitlement_denial"
    and c["business_validation"].get("expected_code") == "FEATURE_NOT_IN_PLAN"
]
PLATFORM_DENIAL_CASES = [
    c for c in STANDARD_API_CASES
    if (c.get("business_validation") or {}).get("type") == "entitlement_denial"
    and c["business_validation"].get("expected_code") == "PLATFORM_ADMIN_REQUIRED"
]
ENV_KEYS = ("TEST_BASIC_PLAN_COMPANY_ID", "TEST_BASIC_PLAN_EMPLOYEE_ID", "JWT_SECRET")


class TestEntitlementIdentity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.runner = APIRunner(self.temp_dir, backend_workspace=self.temp_dir / "backend")
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_catalog_has_the_cases(self):
        self.assertEqual(len(FEATURE_CASES), 3)
        self.assertEqual(len(PLATFORM_DENIAL_CASES), 2)

    def test_feature_denial_uses_basic_plan_token(self):
        for case in FEATURE_CASES:
            token, gap = self.runner._select_token_for_case(case, "basic", "premium", "platform", "basic-plan")
            self.assertEqual((token, gap), ("basic-plan", None), case["id"])

    def test_feature_denial_blocked_without_basic_plan_tenant(self):
        for case in FEATURE_CASES:
            token, gap = self.runner._select_token_for_case(case, "basic", "premium", "platform", "")
            self.assertEqual(token, "", case["id"])
            self.assertEqual(gap, "FIXTURE_MISSING_BASIC_PLAN_TENANT", case["id"])

    def test_platform_denial_still_uses_basic_tenant(self):
        for case in PLATFORM_DENIAL_CASES:
            token, gap = self.runner._select_token_for_case(case, "basic", "premium", "platform", "basic-plan")
            self.assertEqual((token, gap), ("basic", None), case["id"])

    def test_basic_plan_token_empty_when_not_configured(self):
        os.environ["JWT_SECRET"] = "unit-test-secret"
        self.assertEqual(self.runner._get_basic_plan_token(), "")

    def test_basic_plan_token_minted_for_configured_tenant(self):
        os.environ.update({
            "JWT_SECRET": "unit-test-secret",
            "TEST_BASIC_PLAN_COMPANY_ID": "aaa000000000000000000020",
            "TEST_BASIC_PLAN_EMPLOYEE_ID": "aaa000000000000000000021",
        })
        token = self.runner._get_basic_plan_token()
        self.assertEqual(token.count("."), 2)
        summary = self.runner.get_fixture_summary()["basic_plan_tenant"]
        self.assertTrue(summary["configured"])
        self.assertEqual(summary["company_id"], "aaa000000000000000000020")


if __name__ == "__main__":
    unittest.main()
