from __future__ import annotations

import json
from typing import Any

from .schemas import AgentResult, MetricFact


def build_commentary_prompt(
    agent_results: list[AgentResult],
    metric_facts: list[MetricFact],
    limitations: list[str],
) -> str:
    """Build a compact JSON-oriented prompt for local LLM commentary."""
    agent_summaries = [
        {
            "agent_name": result.agent_name,
            "status": result.status,
            "summary": result.summary,
            "findings": [
                {
                    "title": finding.title,
                    "severity": finding.severity,
                    "summary": finding.summary,
                    "metric_name": finding.metric_name,
                    "metric_value": str(finding.metric_value)
                    if finding.metric_value is not None
                    else None,
                }
                for finding in result.findings[:4]
            ],
        }
        for result in agent_results
    ]
    facts = [
        {
            "name": fact.name,
            "value": str(fact.value) if fact.value is not None else None,
            "unit": fact.unit,
            "source": fact.source,
            "scenario_id": fact.scenario_id,
            "model": fact.model,
        }
        for fact in metric_facts[:24]
    ]
    payload: dict[str, Any] = {
        "task": (
            "Generate fresh board-level commentary for the RWA dashboard. Use only these facts. "
            "Return a single JSON object and no markdown."
        ),
        "allowed_source_agent_names": [result.agent_name for result in agent_results],
        "required_schema": {
            "executive_summary": "string",
            "key_messages": ["string"],
            "risk_watchlist": ["string"],
            "recommended_actions": ["string"],
            "limitations": ["string"],
            "source_agent_names": ["one of the provided agent names"],
        },
        "rules": [
            "Do not calculate RWA.",
            "Do not invent metrics or data sources.",
            "Use short board-ready sentences.",
            "Mention evidence only when it appears in the provided inputs.",
            "Return one JSON object only. Do not use markdown fences.",
        ],
        "metric_facts": facts,
        "agent_results": agent_summaries,
        "limitations": limitations,
    }
    return json.dumps(payload, indent=2)
