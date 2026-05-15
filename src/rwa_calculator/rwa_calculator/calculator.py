from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, is_dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import NormalDist
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH

from .models import (
    OUTPUT_SUCCESS_COLUMNS,
    CalculationTraceStep,
    CoreInfoRecord,
    CountryInfoRecord,
)
from .reference import (
    bank_ecra_rw,
    bank_scra_rw,
    corporate_external_rw,
    load_country_info,
    load_nccr_mapping,
    mdb_rw,
    pse_option_1_rw,
    sovereign_external_rw,
)

RATE_Q = Decimal("0.000001")
MONEY_Q = Decimal("0.01")
NORMAL = NormalDist()


class RwaCalculator:
    """Deterministic Basel/RWA calculation engine over validated exposure rows."""

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        countries: dict[str, CountryInfoRecord] | None = None,
        nccr_mapping: dict[str, dict[str, Decimal]] | None = None,
    ) -> None:
        """Create a calculator from in-memory or file-backed reference data."""
        self.nccr_mapping_path = Path(nccr_mapping_path)
        self.nccr_mapping = nccr_mapping or load_nccr_mapping(self.nccr_mapping_path)
        self.countries = countries or {}

    @classmethod
    def from_files(
        cls,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
    ) -> RwaCalculator:
        """Load the default calculator reference inputs from CSV files."""
        return cls(
            nccr_mapping_path=nccr_mapping_path, countries=load_country_info(country_info_path)
        )

    def calculate_batch(
        self,
        rows: list[dict[str, Any]],
        include_trace: bool = False,
        projection_date: str | None = None,
    ) -> dict[str, Any]:
        """Calculate RWA for a list of input rows and collect row-level errors.

        Batch mode is intentionally tolerant: one invalid row is returned in the
        `errors` collection while valid rows continue through the engine. This
        mirrors bank data-quality workflows where partial portfolio feedback is
        more useful than failing the entire upload.
        """
        results: list[dict[str, Any]] = []
        projections: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for index, row in enumerate(rows, start=1):
            row_id = str(row.get("id") or f"row_{index}")
            try:
                record = CoreInfoRecord.from_mapping(row)
                if record.id in seen_ids:
                    raise ValueError(f"Duplicate id {record.id}")
                seen_ids.add(record.id)
                result, trace = self.calculate_record(record)
                if include_trace:
                    result["trace"] = [asdict(step) for step in trace]
                results.append(result)
                if projection_date:
                    projections.append(self._build_projection(result, projection_date))
            except Exception as exc:
                errors.append({"id": row_id, "messages": [str(exc)]})

        return {
            "summary": {
                "input_data_records": len(rows),
                "output_successful_records": len(results),
                "output_successful_projection_records": len(projections),
                "output_failure_records": len(errors),
            },
            "results": results,
            "projections": projections,
            "errors": errors,
        }

    def calculate_record(
        self, record: CoreInfoRecord
    ) -> tuple[dict[str, Any], list[CalculationTraceStep]]:
        """Calculate Basel 3.0 and Basel 3.1 RWA measures for one exposure."""
        trace: list[CalculationTraceStep] = []
        country = self.countries.get(record.incorporation_country)
        if country is None:
            raise ValueError(f"No country info for {record.incorporation_country}")

        selected_grade = (
            record.counterparty_lcy_internal_rating
            if record.exposure_ccy == country.local_currency
            else record.counterparty_fcy_internal_rating
        )
        pd_bucket = self._pd_bucket(record.entity_class)
        raw_pd = self.nccr_mapping[selected_grade][pd_bucket]
        basel_3_0_pd = self._pd_with_floor(raw_pd, record.entity_class)
        basel_3_1_pd = self._pd_with_floor(raw_pd, record.entity_class)
        trace.append(
            CalculationTraceStep(
                step_id="pd_lookup",
                description=(
                    "Lookup PD from NCCR/CRR mapping using local-currency grade when "
                    "exposure currency matches country local currency."
                ),
                input_values={
                    "selected_grade": selected_grade,
                    "pd_bucket": pd_bucket,
                    "raw_pd": str(raw_pd),
                },
                formula="PD = max(mapped_pd, regulatory_floor_where_applicable)",
                output_values={
                    "basel_3_0_pd": str(basel_3_0_pd),
                    "basel_3_1_pd": str(basel_3_1_pd),
                },
                rule_reference={"source_document": "Project nccr_mapping.csv", "section": "18.4"},
            )
        )

        basel_3_0_dlgd = record.counterparty_dlgd
        basel_3_1_dlgd = self._foundation_lgd(record, country)
        maturity = min(max(record.residual_maturity, Decimal("1")), Decimal("5"))
        trace.append(
            CalculationTraceStep(
                step_id="lgd_maturity",
                description=(
                    "Determine Basel 3.0 DLGD, Basel 3.1 foundation LGD and effective maturity."
                ),
                input_values={
                    "counterparty_dlgd": str(record.counterparty_dlgd),
                    "residual_maturity": str(record.residual_maturity),
                    "entity_class": record.entity_class,
                },
                formula="M = min(max(residual_maturity, 1), 5)",
                output_values={
                    "basel_3_0_dlgd": str(basel_3_0_dlgd),
                    "basel_3_1_dlgd": str(basel_3_1_dlgd),
                    "effective_maturity": str(maturity),
                },
                rule_reference={
                    "source_document": "Basel III Finalising post-crisis reforms",
                    "section": "7.6",
                },
            )
        )

        basel_3_0_rw = self._irb_risk_weight(record, basel_3_0_pd, basel_3_0_dlgd, maturity)
        basel_3_1_foundation_rw = self._irb_risk_weight(
            record, basel_3_1_pd, basel_3_1_dlgd, maturity
        )
        standardised_rw = self._standardised_risk_weight(record, country)

        if record.govt_guarantee_flag == "Y":
            guarantor_rw = self._sovereign_or_country_rw(country)
            basel_3_0_rw = min(basel_3_0_rw, guarantor_rw)
            basel_3_1_foundation_rw = min(basel_3_1_foundation_rw, guarantor_rw)
            standardised_rw = min(standardised_rw, guarantor_rw)
            guarantee_output = {"guarantor_rw": str(guarantor_rw)}
        else:
            guarantee_output = {"guarantor_rw": "not_applied"}

        standardised_floor_rw = standardised_rw * Decimal("0.725")
        final_3_1_rw = max(basel_3_1_foundation_rw, standardised_floor_rw)

        trace.append(
            CalculationTraceStep(
                step_id="risk_weight",
                description=(
                    "Calculate IRB foundation, standardised and exposure-level "
                    "output-floor proxy risk weights."
                ),
                input_values={
                    "avc": str(record.avc),
                    "entity_class": record.entity_class,
                    "standardised_rw": str(standardised_rw),
                    **guarantee_output,
                },
                formula="RW_final_3_1 = max(IRB_foundation_RW, 72.5% * standardised_RW)",
                output_values={
                    "basel_3_0_rw_final": str(basel_3_0_rw),
                    "basel_3_1_rw_foundation": str(basel_3_1_foundation_rw),
                    "basel_3_1_rw_standardised": str(standardised_rw),
                    "basel_3_1_rw_final": str(final_3_1_rw),
                },
                rule_reference={
                    "source_document": "Basel III Finalising post-crisis reforms",
                    "section": "7.3/10",
                },
            )
        )

        ead = record.exposure_amount
        result = {
            "id": record.id,
            "counterparty_gid": record.counterparty_gid,
            "basel_3_0_pd": self._q_rate(basel_3_0_pd),
            "basel_3_1_pd": self._q_rate(basel_3_1_pd),
            "basel_3_0_dlgd": self._q_rate(basel_3_0_dlgd),
            "basel_3_1_dlgd": self._q_rate(basel_3_1_dlgd),
            "basel_3_0_rw_final": self._q_rate(basel_3_0_rw),
            "basel_3_0_rwa": self._q_money(ead * basel_3_0_rw),
            "basel_3_0_ro_rw": self._q_rate(basel_3_0_rw),
            "basel_3_1_rw_foundation": self._q_rate(basel_3_1_foundation_rw),
            "basel_3_1_rwa_foundation": self._q_money(ead * basel_3_1_foundation_rw),
            "basel_3_1_ro_rw_foundation": self._q_rate(basel_3_1_foundation_rw),
            "basel_3_1_rw_standardised": self._q_rate(standardised_rw),
            "basel_3_1_rwa_standardised": self._q_money(ead * standardised_rw),
            "basel_3_1_ro_rw_standardised": self._q_rate(standardised_rw),
            "basel_3_1_rw_final": self._q_rate(final_3_1_rw),
            "basel_3_1_rwa_final": self._q_money(ead * final_3_1_rw),
            "basel_3_1_ro_rw_final": self._q_rate(final_3_1_rw),
        }
        return result, trace

    def _standardised_risk_weight(
        self, record: CoreInfoRecord, country: CountryInfoRecord
    ) -> Decimal:
        """Select the Basel standardised risk weight for the exposure class."""
        rating = record.trade_external_rating or record.counterparty_external_rating
        if record.entity_class == "SOV":
            rw = sovereign_external_rw(
                record.counterparty_external_rating or country.country_external_rating
            )
            if (
                country.sov_concessionary_flag == "Y"
                and record.exposure_ccy == country.local_currency
                and record.govt_guarantee_flag == "Y"
            ):
                return Decimal("0.00")
            return rw
        if record.entity_class == "PSE":
            return pse_option_1_rw(country.country_external_rating)
        if record.entity_class == "MDB":
            return mdb_rw(rating, record.pra_io_mdb_3_1_flag == "Y")
        if record.entity_class in {"BANK", "FI"}:
            short_term = record.original_maturity <= Decimal("0.25")
            ecra = bank_ecra_rw(record.counterparty_external_rating, short_term)
            return (
                ecra
                if ecra is not None
                else bank_scra_rw(record.counterparty_credit_quality_grade, short_term)
            )
        if record.entity_class == "RETAIL":
            return Decimal("0.75")
        if record.entity_class == "OTHER":
            return Decimal("1.00")
        if (
            record.sub_class in {"OBJECT_FINANCE", "COMMODITIES_FINANCE"}
            and record.trade_external_rating is None
        ):
            return Decimal("1.00")
        if record.sub_class == "PROJECT_FINANCE" and record.trade_external_rating is None:
            return Decimal("1.00")
        if record.sub_class == "RESIDENTIAL_REAL_ESTATE":
            return Decimal("0.75")
        if record.sub_class == "COMMERCIAL_REAL_ESTATE":
            return Decimal("1.00")
        return corporate_external_rw(
            rating, record.counterparty_credit_quality_grade == "INVESTMENT_GRADE"
        )

    def _irb_risk_weight(
        self,
        record: CoreInfoRecord,
        pd: Decimal,
        lgd: Decimal,
        maturity: Decimal,
    ) -> Decimal:
        """Calculate the IRB risk weight proxy, falling back where IRB is unsupported."""
        if record.entity_class in {"RETAIL"}:
            k = self._retail_capital_requirement(record, pd, lgd)
        elif record.entity_class == "OTHER":
            return self._standardised_risk_weight(
                record, self.countries[record.incorporation_country]
            )
        else:
            k = self._corporate_bank_capital_requirement(pd, lgd, maturity)
        return max(Decimal("0"), Decimal("12.5") * k * record.avc)

    def _corporate_bank_capital_requirement(
        self, pd: Decimal, lgd: Decimal, maturity: Decimal
    ) -> Decimal:
        """Return Basel corporate/bank capital requirement `K` before 12.5 scaling."""
        pd_f = min(max(float(pd), 0.000001), 0.999999)
        lgd_f = float(lgd)
        maturity_f = float(maturity)
        exp_part = (1 - math.exp(-50 * pd_f)) / (1 - math.exp(-50))
        correlation = 0.12 * exp_part + 0.24 * (1 - exp_part)
        b = (0.11852 - 0.05478 * math.log(pd_f)) ** 2
        z = (NORMAL.inv_cdf(pd_f) + math.sqrt(correlation) * NORMAL.inv_cdf(0.999)) / math.sqrt(
            1 - correlation
        )
        maturity_adjustment = (1 + (maturity_f - 2.5) * b) / (1 - 1.5 * b)
        k = (lgd_f * NORMAL.cdf(z) - pd_f * lgd_f) * maturity_adjustment
        return Decimal(str(max(k, 0.0)))

    def _retail_capital_requirement(
        self, record: CoreInfoRecord, pd: Decimal, lgd: Decimal
    ) -> Decimal:
        """Return Basel retail capital requirement `K` for the supported subclasses."""
        pd_f = min(max(float(pd), 0.000001), 0.999999)
        lgd_f = float(lgd)
        if record.sub_class == "RESIDENTIAL_REAL_ESTATE":
            correlation = 0.15
        else:
            exp_part = (1 - math.exp(-35 * pd_f)) / (1 - math.exp(-35))
            correlation = 0.03 * exp_part + 0.16 * (1 - exp_part)
        z = (NORMAL.inv_cdf(pd_f) + math.sqrt(correlation) * NORMAL.inv_cdf(0.999)) / math.sqrt(
            1 - correlation
        )
        k = lgd_f * NORMAL.cdf(z) - pd_f * lgd_f
        return Decimal(str(max(k, 0.0)))

    def _foundation_lgd(self, record: CoreInfoRecord, country: CountryInfoRecord) -> Decimal:
        """Derive Basel 3.1 foundation LGD from exposure class and country inputs."""
        if record.entity_class in {"SOV", "PSE", "MDB"}:
            return country.country_dlgd if country.country_dlgd is not None else Decimal("0.05")
        if record.entity_class in {"BANK", "FI"}:
            return Decimal("0.45")
        if record.entity_class == "RETAIL" and record.sub_class == "RESIDENTIAL_REAL_ESTATE":
            return max(record.counterparty_dlgd, Decimal("0.05"))
        if record.entity_class == "RETAIL":
            return max(record.counterparty_dlgd, Decimal("0.30"))
        return Decimal("0.40")

    def _pd_bucket(self, entity_class: str) -> str:
        """Map exposure class to the NCCR PD bucket used in the reference table."""
        if entity_class in {"SOV", "PSE", "MDB"}:
            return "SOV"
        if entity_class in {"BANK", "FI"}:
            return "BANK"
        return "CORP"

    def _pd_with_floor(self, pd: Decimal, entity_class: str) -> Decimal:
        """Apply the current PD floor for exposure classes in scope."""
        if entity_class in {"CORP", "BANK", "FI"}:
            return max(pd, Decimal("0.0005"))
        if entity_class == "RETAIL":
            return max(pd, Decimal("0.0005"))
        return pd

    def _sovereign_or_country_rw(self, country: CountryInfoRecord) -> Decimal:
        """Return sovereign risk weight used for government-guarantee substitution."""
        return sovereign_external_rw(country.country_external_rating)

    def _build_projection(self, result: dict[str, Any], projection_date: str) -> dict[str, Any]:
        """Build the calculator's compatibility one-date projection record from a result row."""
        fields = {
            key: result[key]
            for key in OUTPUT_SUCCESS_COLUMNS
            if key in result
            and key
            not in {
                "counterparty_gid",
                "basel_3_0_pd",
                "basel_3_1_pd",
                "basel_3_0_dlgd",
                "basel_3_1_dlgd",
                "basel_3_1_rw_final",
                "basel_3_1_rwa_final",
                "basel_3_1_ro_rw_final",
            }
        }
        fields["projection_date"] = projection_date
        return fields

    def _q_rate(self, value: Decimal) -> Decimal:
        """Quantize rate-like outputs to the engine's published precision."""
        return value.quantize(RATE_Q, rounding=ROUND_HALF_UP)

    def _q_money(self, value: Decimal) -> Decimal:
        """Quantize money-like outputs to cents."""
        return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def load_core_csv(path: str | Path) -> list[dict[str, str]]:
    """Load CoreInfo CSV rows as dictionaries for restricted CLI/server mode."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def decimal_json_default(value: Any) -> Any:
    """JSON fallback for Decimals and dataclass trace/reference objects."""
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps_json(payload: Any) -> str:
    """Dump calculator payloads with stable formatting and Decimal support."""
    return json.dumps(payload, default=decimal_json_default, indent=2, sort_keys=False)
