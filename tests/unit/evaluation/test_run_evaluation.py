from __future__ import annotations

import json

from archoptimize.schemas import ReviewResult, Verdict
from evaluation.run_evaluation import format_table, main, run_evaluation, save_results


def test_rubber_stamp_scores_zero_recall(tmp_path):
    summary, scores = run_evaluation("rubber_stamp", lambda _s: ReviewResult(verdict="approve"))
    assert summary.cases == len(scores) >= 12
    assert summary.flaw_recall == 0.0
    assert summary.false_alarms == 0
    # approving everything is only right for the one good design
    assert [s.case_id for s in scores if s.verdict_correct] == ["04_well_architected"]

    path = save_results(summary, scores, results_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["summary"]["reviewer"] == "rubber_stamp"
    assert len(saved["cases"]) == summary.cases
    assert "flaw recall=0%" in format_table(summary, scores)


def test_a_crashing_reviewer_does_not_stop_the_run():
    def broken(_submission):
        raise RuntimeError("model unavailable gsk_" + "k" * 30)

    summary, scores = run_evaluation("broken", broken, only="pci")
    assert summary.errors == 1
    assert "[redacted-key]" in scores[0].error


def test_cli_runs_without_saving(capsys):
    assert main(["--case", "public_database", "--no-save"]) == 0
    out = capsys.readouterr().out
    assert "13_public_database" in out and "Saved" not in out


def test_cli_no_matching_cases():
    assert main(["--case", "does-not-exist", "--no-save"]) == 1


def test_verdict_enum_values_match_answer_keys():
    assert {v.value for v in Verdict} == {"approve", "approve_with_changes", "reject"}
