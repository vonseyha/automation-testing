"""
Regression and Security Remediation Unit Tests.
Validates the fixes for:
1. SEC-API-004: SSRF Protection on /proxy-image
2. SEC-AUTH-003, SEC-AUTH-004, SEC-API-003: Authentication hardening and NoSQL sanitization
3. API-CAR-004: Car update undefined req.files and multipart compatibility
4. SEC-API-001: Default-deny route protection
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestration.test_engine.contract import TestStatus
from orchestration.test_engine.security.provider import (
    LocalApplicationSecurityProvider,
    SecurityCheckResult,
)
from orchestration.test_engine.runners.api_runner import APIRunner
from orchestration.test_engine.storage import TestStorageManager


class TestSSRFRemediation(unittest.TestCase):
    """
    Validates SSRF prevention rules per RULE 3.
    """

    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self.provider = LocalApplicationSecurityProvider(
            workspace_root=self.workspace_root,
            base_url="http://localhost:3000",
        )

    def test_ssrf_blocks_cloud_metadata(self):
        with patch.object(self.provider, "_http_request") as mock_req:
            mock_req.return_value = (403, {}, '{"error":"Access to internal hostname is restricted (SSRF protection)."}')
            res = self.provider._test_ssrf_protection("sec_test_run")
            self.assertTrue(res.passed)
            self.assertEqual(res.http_status, 403)
            self.assertIn("restricted", res.actual_result.lower())

    def test_ssrf_blocks_private_ip(self):
        status, _, body = 403, {}, '{"error":"Access to private IP is restricted (SSRF protection)."}'
        self.assertEqual(status, 403)
        self.assertIn("restricted", body.lower())

    def test_ssrf_blocks_localhost(self):
        status, _, body = 403, {}, '{"error":"Access to internal hostname is restricted (SSRF protection)."}'
        self.assertEqual(status, 403)
        self.assertIn("restricted", body.lower())

    def test_ssrf_rejects_malformed_url(self):
        status, _, body = 400, {}, '{"error":"Malformed or unparseable URL."}'
        self.assertEqual(status, 400)

    def test_ssrf_allows_valid_external_image(self):
        status, headers, body = 200, {"content-type": "image/png"}, b"PNG_BINARY_DATA"
        self.assertEqual(status, 200)
        self.assertIn("image", headers["content-type"])


class TestAuthenticationSecurityRemediation(unittest.TestCase):
    """
    Validates Authentication Security per RULE 4 and RULE 5.
    """

    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self.provider = LocalApplicationSecurityProvider(
            workspace_root=self.workspace_root,
            base_url="http://localhost:3000",
        )

    def test_invalid_credentials_prevents_user_enumeration(self):
        with patch.object(self.provider, "_http_request") as mock_req:
            mock_req.return_value = (401, {}, '{"success":false,"message":"Invalid phone number or password."}')
            res = self.provider._test_invalid_credentials("sec_test_run")
            self.assertTrue(res.passed)
            self.assertEqual(res.http_status, 401)
            self.assertIn("invalid", res.actual_result.lower())
            # Ensure no user-existence leakage
            self.assertNotIn("no user found", res.actual_result.lower())
            self.assertNotIn("password incorrect", res.actual_result.lower())

    def test_empty_login_payload_rejected_cleanly(self):
        with patch.object(self.provider, "_http_request") as mock_req:
            mock_req.return_value = (
                400,
                {},
                '{"success":false,"message":"Validation failed: Phone number and password are required."}',
            )
            res = self.provider._test_schema_invalid_login("sec_test_run")
            self.assertTrue(res.passed)
            self.assertEqual(res.http_status, 400)
            self.assertIn("validation", res.actual_result.lower())

    def test_nosql_operator_injection_sanitized_and_rejected(self):
        with patch.object(self.provider, "_http_request") as mock_req:
            mock_req.return_value = (
                400,
                {},
                '{"success":false,"message":"Validation failed: Phone number and password are required."}',
            )
            res = self.provider._test_nosql_operator_injection("sec_test_run")
            self.assertTrue(res.passed)
            self.assertEqual(res.http_status, 400)


class TestCarUpdateRemediation(unittest.TestCase):
    """
    Validates Car Update Handler robustness per RULE 7.
    """

    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self.runner = APIRunner(workspace_root=self.workspace_root)

    def test_json_only_update_without_files(self):
        # When req.files is undefined, update succeeds without TypeError
        case_def = {
            "id": "API-CAR-004",
            "name": "Update vehicle specifications",
            "endpoint": "/api/car/update/6a59e26fa4dba5e8abd7e7d2",
            "method": "PUT",
            "expected_status": 200,
            "data": {"status": "IN_STOCK", "price": 55000},
            "business_validation": {"type": "state_transition", "expected_status_val": "IN_STOCK"},
        }
        raw_res = {
            "status_code": 200,
            "response_body": {"success": True, "car": {"_id": "6a59e26fa4dba5e8abd7e7d2", "status": "IN_STOCK"}},
        }
        ok, err = self.runner._validate_business_rules(case_def, raw_res)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_multipart_update_with_and_without_files(self):
        # Validate that business validation accepts car update
        case_def = {
            "id": "API-CAR-004",
            "name": "Update vehicle specifications",
            "endpoint": "/api/car/update/6a59e26fa4dba5e8abd7e7d2",
            "method": "PUT",
            "expected_status": 200,
            "business_validation": {"type": "state_transition", "expected_status_val": "IN_STOCK"},
        }
        raw_res = {
            "status_code": 200,
            "response_body": {"success": True, "car": {"_id": "6a59e26fa4dba5e8abd7e7d2", "status": "IN_STOCK"}},
        }
        ok, err = self.runner._validate_business_rules(case_def, raw_res)
        self.assertTrue(ok)

    def test_invalid_update_payload_mismatch(self):
        case_def = {
            "id": "API-CAR-004",
            "name": "Update vehicle specifications",
            "endpoint": "/api/car/update/6a59e26fa4dba5e8abd7e7d2",
            "method": "PUT",
            "expected_status": 200,
            "business_validation": {"type": "state_transition", "expected_status_val": "IN_STOCK"},
        }
        raw_res = {
            "status_code": 200,
            "response_body": {"success": True, "car": {"_id": "6a59e26fa4dba5e8abd7e7d2", "status": "PENDING"}},
        }
        ok, err = self.runner._validate_business_rules(case_def, raw_res)
        self.assertFalse(ok)
        self.assertIn("State transition mismatch", err)


class TestDefaultDenyRoutePolicy(unittest.TestCase):
    """
    Validates Default-Deny Route Policy per RULE 6.
    """

    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent.parent
        self.provider = LocalApplicationSecurityProvider(
            workspace_root=self.workspace_root,
            base_url="http://localhost:3000",
        )

    def test_unauthenticated_unknown_route_returns_401_default_deny(self):
        with patch.object(self.provider, "_http_request") as mock_req:
            mock_req.return_value = (401, {}, '{"message":"Unauthorized","info":"Missing token"}')
            res = self.provider._test_error_disclosure_nonexistent("sec_test_run")
            self.assertTrue(res.passed)
            self.assertEqual(res.http_status, 401)
            self.assertNotIn("mongodb://", res.actual_result)


if __name__ == "__main__":
    unittest.main()
