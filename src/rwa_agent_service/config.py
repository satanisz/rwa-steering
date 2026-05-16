from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentServiceSettings(BaseSettings):
    """Runtime settings for local and deployed agent service modes."""

    model_config = SettingsConfigDict(env_prefix="RWA_AGENT_", extra="ignore")

    llm_provider: Literal["deterministic", "ollama"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:e4b"
    ollama_fallback_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = Field(default=45.0, ge=1.0)
    allow_deterministic_fallback: bool = False

    rag_backend: Literal["in_memory", "weaviate"] = "in_memory"
    weaviate_url: str | None = None
    langfuse_enabled: bool = False
    langfuse_prompt_label: str | None = "production"
    langfuse_prompt_cache_ttl_seconds: int = Field(default=300, ge=0)
    langfuse_prompt_fetch_timeout_seconds: int = Field(default=5, ge=1)
    langsmith_enabled: bool = False
    memory_scope: Literal["disabled", "request"] = "disabled"


def load_settings() -> AgentServiceSettings:
    """Load agent service settings from environment variables."""
    return AgentServiceSettings()
