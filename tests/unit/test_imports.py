"""Smoke tests verifying all modules import cleanly."""


def test_fetcher_base_imports():
    from pr_review_agent.fetchers.base import PRFetcher
    from pr_review_agent.fetchers.models import FileDiff, PullRequest
    assert PRFetcher is not None
    assert PullRequest is not None
    assert FileDiff is not None


def test_llm_base_imports():
    from pr_review_agent.llm.base import LLMProvider, LLMResponse
    assert LLMProvider is not None
    assert LLMResponse is not None


def test_output_models_imports():
    from pr_review_agent.output.models import Finding, Review
    assert Finding is not None
    assert Review is not None


def test_core_imports():
    from pr_review_agent.core.state import ReviewState
    from pr_review_agent.core.settings import Settings
    assert ReviewState is not None
    assert Settings is not None


def test_factories_import():
    from pr_review_agent.fetchers.factory import get_fetcher
    from pr_review_agent.llm.factory import get_llm
    assert get_fetcher is not None
    assert get_llm is not None


def test_factory_raises_for_unknown_provider():
    import pytest
    from pr_review_agent.fetchers.factory import get_fetcher
    from pr_review_agent.llm.factory import get_llm

    with pytest.raises(ValueError, match="Unknown provider"):
        get_fetcher("nonexistent", object())

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm("nonexistent", object())
