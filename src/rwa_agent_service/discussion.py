from __future__ import annotations

import warnings
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TypedDict
from uuid import uuid4

from .discussion_schemas import (
    AgentState,
    CommentaryViews,
    DiscussionAgentFinding,
    DiscussionAgentName,
    DiscussionMessage,
    ExecutiveCommentaryPayload,
    GuardrailScanResult,
    ReActStep,
    ValidationFlag,
)
from .guardrails import RwaLlmGuard, create_guard
from .langfuse_integration import (
    LangfuseWorkflowTelemetry,
    LocalPromptRegistry,
    PromptRegistry,
)
from .quantitative_tools import (
    concentration_flags,
    detect_portfolio_input_anomalies,
    summarize_portfolio_structure,
    summarize_rwa_movement_drivers,
    validate_rwa_formula_deterministically,
)


class _DiscussionRuntimeState(TypedDict):
    """LangGraph wrapper carrying the strongly typed Pydantic agent state."""

    state: AgentState


RouteDecision = Literal["data_analyst", "risk_expert", "end"]

_ACTIVE_PROMPT_REGISTRY: ContextVar[PromptRegistry | None] = ContextVar(
    "active_rwa_prompt_registry",
    default=None,
)
_ACTIVE_TELEMETRY: ContextVar[LangfuseWorkflowTelemetry | None] = ContextVar(
    "active_rwa_langfuse_telemetry",
    default=None,
)
_ACTIVE_GUARD: ContextVar[RwaLlmGuard | None] = ContextVar(
    "active_rwa_llm_guard",
    default=None,
)


class MultiAgentRwaDiscussionGraph:
    """Supervisor + ReAct worker LangGraph workflow for RWA commentary."""

    def __init__(self) -> None:
        self.checkpointer_name = "MemorySaver"
        self._compiled_graph = self._build_langgraph()
        self.backend_name = "langgraph" if self._compiled_graph is not None else "local_graph"

    async def arun(
        self,
        state: AgentState,
        *,
        prompt_registry: PromptRegistry | None = None,
        telemetry: LangfuseWorkflowTelemetry | None = None,
        guard: RwaLlmGuard | None = None,
    ) -> AgentState:
        """Execute the guarded Supervisor + ReAct graph."""
        runtime_prompts = prompt_registry or LocalPromptRegistry()
        runtime_telemetry = telemetry or LangfuseWorkflowTelemetry.disabled()
        runtime_guard = guard or create_guard()
        prompt_token = _ACTIVE_PROMPT_REGISTRY.set(runtime_prompts)
        telemetry_token = _ACTIVE_TELEMETRY.set(runtime_telemetry)
        guard_token = _ACTIVE_GUARD.set(runtime_guard)
        thread_id = state.request_id or uuid4().hex
        try:
            with runtime_telemetry.workflow_context(
                name="rwa-commentary-workflow",
                request_id=state.request_id,
            ):
                if self._compiled_graph is not None:
                    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
                    callbacks = runtime_telemetry.callbacks()
                    if callbacks:
                        config["callbacks"] = callbacks
                    result = await self._compiled_graph.ainvoke({"state": state}, config=config)
                    final_state = result["state"]
                else:
                    final_state = await _run_local_graph(state)
                runtime_telemetry.submit_evaluation_scores(final_state)
                return final_state
        finally:
            _ACTIVE_GUARD.reset(guard_token)
            _ACTIVE_TELEMETRY.reset(telemetry_token)
            _ACTIVE_PROMPT_REGISTRY.reset(prompt_token)

    def _build_langgraph(self) -> Any | None:
        """Build the LangGraph workflow, falling back locally if unavailable."""
        try:
            try:
                from langchain_core._api.deprecation import (
                    suppress_langchain_deprecation_warning,
                )
            except Exception:
                suppress_langchain_deprecation_warning = nullcontext

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with suppress_langchain_deprecation_warning():
                    from langgraph.checkpoint.memory import MemorySaver
                    from langgraph.graph import END, StateGraph

                    graph = StateGraph(_DiscussionRuntimeState)
                    graph.add_node(
                        "supervisor",
                        _wrap_async_node(supervisor_agent, "SupervisorAgent"),
                    )
                    graph.add_node(
                        "data_analyst",
                        _wrap_async_node(data_analyst_agent, "DataAnalystAgent"),
                    )
                    graph.add_node(
                        "risk_expert",
                        _wrap_async_node(risk_expert_agent, "RiskExpertAgent"),
                    )
                    graph.set_entry_point("supervisor")
                    graph.add_conditional_edges(
                        "supervisor",
                        _route_after_supervisor,
                        {"data_analyst": "data_analyst", "risk_expert": "risk_expert", "end": END},
                    )
                    graph.add_edge("data_analyst", "supervisor")
                    graph.add_edge("risk_expert", "supervisor")
                    return graph.compile(checkpointer=MemorySaver())
        except Exception:
            self.checkpointer_name = "local_in_memory"
            return None


