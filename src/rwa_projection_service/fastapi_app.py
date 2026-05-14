from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH

from .engine import PROJECTION_ENGINE_VERSION, RwaProjectionService
from .schemas import ProjectionRequest, ProjectionResponse


class ProjectionServiceSettings(BaseSettings):
    nccr_mapping_path: Path = NCCR_MAPPING_PATH
    country_info_path: Path = PREPROD_COUNTRY_INFO_PATH


def create_app(settings: ProjectionServiceSettings | None = None) -> FastAPI:
    resolved_settings = settings or ProjectionServiceSettings()
    service = RwaProjectionService(
        nccr_mapping_path=resolved_settings.nccr_mapping_path,
        country_info_path=resolved_settings.country_info_path,
    )

    app = FastAPI(
        title="RWA Projection Service",
        version=PROJECTION_ENGINE_VERSION,
        description=(
            "Projection service for Basel/RWA time series using the rwa_calculator calculator."
        ),
    )
    app.state.settings = resolved_settings
    app.state.service = service

    @app.get("/health", tags=["service"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "rwa-projection-service",
            "projection_engine_version": PROJECTION_ENGINE_VERSION,
        }

    @app.post("/projections/calculate", response_model=ProjectionResponse, tags=["projection"])
    def calculate(request: ProjectionRequest) -> ProjectionResponse:
        return app.state.service.calculate(request)

    return app


app = create_app()
