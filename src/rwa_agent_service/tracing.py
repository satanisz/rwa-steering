from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from .schemas import AgentTraceSpan


@dataclass
class TraceRecorder:
    """Local trace recorder with an interface compatible with external tracing."""

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    spans: list[AgentTraceSpan] = field(default_factory=list)

    def span(self, name: str, status: str = "ok", **attributes: object) -> None:
        """Record a lightweight span for the response and tests."""
        serializable = {
            key: value
            for key, value in attributes.items()
            if isinstance(value, (str, int, bool)) or value is None
        }
        self.spans.append(AgentTraceSpan(name=name, status=status, attributes=serializable))


class LangfuseTraceRecorder(TraceRecorder):
    """Placeholder-compatible recorder for environments with Langfuse configured."""

    def span(self, name: str, status: str = "ok", **attributes: object) -> None:
        """Record locally; external Langfuse wiring can be added without API changes."""
        super().span(name, status, **attributes)
