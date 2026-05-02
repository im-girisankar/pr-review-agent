# Feature Plan: Project-Context Loader for pr-review-agent

> **Hand-off doc.** Built for an executor agent (Claude Sonnet) to implement step-by-step. Each task is a checklist item with file paths, signatures, and acceptance criteria. Work top-to-bottom; do not skip ahead.

---

## 1. Context (Why)

The agent reviews PRs with **no project-specific knowledge**. Reviews can't honor in-house conventions, domain rules, or architecture facts (e.g. "auth handled by service X, don't flag missing checks"). Users want a one-time `.md` describing the project + custom review instructions, consumed by every analysis pass.

Pasting the full `.md` into all 6 LLM calls (4 analysis + critique + summary) wastes tokens. On **Ollama mid models** (qwen2.5-coder 7B class, 32K-128K ctx) reviewing **bigger PRs**, we can't afford to. We compress context with a **knowledge graph (graphify-style)** and retrieve only the slice relevant to each pass.

**Diff-side compression** (chunking huge PRs across files) is a bigger architectural change — deferred to **Phase 2**.

### Decisions (locked)
- **Phase 1 only**: project context with graph retrieval + caching-friendly prompts
- **Phase 2 deferred**: diff chunking + map-reduce + per-chunk retrieval (sketched, not built)
- Worst-case target: Ollama mid (qwen2.5-coder 7B, 32K-128K ctx)
- Inputs: CLI `--project-context PATH` **and** Streamlit upload
- Apply to **all 6 passes** (4 analysis + critique + summary)
- Code changes in this repo only — **no PR comment-posting** (separate future feature)
- Soft cap: ~1500 tokens of retrieved context per pass; warn when raw .md > ~10KB
- Optional dependency: `graphifyy` + `networkx` under extras `[context]` — no graph means raw-`.md` fallback

---

## 2. Architecture

```
                                    ┌─────────────────────────────┐
                                    │ ProjectContext              │
                                    │  graph: nx.Graph | None     │
                                    │  global_md: str | None      │
 .pr-review-context.md  ──┐         │  retrieve(category) -> str  │
                          ├──load──►│                             │
 graphify-out/graph.json ─┘         └──────────────┬──────────────┘
                                                   │
        Settings ──► CLI/_run() ──► state["project_context"] ──► all nodes
                                                                   │
                              ┌───────────────────┬────────────────┴─────────────┐
                              ▼                   ▼                              ▼
                  build_prompt(...,      build_critique_prompt(...,    build_summary_prompt(...,
                  project_context)       project_context)              project_context)
```

### Retrieval algorithm (per pass)
1. **No graph, only raw .md** → return verbatim, truncated at budget. Fine for frontier models.
2. **Graphify `graph.json` loaded** →
   - Look up the pass's seed terms (static map below).
   - Score nodes by label/description term overlap; pick top-K seeds (default 3).
   - BFS depth=2 from seeds; collect labels + edge relations.
   - Render compact text:
     ```
     ## Project Context (from knowledge graph)
     - <Node Label> [<file_type>]: <brief>
       --<relation>--> <Neighbor Label>
       ...
     ```
   - Hard-cap at per-pass token budget; truncate with `... (truncated)`.

### Seed-term map (in `retriever.py`)
```python
SEED_TERMS = {
    "bug_detection":      ["bug", "null", "exception", "race", "leak", "boundary", "validation"],
    "security":           ["auth", "crypto", "input", "injection", "secret", "permission", "token"],
    "performance":        ["latency", "throughput", "cache", "query", "loop", "memory", "io"],
    "test_coverage":      ["test", "coverage", "fixture", "mock", "assert", "spec"],
    "synthesis_critique": ["correctness", "evidence", "diff", "scope"],
    "synthesis_summary":  ["overview", "architecture", "module", "feature", "release"],
}
```

### Prompt-injection point
Inject inside the **system** prompt right after the role declaration (split current `_SYSTEM` into `_SYSTEM_HEAD` + `_SYSTEM_TAIL`, slot context between). Stable prefix → variable suffix layout maximises Anthropic prompt-cache hits and Ollama prefix-cache hits.

```python
ctx_block = (
    f"\n<project_context>\n{project_context.strip()}\n</project_context>\n"
    if project_context.strip() else ""
)
system = _SYSTEM_HEAD + ctx_block + _SYSTEM_TAIL
```

