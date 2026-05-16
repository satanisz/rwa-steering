from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RequestMemory:
    """Request-scoped memory used only inside one agent graph execution."""

    enabled: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def scope(self) -> str:
        """Return the externally visible memory scope label."""
        return "request" if self.enabled else "disabled"

    def remember(self, note: str) -> None:
        """Store a transient note when request memory is enabled."""
        if self.enabled:
            self.notes.append(note)
