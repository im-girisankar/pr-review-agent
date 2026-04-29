# PR Review Agent

> Multi-pass agentic code review system built on LangGraph. Swappable PR sources (GitHub, Azure DevOps) and swappable LLM backends (OpenAI, Anthropic, Ollama).

---

## Why

Automated code review tools typically make a single LLM call and return whatever comes back. This project runs **four focused analysis passes in parallel** (bug detection, security, performance, test coverage), then applies a **self-critique step** that drops any finding not grounded in the actual diff. The result is a structured, ranked review with far fewer hallucinations than a single-pass approach.

## Features

- **4 parallel analysis passes** — bug, security, performance, test coverage
- **Self-critique synthesis** — each finding is verified against the diff before reporting
- **Swappable PR sources** — GitHub and Azure DevOps; adding GitLab is one new file
- **Swappable LLM backends** — OpenAI, Anthropic, or local models via Ollama (no API key required)
- **Structured output** — JSON and GitHub-comment-ready Markdown
- **CLI + Streamlit UI** — run from terminal or demo in a browser

## Architecture

```
PR URL
  │
  ▼
PRFetcher (GitHub / Azure DevOps)
  │
  ▼
LangGraph Orchestrator
  ├── Bug Detection ──┐
  ├── Security ───────┤  (parallel)
  ├── Performance ────┤
  └── Test Coverage ──┘
              │
              ▼
      Synthesis + Self-Critique
              │
              ▼
      JSON / Markdown Output
```

LangGraph is used for explicit state management and native parallel execution. The `Annotated[list[Finding], add]` reducer on the shared state lets all four passes write findings concurrently without conflicts.

## Tech Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph |
| LLM SDKs | OpenAI, Anthropic, Ollama Python clients |
| PR Sources | PyGithub, requests (Azure DevOps) |
| UI | Streamlit |
| Config | pydantic-settings + .env |
| Testing | pytest + pytest-asyncio + responses |
| Packaging | uv |

## Quickstart (local with Ollama — no API key needed)

```bash
# 1. Clone and install
git clone https://github.com/im-girisankar/pr-review-agent
cd pr-review-agent
uv sync

# 2. Configure
cp .env.example .env
# Add your GITHUB_PAT to .env

# 3. Pull a model and run
ollama pull llama3.1:8b
uv run pr-review-agent review https://github.com/owner/repo/pull/123 --llm ollama
```

## Quickstart (OpenAI / Anthropic)

```bash
cp .env.example .env
# Add OPENAI_API_KEY or ANTHROPIC_API_KEY to .env

uv run pr-review-agent review https://github.com/owner/repo/pull/123 --llm openai --model gpt-4o
```

## CLI Reference

```
pr-review-agent review <url>
  --provider   github | azure_devops     (default: github)
  --llm        openai | anthropic | ollama  (default: ollama)
  --model      gpt-4o | claude-sonnet-4 | llama3.1:8b
  --output     json | markdown           (default: markdown)
```

## Configuration

Copy `.env.example` to `.env` and fill in the relevant keys. Non-secret defaults live in `config.yaml`:

```yaml
analysis:
  parallel: true          # set false to debug pass-by-pass
  max_diff_size_kb: 500

llm:
  temperature: 0.2
  max_tokens: 2000

synthesis:
  enable_self_critique: true
```

## Project Structure

```
src/pr_review_agent/
├── core/          # LangGraph state, graph wiring, settings
├── fetchers/      # PRFetcher ABC + GitHub + Azure DevOps implementations
├── llm/           # LLMProvider ABC + OpenAI, Anthropic, Ollama implementations
├── nodes/         # LangGraph node functions (fetch, analysis, synthesis, output)
├── output/        # Finding/Review models, JSON + Markdown formatters
└── ui/            # Streamlit app + Click CLI
```

## Adding a New PR Provider

Create one file — `src/pr_review_agent/fetchers/gitlab.py` — implementing the `PRFetcher` ABC, then add a case to `fetchers/factory.py`. Zero changes anywhere else.

## Adding a New LLM Provider

Same pattern — one file in `src/pr_review_agent/llm/`, one case in `llm/factory.py`.

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Project skeleton + abstractions | ✅ Done |
| 2 | GitHub fetcher | 🔄 In progress |
| 3 | LLM providers (OpenAI, Anthropic, Ollama) | ⏳ Planned |
| 4 | Single analysis node + LangGraph wiring | ⏳ Planned |
| 5 | All four passes in parallel | ⏳ Planned |
| 6 | Synthesis + self-critique | ⏳ Planned |
| 7 | Output formatters + CLI | ⏳ Planned |
| 8 | Azure DevOps fetcher | ⏳ Planned |
| 9 | Streamlit UI | ⏳ Planned |
| 10 | Polish + deploy | ⏳ Planned |

## License

MIT
