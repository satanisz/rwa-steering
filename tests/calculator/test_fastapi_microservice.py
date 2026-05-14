from __future__ import annotations

import csv
import unittest

from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_calculator.rwa_calculator.fastapi_app import create_app


class FastApiMicroserviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_reports_scipy_backend(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["normal_distribution_backend"], "scipy.stats.norm")
        self.assertEqual(
            response.json()["reference_data_package_id"], "rwa_regulatory_reference_seed"
        )
        self.assertFalse(response.json()["reference_data_production_ready"])

    def test_reference_data_seed_endpoints(self) -> None:
        manifest = self.client.get("/reference/manifest")
        baseline = self.client.get("/reference/baseline")
        eu_overlay = self.client.get("/reference/jurisdictions/EU_CRR3_EBA")

        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(baseline.status_code, 200)
        self.assertEqual(eu_overlay.status_code, 200)
        self.assertEqual(manifest.json()["baseline"]["id"], "BCBS_BASEL_III_FINAL_2017")
        self.assertIn("output_floor", baseline.json()["tables"])
        self.assertEqual(eu_overlay.json()["jurisdiction_id"], "EU_CRR3_EBA")

    def test_json_calculation_endpoint_validates_and_calculates(self) -> None:
        with PREPROD_CORE_INFO_PATH.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))

        response = self.client.post(
            "/rwa/calculate",
            json={"include_trace": True, "core_info": [row]},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["output_successful_records"], 1)
        self.assertEqual(payload["summary"]["output_failure_records"], 0)
        self.assertEqual(payload["results"][0]["id"], row["id"])
        self.assertTrue(payload["results"][0]["trace"])

    def test_csv_calculation_endpoint_uses_batch_validation(self) -> None:
        with PREPROD_CORE_INFO_PATH.open("rb") as core:
            response = self.client.post(
                "/rwa/calculate/csv",
                files={"core_file": ("preprod_core_info_1000.csv", core, "text/csv")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["input_data_records"], 1000)
        self.assertEqual(payload["summary"]["output_successful_records"], 1000)
        self.assertEqual(payload["summary"]["output_failure_records"], 0)


if __name__ == "__main__":
    unittest.main()