async def supervisor_agent(
    state: AgentState,
    *,
    system_prompt: str | None = None,
) -> AgentState:
    """Route worker agents, evaluate consensus and compile structured commentary."""
    _ = system_prompt
    if state.guardrail_blocked:
        state.next_agent = "END"
        state.final_commentary = _build_blocked_payload(state)
        return state

    data_findings = _findings_for(state, "DataAnalystAgent")
    risk_findings = _findings_for(state, "RiskExpertAgent")
    completed_cycles = min(len(data_findings), len(risk_findings))
    state.loop_count = max(state.loop_count, completed_cycles)

    if not data_findings:
        state.next_agent = "DataAnalystAgent"
        _append_supervisor_message(state, "Routing to DataAnalystAgent for input review.")
        return state
    if len(risk_findings) < len(data_findings):
        state.next_agent = "RiskExpertAgent"
        _append_supervisor_message(state, "Routing to RiskExpertAgent for RWA interpretation.")
        return state

    critical_flags = [flag for flag in state.validation_flags if flag.severity == "CRITICAL"]
    state.consensus_reached = not critical_flags
    if state.consensus_reached or state.loop_count >= state.loop_limit:
        state.next_agent = "END"
        final_status = "COMPLETED" if state.consensus_reached else "LOOP_LIMIT_REACHED"
        state.final_commentary = _build_commentary_payload(state, status=final_status)
        _append_supervisor_message(
            state,
            "Consensus reached and structured commentary compiled."
            if state.consensus_reached
            else "Loop limit reached; structured commentary compiled with unresolved flags.",
        )
        return state

    state.next_agent = "DataAnalystAgent"
    _append_supervisor_message(
        state,
        "Critical flags remain; requesting another DataAnalystAgent and RiskExpertAgent pass.",
    )
    return state


async def data_analyst_agent(
    state: AgentState,
    *,
    system_prompt: str | None = None,
) -> AgentState:
    """Run ReAct-style data-quality and portfolio-structure analysis."""
    _ = system_prompt
    telemetry = _ACTIVE_TELEMETRY.get() or LangfuseWorkflowTelemetry.disabled()

    telemetry.record_tool_call("summarize_portfolio_structure", agent_name="DataAnalystAgent")
    summary = summarize_portfolio_structure(state.rwa_input_data, state.rwa_output_results)
    structure_step = ReActStep(
        agent_name="DataAnalystAgent",
        inspection=(
            f"Inspect {summary['input_record_count']} input records and "
            f"{summary['output_record_count']} calculator outputs."
        ),
        selected_action="Analyze portfolio structure and concentration.",
        tool_name="summarize_portfolio_structure",
        observation=(
            f"{summary['asset_class_count']} asset classes, {summary['sector_count']} sectors, "
            f"largest asset class {summary['largest_asset_class']} at "
            f"{summary['largest_asset_class_share'] * 100:.1f}%."
        ),
    )

    telemetry.record_tool_call("detect_portfolio_input_anomalies", agent_name="DataAnalystAgent")
    flags = detect_portfolio_input_anomalies(state.rwa_input_data, state.rwa_output_results)
    flags.extend(concentration_flags(summary))
    _append_unique_flags(state, flags)
    data_codes = [flag.code for flag in flags]
    affected = [flag.asset_id for flag in flags if flag.asset_id]
    anomaly_step = ReActStep(
        agent_name="DataAnalystAgent",
        inspection="Inspect rating, validation, PD, LGD, EAD and input/output coverage fields.",
        selected_action="Detect data-quality and risk-parameter anomalies.",
        tool_name="detect_portfolio_input_anomalies",
        observation=f"{len(flags)} validation flags returned: {', '.join(data_codes) or 'none'}.",
    )

    actions = _data_actions(flags)
    state.agent_findings.append(
        DiscussionAgentFinding(
            finding_id=f"data-quality-{len(_findings_for(state, 'DataAnalystAgent')) + 1}",
            agent_name="DataAnalystAgent",
            category="DATA_QUALITY",
            severity=_max_severity(flags),
            title="Input data quality and portfolio structure review",
            summary=(
                f"Reviewed anonymized inputs for missing ratings, failed validations, "
                f"unexpected PD/LGD/EAD values and concentration. {len(flags)} findings "
                "were raised by deterministic tools."
            ),
            affected_asset_ids=affected[:25],
            validation_codes=data_codes,
            recommended_actions=actions,
            react_steps=[structure_step, anomaly_step],
        )
    )
    _extend_unique(state.recommended_actions, actions)
    state.messages.append(
        DiscussionMessage(
            agent_name="DataAnalystAgent",
            validation_codes=data_codes,
            requires_follow_up=any(flag.requires_human_intervention for flag in flags),
            content=(
                "DataAnalystAgent completed ReAct analysis using portfolio-structure and "
                f"input-anomaly tools; {len(flags)} data-quality flags were observed."
            ),
        )
    )
    return state


