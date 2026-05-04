import asyncio
import tempfile
from pathlib import Path

import streamlit as st

from pr_review_agent.context import load_project_context
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

# Order matters: drives progress bar layout.
# Chunked mode uses "analyze"; full mode uses the 4 category nodes.
_NODE_LABELS_CHUNKED = {
    "fetch": "Fetch PR",
    "analyze": "Analyze files",
    "synthesis": "Synthesis",
}
_NODE_LABELS_FULL = {
    "fetch": "Fetch PR",
    "bug_detection": "Bug detection",
    "security": "Security",
    "performance": "Performance",
    "test_coverage": "Test coverage",
    "synthesis": "Synthesis",
}
_ANALYSIS_NODES_CHUNKED = ("analyze",)
_ANALYSIS_NODES_FULL = ("bug_detection", "security", "performance", "test_coverage")

_OLLAMA_MODELS = [
    "qwen3-coder-next:cloud",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "llama3.1:8b",
    "(custom)",
]

_MODEL_DEFAULTS = {
    "ollama": "qwen3-coder-next:cloud",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-5",
}


# ---------------------------------------------------------------------------
# Pipeline driver
# ---------------------------------------------------------------------------


async def _run_with_progress(graph, initial_state, progress_widgets, node_labels, analysis_nodes):
    """
    Drive the graph via astream and update progress bars in real time.

    Each yielded chunk is `{node_name: state_update}`. We mark that bar
    "done" and accumulate the update into our local copy so the final
    state has every node's contribution merged with the right reducers.
    """
    accumulated = dict(initial_state)
    fetch_seen = False
    analysis_done: set[str] = set()

    async for chunk in graph.astream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            # Apply state update with reducer-aware merging.
            for k, v in update.items():
                if isinstance(v, list) and isinstance(accumulated.get(k), list):
                    accumulated[k] = accumulated[k] + v
                else:
                    accumulated[k] = v

            # Update progress.
            label = node_labels.get(node_name, node_name)
            ph = progress_widgets.get(node_name)
            if ph is not None:
                ph.progress(1.0, text=f"✓ {label}")

            if node_name == "fetch":
                fetch_seen = True
                for n in analysis_nodes:
                    if n not in analysis_done:
                        w = progress_widgets.get(n)
                        if w is not None:
                            w.progress(0.5, text=f"⏳ {node_labels[n]} (running…)")
            elif node_name in analysis_nodes:
                analysis_done.add(node_name)
                if fetch_seen and len(analysis_done) == len(analysis_nodes):
                    w = progress_widgets.get("synthesis")
                    if w is not None:
                        w.progress(0.5, text=f"⏳ {node_labels['synthesis']} (running…)")

    return accumulated


def _build_graph_for_run(provider, llm_provider, model, pat, context_path):
    settings = Settings.from_yaml()
    if pat:
        if provider == "github":
            settings.github_pat = pat
        else:
            settings.azure_pat = pat
    pc = load_project_context(context_path)
    fetcher = get_fetcher(provider, settings)
    llm = get_llm(llm_provider, settings, model_override=model or None)
    return build_graph(fetcher, llm, settings), pc, settings.analysis_mode


def _fresh_initial_state(url, provider, pc):
    return {
        "pr_url": url,
        "provider": provider,
        "project_context": pc,
        "pull_request": None,
        "findings": [],
        "final_findings": None,
        "summary": None,
        "errors": [],
        "completed_passes": [],
        "failed_passes": [],
    }


