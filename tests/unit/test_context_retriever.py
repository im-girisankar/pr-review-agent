import json
from pathlib import Path

import pytest


def _make_graph():
    """Build a small NetworkX graph matching the fixture for tests that can't read the file."""
    try:
        import networkx as nx
    except ImportError:
        return None

    G = nx.Graph()
    G.add_node("auth_module", label="Authentication Module", file_type="code")
    G.add_node("token_validator", label="Token Permission Validator", file_type="code")
    G.add_node("null_handler", label="Null Exception Handler", file_type="code")
    G.add_node("resource_cleanup", label="Resource Leak Cleanup", file_type="code")
    G.add_node("query_cache", label="Redis Query Cache Layer", file_type="code")
    G.add_node("latency_monitor", label="Latency Memory Monitor", file_type="code")
    G.add_node("test_fixtures", label="Test Fixture Factory", file_type="code")
    G.add_node("mock_provider", label="Mock Coverage Provider", file_type="code")

    G.add_edge("auth_module", "token_validator", relation="uses")
    G.add_edge("null_handler", "resource_cleanup", relation="implements")
    G.add_edge("query_cache", "latency_monitor", relation="reports_to")
    G.add_edge("test_fixtures", "mock_provider", relation="uses")
    return G


nx = pytest.importorskip("networkx", reason="networkx not installed — skipping graph tests")


class TestProjectContextRetrieve:
    def test_empty_context_returns_empty_string(self):
        from pr_review_agent.context.retriever import ProjectContext

        pc = ProjectContext()
        assert pc.retrieve("security") == ""

    def test_global_md_returned_when_no_graph(self):
        from pr_review_agent.context.retriever import ProjectContext

        pc = ProjectContext(global_md="My project conventions here.")
        result = pc.retrieve("security")
        assert "My project conventions here." in result

    def test_graph_retrieval_security_category(self):
        from pr_review_agent.context.retriever import ProjectContext

        G = _make_graph()
        pc = ProjectContext(graph=G)
        result = pc.retrieve("security")
        # Security seeds include "auth", "token", "permission" — should find auth_module / token_validator
        assert "Authentication" in result or "Token" in result

    def test_graph_retrieval_bug_category(self):
        from pr_review_agent.context.retriever import ProjectContext

        G = _make_graph()
        pc = ProjectContext(graph=G)
        result = pc.retrieve("bug_detection")
        # Bug seeds include "null", "leak" — should find null_handler / resource_cleanup
        assert "Null" in result or "Leak" in result or "Resource" in result

    def test_graph_retrieval_test_coverage_category(self):
        from pr_review_agent.context.retriever import ProjectContext

        G = _make_graph()
        pc = ProjectContext(graph=G)
        result = pc.retrieve("test_coverage")
        # Test seeds include "test", "fixture", "mock", "coverage"
        assert "Fixture" in result or "Mock" in result or "Coverage" in result

    def test_security_result_does_not_contain_only_bug_nodes(self):
        from pr_review_agent.context.retriever import ProjectContext

        G = _make_graph()
        pc = ProjectContext(graph=G)
        security_result = pc.retrieve("security")
        bug_result = pc.retrieve("bug_detection")
        # They may overlap via BFS but security should not exclusively return bug-only nodes
        assert security_result != bug_result or security_result == ""

    def test_budget_truncation_kicks_in(self):
        from pr_review_agent.context.retriever import ProjectContext

        long_md = "x" * 10_000
        pc = ProjectContext(global_md=long_md)
        result = pc.retrieve("security", budget_tokens=100)
        assert len(result) <= 100 * 4 + len("\n... (truncated)")
        assert "(truncated)" in result

    def test_no_matching_nodes_falls_back_to_global_md(self):
        from pr_review_agent.context.retriever import ProjectContext

        G = nx.Graph()
        G.add_node("unrelated", label="Completely Unrelated Thing", file_type="code")
        pc = ProjectContext(graph=G, global_md="fallback text")
        # No security seed matches "unrelated" → should fall back to global_md
        result = pc.retrieve("security")
        assert "fallback text" in result
