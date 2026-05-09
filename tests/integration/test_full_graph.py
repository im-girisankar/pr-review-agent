"""
Integration tests for the full LangGraph review pipeline.

Marked @pytest.mark.integration — skipped in CI unless API keys are present.
Run manually with: pytest tests/integration/ -m integration
"""
import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_graph_with_mock_providers():
    """
    Runs the complete graph end-to-end using mock fetcher and LLM.
    Verifies that state flows correctly through all nodes.
    """
    import json
    from unittest.mock import AsyncMock, MagicMock

    from pr_review_agent.core.graph import build_graph
    from pr_review_agent.core.settings import Settings
    from pr_review_agent.fetchers.models import FileDiff, PullRequest
    from pr_review_agent.llm.base import LLMResponse
    from pr_review_agent.nodes.output import state_to_review

    # --- Mock fetcher ---
    pr = PullRequest(
        id="1", title="Fix auth bug", description="Fixes a critical auth bypass",
        author="dev", source_branch="fix/auth", target_branch="main",
        provider="github", url="https://github.com/example/repo/pull/1",
        files=[
            FileDiff(
                path="src/auth.py", status="modified",
                additions=3, deletions=2,
                diff_text="@@ -10,4 +10,5 @@\n-    if user == admin:\n+    if user.role == 'admin':\n",
                language="python",
            )
        ],
    )
    fetcher = MagicMock()
    fetcher.fetch_pr.return_value = pr

    # --- Mock LLM — returns valid JSON for analysis passes, then critique, then summary ---
    analysis_response = json.dumps({"findings": [
        {
            "category": "bug", "severity": "high",
            "file": "src/auth.py", "line_start": 10, "line_end": 11,
            "title": "String comparison for role check",
            "description": "Direct string comparison is fragile.",
            "suggestion": "Use an enum or constant.",
        }
    ]})
    critique_response = json.dumps({
        "results": [{"index": 0, "grounded": True, "reasoning": "visible in diff"}]
    })
    summary_response = "One high severity bug found. Request changes."

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First 4 calls = analysis passes; 5th = self-critique; 6th = summary
        if call_count <= 4:
            return LLMResponse(content=analysis_response, model="mock")
        if call_count == 5:
            return LLMResponse(content=critique_response, model="mock")
        return LLMResponse(content=summary_response, model="mock")

    llm = MagicMock()
    llm.acomplete = AsyncMock(side_effect=side_effect)

    settings = Settings.model_construct(
        temperature=0.2, max_tokens=2000, retry_attempts=1,
        parallel=True, enable_self_critique=True,
        github_pat="", azure_org="", azure_pat="",
        openai_api_key="", anthropic_api_key="",
        ollama_base_url="http://localhost:11434",
        default_provider="github", default_llm="ollama",
        default_model="llama3.1:8b",
        max_diff_size_kb=500, default_format="markdown",
    )

    graph = build_graph(fetcher, llm, settings)

    initial_state = {
        "pr_url": "https://github.com/example/repo/pull/1",
        "provider": "github",
        "pull_request": None,
        "findings": [],
        "final_findings": None,
        "summary": None,
        "errors": [],
    }

    result = await graph.ainvoke(initial_state)
    review = state_to_review(result)

    assert review.pr_url == "https://github.com/example/repo/pull/1"
    assert len(review.findings) >= 1
    assert review.summary
    assert not review.errors
