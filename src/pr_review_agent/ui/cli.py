import asyncio
import io
import sys

import click
import structlog

# Ensure stdout is UTF-8 on Windows (default cp1252 breaks emoji in markdown output)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

# Send structured logs to stderr so they don't pollute piped/redirected output
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

from pr_review_agent.core.graph import build_graph
from pr_review_agent.core.settings import Settings
from pr_review_agent.fetchers.factory import get_fetcher
from pr_review_agent.llm.factory import get_llm
from pr_review_agent.nodes.output import state_to_review
from pr_review_agent.output.json_formatter import to_json
from pr_review_agent.output.markdown_formatter import to_markdown

log = structlog.get_logger(__name__)


async def _run(
    url: str,
    provider: str,
    llm_provider: str,
    model: str | None,
    output_format: str,
    pat: str | None,
) -> str:
    settings = Settings.from_yaml()
    if pat:
        if provider == "github":
            settings.github_pat = pat
        elif provider == "azure_devops":
            settings.azure_pat = pat

    fetcher = get_fetcher(provider, settings)
    llm = get_llm(llm_provider, settings, model_override=model)
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

    result = await graph.ainvoke(initial_state)
    review = state_to_review(result)

    return to_json(review) if output_format == "json" else to_markdown(review)


@click.group()
def main() -> None:
    """PR Review Agent — multi-pass agentic code review."""


@main.command()
@click.argument("url")
@click.option(
    "--provider",
    default="github",
    show_default=True,
    type=click.Choice(["github", "azure_devops"]),
    help="PR source provider.",
)
@click.option(
    "--llm",
    "llm_provider",
    default="ollama",
    show_default=True,
    type=click.Choice(["openai", "anthropic", "groq", "ollama"]),
    help="LLM backend.",
)
@click.option("--model", default=None, help="Model name (overrides config default).")
@click.option(
    "--output",
    "output_format",
    default="markdown",
    show_default=True,
    type=click.Choice(["json", "markdown"]),
    help="Output format.",
)
@click.option("--pat", default=None, help="Personal access token (overrides env var).")
def review(
    url: str,
    provider: str,
    llm_provider: str,
    model: str | None,
    output_format: str,
    pat: str | None,
) -> None:
    """Review a pull request at URL."""
    try:
        output = asyncio.run(_run(url, provider, llm_provider, model, output_format, pat))
        click.echo(output)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
