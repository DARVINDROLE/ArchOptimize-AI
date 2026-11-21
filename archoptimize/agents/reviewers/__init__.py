"""Specialist reviewers, one per pillar. `REVIEWERS` maps a pillar to its spec."""

from archoptimize.agents.reviewers.cost_reviewer import COST_REVIEWER
from archoptimize.agents.reviewers.pci_compliance_reviewer import PCI_COMPLIANCE_REVIEWER
from archoptimize.agents.reviewers.reliability_reviewer import RELIABILITY_REVIEWER
from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec, run_pillar_review
from archoptimize.agents.reviewers.scalability_reviewer import SCALABILITY_REVIEWER
from archoptimize.agents.reviewers.security_reviewer import SECURITY_REVIEWER

REVIEWERS: dict = {
    spec.pillar: spec
    for spec in (
        SECURITY_REVIEWER,
        RELIABILITY_REVIEWER,
        COST_REVIEWER,
        SCALABILITY_REVIEWER,
        PCI_COMPLIANCE_REVIEWER,
    )
}

__all__ = ["REVIEWERS", "ReviewerSpec", "run_pillar_review"]
