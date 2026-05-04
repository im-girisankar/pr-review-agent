from langgraph.graph import END, START, StateGraph

from pr_review_agent.core.settings import Settings
from pr_review_agent.core.state import ReviewState
from pr_review_agent.fetchers.base import PRFetcher
from pr_review_agent.llm.base import LLMProvider
from pr_review_agent.llm.prompts import bug_detection, performance, security, test_coverage
from pr_review_agent.nodes.analysis import make_analysis_node
from pr_review_agent.nodes.fetch import make_fetch_node
from pr_review_agent.nodes.file_analysis import make_file_analysis_node
from pr_review_agent.nodes.synthesis import make_synthesis_node

_ANALYSIS_PASSES = [
    ("bug_detection", bug_detection.build_prompt),
    ("security", security.build_prompt),
    ("performance", performance.build_prompt),
    ("test_coverage", test_coverage.build_prompt),
]


def build_graph(fetcher: PRFetcher, llm: LLMProvider, settings: Settings):
    """Build and compile the LangGraph review graph."""
    graph = StateGraph(ReviewState)

    graph.add_node("fetch", make_fetch_node(fetcher))
    graph.add_node("synthesis", make_synthesis_node(llm, settings))

    if settings.analysis_mode == "chunked":
        # One unified LLM call per file — fits any model size.
        graph.add_node("analyze", make_file_analysis_node(llm, settings))
        graph.add_edge(START, "fetch")
        graph.add_edge("fetch", "analyze")
        graph.add_edge("analyze", "synthesis")
    else:
        # Full mode: 4 category passes on the whole diff. Needs large context window.
        for name, prompt_fn in _ANALYSIS_PASSES:
            graph.add_node(name, make_analysis_node(name, prompt_fn, llm, settings))

        graph.add_edge(START, "fetch")

        pass_names = [name for name, _ in _ANALYSIS_PASSES]
        if settings.parallel:
            for name in pass_names:
                graph.add_edge("fetch", name)
                graph.add_edge(name, "synthesis")
        else:
            graph.add_edge("fetch", pass_names[0])
            for a, b in zip(pass_names, pass_names[1:]):
                graph.add_edge(a, b)
            graph.add_edge(pass_names[-1], "synthesis")

    graph.add_edge("synthesis", END)

    return graph.compile()
