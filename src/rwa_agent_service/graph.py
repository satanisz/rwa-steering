from __future__ import annotations

import warnings
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, TypedDict

from .config import AgentServiceSettings
from .llm import BriefingLanguageModel
from .memory import RequestMemory
from .rag import EvidenceRetriever
from .schemas import AgentResult, BoardCommentary, BriefingRequest, EvidenceItem, MetricFact
from .tools import AgentRuntimeContext
from .tracing import TraceRecorder


@dataclass
class AgentGraphState:
    """Mutable state carried between agent graph nodes."""

    request: BriefingRequest
    context: AgentRuntimeContext
    settings: AgentServiceSettings
    language_model: BriefingLanguageModel
    retriever: EvidenceRetriever
    memory: RequestMemory
    trace: TraceRecorder
    metric_facts: list[MetricFact] = field(default_factory=list)
    evidence_inventory: list[EvidenceItem] = field(default_factory=list)
    lineage: list[dict[str, str | int]] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    board_commentary: BoardCommentary | None = None


class _LangGraphRuntimeState(TypedDict):
    """LangGraph state wrapper carrying the mutable service state object."""

    state: AgentGraphState


class RwaAgentGraph:
    """Read-only LangGraph workflow for RWA briefing agents."""

    def __init__(self) -> None:
        self._node_sequence = _node_sequence()
        self._compiled_graph = self._build_langgraph()
        self.backend_name = "langgraph" if self._compiled_graph is not None else "local_graph"

    def run(self, state: AgentGraphState) -> AgentGraphState:
        """Execute each read-only RWA agent node in order."""
        if self._compiled_graph is not None:
            result = self._compiled_graph.invoke({"state": state})
            return result["state"]

        for _name, node in self._node_sequence:
            state = node(state)
        return state

    def _build_langgraph(self) -> Any | None:
        """Build a LangGraph workflow with explicit local degradation."""
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
                    from langgraph.graph import END, StateGraph

                    graph = StateGraph(_LangGraphRuntimeState)
                    previous_name: str | None = None
                    for name, node in self._node_sequence:
                        graph.add_node(  # type: ignore[call-overload]
                            name,
                            _wrap_langgraph_node(node),
                        )
                        if previous_name is None:
                            graph.set_entry_point(name)
                        else:
                            graph.add_edge(previous_name, name)
                        previous_name = name
                    if previous_name is not None:
                        graph.add_edge(previous_name, END)
                    return graph.compile()
        except Exception:
            return None


def _node_sequence() -> tuple[tuple[str, Callable[[AgentGraphState], AgentGraphState]], ...]:
    """Return the ordered agent workflow."""
    from .nodes import (
        board_commentary_node,
        capital_stack_node,
        data_quality_node,
        evidence_pack_node,
        prepare_context_node,
        rwa_movement_node,
    )

    return (
        ("prepare_context", prepare_context_node),
        ("rwa_movement", rwa_movement_node),
        ("capital_stack", capital_stack_node),
        ("data_quality", data_quality_node),
        ("evidence_pack", evidence_pack_node),
        ("board_commentary", board_commentary_node),
    )


def _wrap_langgraph_node(
    node: Callable[[AgentGraphState], AgentGraphState],
) -> Callable[[_LangGraphRuntimeState], _LangGraphRuntimeState]:
    """Adapt service node functions to LangGraph's dict update contract."""

    def wrapped(runtime_state: _LangGraphRuntimeState) -> _LangGraphRuntimeState:
        return {"state": node(runtime_state["state"])}

    return wrapped
