# Executive Plan 2: Missing Input Generation for RWA Steering PoC

## 1. Executive Summary

The RWA Steering PoC requires more input data than a static RWA Calculator. The current calculator can process exposure records, but forecasting, scenario analysis, driver attribution and steering recommendations require additional inputs that are not yet present in the current `CoreInfo` and output schemas.

This plan defines how to generate the missing inputs in a controlled, auditable and hackathon-ready way. The objective is not to fabricate production data. The objective is to create a synthetic but realistic non-production dataset that allows the PoC to demonstrate the full target workflow:

```text
current portfolio
  + scenario assumptions
  + rating migration
  + FX assumptions
  + regulatory calendar
  + profitability / steering metadata
  + segmentation
  -> projected RWA
  -> attribution
  -> recommendations
```

All generated inputs must be clearly labelled as synthetic and must pass Pydantic validation before use.

## 2. Current Input Baseline

The existing `CoreInfo`-style input contains:

- `id`
- `counterparty_gid`
- `hsbc_intragroup_flag`
- `counterparty_fcy_internal_rating`
- `counterparty_lcy_internal_rating`
- `incorporation_country`
- `lgd_classification`
- `pd_classification`
- `entity_class`
- `sub_class`
- `counterparty_dlgd`
- `govt_guarantee_flag`
- `trade_external_rating`
- `counterparty_external_rating`
- `avc`
- `pra_io_mdb_3_1_flag`
- `exposure_ccy`
- `bond_or_loan_flag`
- `original_maturity`
- `residual_maturity`
- `exposure_amount`
- `expected_yield`
- `counterparty_credit_quality_grade`

The current generated dataset contains 1,000 synthetic assets and a small country reference file.

This is enough for a calculator demo, but not enough for full steering.

## 3. Missing Input Categories

The missing inputs fall into eight groups:

1. Scenario assumptions.
2. Forecast calendar.
3. Rating migration assumptions.
4. DLGD and collateral assumptions.
5. FX and macro assumptions.
6. Regulatory overlay inputs.
7. Profitability and business value inputs.
8. Steering action constraints.

Each group should be generated as a separate versioned file so it can be audited, swapped or upgraded independently.

## 4. Target Input Files

The missing-input generation package should create:

```text
generated_inputs/
  manifest.json
  scenario_definitions.csv
  forecast_calendar.csv
  segment_growth_assumptions.csv
  rating_migration_matrix.csv
  dlgd_scenario_assumptions.csv
  fx_scenario_rates.csv
  macro_regime_indicators.csv
  regulatory_overlay_selection.csv
  profitability_inputs.csv
  steering_action_constraints.csv
  portfolio_strategy_limits.csv
  data_quality_flags.csv
```

The existing files remain:

```text
preprod_core_info_1000.csv
preprod_country_info.csv
nccr_mapping.csv
regulatory_reference_data/
```

## 5. Data Generation Principles

The synthetic input generator must follow these principles:

- Deterministic seed for reproducibility.
- No production customer data.
- All IDs synthetic.
- All assumptions versioned.
- All values within realistic banking ranges.
- All files validated with Pydantic.
- All scenario shocks traceable to named assumption sets.
- Generated inputs must be consistent with the existing 1,000 asset file.
- Missing values must be intentional and documented, not accidental.

## 6. Scenario Definitions

File: `scenario_definitions.csv`

Purpose: define the available forecast scenarios.

Required columns:

```text
scenario_id
scenario_name
scenario_type
severity_level
description
is_active
assumption_version
```

Recommended rows:

```text
BASE
DOWNSIDE
STRESS
RECOVERY
```

Example:

```text
scenario_id=scn_stress_001
scenario_name=STRESS
scenario_type=macro_credit_stress
severity_level=3
description=Severe but plausible credit deterioration scenario
is_active=true
assumption_version=2026Q2_SEED
```

## 7. Forecast Calendar

File: `forecast_calendar.csv`

Purpose: define projection horizons.

Required columns:

```text
as_of_date
projection_date
projection_year
projection_quarter
horizon_months
is_year_end
regulatory_year
```

Recommended dates:

- Current as-of date.
- 2026-12-31.
- 2027-12-31.
- 2028-12-31.
- 2029-12-31.
- 2030-12-31.

Why this matters:

- EU output floor phase-in runs to 2030.
- UK PRA Basel 3.1 starts in 2027 and reaches 72.5% by 2030 in the seed overlay.
- Switzerland has final Basel III implementation from 2025 and output floor relevance around 2028.

