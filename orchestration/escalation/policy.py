"""
Specialist Escalation Policy and Decision Engine.
Per Section 4, 5, 11, 12, 18:
Evaluates whether a task can continue on Gemini 3.8 Flash High
or must escalate to Gemini 3.1 Pro High.
"""

import re
from typing import Any, Dict, List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.core_types import EscalationDecision, EscalationReason


class EscalationPolicy:
    """
    Determines whether a development, architecture, or test task requires escalation
    from Gemini 3.8 Flash High to Gemini 3.1 Pro High.
    """

    # Signals for tasks that should NOT escalate (simple/routine)
    SIMPLE_SIGNALS = [
        r"\bformat(?:ting)?\b",
        r"\blint(?:ing)?\b",
        r"\btypo\b",
        r"\bsimple crud\b",
        r"\bminor ui\b",
        r"\bminor css\b",
        r"\bcomment(?:s)?\b",
        r"\bdoc(?:umentation)? edit\b",
        r"\broutine test\b",
        r"\bversion bump\b",
        r"\brename variable\b",
    ]

    # Explicit user overrides
    FORCE_PRO_SIGNALS = [
        r"review this architecture",
        r"use the pro reviewer",
        r"deep review",
        r"escalate to pro",
        r"pro review",
        r"require pro",
    ]

    FORCE_FLASH_SIGNALS = [
        r"do not escalate",
        r"skip review",
        r"no review",
        r"flash only",
        r"stay on flash",
    ]

    # Escalation trigger categories
    ARCHITECTURE_SIGNALS = [
        r"\barchitectur(?:e|al)\b",
        r"\bnew subsystem\b",
        r"\bintegration layer\b",
        r"\bdata ownership\b",
        r"\bpersistence strategy\b",
        r"\bagent orchestration\b",
        r"\btest[- ]engine architectur\b",
        r"\brelease[- ]gate\b",
        r"\basynchronous processing\b",
        r"\bdistributed\b",
        r"\bmigration strategy\b",
        r"\bstrangler[- ]fig\b",
        r"\bmonorepo boundary\b",
    ]

    SECURITY_SIGNALS = [
        r"\bauthenticat(?:ion|e)\b",
        r"\bauthoriz(?:ation|e)\b",
        r"\bsecurity[- ]sensitive\b",
        r"\bprompt[- ]injection\b",
        r"\bhmac\b",
        r"\bjwt\b",
        r"\bguardrail\b",
        r"\bdata[- ]access boundar\b",
        r"\bgrounding architectur\b",
        r"\bpenetration\b",
        r"\brbac\b",
        r"\bcsrf\b",
        r"\bxss\b",
        r"\bnosql injection\b",
        r"\bsql injection\b",
    ]

    CRITICAL_BUSINESS_SIGNALS = [
        r"\bfinancial\b",
        r"\baccounting\b",
        r"\bgeneral[- ]ledger\b",
        r"\bcashflow\b",
        r"\breconciliation\b",
        r"\bproduction deployment\b",
        r"\bdata integrity\b",
        r"\bcost calculation\b",
        r"\binvariant\b",
    ]

    COMPLEX_REASONING_SIGNALS = [
        r"\btrade[- ]off\b",
        r"\bambiguous\b",
        r"\bconflicting requirements\b",
        r"\bpersistent bug\b",
        r"\brecurring failure\b",
        r"\bdeep reasoning\b",
        r"\blow confidence\b",
        r"\bcomplex refactor\b",
        r"\bcore service rewrite\b",
    ]

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()

    def evaluate(
        self,
        task_description: str,
        changed_files: Optional[List[str]] = None,
        test_failures: Optional[List[Dict[str, Any]]] = None,
        failure_attempts: int = 0,
        user_prompt_override: Optional[str] = None,
    ) -> EscalationDecision:
        """
        Runs the 7-question escalation evaluation per Section 5.
        """
        changed_files = changed_files or []
        test_failures = test_failures or []
        combined_text = f"{task_description} {user_prompt_override or ''}".lower()

        # Check if review is globally disabled
        if not self.config.review_enabled:
            return EscalationDecision(
                should_escalate=False,
                reasons=[],
                explanation="Review disabled in configuration (REVIEW_ENABLED=false).",
                task_complexity="NORMAL",
            )

        # 1. Check explicit user overrides (Section 18)
        for pattern in self.FORCE_FLASH_SIGNALS:
            if re.search(pattern, combined_text):
                return EscalationDecision(
                    should_escalate=False,
                    reasons=[],
                    explanation="User explicitly requested no escalation ('do not escalate' / 'flash only').",
                    user_override="FORCE_FLASH",
                    task_complexity="NORMAL",
                )

        for pattern in self.FORCE_PRO_SIGNALS:
            if re.search(pattern, combined_text):
                return EscalationDecision(
                    should_escalate=True,
                    reasons=[EscalationReason.USER_EXPLICIT],
                    explanation="User explicitly requested Pro Reviewer escalation.",
                    user_override="FORCE_PRO",
                    task_complexity="COMPLEX",
                )

        # 2. Check if task is explicitly simple/routine
        is_simple = any(re.search(pat, combined_text) for pat in self.SIMPLE_SIGNALS)
        if is_simple and len(changed_files) <= 1 and failure_attempts == 0 and not test_failures:
            return EscalationDecision(
                should_escalate=False,
                reasons=[],
                explanation="Routine task (formatting, simple CRUD, minor UI, or docs). Flash continues.",
                task_complexity="NORMAL",
            )

        reasons: List[EscalationReason] = []
        explanations: List[str] = []

        # 3. Architecture review check
        if self.config.review_on_architecture_change:
            if any(re.search(pat, combined_text) for pat in self.ARCHITECTURE_SIGNALS):
                reasons.append(EscalationReason.ARCHITECTURE_REVIEW)
                explanations.append("Architecturally significant change or system boundary modification.")

        # 4. Security & critical review check
        if self.config.review_on_security_change:
            if any(re.search(pat, combined_text) for pat in self.SECURITY_SIGNALS):
                reasons.append(EscalationReason.AI_SECURITY if "prompt" in combined_text or "grounding" in combined_text else EscalationReason.CRITICAL_REVIEW)
                explanations.append("Security-sensitive, authentication, or AI safety/grounding change.")

        # 5. Critical business rules / financial check
        if any(re.search(pat, combined_text) for pat in self.CRITICAL_BUSINESS_SIGNALS):
            reasons.append(EscalationReason.CRITICAL_REVIEW)
            explanations.append("Core financial, ledger reconciliation, or business invariant logic.")

        # 6. Complex reasoning / ambiguous trade-offs
        if any(re.search(pat, combined_text) for pat in self.COMPLEX_REASONING_SIGNALS):
            reasons.append(EscalationReason.COMPLEX_REASONING)
            explanations.append("Complex reasoning, trade-off analysis, or ambiguous requirement.")

        # 7. Multi-file code review / core service modification
        if len(changed_files) >= 4:
            reasons.append(EscalationReason.CODE_REVIEW)
            explanations.append(f"Multi-file change affecting {len(changed_files)} files across components.")

        # 8. Test failures escalation (Section 11)
        if test_failures:
            has_security_failure = any(
                f.get("pillar") in ("Security & Access", "Penetration Check") for f in test_failures
            )
            has_critical_failure = any(
                f.get("critical", False) or f.get("pillar") in ("API & Integration",) for f in test_failures
            )

            if has_security_failure and self.config.review_on_security_change:
                reasons.append(EscalationReason.CRITICAL_REVIEW)
                explanations.append("Security or penetration test failure encountered.")
            elif has_critical_failure and self.config.review_on_critical_failure:
                reasons.append(EscalationReason.TEST_FAILURE)
                explanations.append("Critical integration test failure with cross-component impact.")
            elif failure_attempts >= 2 and self.config.review_on_persistent_failure:
                reasons.append(EscalationReason.TEST_FAILURE)
                explanations.append(f"Persistent test failure unresolved after {failure_attempts} attempts.")

        # Decision synthesis
        if reasons:
            # Deduplicate reasons while preserving order
            unique_reasons = list(dict.fromkeys(reasons))
            return EscalationDecision(
                should_escalate=True,
                reasons=unique_reasons,
                explanation="; ".join(explanations),
                task_complexity="COMPLEX",
            )

        return EscalationDecision(
            should_escalate=False,
            reasons=[],
            explanation="Normal complexity task within Gemini 3.8 Flash High autonomous capabilities.",
            task_complexity="NORMAL",
        )
