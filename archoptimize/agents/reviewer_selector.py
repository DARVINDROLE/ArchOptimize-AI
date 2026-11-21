"""Decide which specialist reviewers run.

A simple rule is enough here (and is cheaper and more predictable than an LLM call):
the four core pillars always run; the PCI reviewer joins only when PCI DSS is required.
"""

from __future__ import annotations

from archoptimize.schemas import ComplianceStandard, DesignSubmission, Pillar

CORE_PILLARS = (
    Pillar.SECURITY,
    Pillar.RELIABILITY,
    Pillar.COST_OPTIMIZATION,
    Pillar.PERFORMANCE_EFFICIENCY,
)


def select_pillars(submission: DesignSubmission) -> list[Pillar]:
    pillars = list(CORE_PILLARS)
    if submission.requirements.requires(ComplianceStandard.PCI_DSS):
        pillars.append(Pillar.COMPLIANCE)
    return pillars
