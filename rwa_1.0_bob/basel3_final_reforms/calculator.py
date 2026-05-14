"""
RWA Calculator implementing Basel III standardised approach for credit risk.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from rwa_pydantic_schemas import (
    CoreInfoRecord,
    CountryInfoRecord,
    EntityClass,
    ExposureSubClass,
)
from .reference_data import ReferenceDataLoader


class RwaCalculator:
    """Calculator for Risk-Weighted Assets using Basel III standardised approach."""
    
    def __init__(self, reference_data: ReferenceDataLoader):
        """
        Initialize RWA calculator.
        
        Args:
            reference_data: Reference data loader instance
        """
        self.reference_data = reference_data
    
    def _get_entity_bucket(self, entity_class: EntityClass) -> str:
        """
        Map entity class to PD bucket for NCCR lookup.
        
        Args:
            entity_class: Entity class from exposure
        
        Returns:
            PD bucket name ("SOV", "BANK", or "CORP")
        """
        if entity_class in {EntityClass.SOV, EntityClass.PSE, EntityClass.MDB}:
            return "SOV"
        elif entity_class in {EntityClass.BANK, EntityClass.FI}:
            return "BANK"
        else:
            return "CORP"
    
    def _is_short_term_exposure(self, original_maturity: Decimal) -> bool:
        """
        Determine if exposure qualifies as short-term.
        
        Args:
            original_maturity: Original maturity in years
        
        Returns:
            True if short-term (≤ 1 year)
        """
        return original_maturity <= Decimal("1.0")
    
    def _calculate_risk_weight(
        self,
        core_info: CoreInfoRecord,
        country_info: Optional[CountryInfoRecord]
    ) -> Tuple[Decimal, List[str]]:
        """
        Calculate risk weight for an exposure.
        
        Args:
            core_info: Core exposure information
            country_info: Country information (optional)
        
        Returns:
            Tuple of (risk_weight, calculation_steps)
        """
        steps = []
        entity_class = core_info.entity_class
        
        # Determine which rating to use
        rating = core_info.counterparty_external_rating
        if not rating and core_info.trade_external_rating:
            rating = core_info.trade_external_rating
            steps.append(f"Using trade external rating: {rating}")
        elif rating:
            steps.append(f"Using counterparty external rating: {rating}")
        else:
            steps.append("No external rating available")
        
        is_short_term = self._is_short_term_exposure(core_info.original_maturity)
        if is_short_term:
            steps.append(f"Short-term exposure (maturity: {core_info.original_maturity} years)")
        
        # Calculate risk weight based on entity class
        if entity_class == EntityClass.SOV:
            rw = self.reference_data.get_sovereign_risk_weight(rating)
            steps.append(f"Sovereign risk weight: {rw * 100}%")
        
        elif entity_class == EntityClass.BANK:
            rw = self.reference_data.get_bank_risk_weight_ecra(rating, is_short_term)
            steps.append(f"Bank risk weight (ECRA): {rw * 100}%")
        
        elif entity_class == EntityClass.FI:
            # Financial institutions treated similarly to banks
            rw = self.reference_data.get_bank_risk_weight_ecra(rating, is_short_term)
            steps.append(f"Financial Institution risk weight: {rw * 100}%")
        
        elif entity_class == EntityClass.PSE:
            sovereign_rating = None
            if country_info:
                sovereign_rating = country_info.country_external_rating
            rw = self.reference_data.get_pse_risk_weight(
                sovereign_rating, 
                rating,
                use_option_2=False  # Using Option 1 by default
            )
            steps.append(f"PSE risk weight: {rw * 100}%")
        
        elif entity_class == EntityClass.MDB:
            # Check if eligible for 0% risk weight
            is_eligible = core_info.pra_io_mdb_3_1_flag == "Y"
            rw = self.reference_data.get_mdb_risk_weight(is_eligible, rating)
            steps.append(f"MDB risk weight (eligible={is_eligible}): {rw * 100}%")
        
        elif entity_class == EntityClass.RETAIL:
            rw = self.reference_data.get_retail_risk_weight()
            steps.append(f"Retail risk weight: {rw * 100}%")
        
        elif entity_class == EntityClass.CORP:
            rw = self.reference_data.get_corporate_risk_weight(rating)
            steps.append(f"Corporate risk weight: {rw * 100}%")
        
        else:
            # Other assets - default 100%
            rw = Decimal("1.0")
            steps.append(f"Other assets risk weight: {rw * 100}%")
        
        # Apply AVC (Asset Value Correlation) multiplier if applicable
        if core_info.avc != Decimal("1.0"):
            original_rw = rw
            rw = rw * core_info.avc
            steps.append(f"Applied AVC multiplier {core_info.avc}: {original_rw * 100}% → {rw * 100}%")
        
        return rw, steps
    
    def calculate_exposure_rwa(
        self,
        core_info: CoreInfoRecord,
        country_info: Optional[CountryInfoRecord]
    ) -> Dict:
        """
        Calculate RWA for a single exposure.
        
        Args:
            core_info: Core exposure information
            country_info: Country information
        
        Returns:
            Dictionary with calculation results
        """
        steps = [f"Processing exposure: {core_info.id}"]
        steps.append(f"Entity class: {core_info.entity_class.value}")
        steps.append(f"Sub-class: {core_info.sub_class.value}")
        steps.append(f"Exposure amount: {core_info.exposure_amount}")
        
        # Get PD from NCCR mapping
        entity_bucket = self._get_entity_bucket(core_info.entity_class)
        rating_grade = core_info.counterparty_fcy_internal_rating
        
        pd_basel_3_0 = self.reference_data.get_pd_for_rating(rating_grade, entity_bucket)
        pd_basel_3_1 = pd_basel_3_0  # Simplified - same for both
        
        if pd_basel_3_0:
            steps.append(f"PD from NCCR grade {rating_grade}: {pd_basel_3_0 * 100}%")
        
        # Calculate risk weight
        risk_weight, rw_steps = self._calculate_risk_weight(core_info, country_info)
        steps.extend(rw_steps)
        
        # Calculate RWA
        exposure_amount = core_info.exposure_amount
        rwa_basel_3_0 = exposure_amount * risk_weight
        rwa_basel_3_1_foundation = rwa_basel_3_0  # Simplified
        rwa_basel_3_1_standardised = rwa_basel_3_0
        
        steps.append(f"RWA calculation: {exposure_amount} × {risk_weight * 100}% = {rwa_basel_3_0}")
        
        # DLGD (Downturn LGD)
        dlgd_basel_3_0 = core_info.counterparty_dlgd
        dlgd_basel_3_1 = dlgd_basel_3_0
        
        if country_info and country_info.country_dlgd:
            steps.append(f"Country DLGD available: {country_info.country_dlgd}")
        
        result = {
            "id": core_info.id,
            "counterparty_gid": core_info.counterparty_gid,
            "basel_3_0_pd": pd_basel_3_0,
            "basel_3_1_pd": pd_basel_3_1,
            "basel_3_0_dlgd": dlgd_basel_3_0,
            "basel_3_1_dlgd": dlgd_basel_3_1,
            "basel_3_0_rw_final": risk_weight,
            "basel_3_0_rwa": rwa_basel_3_0,
            "basel_3_0_ro_rw": risk_weight,  # Simplified - same as final RW
            "basel_3_1_rw_foundation": risk_weight,
            "basel_3_1_rwa_foundation": rwa_basel_3_1_foundation,
            "basel_3_1_ro_rw_foundation": risk_weight,
            "basel_3_1_rw_standardised": risk_weight,
            "basel_3_1_rwa_standardised": rwa_basel_3_1_standardised,
            "basel_3_1_ro_rw_standardised": risk_weight,
            "basel_3_1_rw_final": risk_weight,
            "basel_3_1_rwa_final": rwa_basel_3_1_standardised,
            "basel_3_1_ro_rw_final": risk_weight,
            "calculation_steps": steps,
        }
        
        return result
    
    def calculate_portfolio_rwa(
        self,
        core_info_list: List[CoreInfoRecord],
        country_info_list: List[CountryInfoRecord]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Calculate RWA for a portfolio of exposures.
        
        Args:
            core_info_list: List of core exposure records
            country_info_list: List of country information records
        
        Returns:
            Tuple of (success_results, error_results)
        """
        # Build country lookup
        country_lookup = {
            country.incorporation_country: country 
            for country in country_info_list
        }
        
        success_results = []
        error_results = []
        
        for core_info in core_info_list:
            try:
                country_info = country_lookup.get(core_info.incorporation_country)
                result = self.calculate_exposure_rwa(core_info, country_info)
                success_results.append(result)
            except Exception as e:
                error_results.append({
                    "id": core_info.id,
                    "messages": [f"Calculation error: {str(e)}"]
                })
        
        return success_results, error_results

# Made with Bob
