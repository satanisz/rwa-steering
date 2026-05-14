"""
Main RWA calculation engine orchestrating the entire calculation workflow.
"""

from decimal import Decimal
from typing import List, Optional
from rwa_pydantic_schemas import (
    CoreInfoRecord,
    CountryInfoRecord,
    OutputSuccessRecord,
    RwaError,
    OutputSummary,
)
from .reference_data import ReferenceDataLoader
from .calculator import RwaCalculator
from .models import RwaCalculationRequest, RwaCalculationResponse


class RwaEngine:
    """
    Main engine for RWA calculations.
    Orchestrates reference data loading, validation, and calculation workflow.
    """
    
    def __init__(self, nccr_mapping_path: Optional[str] = None):
        """
        Initialize RWA calculation engine.
        
        Args:
            nccr_mapping_path: Path to NCCR mapping CSV file
        """
        self.reference_data = ReferenceDataLoader(nccr_mapping_path)
        self.calculator = RwaCalculator(self.reference_data)
    
    def calculate(self, request: RwaCalculationRequest) -> RwaCalculationResponse:
        """
        Calculate RWA for a portfolio of exposures.
        
        Args:
            request: RWA calculation request with core and country info
        
        Returns:
            RWA calculation response with results and summary
        """
        # Perform calculations
        success_results, error_results = self.calculator.calculate_portfolio_rwa(
            request.core_info,
            request.country_info
        )
        
        # Convert to output records
        success_records = []
        for result in success_results:
            # Remove calculation_steps before creating output record
            calc_steps = result.pop("calculation_steps", [])
            
            # Create output record
            output_record = OutputSuccessRecord(**result)
            success_records.append(output_record)
        
        # Convert errors
        errors = [RwaError(**error) for error in error_results]
        
        # Create summary
        summary = OutputSummary(
            input_data_records=len(request.core_info),
            output_successful_records=len(success_records),
            output_successful_projection_records=0,  # Not implemented yet
            output_failure_records=len(errors)
        )
        
        return RwaCalculationResponse(
            success_records=success_records,
            errors=errors,
            summary=summary
        )
    
    def calculate_with_trace(
        self,
        core_info_list: List[CoreInfoRecord],
        country_info_list: List[CountryInfoRecord]
    ) -> dict:
        """
        Calculate RWA with detailed calculation traces.
        
        Args:
            core_info_list: List of core exposure records
            country_info_list: List of country information records
        
        Returns:
            Dictionary with results and detailed traces
        """
        success_results, error_results = self.calculator.calculate_portfolio_rwa(
            core_info_list,
            country_info_list
        )
        
        return {
            "success_results": success_results,
            "error_results": error_results,
            "summary": {
                "total_exposures": len(core_info_list),
                "successful_calculations": len(success_results),
                "failed_calculations": len(error_results),
                "total_rwa_basel_3_0": sum(
                    r["basel_3_0_rwa"] for r in success_results
                ),
                "total_rwa_basel_3_1": sum(
                    r["basel_3_1_rwa_final"] for r in success_results
                ),
            }
        }
    
    def get_reference_data_info(self) -> dict:
        """
        Get information about loaded reference data.
        
        Returns:
            Dictionary with reference data statistics
        """
        return {
            "nccr_grades_loaded": len(self.reference_data.nccr_pd_mapping),
            "nccr_grades": list(self.reference_data.nccr_pd_mapping.keys()),
        }

# Made with Bob
