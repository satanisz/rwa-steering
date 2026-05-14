from __future__ import annotations

from fastapi import FastAPI

from .engine import RwaSteeringPocService
from .schemas import SteeringRequest, SteeringResponse

STEERING_ENGINE_VERSION = "rwa-steering-poc-0.1.0"


def create_app() -> FastAPI:
    service = RwaSteeringPocService()
    app = FastAPI(
        title="RWA Steering PoC",
        version=STEERING_ENGINE_VERSION,
        description="Regime-aware RWA forecasting, attribution and steering recommendations.",
    )
    app.state.service = service

    @app.get("/health", tags=["service"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "rwa-steering-poc",
            "steering_engine_version": STEERING_ENGINE_VERSION,
        }

    @app.post("/steering/run", response_model=SteeringResponse, tags=["steering"])
    def run(request: SteeringRequest) -> SteeringResponse:
        return app.state.service.run(request)

    return app


app = create_app()
