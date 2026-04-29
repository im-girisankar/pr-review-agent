from abc import ABC, abstractmethod

from .models import FileDiff, PullRequest


class PRFetcher(ABC):
    """Abstract base for PR source providers."""

    @abstractmethod
    def fetch_pr(self, pr_identifier: str) -> PullRequest:
        """
        Fetch PR metadata and all changed files.

        pr_identifier format depends on provider:
          - GitHub: "owner/repo#123" or full URL
          - Azure DevOps: "org/project/repo/123" or full URL
        """

    @abstractmethod
    def get_file_diff(self, pr: PullRequest, file_path: str) -> FileDiff:
        """Fetch line-by-line diff for a specific file."""
