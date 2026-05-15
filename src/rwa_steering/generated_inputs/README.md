# RWA Steering Generated Missing Inputs

This directory contains generated, non-production inputs for the RWA steering service.
The package is deterministic from control value `20260515` and release `RWA-ENT-2026.2.0`.

These files fill the steering gaps that do not belong inside the RWA calculator:
scenario definitions, forecast calendar, rating migration, DLGD shocks, FX rates,
macro regimes, regulatory overlay selection, profitability inputs, action
constraints, strategy limits, data quality flags and prepared capital-stack
inputs for CVA, operational risk, leverage ratio and capital numerators.

Regenerate with:

```bash
uv run rwa-generate-missing-inputs
```

The data is suitable for controlled lower-environment testing only. It must not be
presented as production customer data, calibrated market forecasts or approved
regulatory reference data.
