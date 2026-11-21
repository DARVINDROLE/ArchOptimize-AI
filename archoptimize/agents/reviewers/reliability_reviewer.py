from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec
from archoptimize.schemas import Pillar

RELIABILITY_REVIEWER = ReviewerSpec(
    pillar=Pillar.RELIABILITY,
    display_name="Reliability reviewer",
    id_prefix="REL",
    prompt_name="reliability_reviewer",
)
