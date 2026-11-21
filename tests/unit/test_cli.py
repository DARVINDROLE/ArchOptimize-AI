from __future__ import annotations

from archoptimize.cli import main
from archoptimize.design_parsing.yaml_design_parser import design_template_text


def test_preview_prints_summary_and_diagram(tmp_path, capsys):
    path = tmp_path / "design.yaml"
    path.write_text(design_template_text(), encoding="utf-8")

    assert main(["preview", str(path)]) == 0
    out = capsys.readouterr().out
    assert "3 components, 2 edges" in out
    assert "```mermaid" in out


def test_preview_reports_invalid_design(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text("design: {name: x, components: []}", encoding="utf-8")

    assert main(["preview", str(path)]) == 1
    assert "design.components" in capsys.readouterr().err


def test_template_command(capsys):
    assert main(["template"]) == 0
    assert "design:" in capsys.readouterr().out
