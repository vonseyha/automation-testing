"""
Unit tests for Review Contract Builder and Output Normalizer.
Per Section 6, 7, 11.
"""

import unittest

from orchestration.review.contract import ReviewContractBuilder
from orchestration.review.normalizer import ReviewNormalizer
from orchestration.core_types import ReviewDecision, ReviewRequest


class TestContractAndNormalizer(unittest.TestCase):
    def test_build_review_prompt_redacts_secrets(self):
        req = ReviewRequest(
            user_requirement="Connect to backend with api_key: 'AIzaSyD123456789012345678901234567890123'",
            relevant_architecture="Turborepo Monorepo",
            changed_files=["api.ts"],
            relevant_code="const secret = 'default_hmac_secret_for_dev';",
        )
        prompt = ReviewContractBuilder.build_review_prompt(req)
        self.assertNotIn("AIzaSy", prompt)
        self.assertIn("[REDACTED_GEMINI_API_KEY]", prompt)
        self.assertIn("Turborepo Monorepo", prompt)
        self.assertIn("api.ts", prompt)

    def test_parse_structured_review_result(self):
        raw_text = """REVIEW RESULT

Decision:
APPROVE WITH CHANGES

Architecture Assessment:
The architecture is modular and adheres to strangler-fig migration patterns.

Critical Findings:
- None

High-Risk Issues:
- Unbounded collection search in legacy API.

Recommended Changes:
- Required: Add .limit(150) to MongoDB cursor.
- Required: Filter out voided records using IsVoided: { $ne: true }.
- Recommended: Memoize query results in Redis.
- Optional: Add extra logging for audit.

Testing Requirements:
- Run Performance test suite to verify memory limit.
- Run Security test suite.

Reasoning Summary:
Applying required query bounds ensures heap safety under 1M records load.
"""
        result = ReviewNormalizer.parse_review(raw_text, reviewer_model="gemini-3.1-pro-preview", iteration=1)
        self.assertEqual(result.decision, ReviewDecision.APPROVE_WITH_CHANGES)
        self.assertEqual(result.reviewer_model, "gemini-3.1-pro-preview")
        self.assertIn("strangler-fig", result.architecture_assessment)
        self.assertEqual(len(result.critical_findings), 0)
        self.assertEqual(len(result.high_risk_issues), 1)
        self.assertEqual(len(result.required_changes), 2)
        self.assertIn("Add .limit(150) to MongoDB cursor.", result.required_changes)
        self.assertIn("Filter out voided records using IsVoided: { $ne: true }.", result.required_changes)
        self.assertEqual(len(result.recommended_changes), 1)
        self.assertIn("Memoize query results in Redis.", result.recommended_changes)
        self.assertEqual(len(result.optional_improvements), 1)
        self.assertIn("Add extra logging for audit.", result.optional_improvements)
        self.assertEqual(len(result.testing_requirements), 2)

    def test_parse_failure_diagnosis(self):
        raw_text = """FAILURE DIAGNOSIS

Root Cause Hypothesis:
The MongoDB aggregation pipeline encounters an unhandled null when user reference is missing in legacy buyers.

Evidence Needed:
- Controller stack trace from /api/cashflow
- Null record ID in database

Recommended Fix:
Use $ifNull or batch fallback query against users collection.

Regression Risk:
Minimal risk to existing reports; resolves null pointer exception.

Required Validation:
- Execute car-sale-report revenue integration test with unpopulated buyer ID.
"""
        diag = ReviewNormalizer.parse_failure_diagnosis(raw_text, reviewer_model="gemini-3.1-pro-preview")
        self.assertIn("MongoDB aggregation pipeline encounters an unhandled null", diag.root_cause_hypothesis)
        self.assertEqual(len(diag.evidence_needed), 2)
        self.assertIn("Use $ifNull or batch fallback", diag.recommended_fix)
        self.assertIn("Minimal risk", diag.regression_risk)
        self.assertEqual(len(diag.required_validation), 1)


if __name__ == "__main__":
    unittest.main()
