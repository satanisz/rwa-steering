from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal, Protocol

from .config import AgentServiceSettings
from .discussion_schemas import (
    AgentState,
    DiscussionAgentName,
    EvaluationScore,
    GuardrailScanResult,
    PromptUsage,
    ValidationFlag,
)

_PROMPT_NAMES: dict[DiscussionAgentName, str] = {
    "DataAnalystAgent": "rwa-data-analyst-agent-system",
    "RiskExpertAgent": "rwa-risk-expert-agent-system",
    "SupervisorAgent": "rwa-supervisor-agent-system",
}

_PROMPT_FALLBACKS: dict[DiscussionAgentName, str] = {
    "DataAnalystAgent": (
        "You are a data analyst reviewing anonymized RWA input data. Use only provided "
        "asset IDs, sectors, asset classes, risk parameters and financial values. Do not "
        "introduce PII or calculate RWA formulas natively."
    ),
    "RiskExpertAgent": (
        "You are a regulatory risk expert reviewing calculator outputs. Interpret Basel "
        "RWA results conservatively and route all quantitative formula validation through "
        "deterministic Python tools."
    ),
    "SupervisorAgent": (
        "You are the supervisor coordinating an RWA analysis discussion. Decide whether "
        "consensus is reached, enforce loop limits and return structured executive "
        "commentary backed by validation flags."
    ),
}


@dataclass(frozen=True)
class AgentSystemPrompt:
    """System prompt content and registry metadata for one agent."""

    agent_name: DiscussionAgentName
    prompt_name: str
    content: str
    source: str
    version: int | str | None = None
    raw_prompt: Any | None = None


class PromptRegistry(Protocol):
    """Prompt registry interface used by graph nodes."""

    def get_system_prompt(self, agent_name: DiscussionAgentName) -> AgentSystemPrompt:
        """Fetch a system prompt for an agent node."""


class LocalPromptRegistry:
    """Fallback prompt provider used when Langfuse is disabled."""

    def get_system_prompt(self, agent_name: DiscussionAgentName) -> AgentSystemPrompt:
        return AgentSystemPrompt(
            agent_name=agent_name,
            prompt_name=_PROMPT_NAMES[agent_name],
            content=_PROMPT_FALLBACKS[agent_name],
            source="local_fallback",
        )


class LangfusePromptRegistry:
    """Langfuse Prompt Registry adapter for agent system prompts."""

    def __init__(self, settings: AgentServiceSettings, *, client: Any | None = None) -> None:
        self._settings = settings
        if client is None:
            from langfuse import get_client

            client = get_client()
        self._client = client

    def get_system_prompt(self, agent_name: DiscussionAgentName) -> AgentSystemPrompt:
        prompt_name = _PROMPT_NAMES[agent_name]
        fallback = _PROMPT_FALLBACKS[agent_name]
        prompt = self._client.get_prompt(
            prompt_name,
            label=self._settings.langfuse_prompt_label,
            type="text",
            cache_ttl_seconds=self._settings.langfuse_prompt_cache_ttl_seconds,
            fetch_timeout_seconds=self._settings.langfuse_prompt_fetch_timeout_seconds,
            fallback=fallback,
        )
        return AgentSystemPrompt(
            agent_name=agent_name,
            prompt_name=prompt_name,
            content=_prompt_content(prompt, fallback=fallback),
            source="langfuse",
            version=_prompt_version(prompt),
            raw_prompt=prompt,
        )


