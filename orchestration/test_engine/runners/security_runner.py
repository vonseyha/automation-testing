"""
Real Security & Access Test Runner with Pluggable Provider Architecture.
Per User Specifications:
Supports:
- LocalApplicationSecurityProvider (DEFAULT: Real HTTP security validation)
- SalesforceSecurityProvider (OPTIONAL/FUTURE)
- EnterpriseIAMSecurityProvider (OPTIONAL/FUTURE)

Provider is selected via configuration (SECURITY_PROVIDER, default: 'local').
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.security.provider import (
    SecurityProvider,
    SecurityProviderFactory,
)
from orchestration.test_engine.storage import TestStorageManager


class SecurityAccessRunner(BaseTestRunner):
    """
    Security & Access runner delegating to the configured SecurityProvider.
    Defaults to LocalApplicationSecurityProvider.
    """

    def __init__(
        self,
        workspace_root: Path,
        storage_manager: Optional[TestStorageManager] = None,
        security_provider: Optional[str] = None,
        base_url: Optional[str] = None,
        sf_cli_path: Optional[str] = None,
        sf_target_org: Optional[str] = None,
        security_validation_command: Optional[str] = None,
    ):
        super().__init__(workspace_root=workspace_root, runner_name="security_access")
        self.storage = storage_manager or TestStorageManager()
        self.security_provider_name = (
            security_provider
            or os.environ.get("SECURITY_PROVIDER")
            or "local"
        ).strip().lower()
        self.base_url = base_url or os.environ.get("SECURITY_BASE_URL") or os.environ.get("API_BASE_URL") or "http://localhost:3000"
        self.sf_cli_path = sf_cli_path
        self.sf_target_org = sf_target_org
        self.security_validation_command = security_validation_command

        self._provider: SecurityProvider = SecurityProviderFactory.create(
            provider_name=self.security_provider_name,
            workspace_root=self.workspace_root,
            storage=self.storage,
            base_url=self.base_url,
            sf_cli_path=self.sf_cli_path,
            sf_target_org=self.sf_target_org,
            security_validation_command=self.security_validation_command,
        )

    @property
    def provider(self) -> SecurityProvider:
        return self._provider

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[Any]:
        return self._provider.discover_test_cases(context=context)

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """Delegates validation to the configured provider."""
        return self._provider.validate_configuration()

    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        context = context or {}
        test_run_id = context.get("test_run_id") or self.storage.generate_run_id("sec")
        return self._provider.execute(test_run_id=test_run_id, context=context)

    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        if isinstance(raw_result, TestExecutionResult):
            return raw_result
        raise NotImplementedError()

