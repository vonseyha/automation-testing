"""
Common Execution Interface and Result Contract for Real Test Engine.
Per Section 6:
Every runner must implement validate_configuration, execute, and normalize_result,
returning a consistent, un-faked result structure.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class TestStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


@dataclass
class TestCaseResult:
    """
    Structured identity and accounting record for an individual executable test case.
    Per Requirement 1 & Sections 4, 6, 7, 9.
    """
    test_case_id: str
    test_name: str
    test_pillar: str
    description: str
    execution_status: TestStatus
    started_at: str
    completed_at: str
    duration_ms: float
    error: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    execution_id: str = ""
    details: Optional[str] = None
    failure_reason: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    required_action: Optional[str] = None
    blocking_dependency: Optional[str] = None
    missing_configuration: Optional[str] = None
    exact_missing_configuration: Optional[str] = None
    exact_missing_config: Optional[str] = None
    required_remediation: Optional[str] = None
    runner: str = ""
    feature_id: str = ""
    module: str = ""
    test_type: str = ""
    priority: str = "P1"
    preconditions: str = ""
    steps: List[str] = field(default_factory=list)
    expected_result: Optional[str] = None
    lifecycle_status: str = "DISCOVERED"

    def __post_init__(self):
        if not self.expected_result and self.expected:
            self.expected_result = self.expected
        if not self.expected and self.expected_result:
            self.expected = self.expected_result
        if isinstance(self.execution_status, str):
            try:
                self.execution_status = TestStatus(self.execution_status.upper())
            except ValueError:
                self.execution_status = TestStatus.PENDING
        missing = self.exact_missing_configuration or self.exact_missing_config or self.missing_configuration
        self.missing_configuration = missing
        self.exact_missing_configuration = missing
        self.exact_missing_config = missing

        if self.evidence:
            normalized_ev = []
            for ev in self.evidence:
                if isinstance(ev, str):
                    normalized_ev.append({"path": ev, "uri": f"file://{ev}", "filename": Path(ev).name})
                elif isinstance(ev, dict):
                    normalized_ev.append(ev)
            self.evidence = normalized_ev

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        status_val = self.execution_status.value if hasattr(self.execution_status, "value") else str(self.execution_status)
        d["execution_status"] = status_val
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCaseResult":
        valid_fields = {f.name for f in fields(cls)}
        clean_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean_data)


@dataclass
class TestExecutionResult:
    """
    Standardized, un-faked execution result for any test runner.
    Per Section 6:
    Contains runner summary metrics, failure details, evidence artifacts,
    and granular individual test case results.
    """
    test_run_id: str
    test_type: str
    status: TestStatus
    started_at: str
    completed_at: str
    duration_ms: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    environment: str = "local"
    raw_result_reference: Optional[str] = None
    blocked_reason: Optional[str] = None
    test_cases: List[TestCaseResult] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.status, str):
            try:
                self.status = TestStatus(self.status.upper())
            except ValueError:
                self.status = TestStatus.PENDING
        if self.test_cases:
            self.test_cases = [
                TestCaseResult.from_dict(tc) if isinstance(tc, dict) else tc
                for tc in self.test_cases
            ]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        status_val = self.status.value if hasattr(self.status, "value") else str(self.status)
        d["status"] = status_val
        d["test_cases"] = [tc.to_dict() if hasattr(tc, "to_dict") else tc for tc in self.test_cases]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestExecutionResult":
        valid_fields = {f.name for f in fields(cls)}
        clean_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean_data)


class BaseTestRunner(ABC):
    """
    Abstract base runner that all 6 pillars must inherit from.
    """

    def __init__(self, workspace_root: Path, runner_name: str):
        self.workspace_root = workspace_root
        self.runner_name = runner_name

    def discover_test_cases(self, context: Optional[Dict[str, Any]] = None) -> List[TestCaseResult]:
        """
        Discovers all available executable test cases for this runner before execution.
        Subclasses should override this to return genuine discoverable test cases.
        """
        return []

    @abstractmethod
    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """
        Validates if the external tool/engine is installed and configured.
        Returns:
            (True, None) if ready to execute.
            (False, "reason why unavailable") if blocked.
        """
        pass

    @abstractmethod
    def execute(self, context: Optional[Dict[str, Any]] = None) -> TestExecutionResult:
        """
        Triggers real execution against the target environment or tool.
        Must NOT fake results. If validate_configuration is False, returns BLOCKED.
        """
        pass

    @abstractmethod
    def normalize_result(self, raw_result: Any) -> TestExecutionResult:
        """
        Converts the raw output/logs into a normalized TestExecutionResult.
        """
        pass

