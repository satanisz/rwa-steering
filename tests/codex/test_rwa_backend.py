from __future__ import annotations

import unittest
from decimal import Decimal

from rwa_codex.paths import NCCR_MAPPING_PATH, PREPROD_CORE_INFO_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_codex.rwa_calculator.calculator import load_core_csv
from rwa_codex.rwa_calculator.server import calculate_file


class RwaBackendTests(unittest.TestCase):
    def test_preprod_dataset_calculates_without_row_errors(self) -> None:
        result = calculate_file(
            PREPROD_CORE_INFO_PATH,
            PREPROD_COUNTRY_INFO_PATH,
            NCCR_MAPPING_PATH,
        )

        self.assertEqual(result["summary"]["input_data_records"], 1000)
        self.assertEqual(result["summary"]["output_successful_records"], 1000)
        self.assertEqual(result["summary"]["output_failure_records"], 0)

    def test_single_record_has_expected_output_contract(self) -> None:
        row = load_core_csv(PREPROD_CORE_INFO_PATH)[0]
        result = calculate_file(
            PREPROD_CORE_INFO_PATH,
            PREPROD_COUNTRY_INFO_PATH,
            NCCR_MAPPING_PATH,
        )
        output = result["results"][0]

        self.assertEqual(output["id"], row["id"])
        self.assertIn("basel_3_1_rwa_final", output)
        self.assertGreaterEqual(Decimal(output["basel_3_1_rwa_final"]), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
