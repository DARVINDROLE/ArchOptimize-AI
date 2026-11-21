from __future__ import annotations

import pytest

from archoptimize.schemas import Component, ComponentType
from archoptimize.schemas.design_patch import (
    ComponentUpdate,
    DesignPatch,
    EdgeRef,
    PatchError,
    apply_design_patch,
)
from evaluation.eval_cases import load_cases

DESIGN = load_cases(only="01_single")[0].submission.design


def test_update_add_and_rewire():
    patch = DesignPatch(
        update_components=[
            ComponentUpdate(id="web", replicas=2, availability_zones=2),
            ComponentUpdate(id="orders-db", availability_zones=2),
        ],
        add_components=[Component(id="alb", name="ALB", type=ComponentType.LOAD_BALANCER)],
        remove_edges=[EdgeRef(source="users", target="web")],
        add_edges=[{"from": "users", "to": "alb"}, {"from": "alb", "to": "web"}],
    )
    new = apply_design_patch(DESIGN, patch)
    assert new.component("web").replicas == 2
    assert new.component("web").instance_type == "m5.large"  # untouched fields kept
    assert {(e.source, e.target) for e in new.edges} == {
        ("users", "alb"),
        ("alb", "web"),
        ("web", "orders-db"),
    }
    assert DESIGN.component("web").replicas == 1  # original unchanged


def test_removing_a_component_drops_its_edges():
    new = apply_design_patch(DESIGN, DesignPatch(remove_component_ids=["orders-db"]))
    assert all("orders-db" not in (e.source, e.target) for e in new.edges)


@pytest.mark.parametrize(
    "patch",
    [
        DesignPatch(update_components=[ComponentUpdate(id="ghost", replicas=2)]),
        DesignPatch(remove_component_ids=["ghost"]),
        DesignPatch(add_components=[Component(id="web", name="Dup", type=ComponentType.OTHER)]),
        DesignPatch(add_edges=[{"from": "web", "to": "nowhere"}]),
    ],
)
def test_invalid_patches_are_rejected(patch):
    with pytest.raises(PatchError):
        apply_design_patch(DESIGN, patch)
