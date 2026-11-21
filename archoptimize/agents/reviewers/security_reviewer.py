from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec
from archoptimize.schemas import Pillar

SECURITY_REVIEWER = ReviewerSpec(
    pillar=Pillar.SECURITY,
    display_name="Security reviewer",
    id_prefix="SEC",
    prompt_name="security_reviewer",
)
