from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictRwaModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


Code = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")]
CountryCode = Annotated[str, Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]


NCCR_RATING_GRADES = (
    "0.1",
    "1.1",
    "1.2",
    "2.1",
    "2.2",
    "3.1",
    "3.2",
    "3.3",
    "4.1",
    "4.2",
    "4.3",
    "5.1",
    "5.2",
    "5.3",
    "6.1",
    "6.2",
    "7.1",
    "7.2",
    "8.1",
    "8.2",
    "8.3",
)


class ExternalRating(str, Enum):
    AAA = "AAA"
    AA_PLUS = "AA+"
    AA = "AA"
    AA_MINUS = "AA-"
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    BBB_PLUS = "BBB+"
    BBB = "BBB"
    BBB_MINUS = "BBB-"
    BB_PLUS = "BB+"
    BB = "BB"
    BB_MINUS = "BB-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    CCC = "CCC"
    CC = "CC"
    C = "C"
    D = "D"
    UNRATED = "UNRATED"


class EntityClass(str, Enum):
    SOV = "SOV"
    CORP = "CORP"
    BANK = "BANK"
    PSE = "PSE"
    MDB = "MDB"
    FI = "FI"
    RETAIL = "RETAIL"
    OTHER = "OTHER"


class ExposureSubClass(str, Enum):
    GENERAL = "GENERAL"
    SOVEREIGN = "SOVEREIGN"
    BANK = "BANK"
    FINANCIAL_INSTITUTION = "FINANCIAL_INSTITUTION"
    CORPORATE = "CORPORATE"
    SPECIALISED_LENDING = "SPECIALISED_LENDING"
    PROJECT_FINANCE = "PROJECT_FINANCE"
    OBJECT_FINANCE = "OBJECT_FINANCE"
    COMMODITIES_FINANCE = "COMMODITIES_FINANCE"
    RESIDENTIAL_REAL_ESTATE = "RESIDENTIAL_REAL_ESTATE"
    COMMERCIAL_REAL_ESTATE = "COMMERCIAL_REAL_ESTATE"
    RETAIL = "RETAIL"
    OTHER = "OTHER"


class CounterpartyCreditQualityGrade(str, Enum):
    INVESTMENT_GRADE = "INVESTMENT_GRADE"
    HIGH_YIELD = "HIGH_YIELD"
    NOT_RATED = "NOT_RATED"


def _normalise_empty(value: Any) -> Any:
    if value == "":
        return None
    return value


def _normalise_rating_grade(value: Any) -> str | None:
    value = _normalise_empty(value)
    if value is None:
        return None
    if isinstance(value, Decimal):
        normalised = format(value.normalize(), "f")
    elif isinstance(value, (float, int)):
        normalised = str(value)
    else:
        normalised = str(value).strip()
    if normalised.endswith(".0"):
        normalised = normalised[:-2]
    if normalised not in NCCR_RATING_GRADES:
        allowed = ", ".join(NCCR_RATING_GRADES)
        raise ValueError(f"Unknown NCCR rating grade {normalised!r}; expected one of: {allowed}")
    return normalised