async def risk_expert_agent(
    state: AgentState,
    *,
    system_prompt: str | None = None,
) -> AgentState:
    """Run ReAct-style RWA movement, Basel context and capital-risk analysis."""
    _ = system_prompt
    telemetry = _ACTIVE_TELEMETRY.get() or LangfuseWorkflowTelemetry.disabled()

    telemetry.record_tool_call(
        "validate_rwa_formula_deterministically", agent_name="RiskExpertAgent"
    )
    formula_flags = validate_rwa_formula_deterministically(
        state.rwa_input_data,
        state.rwa_output_results,
        materiality_threshold=state.materiality_threshold,
    )
    _append_unique_flags(state, formula_flags)
    formula_step = ReActStep(
        agent_name="RiskExpertAgent",
        inspection="Inspect exposure, risk weight and reported RWA output fields.",
        selected_action="Validate RWA formula through deterministic Python code.",
        tool_name="validate_rwa_formula_deterministically",
        observation=f"{len(formula_flags)} formula validation flags returned.",
    )

    telemetry.record_tool_call("summarize_rwa_movement_drivers", agent_name="RiskExpertAgent")
    movement = summarize_rwa_movement_drivers(state.rwa_input_data, state.rwa_output_results)
    movement_step = ReActStep(
        agent_name="RiskExpertAgent",
        inspection="Inspect previous and current RWA, sector, risk class and rating fields.",
        selected_action="Explain RWA movement drivers by sector and rating migration.",
        tool_name="summarize_rwa_movement_drivers",
        observation=(
            f"{movement['movement_record_count']} movement records; total RWA delta "
            f"{movement['total_rwa_delta']}; top sector {movement['top_movement_sector']}."
        ),
    )

    codes = [flag.code for flag in formula_flags]
    actions = _risk_actions(formula_flags, movement)
    state.agent_findings.append(
        DiscussionAgentFinding(
            finding_id=f"risk-interpretation-{len(_findings_for(state, 'RiskExpertAgent')) + 1}",
            agent_name="RiskExpertAgent",
            category="RISK_INTERPRETATION",
            severity=_max_severity(formula_flags),
            title="RWA movement and Basel interpretation",
            summary=(
                "RiskExpertAgent interpreted RWA outputs using deterministic formula checks, "
                "movement-driver grouping and Basel/internal-buffer review context. "
                f"Top movement sector: {movement['top_movement_sector']}."
            ),
            affected_asset_ids=[flag.asset_id for flag in formula_flags if flag.asset_id][:25],
            validation_codes=codes,
            recommended_actions=actions,
            react_steps=[formula_step, movement_step],
        )
    )
    _extend_unique(state.recommended_actions, actions)
    state.messages.append(
        DiscussionMessage(
            agent_name="RiskExpertAgent",
            validation_codes=codes,
            requires_follow_up=any(flag.requires_human_intervention for flag in formula_flags),
            content=(
                "RiskExpertAgent completed ReAct analysis using deterministic RWA validation "
                "and movement-driver tools."
            ),
        )
    )
    return state


