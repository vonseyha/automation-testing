"""
Review Result Normalizer and Structured Parser.
Per Section 7 and Section 11:
Parses raw LLM responses into typed ReviewResult and TestFailureAnalysis objects.
"""

import re
from typing import List, Optional

from orchestration.core_types import (
    ReviewDecision,
    ReviewResult,
    ReviewerStatus,
    TestFailureAnalysis,
)


class ReviewNormalizer:
    """
    Parses and validates reviewer output text into structured ReviewResult objects.
    """

    @classmethod
    def parse_review(cls, text: str, reviewer_model: str = "gemini-3.1-pro-preview", iteration: int = 1) -> ReviewResult:
        if not text or not text.strip():
            return ReviewResult(
                decision=ReviewDecision.REJECT,
                architecture_assessment="Empty response from reviewer.",
                critical_findings=["Reviewer returned an empty response."],
                raw_response=text,
                reviewer_status=ReviewerStatus.COMPLETED,
                reviewer_model=reviewer_model,
                iteration=iteration,
            )

        # 1. Parse Decision
        decision_match = re.search(r"Decision:\s*([A-Z_\s]+)", text, re.IGNORECASE)
        decision = ReviewDecision.APPROVE_WITH_CHANGES
        if decision_match:
            raw_decision = decision_match.group(1).strip().upper()
            if "APPROVE WITH CHANGES" in raw_decision:
                decision = ReviewDecision.APPROVE_WITH_CHANGES
            elif "APPROVE" in raw_decision and "CHANGES" not in raw_decision and "NOT" not in raw_decision:
                decision = ReviewDecision.APPROVE
            elif "REJECT" in raw_decision:
                decision = ReviewDecision.REJECT

        # 2. Extract sections using regex
        arch_assessment = cls._extract_section(text, r"Architecture Assessment:\s*([\s\S]*?)(?=(?:Critical Findings:|High-Risk Issues:|Recommended Changes:|Optional Improvements:|Testing Requirements:|Reasoning Summary:|$))")
        critical_findings_raw = cls._extract_section(text, r"Critical Findings:\s*([\s\S]*?)(?=(?:High-Risk Issues:|Recommended Changes:|Optional Improvements:|Testing Requirements:|Reasoning Summary:|$))")
        high_risk_raw = cls._extract_section(text, r"High-Risk Issues:\s*([\s\S]*?)(?=(?:Recommended Changes:|Optional Improvements:|Testing Requirements:|Reasoning Summary:|$))")
        rec_changes_raw = cls._extract_section(text, r"Recommended Changes:\s*([\s\S]*?)(?=(?:Optional Improvements:|Testing Requirements:|Reasoning Summary:|$))")
        optional_improvements_raw = cls._extract_section(text, r"Optional Improvements:\s*([\s\S]*?)(?=(?:Testing Requirements:|Reasoning Summary:|$))")
        testing_reqs_raw = cls._extract_section(text, r"Testing Requirements:\s*([\s\S]*?)(?=(?:Reasoning Summary:|$))")
        reasoning_summary = cls._extract_section(text, r"Reasoning Summary:\s*([\s\S]*?)$")

        # 3. Categorize changes: Required vs Recommended vs Optional
        required_changes: List[str] = []
        recommended_changes: List[str] = []
        optional_improvements: List[str] = cls._parse_bullet_points(optional_improvements_raw)

        raw_change_bullets = cls._parse_bullet_points(rec_changes_raw)
        for bullet in raw_change_bullets:
            bullet_lower = bullet.lower()
            if bullet_lower.startswith("required:") or "must " in bullet_lower or "[required]" in bullet_lower:
                clean = re.sub(r"^(?:required:|\(?required\)?)\s*", "", bullet, flags=re.IGNORECASE).strip()
                required_changes.append(clean)
            elif bullet_lower.startswith("optional:") or "[optional]" in bullet_lower:
                clean = re.sub(r"^(?:optional:|\(?optional\)?)\s*", "", bullet, flags=re.IGNORECASE).strip()
                optional_improvements.append(clean)
            else:
                clean = re.sub(r"^(?:recommended:|\(?recommended\)?)\s*", "", bullet, flags=re.IGNORECASE).strip()
                recommended_changes.append(clean)

        return ReviewResult(
            decision=decision,
            architecture_assessment=arch_assessment.strip(),
            critical_findings=cls._parse_bullet_points(critical_findings_raw),
            high_risk_issues=cls._parse_bullet_points(high_risk_raw),
            required_changes=required_changes,
            recommended_changes=recommended_changes,
            optional_improvements=optional_improvements,
            testing_requirements=cls._parse_bullet_points(testing_reqs_raw),
            reasoning_summary=reasoning_summary.strip(),
            raw_response=text,
            reviewer_status=ReviewerStatus.COMPLETED,
            reviewer_model=reviewer_model,
            iteration=iteration,
        )

    @classmethod
    def parse_failure_diagnosis(cls, text: str, reviewer_model: str = "gemini-3.1-pro-preview") -> TestFailureAnalysis:
        root_cause = cls._extract_section(text, r"Root Cause Hypothesis:\s*([\s\S]*?)(?=(?:Evidence Needed:|Recommended Fix:|Regression Risk:|Required Validation:|$))")
        evidence_raw = cls._extract_section(text, r"Evidence Needed:\s*([\s\S]*?)(?=(?:Recommended Fix:|Regression Risk:|Required Validation:|$))")
        recommended_fix = cls._extract_section(text, r"Recommended Fix:\s*([\s\S]*?)(?=(?:Regression Risk:|Required Validation:|$))")
        regression_risk = cls._extract_section(text, r"Regression Risk:\s*([\s\S]*?)(?=(?:Required Validation:|$))")
        validation_raw = cls._extract_section(text, r"Required Validation:\s*([\s\S]*?)$")

        return TestFailureAnalysis(
            root_cause_hypothesis=root_cause.strip() or "No distinct root cause identified.",
            evidence_needed=cls._parse_bullet_points(evidence_raw),
            recommended_fix=recommended_fix.strip(),
            regression_risk=regression_risk.strip(),
            required_validation=cls._parse_bullet_points(validation_raw),
            reviewer_model=reviewer_model,
        )

    @staticmethod
    def _extract_section(text: str, pattern: str) -> str:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _parse_bullet_points(text: str) -> List[str]:
        if not text:
            return []
        lines = text.strip().splitlines()
        results: List[str] = []
        for line in lines:
            line = line.strip()
            # Look for bullet points (- or * or numbers)
            match = re.match(r"^(?:[-*•]|\d+\.)\s*(.*)$", line)
            if match:
                content = match.group(1).strip()
                if content and content.lower() not in ("none", "n/a", "none reported"):
                    results.append(content)
            elif line and not line.endswith(":") and len(results) > 0:
                # Continuation of previous bullet point
                results[-1] += f" {line}"
            elif line and line.lower() not in ("none", "n/a", "none reported") and not line.endswith(":"):
                results.append(line)
        return results
