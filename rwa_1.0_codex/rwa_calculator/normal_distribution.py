from __future__ import annotations

from statistics import NormalDist


class NormalDistribution:
    """Normal CDF/PPF adapter.

    SciPy is preferred in the production microservice profile. The standard
    library fallback keeps the restricted CLI usable when dependencies are not
    installed.
    """

    def __init__(self) -> None:
        try:
            from scipy.stats import norm  # type: ignore
        except Exception:  # noqa: BLE001 - optional dependency fallback.
            self._scipy_norm = None
            self._stdlib_norm = NormalDist()
        else:
            self._scipy_norm = norm
            self._stdlib_norm = None

    @property
    def backend(self) -> str:
        return "scipy.stats.norm" if self._scipy_norm is not None else "statistics.NormalDist"

    def cdf(self, value: float) -> float:
        if self._scipy_norm is not None:
            return float(self._scipy_norm.cdf(value))
        return self._stdlib_norm.cdf(value)  # type: ignore[union-attr]

    def inv_cdf(self, probability: float) -> float:
        if self._scipy_norm is not None:
            return float(self._scipy_norm.ppf(probability))
        return self._stdlib_norm.inv_cdf(probability)  # type: ignore[union-attr]
