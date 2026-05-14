# Executive Plan 1: Regime-Aware RWA Steering PoC

## 1. Executive Summary

The goal of this Proof of Concept is to evolve the existing RWA Calculator into a first version of an RWA Steering tool. The PoC will not replace the regulatory calculator. Instead, it will sit above it as a forecasting, scenario, attribution and recommendation layer.

The current assets are:

- Existing RWA Calculator aligned to regulatory logic.
- Validated input and output schemas.
- Synthetic pre-production dataset of 1,000 assets.
- `nccr_mapping.csv` for internal rating / PD mapping.
- Initial regulatory reference-data seed with BCBS base plus EU, UK and Swiss jurisdiction overlays.
- Technical planning already established for Pydantic validation, modular architecture and auditability.

The proposed PoC is inspired by the Nature Scientific Reports article "A machine learning approach to risk based asset allocation in portfolio optimization", which combines regime detection, dynamic risk budgeting, volatility/risk forecasting and interpretable attribution. The PoC adapts this concept from investment portfolio allocation to banking RWA management:

```text
Article concept:
market assets -> regime/risk forecast -> dynamic risk budget -> portfolio weights

RWA Steering PoC:
bank assets -> scenario/regime forecast -> dynamic RWA budget -> steering recommendations
```

The PoC should demonstrate that a bank can forecast RWA under multiple future regimes, explain the drivers of RWA movement and recommend management actions before regulatory capital pressure materializes.

## 2. Strategic Objective

The PoC must answer four business questions:

1. What will RWA look like under base, downside and stress scenarios?
2. Which exposures, counterparties, currencies, entity classes and regulatory treatments are driving the RWA change?
3. Which steering actions reduce future RWA most efficiently?
4. Can the tool explain its recommendations in a way that is credible for a bank risk, finance and regulatory audience?

The PoC is successful if it clearly shows a transition from a static calculator to an active steering engine.

## 3. Target Use Case

The target user is a bank risk, finance or capital management team. The user wants to load the current portfolio, choose a regulatory jurisdiction and scenario horizon, and receive:

- Current RWA.
- Forecast RWA by scenario and projection date.
- Delta versus current and delta versus base scenario.
- Attribution of RWA movement by driver.
- List of top RWA-consuming exposures.
- List of top RWA-increasing exposures.
- Recommended steering actions.
- Estimated RWA saving and business impact per action.

Example steering output:

```text
Scenario: STRESS
Projection date: 2027-12-31
Projected RWA increase: +18.4%
Main drivers:
  Rating migration: +9.1%
  DLGD shock: +4.7%
  FX movement: +2.3%
  Portfolio volume: +1.8%
  Regulatory floor: +0.5%

Recommended actions:
  1. Reprice low-return high-RWA corporate exposures.
  2. Reduce or syndicate top 25 RWA-heavy obligors.
  3. Prioritize collateral enhancement for selected project finance exposures.
  4. Shift new origination away from high AVC / high LGD segments.
```

## 4. Functional Scope

### 4.1 In Scope

The PoC must include:

- Scenario definition engine.
- Regime-aware forecast layer.
- Input projection engine for existing RWA input records.
- Integration with current RWA Calculator.
- RWA projection output table.
- Driver attribution.
- Steering recommendation rules.
- Basic optimization / ranking of actions.
- Pydantic-validated forecast inputs and outputs.
- Dashboard-ready CSV or JSON outputs.

### 4.2 Out of Scope for PoC

The PoC should not attempt to implement:

- Full production ML training pipeline.
- Full LSTM architecture from the article.
- Real-time market data ingestion.
- Full ALM, FTP or profitability stack.
- Full supervisory capital reporting.
- Binding legal interpretation of jurisdiction-specific rules.
- Production-grade model risk management.

These should be marked as future delivery items.

## 5. PoC Architecture

Recommended package structure:

