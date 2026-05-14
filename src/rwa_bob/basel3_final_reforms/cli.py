"""
Command-line interface for batch RWA calculations.
"""

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

from rwa_bob.paths import NCCR_MAPPING_PATH, PREPROD_CORE_INFO_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_bob.rwa_pydantic_schemas import (
    CORE_INFO_COLUMNS,
    COUNTRY_INFO_COLUMNS,
    CoreInfoRecord,
    CountryInfoRecord,
)

from .engine import RwaEngine


def load_csv_to_records(csv_path: Path, record_class, columns: tuple) -> list:
    """
    Load CSV file and convert to Pydantic records.

    Args:
        csv_path: Path to CSV file
        record_class: Pydantic model class
        columns: Expected column names

    Returns:
        List of validated records
    """
    records = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                record = record_class.model_validate(row)
                records.append(record)
            except Exception as e:
                print(f"Warning: Failed to parse row: {e}", file=sys.stderr)
    return records


def save_results_to_csv(results: list[dict], output_path: Path) -> None:
    """
    Save calculation results to CSV file.

    Args:
        results: List of result dictionaries
        output_path: Output CSV file path
    """
    if not results:
        print("No results to save", file=sys.stderr)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].keys())

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            # Convert Decimal to string for CSV
            row = {}
            for key, value in result.items():
                if isinstance(value, Decimal):
                    row[key] = str(value)
                elif isinstance(value, list):
                    row[key] = json.dumps(value)
                else:
                    row[key] = value
            writer.writerow(row)


def save_results_to_json(results: dict, output_path: Path) -> None:
    """
    Save calculation results to JSON file.

    Args:
        results: Results dictionary
        output_path: Output JSON file path
    """

    # Convert Decimal to float for JSON serialization
    def decimal_to_float(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: decimal_to_float(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [decimal_to_float(item) for item in obj]
        return obj

    json_data = decimal_to_float(results)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(json_data, handle, indent=2)


def run_batch_calculation(
    core_info_path: Path,
    country_info_path: Path,
    output_path: Path | None = None,
    output_format: str = "json",
    nccr_mapping_path: str | None = None,
    verbose: bool = False,
) -> None:
    """
    Run batch RWA calculation from CSV files.

    Args:
        core_info_path: Path to core info CSV
        country_info_path: Path to country info CSV
        output_path: Output file path (optional)
        output_format: Output format ("json" or "csv")
        nccr_mapping_path: Path to NCCR mapping CSV
        verbose: Enable verbose output
    """
    print(f"Loading core info from: {core_info_path}")
    core_info_list = load_csv_to_records(core_info_path, CoreInfoRecord, CORE_INFO_COLUMNS)
    print(f"Loaded {len(core_info_list)} core info records")

    print(f"Loading country info from: {country_info_path}")
    country_info_list = load_csv_to_records(
        country_info_path, CountryInfoRecord, COUNTRY_INFO_COLUMNS
    )
    print(f"Loaded {len(country_info_list)} country info records")

    print("Initializing RWA engine...")
    engine = RwaEngine(nccr_mapping_path)

    ref_info = engine.get_reference_data_info()
    print(f"Reference data loaded: {ref_info['nccr_grades_loaded']} NCCR grades")

    print("Calculating RWA...")
    results = engine.calculate_with_trace(core_info_list, country_info_list)

    print("\n" + "=" * 60)
    print("CALCULATION SUMMARY")
    print("=" * 60)
    print(f"Total exposures: {results['summary']['total_exposures']}")
    print(f"Successful calculations: {results['summary']['successful_calculations']}")
    print(f"Failed calculations: {results['summary']['failed_calculations']}")
    print(f"Total RWA (Basel 3.0): {results['summary']['total_rwa_basel_3_0']:,.2f}")
    print(f"Total RWA (Basel 3.1): {results['summary']['total_rwa_basel_3_1']:,.2f}")
    print("=" * 60 + "\n")

    if verbose and results["success_results"]:
        print("\nSample calculation trace (first exposure):")
        first_result = results["success_results"][0]
        print(f"Exposure ID: {first_result['id']}")
        for step in first_result.get("calculation_steps", [])[:10]:
            print(f"  - {step}")
        print()

    if output_path:
        print(f"Saving results to: {output_path}")
        if output_format == "json":
            save_results_to_json(results, output_path)
        elif output_format == "csv":
            save_results_to_csv(results["success_results"], output_path)
        print("Results saved successfully")

    if results["error_results"]:
        print(f"\nWarning: {len(results['error_results'])} exposures failed calculation")
        if verbose:
            for error in results["error_results"][:5]:
                print(f"  - {error['id']}: {error['messages']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Basel III RWA Calculator - Batch Processing CLI")

    parser.add_argument(
        "--core-info", type=Path, default=PREPROD_CORE_INFO_PATH, help="Path to core info CSV file"
    )

    parser.add_argument(
        "--country-info",
        type=Path,
        default=PREPROD_COUNTRY_INFO_PATH,
        help="Path to country info CSV file",
    )

    parser.add_argument("--output", type=Path, help="Output file path (optional)")

    parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="Output format (default: json)"
    )

    parser.add_argument(
        "--nccr-mapping", type=Path, default=NCCR_MAPPING_PATH, help="Path to NCCR mapping CSV file"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    try:
        run_batch_calculation(
            core_info_path=args.core_info,
            country_info_path=args.country_info,
            output_path=args.output,
            output_format=args.format,
            nccr_mapping_path=str(args.nccr_mapping),
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

# Made with Bob
