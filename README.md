# RWA Steering

Python monorepo for two Basel III RWA calculator implementations:

- `src/rwa_bob` - Bob implementation, exposed as `rwa-bob`.
- `src/rwa_codex` - Codex implementation, exposed as `rwa-codex`.

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
uv run rwa-bob --output build/bob/results.json --verbose
uv run rwa-codex calculate --out build/codex/results.json --trace
uv run rwa-codex serve-fastapi --host 127.0.0.1 --port 8000
```

Legacy project READMEs are preserved in `docs_bob_README.md` and `docs_codex_README.md`.
