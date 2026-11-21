from __future__ import annotations

from archoptimize.reporting.design_diff import diff_designs
from archoptimize.reporting.mermaid_diagram import to_mermaid
from archoptimize.schemas import Component, ComponentType
from archoptimize.schemas.design_patch import ComponentUpdate, DesignPatch, apply_design_patch
from evaluation.eval_cases import load_cases

BEFORE = load_cases(only="01_single")[0].submission.design
AFTER = apply_design_patch(
    BEFORE,
    DesignPatch(
        update_components=[ComponentUpdate(id="orders-db", availability_zones=2)],
        add_components=[Component(id="waf", name="WAF", type=ComponentType.WAF)],
        add_edges=[{"from": "users", "to": "waf"}, {"from": "waf", "to": "web"}],
        remove_edges=[{"source": "users", "target": "web"}],
    ),
)


def test_diff_lists_added_changed_and_rewired():
    diff = diff_designs(BEFORE, AFTER)
    assert diff.added_components == ["waf"]
    assert diff.changed_components["orders-db"][0].field == "availability_zones"
    assert diff.changed_components["orders-db"][0].before == "1"
    assert diff.added_edges == ["users -> waf", "waf -> web"]
    assert diff.removed_edges == ["users -> web"]
    lines = diff.summary_lines()
    assert "+ added waf" in lines and "~ orders-db.availability_zones: 1 → 2" in lines


def test_identical_designs_have_an_empty_diff():
    assert diff_designs(BEFORE, BEFORE).is_empty


def test_after_diagram_highlights_changes():
    diagram = to_mermaid(AFTER, added={"waf"}, changed={"orders-db"})
    assert "class n_waf added" in diagram
    assert "class n_orders_db changed" in diagram
