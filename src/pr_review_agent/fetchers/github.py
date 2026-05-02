import structlog
from github import Github, GithubException
from github.File import File as GHFile

from .base import PRFetcher
from .models import FileDiff, PullRequest
from .utils import detect_language, parse_github_pr_url

log = structlog.get_logger(__name__)

# GitHub hard-caps paginated file lists at 3000 files per PR.
_GITHUB_MAX_FILES = 3000
# Files whose diff text exceeds this are included but diff_text is truncated.
_MAX_DIFF_BYTES = 500 * 1024  # 500 KB


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

        if gh_pr.changed_files >= _GITHUB_MAX_FILES:
            log.warning(
                "pr_at_github_file_cap",
                pr=pr_number,
                changed_files=gh_pr.changed_files,
                cap=_GITHUB_MAX_FILES,
            )

        # get_files() returns a PaginatedList — PyGithub handles pagination automatically.
        files = [
            self._map_file(f)
            for f in gh_pr.get_files()
            if not self._is_binary(f)
        ]

        log.info(
            "pr_fetched",
            pr=pr_number,
            total_files=gh_pr.changed_files,
            text_files=len(files),
        )

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
        for f in pr.files:
            if f.path == file_path:
                return f
        raise ValueError(f"File {file_path!r} not found in PR {pr.id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _map_file(self, gh_file: GHFile) -> FileDiff:
        status = gh_file.status
        if status not in ("added", "modified", "deleted", "renamed"):
            status = "modified"

        diff_text = gh_file.patch or ""
        if len(diff_text.encode()) > _MAX_DIFF_BYTES:
            log.warning("diff_truncated", path=gh_file.filename)
            diff_text = diff_text.encode()[:_MAX_DIFF_BYTES].decode("utf-8", errors="ignore")

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
        """Binary files have no patch — skip them as diffs are meaningless."""
        return gh_file.patch is None
