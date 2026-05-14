from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from rwa_calculator.paths import REFERENCE_DATA_ROOT

from .models import CountryInfoRecord, parse_decimal

RATING_ORDER = [
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
]


def load_nccr_mapping(path: str | Path) -> dict[str, dict[str, Decimal]]:
    mapping: dict[str, dict[str, Decimal]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            grade = (row.get("CRR") or "").strip()
            if not grade:
                continue
            mapping[grade] = {
                "SOV": parse_decimal(row["SOV"], "SOV"),
                "CORP": parse_decimal(row["CORP"], "CORP"),
                "BANK": parse_decimal(row["BANK"], "BANK"),
            }
    if not mapping:
        raise ValueError(f"No CRR rows loaded from {path}")
    return mapping


def load_country_info(path: str | Path) -> dict[str, CountryInfoRecord]:
    countries: dict[str, CountryInfoRecord] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            country = CountryInfoRecord.from_mapping(row)
            if country.incorporation_country in countries:
                raise ValueError(f"Duplicate country {country.incorporation_country}")
            countries[country.incorporation_country] = country
    return countries


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON reference file must contain an object: {path}")
    return payload


class ReferenceDataPackage:
    def __init__(self, root: str | Path = REFERENCE_DATA_ROOT) -> None:
        self.root = Path(root)
        self.manifest = load_json(self.root / "manifest.json")
        baseline_path = self.root / self.manifest["baseline"]["path"]
        self.baseline = load_json(baseline_path)
        self.jurisdictions = {
            item["id"]: load_json(self.root / item["path"])
            for item in self.manifest.get("jurisdictions", [])
        }

    @property
    def package_id(self) -> str:
        return str(self.manifest.get("package_id", "unknown"))

    @property
    def package_version(self) -> str:
        return str(self.manifest.get("package_version", "unknown"))

    @property
    def production_ready(self) -> bool:
        return bool(self.manifest.get("production_ready", False))

    def jurisdiction(self, jurisdiction_id: str) -> dict[str, Any]:
        try:
            return self.jurisdictions[jurisdiction_id]
        except KeyError as exc:
            available = ", ".join(sorted(self.jurisdictions))
            raise ValueError(
                f"Unknown jurisdiction {jurisdiction_id!r}; available jurisdictions: {available}"
            ) from exc


def rating_index(rating: str | None) -> int | None:
    if rating is None:
        return None
    try:
        return RATING_ORDER.index(rating)
    except ValueError:
        return None


def rated_between(rating: str | None, best: str, worst: str) -> bool:
    idx = rating_index(rating)
    if idx is None:
        return False
    return rating_index(best) <= idx <= rating_index(worst)


def sovereign_external_rw(rating: str | None) -> Decimal:
    if rated_between(rating, "AAA", "AA-"):
        return Decimal("0.00")
    if rated_between(rating, "A+", "A-"):
        return Decimal("0.20")
    if rated_between(rating, "BBB+", "BBB-"):
        return Decimal("0.50")
    if rated_between(rating, "BB+", "B-"):
        return Decimal("1.00")
    if rating is None:
        return Decimal("1.00")
    return Decimal("1.50")


def pse_option_1_rw(sovereign_rating: str | None) -> Decimal:
    if rated_between(sovereign_rating, "AAA", "AA-"):
        return Decimal("0.20")
    if rated_between(sovereign_rating, "A+", "A-"):
        return Decimal("0.50")
    if rated_between(sovereign_rating, "BBB+", "B-"):
        return Decimal("1.00")
    if sovereign_rating is None:
        return Decimal("1.00")
    return Decimal("1.50")


def mdb_rw(rating: str | None, eligible_zero_weight: bool) -> Decimal:
    if eligible_zero_weight:
        return Decimal("0.00")
    if rated_between(rating, "AAA", "AA-"):
        return Decimal("0.20")
    if rated_between(rating, "A+", "A-"):
        return Decimal("0.30")
    if rated_between(rating, "BBB+", "BBB-"):
        return Decimal("0.50")
    if rated_between(rating, "BB+", "B-"):
        return Decimal("1.00")
    if rating is None:
        return Decimal("0.50")
    return Decimal("1.50")


def bank_ecra_rw(rating: str | None, short_term: bool) -> Decimal | None:
    if rating is None:
        return None
    if rated_between(rating, "AAA", "AA-"):
        return Decimal("0.20")
    if rated_between(rating, "A+", "A-"):
        return Decimal("0.20") if short_term else Decimal("0.30")
    if rated_between(rating, "BBB+", "BBB-"):
        return Decimal("0.20") if short_term else Decimal("0.50")
    if rated_between(rating, "BB+", "B-"):
        return Decimal("0.50") if short_term else Decimal("1.00")
    return Decimal("1.50")


def bank_scra_rw(credit_quality: str, short_term: bool) -> Decimal:
    if credit_quality == "INVESTMENT_GRADE":
        return Decimal("0.20") if short_term else Decimal("0.40")
    if credit_quality == "HIGH_YIELD":
        return Decimal("0.50") if short_term else Decimal("0.75")
    return Decimal("1.50")


def corporate_external_rw(rating: str | None, investment_grade: bool) -> Decimal:
    if rating is None:
        return Decimal("0.65") if investment_grade else Decimal("1.00")
    if rated_between(rating, "AAA", "AA-"):
        return Decimal("0.20")
    if rated_between(rating, "A+", "A-"):
        return Decimal("0.50")
    if rated_between(rating, "BBB+", "BBB-"):
        return Decimal("0.75")
    if rated_between(rating, "BB+", "BB-"):
        return Decimal("1.00")
    return Decimal("1.50")
