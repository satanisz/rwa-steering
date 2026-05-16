from __future__ import annotations

from decimal import Decimal

from .graph import AgentGraphState
from .schemas import AgentFinding, AgentResult
from .tools import (
    evidence_inventory,
    evidence_ref,
    largest_capital_components,
    lineage_records,
    metric_facts,
    top_model_movements,
)


def prepare_context_node(state: AgentGraphState) -> AgentGraphState:
    """Extract facts and evidence from calculated runtime context."""
    state.metric_facts = metric_facts(state.context)
    state.evidence_inventory = evidence_inventory(state.context)
    state.lineage = lineage_records(state.context)
    state.retriever.index(state.evidence_inventory)
    if state.request.include_rag_context:
        retrieved = state.retriever.retrieve("RWA model capital evidence validation", limit=5)
        state.memory.remember(f"retrieved_evidence={len(retrieved)}")
    state.trace.span(
        "prepare_context",
        facts=len(state.metric_facts),
        evidence=len(state.evidence_inventory),
    )
    return state


def rwa_movement_node(state: AgentGraphState) -> AgentGraphState:
    """Summarize RWA movement across calculated projection models."""
    summary_frame = state.context.runs.model_summary
    evidence = [
        evidence_ref(
            "model_run_set.model_summary",
            "terminal_projection_rows",
            metric_name="rwa_delta",
            row_count=int(summary_frame.shape[0]),
        )
    ]
    if summary_frame.empty:
        result = AgentResult(
            agent_name="RWA Movement Agent",
            status="SKIPPED",
            summary="No calculated model summary rows were available.",
            evidence=evidence,
            confidence=Decimal("0.0"),
        )
        state.agent_results.append(result)
        state.trace.span("rwa_movement_agent", status="skipped")
        return state

    total_abs_delta = Decimal(str(summary_frame["rwa_delta"].abs().sum()))
    movements = top_model_movements(summary_frame, limit=3)
    findings = [
        AgentFinding(
            title=f"{row['model']} movement",
            severity=_movement_severity(Decimal(str(row["rwa_delta"]))),
            summary=(
                f"{row['model']} under {row['scenario_id']} projects "
                f"{_money(row['projected_rwa'])} with movement {_money(row['rwa_delta'])}."
            ),
            metric_name="rwa_delta",
            metric_value=Decimal(str(row["rwa_delta"])),
            evidence=evidence,
        )
        for row in movements
    ]
    result = AgentResult(
        agent_name="RWA Movement Agent",
        status="COMPLETED",
        summary=(
            f"{summary_frame['model'].nunique()} calculated models are present; "
            f"aggregate absolute terminal movement is {_money(total_abs_delta)}."
        ),
        findings=findings,
        evidence=evidence,
        confidence=Decimal("0.95"),
    )
    state.agent_results.append(result)
    state.trace.span("rwa_movement_agent", status="completed", findings=len(findings))
    return state


def capital_stack_node(state: AgentGraphState) -> AgentGraphState:
    """Summarize calculated Basel capital stack and ratios."""
    capital = state.context.capital
    output_floor = capital.output_floor
    leverage = capital.leverage_ratio
    stack = capital.capital_stack
    evidence = [
        evidence_ref(
            "regulatory_capital_snapshot.output_floor",
            "portfolio_output_floor",
            metric_name="applicable_rwa",
        ),
        evidence_ref(
            "regulatory_capital_snapshot.capital_stack",
            "capital_components",
            row_count=int(stack.shape[0]),
        ),
    ]
    findings = [
        AgentFinding(
            title="Applicable total RWA",
            severity="INFO",
            summary=(
                f"Applicable total RWA is {_money(output_floor['applicable_rwa'])}; "
                f"pre-floor RWA is {_money(output_floor['pre_floor_rwa'])}."
            ),
            metric_name="applicable_rwa",
            metric_value=Decimal(str(output_floor["applicable_rwa"])),
            evidence=evidence,
        ),
        AgentFinding(
            title="Capital and leverage ratios",
            severity=_ratio_severity(Decimal(str(output_floor["cet1_ratio"]))),
            summary=(
                f"CET1 ratio is {_ratio(output_floor['cet1_ratio'])}; total capital ratio "
                f"is {_ratio(output_floor['total_capital_ratio'])}; leverage ratio is "
                f"{_ratio(leverage['leverage_ratio'])}."
            ),
            metric_name="cet1_ratio",
            metric_value=Decimal(str(output_floor["cet1_ratio"])),
            evidence=evidence,
        ),
    ]
    findings.extend(
        [
            AgentFinding(
                title=f"Capital component: {row['component']}",
                severity="INFO",
                summary=f"{row['component']} contributes {_money(row['rwa'])} to capital stack.",
                metric_name="component_rwa",
                metric_value=Decimal(str(row["rwa"])),
                evidence=evidence,
            )
            for row in largest_capital_components(stack, limit=2)
        ]
    )
    result = AgentResult(
        agent_name="Capital Stack Agent",
        status="COMPLETED",
        summary=(
            f"Capital stack contains {len(stack)} calculated components; CET1 ratio "
            f"is {_ratio(output_floor['cet1_ratio'])}."
        ),
        findings=findings,
        evidence=evidence,
        limitations=list(capital.methodology_notes),
        confidence=Decimal("0.96"),
    )
    state.agent_results.append(result)
    state.limitations.extend(capital.methodology_notes)
    state.trace.span("capital_stack_agent", status="completed", findings=len(findings))
    return state


