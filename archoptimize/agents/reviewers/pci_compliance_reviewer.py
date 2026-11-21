from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec
from archoptimize.schemas import Pillar

PCI_COMPLIANCE_REVIEWER = ReviewerSpec(
    pillar=Pillar.COMPLIANCE,
    display_name="PCI DSS compliance reviewer",
    id_prefix="PCI",
    prompt_name="pci_compliance_reviewer",
)