---

## 3. Implementation Checklist

### 3.1 Module scaffolding

- [ ] Create `src/pr_review_agent/context/__init__.py`
  - Export `ProjectContext`, `load_project_context`
- [ ] Create `src/pr_review_agent/context/loader.py`
  - `def load_project_context(path: Path | None, *, cwd: Path | None = None) -> ProjectContext | None:`
  - If `path is None`, auto-discover (in this order, in `cwd or Path.cwd()`):
    1. `.pr-review-context.md`
    2. `graphify-out/graph.json`
    3. Both, if both exist → return `ProjectContext(global_md=..., graph=...)`
  - If `path.suffix == ".json"` → load NetworkX node-link graph via `networkx.readwrite.json_graph.node_link_graph(json.loads(path.read_text()), edges="links")`
  - If `path.suffix == ".md"` → read text, store as `global_md`. Also auto-load sibling `graphify-out/graph.json` if present.
  - Return `None` if nothing found (silent — feature is opt-in).
  - Soft warn (`structlog`) if raw `global_md` > 10_000 chars.
- [ ] Create `src/pr_review_agent/context/retriever.py`
  - `@dataclass class ProjectContext:` with fields `graph: "nx.Graph | None" = None`, `global_md: str | None = None`
  - `def retrieve(self, category: str, budget_tokens: int = 1500) -> str:`
    - If `self.graph` is not None → graph-retrieval branch (BFS algorithm above)
    - Else if `self.global_md` → return `_truncate(self.global_md, budget_tokens)`
    - Else → return `""`
  - `def _truncate(text: str, budget_tokens: int) -> str:` — char-budget = `budget_tokens * 4`; on truncate append `\n... (truncated)`
  - Constant `SEED_TERMS` dict (see § 2)
- [ ] Create `tests/unit/test_context_retriever.py`
  - Fixture: small NetworkX graph (~10 nodes, ~15 edges) covering all 4 analysis-pass categories
  - Test: `retrieve("security")` returns text containing security-tagged nodes, not bug-only nodes
  - Test: budget-truncation kicks in when fixture exceeds budget
  - Test: `ProjectContext()` (no graph, no md) → `retrieve(...)` returns `""`
  - Test: raw-`.md` fallback works when graph is None

### 3.2 State, settings, config

- [ ] Edit `src/pr_review_agent/core/state.py`
  - Add field: `project_context: "ProjectContext | None"` (string-quoted forward ref, no import to avoid cycle)
- [ ] Edit `src/pr_review_agent/core/settings.py`
  - Add fields:
    ```python
    project_context_path: Path | None = None
    context_budget_tokens: int = 1500
    ```
  - In `from_yaml`, read `cfg.get("context", {}).get("path")` and `cfg.get("context", {}).get("budget_tokens", 1500)`
- [ ] Edit `config.yaml` — append (commented):
  ```yaml
  context:
    # path: .pr-review-context.md   # or graphify-out/graph.json
    budget_tokens: 1500
  ```
- [ ] Edit `pyproject.toml` — add optional deps:
  ```toml
  [project.optional-dependencies]
  context = ["graphifyy>=0.3.0", "networkx>=3.0"]
  ```
  Keep `networkx` as a soft import inside `loader.py` so missing dep doesn't crash; raise a clear error only when the user actually points to a `.json` graph.

### 3.3 Prompt builders

For **each** of these files, do the same edit pattern:

- [ ] `src/pr_review_agent/llm/prompts/bug_detection.py`
- [ ] `src/pr_review_agent/llm/prompts/security.py`
- [ ] `src/pr_review_agent/llm/prompts/performance.py`
- [ ] `src/pr_review_agent/llm/prompts/test_coverage.py`

Edit pattern:
1. Split current `_SYSTEM` string into `_SYSTEM_HEAD` (the role declaration line) and `_SYSTEM_TAIL` (the rest).
2. Update signature:
   ```python
   def build_prompt(
       title: str,
       description: str,
       diff: str,
       project_context: str = "",
   ) -> tuple[str, str]:
       ctx_block = (
           f"\n<project_context>\n{project_context.strip()}\n</project_context>\n"
           if project_context.strip() else ""
       )
       system = _SYSTEM_HEAD + ctx_block + _SYSTEM_TAIL
       return system, _USER_TEMPLATE.format(...)
   ```

