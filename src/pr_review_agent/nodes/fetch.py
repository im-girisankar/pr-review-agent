from collections.abc import Callable

import structlog

from pr_review_agent.core.state import ReviewState
from pr_review_agent.fetchers.base import PRFetcher

log = structlog.get_logger(__name__)


def make_fetch_node(fetcher: PRFetcher) -> Callable:
    async def fetch(state: ReviewState) -> dict:
        pr_url = state["pr_url"]
        log.info("fetch_node_start", url=pr_url)
        try:
            pr = fetcher.fetch_pr(pr_url)
            log.info("fetch_node_done", files=len(pr.files))
            return {"pull_request": pr, "errors": []}
        except Exception as exc:
            log.error("fetch_node_failed", url=pr_url, error=str(exc))
            return {"pull_request": None, "errors": [f"Failed to fetch PR: {exc}"]}

    return fetch
