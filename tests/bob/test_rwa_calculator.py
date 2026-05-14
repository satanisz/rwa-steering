"""
Test script for RWA calculator using preprod data.
"""

from pathlib import Path

from rwa_bob.basel3_final_reforms.cli import run_batch_calculation
from rwa_bob.paths import NCCR_MAPPING_PATH, PREPROD_CORE_INFO_PATH, PREPROD_COUNTRY_INFO_PATH


def test_with_preprod_data():
    """Test RWA calculator with preprod dataset."""

    print("=" * 70)
    print("BASEL III RWA CALCULATOR - TEST RUN")
    print("=" * 70)
    print()

    # Define file paths
    core_info_path = PREPROD_CORE_INFO_PATH
    country_info_path = PREPROD_COUNTRY_INFO_PATH
    output_path = Path("build/bob/rwa_calculation_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nccr_mapping_path = str(NCCR_MAPPING_PATH)

    # Check if files exist
    if not core_info_path.exists():
        print(f"Error: {core_info_path} not found")
        return

    if not country_info_path.exists():
        print(f"Error: {country_info_path} not found")
        return

    if not Path(nccr_mapping_path).exists():
        print(f"Error: {nccr_mapping_path} not found")
        return

    print("All required files found. Starting calculation...\n")

    # Run batch calculation
    try:
        run_batch_calculation(
            core_info_path=core_info_path,
            country_info_path=country_info_path,
            output_path=output_path,
            output_format="json",
            nccr_mapping_path=nccr_mapping_path,
            verbose=True,
        )

        print("\n" + "=" * 70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print(f"\nResults saved to: {output_path}")
        print("\nYou can now:")
        print("1. Review the JSON output file")
        print("2. Run the API server: python -m rwa_bob.basel3_final_reforms.api")
        print("3. Use the CLI for other datasets")

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_with_preprod_data()

# Made with Bob
