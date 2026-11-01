"""
Unit tests for the Provider-Based Security Architecture.
Tests LocalApplicationSecurityProvider, SalesforceSecurityProvider,
EnterpriseIAMSecurityProvider, and SecurityProviderFactory.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestration.test_engine.contract import TestStatus
from orchestration.test_engine.security.provider import (
    EnterpriseIAMSecurityProvider,
    LocalApplicationSecurityProvider,
    SalesforceSecurityProvider,
    SecurityCheckResult,
    SecurityProviderFactory,
)
from orchestration.test_engine.storage import TestStorageManager


class TestSecurityProviders(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self.storage = TestStorageManager()

    def test_factory_defaults_to_local(self):
        provider = SecurityProviderFactory.create(
            provider_name=None,
            workspace_root=self.workspace_root,
            storage=self.storage,
        )
        self.assertIsInstance(provider, LocalApplicationSecurityProvider)

    def test_factory_creates_salesforce_provider(self):
        provider = SecurityProviderFactory.create(
            provider_name="salesforce",
            workspace_root=self.workspace_root,
            storage=self.storage,
            sf_cli_path="/fake/sf",
            sf_target_org="my-org",
        )
        self.assertIsInstance(provider, SalesforceSecurityProvider)

    def test_factory_creates_enterprise_provider(self):
        provider = SecurityProviderFactory.create(
            provider_name="enterprise",
            workspace_root=self.workspace_root,
            storage=self.storage,
            security_validation_command="vault status",
        )
        self.assertIsInstance(provider, EnterpriseIAMSecurityProvider)

    def test_salesforce_provider_validation_blocks_without_target_org(self):
        provider = SalesforceSecurityProvider(
            workspace_root=self.workspace_root,
            storage=self.storage,
            sf_cli_path="/opt/homebrew/bin/sf",
            sf_target_org=None,
        )
        valid, reason = provider.validate_configuration()
        self.assertFalse(valid)
        self.assertIn("target org is not configured", reason)

    def test_local_provider_execution_mocked_http(self):
        provider = LocalApplicationSecurityProvider(
            workspace_root=self.workspace_root,
            storage=self.storage,
            base_url="http://localhost:3000",
        )

        with patch.object(provider, "validate_configuration", return_value=(True, None)):
            with patch.object(provider, "_http_request") as mock_req:
                # Return standard expected responses for security checks
                def mock_resp(endpoint, method="GET", headers=None, data=None, timeout=10):
                    if endpoint == "/health":
                        return 200, {"x-content-type-options": "nosniff", "x-frame-options": "SAMEORIGIN", "strict-transport-security": "max-age=15552000"}, '{"status":"ok"}'
                    elif endpoint == "/api/employee/add" and headers and "Bearer" in headers.get("Authorization", ""):
                        return 401, {}, '{"message":"Unauthorized","info":"jwt malformed"}'
                    elif endpoint == "/api/auth/login" and data and b"WrongPassword" in data:
                        return 401, {}, '{"success":false,"message":"Invalid phone number or password"}'
                    elif endpoint == "/api/auth/login" and data and b"$gt" in data:
                        return 400, {}, '{"success":false,"message":"validation failed"}'
                    elif endpoint == "/api/auth/login" and data == b"{}":
                        return 400, {}, '{"success":false,"message":"validation failed"}'
                    elif endpoint == "/api/auth/login" and method == "DELETE":
                        return 404, {}, '"No API route found"'
                    elif endpoint == "/api/role/list" and headers and "Bearer" in headers.get("Authorization", ""):
                        return 200, {}, '{"roles":[]}'
                    elif "api/employee/list" in endpoint and headers and "Bearer" in headers.get("Authorization", ""):
                        return 200, {}, '{"success":true,"data":[]}'
                    elif endpoint == "/api/cashflow" and headers and "Bearer" in headers.get("Authorization", ""):
                        return 401, {}, '{"message":"Unauthorized","info":"Token invalidated"}'
                    elif "proxy-image" in endpoint:
                        return 403, {}, '{"success":false,"message":"Access to the requested URL is restricted."}'
                    elif "nonexistent" in endpoint:
                        return 404, {}, '"No API route found"'
                    else:
                        return 401, {}, '{"message":"Unauthorized","info":"Missing token"}'

                mock_req.side_effect = mock_resp

                res = provider.execute("test_sec_run_1")
                self.assertEqual(res.status, TestStatus.PASSED)
                self.assertEqual(res.metrics["provider"], "local")
                self.assertEqual(res.metrics["total_checks"], 16)
                self.assertEqual(res.metrics["passed_checks"], 16)
                self.assertEqual(res.metrics["failed_checks"], 0)
                self.assertTrue(len(res.evidence) > 0)


if __name__ == "__main__":
    unittest.main()
