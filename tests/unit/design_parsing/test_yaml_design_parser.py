from __future__ import annotations

import pytest

from archoptimize.core.errors import DesignInputError
from archoptimize.design_parsing.yaml_design_parser import (
    design_template_text,
    load_design_file,
    parse_design_yaml,
)
from archoptimize.schemas import ComponentType

MINIMAL = """
design:
  name: Tiny
  components:
    - {id: app, name: App, type: compute_vm}
"""


def issues_of(text: str) -> list[str]:
    with pytest.raises(DesignInputError) as err:
        parse_design_yaml(text)
    return [str(issue) for issue in err.value.issues]


def test_template_is_a_valid_design():
    submission = parse_design_yaml(design_template_text())
    assert submission.design.component("orders-db").type is ComponentType.RELATIONAL_DATABASE
    assert submission.requirements.availability_slo_percent == 99.9
    assert len(submission.design.edges) == 2


def test_minimal_design_gets_default_requirements():
    submission = parse_design_yaml(MINIMAL)
    assert submission.requirements.region == "us-east-1"
    assert submission.requirements.missing_essentials()  # nothing stated


def test_load_from_file(tmp_path):
    path = tmp_path / "design.yaml"
    path.write_text(MINIMAL, encoding="utf-8")
    assert load_design_file(path).design.name == "Tiny"


def test_non_utf8_file_gives_a_friendly_error(tmp_path):
    path = tmp_path / "design.yaml"
    path.write_bytes("design:\n  name: Café — shop\n".encode("cp1252"))
    with pytest.raises(DesignInputError, match="not UTF-8"):
        load_design_file(path)


def test_validation_errors_point_at_the_field():
    text = MINIMAL.replace("compute_vm", "mainframe")
    assert any(i.startswith("design.components[0].type:") for i in issues_of(text))


def test_all_errors_are_reported_at_once():
    text = """
design:
  name: Bad
  components:
    - {id: App, name: App, type: compute_vm}
requirements:
  peak_rps: -5
"""
    locations = [i.split(":")[0] for i in issues_of(text)]
    assert "design.components[0].id" in locations
    assert "requirements.peak_rps" in locations


def test_broken_yaml_reports_line():
    assert "line" in issues_of("design:\n  name: [unclosed\n")[0]


def test_aliases_are_rejected():
    text = MINIMAL + "\nx: &a [1, 2]\ny: *a\n"
    assert "aliases" in issues_of(text)[0]


@pytest.mark.parametrize("text", ["", "   ", "- just\n- a list\n", "plain string"])
def test_non_mapping_or_empty_input(text):
    assert issues_of(text)


def test_size_cap():
    assert "limit" in issues_of(MINIMAL + "#" * 20_000)[0]


def test_python_object_tags_are_not_executed():
    assert issues_of("!!python/object/apply:os.system ['echo hacked']")
