import structlog
from github import Github, GithubException
from github.PullRequest import PullRequest as GHPullRequest
from github.File import File as GHFile

from .base import PRFetcher
from .models import FileDiff, PullRequest
from .utils import detect_language, parse_github_pr_url

log = structlog.get_logger(__name__)

_MAX_DIFF_SIZE_BYTES = 500 * 1024  # 500 KB


class GitHubFetcher(PRFetcher):
    """Fetches PR data from GitHub using PyGithub."""

    def __init__(self, pat: str) -> None:
        self._client = Github(pat)

    def fetch_pr(self, pr_identifier: str) -> PullRequest:
        owner, repo_name, pr_number = parse_github_pr_url(pr_identifier)
        log.info("fetching_pr", owner=owner, repo=repo_name, pr=pr_number)

        try:
            repo = self._client.get_repo(f"{owner}/{repo_name}")
            gh_pr = repo.get_pull(pr_number)
        except GithubException as exc:
            raise RuntimeError(
                f"Failed to fetch PR {pr_identifier}: {exc.status} {exc.data}"
            ) from exc

        files = [self._map_file(f) for f in gh_pr.get_files() if not self._is_binary(f)]

        return PullRequest(
            id=str(gh_pr.number),
            title=gh_pr.title,
            description=gh_pr.body or "",
            author=gh_pr.user.login,
            source_branch=gh_pr.head.ref,
            target_branch=gh_pr.base.ref,
            files=files,
            provider="github",
            url=gh_pr.html_url,
        )

    def get_file_diff(self, pr: PullRequest, file_path: str) -> FileDiff:
        """Return the FileDiff for a specific file already loaded in the PR."""
        for f in pr.files:
            if f.path == file_path:
                return f
        raise ValueError(f"File {file_path!r} not found in PR {pr.id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _map_file(self, gh_file: GHFile) -> FileDiff:
        status = gh_file.status
        # PyGithub uses "renamed" as a status; normalise to our literal
        if status not in ("added", "modified", "deleted", "renamed"):
            status = "modified"

        diff_text = gh_file.patch or ""
        return FileDiff(
            path=gh_file.filename,
            status=status,  # type: ignore[arg-type]
            additions=gh_file.additions,
            deletions=gh_file.deletions,
            diff_text=diff_text,
            language=detect_language(gh_file.filename),
        )

    @staticmethod
    def _is_binary(gh_file: GHFile) -> bool:
        """Skip binary files — patch is None and diff is meaningless."""
        return gh_file.patch is None
