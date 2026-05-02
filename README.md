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

## Project Context (optional)

Teach the agent about your project so reviews reflect your conventions, architecture, and domain rules.

### Option A — Plain markdown (simple)

Create `.pr-review-context.md` in your repo root (auto-discovered) or pass it explicitly:

```bash
pr-review-agent review <url> --project-context .pr-review-context.md
```

See `examples/sample_project_context.md` for the recommended structure. Include sections like:
- **Overview** — what the service does
- **Conventions** — rules that override generic findings ("we use JWT, don't flag missing session checks")
- **Review Instructions** — explicit priorities ("flag SQL concatenation as critical")

### Option B — Knowledge graph (large projects)

For bigger projects, build a knowledge graph once and get targeted per-pass retrieval (only the relevant slice of context is injected per analysis pass):

```bash
pip install pr-review-agent[context]   # installs graphifyy + networkx
/graphify docs/                        # or: python -m graphify docs/
# produces graphify-out/graph.json
```

Then pass the graph:
```bash
pr-review-agent review <url> --project-context graphify-out/graph.json
```

The agent runs a BFS query on the graph for each analysis pass using category-specific seed terms (e.g. "auth", "token", "permission" for the security pass), injecting only the relevant subgraph — bounded to ~1500 tokens by default.

### Streamlit UI

Upload your `.md` or `graph.json` via the **Project Context** file uploader in the sidebar before running a review.

### Configuration

Set a default path in `config.yaml` so you never need to pass the flag:

```yaml
context:
  path: .pr-review-context.md   # or graphify-out/graph.json
  budget_tokens: 1500           # max tokens injected per pass (lower for small models)
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
| 2 | GitHub fetcher | ✅ Done |
| 3 | LLM providers (OpenAI, Anthropic, Ollama) | ✅ Done |
| 4 | Single analysis node + LangGraph wiring | ✅ Done |
| 5 | All four passes in parallel | ✅ Done |
| 6 | Synthesis + self-critique | ✅ Done |
| 7 | Output formatters + CLI | ✅ Done |
| 8 | Azure DevOps fetcher | ✅ Done |
| 9 | Streamlit UI | ✅ Done |
| 10 | Polish + deploy | ✅ Done |

## License

MIT
