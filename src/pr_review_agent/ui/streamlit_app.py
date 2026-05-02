import asyncio

import streamlit as st

from pr_review_agent.core.graph import build_graph
from pr_review_agent.core.settings import Settings
from pr_review_agent.fetchers.factory import get_fetcher
from pr_review_agent.llm.factory import get_llm
from pr_review_agent.nodes.output import state_to_review
from pr_review_agent.output.json_formatter import to_json
from pr_review_agent.output.markdown_formatter import to_markdown

_SEVERITY_COLOR = {
    "critical": "#ff4b4b",
    "high": "#ff8c00",
    "medium": "#ffd700",
    "low": "#4b9fff",
    "informational": "#a0a0a0",
}


def _run_review(url, provider, llm_provider, model, pat):
    settings = Settings.from_yaml()
    if pat:
        if provider == "github":
            settings.github_pat = pat
        else:
            settings.azure_pat = pat

    fetcher = get_fetcher(provider, settings)
    llm = get_llm(llm_provider, settings, model_override=model or None)
    graph = build_graph(fetcher, llm, settings)

    initial_state = {
        "pr_url": url,
        "provider": provider,
        "pull_request": None,
        "findings": [],
        "final_findings": None,
        "summary": None,
        "errors": [],
    }
    return asyncio.run(graph.ainvoke(initial_state))


def main():
    st.set_page_config(page_title="PR Review Agent", page_icon="🔍", layout="wide")
    st.title("🔍 PR Review Agent")
    st.caption("Multi-pass agentic code review · GitHub & Azure DevOps · OpenAI, Anthropic, Ollama")

    with st.sidebar:
        st.header("Configuration")
        provider = st.selectbox("PR Source", ["github", "azure_devops"])
        llm_provider = st.selectbox("LLM Backend", ["groq", "ollama", "openai", "anthropic"])
        model = st.text_input(
            "Model",
            placeholder="llama3.1:8b / gpt-4o / claude-sonnet-4-6",
        )
        pat = st.text_input(
            "Personal Access Token",
            type="password",
            help="Your PAT is used only for this session and never stored.",
        )
        st.divider()
        st.caption("Run locally for free with [Ollama](https://ollama.ai)")

    url = st.text_input(
        "Pull Request URL",
        placeholder="https://github.com/owner/repo/pull/123",
    )

    if st.button("🚀 Review PR", type="primary", disabled=not url):
        with st.spinner("Fetching PR and running analysis passes..."):
            try:
                result = _run_review(url, provider, llm_provider, model, pat)
                review = state_to_review(result)
            except Exception as exc:
                st.error(f"Error: {exc}")
                return

        # Summary
        st.subheader("Summary")
        st.info(review.summary or "No summary available.")

        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Findings", len(review.findings))
        critical_high = sum(1 for f in review.findings if f.severity in ("critical", "high"))
        col2.metric("Critical / High", critical_high)
        col3.metric("Files Affected", len({f.file for f in review.findings}))

        # Findings
        if review.findings:
            st.subheader(f"Findings ({len(review.findings)})")
            for i, finding in enumerate(review.findings, 1):
                color = _SEVERITY_COLOR.get(finding.severity, "#a0a0a0")
                with st.expander(
                    f"{i}. [{finding.severity.upper()}] {finding.title} — `{finding.file}`"
                ):
                    st.markdown(
                        f"<span style='color:{color}; font-weight:bold'>"
                        f"{finding.severity.upper()}</span> · "
                        f"**{finding.category.replace('_', ' ').title()}** · "
                        f"`{finding.file}` lines {finding.line_start}–{finding.line_end}",
                        unsafe_allow_html=True,
                    )
                    st.write(finding.description)
                    if finding.suggestion:
                        st.success(f"**Suggestion:** {finding.suggestion}")
        else:
            st.success("No issues found. ✅")

        # Errors
        if review.errors:
            st.subheader("Errors")
            for err in review.errors:
                st.warning(err)

        # Downloads
        st.divider()
        dl_col1, dl_col2 = st.columns(2)
        dl_col1.download_button(
            "⬇️ Download Markdown",
            data=to_markdown(review),
            file_name="review.md",
            mime="text/markdown",
        )
        dl_col2.download_button(
            "⬇️ Download JSON",
            data=to_json(review),
            file_name="review.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
