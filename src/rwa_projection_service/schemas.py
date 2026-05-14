from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic_settings import BaseSettings


class ProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        return value


class RunInstructions(BaseSettings):
    run_date: date = Field(default_factory=date.today)
    projected_months: int = Field(default=24, gt=0, le=24)


class ProjectionRequest(ProjectionModel):
    regulatory_reference_version: str = Field(default="basel_iii_final_reforms_2017")
    run_date: date = Field(default_factory=date.today)
    projected_months: int = Field(default=24, gt=0, le=24)
    core_info: list[dict[str, Any]] = Field(min_length=1)
    country_info: list[dict[str, Any]] | None = None


class OutputSummary(ProjectionModel):
    input_data_records: int = Field(ge=0)
    output_successful_records: int = Field(ge=0)
    output_successful_projection_records: int = Field(ge=0)
    output_failure_records: int = Field(ge=0)


class ProjectionError(ProjectionModel):
    id: str
    projection_date: date | None = None
    messages: list[str]


class OutputProjection(ProjectionModel):
    id: str
    projection_date: date
    basel_3_0_rw_final: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_0_rwa: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_0_ro_rw: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_rw_foundation: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_rwa_foundation: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_ro_rw_foundation: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_rw_standardised: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_rwa_standardised: Decimal | None = Field(default=None, ge=Decimal("0"))
    basel_3_1_ro_rw_standardised: Decimal | None = Field(default=None, ge=Decimal("0"))


class ProjectionResponse(ProjectionModel):
    regulatory_reference_version: str
    calculation_engine_version: str
    projection_engine_version: str
    run_date: date
    projected_months: int
    projection_dates: list[date]
    summary: OutputSummary
    results: list[dict[str, Any]]
    projections: list[OutputProjection]
    errors: list[ProjectionError] = Field(default_factory=list)
