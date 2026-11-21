from __future__ import annotations

import pytest

from archoptimize.design_parsing.yaml_design_parser import design_template_text, parse_design_yaml
from archoptimize.reporting.mermaid_diagram import to_mermaid, to_mermaid_markdown
from archoptimize.schemas import Component, ComponentGraph, ComponentType, Edge


@pytest.fixture
def template_graph() -> ComponentGraph:
    return parse_design_yaml(design_template_text()).design


def test_renders_nodes_edges_and_shapes(template_graph):
    diagram = to_mermaid(template_graph)
    lines = diagram.splitlines()
    assert lines[0] == "flowchart LR"
    assert any(line.strip().startswith('n_orders_db[("') for line in lines)  # cylinder
    assert any(line.strip().startswith('n_users(["') for line in lines)  # stadium
    assert "n_users -->|https| n_web" in diagram
    assert "n_web -->|sql| n_orders_db" in diagram
    assert "class n_web public" in diagram  # internet-facing marked


def test_output_is_deterministic(template_graph):
    assert to_mermaid(template_graph) == to_mermaid(template_graph)


def test_async_edges_are_dotted():
    graph = ComponentGraph(
        name="x",
        components=[
            Component(id="api", name="API", type=ComponentType.SERVERLESS_FUNCTION),
            Component(id="jobs", name="Jobs", type=ComponentType.QUEUE),
        ],
        edges=[Edge(source="api", target="jobs", mode="async")],
    )
    assert "n_api -.-> n_jobs" in to_mermaid(graph)


def test_labels_are_escaped_and_keywords_are_safe():
    graph = ComponentGraph(
        name="x",
        components=[Component(id="end", name='Say "hi" <now>', type=ComponentType.COMPUTE_VM)],
    )
    diagram = to_mermaid(graph)
    assert "n_end[" in diagram  # 'end' is a Mermaid keyword; the prefix keeps it safe
    assert "#quot;hi#quot;" in diagram and "#lt;now#gt;" in diagram


def test_similar_ids_do_not_collide():
    graph = ComponentGraph(
        name="x",
        components=[
            Component(id="a-b", name="One", type=ComponentType.OTHER),
            Component(id="a_b", name="Two", type=ComponentType.OTHER),
        ],
    )
    diagram = to_mermaid(graph)
    assert "n_a_b[" in diagram and "n_a_b_2[" in diagram


def test_autoscaling_label_and_markdown_wrapper():
    graph = ComponentGraph(
        name="x",
        components=[
            Component(
                id="web",
                name="Web",
                type=ComponentType.COMPUTE_VM,
                availability_zones=2,
                autoscaling={"min_replicas": 2, "max_replicas": 6},
            )
        ],
    )
    assert "×2–6 (auto) · 2 AZ" in to_mermaid(graph)
    assert to_mermaid_markdown(graph).startswith("```mermaid\nflowchart LR")


def test_rejects_unknown_direction(template_graph):
    with pytest.raises(ValueError):
        to_mermaid(template_graph, direction="XY")
