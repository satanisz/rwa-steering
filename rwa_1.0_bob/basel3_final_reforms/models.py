"""
Data models for RWA calculations using existing Pydantic schemas.
"""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field
from rwa_pydantic_schemas import (
    CoreInfoRecord,
    CountryInfoRecord,
    OutputSuccessRecord,
    RwaError,
    OutputSummary,
)


class RwaCalculationRequest(BaseModel):
    """Request model for RWA calculation."""
    
    core_info: List[CoreInfoRecord]
    country_info: List[CountryInfoRecord]
    
    class Config:
        arbitrary_types_allowed = True


class RwaCalculationResponse(BaseModel):
    """Response model for RWA calculation."""
    
    success_records: List[OutputSuccessRecord] = Field(default_factory=list)
    errors: List[RwaError] = Field(default_factory=list)
    summary: OutputSummary
    
    class Config:
        arbitrary_types_allowed = True


class ExposureCalculationTrace(BaseModel):
    """Detailed trace of calculation steps for an exposure."""
    
    exposure_id: str
    entity_class: str
    risk_weight_pct: Decimal
    exposure_amount: Decimal
    rwa: Decimal
    calculation_steps: List[str] = Field(default_factory=list)
    applied_rules: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True

# Made with Bob
