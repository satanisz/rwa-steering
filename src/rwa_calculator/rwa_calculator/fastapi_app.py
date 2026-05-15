from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH, REFERENCE_DATA_ROOT

from .api_schemas import (
    CalculateRequest,
    CalculateResponse,
    HealthResponse,
    pydantic_row_to_engine_row,
)
from .calculator import RwaCalculator
from .capital import (
    calculate_cva_risk,
    calculate_leverage_ratio,
    calculate_operational_risk,
    calculate_output_floor,
    calculate_portfolio_capital,
)
from .capital_models import (
    CvaRiskRequest,
    CvaRiskResponse,
    LeverageRatioRequest,
    LeverageRatioResponse,
    OperationalRiskRequest,
    OperationalRiskResponse,
    OutputFloorRequest,
    OutputFloorResponse,
    PortfolioCapitalRequest,
    PortfolioCapitalResponse,
)
from .models import CountryInfoRecord
from .normal_distribution import NormalDistribution
from .pandera_validation import read_core_csv_bytes, read_country_csv_bytes
from .reference import ReferenceDataPackage

CALCULATION_ENGINE_VERSION = "rwa-alpha-0.2.0"


class ServiceSettings:
    """File-system configuration for the calculator microservice."""

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
        reference_data_root: str | Path = REFERENCE_DATA_ROOT,
    ) -> None:
        """Resolve configured reference-data paths to `Path` objects."""
        self.nccr_mapping_path = Path(nccr_mapping_path)
        self.country_info_path = Path(country_info_path)
        self.reference_data_root = Path(reference_data_root)


def get_settings() -> ServiceSettings:
    """Return default settings for framework integrations and tests."""
    return ServiceSettings()


