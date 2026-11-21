"""How similar are two designs? Used to check that YAML and free-text input of the same
system produce (nearly) the same ComponentGraph (Step 8).

Ids may differ between inputs ("orders-db" vs "orders_database"), so components are
matched by type (and AWS service when both have one), not by id.

score = average of
- component match:  matched components / max(component counts)
- edge match:       edges whose (source type, target type) pair appears in both
- fact match:       for matched components, equal availability_zones / replicas / public
"""

from __future__ import annotations

from collections import Counter

from archoptimize.schemas import Component, ComponentGraph


def _key(c: Component) -> str:
    return c.type.value


def _match_components(a: ComponentGraph, b: ComponentGraph) -> list[tuple[Component, Component]]:
    pairs: list[tuple[Component, Component]] = []
    free = list(b.components)
    for ca in a.components:
        candidates = [cb for cb in free if _key(cb) == _key(ca)]
        if not candidates:
            continue
        # prefer the same AWS service, then the same name
        candidates.sort(
            key=lambda cb: (
                (cb.aws_service or "").lower() != (ca.aws_service or "").lower(),
                cb.name.lower() != ca.name.lower(),
            )
        )
        pairs.append((ca, candidates[0]))
        free.remove(candidates[0])
    return pairs


def _edge_types(g: ComponentGraph) -> Counter:
    types = {c.id: c.type.value for c in g.components}
    return Counter((types[e.source], types[e.target]) for e in g.edges)


def graph_similarity(a: ComponentGraph, b: ComponentGraph) -> float:
    pairs = _match_components(a, b)
    component_score = len(pairs) / max(len(a.components), len(b.components))

    ea, eb = _edge_types(a), _edge_types(b)
    total_edges = max(sum(ea.values()), sum(eb.values()))
    edge_score = sum((ea & eb).values()) / total_edges if total_edges else 1.0

    checks = [
        getattr(x, f) == getattr(y, f)
        for x, y in pairs
        for f in ("availability_zones", "replicas", "public")
    ]
    fact_score = sum(checks) / len(checks) if checks else 0.0
    return round((component_score + edge_score + fact_score) / 3, 3)
