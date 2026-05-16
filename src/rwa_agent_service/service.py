from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from .config import AgentServiceSettings, load_settings
from .discussion import MultiAgentRwaDiscussionGraph
from .discussion_schemas import (
    AgentState,
    MultiAgentObservability,
    MultiAgentRwaAnalysisRequest,
    MultiAgentRwaAnalysisResponse,
)
from .graph import AgentGraphState, RwaAgentGraph
from .langfuse_integration import (
    LangfuseWorkflowTelemetry,
    create_prompt_registry,
)
from .llm import create_language_model
from .memory import RequestMemory
from .rag import create_retriever
from .schemas import (
    AgentObservability,
    BoardCommentary,
    BriefingRequest,
    BriefingResponse,
    CommentaryRequest,
    EvidenceResponse,
    LlmProvider,
)
from .tools import AgentRuntimeContext, evidence_inventory, lineage_records
from .tracing import LangfuseTraceRecorder, TraceRecorder

AGENT_SERVICE_VERSION = "0.1.0"


class RwaAgentService:
    """Read-only agentic service over calculated RWA dashboard artifacts."""

    def __init__(
        self,
        *,
        settings: AgentServiceSettings | None = None,
        graph: RwaAgentGraph | None = None,
        discussion_graph: MultiAgentRwaDiscussionGraph | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.graph = graph or RwaAgentGraph()
        self.discussion_graph = discussion_graph or MultiAgentRwaDiscussionGraph()

    def run(self, request: BriefingRequest) -> BriefingResponse:
        """Calculate dashboard artifacts from prepared data and run the agent graph."""
        return self.run_from_context(request, self.build_context(request))

    def build_context(self, request: BriefingRequest) -> AgentRuntimeContext:
        """Build the read-only runtime context from prepared project data."""
        from rwa_dashboard.data import (
            current_rwa_snapshot,
            input_package_overview,
            model_run_set,
            regulatory_capital_snapshot,
        )

        controls = request.controls
        snapshot = current_rwa_snapshot(request.as_of_date)
        capital = regulatory_capital_snapshot(request.as_of_date)
        overview = input_package_overview()
        runs = model_run_set(
            as_of_date=request.as_of_date,
            scenario_id=request.scenario_id,
            runoff_months=controls.runoff_months,
            runoff_assets=controls.runoff_assets,
            forecast_assets=controls.forecast_assets,
            monte_carlo_horizon_months=controls.monte_carlo_horizon_months,
            monte_carlo_paths=controls.monte_carlo_paths,
            monte_carlo_assets=controls.monte_carlo_assets,
            steering_assets=controls.steering_assets,
            steering_recommendations=controls.steering_recommendations,
            rats_assets=controls.rats_assets,
            rats_candidates=controls.rats_candidates,
            rats_legs=controls.rats_legs,
            rats_particles=controls.rats_particles,
            rats_iterations=controls.rats_iterations,
        )
        return AgentRuntimeContext(
            as_of_date=request.as_of_date,
            scenario_id=request.scenario_id,
            snapshot=snapshot,
            capital=capital,
            overview=overview,
            runs=runs,
        )

    def run_from_context(
        self,
        request: BriefingRequest,
        context: AgentRuntimeContext,
    ) -> BriefingResponse:
        """Run the agent graph over already calculated dashboard data."""
        provider = self._provider(request.llm_provider)
        language_model = create_language_model(provider, self.settings)
        retriever = create_retriever(
            self.settings.rag_backend,
            weaviate_url=self.settings.weaviate_url,
        )
        trace = self._trace_recorder()
        memory = RequestMemory(
            enabled=request.include_memory or self.settings.memory_scope == "request"
        )
        state = AgentGraphState(
            request=request,
            context=context,
            settings=self.settings,
            language_model=language_model,
            retriever=retriever,
            memory=memory,
            trace=trace,
        )
        final_state = self.graph.run(state)
        if final_state.board_commentary is None:
            raise RuntimeError("Agent graph completed without board commentary.")
        return BriefingResponse(
            service_version=AGENT_SERVICE_VERSION,
            request_id=request.request_id,
            run_id=request.request_id or uuid4().hex,
            as_of_date=context.as_of_date,
            scenario_id=context.scenario_id,
            agent_results=final_state.agent_results,
            board_commentary=final_state.board_commentary,
            metric_facts=final_state.metric_facts,
            evidence_inventory=final_state.evidence_inventory,
            lineage=final_state.lineage,
            limitations=list(dict.fromkeys(final_state.limitations)),
            observability=AgentObservability(
                trace_id=trace.trace_id,
                graph_backend=self.graph.backend_name,
                llm_provider=provider,
                rag_backend=retriever.backend_name,
                memory_scope=memory.scope,
                spans=trace.spans,
            ),
        )

    def evidence_from_context(
        self,
        request: BriefingRequest,
        context: AgentRuntimeContext,
    ) -> EvidenceResponse:
        """Return evidence inventory without running commentary generation."""
        return EvidenceResponse(
            run_id=request.request_id or uuid4().hex,
            as_of_date=context.as_of_date,
            scenario_id=context.scenario_id,
            evidence_inventory=evidence_inventory(context),
            lineage=lineage_records(context),
        )

    def evidence(self, request: BriefingRequest) -> EvidenceResponse:
        """Build evidence inventory from prepared data without commentary generation."""
        return self.evidence_from_context(request, self.build_context(request))

    def generate_commentary(self, request: CommentaryRequest) -> BoardCommentary:
        """Generate board commentary from completed agent results."""
        provider = self._provider(request.llm_provider)
        model = create_language_model(provider, self.settings)
        return model.generate_board_commentary(
            agent_results=request.agent_results,
            metric_facts=request.metric_facts,
            limitations=[],
        )

    async def run_multi_agent_analysis(
        self,
        request: MultiAgentRwaAnalysisRequest,
    ) -> MultiAgentRwaAnalysisResponse:
        """Run the async LangGraph RWA discussion workflow."""
        telemetry = LangfuseWorkflowTelemetry.from_settings(self.settings)
        prompt_registry = create_prompt_registry(self.settings)
        final_state = await self.discussion_graph.arun(
            AgentState.from_request(request),
            prompt_registry=prompt_registry,
            telemetry=telemetry,
        )
        if final_state.final_commentary is None:
            raise RuntimeError("Multi-agent graph completed without final commentary.")
        return MultiAgentRwaAnalysisResponse(
            service_version=AGENT_SERVICE_VERSION,
            request_id=request.request_id,
            run_id=request.request_id or uuid4().hex,
            status=final_state.final_commentary.status,
            graph_backend=self.discussion_graph.backend_name,
            final_commentary=final_state.final_commentary,
            messages=final_state.messages,
            validation_flags=final_state.validation_flags,
            agent_findings=final_state.agent_findings,
            recommended_actions=final_state.recommended_actions,
            commentary_views=final_state.commentary_views,
            observability=MultiAgentObservability(
                langfuse_enabled=telemetry.enabled,
                trace_id=telemetry.trace_id,
                callback_handler_attached=telemetry.callback_handler_attached,
                checkpointer=self.discussion_graph.checkpointer_name,
                prompt_usages=telemetry.prompt_usages,
                evaluation_scores=telemetry.evaluation_scores,
                guardrail_results=telemetry.guardrail_results,
                guardrail_block_count=sum(
                    1 for result in telemetry.guardrail_results if result.action == "blocked"
                ),
                pii_detected=any(
                    result.scanner_name == "PII" and result.action != "passed"
                    for result in telemetry.guardrail_results
                ),
                prompt_injection_risk=max(
                    (
                        result.risk_score
                        for result in telemetry.guardrail_results
                        if result.scanner_name == "PromptInjection"
                    ),
                    default=Decimal("0"),
                ),
                node_transition_count=telemetry.node_transition_count,
                llm_call_count=telemetry.llm_call_count,
                tool_call_count=telemetry.tool_call_count,
                total_token_count=telemetry.total_token_count,
            ),
        )

    def health(self) -> dict[str, str | bool]:
        """Return lightweight service metadata for liveness probes."""
        return {
            "status": "ok",
            "service": "rwa-agent-service",
            "service_version": AGENT_SERVICE_VERSION,
            "llm_provider": self.settings.llm_provider,
            "ollama_model": self.settings.ollama_model,
            "rag_backend": self.settings.rag_backend,
            "langfuse_enabled": self.settings.langfuse_enabled,
            "langsmith_enabled": self.settings.langsmith_enabled,
            "memory_scope": self.settings.memory_scope,
        }

    def _provider(self, request_provider: LlmProvider | None) -> LlmProvider:
        return request_provider or self.settings.llm_provider

    def _trace_recorder(self) -> TraceRecorder:
        if self.settings.langfuse_enabled:
            return LangfuseTraceRecorder()
        return TraceRecorder()
