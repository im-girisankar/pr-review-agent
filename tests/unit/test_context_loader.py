import json
from pathlib import Path

import pytest


class TestLoadProjectContext:
    def test_returns_none_when_nothing_present(self, tmp_path):
        from pr_review_agent.context.loader import load_project_context

        result = load_project_context(cwd=tmp_path)
        assert result is None

    def test_auto_discovers_md_file(self, tmp_path):
        from pr_review_agent.context.loader import load_project_context

        (tmp_path / ".pr-review-context.md").write_text("my context", encoding="utf-8")
        pc = load_project_context(cwd=tmp_path)
        assert pc is not None
        assert pc.global_md == "my context"

    def test_explicit_md_path(self, tmp_path):
        from pr_review_agent.context.loader import load_project_context

        md = tmp_path / "ctx.md"
        md.write_text("explicit context", encoding="utf-8")
        pc = load_project_context(path=md)
        assert pc is not None
        assert pc.global_md == "explicit context"

    def test_warns_on_large_md(self, tmp_path, capsys):
        from pr_review_agent.context.loader import load_project_context

        large_md = tmp_path / ".pr-review-context.md"
        large_md.write_text("a" * 11_000, encoding="utf-8")
        pc = load_project_context(cwd=tmp_path)
        captured = capsys.readouterr()
        assert pc is not None
        assert "large" in (captured.out + captured.err).lower()

    def test_unknown_extension_returns_none(self, tmp_path, caplog):
        from pr_review_agent.context.loader import load_project_context
        import logging

        txt = tmp_path / "context.txt"
        txt.write_text("data", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            pc = load_project_context(path=txt)
        assert pc is None

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("networkx"),
        reason="networkx not installed",
    )
    def test_auto_discovers_graph_json(self, tmp_path):
        from pr_review_agent.context.loader import load_project_context

        graph_dir = tmp_path / "graphify-out"
        graph_dir.mkdir()
        graph_data = {
            "directed": False,
            "multigraph": False,
            "graph": {},
            "nodes": [{"id": "n1", "label": "Auth Module"}],
            "links": [],
        }
        (graph_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")

        pc = load_project_context(cwd=tmp_path)
        assert pc is not None
        assert pc.graph is not None

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("networkx"),
        reason="networkx not installed",
    )
    def test_both_md_and_graph_loaded_when_present(self, tmp_path):
        from pr_review_agent.context.loader import load_project_context

        (tmp_path / ".pr-review-context.md").write_text("my project", encoding="utf-8")
        graph_dir = tmp_path / "graphify-out"
        graph_dir.mkdir()
        graph_data = {
            "directed": False,
            "multigraph": False,
            "graph": {},
            "nodes": [{"id": "n1", "label": "Auth Module"}],
            "links": [],
        }
        (graph_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")

        pc = load_project_context(cwd=tmp_path)
        assert pc is not None
        assert pc.global_md == "my project"
        assert pc.graph is not None
