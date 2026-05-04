from operator import add
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from pr_review_agent.fetchers.models import PullRequest
from pr_review_agent.output.models import Finding

if TYPE_CHECKING:
    from pr_review_agent.context.retriever import ProjectContext


class ReviewState(TypedDict):
    # Input
    pr_url: str
    provider: str  # "github" | "azure_devops"

    # Optional project context loaded from .md or graphify graph.json
    project_context: Any  # ProjectContext | None

    # Populated by fetch node
    pull_request: PullRequest | None

    # Populated by analysis nodes — add reducer merges results from parallel branches
    findings: Annotated[list[Finding], add]

    # Populated by synthesis node
    final_findings: list[Finding] | None
    summary: str | None

    # add reducer so parallel branches can safely write errors without overwriting each other
    errors: Annotated[list[str], add]

    # Pass-level completion tracking — used by stop-and-resume.
    # On resume, analysis nodes whose name is in completed_passes are skipped.
    completed_passes: Annotated[list[str], add]

    # Each entry: {"category", "error", "response_preview", "attempt", "kind"}.
    # If non-empty after analysis, synthesis short-circuits without running so the
    # caller can decide whether to resume.
    failed_passes: Annotated[list[dict], add]
