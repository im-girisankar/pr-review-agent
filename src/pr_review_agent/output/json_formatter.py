from pr_review_agent.output.models import Review


def to_json(review: Review, indent: int = 2) -> str:
    return review.model_dump_json(indent=indent)
