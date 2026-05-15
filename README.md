# RWA Steering

Python `src/` layout repository for Basel III RWA calculation, projection and steering
services:

- `src/rwa_calculator` - RWA calculator backend, exposed as `rwa-calculator`.
- `src/rwa_forecast_service` - VAR/recurrent forecast and Monte Carlo trajectory service.
- `src/rwa_projection_service` - projection service using `rwa_calculator` as `f(x, t)`.
- `src/rwa_steering` - regime-aware steering service with generated scenario inputs,
  attribution and recommendations.
- `src/rwa_rats_service` - Risk-Aware Trading Swarm optimization service for forecasted RWA.
- `src/rwa_dashboard` - Streamlit dashboard over the calculator, projection and steering services.

The repository uses a modern `src/` layout, `uv` for environment and lockfile management,
`pytest` for tests, `ruff` for linting/formatting, and coverage/security tooling suitable for
enterprise CI.

## Architecture

```text
preprod CoreInfo / CountryInfo / NCCR mapping
  -> rwa_calculator
  -> rwa_projection_service for f(x, t) monthly projections
  -> rwa_steering generated_inputs package
  -> scenario projection, attribution, recommendations
```

`rwa_steering` now consumes the validated package in
`src/rwa_steering/generated_inputs/` instead of relying only on hardcoded scenario knobs. The
runtime loader verifies the manifest, file hashes, scenario references, projection dates and
rating-migration probability totals before the FastAPI app starts.

## Quickstart

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run bandit -q -c pyproject.toml -r src
uv run pip-audit
uv build
```

## CLI

```powershell
uv run rwa-calculator calculate --out build/calculator/results.json --trace
uv run rwa-calculator serve-fastapi --host 127.0.0.1 --port 8000
uv run rwa-forecast --host 127.0.0.1 --port 8040
uv run rwa-generate-missing-inputs
uv run rwa-dashboard --host 127.0.0.1 --port 8501
uv run rwa-projection --host 127.0.0.1 --port 8010
uv run rwa-rats --host 127.0.0.1 --port 8030
uv run rwa-steering --host 127.0.0.1 --port 8020
```

Dashboard:

```text
http://127.0.0.1:8501
```

The Streamlit dashboard exposes the `Run-off f(x,t)` methodology and a separate regulatory capital
stack panel:

- current row-level credit RWA plus aggregate applicable RWA
- `Run-off f(x,t)` for the existing book using monthly maturity roll-forward
- aggregate output floor, CVA, operational risk and leverage-ratio views
- generated input package quality diagnostics

Projection endpoint:

```text
POST http://127.0.0.1:8010/v1/projections/calculate
```

Forecast endpoint:

```text
POST http://127.0.0.1:8040/v1/forecasts/run
```

Steering endpoint:

```text
POST http://127.0.0.1:8020/v1/steering/run
```

RATS endpoint:

```text
POST http://127.0.0.1:8030/v1/rats/optimize
```

Capital module endpoints:

```text
POST http://127.0.0.1:8000/v1/output-floor/calculate
POST http://127.0.0.1:8000/v1/operational-risk/calculate
POST http://127.0.0.1:8000/v1/cva/calculate
POST http://127.0.0.1:8000/v1/leverage-ratio/calculate
POST http://127.0.0.1:8000/v1/capital/portfolio
```

The unversioned compatibility `POST /steering/run` route is still available during the PoC.
Calculator and projection services follow the same pattern: `/v1/rwa/calculate` and
`/v1/projections/calculate` are the versioned contracts, while the older unversioned routes
remain available during transition.

The projection request accepts `run_date`, `projected_months` up to 24 and `core_info`
rows. It returns `t0 = run_date` plus month-end projection points. Maturity equal to zero is
calculated; negative projected maturity returns zero projection values; missing maturity returns
null projection values.

The forecast service simulates multi-period ALM trajectories before optimization. It supports a
classic VAR-style autoregressive factor model and a recurrent factor model, then generates Monte
Carlo paths of market factors, portfolio baskets, RWA, profit, capital-ratio breaches, turnover
and drawdown. Each full path is scored with a loss function balancing profit against RWA floor
penalties, turnover, drawdown and terminal RWA usage.

The steering service applies BASE, DOWNSIDE, STRESS and RECOVERY assumptions from the generated
input package to the current input records, calls the existing RWA calculator, and returns
scenario summaries, projection rows, portfolio attribution and ranked decision-support
recommendations. Structured domain errors are returned as:

The RATS service implements a deterministic Risk-Aware Trading Swarm inspired by RATPO/RATS. It
forecasts calculator inputs to a scenario/date, builds Unique Eligible Instruments from allowed
steering actions, and searches for an eligible optimization strategy that improves projected RWA
after business cost, concentration and risk-limit penalties.

```json
{
  "api_version": "v1",
  "error": {
    "code": "UNKNOWN_JURISDICTION_OVERLAY",
    "message": "Unknown jurisdiction overlay 'NO_SUCH_OVERLAY'.",
    "field_path": "jurisdiction",
    "severity": "ERROR",
    "remediation": "Use one of the overlays listed in regulatory_overlay_selection.csv.",
    "context": {
      "available": ["CH_FINMA_BASEL_III_FINAL", "EU_CRR3_EBA", "UK_PRA_BASEL_3_1"]
    }
  }
}
```

## Generated Inputs

The steering input package contains synthetic, non-production CSVs plus a manifest and validation
report:

- scenario definitions and forecast calendar
- segment growth, rating migration, DLGD and FX assumptions
- macro regime indicators and regulatory overlay selection
- profitability inputs, steering action constraints, strategy limits and data quality flags
- prepared capital stack inputs: capital positions, operational BI/loss history, CVA netting
  sets/hedges and leverage exposure components

Regenerate deterministically with:

```powershell
uv run rwa-generate-missing-inputs
```

CI regenerates the package and fails if committed generated files drift.

## Quality Gates

Current automated gates:

- `ruff format --check .`
- `ruff check .`
- `pytest` with branch coverage and golden calculator regression cases
- `mypy`
- `bandit`
- `pip-audit`
- `uv build`
- generated-input reproducibility check

## Production Readiness

Before production use, the methodology, reference data, jurisdiction overlays, rating migrations,
profitability inputs and steering recommendations must be reconciled with approved bank policy,
binding legal text and model-risk governance.

Archived project READMEs are preserved in `docs_bob_README.md` and `docs_codex_README.md`.
