from typing import Literal

from pydantic import BaseModel


class FileDiff(BaseModel):
    path: str
    status: Literal["added", "modified", "deleted", "renamed"]
    additions: int
    deletions: int
    diff_text: str
    language: str | None = None


class PullRequest(BaseModel):
    id: str
    title: str
    description: str
    author: str
    source_branch: str
    target_branch: str
    files: list[FileDiff]
    provider: Literal["github", "azure_devops", "gitlab"]
    url: str
