"""
Mock Specialist Client for Deterministic Testing and Simulation.
"""

from typing import Callable, Optional

from orchestration.models.base import BaseModelClient


class MockSpecialistClient(BaseModelClient):
    """
    Mock specialist reviewer model client for automated testing and deterministic validation.
    """

    def __init__(
        self,
        model_id: str = "gemini-3.1-pro-preview",
        thinking_level: str = "high",
        custom_response_generator: Optional[Callable[[str], str]] = None,
        is_available_flag: bool = True,
        unavailability_reason: Optional[str] = None,
    ):
        super().__init__(model_id=model_id, thinking_level=thinking_level)
        self.custom_response_generator = custom_response_generator
        self._is_available = is_available_flag
        self._unavailability_reason = unavailability_reason
        self.call_history = []

    def is_available(self) -> bool:
        return self._is_available

    def get_unavailability_reason(self) -> Optional[str]:
        return self._unavailability_reason

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.call_history.append({"prompt": prompt, "system_instruction": system_instruction})
        if self.custom_response_generator:
            return self.custom_response_generator(prompt)

        # Standard default mock review response complying with Section 7
        if "FAILURE DIAGNOSIS" in (system_instruction or "") or "TEST FAILURE" in prompt:
            return """FAILURE DIAGNOSIS

Root Cause Hypothesis:
Unbounded query in legacy controller without index causes memory spike and socket timeout under concurrent load.

Evidence Needed:
- MongoDB query profile logs showing COLLSCAN
- Heap memory profile during 100 concurrent requests

Recommended Fix:
Add compound index on { IsVoided: 1, TxDate: -1 } and ensure .limit(150) is pushed down to query engine.

Regression Risk:
Low risk; index addition does not alter query return semantics.

Required Validation:
- Run Performance test suite to verify response time stays under 200ms.
- Run Security test suite to verify IsVoided filter cannot be bypassed.
"""

        return """REVIEW RESULT

Decision:
APPROVE WITH CHANGES

Architecture Assessment:
The architecture appropriately isolates legacy Express endpoints from the modern Turborepo cluster. The contract bridging preserves strict typing across monorepo packages.

Critical Findings:
- None

High-Risk Issues:
- Potential unhandled null reference when buyer details are not fully populated in legacy sale records.

Recommended Changes:
- Required: Enforce IsVoided: { $ne: true } on all financial aggregation pipelines to prevent voided transactions from corrupting cash balance.
- Required: Enforce .limit(150) on all in-stock car list endpoints to prevent Node.js heap exhaustion.
- Recommended: Batch related collections using Mongoose $in lookup rather than single sequential roundtrips.
- Optional: Add memoized caching layer in Redis for static brand and model mappings.

Testing Requirements:
- Verify parity between legacy and cluster cashflow balance calculation.
- Run penetration test with voided transaction payload.

Reasoning Summary:
Changes are sound and align with strangler-fig migration guidelines. Applying required query bounds and voided filters guarantees data integrity and memory safety.
"""
