from pr_review_agent.core.state import ReviewState
from pr_review_agent.output.models import Review


def state_to_review(state: ReviewState) -> Review:
    return Review(
        pr_url=state["pr_url"],
        summary=state.get("summary") or "",
        findings=state.get("final_findings") or [],
        errors=state.get("errors") or [],
    )
