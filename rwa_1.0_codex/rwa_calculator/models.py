from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


NCCR_RATING_GRADES = {
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
}

EXTERNAL_RATINGS = {
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC",
    "CC",
    "C",
    "D",
    "UNRATED",
}

ENTITY_CLASSES = {"SOV", "CORP", "BANK", "PSE", "MDB", "FI", "RETAIL", "OTHER"}
EXPOSURE_SUB_CLASSES = {
    "GENERAL",
    "SOVEREIGN",
    "BANK",
    "FINANCIAL_INSTITUTION",
    "CORPORATE",
    "SPECIALISED_LENDING",
    "PROJECT_FINANCE",
    "OBJECT_FINANCE",
    "COMMODITIES_FINANCE",
    "RESIDENTIAL_REAL_ESTATE",
    "COMMERCIAL_REAL_ESTATE",
    "RETAIL",
    "OTHER",
}
COUNTERPARTY_CREDIT_QUALITY_GRADES = {"INVESTMENT_GRADE", "HIGH_YIELD", "NOT_RATED"}

CORE_INFO_COLUMNS = (
    "id",
    "counterparty_gid",
    "hsbc_intragroup_flag",
    "counterparty_fcy_internal_rating",
    "counterparty_lcy_internal_rating",
    "incorporation_country",
    "lgd_classification",
    "pd_classification",
    "entity_class",
    "sub_class",
    "counterparty_dlgd",
    "govt_guarantee_flag",
    "trade_external_rating",
    "counterparty_external_rating",
    "avc",
    "pra_io_mdb_3_1_flag",
    "exposure_ccy",
    "bond_or_loan_flag",
    "original_maturity",
    "residual_maturity",
    "exposure_amount",
    "expected_yield",
    "counterparty_credit_quality_grade",
)

COUNTRY_INFO_COLUMNS = (
    "incorporation_country",
    "local_currency",
    "country_dlgd",
    "eea_country_flag",
    "eea_country_ten_percent_dlgd_flag",
    "country_internal_rating",
    "country_external_rating",
    "sov_concessionary_flag",
)

OUTPUT_SUCCESS_COLUMNS = (
    "id",
    "counterparty_gid",
    "basel_3_0_pd",
    "basel_3_1_pd",
    "basel_3_0_dlgd",
    "basel_3_1_dlgd",
    "basel_3_0_rw_final",
    "basel_3_0_rwa",
    "basel_3_0_ro_rw",
    "basel_3_1_rw_foundation",
    "basel_3_1_rwa_foundation",
    "basel_3_1_ro_rw_foundation",
    "basel_3_1_rw_standardised",
    "basel_3_1_rwa_standardised",
    "basel_3_1_ro_rw_standardised",
    "basel_3_1_rw_final",
    "basel_3_1_rwa_final",
    "basel_3_1_ro_rw_final",
)


def normalise_empty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def parse_decimal(value: Any, field: str) -> Decimal:
    value = normalise_empty(value)
    if value is None:
        raise ValueError(f"{field} is required")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    try:
        if text.endswith("%"):
            return Decimal(text[:-1]) / Decimal("100")
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc


def parse_optional_decimal(value: Any, field: str) -> Decimal | None:
    if normalise_empty(value) is None:
        return None
    return parse_decimal(value, field)


def normalise_rating_grade(value: Any, field: str) -> str:
    value = normalise_empty(value)
    if value is None:
        raise ValueError(f"{field} is required")
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text not in NCCR_RATING_GRADES:
        raise ValueError(f"{field} has unknown NCCR grade {text!r}")
    return text


def normalise_optional_external_rating(value: Any, field: str) -> str | None:
    value = normalise_empty(value)
    if value is None:
        return None
    text = str(value).strip().upper()
    if text not in EXTERNAL_RATINGS:
        raise ValueError(f"{field} has unknown external rating {text!r}")
    return None if text == "UNRATED" else text


def require_code(value: Any, field: str, length: int | None = None) -> str:
    value = normalise_empty(value)
    if value is None:
        raise ValueError(f"{field} is required")
    text = str(value).strip().upper()
    if not text:
        raise ValueError(f"{field} is required")
    if length is not None and len(text) != length:
        raise ValueError(f"{field} must have length {length}")
    return text


def require_flag(value: Any, field: str) -> str:
    text = require_code(value, field)
    if text not in {"Y", "N"}:
        raise ValueError(f"{field} must be Y or N")
    return text