def _route_after_supervisor(runtime_state: _DiscussionRuntimeState) -> RouteDecision:
    state = runtime_state["state"]
    if state.guardrail_blocked or state.next_agent == "END":
        return "end"
    if state.next_agent == "RiskExpertAgent":
        return "risk_expert"
    return "data_analyst"


def _wrap_async_node(node: Any, agent_name: DiscussionAgentName) -> Any:
    async def wrapped(runtime_state: _DiscussionRuntimeState) -> _DiscussionRuntimeState:
        state = runtime_state["state"]
        prompt_registry = _ACTIVE_PROMPT_REGISTRY.get() or LocalPromptRegistry()
        telemetry = _ACTIVE_TELEMETRY.get() or LangfuseWorkflowTelemetry.disabled()
        guard = _ACTIVE_GUARD.get() or create_guard()
        prompt = prompt_registry.get_system_prompt(agent_name)
        telemetry.record_prompt_usage(prompt)

        input_decision = guard.scan_input(
            _agent_input_text(state, prompt.content), agent_name=agent_name
        )
        _record_guardrail_results(state, telemetry, input_decision.results)
        if input_decision.blocked:
            _mark_guardrail_blocked(state, agent_name, input_decision.results)
            return {"state": state}

        before = _state_counts(state)
        with telemetry.node_context(node_name=agent_name, state=state, prompt=prompt):
            state = await node(state, system_prompt=input_decision.sanitized_text)

        output_decision = guard.scan_output(_new_output_text(state, before), agent_name=agent_name)
        _record_guardrail_results(state, telemetry, output_decision.results)
        if output_decision.blocked:
            _rollback_state(state, before)
            _mark_guardrail_blocked(state, agent_name, output_decision.results)
        return {"state": state}

    return wrapped


async def _run_local_graph(state: AgentState) -> AgentState:
    state = (await _wrap_async_node(supervisor_agent, "SupervisorAgent")({"state": state}))["state"]
    while _route_after_supervisor({"state": state}) != "end":
        if state.next_agent == "RiskExpertAgent":
            state = (
                await _wrap_async_node(risk_expert_agent, "RiskExpertAgent")({"state": state})
            )["state"]
        else:
            state = (
                await _wrap_async_node(data_analyst_agent, "DataAnalystAgent")({"state": state})
            )["state"]
        state = (await _wrap_async_node(supervisor_agent, "SupervisorAgent")({"state": state}))[
            "state"
        ]
    return state


def _append_supervisor_message(state: AgentState, content: str) -> None:
    state.messages.append(
        DiscussionMessage(
            agent_name="SupervisorAgent",
            content=content,
            validation_codes=[flag.code for flag in state.validation_flags],
            requires_follow_up=state.next_agent != "END",
        )
    )


def _append_unique_flags(state: AgentState, flags: list[ValidationFlag]) -> None:
    existing = {
        (flag.code, flag.asset_id, flag.source_agent, flag.message)
        for flag in state.validation_flags
    }
    for flag in flags:
        key = (flag.code, flag.asset_id, flag.source_agent, flag.message)
        if key not in existing:
            state.validation_flags.append(flag)
            existing.add(key)


def _record_guardrail_results(
    state: AgentState,
    telemetry: LangfuseWorkflowTelemetry,
    results: list[GuardrailScanResult],
) -> None:
    state.guardrail_results.extend(results)
    telemetry.record_guardrail_results(results)


def _mark_guardrail_blocked(
    state: AgentState,
    agent_name: DiscussionAgentName,
    results: list[GuardrailScanResult],
) -> None:
    blocked = [result for result in results if result.action == "blocked"]
    state.guardrail_blocked = True
    state.next_agent = "END"
    state.consensus_reached = False
    state.validation_flags.append(
        ValidationFlag(
            code="LLM_GUARD_BLOCKED",
            severity="CRITICAL",
            source_agent=agent_name,
            message=f"LLM Guard blocked {agent_name} execution before unsafe state update.",
            requires_human_intervention=True,
        )
    )
    state.final_commentary = _build_blocked_payload(state)
    state.messages.append(
        DiscussionMessage(
            agent_name="SupervisorAgent",
            content=(
                f"Guardrail policy blocked {agent_name}; "
                f"{len(blocked)} scanner result(s) require review."
            ),
            validation_codes=["LLM_GUARD_BLOCKED"],
            requires_follow_up=True,
        )
    )


