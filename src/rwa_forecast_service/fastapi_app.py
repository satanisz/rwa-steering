from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rwa_steering.errors import SteeringDomainError

from .engine import FORECAST_ENGINE_VERSION, RwaForecastService
from .schemas import ApiErrorDetail, ApiErrorResponse, ForecastRequest, ForecastResponse


def create_app() -> FastAPI:
    """Create the FastAPI app for the autoregressive forecast service."""
    service = RwaForecastService()
    app = FastAPI(
        title="RWA Forecast Service",
        version=FORECAST_ENGINE_VERSION,
        description="VAR/LSTM-proxy market forecast and Monte Carlo RWA path simulation.",
    )
    app.state.service = service

    @app.exception_handler(SteeringDomainError)
    async def steering_domain_error_handler(
        request: Request, exc: SteeringDomainError
    ) -> JSONResponse:
        """Return stable structured errors for domain and generated-input failures."""
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
        """Return lightweight liveness metadata for orchestration probes."""
        return {
            "status": "ok",
            "service": "rwa-forecast-service",
            "forecast_engine_version": FORECAST_ENGINE_VERSION,
            "input_package_version": app.state.service.input_package.manifest.version_id,
            "input_package_validation_status": (
                app.state.service.input_package.manifest.validation_status
            ),
        }

    @app.post("/v1/forecasts/run", response_model=ForecastResponse, tags=["forecast"])
    @app.post("/forecasts/run", response_model=ForecastResponse, tags=["forecast"])
    def run(request: ForecastRequest) -> ForecastResponse:
        """Run autoregressive forecast and Monte Carlo trajectory scoring."""
        return app.state.service.run(request)

    return app


app = create_app()
