"""ReviewResult → Markdown, section by section (the UI shows sections in tabs; the
downloadable report joins them). Pure functions: no LLM, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from archoptimize.reporting.design_diff import diff_designs
from archoptimize.reporting.mermaid_diagram import to_mermaid_markdown
from archoptimize.schemas import DesignSubmission, ReviewResult, Verdict
from archoptimize.schemas.design_metrics import DesignMetrics

DISCLAIMER = (
    "> **AI suggestion, not an approval.** ArchOptimize AI is a learning project. Findings "
    "and numbers are estimates; have a qualified engineer review any real design."
)
VERDICT_LABEL = {
    Verdict.APPROVE: "✅ Approve",
    Verdict.APPROVE_WITH_CHANGES: "🟡 Approve with changes",
    Verdict.REJECT: "⛔ Reject",
}
SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}


def _esc(text: str) -> str:
    """Keep user/LLM text from breaking Markdown tables."""
    return text.replace("|", "\\|").replace("\n", " ")


def verdict_section(result: ReviewResult) -> str:
    lines = [f"## Verdict: {VERDICT_LABEL[result.verdict]}", "", result.summary or "", ""]
    if result.input_flagged:
        lines += [
            "> ⚠️ **Input guard:** the design text looked like a prompt-injection attempt "
            f"({'; '.join(result.guard_reasons)}). It was reviewed on its facts only.",
            "",
        ]
    if result.pillar_scores:
        lines += ["| Pillar | Score | Why |", "|---|---|---|"]
        lines += [
            f"| {s.pillar.value.replace('_', ' ').title()} | {'★' * s.score}{'☆' * (5 - s.score)} "
            f"{s.score}/5 | {_esc(s.rationale)} |"
            for s in result.pillar_scores
        ]
        lines.append("")
    if result.requirement_conflicts:
        lines += ["**Requirement conflicts**", ""]
        lines += [f"- {c}" for c in result.requirement_conflicts] + [""]
    if result.assumptions:
        lines += ["**Assumptions / missing information**", ""]
        lines += [f"- {a}" for a in result.assumptions] + [""]
    if result.warnings:
        lines += ["**Warnings**", ""] + [f"- {w}" for w in result.warnings] + [""]
    return "\n".join(lines)


def findings_section(result: ReviewResult) -> str:
    if not result.findings:
        return "## Findings\n\nNo findings: the design meets its stated requirements."
    sources = {c.chunk_id: c for c in result.sources}
    lines = ["## Findings", ""]
    for f in result.findings:
        cites = []
        for cid in f.citation_chunk_ids:
            chunk = sources.get(cid)
            cites.append(f"[{cid}]({chunk.url})" if chunk else cid)
        uncited = " · _uncited_" if f.id in result.uncited_finding_ids else ""
        lines += [
            f"### {SEVERITY_ICON.get(f.severity.value, '')} {f.id} · {f.title}",
            f"**{f.severity.value.upper()}** · {f.pillar.value.replace('_', ' ')}"
            + (f" · components: `{'`, `'.join(f.component_ids)}`" if f.component_ids else "")
            + uncited,
            "",
            f"**Why:** {f.evidence}",
            "",
            f"**Fix:** {f.recommendation}",
            "",
            f"**Sources:** {', '.join(cites)}" if cites else "",
            "",
        ]
    return "\n".join(lines)


def _metrics_rows(label: str, m: DesignMetrics | None) -> str:
    if m is None:
        return f"| {label} | – | – | – |"
    budget = f" / ${m.cost.budget_usd:,.0f}" if m.cost.budget_usd is not None else ""
    slo = f" / {m.availability.slo_percent} %" if m.availability.slo_percent is not None else ""
    cap = "–" if m.capacity.capacity_rps is None else f"{m.capacity.capacity_rps:,.0f}"
    peak = f" / {m.capacity.peak_rps:,}" if m.capacity.peak_rps else ""
    return (
        f"| {label} | ${m.cost.total_monthly_usd:,.0f}{budget} | "
        f"{m.availability.estimated_percent:.3f} %{slo} | {cap}{peak} |"
    )


def cost_section(result: ReviewResult) -> str:
    lines = [
        "## Cost, availability & capacity",
        "",
        "Numbers come from the calculator tools (MCP), not from the LLM.",
        "",
        "| Design | Monthly cost / budget | Availability / SLO | Capacity RPS / peak |",
        "|---|---|---|---|",
        _metrics_rows("Original", result.original_metrics),
    ]
    if result.revised_metrics:
        lines.append(_metrics_rows("**Revised**", result.revised_metrics))
    for c in result.candidates:
        score = f" (critic {c.critic_score}/10)" if c.critic_score else ""
        lines.append(_metrics_rows(f"Option: {_esc(c.name)}{score}", c.metrics))
    m = result.revised_metrics or result.original_metrics
    if m and m.cost.lines:
        lines += [
            "",
            "**Cost breakdown** (" + ("revised" if result.revised_metrics else "original") + ")",
            "",
        ]
        lines += ["| Component | Basis | $/month |", "|---|---|---|"]
        lines += [
            f"| {x.component_id} | {_esc(x.description)} | {x.monthly_usd:,.0f} |"
            for x in m.cost.lines
        ]
        if m.cost.unpriced_component_ids:
            lines += ["", f"Not priced: {', '.join(m.cost.unpriced_component_ids)}"]
        lines += ["", f"_{m.cost.basis}_"]
    if result.candidates:
        lines += ["", "## Options considered (Tree of Thoughts)", ""]
        for c in result.candidates:
            lines += [f"**{c.name}** — {c.approach}", "", f"Trade-offs: {c.trade_offs}", ""]
        if result.critic_rationale:
            lines += [f"**Critic's choice:** {result.critic_rationale}", ""]
    if result.tool_calls:
        lines += [
            "",
            "**Calculator calls:** "
            + ", ".join(
                f"{t.tool} via {t.via} ({t.summary}, {t.seconds}s)" for t in result.tool_calls
            ),
        ]
    return "\n".join(lines)


def design_section(submission: DesignSubmission, result: ReviewResult) -> str:
    before = submission.design
    if result.revised_design is None:
        return "## Design\n\nNo redesign needed.\n\n" + to_mermaid_markdown(before)
    diff = diff_designs(before, result.revised_design)
    lines = [
        "## Revised design",
        "",
        f"Redesign rounds: {result.redesign_rounds}. Green = added, amber = changed.",
        "",
        "### Before",
        to_mermaid_markdown(before),
        "",
        "### After",
        to_mermaid_markdown(
            result.revised_design,
            added=set(diff.added_components),
            changed=set(diff.changed_components),
        ),
        "",
        "### Changes",
        "",
    ]
    lines += [
        f"- {c.description}" + (f" _(fixes {', '.join(c.finding_ids)})_" if c.finding_ids else "")
        for c in result.design_changes
    ]
    lines += ["", "<details><summary>Exact diff</summary>", "", "```diff"]
    lines += diff.summary_lines() or ["(no structural change)"]
    lines += ["```", "</details>"]
    if result.remaining_issues:
        lines += ["", "**Still open after redesign:**", ""]
        lines += [f"- {f.id} ({f.severity.value}): {f.title}" for f in result.remaining_issues]
    return "\n".join(lines)


def trace_section(result: ReviewResult) -> str:
    lines = ["## How this review was produced", "", "| Agent | Model |", "|---|---|"]
    lines += [f"| {agent} | `{model}` |" for agent, model in result.models_used.items()]
    if result.tokens_used:
        lines += ["", f"Tokens used: {result.tokens_used:,}"]
    return "\n".join(lines)


def build_report(submission: DesignSubmission, result: ReviewResult) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return "\n\n".join(
        [
            f"# Architecture review: {submission.design.name}",
            f"_Generated by ArchOptimize AI on {stamp}_",
            DISCLAIMER,
            verdict_section(result),
            findings_section(result),
            design_section(submission, result),
            cost_section(result),
            trace_section(result),
        ]
    )