def build_calculator(settings: ServiceSettings) -> RwaCalculator:
    """Build a calculator instance from service settings."""
    return RwaCalculator.from_files(settings.nccr_mapping_path, settings.country_info_path)


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    """Create the calculator FastAPI app and attach shared service dependencies."""
    resolved_settings = settings or ServiceSettings()
    calculator = build_calculator(resolved_settings)
    normal_distribution = NormalDistribution()
    reference_data_package = ReferenceDataPackage(resolved_settings.reference_data_root)

    app = FastAPI(
        title="RWA Calculator Microservice",
        version=CALCULATION_ENGINE_VERSION,
        description="Basel/RWA calculator for pre-production portfolio integration.",
    )
    app.state.settings = resolved_settings
    app.state.calculator = calculator
    app.state.normal_distribution = normal_distribution
    app.state.reference_data_package = reference_data_package

    def get_calculator() -> RwaCalculator:
        """Provide the app-scoped calculator to request handlers."""
        return app.state.calculator

    @app.get("/v1/health", response_model=HealthResponse, tags=["service"])
    @app.get("/health", response_model=HealthResponse, tags=["service"])
    def health() -> HealthResponse:
        """Return liveness and dependency metadata for monitoring."""
        return HealthResponse(
            status="ok",
            service="rwa-calculator",
            calculation_engine_version=CALCULATION_ENGINE_VERSION,
            normal_distribution_backend=app.state.normal_distribution.backend,
            reference_data_package_id=app.state.reference_data_package.package_id,
            reference_data_package_version=app.state.reference_data_package.package_version,
            reference_data_production_ready=app.state.reference_data_package.production_ready,
        )

    @app.get("/v1/readiness", tags=["service"])
    @app.get("/readiness", tags=["service"])
    def readiness() -> dict[str, str]:
        """Verify that required reference-data files are available on disk."""
        settings_obj: ServiceSettings = app.state.settings
        for path in (
            settings_obj.nccr_mapping_path,
            settings_obj.country_info_path,
            settings_obj.reference_data_root / "manifest.json",
        ):
            if not path.exists():
                raise HTTPException(status_code=503, detail=f"Missing reference file: {path}")
        return {"status": "ready"}

    @app.get("/reference/nccr", tags=["reference"])
    def nccr_reference(calc: RwaCalculator = Depends(get_calculator)) -> dict:
        """Expose the loaded NCCR mapping for debugging and audit inspection."""
        return calc.nccr_mapping

    @app.get("/reference/manifest", tags=["reference"])
    def reference_manifest() -> dict:
        """Expose the reference-data manifest currently used by the service."""
        return app.state.reference_data_package.manifest

    @app.get("/reference/baseline", tags=["reference"])
    def reference_baseline() -> dict:
        """Expose baseline reference-data package contents."""
        return app.state.reference_data_package.baseline

    @app.get("/reference/jurisdictions/{jurisdiction_id}", tags=["reference"])
    def reference_jurisdiction(jurisdiction_id: str) -> dict:
        """Expose one jurisdiction-specific reference-data overlay."""
        try:
            return app.state.reference_data_package.jurisdiction(jurisdiction_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/countries", tags=["reference"])
    def countries(calc: RwaCalculator = Depends(get_calculator)) -> dict:
        """Expose country reference records loaded into the calculator."""
        return {code: asdict(country) for code, country in calc.countries.items()}

    @app.post("/v1/rwa/calculate", response_model=CalculateResponse, tags=["calculation"])
    @app.post("/rwa/calculate", response_model=CalculateResponse, tags=["calculation"])
    def calculate(
        request: CalculateRequest,
        calc: RwaCalculator = Depends(get_calculator),
    ) -> CalculateResponse:
        """Calculate RWA for a JSON portfolio slice."""
        rows = [pydantic_row_to_engine_row(row) for row in request.core_info]
        if request.country_info:
            countries = {
                country.incorporation_country: CountryInfoRecord.from_mapping(
                    pydantic_row_to_engine_row(country)
                )
                for country in request.country_info
            }
            calc = RwaCalculator(
                nccr_mapping_path=calc.nccr_mapping_path,
                countries=countries,
                nccr_mapping=calc.nccr_mapping,
            )

        payload = calc.calculate_batch(
            rows,
            include_trace=request.include_trace,
            projection_date=request.projection_date.isoformat()
            if request.projection_date
            else None,
        )
        return CalculateResponse(
            regulatory_reference_version=request.regulatory_reference_version,
            calculation_engine_version=CALCULATION_ENGINE_VERSION,
            **payload,
        )

    @app.post("/v1/rwa/calculate/csv", response_model=CalculateResponse, tags=["calculation"])
    @app.post("/rwa/calculate/csv", response_model=CalculateResponse, tags=["calculation"])
    async def calculate_csv(
        core_file: UploadFile = File(description="CoreInfo CSV"),
        country_file: UploadFile | None = File(
            default=None, description="Optional CountryInfo CSV"
        ),
        include_trace: bool = False,
        projection_date: str | None = None,
        regulatory_reference_version: str = "basel_iii_final_reforms_2017",
        calc: RwaCalculator = Depends(get_calculator),
    ) -> CalculateResponse:
        """Calculate RWA for uploaded CoreInfo and optional CountryInfo CSV files."""
        try:
            rows = read_core_csv_bytes(await core_file.read())
            if country_file is not None:
                country_rows = read_country_csv_bytes(await country_file.read())
                countries = {
                    row["incorporation_country"]: CountryInfoRecord.from_mapping(row)
                    for row in country_rows
                }
                calc = RwaCalculator(
                    nccr_mapping_path=calc.nccr_mapping_path,
                    countries=countries,
                    nccr_mapping=calc.nccr_mapping,
                )
            payload = calc.calculate_batch(
                rows, include_trace=include_trace, projection_date=projection_date
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return CalculateResponse(
            regulatory_reference_version=regulatory_reference_version,
            calculation_engine_version=CALCULATION_ENGINE_VERSION,
            **payload,
        )

    @app.post(
        "/v1/output-floor/calculate",
        response_model=OutputFloorResponse,
        tags=["capital"],
    )
    def output_floor(request: OutputFloorRequest) -> OutputFloorResponse:
        """Calculate aggregate output floor using portfolio-level RWA inputs."""
        return calculate_output_floor(request)

    @app.post(
        "/v1/operational-risk/calculate",
        response_model=OperationalRiskResponse,
        tags=["capital"],
    )
    def operational_risk(request: OperationalRiskRequest) -> OperationalRiskResponse:
        """Calculate operational risk BI, BIC, ILM, ORC and RWA."""
        return calculate_operational_risk(request)

    @app.post("/v1/cva/calculate", response_model=CvaRiskResponse, tags=["capital"])
    def cva_risk(request: CvaRiskRequest) -> CvaRiskResponse:
        """Calculate CVA capital under materiality, BA-CVA or SA-CVA paths."""
        try:
            return calculate_cva_risk(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/v1/leverage-ratio/calculate",
        response_model=LeverageRatioResponse,
        tags=["capital"],
    )
    def leverage_ratio(request: LeverageRatioRequest) -> LeverageRatioResponse:
        """Calculate leverage ratio exposure measure and buffer shortfall."""
        return calculate_leverage_ratio(request)

    @app.post(
        "/v1/capital/portfolio",
        response_model=PortfolioCapitalResponse,
        tags=["capital"],
    )
    def portfolio_capital(request: PortfolioCapitalRequest) -> PortfolioCapitalResponse:
        """Aggregate risk-type RWAs and apply the output floor."""
        return calculate_portfolio_capital(request)

    return app


app = create_app()
