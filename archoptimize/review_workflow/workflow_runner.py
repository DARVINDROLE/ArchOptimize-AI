"""Run a full board review and stream progress events (used by the UI, CLI and eval)."""

from __future__ import annotations

from collections.abc import Callable

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.review_workflow.workflow_graph import build_review_graph
from archoptimize.review_workflow.workflow_state import WorkflowDeps
from archoptimize.schemas import DesignSubmission, ReviewResult

# Parallel reviewers at once. Small on purpose: Groq free-tier rate limits.
MAX_PARALLEL_REVIEWERS = 2


class ReviewFailedError(RuntimeError):
    pass


def run_review(
    submission: DesignSubmission,
    *,
    keys: ProviderKeys | None = None,
    retriever: PillarRetriever | None = None,
    router: ModelRouter | None = None,
    use_guard_model: bool = True,
    redesign: bool = True,
    on_event: Callable[[str], None] | None = None,
) -> ReviewResult:
    deps = WorkflowDeps(
        keys=keys or ProviderKeys.from_env(),
        retriever=retriever,
        router=router,
        use_guard_model=use_guard_model,
        redesign=redesign,
    )
    config = {"configurable": {"deps": deps}, "max_concurrency": MAX_PARALLEL_REVIEWERS}
    result: ReviewResult | None = None
    # stream_mode="updates" yields {node_name: what_that_node_returned} as each node finishes
    for update in build_review_graph().stream(
        {"submission": submission}, config, stream_mode="updates"
    ):
        for node_output in update.values():
            if not node_output:
                continue
            if on_event:
                for event in node_output.get("events", []):
                    on_event(event)
            result = node_output.get("result", result)
    if result is None:
        raise ReviewFailedError("the review did not produce a result")
    return result
