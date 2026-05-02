from __future__ import annotations

import json
from pathlib import Path

import structlog

from .retriever import ProjectContext

log = structlog.get_logger(__name__)

try:
    import networkx as nx
    from networkx.readwrite import json_graph as nx_json

    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False


def load_project_context(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
) -> ProjectContext | None:
    base = cwd or Path.cwd()

    if path is None:
        md_path = base / ".pr-review-context.md"
        graph_path = base / "graphify-out" / "graph.json"
        has_md = md_path.exists()
        has_graph = graph_path.exists()
        if not has_md and not has_graph:
            return None
        global_md = _load_md(md_path) if has_md else None
        graph = _load_graph(graph_path) if has_graph else None
        return ProjectContext(global_md=global_md, graph=graph)

    path = Path(path)

    if path.suffix == ".json":
        graph = _load_graph(path)
        sibling_md = path.parent.parent / ".pr-review-context.md"
        global_md = _load_md(sibling_md) if sibling_md.exists() else None
        return ProjectContext(graph=graph, global_md=global_md)

    if path.suffix == ".md":
        global_md = _load_md(path)
        sibling_graph = path.parent / "graphify-out" / "graph.json"
        graph = _load_graph(sibling_graph) if sibling_graph.exists() else None
        return ProjectContext(global_md=global_md, graph=graph)

    log.warning("project_context_unknown_format", path=str(path))
    return None


def _load_md(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) > 10_000:
        log.warning(
            "project_context_large",
            chars=len(text),
            path=str(path),
            tip="Consider building a graphify graph.json for efficient per-pass retrieval",
        )
    return text


def _load_graph(path: Path) -> nx.Graph | None:
    if not _NX_AVAILABLE:
        raise ImportError(
            "Loading a graph.json requires the [context] extras: "
            "pip install pr-review-agent[context]"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return nx_json.node_link_graph(data, edges="links")