def _normalise_decimal(value: Any) -> Any:
    value = _normalise_empty(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith("%"):
            return Decimal(stripped[:-1]) / Decimal("100")
        return stripped
    return value


class CoreInfoRecord(StrictRwaModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    counterparty_gid: Annotated[str, Field(min_length=1, max_length=64)]
    hsbc_intragroup_flag: Literal["Y", "N"]
    counterparty_fcy_internal_rating: str
    counterparty_lcy_internal_rating: str
    incorporation_country: CountryCode
    lgd_classification: Code
    pd_classification: Code
    entity_class: EntityClass
    sub_class: ExposureSubClass
    counterparty_dlgd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
    govt_guarantee_flag: Literal["Y", "N"]
    trade_external_rating: ExternalRating | None = None
    counterparty_external_rating: ExternalRating | None = None
    avc: Annotated[Decimal, Field(ge=Decimal("1"), le=Decimal("1.25"))]
    pra_io_mdb_3_1_flag: Literal["Y", "N"]
    exposure_ccy: CurrencyCode
    bond_or_loan_flag: Literal["B", "L"]
    original_maturity: Annotated[Decimal, Field(ge=Decimal("0"))]
    residual_maturity: Annotated[Decimal, Field(ge=Decimal("0"))]
    exposure_amount: Annotated[Decimal, Field(ge=Decimal("0"))]
    expected_yield: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    counterparty_credit_quality_grade: CounterpartyCreditQualityGrade

    _validate_fcy_rating = field_validator("counterparty_fcy_internal_rating", mode="before")(
        _normalise_rating_grade
    )
    _validate_lcy_rating = field_validator("counterparty_lcy_internal_rating", mode="before")(
        _normalise_rating_grade
    )

    @field_validator(
        "counterparty_dlgd",
        "avc",
        "original_maturity",
        "residual_maturity",
        "exposure_amount",
        "expected_yield",
        mode="before",
    )
    @classmethod
    def normalise_decimal_fields(cls, value: Any) -> Any:
        return _normalise_decimal(value)

    @field_validator("trade_external_rating", "counterparty_external_rating", mode="before")
    @classmethod
    def normalise_optional_rating(cls, value: Any) -> Any:
        return _normalise_empty(value)

    @field_validator("avc")
    @classmethod
    def validate_avc(cls, value: Decimal) -> Decimal:
        if value not in {Decimal("1"), Decimal("1.0"), Decimal("1.25")}:
            raise ValueError("AVC must be either 1.0 or 1.25")
        return Decimal("1.0") if value == Decimal("1") else value

    @model_validator(mode="after")
    def validate_maturities_and_flags(self) -> CoreInfoRecord:
        if self.residual_maturity > self.original_maturity:
            raise ValueError("residual_maturity cannot exceed original_maturity")
        if self.entity_class == EntityClass.MDB and self.pra_io_mdb_3_1_flag != "Y":
            raise ValueError("MDB exposures must set pra_io_mdb_3_1_flag to Y")
        if self.entity_class in {EntityClass.BANK, EntityClass.FI} and self.avc != Decimal("1.25"):
            raise ValueError("BANK and FI exposures must use AVC 1.25 in this schema version")
        return self


class CountryInfoRecord(StrictRwaModel):
    incorporation_country: CountryCode
    local_currency: CurrencyCode
    country_dlgd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))] | None = None
    eea_country_flag: Literal["Y", "N"]
    eea_country_ten_percent_dlgd_flag: Literal["Y", "N"]
    country_internal_rating: str | None = None
    country_external_rating: ExternalRating | None = None
    sov_concessionary_flag: Literal["Y", "N"]

    _validate_country_rating = field_validator("country_internal_rating", mode="before")(
        _normalise_rating_grade
    )

    @field_validator("country_dlgd", mode="before")
    @classmethod
    def normalise_country_dlgd(cls, value: Any) -> Any:
        return _normalise_decimal(value)

    @field_validator("country_external_rating", mode="before")
    @classmethod
    def normalise_country_external_rating(cls, value: Any) -> Any:
        return _normalise_empty(value)


class RwaOutputBase(StrictRwaModel):
    basel_3_0_rw_final: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_0_rwa: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_0_ro_rw: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_rw_foundation: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_rwa_foundation: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_ro_rw_foundation: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_rw_standardised: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_rwa_standardised: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_ro_rw_standardised: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def normalise_output_decimals(cls, value: Any) -> Any:
        return _normalise_decimal(value)


class OutputSuccessRecord(RwaOutputBase):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    counterparty_gid: Annotated[str, Field(min_length=1, max_length=64)]
    basel_3_0_pd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))] | None = None
    basel_3_1_pd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))] | None = None
    basel_3_0_dlgd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))] | None = None
    basel_3_1_dlgd: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))] | None = None
    basel_3_1_rw_final: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_rwa_final: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    basel_3_1_ro_rw_final: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None


class OutputProjectionRecord(RwaOutputBase):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    projection_date: date


class RwaError(StrictRwaModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    messages: list[Annotated[str, Field(min_length=1)]]


class OutputErrorResponse(StrictRwaModel):
    errors: list[RwaError] = Field(default_factory=list)


class OutputSummary(StrictRwaModel):
    input_data_records: Annotated[int, Field(ge=0)]
    output_successful_records: Annotated[int, Field(ge=0)]
    output_successful_projection_records: Annotated[int, Field(ge=0)]
    output_failure_records: Annotated[int, Field(ge=0)]


class RequestedFx(StrictRwaModel):
    currencies: list[CurrencyCode] = Field(default_factory=list)


CORE_INFO_COLUMNS = tuple(CoreInfoRecord.model_fields.keys())
COUNTRY_INFO_COLUMNS = tuple(CountryInfoRecord.model_fields.keys())
OUTPUT_SUCCESS_COLUMNS = tuple(OutputSuccessRecord.model_fields.keys())
OUTPUT_PROJECTION_COLUMNS = tuple(OutputProjectionRecord.model_fields.keys())
