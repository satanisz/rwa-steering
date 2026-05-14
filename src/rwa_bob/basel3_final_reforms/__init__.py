"""
Basel III Final Reforms - RWA Calculator
A modular Python application for calculating Risk-Weighted Assets (RWA)
according to Basel III final reforms.
"""

__version__ = "0.1.0"

from .engine import RwaEngine
from .models import RwaCalculationRequest, RwaCalculationResponse

__all__ = ["RwaCalculationRequest", "RwaCalculationResponse", "RwaEngine"]

# Made with Bob
