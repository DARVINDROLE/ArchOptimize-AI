"""Wire the nodes into a LangGraph graph.

START → input_guard → select_reviewers ─┬→ pillar_review (security)    ─┐
                                        ├→ pillar_review (reliability) ─┤
                                        ├→ pillar_review (cost)        ─┼→ chair
                                        ├→ pillar_review (scalability) ─┤
                                        └→ pillar_review (pci, if any) ─┘
chair ──(approved)──────────────────────────────────────────────────────→ finalize → END
chair ──(needs changes)→ architect → critic → rereview ─(issues left, round < 2)→ architect
                                                       └(done)──────────────────→ finalize
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from archoptimize.review_workflow.workflow_nodes import (
    after_architect,
    after_chair,
    after_rereview,
    architect_node,
    chair_node,
    critic_node,
    fan_out_to_reviewers,
    finalize_node,
    guard_node,
    pillar_review_node,
    rereview_node,
    select_node,
)
from archoptimize.review_workflow.workflow_state import ReviewState


@lru_cache(maxsize=1)
def build_review_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("input_guard", guard_node)
    graph.add_node("select_reviewers", select_node)
    graph.add_node("pillar_review", pillar_review_node)
    graph.add_node("chair", chair_node)
    graph.add_node("architect", architect_node)
    graph.add_node("critic", critic_node)
    graph.add_node("rereview", rereview_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "input_guard")
    graph.add_edge("input_guard", "select_reviewers")
    graph.add_conditional_edges("select_reviewers", fan_out_to_reviewers, ["pillar_review"])
    graph.add_edge("pillar_review", "chair")  # waits for all parallel reviewers
    graph.add_conditional_edges("chair", after_chair, ["architect", "finalize"])
    graph.add_conditional_edges("architect", after_architect, ["critic", "finalize"])
    graph.add_edge("critic", "rereview")
    graph.add_conditional_edges("rereview", after_rereview, ["architect", "finalize"])
    graph.add_edge("finalize", END)
    return graph.compile()
