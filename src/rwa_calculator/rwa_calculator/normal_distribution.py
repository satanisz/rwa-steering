from __future__ import annotations

from statistics import NormalDist


class NormalDistribution:
    """Normal CDF/PPF adapter.

    SciPy is preferred in the production microservice profile. The standard
    library fallback keeps the restricted CLI usable when dependencies are not
    installed.
    """

    def __init__(self) -> None:
        """Select SciPy at runtime, otherwise initialise the standard-library fallback."""
        try:
            from scipy.stats import norm  # type: ignore
        except Exception:
            self._scipy_norm = None
            self._stdlib_norm = NormalDist()
        else:
            self._scipy_norm = norm
            self._stdlib_norm = None

    @property
    def backend(self) -> str:
        """Return the active normal distribution implementation for health checks."""
        return "scipy.stats.norm" if self._scipy_norm is not None else "statistics.NormalDist"

    def cdf(self, value: float) -> float:
        """Evaluate the standard normal cumulative distribution function."""
        if self._scipy_norm is not None:
            return float(self._scipy_norm.cdf(value))
        return self._stdlib_norm.cdf(value)  # type: ignore[union-attr]

    def inv_cdf(self, probability: float) -> float:
        """Evaluate the standard normal inverse cumulative distribution function."""
        if self._scipy_norm is not None:
            return float(self._scipy_norm.ppf(probability))
        return self._stdlib_norm.inv_cdf(probability)  # type: ignore[union-attr]
