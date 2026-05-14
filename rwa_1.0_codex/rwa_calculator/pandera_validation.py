from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import pandera.pandas as pa

from .models import (
    CORE_INFO_COLUMNS,
    COUNTRY_INFO_COLUMNS,
    COUNTERPARTY_CREDIT_QUALITY_GRADES,
    ENTITY_CLASSES,
    EXPOSURE_SUB_CLASSES,
    NCCR_RATING_GRADES,
)


def _isin(values: set[str]):
    return pa.Check.isin(sorted(values))


CORE_INFO_SCHEMA = pa.DataFrameSchema(
    {
        "id": pa.Column(str, nullable=False, unique=True),
        "counterparty_gid": pa.Column(str, nullable=False),
        "hsbc_intragroup_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
        "counterparty_fcy_internal_rating": pa.Column(str, _isin(NCCR_RATING_GRADES), nullable=False),
        "counterparty_lcy_internal_rating": pa.Column(str, _isin(NCCR_RATING_GRADES), nullable=False),
        "incorporation_country": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{2}$"), nullable=False),
        "lgd_classification": pa.Column(str, nullable=False),
        "pd_classification": pa.Column(str, nullable=False),
        "entity_class": pa.Column(str, _isin(ENTITY_CLASSES), nullable=False),
        "sub_class": pa.Column(str, _isin(EXPOSURE_SUB_CLASSES), nullable=False),
        "counterparty_dlgd": pa.Column(float, [pa.Check.ge(0), pa.Check.le(1)], nullable=False, coerce=True),
        "govt_guarantee_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
        "trade_external_rating": pa.Column(str, nullable=True, required=True),
        "counterparty_external_rating": pa.Column(str, nullable=True, required=True),
        "avc": pa.Column(float, _isin({1.0, 1.25}), nullable=False, coerce=True),
        "pra_io_mdb_3_1_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
        "exposure_ccy": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{3}$"), nullable=False),
        "bond_or_loan_flag": pa.Column(str, _isin({"B", "L"}), nullable=False),
        "original_maturity": pa.Column(float, pa.Check.ge(0), nullable=False, coerce=True),
        "residual_maturity": pa.Column(float, pa.Check.ge(0), nullable=False, coerce=True),
        "exposure_amount": pa.Column(float, pa.Check.ge(0), nullable=False, coerce=True),
        "expected_yield": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        "counterparty_credit_quality_grade": pa.Column(
            str,
            _isin(COUNTERPARTY_CREDIT_QUALITY_GRADES),
            nullable=False,
        ),
    },
    strict=True,
    coerce=True,
    checks=[
        pa.Check(lambda df: df["residual_maturity"] <= df["original_maturity"], element_wise=False),
        pa.Check(
            lambda df: ((~df["entity_class"].isin(["BANK", "FI"])) | (df["avc"] == 1.25)),
            element_wise=False,
        ),
        pa.Check(
            lambda df: ((df["entity_class"] != "MDB") | (df["pra_io_mdb_3_1_flag"] == "Y")),
            element_wise=False,
        ),
    ],
)

COUNTRY_INFO_SCHEMA = pa.DataFrameSchema(
    {
        "incorporation_country": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{2}$"), nullable=False, unique=True),
        "local_currency": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{3}$"), nullable=False),
        "country_dlgd": pa.Column(float, [pa.Check.ge(0), pa.Check.le(1)], nullable=True, coerce=True),
        "eea_country_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
        "eea_country_ten_percent_dlgd_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
        "country_internal_rating": pa.Column(str, _isin(NCCR_RATING_GRADES), nullable=True),
        "country_external_rating": pa.Column(str, nullable=True),
        "sov_concessionary_flag": pa.Column(str, _isin({"Y", "N"}), nullable=False),
    },
    strict=True,
    coerce=True,
)


def read_core_csv_bytes(content: bytes) -> list[dict[str, Any]]:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    frame = CORE_INFO_SCHEMA.validate(frame, lazy=True)
    return frame.to_dict(orient="records")


def read_country_csv_bytes(content: bytes) -> list[dict[str, Any]]:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    frame = COUNTRY_INFO_SCHEMA.validate(frame, lazy=True)
    return frame.to_dict(orient="records")
