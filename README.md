# PR Review Agent

> Multi-pass code review agent. Swappable PR sources (GitHub, Azure DevOps). Swappable LLM backends (OpenAI, Anthropic, Ollama). Built on LangGraph.

## Features

- 4 parallel analysis passes (bug, security, performance, test coverage)
- Self-critique step that grounds findings in the actual diff
- Works with GitHub and Azure DevOps PRs
- Works with cloud LLMs (OpenAI, Anthropic) or local models via Ollama
- CLI, Streamlit UI, and Python API

## Quickstart (local with Ollama)

```bash
cp .env.example .env
# edit .env with your GitHub PAT
uv run pr-review-agent review https://github.com/owner/repo/pull/123 --llm ollama
```

## Quickstart (cloud LLM)

```bash
cp .env.example .env
# edit .env with your API keys
uv run pr-review-agent review https://github.com/owner/repo/pull/123 --llm openai
```

## Architecture

See [project plan](docs/plan.md) for full architecture details.
