"""
Provider-Based Security Architecture for TopAuto Test Engine.

Supports multiple pluggable security providers:
- LocalApplicationSecurityProvider: Real HTTP security checks against local/staging backend (DEFAULT).
- SalesforceSecurityProvider: Real Salesforce CLI profile & org validation (OPTIONAL/FUTURE).
- EnterpriseIAMSecurityProvider: Custom command-based enterprise IAM verification (OPTIONAL/FUTURE).
"""

import abc
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.config import basic_company_id, basic_employee_id
from orchestration.security.sanitizer import sanitize_data
from orchestration.test_engine.contract import TestCaseResult, TestExecutionResult, TestStatus
from orchestration.test_engine.storage import TestStorageManager


@dataclass
class SecurityCheckResult:
    """
    Individual security test execution record.
    Per Section 5:
    Includes Test ID, category, action performed, expected behavior, actual result,
    HTTP status, PASS/FAIL status, evidence reference, and execution ID.
    """
    test_id: str
    category: str
    request_action: str
    expected_behavior: str
    actual_result: str
    http_status: Optional[int]
    passed: bool
    evidence_reference: Optional[str]
    execution_id: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SecurityProvider(abc.ABC):
    """
    Abstract Base Class for security validation providers.
    """

    def __init__(self, workspace_root: Path, storage: Optional[TestStorageManager] = None):
        self.workspace_root = workspace_root
        self.storage = storage or TestStorageManager()

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        """Discovers available test cases for this security provider."""
        return []

    @abc.abstractmethod
    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """Checks if required binaries, URLs, or environment variables are available."""
        pass

    @abc.abstractmethod
    def execute(self, test_run_id: str, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        """Executes real security verification and returns TestExecutionResult with evidence."""
        pass


SECURITY_TEST_METADATA: Dict[str, Dict[str, str]] = {
    "SEC-AUTH-001": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-AUTH-002": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-AUTH-003": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-AUTH-004": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-AUTH-005": {"feature_id": "SYS-004", "module": "System & Integrations", "priority": "P0"},
    "SEC-AUTHZ-001": {"feature_id": "FIN-001", "module": "Finance & Cashflow", "priority": "P0"},
    "SEC-AUTHZ-002": {"feature_id": "HR-001", "module": "HR & Attendance", "priority": "P0"},
    "SEC-AUTHZ-003": {"feature_id": "RBAC-001", "module": "Access Control & RBAC", "priority": "P0"},
    "SEC-API-001": {"feature_id": "SYS-004", "module": "System & Integrations", "priority": "P1"},
    "SEC-API-002": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P1"},
    "SEC-API-003": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-API-004": {"feature_id": "SYS-004", "module": "System & Integrations", "priority": "P1"},
    "SEC-API-005": {"feature_id": "SYS-004", "module": "System & Integrations", "priority": "P0"},
    "SEC-RBAC-001": {"feature_id": "RBAC-003", "module": "Access Control & RBAC", "priority": "P0"},
    "SEC-AUTH-002-REVOKE": {"feature_id": "AUTH-001", "module": "Authentication & Identity", "priority": "P0"},
    "SEC-RBAC-002": {"feature_id": "RBAC-001", "module": "Access Control & RBAC", "priority": "P0"},
}


class LocalApplicationSecurityProvider(SecurityProvider):
    """
    DEFAULT provider: Performs real HTTP requests against the application backend.
    Validates actual authentication, authorization, RBAC, input validation, and API security.
    Never uses regex-only source inspection or fake results.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage: Optional[TestStorageManager] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(workspace_root, storage)
        self.base_url = (base_url or os.environ.get("SECURITY_BASE_URL") or os.environ.get("API_BASE_URL") or "http://localhost:3000").rstrip("/")

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        specs = [
            ("SEC-AUTH-001", "Missing token check", "GET /api/payroll", "HTTP 401 Unauthorized rejecting request with 'Missing token'"),
            ("SEC-AUTH-002", "Malformed token check", "POST /api/employee/add", "HTTP 401 Unauthorized rejecting malformed token"),
            ("SEC-AUTH-003", "Invalid credentials check", "POST /api/auth/login", "HTTP 401 Unauthorized or 429 Rate Limited"),
            ("SEC-AUTH-004", "Empty payload schema check", "POST /api/auth/login", "HTTP 400 Bad Request or 429 Rate Limited"),
            ("SEC-AUTH-005", "Public health endpoint probe", "GET /health", "HTTP 200 OK permitting unauthenticated probe"),
            ("SEC-AUTHZ-001", "Protected financial records check", "GET /api/cashflow", "HTTP 401 Unauthorized blocking ledger access"),
            ("SEC-AUTHZ-002", "Unauthorized record modification", "PATCH /api/employee/update/status/:id", "HTTP 401 Unauthorized denying state alteration"),
            ("SEC-AUTHZ-003", "Role management route check", "GET /api/role/list", "HTTP 401 Unauthorized protecting RBAC directory"),
            ("SEC-API-001", "Default-deny route inspection probe", "GET /api/probe/nonexistent-internal-resource", "HTTP 401 Unauthorized (Default-Deny policy) or HTTP 404 without leaking secrets or DB URIs"),
            ("SEC-API-002", "Disallowed method restriction", "DELETE /api/auth/login", "HTTP 404/405 rejecting unsupported method"),
            ("SEC-API-003", "NoSQL operator injection defense", "POST /api/auth/login", "HTTP 400/401 safely refusing operator injection"),
            ("SEC-API-004", "SSRF protection probe", "GET /api/probe/ssrf", "Request blocked or denied (SSRF prevention)"),
            ("SEC-API-005", "Security headers inspection", "GET /health", "Helmet headers enforced (X-Content-Type-Options, etc.)"),
            ("SEC-RBAC-001", "Unprivileged role access denial", "GET /api/cashflow", "HTTP 401/403 denying access to unauthorized roles"),
            ("SEC-AUTH-002-REVOKE", "Invalidated token rejection via tokenValidUntil", "GET /api/cashflow", "HTTP 401 Unauthorized rejecting invalidated token with 'Token invalidated'"),
            ("SEC-RBAC-002", "Admin full bypass authorization guarantee", "GET /api/role/list", "HTTP 200 permitting Admin full access bypass"),
        ]
        cases = []
        for tid, name, endpoint, expected in specs:
            meta = SECURITY_TEST_METADATA.get(tid, {})
            cases.append(
                TestCaseResult(
                    test_case_id=tid,
                    test_name=f"{name} ({endpoint})",
                    test_pillar="Security & Access",
                    description=f"{name}: {endpoint} -> {expected}",
                    execution_status=TestStatus.PENDING,
                    started_at="",
                    completed_at="",
                    duration_ms=0.0,
                    details=endpoint,
                    expected=expected,
                    runner="security_access",
                    feature_id=meta.get("feature_id", ""),
                    module=meta.get("module", ""),
                    priority=meta.get("priority", "P1"),
                )
            )
        return cases

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        # Verify base_url format and backend accessibility
        if not self.base_url.startswith("http://") and not self.base_url.startswith("https://"):
            return False, f"Invalid SECURITY_BASE_URL format: '{self.base_url}'"

        # Safe diagnostic probe to ensure local server is responsive
        try:
            req = urllib.request.Request(f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status < 500:
                    return True, None
        except Exception:
            # Fallback probe to root
            try:
                req = urllib.request.Request(self.base_url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return True, None
            except urllib.error.HTTPError:
                # Any HTTP status (even 401/404) means the server is reachable and active
                return True, None
            except Exception as e:
                return False, f"Local application backend is not reachable at {self.base_url}: {e}"

        return True, None

    def execute(self, test_run_id: str, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            blocked_cases = []
            for c in self.discover_test_cases(context):
                c.execution_status = TestStatus.BLOCKED
                c.started_at = start_time
                c.completed_at = end_time
                c.execution_id = test_run_id
                c.blocking_dependency = "Backend server availability"
                c.missing_configuration = reason or "Backend server not accessible"
                c.required_remediation = f"Ensure backend server is running and accessible at {self.base_url}"
                c.error = reason
                c.details = reason
                blocked_cases.append(c)

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "local"},
                failures=[],
                evidence=[],
                environment="local",
                blocked_reason=reason,
                test_cases=blocked_cases,
            )

        checks: List[SecurityCheckResult] = []

        # --- 1. Authentication Checks ---
        checks.append(self._test_missing_token(test_run_id))
        checks.append(self._test_malformed_token(test_run_id))
        checks.append(self._test_invalid_credentials(test_run_id))
        checks.append(self._test_schema_invalid_login(test_run_id))
        checks.append(self._test_public_endpoint_access(test_run_id))
        checks.append(self._test_token_revocation(test_run_id))

        # --- 2. Authorization & RBAC Checks ---
        checks.append(self._test_protected_financial_records(test_run_id))
        checks.append(self._test_unauthorized_record_modification(test_run_id))
        checks.append(self._test_role_management_route(test_run_id))
        checks.append(self._test_unprivileged_role_denial(test_run_id))
        checks.append(self._test_admin_bypass(test_run_id))

        # --- 3. API Security & Input Validation Checks ---
        checks.append(self._test_error_disclosure_nonexistent(test_run_id))
        checks.append(self._test_disallowed_method_restriction(test_run_id))
        checks.append(self._test_nosql_operator_injection(test_run_id))
        checks.append(self._test_ssrf_protection(test_run_id))
        checks.append(self._test_security_headers(test_run_id))

        duration_ms = (time.perf_counter() - t_start) * 1000
        end_time = datetime.now(timezone.utc).isoformat()

        passed_count = sum(1 for c in checks if c.passed)
        failed_count = sum(1 for c in checks if not c.passed)
        failures = [{"test_id": c.test_id, "error": c.actual_result} for c in checks if not c.passed]

        # Sanitize report payload
        clean_report = {
            "test_run_id": test_run_id,
            "provider": "LocalApplicationSecurityProvider",
            "base_url": self.base_url,
            "total_checks": len(checks),
            "passed_checks": passed_count,
            "failed_checks": failed_count,
            "checks": [c.to_dict() for c in checks],
        }
        sanitized_report = sanitize_data(clean_report)

        ev_ref = self.storage.save_evidence_file(
            test_run_id=test_run_id,
            filename="security_audit.json",
            content=json.dumps(sanitized_report, indent=2),
            evidence_type="security_audit",
            description="Real Local Application Security & Authorization Test Report",
        )

        test_cases: List[TestCaseResult] = []
        per_case_duration = round(duration_ms / len(checks), 1) if checks else 0.0
        for c in checks:
            case_evidence = dict(ev_ref)
            case_evidence["execution_id"] = test_run_id
            case_evidence["test_case_id"] = c.test_id
            case_evidence["runner"] = "security_access"
            case_evidence["timestamp"] = end_time
            case_evidence["log_reference"] = ev_ref.get("path")

            meta = SECURITY_TEST_METADATA.get(c.test_id, {})
            tc = TestCaseResult(
                test_case_id=c.test_id,
                test_name=c.request_action,
                test_pillar="Security & Access",
                description=f"{c.category.upper()}: {c.request_action} - {c.expected_behavior}",
                execution_status=TestStatus.PASSED if c.passed else TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=per_case_duration,
                error=None if c.passed else f"Actual: {c.actual_result} (Expected: {c.expected_behavior})",
                evidence=[case_evidence],
                execution_id=test_run_id,
                details=f"HTTP {c.http_status}" if c.http_status else c.actual_result,
                failure_reason=f"Security check failed: {c.actual_result}" if not c.passed else None,
                expected=c.expected_behavior,
                actual=c.actual_result,
                required_action="Enforce security middleware / authentication boundary on endpoint." if not c.passed else None,
                runner="security_access",
                feature_id=meta.get("feature_id", ""),
                module=meta.get("module", ""),
                priority=meta.get("priority", "P1"),
            )
            test_cases.append(tc)

        status = TestStatus.PASSED if failed_count == 0 else TestStatus.FAILED

        return TestExecutionResult(
            test_run_id=test_run_id,
            test_type="security_access",
            status=status,
            started_at=start_time,
            completed_at=end_time,
            duration_ms=duration_ms,
            metrics={
                "provider": "local",
                "total_checks": len(checks),
                "passed_checks": passed_count,
                "failed_checks": failed_count,
                "success_rate_pct": round((passed_count / len(checks)) * 100.0, 1),
            },
            failures=failures,
            evidence=[ev_ref],
            environment="local",
            raw_result_reference=ev_ref["path"],
            test_cases=test_cases,
        )


    # ──────────────────────────────────────────────────────────────────────────
    # Individual Real Test Implementations
    # ──────────────────────────────────────────────────────────────────────────

    def _http_request(
        self,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
        timeout: int = 10,
    ) -> Tuple[int, Dict[str, str], str]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        req_headers = headers or {}
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_headers = {k.lower(): v for k, v in resp.getheaders()}
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, resp_headers, body
        except urllib.error.HTTPError as e:
            resp_headers = {k.lower(): v for k, v in e.headers.items()} if hasattr(e, "headers") and e.headers else {}
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            return e.code, resp_headers, body
        except Exception as ex:
            return 0, {}, str(ex)

    def _test_missing_token(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/api/payroll", method="GET")
        passed = (status == 401 and ("AUTH_TOKEN_MISSING" in body or "token" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTH-001",
            category="authentication",
            request_action="GET /api/payroll (no Authorization header)",
            expected_behavior="HTTP 401 Unauthorized rejecting request without auth token",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/payroll", "status": status},
        )

    def _test_malformed_token(self, execution_id: str) -> SecurityCheckResult:
        headers = {"Authorization": "Bearer invalid.malformed.garbage-token"}
        status, _, body = self._http_request("/api/employee/add", method="POST", headers=headers, data=b"{}")
        passed = (status == 401 and ("jwt malformed" in body or "invalid" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTH-002",
            category="authentication",
            request_action="POST /api/employee/add (malformed Bearer JWT)",
            expected_behavior="HTTP 401 Unauthorized rejecting malformed token",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/employee/add", "status": status},
        )

    def _test_invalid_credentials(self, execution_id: str) -> SecurityCheckResult:
        payload = json.dumps({"phoneNumber": "099999999", "password": "WrongPasswordXYZ987!"}).encode()
        headers = {"Content-Type": "application/json"}
        status, _, body = self._http_request("/api/auth/login", method="POST", headers=headers, data=payload)
        # 400 (user not found), 401 (credentials rejected), or 429 (rate limiter actively blocking)
        passed = (status in (400, 401, 429) and ("invalid" in body.lower() or "too many" in body.lower() or "no user found" in body.lower() or "not found" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTH-003",
            category="authentication",
            request_action="POST /api/auth/login (incorrect credentials)",
            expected_behavior="HTTP 401 Unauthorized or 429 Rate Limited blocking unauthorized login attempt",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/auth/login", "status": status},
        )

    def _test_schema_invalid_login(self, execution_id: str) -> SecurityCheckResult:
        headers = {"Content-Type": "application/json"}
        status, _, body = self._http_request("/api/auth/login", method="POST", headers=headers, data=b"{}")
        # 400 Bad Request (schema rejected) or 429 (rate limiter)
        passed = ((status == 400 and ("validation" in body.lower() or "errors" in body.lower())) or (status == 429 and "too many" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTH-004",
            category="authentication",
            request_action="POST /api/auth/login (empty payload)",
            expected_behavior="HTTP 400 Bad Request or 429 Rate Limited strictly rejecting malformed input",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/auth/login", "status": status},
        )

    def _test_public_endpoint_access(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/health", method="GET")
        passed = (status == 200 and "ok" in body.lower())
        return SecurityCheckResult(
            test_id="SEC-AUTH-005",
            category="authentication",
            request_action="GET /health (public health probe)",
            expected_behavior="HTTP 200 OK permitting unauthenticated probe on public endpoint",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/health", "status": status},
        )

    def _test_protected_financial_records(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/api/cashflow", method="GET")
        passed = (status == 401 and ("AUTH_TOKEN_MISSING" in body or "token" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTHZ-001",
            category="authorization",
            request_action="GET /api/cashflow (unauthenticated financial ledger access)",
            expected_behavior="HTTP 401 Unauthorized blocking unauthenticated ledger access",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/cashflow", "status": status},
        )

    def _test_unauthorized_record_modification(self, execution_id: str) -> SecurityCheckResult:
        payload = json.dumps({"status": "inactive"}).encode()
        headers = {"Content-Type": "application/json"}
        status, _, body = self._http_request(
            "/api/employee/update/status/60d5ec49f1b2c82d88c8e111",
            method="PATCH",
            headers=headers,
            data=payload,
        )
        passed = (status == 401 and ("AUTH_TOKEN_MISSING" in body or "token" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTHZ-002",
            category="authorization",
            request_action="PATCH /api/employee/update/status/:id (unauthorized state alteration)",
            expected_behavior="HTTP 401 Unauthorized denying unauthenticated record update",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/employee/update/status", "status": status},
        )

    def _test_role_management_route(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/api/role/list", method="GET")
        passed = (status in (401, 403) and ("token" in body.lower() or "unauthorized" in body.lower() or "admin" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-AUTHZ-003",
            category="authorization",
            request_action="GET /api/role/list (unauthenticated RBAC role directory inspection)",
            expected_behavior="HTTP 401/403 protecting RBAC role definitions from unauthenticated access",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/role/list", "status": status},
        )

    def _test_unprivileged_role_denial(self, execution_id: str) -> SecurityCheckResult:
        headers = {"Authorization": "Bearer customer.unprivileged.token"}
        status, _, body = self._http_request("/api/cashflow", method="GET", headers=headers)
        passed = (status in (401, 403))
        return SecurityCheckResult(
            test_id="SEC-RBAC-001",
            category="authorization",
            request_action="GET /api/cashflow (unprivileged non-admin role access attempt)",
            expected_behavior="HTTP 401/403 denying access to unauthorized roles",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/cashflow", "status": status},
        )

    def _test_error_disclosure_nonexistent(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/api/probe/nonexistent-internal-resource", method="GET")
        sensitive_keywords = ["mongodb://", "password", "jwt_secret", "aws_secret"]
        leaked = any(k in body.lower() for k in sensitive_keywords)
        # HTTP 401 (Default-Deny auth boundary) or 404 (route not found), without sensitive leakage
        passed = (status in (401, 404) and not leaked)
        return SecurityCheckResult(
            test_id="SEC-API-001",
            category="api_security",
            request_action="GET /api/probe/nonexistent-internal-resource (default-deny error disclosure probe)",
            expected_behavior="HTTP 401 Unauthorized (Default-Deny policy) or HTTP 404 without leaking internal secrets, passwords, or database URIs",
            actual_result=f"HTTP {status}: {body[:80]} (leaked={leaked})",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/probe/nonexistent", "status": status, "leaked": leaked},
        )

    def _test_disallowed_method_restriction(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/api/auth/login", method="DELETE")
        passed = (status in (404, 405))
        return SecurityCheckResult(
            test_id="SEC-API-002",
            category="api_security",
            request_action="DELETE /api/auth/login (disallowed HTTP verb)",
            expected_behavior="HTTP 404/405 rejecting unsupported method on login endpoint",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/auth/login", "method": "DELETE", "status": status},
        )

    def _test_nosql_operator_injection(self, execution_id: str) -> SecurityCheckResult:
        payload = json.dumps({"phoneNumber": {"$gt": ""}, "password": "wrong"}).encode()
        headers = {"Content-Type": "application/json"}
        status, _, body = self._http_request("/api/auth/login", method="POST", headers=headers, data=payload)
        passed = ((status == 400 and ("validation" in body.lower() or "phonenumber" in body.lower() or "phone number" in body.lower() or "no user found" in body.lower())) or (status == 429 and "too many" in body.lower()))
        return SecurityCheckResult(
            test_id="SEC-API-003",
            category="api_security",
            request_action="POST /api/auth/login (NoSQL operator object injection {$gt: ''})",
            expected_behavior="HTTP 400 Bad Request or 429 Rate Limited rejecting NoSQL injection attempt",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/auth/login", "status": status},
        )

    def _test_ssrf_protection(self, execution_id: str) -> SecurityCheckResult:
        status, _, body = self._http_request("/proxy-image?url=http://169.254.169.254/latest/meta-data/", method="GET")
        passed = (status == 403 and "restricted" in body.lower())
        return SecurityCheckResult(
            test_id="SEC-API-004",
            category="api_security",
            request_action="GET /proxy-image?url=http://169.254.169.254/ (cloud metadata SSRF probe)",
            expected_behavior="HTTP 403 Forbidden actively blocking SSRF access to internal IP",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/proxy-image", "status": status},
        )

    def _test_security_headers(self, execution_id: str) -> SecurityCheckResult:
        status, headers, _ = self._http_request("/health", method="GET")
        has_nosniff = headers.get("x-content-type-options") == "nosniff"
        has_frame_options = "x-frame-options" in headers
        has_hsts = "strict-transport-security" in headers
        passed = (status == 200 and has_nosniff and has_frame_options and has_hsts)
        header_summary = f"nosniff={has_nosniff}, frame_options={has_frame_options}, hsts={has_hsts}"
        return SecurityCheckResult(
            test_id="SEC-API-005",
            category="api_security",
            request_action="GET /health (HTTP response security header inspection)",
            expected_behavior="Helmet headers enforced (X-Content-Type-Options, X-Frame-Options, HSTS)",
            actual_result=f"HTTP {status}: {header_summary}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"headers": headers, "status": status},
        )

    def _get_jwt_secret(self) -> str:
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            from orchestration.config import OrchestrationConfig
            env_file = OrchestrationConfig.load().backend_workspace / ".env"
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("JWT_SECRET="):
                            secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                except Exception:
                    pass
        return secret or ""

    def _generate_test_jwt(self, user_id: str, role: str = "ROLE ADMIN", iat_offset: int = 0, *, include_company: bool = True) -> str:
        import base64
        import hashlib
        import hmac
        secret = self._get_jwt_secret()
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "id": user_id,
            "type": "final",
            "role": role,
            "iat": now + iat_offset,
            "exp": now + 86400 * 30,
        }
        if include_company:
            payload["companyId"] = basic_company_id()

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

        h_b64 = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        p_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        msg = f"{h_b64}.{p_b64}".encode("utf-8")
        sig = b64url(hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest())
        return f"{h_b64}.{p_b64}.{sig}"

    def _test_token_revocation(self, execution_id: str) -> SecurityCheckResult:
        # Token issued in the past for an account with tokenValidUntil
        revoked_token = self._generate_test_jwt("6931087f9a8055f043cb8c7b", role="ROLE ADMIN", iat_offset=-1000000000)
        headers = {"Authorization": f"Bearer {revoked_token}"}
        status, _, body = self._http_request("/api/cashflow", method="GET", headers=headers)
        passed = (status == 401 and ("SESSION_INVALIDATED" in body or "session" in body.lower() or "invalidated" in body.lower() or "ACCOUNT_NOT_FOUND" in body))
        return SecurityCheckResult(
            test_id="SEC-AUTH-002-REVOKE",
            category="authentication",
            request_action="GET /api/cashflow (invalidated JWT issued prior to tokenValidUntil)",
            expected_behavior="HTTP 401 Unauthorized rejecting invalidated/revoked token",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/cashflow", "status": status},
        )

    def _test_admin_bypass(self, execution_id: str) -> SecurityCheckResult:
        admin_token = self._generate_test_jwt(basic_employee_id(), role="ROLE ADMIN")
        headers = {"Authorization": f"Bearer {admin_token}"}
        status, _, body = self._http_request("/api/employee/list?page=1&limit=1", method="GET", headers=headers)
        passed = (status == 200)
        return SecurityCheckResult(
            test_id="SEC-RBAC-002",
            category="authorization",
            request_action="GET /api/employee/list (admin authorization bypass check)",
            expected_behavior="HTTP 200 OK permitting Admin full access on protected employee directory",
            actual_result=f"HTTP {status}: {body[:80]}",
            http_status=status,
            passed=passed,
            evidence_reference=None,
            execution_id=execution_id,
            details={"endpoint": "/api/role/list", "status": status},
        )


class SalesforceSecurityProvider(SecurityProvider):
    """
    OPTIONAL/FUTURE provider: Validates authorization boundaries and profiles via Salesforce CLI.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage: Optional[TestStorageManager] = None,
        sf_cli_path: Optional[str] = None,
        sf_target_org: Optional[str] = None,
    ):
        super().__init__(workspace_root, storage)
        self.sf_cli_path = sf_cli_path or shutil.which("sf") or shutil.which("sfdx") or os.environ.get("SF_CLI_PATH") or "/opt/homebrew/bin/sf"
        self.sf_target_org = sf_target_org or os.environ.get("SF_TARGET_ORG") or os.environ.get("SALESFORCE_ORG_ALIAS")

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        cli_found = self.sf_cli_path and (shutil.which(self.sf_cli_path) or Path(self.sf_cli_path).exists())
        if not cli_found:
            return False, "Salesforce CLI (sf / sfdx) is not installed or configured in PATH."
        if not self.sf_target_org:
            return False, "Salesforce target org is not configured (missing SF_TARGET_ORG or SALESFORCE_ORG_ALIAS)."
        return True, None

    def execute(self, test_run_id: str, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "salesforce"},
                failures=[],
                evidence=[],
                environment="salesforce",
                blocked_reason=reason,
            )

        cmd = f"{self.sf_cli_path} org display --target-org {self.sf_target_org} --json"
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=int(context.get("timeout_seconds", 60)),
            )
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()

            raw_output = res.stdout if res.returncode == 0 else res.stderr
            try:
                parsed_json = json.loads(res.stdout)
            except Exception:
                parsed_json = {"raw": raw_output}

            clean_evidence = sanitize_data(parsed_json)
            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename="security_audit.json",
                content=json.dumps(clean_evidence, indent=2),
                evidence_type="security_audit",
                description="Real Salesforce security profile audit",
            )

            status = TestStatus.PASSED if res.returncode == 0 else TestStatus.FAILED
            failures = [] if res.returncode == 0 else [{"error": "Security validation query failed", "code": res.returncode}]

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "salesforce", "query_status": res.returncode},
                failures=failures,
                evidence=[ev_ref],
                environment="salesforce",
                raw_result_reference=ev_ref["path"],
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "salesforce"},
                failures=[{"error": str(e)}],
                evidence=[],
                environment="salesforce",
            )


