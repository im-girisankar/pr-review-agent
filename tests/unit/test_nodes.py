import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from pr_review_agent.fetchers.models import FileDiff, PullRequest
from pr_review_agent.output.models import Finding


def _make_pr(**kwargs) -> PullRequest:
    defaults = dict(
        id="42", title="Test PR", description="", author="dev",
        source_branch="feat", target_branch="main",
        provider="github", url="https://github.com/o/r/pull/42",
        files=[
            FileDiff(
                path="src/main.py", status="modified",
                additions=5, deletions=2,
                diff_text="@@ -1,2 +1,5 @@\n context\n+new line\n",
                language="python",
            )
        ],
    )
    defaults.update(kwargs)
    return PullRequest(**defaults)


def _make_finding(**kwargs) -> Finding:
    defaults = dict(
        category="bug", severity="medium", file="src/main.py",
        line_start=10, line_end=12,
        title="Null dereference", description="obj may be None",
        suggestion="Add a None check",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _make_settings(**kwargs):
    from pr_review_agent.core.settings import Settings
    defaults = dict(
        temperature=0.2, max_tokens=2000, retry_attempts=1,
        parallel=True, enable_self_critique=True,
        context_budget_tokens=1500, project_context_path=None,
    )
    defaults.update(kwargs)
    s = Settings.model_construct(**defaults)
    return s


# ---------------------------------------------------------------------------
# fetch node
# ---------------------------------------------------------------------------

class TestFetchNode:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        from pr_review_agent.nodes.fetch import make_fetch_node
        pr = _make_pr()
        fetcher = MagicMock()
        fetcher.fetch_pr.return_value = pr

        node = make_fetch_node(fetcher)
        result = await node({"pr_url": "https://github.com/o/r/pull/42", "provider": "github", "errors": []})

        assert result["pull_request"] == pr
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_fetch_exception_captured(self):
        from pr_review_agent.nodes.fetch import make_fetch_node
        fetcher = MagicMock()
        fetcher.fetch_pr.side_effect = RuntimeError("network error")

        node = make_fetch_node(fetcher)
        result = await node({"pr_url": "bad-url", "provider": "github", "errors": []})

        assert result["pull_request"] is None
        assert len(result["errors"]) == 1
        assert "network error" in result["errors"][0]


# ---------------------------------------------------------------------------
# analysis node
# ---------------------------------------------------------------------------

class TestAnalysisNode:
    def _make_llm(self, content: str) -> MagicMock:
        llm = MagicMock()
        from pr_review_agent.llm.base import LLMResponse
        llm.acomplete = AsyncMock(return_value=LLMResponse(content=content, model="test"))
        return llm

    @pytest.mark.asyncio
    async def test_returns_parsed_findings(self):
        from pr_review_agent.nodes.analysis import make_analysis_node
        payload = json.dumps({"findings": [
            {
                "category": "bug", "severity": "high",
                "file": "src/main.py", "line_start": 5, "line_end": 7,
                "title": "Null deref", "description": "obj may be None",
                "suggestion": "Check for None",
            }
        ]})
        llm = self._make_llm(payload)
        settings = _make_settings()

        def build_prompt(title, desc, diff, project_context=""):
            return "sys", "user"

        node = make_analysis_node("bug", build_prompt, llm, settings)
        state = {
            "pull_request": _make_pr(),
            "findings": [],
            "errors": [],
        }
        result = await node(state)

        assert len(result["findings"]) == 1
        assert result["findings"][0].severity == "high"

    @pytest.mark.asyncio
    async def test_no_pr_returns_empty(self):
        from pr_review_agent.nodes.analysis import make_analysis_node
        llm = MagicMock()
        node = make_analysis_node("bug", lambda *a, **kw: ("s", "u"), llm, _make_settings())
        result = await node({"pull_request": None, "findings": [], "errors": []})

        assert result["findings"] == []
        assert result["errors"]

    @pytest.mark.asyncio
    async def test_malformed_json_captured_to_errors(self):
        from pr_review_agent.nodes.analysis import make_analysis_node
        from pr_review_agent.llm.base import LLMResponse
        llm = MagicMock()
        llm.acomplete = AsyncMock(return_value=LLMResponse(content="not json", model="t"))
        node = make_analysis_node("security", lambda *a, **kw: ("s", "u"), llm, _make_settings(retry_attempts=0))
        result = await node({"pull_request": _make_pr(), "findings": [], "errors": []})

        assert result["findings"] == []
        assert result["errors"]


# ---------------------------------------------------------------------------
# synthesis node — deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_overlapping_same_category_deduplicated(self):
        from pr_review_agent.nodes.synthesis import _deduplicate
        f1 = _make_finding(severity="high", line_start=10, line_end=15)
        f2 = _make_finding(severity="medium", line_start=12, line_end=18)
        result = _deduplicate([f1, f2])
        assert len(result) == 1
        assert result[0].severity == "high"

    def test_non_overlapping_both_kept(self):
        from pr_review_agent.nodes.synthesis import _deduplicate
        f1 = _make_finding(line_start=1, line_end=5)
        f2 = _make_finding(line_start=20, line_end=25)
        assert len(_deduplicate([f1, f2])) == 2

    def test_different_files_both_kept(self):
        from pr_review_agent.nodes.synthesis import _deduplicate
        f1 = _make_finding(file="a.py", line_start=10, line_end=15)
        f2 = _make_finding(file="b.py", line_start=10, line_end=15)
        assert len(_deduplicate([f1, f2])) == 2

    def test_different_category_both_kept(self):
        from pr_review_agent.nodes.synthesis import _deduplicate
        f1 = _make_finding(category="bug", line_start=10, line_end=15)
        f2 = _make_finding(category="security", line_start=10, line_end=15)
        assert len(_deduplicate([f1, f2])) == 2


# ---------------------------------------------------------------------------
# synthesis node — full flow
# ---------------------------------------------------------------------------

class TestSynthesisNode:
    def _make_llm(self, critique_content: str, summary_content: str) -> MagicMock:
        from pr_review_agent.llm.base import LLMResponse
        llm = MagicMock()
        llm.acomplete = AsyncMock(side_effect=[
            LLMResponse(content=critique_content, model="t"),
            LLMResponse(content=summary_content, model="t"),
        ])
        return llm

    @pytest.mark.asyncio
    async def test_synthesis_drops_ungrounded_findings(self):
        from pr_review_agent.nodes.synthesis import make_synthesis_node
        finding = _make_finding()
        critique = json.dumps({"results": [{"index": 0, "grounded": False, "reasoning": "not in diff"}]})
        llm = self._make_llm(critique, "Looks good overall.")

        node = make_synthesis_node(llm, _make_settings())
        result = await node({
            "findings": [finding],
            "pull_request": _make_pr(),
            "errors": [],
        })

        assert result["final_findings"] == []

    @pytest.mark.asyncio
    async def test_synthesis_keeps_grounded_findings(self):
        from pr_review_agent.nodes.synthesis import make_synthesis_node
        finding = _make_finding()
        critique = json.dumps({"results": [{"index": 0, "grounded": True, "reasoning": "found it"}]})
        llm = self._make_llm(critique, "One bug found.")

        node = make_synthesis_node(llm, _make_settings())
        result = await node({
            "findings": [finding],
            "pull_request": _make_pr(),
            "errors": [],
        })

        assert len(result["final_findings"]) == 1
        assert result["summary"] == "One bug found."

    @pytest.mark.asyncio
    async def test_synthesis_no_findings_returns_empty(self):
        from pr_review_agent.nodes.synthesis import make_synthesis_node
        from pr_review_agent.llm.base import LLMResponse
        llm = MagicMock()
        llm.acomplete = AsyncMock(return_value=LLMResponse(content="All clear.", model="t"))

        node = make_synthesis_node(llm, _make_settings(enable_self_critique=False))
        result = await node({"findings": [], "pull_request": _make_pr(), "errors": []})

        assert result["final_findings"] == []
        assert "No significant" in result["summary"]


# ---------------------------------------------------------------------------
# analysis node — project context injection
# ---------------------------------------------------------------------------

class TestAnalysisNodeWithContext:
    def _make_llm(self, content: str) -> MagicMock:
        from pr_review_agent.llm.base import LLMResponse
        llm = MagicMock()
        llm.acomplete = AsyncMock(return_value=LLMResponse(content=content, model="test"))
        return llm

    @pytest.mark.asyncio
    async def test_project_context_passed_into_system_prompt(self):
        from pr_review_agent.context.retriever import ProjectContext
        from pr_review_agent.nodes.analysis import make_analysis_node

        captured = {}

        async def fake_acomplete(system, user, **kwargs):
            from pr_review_agent.llm.base import LLMResponse
            captured["system"] = system
            return LLMResponse(content='{"findings": []}', model="test")

        llm = MagicMock()
        llm.acomplete = fake_acomplete

        pc = ProjectContext(global_md="## Conventions\nNever use eval().")

        def build_prompt(title, desc, diff, project_context=""):
            return f"ROLE{project_context}", "USER"

        node = make_analysis_node("security", build_prompt, llm, _make_settings())
        await node({
            "pull_request": _make_pr(),
            "project_context": pc,
            "findings": [],
            "errors": [],
        })

        assert "eval" in captured["system"]

    @pytest.mark.asyncio
    async def test_no_project_context_passes_empty_string(self):
        from pr_review_agent.nodes.analysis import make_analysis_node

        captured = {}

        async def fake_acomplete(system, user, **kwargs):
            from pr_review_agent.llm.base import LLMResponse
            captured["system"] = system
            return LLMResponse(content='{"findings": []}', model="test")

        llm = MagicMock()
        llm.acomplete = fake_acomplete

        def build_prompt(title, desc, diff, project_context=""):
            captured["ctx"] = project_context
            return "ROLE", "USER"

        node = make_analysis_node("bug", build_prompt, llm, _make_settings())
        await node({
            "pull_request": _make_pr(),
            "project_context": None,
            "findings": [],
            "errors": [],
        })

        assert captured["ctx"] == ""