For synthesis prompts:
- [ ] `src/pr_review_agent/llm/prompts/synthesis.py`
  - Split both `_CRITIQUE_SYSTEM` and `_SUMMARY_SYSTEM` into HEAD/TAIL
  - Add `project_context: str = ""` kwarg to **both** `build_critique_prompt` and `build_summary_prompt`
  - Inject `<project_context>` block in both system strings

### 3.4 Nodes

- [ ] Edit `src/pr_review_agent/nodes/analysis.py`
  - Inside `make_analysis_node`'s inner `node(state)` (around current line 60), before `build_prompt(...)`:
    ```python
    ctx = state.get("project_context")
    project_context = ctx.retrieve(category, settings.context_budget_tokens) if ctx else ""
    system, user = build_prompt(pr.title, pr.description, diff, project_context=project_context)
    ```
  - Add comment near `format_diff` (line 18):
    ```python
    # Phase 2: chunk per-file here and run map-reduce so big PRs fit on small models.
    ```
- [ ] Edit `src/pr_review_agent/nodes/synthesis.py`
  - In `_self_critique`: retrieve with `"synthesis_critique"` before `build_critique_prompt(...)`
  - In `_generate_summary`: retrieve with `"synthesis_summary"` before `build_summary_prompt(...)`
  - Both need access to `state` — thread it through if necessary (current code likely already has it, verify when reading)

### 3.5 Entry points

- [ ] Edit `src/pr_review_agent/ui/cli.py`
  - Add Click option:
    ```python
    @click.option(
        "--project-context",
        "project_context_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        default=None,
        help="Path to project context .md file or graphify-out/graph.json.",
    )
    ```
  - Thread `project_context_path` through `review(...)` → `_run(...)`
  - In `_run`: `pc = load_project_context(project_context_path or settings.project_context_path)`
  - Add to `initial_state`: `"project_context": pc`
- [ ] Edit `src/pr_review_agent/ui/streamlit_app.py`
  - Sidebar: `st.file_uploader("Project context", type=["md", "json"])`
  - On upload, write to a tempfile, pass path to backend through the same code path as the CLI
  - Show a small indicator: "✓ context loaded (<N> tokens)" when present
- [ ] Edit `src/pr_review_agent/core/graph.py` — **no changes required** (state flows automatically via TypedDict)

### 3.6 Tests

- [ ] Add fixtures
  - `tests/fixtures/project_context.md` — ~30 lines of mock project description with sections referencing each category
  - `tests/fixtures/project_graph.json` — pre-built NetworkX node-link JSON covering all 4 categories
- [ ] Extend `tests/unit/test_nodes.py`
  - Add a parametrized variant per category: build a `ProjectContext` from the fixture graph, run the node, capture the LLM mock's `system` arg, assert it contains expected category-relevant terms
- [ ] Extend `tests/integration/test_full_graph.py`
  - Add second test that runs the full graph with `project_context` populated; assert the final summary references at least one term from the project-context fixture
- [ ] Add `tests/unit/test_context_loader.py`
  - Auto-discovery of `.pr-review-context.md` from a tmp_path
  - Auto-discovery of `graphify-out/graph.json` from a tmp_path
  - Both present → both loaded
  - Soft-warn when `.md` > 10_000 chars (caplog assertion)

### 3.7 Documentation

- [ ] Update `README.md`
  - Add a "Project context" section explaining:
    - How to write `.pr-review-context.md` (free-form, but mention sections like `## Tech Stack`, `## Conventions`, `## Review Instructions`)
    - How to build a graph: `pip install pr-review-agent[context]`, then `/graphify <docs-folder>` (or `python -m graphify <docs-folder>`) → produces `graphify-out/graph.json`
    - CLI usage: `pr-review-agent review <URL> --project-context .pr-review-context.md`
    - Streamlit usage: upload via sidebar
- [ ] Update `examples/sample_review_output.md` — leave untouched, but add a sibling `examples/sample_project_context.md` with a worked example

---

## 4. Acceptance Criteria