@dataclass
class LangfuseWorkflowTelemetry:
    """Small adapter around Langfuse tracing, callback and scoring APIs."""

    enabled: bool
    client: Any | None = None
    callback_handler: Any | None = None
    trace_id: str | None = None
    prompt_usages: list[PromptUsage] = field(default_factory=list)
    evaluation_scores: list[EvaluationScore] = field(default_factory=list)
    guardrail_results: list[GuardrailScanResult] = field(default_factory=list)
    node_transition_count: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    total_token_count: int = 0
    callback_handler_attached: bool = False

    @classmethod
    def disabled(cls) -> LangfuseWorkflowTelemetry:
        return cls(enabled=False)

    @classmethod
    def from_settings(
        cls,
        settings: AgentServiceSettings,
        *,
        client: Any | None = None,
        callback_handler: Any | None = None,
    ) -> LangfuseWorkflowTelemetry:
        if not settings.langfuse_enabled:
            return cls.disabled()
        if client is None:
            from langfuse import get_client

            client = get_client()
        if callback_handler is None:
            from langfuse.langchain import CallbackHandler

            callback_handler = CallbackHandler()
        return cls(enabled=True, client=client, callback_handler=callback_handler)

    def callbacks(self) -> list[Any]:
        if self.enabled and self.callback_handler is not None:
            self.callback_handler_attached = True
            return [self.callback_handler]
        return []

    def workflow_context(
        self,
        *,
        name: str,
        request_id: str | None,
    ) -> AbstractContextManager[Any]:
        if not self.enabled or self.client is None:
            return nullcontext()
        return _LangfuseWorkflowContext(
            telemetry=self,
            context=self.client.start_as_current_observation(
                name=name,
                as_type="chain",
                input={"request_id": request_id},
                metadata={"component": "rwa_agent_service"},
            ),
        )

    def node_context(
        self,
        *,
        node_name: str,
        state: AgentState,
        prompt: AgentSystemPrompt,
    ) -> AbstractContextManager[Any]:
        self.node_transition_count += 1
        if not self.enabled or self.client is None:
            return _LatencyContext(self, node_name=node_name)
        return _LangfuseNodeContext(self, node_name=node_name, state=state, prompt=prompt)

    def record_prompt_usage(self, prompt: AgentSystemPrompt) -> None:
        self.prompt_usages.append(
            PromptUsage(
                agent_name=prompt.agent_name,
                prompt_name=prompt.prompt_name,
                prompt_source="langfuse" if prompt.source == "langfuse" else "local_fallback",
                prompt_version=prompt.version,
            )
        )

    def record_llm_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        self.llm_call_count += 1
        self.total_token_count += input_tokens + output_tokens

    def record_tool_call(self, tool_name: str, *, agent_name: DiscussionAgentName) -> None:
        self.tool_call_count += 1
        if self.enabled and self.client is not None:
            with self.client.start_as_current_observation(
                name=tool_name,
                as_type="tool",
                input={"agent_name": agent_name},
                metadata={"component": "rwa_deterministic_tool"},
            ):
                pass

    def record_guardrail_results(self, results: list[GuardrailScanResult]) -> None:
        self.guardrail_results.extend(results)
        if self.enabled and self.client is not None:
            for result in results:
                with self.client.start_as_current_observation(
                    name=f"llm_guard.{result.scanner_name}.{result.stage}",
                    as_type="guardrail",
                    input={"agent_name": result.agent_name, "stage": result.stage},
                    output=result.model_dump(mode="json"),
                    metadata={
                        "action": result.action,
                        "risk_score": str(result.risk_score),
                        "scanner": result.scanner_name,
                    },
                ):
                    pass

    def submit_evaluation_scores(self, state: AgentState) -> None:
        scores = evaluate_final_state(state)
        self.evaluation_scores.extend(scores)
        if not self.enabled or self.client is None:
            return
        for score in scores:
            self.client.score_current_trace(
                name=score.name,
                value=float(score.value) if isinstance(score.value, Decimal) else score.value,
                data_type=score.data_type,
                comment=score.comment,
            )


class _LatencyContext:
    def __init__(self, telemetry: LangfuseWorkflowTelemetry, *, node_name: str) -> None:
        self._telemetry = telemetry
        self._node_name = node_name
        self._started_at = 0.0

    def __enter__(self) -> _LatencyContext:
        self._started_at = perf_counter()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        _ = self._node_name, perf_counter() - self._started_at
        return False


class _LangfuseWorkflowContext:
    def __init__(
        self,
        *,
        telemetry: LangfuseWorkflowTelemetry,
        context: AbstractContextManager[Any],
    ) -> None:
        self._telemetry = telemetry
        self._context = context

    def __enter__(self) -> Any:
        observation = self._context.__enter__()
        trace_id = getattr(observation, "trace_id", None)
        if isinstance(trace_id, str):
            self._telemetry.trace_id = trace_id
        return observation

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return bool(self._context.__exit__(exc_type, exc, traceback))


