from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
NCCR_MAPPING_PATH = PACKAGE_ROOT / "nccr_mapping.csv"
PREPROD_CORE_INFO_PATH = PACKAGE_ROOT / "preprod_core_info_1000.csv"
PREPROD_COUNTRY_INFO_PATH = PACKAGE_ROOT / "preprod_country_info.csv"
REFERENCE_DATA_ROOT = PACKAGE_ROOT / "reference_data"
