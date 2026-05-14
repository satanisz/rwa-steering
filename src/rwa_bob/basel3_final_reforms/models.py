"""
Data models for RWA calculations using existing Pydantic schemas.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from rwa_bob.rwa_pydantic_schemas import (
    CoreInfoRecord,
    CountryInfoRecord,
    OutputSuccessRecord,
    OutputSummary,
    RwaError,
)


class RwaCalculationRequest(BaseModel):
    """Request model for RWA calculation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    core_info: list[CoreInfoRecord]
    country_info: list[CountryInfoRecord]


class RwaCalculationResponse(BaseModel):
    """Response model for RWA calculation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success_records: list[OutputSuccessRecord] = Field(default_factory=list)
    errors: list[RwaError] = Field(default_factory=list)
    summary: OutputSummary


class ExposureCalculationTrace(BaseModel):
    """Detailed trace of calculation steps for an exposure."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    exposure_id: str
    entity_class: str
    risk_weight_pct: Decimal
    exposure_amount: Decimal
    rwa: Decimal
    calculation_steps: list[str] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)


# Made with Bob
