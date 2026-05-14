from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SteeringErrorDetail:
    """Structured error detail used by services and HTTP exception handlers."""

    code: str
    message: str
    field_path: str | None = None
    severity: str = "ERROR"
    remediation: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class SteeringDomainError(Exception):
    """Domain-level steering failure that can be converted to a stable API error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field_path: str | None = None,
        severity: str = "ERROR",
        remediation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.detail = SteeringErrorDetail(
            code=code,
            message=message,
            field_path=field_path,
            severity=severity,
            remediation=remediation,
            context=context or {},
        )

    @classmethod
    def from_calculator_errors(
        cls,
        errors: list[dict[str, Any]],
        *,
        scenario_id: str | None = None,
        projection_date: str | None = None,
    ) -> SteeringDomainError:
        """Build a structured error from calculator batch row failures."""
        return cls(
            code="CALCULATOR_ROW_FAILURE",
            message="RWA calculator returned row-level failures during steering run.",
            remediation="Inspect error context, fix source rows, then rerun steering.",
            context={
                "scenario_id": scenario_id,
                "projection_date": projection_date,
                "errors": errors,
            },
        )