class _LangfuseNodeContext:
    def __init__(
        self,
        telemetry: LangfuseWorkflowTelemetry,
        *,
        node_name: str,
        state: AgentState,
        prompt: AgentSystemPrompt,
    ) -> None:
        self._telemetry = telemetry
        self._node_name = node_name
        self._state = state
        self._prompt = prompt
        self._started_at = 0.0
        self._context: AbstractContextManager[Any] | None = None

    def __enter__(self) -> Any:
        self._started_at = perf_counter()
        input_tokens = _token_estimate(self._prompt.content) + _state_token_estimate(self._state)
        self._telemetry.record_llm_usage(input_tokens=input_tokens, output_tokens=0)
        client = self._telemetry.client
        if client is None:
            raise RuntimeError("Langfuse node context requires an initialized client.")
        self._context = client.start_as_current_observation(
            name=self._node_name,
            as_type="generation",
            input={"loop_count": self._state.loop_count, "prompt_name": self._prompt.prompt_name},
            model="rwa-deterministic-python-tools",
            usage_details={"input": input_tokens, "output": 0, "total": input_tokens},
            prompt=self._prompt.raw_prompt,
            metadata={
                "agent_name": self._prompt.agent_name,
                "validation_flags": len(self._state.validation_flags),
            },
        )
        return self._context.__enter__()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        elapsed_ms = int((perf_counter() - self._started_at) * 1000)
        if self._context is not None:
            return bool(self._context.__exit__(exc_type, exc, traceback))
        _ = elapsed_ms
        return False


def create_prompt_registry(
    settings: AgentServiceSettings,
    *,
    client: Any | None = None,
) -> PromptRegistry:
    """Create the configured prompt registry adapter."""
    if settings.langfuse_enabled:
        return LangfusePromptRegistry(settings, client=client)
    return LocalPromptRegistry()


def evaluate_final_state(state: AgentState) -> list[EvaluationScore]:
    """Produce deterministic post-execution scores for Langfuse evaluation."""
    if state.final_commentary is None:
        return []
    critical_flags = [flag for flag in state.validation_flags if flag.severity == "CRITICAL"]
    faithfulness = (
        Decimal("1.0") if _commentary_references_flags(state.validation_flags) else Decimal("0.0")
    )
    groundedness = Decimal("1.0") if state.messages else Decimal("0.0")
    anomaly_detection = (
        Decimal("1.0") if _anomaly_detection_passed(state.validation_flags) else Decimal("0.0")
    )
    guardrail_block_count = sum(
        1 for result in state.guardrail_results if result.action == "blocked"
    )
    pii_detected = any(
        result.scanner_name == "PII" and result.action != "passed"
        for result in state.guardrail_results
    )
    prompt_injection_risk = max(
        (
            result.risk_score
            for result in state.guardrail_results
            if result.scanner_name == "PromptInjection"
        ),
        default=Decimal("0"),
    )
    return [
        EvaluationScore(
            name="Faithfulness",
            value=faithfulness,
            data_type="NUMERIC",
            comment="Final commentary references the validation state produced by graph agents.",
        ),
        EvaluationScore(
            name="Groundedness",
            value=groundedness,
            data_type="NUMERIC",
            comment="Final commentary is grounded in graph messages and deterministic validations.",
        ),
        EvaluationScore(
            name="Anomaly_Detection",
            value=anomaly_detection,
            data_type="BOOLEAN",
            comment=f"{len(critical_flags)} critical validation flags present.",
        ),
        EvaluationScore(
            name="Guardrail_Block_Count",
            value=guardrail_block_count,
            data_type="NUMERIC",
            comment="Number of LLM Guard scanner results that blocked execution.",
        ),
        EvaluationScore(
            name="PII_Detected",
            value=pii_detected,
            data_type="BOOLEAN",
            comment="Whether LLM Guard detected PII-like input or output.",
        ),
        EvaluationScore(
            name="Prompt_Injection_Risk",
            value=prompt_injection_risk,
            data_type="NUMERIC",
            comment="Maximum prompt-injection risk score observed by LLM Guard.",
        ),
    ]


def _prompt_content(prompt: Any, *, fallback: str) -> str:
    if hasattr(prompt, "compile"):
        compiled = prompt.compile()
        return str(compiled)
    if hasattr(prompt, "get_langchain_prompt"):
        return str(prompt.get_langchain_prompt())
    value = getattr(prompt, "prompt", fallback)
    return str(value)


def _prompt_version(prompt: Any) -> int | str | None:
    version = getattr(prompt, "version", None)
    return version if isinstance(version, (int, str)) else None


def _commentary_references_flags(flags: list[ValidationFlag]) -> bool:
    return True if not flags else all(flag.message for flag in flags)


def _anomaly_detection_passed(flags: list[ValidationFlag]) -> bool:
    material_flags = [flag for flag in flags if flag.severity in {"MATERIAL", "CRITICAL"}]
    return not material_flags or any(flag.requires_human_intervention for flag in material_flags)


def _state_token_estimate(state: AgentState) -> int:
    return _token_estimate(
        " ".join(
            [
                str(len(state.rwa_input_data)),
                str(len(state.rwa_output_results)),
                " ".join(flag.code for flag in state.validation_flags),
            ]
        )
    )


def _token_estimate(value: str) -> int:
    return max(1, len(value.split()))
