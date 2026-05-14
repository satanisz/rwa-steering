from __future__ import annotations

import csv
import json
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from rwa_calculator.rwa_pydantic_schemas import (
    CORE_INFO_COLUMNS,
    COUNTRY_INFO_COLUMNS,
    CoreInfoRecord,
    CountryInfoRecord,
    EntityClass,
    ExposureSubClass,
)

SOURCE_MAPPING = Path(r"C:\Users\stani\Documents\IBM_hackaton\RWA\nccr_mapping.csv")
OUTPUT_CORE = Path("preprod_core_info_1000.csv")
OUTPUT_COUNTRY = Path("preprod_country_info.csv")
OUTPUT_SUMMARY = Path("preprod_dataset_summary.json")
SEED = 20260514
ROW_COUNT = 1000


COUNTRIES = [
    ("PL", "PLN", "Y", "Y", "2.1", "A", "Y"),
    ("US", "USD", "N", "N", "1.2", "AA", "Y"),
    ("GB", "GBP", "N", "N", "2.1", "A+", "Y"),
    ("DE", "EUR", "Y", "Y", "1.2", "AA-", "Y"),
    ("FR", "EUR", "Y", "Y", "2.1", "A+", "Y"),
    ("NL", "EUR", "Y", "Y", "1.2", "AA", "Y"),
    ("ES", "EUR", "Y", "Y", "3.1", "A-", "N"),
    ("IT", "EUR", "Y", "Y", "3.2", "BBB+", "N"),
    ("SE", "SEK", "Y", "Y", "1.2", "AA", "Y"),
    ("CH", "CHF", "N", "N", "1.1", "AAA", "Y"),
]

CCYS = ["PLN", "EUR", "USD", "GBP", "CHF", "SEK"]

EXTERNAL_RATING_BY_NCCR = {
    "0.1": "AAA",
    "1.1": "AA",
    "1.2": "AA-",
    "2.1": "A+",
    "2.2": "A",
    "3.1": "A-",
    "3.2": "BBB+",
    "3.3": "BBB",
    "4.1": "BBB-",
    "4.2": "BB+",
    "4.3": "BB",
    "5.1": "BB-",
    "5.2": "B+",
    "5.3": "B",
    "6.1": "B-",
    "6.2": "CCC",
    "7.1": "CC",
    "7.2": "C",
    "8.1": "D",
    "8.2": "D",
    "8.3": "D",
}

ENTITY_WEIGHTS = [
    (EntityClass.CORP, 0.42),
    (EntityClass.BANK, 0.20),
    (EntityClass.SOV, 0.14),
    (EntityClass.FI, 0.08),
    (EntityClass.RETAIL, 0.08),
    (EntityClass.PSE, 0.04),
    (EntityClass.MDB, 0.03),
    (EntityClass.OTHER, 0.01),
]

SUBCLASSES_BY_ENTITY = {
    EntityClass.SOV: [ExposureSubClass.SOVEREIGN],
    EntityClass.BANK: [ExposureSubClass.BANK],
    EntityClass.FI: [ExposureSubClass.FINANCIAL_INSTITUTION],
    EntityClass.PSE: [ExposureSubClass.GENERAL],
    EntityClass.MDB: [ExposureSubClass.GENERAL],
    EntityClass.RETAIL: [ExposureSubClass.RETAIL, ExposureSubClass.RESIDENTIAL_REAL_ESTATE],
    EntityClass.OTHER: [ExposureSubClass.OTHER],
    EntityClass.CORP: [
        ExposureSubClass.CORPORATE,
        ExposureSubClass.PROJECT_FINANCE,
        ExposureSubClass.OBJECT_FINANCE,
        ExposureSubClass.COMMODITIES_FINANCE,
        ExposureSubClass.SPECIALISED_LENDING,
        ExposureSubClass.COMMERCIAL_REAL_ESTATE,
    ],
}


def parse_percent(value: str) -> Decimal:
    text = value.strip()
    if text.endswith("%"):
        return (Decimal(text[:-1]) / Decimal("100")).quantize(Decimal("0.00000001"))
    return Decimal(text)


