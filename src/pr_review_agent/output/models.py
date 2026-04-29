from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    category: Literal["bug", "security", "performance", "test_coverage"]
    severity: Literal["critical", "high", "medium", "low", "informational"]
    file: str
    line_start: int
    line_end: int
    title: str
    description: str
    suggestion: str | None = None


class Review(BaseModel):
    pr_url: str
    summary: str
    findings: list[Finding]
    errors: list[str] = []
