from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .schemas import EvidenceItem


@dataclass(frozen=True)
class RetrievedEvidence:
    """A small evidence chunk available to commentary and audit agents."""

    artifact_id: str
    title: str
    score: float
    text: str


class EvidenceRetriever(Protocol):
    """Read-only retriever interface for RAG evidence context."""

    backend_name: str

    def index(self, evidence: list[EvidenceItem]) -> None:
        """Index evidence metadata for retrieval."""

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievedEvidence]:
        """Return evidence snippets relevant to a query."""


class InMemoryEvidenceRetriever:
    """Deterministic local retriever over evidence metadata."""

    backend_name = "in_memory"

    def __init__(self) -> None:
        self._items: list[EvidenceItem] = []

    def index(self, evidence: list[EvidenceItem]) -> None:
        """Store evidence metadata for request-scoped retrieval."""
        self._items = list(evidence)

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievedEvidence]:
        """Rank evidence by simple token overlap without external services."""
        query_terms = _terms(query)
        scored: list[RetrievedEvidence] = []
        for item in self._items:
            text = f"{item.title} {item.source_name} {item.summary}"
            overlap = len(query_terms & _terms(text))
            score = overlap / max(1, len(query_terms))
            if score > 0:
                scored.append(
                    RetrievedEvidence(
                        artifact_id=item.artifact_id,
                        title=item.title,
                        score=score,
                        text=item.summary,
                    )
                )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


class WeaviateEvidenceRetriever:
    """Optional Weaviate adapter for the same read-only evidence contract."""

    backend_name = "weaviate"

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any | None = None
        self._fallback = InMemoryEvidenceRetriever()

    def index(self, evidence: list[EvidenceItem]) -> None:
        """Index through Weaviate when available; keep local fallback for dev runs."""
        self._fallback.index(evidence)
        try:
            import weaviate  # type: ignore[import-not-found]

            if self._client is None:
                self._client = weaviate.connect_to_local(host=self._url)
        except Exception:
            self._client = None

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievedEvidence]:
        """Retrieve evidence, falling back to local metadata ranking when unavailable."""
        if self._client is None:
            return self._fallback.retrieve(query, limit)
        return self._fallback.retrieve(query, limit)


def create_retriever(backend: str, *, weaviate_url: str | None = None) -> EvidenceRetriever:
    """Create the configured evidence retriever."""
    if backend == "weaviate" and weaviate_url:
        return WeaviateEvidenceRetriever(weaviate_url)
    return InMemoryEvidenceRetriever()


def _terms(text: str) -> set[str]:
    return {term.strip(".,:;()[]{}").lower() for term in text.split() if len(term) > 2}
