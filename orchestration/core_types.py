"""
Core types and data structures for Master Agent + Specialist Reviewer Orchestration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ThinkingLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EscalationReason(str, Enum):
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    COMPLEX_REASONING = "COMPLEX_REASONING"
    CRITICAL_REVIEW = "CRITICAL_REVIEW"
    CODE_REVIEW = "CODE_REVIEW"
    TEST_FAILURE = "TEST_FAILURE"
    AI_SECURITY = "AI_SECURITY"
    USER_EXPLICIT = "USER_EXPLICIT"


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CHANGES = "APPROVE WITH CHANGES"
    REJECT = "REJECT"
    UNAVAILABLE = "UNAVAILABLE"


class ReviewerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"


class TestPillar(str, Enum):
    UI_CHANNEL = "UI & Channel"
    API_INTEGRATION = "API & Integration"
    PERFORMANCE = "Performance"
    SECURITY_ACCESS = "Security & Access"
    PENETRATION = "Penetration Check"
    AI_GROUNDING = "AI Grounding"


@dataclass
class EscalationDecision:
    should_escalate: bool
    reasons: List[EscalationReason] = field(default_factory=list)
    explanation: str = ""
    user_override: Optional[str] = None
    task_complexity: str = "NORMAL"  # NORMAL or COMPLEX


@dataclass
class ReviewRequest:
    user_requirement: str
    relevant_architecture: str = ""
    current_implementation: str = ""
    changed_files: List[str] = field(default_factory=list)
    relevant_code: str = ""
    existing_constraints: List[str] = field(default_factory=list)
    test_results: Dict[str, Any] = field(default_factory=dict)
    known_failures: List[str] = field(default_factory=list)
    design_alternatives_considered: List[str] = field(default_factory=list)
    specific_question: str = "Please review this architectural and code change according to the specialist contract."


@dataclass
class ReviewResult:
    decision: ReviewDecision
    architecture_assessment: str = ""
    critical_findings: List[str] = field(default_factory=list)
    high_risk_issues: List[str] = field(default_factory=list)
    required_changes: List[str] = field(default_factory=list)
    recommended_changes: List[str] = field(default_factory=list)
    optional_improvements: List[str] = field(default_factory=list)
    testing_requirements: List[str] = field(default_factory=list)
    reasoning_summary: str = ""
    raw_response: str = ""
    reviewer_status: ReviewerStatus = ReviewerStatus.COMPLETED
    reviewer_model: str = "gemini-3.1-pro-preview"
    iteration: int = 1
    unavailability_reason: Optional[str] = None
    fallback_strategy: Optional[str] = None


@dataclass
class TestFailureAnalysis:
    root_cause_hypothesis: str
    evidence_needed: List[str] = field(default_factory=list)
    recommended_fix: str = ""
    regression_risk: str = ""
    required_validation: List[str] = field(default_factory=list)
    reviewer_model: str = "gemini-3.1-pro-preview"


@dataclass
class TestResult:
    pillar: TestPillar
    suite_name: str
    test_name: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class PillarSummary:
    pillar: TestPillar
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    blocked_tests: int = 0
    skipped_tests: int = 0
    pending_tests: int = 0
    executed_tests: int = 0
    duration_ms: float = 0.0
    results: List[TestResult] = field(default_factory=list)
    test_cases: List[Any] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.failed_tests == 0 and self.blocked_tests == 0 and self.passed_tests > 0


@dataclass
class ReleaseScorecard:
    overall_passed: bool
    pillar_summaries: Dict[TestPillar, PillarSummary] = field(default_factory=dict)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    blocked_tests: int = 0
    skipped_tests: int = 0
    pending_tests: int = 0
    executed_tests: int = 0
    release_ready: bool = False
    timestamp: str = ""
    summary: str = ""
    test_run_summary: Optional[Any] = None
    dashboard_markdown: str = ""



@dataclass
class AuditRecord:
    timestamp: str
    task: str
    primary_model: str
    review_requested: bool
    review_reason: str
    reviewer_model: str
    reviewer_decision: str
    changes_applied: List[str]
    tests_executed: List[str]
    final_outcome: str
    iteration_count: int = 1