@dataclass(frozen=True)
class CoreInfoRecord:
    id: str
    counterparty_gid: str
    hsbc_intragroup_flag: str
    counterparty_fcy_internal_rating: str
    counterparty_lcy_internal_rating: str
    incorporation_country: str
    lgd_classification: str
    pd_classification: str
    entity_class: str
    sub_class: str
    counterparty_dlgd: Decimal
    govt_guarantee_flag: str
    trade_external_rating: str | None
    counterparty_external_rating: str | None
    avc: Decimal
    pra_io_mdb_3_1_flag: str
    exposure_ccy: str
    bond_or_loan_flag: str
    original_maturity: Decimal
    residual_maturity: Decimal
    exposure_amount: Decimal
    expected_yield: Decimal | None
    counterparty_credit_quality_grade: str

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "CoreInfoRecord":
        missing = [column for column in CORE_INFO_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Missing core columns: {', '.join(missing)}")

        entity_class = require_code(row["entity_class"], "entity_class")
        if entity_class not in ENTITY_CLASSES:
            raise ValueError(f"entity_class has unsupported value {entity_class!r}")

        sub_class = require_code(row["sub_class"], "sub_class")
        if sub_class not in EXPOSURE_SUB_CLASSES:
            raise ValueError(f"sub_class has unsupported value {sub_class!r}")

        credit_quality = require_code(
            row["counterparty_credit_quality_grade"], "counterparty_credit_quality_grade"
        )
        if credit_quality not in COUNTERPARTY_CREDIT_QUALITY_GRADES:
            raise ValueError(
                "counterparty_credit_quality_grade has unsupported value "
                f"{credit_quality!r}"
            )

        record = cls(
            id=str(row["id"]).strip(),
            counterparty_gid=str(row["counterparty_gid"]).strip(),
            hsbc_intragroup_flag=require_flag(row["hsbc_intragroup_flag"], "hsbc_intragroup_flag"),
            counterparty_fcy_internal_rating=normalise_rating_grade(
                row["counterparty_fcy_internal_rating"], "counterparty_fcy_internal_rating"
            ),
            counterparty_lcy_internal_rating=normalise_rating_grade(
                row["counterparty_lcy_internal_rating"], "counterparty_lcy_internal_rating"
            ),
            incorporation_country=require_code(row["incorporation_country"], "incorporation_country", 2),
            lgd_classification=str(row["lgd_classification"]).strip().upper(),
            pd_classification=str(row["pd_classification"]).strip().upper(),
            entity_class=entity_class,
            sub_class=sub_class,
            counterparty_dlgd=parse_decimal(row["counterparty_dlgd"], "counterparty_dlgd"),
            govt_guarantee_flag=require_flag(row["govt_guarantee_flag"], "govt_guarantee_flag"),
            trade_external_rating=normalise_optional_external_rating(
                row["trade_external_rating"], "trade_external_rating"
            ),
            counterparty_external_rating=normalise_optional_external_rating(
                row["counterparty_external_rating"], "counterparty_external_rating"
            ),
            avc=parse_decimal(row["avc"], "avc"),
            pra_io_mdb_3_1_flag=require_flag(row["pra_io_mdb_3_1_flag"], "pra_io_mdb_3_1_flag"),
            exposure_ccy=require_code(row["exposure_ccy"], "exposure_ccy", 3),
            bond_or_loan_flag=require_code(row["bond_or_loan_flag"], "bond_or_loan_flag"),
            original_maturity=parse_decimal(row["original_maturity"], "original_maturity"),
            residual_maturity=parse_decimal(row["residual_maturity"], "residual_maturity"),
            exposure_amount=parse_decimal(row["exposure_amount"], "exposure_amount"),
            expected_yield=parse_optional_decimal(row["expected_yield"], "expected_yield"),
            counterparty_credit_quality_grade=credit_quality,
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not self.id:
            raise ValueError("id is required")
        if not self.counterparty_gid:
            raise ValueError("counterparty_gid is required")
        for field in ("counterparty_dlgd", "exposure_amount", "original_maturity", "residual_maturity"):
            value = getattr(self, field)
            if value < 0:
                raise ValueError(f"{field} cannot be negative")
        if not Decimal("0") <= self.counterparty_dlgd <= Decimal("1"):
            raise ValueError("counterparty_dlgd must be between 0 and 1")
        if self.expected_yield is not None and self.expected_yield < 0:
            raise ValueError("expected_yield cannot be negative")
        if self.residual_maturity > self.original_maturity:
            raise ValueError("residual_maturity cannot exceed original_maturity")
        if self.avc not in {Decimal("1.0"), Decimal("1"), Decimal("1.25")}:
            raise ValueError("avc must be either 1.0 or 1.25")
        if self.entity_class in {"BANK", "FI"} and self.avc != Decimal("1.25"):
            raise ValueError("BANK and FI exposures must use AVC 1.25")
        if self.entity_class == "MDB" and self.pra_io_mdb_3_1_flag != "Y":
            raise ValueError("MDB exposures must set pra_io_mdb_3_1_flag to Y")
        if self.bond_or_loan_flag not in {"B", "L"}:
            raise ValueError("bond_or_loan_flag must be B or L")


@dataclass(frozen=True)
class CountryInfoRecord:
    incorporation_country: str
    local_currency: str
    country_dlgd: Decimal | None
    eea_country_flag: str
    eea_country_ten_percent_dlgd_flag: str
    country_internal_rating: str | None
    country_external_rating: str | None
    sov_concessionary_flag: str

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "CountryInfoRecord":
        missing = [column for column in COUNTRY_INFO_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Missing country columns: {', '.join(missing)}")
        record = cls(
            incorporation_country=require_code(row["incorporation_country"], "incorporation_country", 2),
            local_currency=require_code(row["local_currency"], "local_currency", 3),
            country_dlgd=parse_optional_decimal(row["country_dlgd"], "country_dlgd"),
            eea_country_flag=require_flag(row["eea_country_flag"], "eea_country_flag"),
            eea_country_ten_percent_dlgd_flag=require_flag(
                row["eea_country_ten_percent_dlgd_flag"],
                "eea_country_ten_percent_dlgd_flag",
            ),
            country_internal_rating=(
                None
                if normalise_empty(row["country_internal_rating"]) is None
                else normalise_rating_grade(row["country_internal_rating"], "country_internal_rating")
            ),
            country_external_rating=normalise_optional_external_rating(
                row["country_external_rating"], "country_external_rating"
            ),
            sov_concessionary_flag=require_flag(row["sov_concessionary_flag"], "sov_concessionary_flag"),
        )
        if record.country_dlgd is not None and not Decimal("0") <= record.country_dlgd <= Decimal("1"):
            raise ValueError("country_dlgd must be between 0 and 1")
        return record


@dataclass(frozen=True)
class CalculationTraceStep:
    step_id: str
    description: str
    input_values: dict[str, str]
    formula: str | None
    output_values: dict[str, str]
    rule_reference: dict[str, str | int | None] | None = None
