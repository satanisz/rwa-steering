from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rwa_steering.errors import SteeringDomainError

from .discussion_schemas import MultiAgentRwaAnalysisRequest, MultiAgentRwaAnalysisResponse
from .schemas import (
    ApiErrorDetail,
    ApiErrorResponse,
    BoardCommentary,
    BriefingRequest,
    BriefingResponse,
    CommentaryRequest,
    EvidenceResponse,
)
from .service import AGENT_SERVICE_VERSION, RwaAgentService


def create_app() -> FastAPI:
    """Create the FastAPI app for the RWA agent service."""
    service = RwaAgentService()
    app = FastAPI(
        title="RWA Agent Service",
        version=AGENT_SERVICE_VERSION,
        description="Read-only agentic AI service for RWA commentary, evidence and lineage.",
    )
    app.state.service = service

    @app.exception_handler(SteeringDomainError)
    async def steering_domain_error_handler(
        request: Request, exc: SteeringDomainError
    ) -> JSONResponse:
        """Return stable structured errors for prepared-data failures."""
        _ = request
        payload = ApiErrorResponse(
            error=ApiErrorDetail(
                code=exc.detail.code,
                message=exc.detail.message,
                field_path=exc.detail.field_path,
                severity=exc.detail.severity,
                remediation=exc.detail.remediation,
                context=exc.detail.context,
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.get("/v1/agents/health", tags=["service"])
    @app.get("/health", tags=["service"])
    def health() -> dict[str, str | bool]:
        """Return lightweight liveness metadata."""
        return app.state.service.health()

    @app.post("/v1/agents/briefing/run", response_model=BriefingResponse, tags=["agents"])
    @app.post("/agents/briefing/run", response_model=BriefingResponse, tags=["agents"])
    def run_briefing(request: BriefingRequest) -> BriefingResponse:
        """Run the complete read-only briefing graph."""
        return app.state.service.run(request)

    @app.post("/v1/agents/commentary/run", response_model=BoardCommentary, tags=["agents"])
    @app.post("/agents/commentary/run", response_model=BoardCommentary, tags=["agents"])
    def run_commentary(request: CommentaryRequest) -> BoardCommentary:
        """Generate board commentary from completed agent findings."""
        return app.state.service.generate_commentary(request)

    @app.post("/v1/agents/evidence/run", response_model=EvidenceResponse, tags=["agents"])
    @app.post("/agents/evidence/run", response_model=EvidenceResponse, tags=["agents"])
    def run_evidence(request: BriefingRequest) -> EvidenceResponse:
        """Build the evidence inventory from prepared dashboard data."""
        return app.state.service.evidence(request)

    @app.post(
        "/v1/agents/rwa-analysis/run",
        response_model=MultiAgentRwaAnalysisResponse,
        tags=["agents"],
    )
    @app.post(
        "/agents/rwa-analysis/run",
        response_model=MultiAgentRwaAnalysisResponse,
        tags=["agents"],
    )
    async def run_multi_agent_analysis(
        request: MultiAgentRwaAnalysisRequest,
    ) -> MultiAgentRwaAnalysisResponse:
        """Run the multi-agent RWA analysis discussion graph."""
        return await app.state.service.run_multi_agent_analysis(request)

    return app


app = create_app()
