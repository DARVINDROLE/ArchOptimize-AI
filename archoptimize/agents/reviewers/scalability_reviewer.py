from archoptimize.agents.reviewers.reviewer_base import ReviewerSpec
from archoptimize.schemas import Pillar

SCALABILITY_REVIEWER = ReviewerSpec(
    pillar=Pillar.PERFORMANCE_EFFICIENCY,
    display_name="Scalability / performance reviewer",
    id_prefix="PERF",
    prompt_name="scalability_reviewer",
)