```text
rwa_steering/
  schemas/
    forecast_inputs.py
    forecast_outputs.py
    scenarios.py
    steering.py
  forecasting/
    scenario_library.py
    regime_engine.py
    exposure_projection.py
    rating_migration.py
    dlgd_projection.py
    maturity_rollforward.py
    fx_projection.py
    regulatory_calendar.py
  calculator_adapter/
    rwa_calculator_client.py
    input_mapper.py
    output_mapper.py
  attribution/
    driver_attribution.py
    waterfall.py
    sensitivity.py
  steering/
    action_library.py
    action_simulator.py
    recommendation_ranker.py
  reporting/
    scenario_report.py
    portfolio_summary.py
    exposure_drilldown.py
  cli/
    run_forecast.py
    run_scenario.py
```

The existing RWA Calculator should remain a separate deterministic engine. The steering layer should call it repeatedly with projected input datasets.

## 6. Data Flow

```text
Current portfolio input
  preprod_core_info_1000.csv
        |
        v
Pydantic validation
        |
        v
Scenario and regime selection
        |
        v
Projected input generation
        |
        v
Existing RWA Calculator
        |
        v
Projected RWA outputs
        |
        v
Attribution and steering engine
        |
        v
Dashboard-ready outputs
```

The most important design decision is that the PoC forecasts calculator inputs, not final RWA directly. This keeps the regulatory logic auditable.

## 7. Scenario Design

The first PoC should support four scenarios.

### 7.1 BASE

Purpose: expected portfolio evolution.

Assumptions:

- Moderate exposure growth.
- Mostly stable ratings.
- Small maturity roll-down.
- Stable DLGD.
- No severe FX shock.
- Jurisdiction calendar follows configured overlay.

### 7.2 DOWNSIDE

Purpose: mild deterioration.

Assumptions:

- Lower new origination.
- Some downgrades.
- Moderate DLGD uplift.
- Higher credit spreads.
- Mild FX pressure.
- Higher RWA density in selected segments.

### 7.3 STRESS

Purpose: severe but plausible capital pressure.

Assumptions:

- Material downgrades.
- DLGD shock.
- Sector concentration pressure.
- Higher defaults or near-default flags.
- FX shock for non-reporting-currency exposures.
- Output floor or jurisdictional transition effects visible.

### 7.4 RECOVERY

Purpose: improved environment after stress.

Assumptions:

- Selected upgrades.
- Moderate exposure growth.
- DLGD normalization.
- Better portfolio mix.
- Lower RWA density.

## 8. Forecast Horizons

Recommended PoC horizons:

- Current date / as-of date.
- 2026-12-31.
- 2027-12-31.
- 2028-12-31.

If the PoC is focused on UK PRA Basel 3.1, include 2027 and 2030 milestones. If focused on EU CRR3, include 2025-2030 output floor phase-in. If focused on Switzerland, include 2025 and 2028 milestones.

## 9. Forecast Transformations

### 9.1 Exposure Amount Projection

Forecast `exposure_amount` using segment-level assumptions:

```text
projected_exposure_amount =
    current_exposure_amount
  * (1 + segment_growth_rate)
  * amortization_factor
  * prepayment_factor
```

Segment dimensions:

- `entity_class`.
- `sub_class`.
- `exposure_ccy`.
- `bond_or_loan_flag`.
- country.
- rating band.

### 9.2 Maturity Roll-Forward

Forecast residual maturity:

```text
projected_residual_maturity =
    max(current_residual_maturity - years_elapsed, 0)
```

If residual maturity reaches zero, the exposure should either:

- mature and leave the portfolio,
- renew under scenario-specific renewal rules,
- convert to new origination if business assumptions allow it.

### 9.3 Rating Migration

Use the NCCR grade scale from `nccr_mapping.csv`.

Base case:

- Majority of ratings remain stable.
- Small percentage upgrade or downgrade by one notch.

Downside:

- Larger percentage downgrade by one notch.
- Selected high-risk segments downgrade by two notches.

Stress:

- Broad downgrade pressure.
- Concentrated downgrade in corporates, banks or FI depending on scenario.

The rating migration should produce:

- projected FCY internal rating.
- projected LCY internal rating.
- projected PD classification.
- projected PD using NCCR mapping.

### 9.4 DLGD Projection

DLGD should be scenario-adjusted:

```text
projected_dlgd = min(current_dlgd * scenario_lgd_multiplier + segment_addon, cap)
```

Possible segment add-ons:

