# RWA Steering Generated Missing Inputs

This directory contains synthetic, non-production inputs for the RWA Steering PoC.
The package is deterministic from seed `20260515` and version `2026Q2_HACKATHON_SEED_V1`.

These files fill the steering gaps that do not belong inside the RWA calculator:
scenario definitions, forecast calendar, rating migration, DLGD shocks, FX rates,
macro regimes, regulatory overlay selection, profitability proxies, action
constraints, strategy limits and data quality flags.

Regenerate with:

```bash
uv run python -m rwa_steering.missing_inputs
```

The data is suitable for hackathon demos and automated tests only. It must not be
presented as production customer data, calibrated market forecasts or approved
regulatory reference data.
