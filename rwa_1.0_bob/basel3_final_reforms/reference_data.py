"""
Reference data for Basel III calculations including risk weights and PD mappings.
"""

from decimal import Decimal
from typing import Dict, Optional
from pathlib import Path
import csv


class ReferenceDataLoader:
    """Loads and manages reference data for RWA calculations."""
    
    def __init__(self, nccr_mapping_path: Optional[str] = None):
        """
        Initialize reference data loader.
        
        Args:
            nccr_mapping_path: Path to NCCR mapping CSV file
        """
        self.nccr_mapping_path = nccr_mapping_path or "nccr_mapping.csv"
        self.nccr_pd_mapping: Dict[str, Dict[str, Decimal]] = {}
        self._load_nccr_mapping()
    
    def _parse_percent(self, value: str) -> Decimal:
        """Parse percentage string to Decimal."""
        text = value.strip()
        if text.endswith("%"):
            return Decimal(text[:-1]) / Decimal("100")
        return Decimal(text)
    
    def _load_nccr_mapping(self) -> None:
        """Load NCCR to PD mapping from CSV file."""
        path = Path(self.nccr_mapping_path)
        if not path.exists():
            raise FileNotFoundError(f"NCCR mapping file not found: {path}")
        
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                grade = (row.get("CRR") or "").strip()
                if not grade:
                    continue
                self.nccr_pd_mapping[grade] = {
                    "SOV": self._parse_percent(row["SOV"]),
                    "CORP": self._parse_percent(row["CORP"]),
                    "BANK": self._parse_percent(row["BANK"]),
                }
        
        if not self.nccr_pd_mapping:
            raise RuntimeError(f"No NCCR grades loaded from {path}")
    
    def get_pd_for_rating(self, rating_grade: str, entity_bucket: str) -> Optional[Decimal]:
        """
        Get PD (Probability of Default) for a given rating grade and entity type.
        
        Args:
            rating_grade: NCCR rating grade (e.g., "2.1", "3.2")
            entity_bucket: Entity bucket ("SOV", "CORP", or "BANK")
        
        Returns:
            PD as Decimal or None if not found
        """
        if rating_grade not in self.nccr_pd_mapping:
            return None
        if entity_bucket not in self.nccr_pd_mapping[rating_grade]:
            return None
        return self.nccr_pd_mapping[rating_grade][entity_bucket]
    
    def get_sovereign_risk_weight(self, external_rating: Optional[str]) -> Decimal:
        """
        Get risk weight for sovereign exposures based on external rating.
        
        Args:
            external_rating: External rating (e.g., "AAA", "BBB+")
        
        Returns:
            Risk weight as Decimal (e.g., 0.0 for 0%, 0.5 for 50%)
        """
        if not external_rating or external_rating == "UNRATED":
            return Decimal("1.0")  # 100%
        
        rating_upper = external_rating.upper()
        
        # AAA to AA-: 0%
        if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
            return Decimal("0.0")
        # A+ to A-: 20%
        elif rating_upper in ["A+", "A", "A-"]:
            return Decimal("0.2")
        # BBB+ to BBB-: 50%
        elif rating_upper in ["BBB+", "BBB", "BBB-"]:
            return Decimal("0.5")
        # BB+ to B-: 100%
        elif rating_upper in ["BB+", "BB", "BB-", "B+", "B", "B-"]:
            return Decimal("1.0")
        # Below B-: 150%
        else:
            return Decimal("1.5")
    
    def get_bank_risk_weight_ecra(
        self, 
        external_rating: Optional[str], 
        is_short_term: bool = False
    ) -> Decimal:
        """
        Get risk weight for bank exposures using ECRA (External Credit Risk Assessment).
        
        Args:
            external_rating: External rating
            is_short_term: Whether exposure has short-term maturity
        
        Returns:
            Risk weight as Decimal
        """
        if not external_rating or external_rating == "UNRATED":
            # Fall back to SCRA Grade B
            return Decimal("0.5") if is_short_term else Decimal("0.75")
        
        rating_upper = external_rating.upper()
        
        # AAA to AA-
        if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
            return Decimal("0.2")
        # A+ to A-
        elif rating_upper in ["A+", "A", "A-"]:
            return Decimal("0.2") if is_short_term else Decimal("0.3")
        # BBB+ to BBB-
        elif rating_upper in ["BBB+", "BBB", "BBB-"]:
            return Decimal("0.2") if is_short_term else Decimal("0.5")
        # BB+ to B-
        elif rating_upper in ["BB+", "BB", "BB-", "B+", "B", "B-"]:
            return Decimal("0.5") if is_short_term else Decimal("1.0")
        # Below B-
        else:
            return Decimal("1.5")
    
    def get_corporate_risk_weight(self, external_rating: Optional[str]) -> Decimal:
        """
        Get risk weight for corporate exposures.
        
        Args:
            external_rating: External rating
        
        Returns:
            Risk weight as Decimal
        """
        if not external_rating or external_rating == "UNRATED":
            return Decimal("1.0")  # 100%
        
        rating_upper = external_rating.upper()
        
        # AAA to AA-: 20%
        if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
            return Decimal("0.2")
        # A+ to A-: 50%
        elif rating_upper in ["A+", "A", "A-"]:
            return Decimal("0.5")
        # BBB+ to BB-: 100%
        elif rating_upper in ["BBB+", "BBB", "BBB-", "BB+", "BB", "BB-"]:
            return Decimal("1.0")
        # B+ to B-: 100%
        elif rating_upper in ["B+", "B", "B-"]:
            return Decimal("1.0")
        # Below B-: 150%
        else:
            return Decimal("1.5")
    
    def get_retail_risk_weight(self) -> Decimal:
        """Get standard risk weight for retail exposures."""
        return Decimal("0.75")  # 75%
    
    def get_pse_risk_weight(
        self, 
        sovereign_rating: Optional[str],
        pse_rating: Optional[str],
        use_option_2: bool = False
    ) -> Decimal:
        """
        Get risk weight for Public Sector Entity exposures.
        
        Args:
            sovereign_rating: Sovereign rating of the country
            pse_rating: PSE's own rating
            use_option_2: Whether to use Option 2 (PSE rating based)
        
        Returns:
            Risk weight as Decimal
        """
        if use_option_2 and pse_rating:
            rating_upper = pse_rating.upper()
            if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
                return Decimal("0.2")
            elif rating_upper in ["A+", "A", "A-"]:
                return Decimal("0.5")
            elif rating_upper in ["BBB+", "BBB", "BBB-"]:
                return Decimal("0.5")
            elif rating_upper in ["BB+", "BB", "BB-", "B+", "B", "B-"]:
                return Decimal("1.0")
            elif pse_rating == "UNRATED":
                return Decimal("0.5")
            else:
                return Decimal("1.5")
        
        # Option 1: Based on sovereign rating
        if not sovereign_rating or sovereign_rating == "UNRATED":
            return Decimal("1.0")
        
        rating_upper = sovereign_rating.upper()
        if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
            return Decimal("0.2")
        elif rating_upper in ["A+", "A", "A-"]:
            return Decimal("0.5")
        else:
            return Decimal("1.0")
    
    def get_mdb_risk_weight(
        self, 
        is_eligible_zero_rw: bool,
        external_rating: Optional[str] = None
    ) -> Decimal:
        """
        Get risk weight for Multilateral Development Bank exposures.
        
        Args:
            is_eligible_zero_rw: Whether MDB is eligible for 0% risk weight
            external_rating: External rating if applicable
        
        Returns:
            Risk weight as Decimal
        """
        if is_eligible_zero_rw:
            return Decimal("0.0")
        
        if not external_rating or external_rating == "UNRATED":
            return Decimal("0.5")
        
        rating_upper = external_rating.upper()
        if rating_upper in ["AAA", "AA+", "AA", "AA-"]:
            return Decimal("0.2")
        elif rating_upper in ["A+", "A", "A-"]:
            return Decimal("0.3")
        elif rating_upper in ["BBB+", "BBB", "BBB-"]:
            return Decimal("0.5")
        elif rating_upper in ["BB+", "BB", "BB-", "B+", "B", "B-"]:
            return Decimal("1.0")
        else:
            return Decimal("1.5")

# Made with Bob