- unsecured corporate.
- specialised lending.
- real estate cashflow dependent.
- high AVC bank/FI exposures.
- lower-quality countries.

### 9.5 FX Projection

If reporting currency differs from exposure currency, apply FX scenario:

```text
projected_reporting_amount =
    projected_exposure_amount
  * fx_rate_scenario[exposure_ccy, reporting_ccy, projection_date]
```

The PoC can start with static scenario shocks:

- EUR/PLN +5%.
- USD/reporting currency +8%.
- CHF/reporting currency +6%.
- GBP/reporting currency +4%.

### 9.6 Regulatory Calendar Projection

The forecast engine must load regulatory overlay data:

- `EU_CRR3_EBA`.
- `UK_PRA_BASEL_3_1`.
- `CH_FINMA_BASEL_III_FINAL`.

The projection must apply:

- output floor phase-in.
- effective dates.
- jurisdiction flags.
- national discretion placeholders.

## 10. RWA Calculator Integration

The PoC should expose a simple adapter:

```python
class RwaCalculatorAdapter:
    def calculate(self, input_records, jurisdiction, as_of_date):
        ...
```

The adapter must:

- accept Pydantic-validated projected records.
- convert them to the format required by the current calculator.
- call the current calculator.
- validate calculator outputs.
- return normalized RWA output records.

If the existing calculator is file-based, the adapter can use CSV in/out. If it is Python-callable, use direct function calls.

## 11. Attribution Methodology

The attribution layer should calculate why projected RWA changed.

Recommended first version: sequential revaluation.

```text
Step 0: current input -> current RWA
Step 1: apply volume only -> volume impact
Step 2: apply maturity only -> maturity impact
Step 3: apply rating only -> rating impact
Step 4: apply DLGD only -> DLGD impact
Step 5: apply FX only -> FX impact
Step 6: apply regulatory calendar only -> regulatory impact
Step 7: all projected inputs -> total projected RWA
```

This produces a waterfall:

```text
RWA_current
+ volume_delta
+ maturity_delta
+ rating_delta
+ dlgd_delta
+ fx_delta
+ regulatory_delta
= RWA_projected
```

The sum of driver deltas should reconcile to total RWA delta or disclose residual interaction.

## 12. Steering Recommendation Engine

The PoC recommendation engine should be rules-based, not black-box ML.

### 12.1 Action Library

Possible actions:

- `REDUCE_EXPOSURE`.
- `DO_NOT_RENEW`.
- `SYNDICATE_OR_SELL_DOWN`.
- `COLLATERAL_ENHANCEMENT`.
- `GUARANTEE_ENHANCEMENT`.
- `REPRICE`.
- `LIMIT_NEW_ORIGINATION`.
- `SHIFT_ORIGINATION_TO_LOWER_RWA_SEGMENT`.
- `REVIEW_RATING_OR_DATA_QUALITY`.

### 12.2 Action Simulation

Each action should simulate a transformation:

```text
REDUCE_EXPOSURE:
  exposure_amount *= 0.80

COLLATERAL_ENHANCEMENT:
  counterparty_dlgd *= 0.90

DO_NOT_RENEW:
  if residual_maturity < threshold:
      future_exposure_amount = 0

REPRICE:
  expected_yield += pricing_addon
```

Then the transformed input is sent back through the RWA Calculator.

### 12.3 Recommendation Ranking

Rank actions by:

```text
score =
    rwa_saving_weight * normalized_rwa_saving
  + capital_ratio_weight * capital_ratio_improvement
  - business_cost_weight * estimated_business_cost
  - implementation_complexity_weight * complexity_score
```

The PoC should not claim the recommendation is final. It should label it as a decision-support proposal.

## 13. Output Requirements

The PoC should produce at least these files:

1. `rwa_forecast_projection.csv`
2. `rwa_forecast_attribution.csv`
3. `rwa_steering_recommendations.csv`
4. `rwa_forecast_summary.json`
5. Optional dashboard-ready Excel workbook or web dashboard.

### 13.1 Projection Output Columns