## 8. Segment Growth Assumptions

File: `segment_growth_assumptions.csv`

Purpose: forecast exposure amount by segment.

Required columns:

```text
scenario_id
projection_year
entity_class
sub_class
exposure_ccy
growth_rate
amortization_rate
prepayment_rate
renewal_rate
new_origination_rate
```

Recommended generation logic:

BASE:

- corporate growth: 2% to 5%.
- bank/FI growth: 0% to 3%.
- retail growth: 1% to 4%.
- sovereign/PSE stable.

DOWNSIDE:

- lower growth or mild contraction.
- higher prepayment in selected segments.
- lower renewal rate for weak ratings.

STRESS:

- contraction in new origination.
- lower renewal.
- forced reduction in high-risk segments.
- higher drawdown may be modelled later if OBS data exists.

RECOVERY:

- renewed growth in selected lower-risk segments.

Formula:

```text
projected_exposure =
    current_exposure
  * (1 + growth_rate)
  * (1 - amortization_rate)
  * (1 - prepayment_rate)
  + new_origination_component
```

## 9. Rating Migration Matrix

File: `rating_migration_matrix.csv`

Purpose: define probability of moving from current NCCR grade to projected NCCR grade.

Required columns:

```text
scenario_id
projection_year
entity_class
from_rating
to_rating
migration_probability
```

Rating scale must come from `nccr_mapping.csv`, for example:

```text
0.1, 1.1, 1.2, 2.1, ..., 8.3
```

Generation logic:

BASE:

- high diagonal probability.
- small one-notch upgrade/downgrade probabilities.

DOWNSIDE:

- lower diagonal.
- more one-notch downgrades.
- some two-notch downgrades for weaker grades.

STRESS:

- material downgrade probability.
- low upgrade probability.
- stronger downgrade for `CORP`, `BANK` and `FI`.

RECOVERY:

- some upgrades.
- low severe downgrade probability.

Validation:

- Probabilities must sum to 1 per scenario, year, entity class and from-rating.
- No target rating may fall outside the rating scale.
- Default/worst ratings may be absorbing or near-absorbing depending on scenario.

## 10. DLGD Scenario Assumptions

File: `dlgd_scenario_assumptions.csv`

Purpose: forecast `counterparty_dlgd`.

Required columns:

```text
scenario_id
projection_year
entity_class
sub_class
base_multiplier
additive_shock
floor
cap
collateral_haircut_multiplier
```

Example logic:

```text
projected_dlgd =
    min(max(current_dlgd * base_multiplier + additive_shock, floor), cap)
```

Recommended values:

BASE:

- multiplier 1.00.
- additive shock 0.00.

DOWNSIDE:

- multiplier 1.05 to 1.15.
- additive shock 0.01 to 0.03.

STRESS:

- multiplier 1.15 to 1.35.
- additive shock 0.03 to 0.08.

RECOVERY:

- multiplier 0.95 to 1.00.
- additive shock 0.00.

## 11. FX Scenario Rates

File: `fx_scenario_rates.csv`

Purpose: convert exposure amounts to reporting currency and attribute FX-driven RWA movement.

Required columns:

```text
scenario_id
projection_date
from_ccy
to_ccy
fx_rate
fx_shock_pct
source
```

For PoC, use deterministic synthetic FX rates. Do not claim they are market forecasts.

Recommended reporting currency:

- EUR for EU/Swiss demo.
- GBP for UK PRA demo.
- PLN only if the story is focused on a Polish bank subsidiary.

Example:

```text
scenario_id=STRESS
projection_date=2027-12-31
from_ccy=USD
to_ccy=EUR
fx_rate=1.12
fx_shock_pct=0.08
source=synthetic_stress_seed
```

## 12. Macro Regime Indicators

File: `macro_regime_indicators.csv`

Purpose: implement the article-inspired regime logic without needing full ML.

Required columns:

```text
scenario_id
projection_date
volatility_index
credit_spread_bps
yield_curve_slope_bps
liquidity_index
unemployment_proxy
gdp_growth_proxy
regime_label
regime_score
```

Suggested regime labels:

- `LOW_VOL_GROWTH`.
- `NORMAL`.
- `LATE_CYCLE`.
- `CREDIT_STRESS`.
- `RECOVERY`.

Regime assignment can be rule-based:

```text
if credit_spread_bps > 250 and volatility_index > 30:
    regime_label = CREDIT_STRESS
elif yield_curve_slope_bps < 0:
    regime_label = LATE_CYCLE
else:
    regime_label = NORMAL
```

This gives hackathon judges the core idea from the article without needing fragile neural network training.

## 13. Regulatory Overlay Selection

File: `regulatory_overlay_selection.csv`

Purpose: select which jurisdiction overlay applies to each portfolio or legal entity.

Required columns:

```text
portfolio_id
legal_entity_id
jurisdiction_overlay
reporting_currency
application_date
output_floor_enabled
national_discretion_profile
```

Allowed overlays:

- `EU_CRR3_EBA`.
- `UK_PRA_BASEL_3_1`.
- `CH_FINMA_BASEL_III_FINAL`.

This file must map to the existing `regulatory_reference_data/` package.

## 14. Profitability Inputs

File: `profitability_inputs.csv`

Purpose: support steering recommendations. RWA steering without profitability can recommend reducing profitable business, which is not credible.

Required columns:

```text
id
net_revenue
funding_cost
expected_loss
operating_cost
capital_cost_rate
raroc
relationship_value_score
strategic_importance_score
```

Recommended synthetic generation:

```text
net_revenue = exposure_amount * expected_yield
funding_cost = exposure_amount * funding_cost_rate
expected_loss = exposure_amount * PD * DLGD
operating_cost = exposure_amount * segment_operating_cost_rate
capital_cost = RWA * capital_cost_rate
raroc = (net_revenue - funding_cost - expected_loss - operating_cost) / capital
```

If current RWA is not available at input-generation time, use a placeholder capital proxy and recalculate after the first calculator run.

## 15. Steering Action Constraints

File: `steering_action_constraints.csv`

Purpose: define which actions are allowed for each exposure segment.

Required columns:

```text
entity_class
sub_class
rating_band
action_code
is_allowed
max_exposure_reduction_pct
min_notice_months
implementation_complexity
business_cost_factor
requires_credit_approval
requires_client_consent
```

Example rules:

- Sovereign exposures: do not apply client-level repricing actions.
- Retail exposures: do not apply bespoke syndication action.
- Corporate loans: allow repricing, collateral enhancement, non-renewal.
- Bonds: allow sell-down but not collateral enhancement.
- Intragroup exposures: actions may require treasury/legal approval.

## 16. Portfolio Strategy Limits

File: `portfolio_strategy_limits.csv`

Purpose: avoid unrealistic recommendations.

Required columns:

```text
portfolio_id
scenario_id
projection_year
entity_class
sub_class
max_rwa_growth_pct
max_exposure_growth_pct
min_raroc
max_single_counterparty_concentration_pct
target_rwa_density
```

This allows the recommendation engine to say:

```text
Corporate specialised lending breaches target RWA density under STRESS.
Reduce growth or increase collateral for top contributors.
```

## 17. Data Quality Flags

File: `data_quality_flags.csv`

Purpose: separate true economic steering actions from data remediation actions.

Required columns:

```text
id
field_name
quality_issue_code
severity
is_blocking
recommended_fix
```

Possible issue codes:

- `MISSING_EXTERNAL_RATING`.
- `MISSING_DLGD`.
- `SUSPICIOUS_MATURITY`.
- `RESIDUAL_GT_ORIGINAL_MATURITY`.
- `UNKNOWN_COUNTRY`.
- `UNKNOWN_CURRENCY`.
- `MISSING_PROFITABILITY`.
- `REGULATORY_FLAG_UNCONFIRMED`.

For bank-grade credibility, the PoC should show that some RWA increases are caused by data quality, not only economic deterioration.

## 18. Pydantic Schemas to Add

The input generator should define Pydantic models for:

```text
ScenarioDefinition
ForecastCalendarRow
SegmentGrowthAssumption
RatingMigrationRow
DlgdScenarioAssumption
FxScenarioRate
MacroRegimeIndicator
RegulatoryOverlaySelection
ProfitabilityInput
SteeringActionConstraint
PortfolioStrategyLimit
DataQualityFlag
GeneratedInputManifest
```

Validation examples:

- Migration probabilities sum to 1.
- FX rate is positive.
- Projection date is after as-of date.
- Scenario ID exists in scenario definitions.
- Entity class exists in core schema.
- Currency is ISO-style 3-letter uppercase code.
- Action constraints reference known actions.

## 19. Generation Workflow

Recommended workflow:

```text
1. Load current synthetic assets.
2. Load nccr_mapping.csv.
3. Load regulatory_reference_data manifest.
4. Generate scenario definitions.
5. Generate forecast calendar.
6. Generate segment growth assumptions.
7. Generate rating migration matrices.
8. Generate DLGD shocks.
9. Generate FX scenario rates.
10. Generate macro regime indicators.
11. Generate profitability proxies.
12. Generate steering constraints.
13. Generate portfolio strategy limits.
14. Generate data quality flags.
15. Validate all generated files with Pydantic.
16. Write manifest with seed, row counts and hashes.
```

## 20. Manifest Requirements

File: `generated_inputs/manifest.json`

Required fields:

```json
{
  "package_name": "rwa_steering_missing_inputs_seed",
  "version_id": "2026Q2_HACKATHON_SEED_V1",
  "generated_on": "2026-05-14",
  "random_seed": 20260514,
  "production_ready": false,
  "source_files": [],
  "generated_files": [],
  "row_counts": {},
  "validation_status": "PASSED",
  "known_limitations": []
}
```

## 21. Data Volume

Recommended hackathon volume:

- 1,000 asset records.
- 4 scenarios.
- 5-6 projection dates.
- 8 entity classes.
- 6 currencies.
- 20+ rating grades.

Expected generated rows:

- scenario definitions: 4.
- forecast calendar: 6.
- growth assumptions: several hundred depending on segmentation.
- rating migration matrix: thousands of rows.
- DLGD assumptions: several hundred.
- FX rates: around 4 scenarios x 6 dates x currency pairs.
- profitability inputs: 1,000.
- steering constraints: 100-300.
- strategy limits: 100-300.
- data quality flags: 50-150 synthetic issues.

## 22. Quality Gates

The generated input package is accepted only when:

- All files exist.
- All files have headers.
- All rows validate.
- No duplicate primary keys where uniqueness is required.
- Migration probabilities sum to 1.
- FX rates are positive.
- Scenario IDs are consistent across files.
- Projection dates are consistent.
- All asset IDs in profitability and data quality files exist in core input.
- All generated values are reproducible from seed.

## 23. Integration With PoC

The PoC should consume generated inputs as follows:

```text
scenario_definitions.csv
  -> scenario registry

forecast_calendar.csv
  -> projection dates

segment_growth_assumptions.csv
  -> exposure amount forecast

rating_migration_matrix.csv
  -> rating forecast

dlgd_scenario_assumptions.csv
  -> DLGD forecast

fx_scenario_rates.csv
  -> FX conversion and attribution

macro_regime_indicators.csv
  -> regime label and regime score

regulatory_overlay_selection.csv
  -> jurisdiction rules

profitability_inputs.csv
  -> RAROC and business cost

steering_action_constraints.csv
  -> allowed actions

portfolio_strategy_limits.csv
  -> target limits and breaches

data_quality_flags.csv
  -> remediation recommendations
```

## 24. Hackathon Story

The generated missing inputs let the team tell a credible story:

```text
We started with 1,000 bank assets.
We added forecast assumptions, rating migration, FX, macro regimes and regulatory calendars.
We projected the future portfolio.
We ran each future portfolio through the existing RWA Calculator.
We explained RWA movement.
We recommended actions.
```

This is the difference between a calculator and a steering tool.

## 25. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| Synthetic assumptions look arbitrary | High | Version all assumptions and show them in the demo |
| Too many generated files confuse users | Medium | Use manifest and clear README |
| Rating migration unrealistic | High | Keep matrices simple and auditable |
| Profitability proxy too simplistic | Medium | Label as proxy and allow replacement with real finance data |
| FX rates mistaken for market forecast | Medium | Label as synthetic scenario rates |
| Regulatory overlays incomplete | High | Keep jurisdiction overlays separate and marked as seed |
| Recommendations too aggressive | Medium | Add action constraints and business cost scores |

## 26. Final Deliverables

The missing-input generation workstream should deliver:

- Python generator script.
- Pydantic schemas for generated input files.
- `generated_inputs/` folder with all CSVs.
- Manifest JSON.
- Validation report.
- README explaining each generated input.
- Example command to regenerate the package.

## 27. Definition of Done

This workstream is complete when:

- Missing inputs can be regenerated deterministically.
- The generated package validates end-to-end.
- The PoC can run without manual data edits.
- Scenario, rating, DLGD, FX and regulatory assumptions are all explicit.
- Steering recommendations can use profitability and constraints.
- The limitations are visible and not hidden.

