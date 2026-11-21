from __future__ import annotations

import pytest
from pydantic import ValidationError

from archoptimize.schemas import Component, ComponentGraph, ComponentType, Edge, EdgeMode


def component(id: str, type: ComponentType = ComponentType.COMPUTE_VM, **kw) -> Component:
    return Component(id=id, name=id.title(), type=type, **kw)


def test_valid_graph_and_helpers():
    graph = ComponentGraph(
        name="Shop",
        components=[
            component("web"),
            component("db", ComponentType.RELATIONAL_DATABASE),
        ],
        edges=[Edge(source="web", target="db", protocol="sql")],
    )
    assert graph.component("db").is_data_store
    assert not graph.component("web").is_data_store
    assert graph.edges_from("web")[0].target == "db"
    assert graph.edges_to("db")[0].mode is EdgeMode.SYNC


def test_edges_accept_from_to_aliases():
    edge = Edge.model_validate({"from": "a", "to": "b", "mode": "async"})
    assert (edge.source, edge.target, edge.mode) == ("a", "b", EdgeMode.ASYNC)


@pytest.mark.parametrize(
    "components, edges, message",
    [
        ([component("web"), component("web")], [], "duplicate component ids: web"),
        ([component("web")], [Edge(source="web", target="ghost")], "unknown component 'ghost'"),
        ([component("web")], [Edge(source="web", target="web")], "cannot call itself"),
    ],
)
def test_invalid_graphs_are_rejected(components, edges, message):
    with pytest.raises(ValidationError, match=message):
        ComponentGraph(name="x", components=components, edges=edges)


def test_needs_at_least_one_component():
    with pytest.raises(ValidationError):
        ComponentGraph(name="x", components=[])


@pytest.mark.parametrize("bad_id", ["Web", "1web", "web server", "", "a" * 41])
def test_component_id_format(bad_id):
    with pytest.raises(ValidationError):
        component(bad_id)


def test_autoscaling_max_must_not_be_below_min():
    with pytest.raises(ValidationError, match="max_replicas must be >= min_replicas"):
        component("web", autoscaling={"min_replicas": 4, "max_replicas": 2})


def test_unknown_fields_are_rejected():
    # catches typos like 'replica' instead of 'replicas'
    with pytest.raises(ValidationError):
        Component.model_validate({"id": "web", "name": "Web", "type": "compute_vm", "replica": 2})
