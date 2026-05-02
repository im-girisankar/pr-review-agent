from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx

SEED_TERMS: dict[str, list[str]] = {
    "bug_detection": ["bug", "null", "exception", "race", "leak", "boundary", "validation"],
    "security": ["auth", "crypto", "input", "injection", "secret", "permission", "token"],
    "performance": ["latency", "throughput", "cache", "query", "loop", "memory", "io"],
    "test_coverage": ["test", "coverage", "fixture", "mock", "assert", "spec"],
    "synthesis_critique": ["correctness", "evidence", "diff", "scope"],
    "synthesis_summary": ["overview", "architecture", "module", "feature", "release"],
}


@dataclass
class ProjectContext:
    graph: nx.Graph | None = field(default=None)
    global_md: str | None = None

    def retrieve(self, category: str, budget_tokens: int = 1500) -> str:
        budget_chars = budget_tokens * 4
        if self.graph is not None:
            result = self._graph_retrieve(category, budget_chars)
            if result:
                return result
        if self.global_md:
            return _truncate(self.global_md, budget_chars)
        return ""

    def _graph_retrieve(self, category: str, budget_chars: int) -> str:
        G = self.graph
        seeds = SEED_TERMS.get(category, [])

        scored: list[tuple[int, str]] = []
        for nid, ndata in G.nodes(data=True):
            label = (ndata.get("label") or "").lower()
            score = sum(1 for s in seeds if s in label)
            if score > 0:
                scored.append((score, nid))
        scored.sort(reverse=True)
        start_nodes = [nid for _, nid in scored[:3]]

        if not start_nodes:
            return ""

        visited: set[str] = set(start_nodes)
        frontier: set[str] = set(start_nodes)
        for _ in range(2):
            next_frontier: set[str] = set()
            for n in frontier:
                for neighbor in G.neighbors(n):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier

        lines = ["## Project Context (from knowledge graph)"]
        for nid in visited:
            ndata = G.nodes[nid]
            label = ndata.get("label") or nid
            file_type = ndata.get("file_type") or ""
            tag = f" [{file_type}]" if file_type else ""
            lines.append(f"- {label}{tag}")
            for neighbor in G.neighbors(nid):
                if neighbor in visited:
                    edge_data = G.edges[nid, neighbor]
                    relation = edge_data.get("relation") or "related-to"
                    n_label = G.nodes[neighbor].get("label") or neighbor
                    lines.append(f"  --{relation}--> {n_label}")

        return _truncate("\n".join(lines), budget_chars)


def _truncate(text: str, budget_chars: int) -> str:
    if len(text) <= budget_chars:
        return text
    return text[:budget_chars] + "\n... (truncated)"
