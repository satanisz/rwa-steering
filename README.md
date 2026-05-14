# RWA Steering

Python monorepo for Basel III RWA calculation and projection services:

- `src/rwa_calculator` - RWA calculator backend, exposed as `rwa-calculator`.
- `src/rwa_projection_service` - projection service using `rwa_calculator` as `f(x, t)`.

The repository uses a modern `src/` layout, `uv` for environment and lockfile management,
`pytest` for tests, `ruff` for linting/formatting, and coverage/security tooling suitable for
enterprise CI.

## Quickstart

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pip-audit
```

## CLI

```powershell
uv run rwa-calculator calculate --out build/calculator/results.json --trace
uv run rwa-calculator serve-fastapi --host 127.0.0.1 --port 8000
uv run rwa-projection --host 127.0.0.1 --port 8010
```

Projection endpoint:

```text
POST http://127.0.0.1:8010/projections/calculate
```

The projection request accepts `run_date`, `projected_months` up to 24 and `core_info`
rows. It returns `t0 = run_date` plus month-end projection points. Maturity equal to zero is
calculated; negative projected maturity returns zero projection values; missing maturity returns
null projection values.

Legacy project READMEs are preserved in `docs_bob_README.md` and `docs_codex_README.md`.
