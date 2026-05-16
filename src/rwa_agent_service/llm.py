from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import httpx
from pydantic import ValidationError

from .config import AgentServiceSettings
from .prompts import build_commentary_prompt
from .schemas import AgentResult, BoardCommentary, LlmProvider, MetricFact


class BriefingLanguageModel(ABC):
    """Interface for commentary generation over completed agent outputs."""

    provider: LlmProvider

    @abstractmethod
    def generate_board_commentary(
        self,
        *,
        agent_results: list[AgentResult],
        metric_facts: list[MetricFact],
        limitations: list[str],
    ) -> BoardCommentary:
        """Generate structured board commentary from agent findings."""


class DeterministicBriefingModel(BriefingLanguageModel):
    """Deterministic renderer used only for explicit tests and offline diagnostics."""

    provider: LlmProvider = "deterministic"

    def generate_board_commentary(
        self,
        *,
        agent_results: list[AgentResult],
        metric_facts: list[MetricFact],
        limitations: list[str],
    ) -> BoardCommentary:
        """Render commentary directly from typed facts without inventing values."""
        facts = {fact.name: fact for fact in metric_facts if fact.model is None}
        total_rwa = _money(facts.get("applicable_total_rwa"))
        cet1 = _ratio(facts.get("cet1_ratio"))
        leverage = _ratio(facts.get("leverage_ratio"))
        quality = _value(facts.get("data_quality_findings"), default="0")
        movement = _agent(agent_results, "RWA Movement Agent")
        capital = _agent(agent_results, "Capital Stack Agent")
        quality_agent = _agent(agent_results, "Data Quality Agent")
        evidence = _agent(agent_results, "Evidence Pack Agent")
        source_names = [result.agent_name for result in agent_results]

        risk_watchlist = [
            finding.summary
            for result in agent_results
            for finding in result.findings
            if finding.severity in {"WATCH", "MATERIAL", "CRITICAL"}
        ][:5]
        if not risk_watchlist:
            risk_watchlist = ["No material agent watch items were identified in calculated data."]

        return BoardCommentary(
            executive_summary=(
                f"Applicable total RWA is {total_rwa}; CET1 ratio is {cet1} and leverage "
                f"ratio is {leverage}. The briefing is based on calculated model outputs, "
                "prepared input files and validation evidence."
            ),
            key_messages=[
                movement.summary,
                capital.summary,
                quality_agent.summary,
                evidence.summary,
            ],
            risk_watchlist=risk_watchlist,
            recommended_actions=[
                "Review the largest model RWA movements before management sign-off.",
                f"Clear or accept {quality} data-quality findings through the evidence workflow.",
                "Retain manifest hashes and model run evidence with the reporting pack.",
            ],
            limitations=limitations,
            source_agent_names=source_names,
        )