def load_nccr_mapping(path: Path) -> dict[str, dict[str, Decimal]]:
    mapping: dict[str, dict[str, Decimal]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            grade = (row.get("CRR") or "").strip()
            if not grade:
                continue
            mapping[grade] = {
                "SOV": parse_percent(row["SOV"]),
                "CORP": parse_percent(row["CORP"]),
                "BANK": parse_percent(row["BANK"]),
            }
    if not mapping:
        raise RuntimeError(f"No primary CRR grades loaded from {path}")
    return mapping


def choose_weighted(rng: random.Random, weighted_values):
    threshold = rng.random()
    cumulative = 0.0
    for value, weight in weighted_values:
        cumulative += weight
        if threshold <= cumulative:
            return value
    return weighted_values[-1][0]


def choose_rating(rng: random.Random, ratings: list[str]) -> str:
    # Better ratings appear more often to keep the synthetic book plausible.
    weights = [max(1, len(ratings) - idx) for idx, _ in enumerate(ratings)]
    return rng.choices(ratings, weights=weights, k=1)[0]


def pd_bucket_for_entity(entity: EntityClass) -> str:
    if entity == EntityClass.SOV or entity in {EntityClass.PSE, EntityClass.MDB}:
        return "SOV"
    if entity in {EntityClass.BANK, EntityClass.FI}:
        return "BANK"
    return "CORP"


def credit_quality_for_rating(grade: str, external_rating: str | None) -> str:
    if external_rating is None:
        return "NOT_RATED"
    numeric = Decimal(grade)
    if numeric <= Decimal("3.3"):
        return "INVESTMENT_GRADE"
    return "HIGH_YIELD"


def dlgd_for_entity(rng: random.Random, entity: EntityClass) -> Decimal:
    base = {
        EntityClass.SOV: Decimal("0.0500"),
        EntityClass.PSE: Decimal("0.1000"),
        EntityClass.MDB: Decimal("0.0800"),
        EntityClass.BANK: Decimal("0.4500"),
        EntityClass.FI: Decimal("0.4500"),
        EntityClass.CORP: Decimal("0.4000"),
        EntityClass.RETAIL: Decimal("0.3500"),
        EntityClass.OTHER: Decimal("0.5000"),
    }[entity]
    noise = Decimal(str(rng.uniform(-0.03, 0.03))).quantize(Decimal("0.0001"))
    return min(max(base + noise, Decimal("0.0100")), Decimal("0.9000"))


def money_amount(rng: random.Random, entity: EntityClass) -> Decimal:
    ranges = {
        EntityClass.SOV: (5_000_000, 250_000_000),
        EntityClass.PSE: (1_000_000, 80_000_000),
        EntityClass.MDB: (1_000_000, 120_000_000),
        EntityClass.BANK: (500_000, 100_000_000),
        EntityClass.FI: (250_000, 60_000_000),
        EntityClass.CORP: (100_000, 50_000_000),
        EntityClass.RETAIL: (5_000, 1_500_000),
        EntityClass.OTHER: (10_000, 5_000_000),
    }[entity]
    amount = Decimal(str(rng.uniform(*ranges)))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def decimal_text(value: Decimal, places: str = "0.0001") -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def build_country_rows() -> list[dict[str, str]]:
    rows = []
    for country, currency, eea, ten_pct, internal_rating, external_rating, concession in COUNTRIES:
        row = {
            "incorporation_country": country,
            "local_currency": currency,
            "country_dlgd": "0.0500" if concession == "Y" else "0.1000",
            "eea_country_flag": eea,
            "eea_country_ten_percent_dlgd_flag": ten_pct,
            "country_internal_rating": internal_rating,
            "country_external_rating": external_rating,
            "sov_concessionary_flag": concession,
        }
        CountryInfoRecord.model_validate(row)
        rows.append(row)
    return rows


def build_core_rows(nccr_mapping: dict[str, dict[str, Decimal]]) -> list[dict[str, str]]:
    rng = random.Random(SEED)
    ratings = sorted(nccr_mapping.keys(), key=lambda item: Decimal(item))
    rows: list[dict[str, str]] = []
    for idx in range(1, ROW_COUNT + 1):
        entity = choose_weighted(rng, ENTITY_WEIGHTS)
        sub_class = rng.choice(SUBCLASSES_BY_ENTITY[entity])
        country, local_currency, *_ = rng.choice(COUNTRIES)
        exposure_ccy = rng.choice([local_currency, *CCYS])
        fcy_rating = choose_rating(rng, ratings)
        lcy_rating = fcy_rating if rng.random() < 0.65 else choose_rating(rng, ratings)
        external_rating = EXTERNAL_RATING_BY_NCCR[fcy_rating]
        if rng.random() < 0.18:
            external_rating = ""
        trade_external_rating = external_rating if rng.random() < 0.35 else ""
        pd_bucket = pd_bucket_for_entity(entity)
        pd = nccr_mapping[fcy_rating][pd_bucket]
        dlgd = dlgd_for_entity(rng, entity)
        amount = money_amount(rng, entity)
        original_maturity = Decimal(str(rng.uniform(0.25, 10.0))).quantize(Decimal("0.01"))
        residual_ratio = Decimal(str(rng.uniform(0.05, 1.0))).quantize(Decimal("0.0001"))
        residual_maturity = (original_maturity * residual_ratio).quantize(Decimal("0.01"))
        expected_yield = (pd + Decimal(str(rng.uniform(0.005, 0.045)))).quantize(Decimal("0.0001"))
        avc = "1.25" if entity in {EntityClass.BANK, EntityClass.FI} else "1.0"
        row = {
            "id": f"EXP{idx:06d}",
            "counterparty_gid": f"CP{rng.randint(1, 260):05d}",
            "hsbc_intragroup_flag": "Y" if rng.random() < 0.04 else "N",
            "counterparty_fcy_internal_rating": fcy_rating,
            "counterparty_lcy_internal_rating": lcy_rating,
            "incorporation_country": country,
            "lgd_classification": f"LGD_{entity.value}",
            "pd_classification": f"PD_{pd_bucket}",
            "entity_class": entity.value,
            "sub_class": sub_class.value,
            "counterparty_dlgd": decimal_text(dlgd),
            "govt_guarantee_flag": "Y"
            if entity in {EntityClass.SOV, EntityClass.PSE, EntityClass.MDB} or rng.random() < 0.07
            else "N",
            "trade_external_rating": trade_external_rating,
            "counterparty_external_rating": external_rating,
            "avc": avc,
            "pra_io_mdb_3_1_flag": "Y" if entity == EntityClass.MDB else "N",
            "exposure_ccy": exposure_ccy,
            "bond_or_loan_flag": "B" if rng.random() < 0.37 else "L",
            "original_maturity": str(original_maturity),
            "residual_maturity": str(residual_maturity),
            "exposure_amount": str(amount),
            "expected_yield": str(expected_yield),
            "counterparty_credit_quality_grade": credit_quality_for_rating(
                fcy_rating, external_rating or None
            ),
        }
        CoreInfoRecord.model_validate(row)
        rows.append(row)
    return rows


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    nccr_mapping = load_nccr_mapping(SOURCE_MAPPING)
    core_rows = build_core_rows(nccr_mapping)
    country_rows = build_country_rows()

    write_csv(OUTPUT_CORE, CORE_INFO_COLUMNS, core_rows)
    write_csv(OUTPUT_COUNTRY, COUNTRY_INFO_COLUMNS, country_rows)

    summary = {
        "seed": SEED,
        "core_rows": len(core_rows),
        "country_rows": len(country_rows),
        "source_mapping": str(SOURCE_MAPPING),
        "outputs": [str(OUTPUT_CORE), str(OUTPUT_COUNTRY)],
        "schema": "rwa_pydantic_schemas.CoreInfoRecord",
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
