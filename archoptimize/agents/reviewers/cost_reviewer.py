from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec
from archoptimize.schemas import Pillar

COST_REVIEWER = ReviewerSpec(
    pillar=Pillar.COST_OPTIMIZATION,
    display_name="Cost reviewer",
    id_prefix="COST",
    prompt_name="cost_reviewer",
)