```text
scenario_id
scenario_name
jurisdiction
as_of_date
projection_date
id
counterparty_gid
entity_class
sub_class
exposure_ccy
current_exposure_amount
projected_exposure_amount
current_rating
projected_rating
current_dlgd
projected_dlgd
current_rwa
projected_rwa
rwa_delta
rwa_delta_pct
```

### 13.2 Attribution Output Columns

```text
scenario_id
projection_date
id
rwa_current
volume_delta
maturity_delta
rating_delta
dlgd_delta
fx_delta
regulatory_delta
interaction_or_residual_delta
rwa_projected
```

### 13.3 Recommendation Output Columns

```text
scenario_id
projection_date
id
counterparty_gid
entity_class
sub_class
recommended_action
action_description
rwa_before_action
rwa_after_action
estimated_rwa_saving
estimated_business_cost
implementation_complexity
recommendation_score
reason_code
```

## 14. Validation and Controls

The PoC must validate:

- Every input record before projection.
- Every projected input record before calculation.
- Every calculator output before attribution.
- Every recommendation output before export.

Controls:

- No negative exposure amounts.
- Residual maturity cannot exceed original maturity.
- Rating migration cannot move outside rating scale.
- DLGD must remain within configured bounds.
- Scenario assumptions must be versioned.
- Regulatory overlay must be explicit.
- Projection date must be equal to or after as-of date.

## 15. Interpretability

The PoC must explain:

- Which scenario assumptions were applied.
- Which fields changed.
- Which RWA drivers matter most.
- Which exposures are top contributors.
- Why each steering action was recommended.

For hackathon presentation, the most persuasive artifact is a waterfall:

```text
Current RWA -> volume -> rating -> DLGD -> FX -> regulation -> forecast RWA
```

## 16. Model Risk Positioning

The PoC should avoid claiming that ML is already production-ready. The correct positioning:

- The RWA Calculator is deterministic and regulatory.
- The Forecast Engine is scenario-based and explainable.
- ML-inspired regime detection can be added later.
- The PoC is decision support, not automated capital management.
- Outputs require risk/finance review before action.

This is important in a bank environment.

## 17. Hackathon MVP Timeline

### Day 1

- Finalize schemas.
- Build scenario assumptions.
- Build projection engine.
- Integrate with 1,000 asset dataset.

### Day 2

- Connect projected input to RWA Calculator.
- Generate base/downside/stress outputs.
- Build attribution.

### Day 3

- Build steering action simulator.
- Generate recommendations.
- Produce summary dashboard outputs.
- Prepare narrative and demo flow.

## 18. Acceptance Criteria

The PoC is accepted when:

- It runs on the 1,000 synthetic asset dataset.
- It produces at least three forecast scenarios.
- It produces at least three projection dates.
- It calls the existing RWA Calculator rather than bypassing it.
- It shows RWA delta versus current and versus base.
- It produces driver attribution.
- It generates ranked steering recommendations.
- It validates input and output using Pydantic.
- It can explain every material number.

## 19. Demo Story

Recommended hackathon demo narrative:

1. "We start with a regulatory RWA calculator."
2. "The problem is that a calculator is reactive."
3. "We add a regime-aware forecast layer."
4. "We project the bank book under base, downside and stress."
5. "We run each future portfolio through the same regulatory calculator."
6. "We explain the RWA delta by driver."
7. "We recommend steering actions and estimate RWA savings."
8. "This turns RWA from reporting into forward-looking capital management."

## 20. Key Risks

| Risk | Impact | Mitigation |
|---|---:|---|
| Forecast assumptions are arbitrary | High | Version assumptions and show them explicitly |
| Calculator integration is unstable | High | Build adapter and file-based fallback |
| Recommendations look too automated | Medium | Label as decision support |
| Missing production data | High | Use synthetic input-generation plan |
| Regulatory overlay incomplete | High | Mark overlay status and require legal reconciliation |
| Attribution residuals are confusing | Medium | Show interaction/residual separately |

## 21. Final Deliverables

The PoC delivery package should include:

- Python forecasting module.
- Scenario assumption files.
- Projected input CSVs.
- Projected RWA outputs.
- Attribution CSV.
- Recommendation CSV.
- Summary JSON.
- Demo notebook or CLI script.
- Short architecture diagram.
- Known limitations and next-step plan.

