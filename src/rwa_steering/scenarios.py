from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScenarioAssumption:
    """Versioned scenario knobs used by the steering service.

    The scenario library exposes the same conceptual levers from the executive plan: regime
    label, dynamic risk budget, exposure growth, rating migration, DLGD shock and FX shock.
    """

    scenario_id: str
    scenario_name: str
    regime_label: str
    regime_score: Decimal
    risk_budget_multiplier: Decimal
    exposure_growth_rate: Decimal
    rating_notch_shift: int
    dlgd_multiplier: Decimal
    dlgd_addon: Decimal
    fx_shocks: dict[str, Decimal]
    description: str


SCENARIO_LIBRARY: dict[str, ScenarioAssumption] = {
    "BASE": ScenarioAssumption(
        scenario_id="BASE",
        scenario_name="Base case",
        regime_label="NORMAL",
        regime_score=Decimal("0.30"),
        risk_budget_multiplier=Decimal("1.00"),
        exposure_growth_rate=Decimal("0.020"),
        rating_notch_shift=0,
        dlgd_multiplier=Decimal("1.00"),
        dlgd_addon=Decimal("0.00"),
        fx_shocks={"EUR": Decimal("0.00"), "USD": Decimal("0.01"), "GBP": Decimal("0.01")},
        description="Expected portfolio evolution under normal credit conditions.",
    ),
    "DOWNSIDE": ScenarioAssumption(
        scenario_id="DOWNSIDE",
        scenario_name="Downside",
        regime_label="LATE_CYCLE",
        regime_score=Decimal("0.60"),
        risk_budget_multiplier=Decimal("1.15"),
        exposure_growth_rate=Decimal("-0.010"),
        rating_notch_shift=1,
        dlgd_multiplier=Decimal("1.10"),
        dlgd_addon=Decimal("0.01"),
        fx_shocks={"EUR": Decimal("0.00"), "USD": Decimal("0.04"), "GBP": Decimal("0.03")},
        description="Mild credit deterioration with moderate downgrade pressure.",
    ),
    "STRESS": ScenarioAssumption(
        scenario_id="STRESS",
        scenario_name="Stress",
        regime_label="CREDIT_STRESS",
        regime_score=Decimal("0.90"),
        risk_budget_multiplier=Decimal("1.40"),
        exposure_growth_rate=Decimal("-0.050"),
        rating_notch_shift=2,
        dlgd_multiplier=Decimal("1.25"),
        dlgd_addon=Decimal("0.04"),
        fx_shocks={
            "EUR": Decimal("0.00"),
            "USD": Decimal("0.08"),
            "GBP": Decimal("0.04"),
            "CHF": Decimal("0.06"),
            "PLN": Decimal("0.05"),
        },
        description="Severe but plausible credit stress with broad downgrade and LGD pressure.",
    ),
    "RECOVERY": ScenarioAssumption(
        scenario_id="RECOVERY",
        scenario_name="Recovery",
        regime_label="RECOVERY",
        regime_score=Decimal("0.20"),
        risk_budget_multiplier=Decimal("0.85"),
        exposure_growth_rate=Decimal("0.030"),
        rating_notch_shift=-1,
        dlgd_multiplier=Decimal("0.95"),
        dlgd_addon=Decimal("0.00"),
        fx_shocks={"EUR": Decimal("0.00"), "USD": Decimal("-0.01"), "GBP": Decimal("-0.01")},
        description="Improving credit environment with selective rating upgrades.",
    ),
}


def get_scenario(scenario_id: str) -> ScenarioAssumption:
    """Return a scenario by id using a case-insensitive lookup.

    Raises:
        ValueError: If the scenario id is not part of the built-in scenario library.
    """

    try:
        return SCENARIO_LIBRARY[scenario_id.upper()]
    except KeyError as exc:
        available = ", ".join(sorted(SCENARIO_LIBRARY))
        raise ValueError(f"Unknown scenario {scenario_id!r}; available: {available}") from exc
