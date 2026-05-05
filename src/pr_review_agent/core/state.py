from operator import add
from typing import Annotated, TypedDict

from pr_review_agent.fetchers.models import PullRequest
from pr_review_agent.output.models import Finding


class ReviewState(TypedDict):
    # Input
    pr_url: str
    provider: str  # "github" | "azure_devops"

    # Populated by fetch node
    pull_request: PullRequest | None

    # Populated by analysis nodes — add reducer merges results from parallel branches
    findings: Annotated[list[Finding], add]

    # Populated by synthesis node
    final_findings: list[Finding] | None
    summary: str | None

    # add reducer so parallel branches can safely write errors without overwriting each other
    errors: Annotated[list[str], add]
