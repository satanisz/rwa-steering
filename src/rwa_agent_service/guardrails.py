from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .discussion_schemas import DiscussionAgentName, GuardrailScanResult

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?:\+|00)\d[\d\s().-]{7,}\d")
_SECRET_PATTERN = re.compile(
    r"\b(?:api[_-]?key|secret|token|password|aws_access_key_id)\s*[:=]\s*[A-Za-z0-9_\-]{8,}",
    re.IGNORECASE,
)
_PROMPT_INJECTION_PATTERN = re.compile(
    r"(ignore (?:all )?(?:previous|prior) instructions|reveal (?:the )?system prompt|"
    r"developer message|jailbreak|do anything now|bypass policy|override guardrails)",
    re.IGNORECASE,
)
_TOXICITY_PATTERN = re.compile(r"\b(hate|kill|terrorist|violent threat)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GuardrailDecision:
    """Decision returned after scanning one agent input or output."""

    sanitized_text: str
    results: list[GuardrailScanResult]

    @property
    def blocked(self) -> bool:
        return any(result.action == "blocked" for result in self.results)


class RwaLlmGuard:
    """LLM Guard adapter with deterministic fallback for Python 3.14 environments."""

    backend_name = "deterministic_llm_guard_compatible"

    def __init__(
        self,
        *,
        block_threshold: Decimal = Decimal("0.85"),
        flag_threshold: Decimal = Decimal("0.50"),
    ) -> None:
        self._block_threshold = block_threshold
        self._flag_threshold = flag_threshold
        self._scan_prompt: Any | None = None
        self._scan_output: Any | None = None
        self._input_scanners: list[Any] = []
        self._output_scanners: list[Any] = []
        self._configure_optional_llm_guard()

    def scan_input(self, text: str, *, agent_name: DiscussionAgentName) -> GuardrailDecision:
        """Scan prompt/context before an agent interaction is allowed to run."""
        return self._scan(text, stage="input", agent_name=agent_name)

    def scan_output(self, text: str, *, agent_name: DiscussionAgentName) -> GuardrailDecision:
        """Scan generated/agent output before writing it back to graph state."""
        return self._scan(text, stage="output", agent_name=agent_name)

    def _scan(
        self,
        text: str,
        *,
        stage: str,
        agent_name: DiscussionAgentName,
    ) -> GuardrailDecision:
        if self._scan_prompt is not None and self._scan_output is not None:
            decision = self._scan_with_optional_llm_guard(text, stage=stage, agent_name=agent_name)
            if decision is not None:
                return decision

        sanitized = text
        results = [
            self._result(
                stage=stage,
                scanner_name="PromptInjection",
                risk_score=Decimal("0.95")
                if _PROMPT_INJECTION_PATTERN.search(text)
                else Decimal("0"),
                finding="Prompt injection pattern detected."
                if _PROMPT_INJECTION_PATTERN.search(text)
                else "No prompt injection pattern detected.",
                agent_name=agent_name,
            ),
            self._result(
                stage=stage,
                scanner_name="PII",
                risk_score=Decimal("0.90")
                if _EMAIL_PATTERN.search(text) or _PHONE_PATTERN.search(text)
                else Decimal("0"),
                finding="PII-like value detected."
                if _EMAIL_PATTERN.search(text) or _PHONE_PATTERN.search(text)
                else "No PII-like value detected.",
                agent_name=agent_name,
            ),
            self._result(
                stage=stage,
                scanner_name="Secrets",
                risk_score=Decimal("0.92") if _SECRET_PATTERN.search(text) else Decimal("0"),
                finding="Secret-like token detected."
                if _SECRET_PATTERN.search(text)
                else "No secret-like token detected.",
                agent_name=agent_name,
            ),
            self._result(
                stage=stage,
                scanner_name="Toxicity",
                risk_score=Decimal("0.70") if _TOXICITY_PATTERN.search(text) else Decimal("0"),
                finding="Unsafe or toxic wording detected."
                if _TOXICITY_PATTERN.search(text)
                else "No unsafe wording detected.",
                agent_name=agent_name,
            ),
        ]
        if any(
            result.scanner_name in {"PII", "Secrets"} and not result.is_valid for result in results
        ):
            sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", sanitized)
            sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
            sanitized = _SECRET_PATTERN.sub("[REDACTED_SECRET]", sanitized)
        return GuardrailDecision(sanitized_text=sanitized, results=results)

    def _configure_optional_llm_guard(self) -> None:
        try:
            from llm_guard import scan_output, scan_prompt
            from llm_guard.input_scanners import PromptInjection, Secrets, Toxicity
            from llm_guard.output_scanners import Sensitive

            self._scan_prompt = scan_prompt
            self._scan_output = scan_output
            self._input_scanners = [
                PromptInjection(threshold=float(self._block_threshold)),
                Secrets(),
                Toxicity(threshold=float(self._flag_threshold)),
            ]
            self._output_scanners = [Sensitive()]
            self.backend_name = "llm_guard"
        except Exception:
            self.backend_name = "deterministic_llm_guard_compatible"

    def _scan_with_optional_llm_guard(
        self,
        text: str,
        *,
        stage: str,
        agent_name: DiscussionAgentName,
    ) -> GuardrailDecision | None:
        scan_prompt = self._scan_prompt
        scan_output = self._scan_output
        if scan_prompt is None or scan_output is None:
            return None
        try:
            if stage == "input":
                sanitized, valid, scores = scan_prompt(self._input_scanners, text)
            else:
                sanitized, valid, scores = scan_output(self._output_scanners, "", text)
        except Exception:
            return None

        results = [
            self._result(
                stage=stage,
                scanner_name=str(name),
                risk_score=Decimal(str(score)),
                finding=f"LLM Guard scanner {name} returned score {score}.",
                agent_name=agent_name,
            )
            for name, score in dict(scores).items()
        ]
        if not bool(valid) and not any(result.action == "blocked" for result in results):
            results.append(
                self._result(
                    stage=stage,
                    scanner_name="LLMGuard",
                    risk_score=self._block_threshold,
                    finding="LLM Guard marked the payload invalid.",
                    agent_name=agent_name,
                )
            )
        return GuardrailDecision(sanitized_text=str(sanitized), results=results)

    def _result(
        self,
        *,
        stage: str,
        scanner_name: str,
        risk_score: Decimal,
        finding: str,
        agent_name: DiscussionAgentName,
    ) -> GuardrailScanResult:
        if risk_score >= self._block_threshold:
            action = "blocked"
        elif risk_score >= self._flag_threshold:
            action = "flagged"
        else:
            action = "passed"
        return GuardrailScanResult(
            stage=stage,
            scanner_name=scanner_name,
            is_valid=action != "blocked",
            risk_score=risk_score,
            action=action,
            finding=finding,
            agent_name=agent_name,
        )


def create_guard() -> RwaLlmGuard:
    """Create the configured LLM Guard compatible scanner."""
    return RwaLlmGuard()