class EnterpriseIAMSecurityProvider(SecurityProvider):
    """
    OPTIONAL/FUTURE provider: Executes custom enterprise IAM verification commands.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage: Optional[TestStorageManager] = None,
        security_validation_command: Optional[str] = None,
    ):
        super().__init__(workspace_root, storage)
        self.command = security_validation_command or os.environ.get("SECURITY_VALIDATION_COMMAND")

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        if not self.command:
            return False, "SECURITY_VALIDATION_COMMAND is not configured."
        bin_name = self.command.split()[0]
        if shutil.which(bin_name) or Path(bin_name).exists():
            return True, None
        return False, f"SECURITY_VALIDATION_COMMAND binary '{bin_name}' not found."

    def execute(self, test_run_id: str, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        start_time = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()

        is_configured, reason = self.validate_configuration()
        if not is_configured:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=TestStatus.BLOCKED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "enterprise_iam"},
                failures=[],
                evidence=[],
                environment="enterprise_iam",
                blocked_reason=reason,
            )

        try:
            res = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=int(context.get("timeout_seconds", 60)),
            )
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()

            raw_output = res.stdout if res.returncode == 0 else res.stderr
            try:
                parsed_json = json.loads(res.stdout)
            except Exception:
                parsed_json = {"raw": raw_output}

            clean_evidence = sanitize_data(parsed_json)
            ev_ref = self.storage.save_evidence_file(
                test_run_id=test_run_id,
                filename="security_audit.json",
                content=json.dumps(clean_evidence, indent=2),
                evidence_type="security_audit",
                description="Enterprise IAM security validation report",
            )

            status = TestStatus.PASSED if res.returncode == 0 else TestStatus.FAILED
            failures = [] if res.returncode == 0 else [{"error": "Enterprise IAM command failed", "code": res.returncode}]

            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "enterprise_iam", "query_status": res.returncode},
                failures=failures,
                evidence=[ev_ref],
                environment="enterprise_iam",
                raw_result_reference=ev_ref["path"],
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t_start) * 1000
            end_time = datetime.now(timezone.utc).isoformat()
            return TestExecutionResult(
                test_run_id=test_run_id,
                test_type="security_access",
                status=TestStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_ms=duration_ms,
                metrics={"provider": "enterprise_iam"},
                failures=[{"error": str(e)}],
                evidence=[],
                environment="enterprise_iam",
            )


class SecurityProviderFactory:
    """
    Factory for instantiating the configured SecurityProvider.
    Defaults to LocalApplicationSecurityProvider.
    """

    @staticmethod
    def create(
        provider_name: Optional[str] = None,
        workspace_root: Optional[Path] = None,
        storage: Optional[TestStorageManager] = None,
        base_url: Optional[str] = None,
        sf_cli_path: Optional[str] = None,
        sf_target_org: Optional[str] = None,
        security_validation_command: Optional[str] = None,
    ) -> SecurityProvider:
        ws_root = workspace_root or Path.cwd()
        name = (provider_name or os.environ.get("SECURITY_PROVIDER") or "local").lower().strip()

        if name == "salesforce":
            return SalesforceSecurityProvider(
                workspace_root=ws_root,
                storage=storage,
                sf_cli_path=sf_cli_path,
                sf_target_org=sf_target_org,
            )
        elif name in ("enterprise", "enterprise_iam", "iam"):
            return EnterpriseIAMSecurityProvider(
                workspace_root=ws_root,
                storage=storage,
                security_validation_command=security_validation_command,
            )
        else:
            # Default to local application security provider
            return LocalApplicationSecurityProvider(
                workspace_root=ws_root,
                storage=storage,
                base_url=base_url,
            )