def data_quality_node(state: AgentGraphState) -> AgentGraphState:
    """Summarize generated-input validation and quality flags."""
    overview = state.context.overview
    flags = overview.data_quality_flags
    summary = overview.data_quality_summary
    blocking = int(summary.loc[summary["is_blocking"], "count"].sum()) if not summary.empty else 0
    evidence = [
        evidence_ref(
            "input_package_overview.data_quality_flags",
            "quality_findings",
            row_count=int(flags.shape[0]),
        ),
        evidence_ref(
            "input_package.validation_report",
            "quality_gates",
            row_count=len(overview.validation_report.get("quality_gates", [])),
            source_type="validation_report",
        ),
    ]
    severity = "MATERIAL" if blocking else ("WATCH" if len(flags) else "INFO")
    findings = [
        AgentFinding(
            title="Input package validation",
            severity=severity,
            summary=(
                f"Input package status is {overview.manifest['validation_status']}; "
                f"{len(flags)} quality findings are present, including {blocking} blocking."
            ),
            metric_name="data_quality_findings",
            metric_value=len(flags),
            evidence=evidence,
        )
    ]
    result = AgentResult(
        agent_name="Data Quality Agent",
        status="COMPLETED",
        summary=(
            f"Prepared input package is {overview.manifest['validation_status']} with "
            f"{len(flags)} quality findings and {blocking} blocking findings."
        ),
        findings=findings,
        evidence=evidence,
        confidence=Decimal("0.98"),
    )
    state.agent_results.append(result)
    state.trace.span(
        "data_quality_agent",
        status="completed",
        findings=len(findings),
        blocking=blocking,
    )
    return state


def evidence_pack_node(state: AgentGraphState) -> AgentGraphState:
    """Summarize evidence inventory and lineage records."""
    hash_count = sum(1 for item in state.evidence_inventory if item.sha256)
    prepared_files = sum(
        1 for item in state.evidence_inventory if item.artifact_type == "prepared_input_file"
    )
    evidence = [
        evidence_ref(
            "agent_service.evidence_inventory",
            "evidence_items",
            row_count=len(state.evidence_inventory),
        )
    ]
    result = AgentResult(
        agent_name="Evidence Pack Agent",
        status="COMPLETED",
        summary=(
            f"Evidence pack contains {len(state.evidence_inventory)} items, "
            f"{prepared_files} prepared files and {hash_count} SHA-256 hashes."
        ),
        findings=[
            AgentFinding(
                title="Evidence inventory coverage",
                severity="INFO",
                summary=(
                    f"{len(state.lineage)} lineage edges connect prepared inputs, "
                    "calculated frames and agent commentary."
                ),
                metric_name="lineage_edges",
                metric_value=len(state.lineage),
                evidence=evidence,
            )
        ],
        evidence=evidence,
        confidence=Decimal("0.97"),
    )
    state.agent_results.append(result)
    state.trace.span(
        "evidence_pack_agent",
        status="completed",
        evidence=len(state.evidence_inventory),
    )
    return state


def board_commentary_node(state: AgentGraphState) -> AgentGraphState:
    """Generate board commentary from completed read-only agent findings."""
    commentary = state.language_model.generate_board_commentary(
        agent_results=state.agent_results,
        metric_facts=state.metric_facts,
        limitations=_unique(state.limitations),
    )
    state.board_commentary = commentary
    state.agent_results.append(
        AgentResult(
            agent_name="Board Commentary Agent",
            status="COMPLETED",
            summary=commentary.executive_summary,
            findings=[
                AgentFinding(
                    title="Board commentary generated",
                    severity="INFO",
                    summary=message,
                    evidence=[
                        evidence_ref(
                            "agent_service.agent_results",
                            "source_agent_findings",
                            row_count=len(state.agent_results),
                        )
                    ],
                )
                for message in commentary.key_messages[:3]
            ],
            evidence=[
                evidence_ref(
                    "agent_service.board_commentary",
                    "structured_commentary",
                    row_count=len(commentary.key_messages),
                )
            ],
            confidence=Decimal("0.90"),
        )
    )
    state.trace.span(
        "board_commentary_agent",
        status="completed",
        provider=state.language_model.provider,
    )
    return state


def _movement_severity(delta: Decimal) -> str:
    absolute = abs(delta)
    if absolute >= Decimal("500000000"):
        return "MATERIAL"
    if absolute > 0:
        return "WATCH"
    return "INFO"


def _ratio_severity(ratio: Decimal) -> str:
    if ratio < Decimal("0.10"):
        return "MATERIAL"
    if ratio < Decimal("0.12"):
        return "WATCH"
    return "INFO"


def _money(value: object) -> str:
    amount = Decimal(str(value))
    return f"PLN {amount / Decimal('1000000'):,.1f}m"


def _ratio(value: object) -> str:
    return f"{Decimal(str(value)) * Decimal('100'):.2f}%"


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
