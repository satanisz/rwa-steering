from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .engine import RwaSteeringService
from .errors import SteeringDomainError
from .schemas import ApiErrorDetail, ApiErrorResponse, SteeringRequest, SteeringResponse

STEERING_ENGINE_VERSION = "rwa-steering-service-0.1.0"


def create_app() -> FastAPI:
    """Create the FastAPI application for the steering service.

    The app is intentionally thin: request validation is handled by Pydantic schemas and all
    business logic lives in ``RwaSteeringService`` so it can be tested without HTTP.
    """

    service = RwaSteeringService()
    app = FastAPI(
        title="RWA Steering API",
        version=STEERING_ENGINE_VERSION,
        description="Regime-aware RWA forecasting, attribution and steering recommendations.",
    )
    app.state.service = service

    @app.exception_handler(SteeringDomainError)
    async def steering_domain_error_handler(
        request: Request, exc: SteeringDomainError
    ) -> JSONResponse:
        """Return stable structured errors for domain and input-package failures."""
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

    @app.get("/v1/health", tags=["service"])
    @app.get("/health", tags=["service"])
    def health() -> dict[str, str]:
        """Return lightweight liveness metadata for the steering API."""
        return {
            "status": "ok",
            "service": "rwa-steering-service",
            "steering_engine_version": STEERING_ENGINE_VERSION,
            "input_package_version": app.state.service.input_package.manifest.version_id,
            "input_package_validation_status": (
                app.state.service.input_package.manifest.validation_status
            ),
        }

    @app.post("/v1/steering/run", response_model=SteeringResponse, tags=["steering"])
    @app.post("/steering/run", response_model=SteeringResponse, tags=["steering"])
    def run(request: SteeringRequest) -> SteeringResponse:
        """Run deterministic steering for the requested scenarios."""
        return app.state.service.run(request)

    return app


app = create_app()
