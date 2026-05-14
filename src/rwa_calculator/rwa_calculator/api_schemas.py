from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from rwa_calculator.rwa_pydantic_schemas import CoreInfoRecord, CountryInfoRecord


class ApiModel(BaseModel):
    """Base API model with strict validation and Decimal-safe JSON rendering."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Serialise Decimal values as strings for lossless API payloads."""
        if isinstance(value, Decimal):
            return str(value)
        return value


class RuleReference(ApiModel):
    """Reference to a regulatory or project rule used by a trace step."""

    source_document: str
    section: str
    pdf_page: int | None = None
    paragraph: str | None = None
    table: str | None = None


class CalculationTraceStep(ApiModel):
    """Human-readable audit step emitted when trace output is requested."""

    step_id: str
    description: str
    input_values: dict[str, str] = Field(default_factory=dict)
    formula: str | None = None
    output_values: dict[str, str] = Field(default_factory=dict)
    rule_reference: RuleReference | None = None


class RwaResult(ApiModel):
    """Successful point-in-time RWA calculation for one exposure."""

    id: str
    counterparty_gid: str
    basel_3_0_pd: Decimal
    basel_3_1_pd: Decimal
    basel_3_0_dlgd: Decimal
    basel_3_1_dlgd: Decimal
    basel_3_0_rw_final: Decimal
    basel_3_0_rwa: Decimal
    basel_3_0_ro_rw: Decimal
    basel_3_1_rw_foundation: Decimal
    basel_3_1_rwa_foundation: Decimal
    basel_3_1_ro_rw_foundation: Decimal
    basel_3_1_rw_standardised: Decimal
    basel_3_1_rwa_standardised: Decimal
    basel_3_1_ro_rw_standardised: Decimal
    basel_3_1_rw_final: Decimal
    basel_3_1_rwa_final: Decimal
    basel_3_1_ro_rw_final: Decimal
    trace: list[CalculationTraceStep] | None = None


class RwaProjection(ApiModel):
    """Legacy one-date projection shape returned by the calculator adapter."""

    id: str
    projection_date: date
    basel_3_0_rw_final: Decimal | None = None
    basel_3_0_rwa: Decimal | None = None
    basel_3_0_ro_rw: Decimal | None = None
    basel_3_1_rw_foundation: Decimal | None = None
    basel_3_1_rwa_foundation: Decimal | None = None
    basel_3_1_ro_rw_foundation: Decimal | None = None
    basel_3_1_rw_standardised: Decimal | None = None
    basel_3_1_rwa_standardised: Decimal | None = None
    basel_3_1_ro_rw_standardised: Decimal | None = None


class RwaError(ApiModel):
    """Calculator error for one input row."""

    id: str
    messages: list[str]


class OutputSummary(ApiModel):
    """Record counts for a calculator request."""

    input_data_records: int = Field(ge=0)
    output_successful_records: int = Field(ge=0)
    output_successful_projection_records: int = Field(ge=0)
    output_failure_records: int = Field(ge=0)


class CalculateRequest(ApiModel):
    """JSON request accepted by the RWA calculator API."""

    regulatory_reference_version: str = Field(default="basel_iii_final_reforms_2017")
    include_trace: bool = False
    projection_date: date | None = None
    core_info: list[CoreInfoRecord] = Field(min_length=1)
    country_info: list[CountryInfoRecord] | None = None


class CalculateResponse(ApiModel):
    """JSON response returned by the RWA calculator API."""

    regulatory_reference_version: str
    calculation_engine_version: str
    summary: OutputSummary
    results: list[RwaResult]
    projections: list[RwaProjection] = Field(default_factory=list)
    errors: list[RwaError] = Field(default_factory=list)


class HealthResponse(ApiModel):
    """Health endpoint payload with dependency and reference-data metadata."""

    status: str
    service: str
    calculation_engine_version: str
    normal_distribution_backend: str
    reference_data_package_id: str | None = None
    reference_data_package_version: str | None = None
    reference_data_production_ready: bool | None = None


def pydantic_row_to_engine_row(model: BaseModel) -> dict[str, Any]:
    """Convert validated API models into the row dictionaries expected by the engine."""
    row = model.model_dump(mode="python")
    normalised: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Enum):
            normalised[key] = value.value
        elif isinstance(value, Decimal):
            normalised[key] = value
        elif isinstance(value, date):
            normalised[key] = value.isoformat()
        elif value is None:
            normalised[key] = ""
        else:
            normalised[key] = value
    return normalised
