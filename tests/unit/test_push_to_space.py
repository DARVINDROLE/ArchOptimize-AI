from __future__ import annotations

from deployment import push_to_space


def test_missing_index_blocks_but_missing_demos_only_warn(tmp_path, monkeypatch):
    monkeypatch.setattr(push_to_space, "ROOT", tmp_path)
    (tmp_path / "requirements.txt").write_text("gradio==6.32.0\n")
    problems, warnings = push_to_space.check_ready()
    assert any("index missing" in p for p in problems)
    assert any("demo" in w for w in warnings)

    index = tmp_path / "data" / "knowledge_index"
    index.mkdir(parents=True)
    (index / "chroma.sqlite3").write_bytes(b"x")
    problems, _ = push_to_space.check_ready()
    assert problems == []


def test_uploads_only_app_files():
    assert "archoptimize/**" in push_to_space.INCLUDE
    assert not any(p.startswith(".env") or "source_docs" in p for p in push_to_space.INCLUDE)
