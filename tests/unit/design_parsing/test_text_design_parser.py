from __future__ import annotations

import pytest

from archoptimize.core.errors import DesignInputError
from archoptimize.design_parsing.text_design_parser import (
    normalise_component_types,
    parse_design_text,
)
from archoptimize.schemas import ComponentType, DesignSubmission
from evaluation.eval_cases import load_cases
from evaluation.graph_similarity import graph_similarity
from tests.fake_llm import KEYS, fake_router

MONOLITH = load_cases(only="01_single")[0].submission


def test_text_is_sent_as_untrusted_data_and_parsed():
    calls: list = []
    router = fake_router({DesignSubmission: MONOLITH}, calls)
    result = parse_design_text("A web server and a database. " * 3, keys=KEYS, router=router)
    assert result == MONOLITH
    system, human = calls[0][1]
    assert "UNTRUSTED" in system[1] and human[1].startswith("<design_document>")


def test_types_contradicting_the_aws_service_are_corrected():
    wrong = MONOLITH.design.model_copy(
        update={
            "components": [
                c.model_copy(update={"type": ComponentType.SERVERLESS_FUNCTION})
                if c.id == "web"
                else c.model_copy(update={"public": True})
                if c.id == "users"
                else c
                for c in MONOLITH.design.components
            ]
        }
    )
    fixed = normalise_component_types(MONOLITH.model_copy(update={"design": wrong}))
    assert fixed.design.component("web").type is ComponentType.COMPUTE_VM  # aws_service EC2
    assert fixed.design.component("users").public is False


@pytest.mark.parametrize("text", ["", "too short", "x" * 20_000])
def test_rejects_empty_short_or_huge_input(text):
    with pytest.raises(DesignInputError):
        parse_design_text(text, keys=KEYS, router=fake_router({}))


def test_similarity_identical_and_renamed():
    assert graph_similarity(MONOLITH.design, MONOLITH.design) == 1.0
    renamed = MONOLITH.design.model_copy(
        update={
            "components": [
                c.model_copy(update={"id": c.id.replace("-", "_") + "x"})
                for c in MONOLITH.design.components
            ],
            "edges": [
                e.model_copy(
                    update={
                        "source": e.source.replace("-", "_") + "x",
                        "target": e.target.replace("-", "_") + "x",
                    }
                )
                for e in MONOLITH.design.edges
            ],
        }
    )
    assert graph_similarity(MONOLITH.design, renamed) == 1.0  # ids do not matter


def test_similarity_drops_for_different_designs():
    other = load_cases(only="04_well")[0].submission.design
    assert graph_similarity(MONOLITH.design, other) < 0.6