def _resume_initial_state(partial, pc):
    """Reuse a halted run's state, clearing failed_passes so retried passes can populate them again."""
    return {
        "pr_url": partial["pr_url"],
        "provider": partial["provider"],
        "project_context": pc,
        "pull_request": partial.get("pull_request"),
        "findings": list(partial.get("findings") or []),
        "final_findings": None,
        "summary": None,
        "errors": list(partial.get("errors") or []),
        "completed_passes": list(partial.get("completed_passes") or []),
        "failed_passes": [],
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render_progress_widgets(node_labels: dict) -> dict:
    """Build a status container with one progress bar per pipeline node."""
    container = st.container()
    with container:
        widgets = {}
        for node, label in node_labels.items():
            ph = st.empty()
            ph.progress(0, text=f"⏳ {label}")
            widgets[node] = ph
    return widgets


def _render_failure_ui(state):
    failed = state.get("failed_passes") or []
    completed = state.get("completed_passes") or []

    st.error(
        f"Run halted — {len(failed)} pass(es) failed. "
        f"{len(completed)} pass(es) succeeded and their findings are preserved."
    )

    st.markdown(f"**PR:** `{state.get('pr_url', '?')}`")

    if completed:
        st.markdown("**Completed:** " + ", ".join(f"`{c}`" for c in completed))

    for i, fail in enumerate(failed, 1):
        with st.expander(
            f"❌ {i}. {fail.get('category', '?')} — {fail.get('kind', 'error')}",
            expanded=(i == 1),
        ):
            st.markdown(f"**Error:** {fail.get('error', '')}")
            if fail.get("model"):
                st.caption(f"Model: {fail['model']}")
            preview = fail.get("response_preview")
            if preview:
                st.markdown("**Last LLM response (first 500 chars):**")
                st.code(preview, language="text")
            else:
                st.caption("No response was received from the LLM.")


def _render_results(review):
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


# ---------------------------------------------------------------------------
# Run dispatcher
# ---------------------------------------------------------------------------


def _execute_run(initial_state, run_args):
    """Build the graph, drive it through the streaming progress UI, and store the result."""
    provider, llm_provider, model, pat, context_path = run_args
    try:
        graph, _, analysis_mode = _build_graph_for_run(provider, llm_provider, model, pat, context_path)
    except Exception as exc:
        st.error(f"Failed to build pipeline: {exc}")
        return

    node_labels = _NODE_LABELS_CHUNKED if analysis_mode == "chunked" else _NODE_LABELS_FULL
    analysis_nodes = _ANALYSIS_NODES_CHUNKED if analysis_mode == "chunked" else _ANALYSIS_NODES_FULL

    with st.status("Running review", expanded=True) as status:
        widgets = _render_progress_widgets(node_labels)
        try:
            final = asyncio.run(_run_with_progress(graph, initial_state, widgets, node_labels, analysis_nodes))
        except Exception as exc:
            status.update(label=f"Pipeline crashed: {exc}", state="error")
            st.error(f"Pipeline crashed: {exc}")
            return

        if final.get("failed_passes"):
            status.update(label="Run halted — see failure details below", state="error")
            st.session_state["partial_state"] = final
            st.session_state["run_args"] = run_args
            st.session_state.pop("completed_review", None)
        else:
            status.update(label="Review complete", state="complete")
            st.session_state["completed_review"] = state_to_review(final)
            st.session_state.pop("partial_state", None)
            st.session_state.pop("run_args", None)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(page_title="PR Review Agent", page_icon="🔍", layout="wide")
    st.title("🔍 PR Review Agent")
    st.caption("Multi-pass agentic code review · GitHub & Azure DevOps · OpenAI, Anthropic, Groq, Ollama")

    with st.sidebar:
        st.header("Configuration")
        provider = st.selectbox("PR Source", ["github", "azure_devops"])
        llm_provider = st.selectbox("LLM Backend", ["groq", "ollama", "openai", "anthropic"])

        if llm_provider == "ollama":
            selected = st.selectbox("Ollama model", _OLLAMA_MODELS)
            if selected == "(custom)":
                model = st.text_input(
                    "Custom model name",
                    placeholder="e.g. mistral:7b",
                )
            else:
                model = selected
        else:
            model = st.text_input(
                "Model",
                value=_MODEL_DEFAULTS.get(llm_provider, ""),
                placeholder="gpt-4o / claude-sonnet-4-5",
            )

        pat = st.text_input(
            "Personal Access Token",
            type="password",
            help="Your PAT is used only for this session and never stored.",
        )
        st.divider()
        st.subheader("Project Context (optional)")
        ctx_file = st.file_uploader(
            "Upload .md or graph.json",
            type=["md", "json"],
            help="Provide project conventions and instructions to guide the review. "
                 "Use a graphify graph.json for large projects.",
        )
        if ctx_file:
            st.caption(f"Loaded: {ctx_file.name} ({ctx_file.size:,} bytes)")
        st.divider()
        st.caption("Run locally for free with [Ollama](https://ollama.ai)")

    has_partial = "partial_state" in st.session_state

    if has_partial:
        partial = st.session_state["partial_state"]
        st.warning(
            f"⚠️ Previous run halted. Resume to retry only the failed pass(es), "
            f"or discard to start fresh."
        )
        col_a, col_b = st.columns([1, 1])
        if col_a.button("🔁 Resume failed passes", type="primary"):
            run_args = st.session_state["run_args"]
            _, _, _, _, context_path = run_args
            _, pc, _ = _build_graph_for_run(*run_args)
            _execute_run(_resume_initial_state(partial, pc), run_args)
            st.rerun()
        if col_b.button("🗑️ Discard halted run"):
            st.session_state.pop("partial_state", None)
            st.session_state.pop("run_args", None)
            st.rerun()
        st.divider()
        _render_failure_ui(partial)

    else:
        url = st.text_input(
            "Pull Request URL",
            placeholder="https://github.com/owner/repo/pull/123",
        )

        if st.button("🚀 Review PR", type="primary", disabled=not url):
            context_path = None
            if ctx_file:
                suffix = Path(ctx_file.name).suffix
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(ctx_file.getvalue())
                tmp.flush()
                context_path = Path(tmp.name)

            run_args = (provider, llm_provider, model, pat, context_path)
            try:
                _, pc, _ = _build_graph_for_run(*run_args)
            except Exception as exc:
                st.error(f"Failed to load configuration: {exc}")
                return

            _execute_run(_fresh_initial_state(url, provider, pc), run_args)
            st.rerun()

        if "completed_review" in st.session_state:
            _render_results(st.session_state["completed_review"])


if __name__ == "__main__":
    main()
