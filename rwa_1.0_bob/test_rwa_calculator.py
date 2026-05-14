"""
Test script for RWA calculator using preprod data.
"""

from pathlib import Path
from basel3_final_reforms.cli import run_batch_calculation


def test_with_preprod_data():
    """Test RWA calculator with preprod dataset."""
    
    print("="*70)
    print("BASEL III RWA CALCULATOR - TEST RUN")
    print("="*70)
    print()
    
    # Define file paths
    core_info_path = Path("preprod_core_info_1000.csv")
    country_info_path = Path("preprod_country_info.csv")
    output_path = Path("rwa_calculation_results.json")
    nccr_mapping_path = "nccr_mapping.csv"
    
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
            verbose=True
        )
        
        print("\n" + "="*70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*70)
        print(f"\nResults saved to: {output_path}")
        print("\nYou can now:")
        print("1. Review the JSON output file")
        print("2. Run the API server: python -m basel3_final_reforms.api")
        print("3. Use the CLI for other datasets")
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_with_preprod_data()

# Made with Bob