- [ ] `pytest tests/unit -v` passes (new tests + existing untouched)
- [ ] `pytest tests/integration -v` passes (with and without context)
- [ ] `pr-review-agent review <PR-URL> --project-context examples/sample_project_context.md --llm anthropic` runs end-to-end and produces a review whose summary visibly reflects the supplied context
- [ ] `pr-review-agent review <PR-URL> --llm ollama --model qwen2.5-coder:7b --project-context graphify-out/graph.json` runs end-to-end on a 20+ file PR without context-window overflow
- [ ] When no `--project-context` flag is given and no auto-discovered file exists, behavior is **identical** to today (no warnings, no extra tokens)
- [ ] When `graphifyy` is **not** installed and the user passes a `.json` graph, the CLI raises a clear error: `Project graph requires the [context] extras: pip install pr-review-agent[context]`

---

## 5. Phase 2 Sketch (do NOT build)

Leave a comment marker in `nodes/analysis.py` near `format_diff`. Future work:

- Chunk diff per-file (or grouped by language/path) before analysis
- Use LangGraph `Send` API to fan out one analysis call per chunk per category
- Reduce findings via existing `add` reducer on `ReviewState.findings`
- Per-chunk retrieval: query the graph using `{file_path, top_identifiers}` instead of just the static category seed terms
- Small-model robustness: regex-based JSON fallback when `json_mode` returns malformed output
- Token budget enforcement per chunk (system + ctx + chunk + reserve_for_response ≤ model_context)

---

## 6. Files Touched (final list)

**New**
- `src/pr_review_agent/context/__init__.py`
- `src/pr_review_agent/context/loader.py`
- `src/pr_review_agent/context/retriever.py`
- `tests/unit/test_context_loader.py`
- `tests/unit/test_context_retriever.py`
- `tests/fixtures/project_context.md`
- `tests/fixtures/project_graph.json`
- `examples/sample_project_context.md`

**Modified**
- `src/pr_review_agent/core/state.py`
- `src/pr_review_agent/core/settings.py`
- `src/pr_review_agent/llm/prompts/bug_detection.py`
- `src/pr_review_agent/llm/prompts/security.py`
- `src/pr_review_agent/llm/prompts/performance.py`
- `src/pr_review_agent/llm/prompts/test_coverage.py`
- `src/pr_review_agent/llm/prompts/synthesis.py`
- `src/pr_review_agent/nodes/analysis.py`
- `src/pr_review_agent/nodes/synthesis.py`
- `src/pr_review_agent/ui/cli.py`
- `src/pr_review_agent/ui/streamlit_app.py`
- `config.yaml`
- `pyproject.toml`
- `tests/unit/test_nodes.py`
- `tests/integration/test_full_graph.py`
- `README.md`

**Untouched**
- `src/pr_review_agent/core/graph.py` (state flows automatically)
- `src/pr_review_agent/llm/base.py`, all LLM providers (interface unchanged)
- `src/pr_review_agent/fetchers/**` (no PR-side changes)
- `src/pr_review_agent/output/**` (no output-shape changes)

---

## 7. Reused Existing Utilities

- `Settings.from_yaml()` (`core/settings.py:37`) — extended, not rewritten
- `make_analysis_node` factory (`nodes/analysis.py:49`) — gains one extra hop, signature unchanged externally
- `format_diff` (`nodes/analysis.py:18`) — untouched in Phase 1
- Graphify's NetworkX node-link JSON format (`graphify-out/graph.json`) — directly loadable via `networkx.readwrite.json_graph.node_link_graph`. See `~/.claude/skills/graphify/SKILL.md` lines 408 (export) and 902-987 (BFS query reference).

---

## 8. Hand-off Notes for Executor

- **Do not rewrite untouched files** — every modified file gets minimal surgical edits, not a full rewrite.
- **Read each modified file before editing** so you preserve unrelated code.
- **Run tests after each section** (3.1 → 3.2 → ...) so you catch regressions early.
- **Soft-import networkx**: `try: import networkx as nx; except ImportError: nx = None` at the top of `loader.py`. Raise a clear error only when a `.json` graph path is actually used.
- **No new top-level deps** — `graphifyy` and `networkx` go under `[project.optional-dependencies].context`.
- **No backwards-compat shims** — the `project_context` kwarg has a default of `""`, so existing callers don't need updating, but don't add a "removed in v2" stub anywhere.
- **Don't post-back to the PR** — that's a separate future feature.
