"""Score one review against its answer key, then summarise many.

Metrics
- flaw recall:      planted flaws found / planted flaws (main quality number)
- false alarms:     HIGH/CRITICAL findings that match neither a planted flaw nor a known
                    secondary issue (low-severity extras are not punished)
- verdict accuracy: verdict is one of the acceptable verdicts
- behaviour pass:   e.g. injection flagged, conflict stated, assumptions listed
- latency, tokens:  cost of the review
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from archoptimize.schemas import Finding, ReviewResult, Severity
from evaluation.eval_cases import BehaviourCheck, EvalCase, ExpectedIssue


def finding_matches(finding: Finding, issue: ExpectedIssue) -> bool:
    if finding.pillar not in issue.pillars:
        return False
    if not issue.component_ids:  # system-wide issue
        return True
    return bool(set(finding.component_ids) & set(issue.component_ids))


def match_findings(
    issues: list[ExpectedIssue], findings: list[Finding], skip: set[int] | None = None
) -> dict[str, int]:
    """Pair each issue with at most one finding (and each finding with at most one issue).
    Findings are tracked by position, because LLMs sometimes repeat ids.
    Returns {issue_id: index into findings}."""
    matched: dict[str, int] = {}
    used: set[int] = set(skip or ())
    for issue in issues:
        for i, finding in enumerate(findings):
            if i not in used and finding_matches(finding, issue):
                matched[issue.id] = i
                used.add(i)
                break
    return matched


def _behaviour_passed(check: BehaviourCheck, result: ReviewResult) -> bool:
    if check is BehaviourCheck.INPUT_FLAGGED:
        return result.input_flagged
    if check is BehaviourCheck.REQUIREMENT_CONFLICT_STATED:
        return bool(result.requirement_conflicts)
    return bool(result.assumptions)  # ASSUMPTIONS_LISTED


@dataclass
class CaseScore:
    case_id: str
    flaws_planted: int
    flaws_found: int
    missed_flaws: list[str]
    false_alarms: int
    unmatched_findings: int
    verdict: str | None
    verdict_correct: bool
    behaviours: dict[str, bool] = field(default_factory=dict)
    findings_total: int = 0
    findings_cited: int = 0  # findings with at least one valid (retrieved) citation
    latency_seconds: float = 0.0
    tokens_used: int | None = None
    error: str | None = None


def score_case(
    case: EvalCase, result: ReviewResult | None, latency_seconds: float, error: str | None = None
) -> CaseScore:
    expected = case.expected
    if result is None:  # the reviewer crashed: everything counts as missed
        return CaseScore(
            case_id=case.case_id,
            flaws_planted=len(expected.planted_flaws),
            flaws_found=0,
            missed_flaws=[f.id for f in expected.planted_flaws],
            false_alarms=0,
            unmatched_findings=0,
            verdict=None,
            verdict_correct=False,
            behaviours={b.value: False for b in expected.behaviours},
            latency_seconds=latency_seconds,
            error=error,
        )

    planted = match_findings(expected.planted_flaws, result.findings)
    secondary = match_findings(
        expected.secondary_issues, result.findings, skip=set(planted.values())
    )
    explained = set(planted.values()) | set(secondary.values())
    unmatched = [f for i, f in enumerate(result.findings) if i not in explained]

    return CaseScore(
        case_id=case.case_id,
        flaws_planted=len(expected.planted_flaws),
        flaws_found=len(planted),
        missed_flaws=[f.id for f in expected.planted_flaws if f.id not in planted],
        false_alarms=sum(1 for f in unmatched if f.severity.rank >= Severity.HIGH.rank),
        unmatched_findings=len(unmatched),
        verdict=result.verdict.value,
        verdict_correct=result.verdict in expected.acceptable_verdicts,
        behaviours={b.value: _behaviour_passed(b, result) for b in expected.behaviours},
        findings_total=len(result.findings),
        findings_cited=sum(1 for f in result.findings if f.citation_chunk_ids),
        latency_seconds=round(latency_seconds, 3),
        tokens_used=result.tokens_used,
        error=error,
    )


@dataclass
class EvalSummary:
    reviewer: str
    cases: int
    flaw_recall: float
    flaws_found: int
    flaws_planted: int
    false_alarms: int
    verdict_accuracy: float
    behaviour_pass_rate: float | None
    citation_rate: float | None  # cited findings / all findings (None if no findings)
    avg_latency_seconds: float
    avg_tokens: float | None
    errors: int

    def as_dict(self) -> dict:
        return asdict(self)


def summarize(reviewer: str, scores: list[CaseScore]) -> EvalSummary:
    n = len(scores)
    planted = sum(s.flaws_planted for s in scores)
    found = sum(s.flaws_found for s in scores)
    behaviour_results = [ok for s in scores for ok in s.behaviours.values()]
    tokens = [s.tokens_used for s in scores if s.tokens_used is not None]
    total_findings = sum(s.findings_total for s in scores)
    return EvalSummary(
        reviewer=reviewer,
        cases=n,
        flaw_recall=round(found / planted, 3) if planted else 0.0,
        flaws_found=found,
        flaws_planted=planted,
        false_alarms=sum(s.false_alarms for s in scores),
        verdict_accuracy=round(sum(s.verdict_correct for s in scores) / n, 3) if n else 0.0,
        behaviour_pass_rate=(
            round(sum(behaviour_results) / len(behaviour_results), 3) if behaviour_results else None
        ),
        citation_rate=(
            round(sum(s.findings_cited for s in scores) / total_findings, 3)
            if total_findings
            else None
        ),
        avg_latency_seconds=round(sum(s.latency_seconds for s in scores) / n, 3) if n else 0.0,
        avg_tokens=round(sum(tokens) / len(tokens), 1) if tokens else None,
        errors=sum(1 for s in scores if s.error),
    )