def _build_blocked_payload(state: AgentState) -> ExecutiveCommentaryPayload:
    state.commentary_views = CommentaryViews(
        executive_summary="AI Executive Commentary is blocked by guardrail policy.",
        cro_view="Risk commentary is unavailable because guardrail scanning blocked the run.",
        cfo_view="Capital commentary is unavailable because guardrail scanning blocked the run.",
    )
    return ExecutiveCommentaryPayload(
        status="BLOCKED",
        consensus_reached=False,
        loop_count=state.loop_count,
        generated_at=datetime.now(UTC),
        source_label="RiskTrace Intelligence",
        executive_summary=state.commentary_views.executive_summary,
        cro_view=state.commentary_views.cro_view,
        cfo_view=state.commentary_views.cfo_view,
        data_quality_observations=[],
        risk_observations=[],
        quantitative_validation=[],
        recommended_actions=["Review guardrail results before re-running commentary generation."],
        validation_flags=state.validation_flags,
        source_agents=["SupervisorAgent"],
    )


def _build_commentary_payload(
    state: AgentState,
    *,
    status: Literal["COMPLETED", "LOOP_LIMIT_REACHED"],
) -> ExecutiveCommentaryPayload:
    portfolio_summary = summarize_portfolio_structure(
        state.rwa_input_data, state.rwa_output_results
    )
    data_findings = _findings_for(state, "DataAnalystAgent")
    risk_findings = _findings_for(state, "RiskExpertAgent")
    quantitative_messages = [
        flag.message for flag in state.validation_flags if flag.source_agent == "RiskExpertAgent"
    ]
    critical_count = sum(1 for flag in state.validation_flags if flag.severity == "CRITICAL")
    material_count = sum(1 for flag in state.validation_flags if flag.severity == "MATERIAL")
    watch_count = sum(1 for flag in state.validation_flags if flag.severity == "WATCH")
    total_rwa = Decimal(str(portfolio_summary["total_rwa"]))
    total_exposure = Decimal(str(portfolio_summary["total_exposure"]))
    rwa_density = Decimal(str(portfolio_summary["rwa_density"]))

    if state.consensus_reached:
        executive_summary = (
            "SupervisorAgent reached consensus after tool-backed DataAnalystAgent and "
            f"RiskExpertAgent reviews. Reviewed {total_exposure:.2f} of exposure and "
            f"{total_rwa:.2f} of RWA with portfolio density {rwa_density * 100:.2f}%."
        )
    else:
        executive_summary = (
            "SupervisorAgent stopped at the loop limit with unresolved validation flags; "
            f"{critical_count} critical and {material_count} material flags remain."
        )

    cro_view = (
        "CRO View: "
        f"{critical_count} critical, {material_count} material and {watch_count} watch flags. "
        f"Largest asset class is {portfolio_summary['largest_asset_class']} at "
        f"{Decimal(str(portfolio_summary['largest_asset_class_share'])) * 100:.1f}% of exposure. "
        "All quantitative checks were routed through deterministic Python tools."
    )
    cfo_view = (
        "CFO View: "
        f"total RWA is {total_rwa:.2f} against exposure {total_exposure:.2f}, "
        f"with RWA density {rwa_density * 100:.2f}%. Recommended actions should be assessed "
        "for capital and buffer impact before management sign-off."
    )
    state.commentary_views = CommentaryViews(
        executive_summary=executive_summary,
        cro_view=cro_view,
        cfo_view=cfo_view,
    )
    return ExecutiveCommentaryPayload(
        status=status,
        consensus_reached=state.consensus_reached,
        loop_count=state.loop_count,
        generated_at=datetime.now(UTC),
        source_label="RiskTrace Intelligence",
        executive_summary=executive_summary,
        cro_view=cro_view,
        cfo_view=cfo_view,
        data_quality_observations=_finding_summaries(data_findings),
        risk_observations=_finding_summaries(risk_findings),
        quantitative_validation=quantitative_messages
        or ["All calculator outputs with available parameters matched deterministic validation."],
        recommended_actions=state.recommended_actions
        or ["Proceed with standard review using the generated executive commentary."],
        validation_flags=state.validation_flags,
        source_agents=["DataAnalystAgent", "RiskExpertAgent", "SupervisorAgent"],
    )