class OllamaBriefingModel(BriefingLanguageModel):
    """Ollama-backed Gemma commentary generator with strict JSON output parsing."""

    provider: LlmProvider = "ollama"

    def __init__(self, settings: AgentServiceSettings) -> None:
        self._settings = settings

    def generate_board_commentary(
        self,
        *,
        agent_results: list[AgentResult],
        metric_facts: list[MetricFact],
        limitations: list[str],
    ) -> BoardCommentary:
        """Call Ollama and validate the model output against the commentary schema."""
        prompt = build_commentary_prompt(agent_results, metric_facts, limitations)
        try:
            return self._request_commentary(
                model_name=self._settings.ollama_model,
                prompt=prompt,
            )
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            if self._settings.ollama_fallback_model != self._settings.ollama_model:
                try:
                    return self._request_commentary(
                        model_name=self._settings.ollama_fallback_model,
                        prompt=prompt,
                    )
                except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError):
                    pass
            if not self._settings.allow_deterministic_fallback:
                raise
            deterministic = DeterministicBriefingModel()
            return deterministic.generate_board_commentary(
                agent_results=agent_results,
                metric_facts=metric_facts,
                limitations=[
                    *limitations,
                    f"Ollama commentary fallback used after provider error: {type(exc).__name__}.",
                ],
            )

    def _request_commentary(self, *, model_name: str, prompt: str) -> BoardCommentary:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a conservative RWA board commentary agent. Use only the "
                        "provided facts. Return valid JSON matching the requested schema. "
                        "Do not reuse example wording; write a fresh management comment."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
        }
        response = httpx.post(
            f"{self._settings.ollama_base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=self._settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        payload = _commentary_json_payload(content, model_name=model_name)
        payload = _normalize_commentary_payload(payload, _source_agent_names(prompt))
        return BoardCommentary.model_validate(payload)


def create_language_model(
    provider: LlmProvider,
    settings: AgentServiceSettings,
) -> BriefingLanguageModel:
    """Create the configured commentary generator."""
    if provider == "ollama":
        return OllamaBriefingModel(settings)
    return DeterministicBriefingModel()


def _commentary_json_payload(content: str, *, model_name: str) -> dict[str, Any]:
    """Extract the JSON object returned by Ollama without fabricating commentary."""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").removeprefix("json").strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError(f"Ollama model {model_name} did not return a JSON object.")
    return payload


def _normalize_commentary_payload(
    payload: dict[str, Any],
    source_agent_names: list[str],
) -> dict[str, Any]:
    """Normalize LLM metadata while preserving generated commentary text."""
    normalized = dict(payload)
    if "executive_summary" not in normalized and isinstance(normalized.get("summary"), str):
        normalized["executive_summary"] = normalized["summary"]
    if "key_messages" not in normalized:
        normalized["key_messages"] = _generated_message_list(
            normalized.get("agent_findings"),
            normalized.get("key_metrics"),
        )
    normalized.setdefault("risk_watchlist", [])
    normalized.setdefault("recommended_actions", [])
    normalized.setdefault("limitations", [])
    for field in ("key_messages", "risk_watchlist", "recommended_actions", "limitations"):
        value = normalized.get(field, [])
        if isinstance(value, str):
            normalized[field] = [value]
        elif value is None:
            normalized[field] = []

    allowed = set(source_agent_names)
    returned_names = normalized.get("source_agent_names")
    if not isinstance(returned_names, list):
        normalized["source_agent_names"] = source_agent_names
    else:
        normalized["source_agent_names"] = [
            name for name in returned_names if isinstance(name, str) and name in allowed
        ] or source_agent_names
    return normalized


def _generated_message_list(*values: Any) -> list[str]:
    messages: list[str] = []
    for value in values:
        if isinstance(value, dict):
            messages.extend(str(item) for item in value.values())
        elif isinstance(value, list):
            messages.extend(str(item) for item in value)
        elif isinstance(value, str):
            messages.append(value)
    return messages


def _agent(agent_results: list[AgentResult], name: str) -> AgentResult:
    for result in agent_results:
        if result.agent_name == name:
            return result
    return AgentResult(agent_name=name, status="SKIPPED", summary=f"{name} did not run.")


def _source_agent_names(prompt: str) -> list[str]:
    try:
        payload = json.loads(prompt)
    except json.JSONDecodeError:
        return []
    names = payload.get("allowed_source_agent_names", [])
    return [name for name in names if isinstance(name, str)]


def _money(fact: MetricFact | None) -> str:
    if fact is None or fact.value is None:
        return "n/a"
    return f"PLN {Decimal(str(fact.value)) / Decimal('1000000'):,.1f}m"


def _ratio(fact: MetricFact | None) -> str:
    if fact is None or fact.value is None:
        return "n/a"
    return f"{Decimal(str(fact.value)) * Decimal('100'):.2f}%"


def _value(fact: MetricFact | None, *, default: str) -> str:
    if fact is None or fact.value is None:
        return default
    return str(fact.value)