def _data_actions(flags: list[ValidationFlag]) -> list[str]:
    actions: list[str] = []
    if any(flag.code == "MISSING_RATING" for flag in flags):
        actions.append("Complete missing rating or risk-bucket fields before approval.")
    if any(flag.code == "FAILED_VALIDATION_RECORD" for flag in flags):
        actions.append("Resolve failed validation records in the source input package.")
    if any(flag.code in {"PD_OUTLIER", "LGD_OUTLIER", "NON_POSITIVE_EXPOSURE"} for flag in flags):
        actions.append("Review PD, LGD and EAD outliers with data owners.")
    if any(flag.code.endswith("CONCENTRATION") for flag in flags):
        actions.append("Review concentration flags against portfolio risk appetite.")
    return actions or ["Retain data-quality evidence with the commentary pack."]


def _risk_actions(
    flags: list[ValidationFlag],
    movement: dict[str, Decimal | int | str],
) -> list[str]:
    actions: list[str] = []
    if any(flag.code == "RWA_FORMULA_DEVIATION" for flag in flags):
        actions.append("Investigate deterministic RWA formula deviations before approval.")
    if Decimal(str(movement["absolute_rwa_delta"])) > Decimal("0"):
        actions.append("Review RWA movement drivers by sector and rating migration.")
    return actions or ["Document Basel and capital-buffer interpretation for management sign-off."]


def _findings_for(
    state: AgentState,
    agent_name: DiscussionAgentName,
) -> list[DiscussionAgentFinding]:
    return [finding for finding in state.agent_findings if finding.agent_name == agent_name]


def _finding_summaries(findings: list[DiscussionAgentFinding]) -> list[str]:
    return [finding.summary for finding in findings[-3:]]


def _max_severity(flags: list[ValidationFlag]) -> Literal["INFO", "WATCH", "MATERIAL", "CRITICAL"]:
    rank = {"INFO": 0, "WATCH": 1, "MATERIAL": 2, "CRITICAL": 3}
    if not flags:
        return "INFO"
    return max((flag.severity for flag in flags), key=lambda severity: rank[severity])


def _extend_unique(target: list[str], values: list[str]) -> None:
    existing = set(target)
    for value in values:
        if value not in existing:
            target.append(value)
            existing.add(value)


def _agent_input_text(state: AgentState, system_prompt: str) -> str:
    portfolio_terms = " ".join(
        f"{record.asset_id} {record.asset_class} {record.sector or ''} {record.rating or ''}"
        for record in state.rwa_input_data[:25]
    )
    return "\n".join(
        [
            system_prompt,
            f"request_id={state.request_id}",
            f"portfolio_terms={portfolio_terms}",
            f"messages={len(state.messages)}",
            f"validation_flags={','.join(flag.code for flag in state.validation_flags)}",
            f"findings={len(state.agent_findings)}",
        ]
    )


def _new_output_text(state: AgentState, before: tuple[int, int, int, int]) -> str:
    message_count, flag_count, finding_count, action_count = before
    new_messages = [message.content for message in state.messages[message_count:]]
    new_flags = [flag.message for flag in state.validation_flags[flag_count:]]
    new_findings = [finding.summary for finding in state.agent_findings[finding_count:]]
    new_actions = state.recommended_actions[action_count:]
    return "\n".join([*new_messages, *new_flags, *new_findings, *new_actions])


def _state_counts(state: AgentState) -> tuple[int, int, int, int]:
    return (
        len(state.messages),
        len(state.validation_flags),
        len(state.agent_findings),
        len(state.recommended_actions),
    )


def _rollback_state(state: AgentState, before: tuple[int, int, int, int]) -> None:
    message_count, flag_count, finding_count, action_count = before
    del state.messages[message_count:]
    del state.validation_flags[flag_count:]
    del state.agent_findings[finding_count:]
    del state.recommended_actions[action_count:]
