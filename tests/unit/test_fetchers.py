import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from pr_review_agent.fetchers.github import GitHubFetcher
from pr_review_agent.fetchers.models import PullRequest, FileDiff
from pr_review_agent.fetchers.utils import detect_language, parse_github_pr_url


# ---------------------------------------------------------------------------
# parse_github_pr_url
# ---------------------------------------------------------------------------

class TestParseGithubPrUrl:
    def test_full_url(self):
        owner, repo, num = parse_github_pr_url("https://github.com/tiangolo/fastapi/pull/11364")
        assert owner == "tiangolo"
        assert repo == "fastapi"
        assert num == 11364

    def test_short_form(self):
        owner, repo, num = parse_github_pr_url("tiangolo/fastapi#11364")
        assert owner == "tiangolo"
        assert repo == "fastapi"
        assert num == 11364

    def test_url_with_trailing_slash(self):
        owner, repo, num = parse_github_pr_url("https://github.com/owner/repo/pull/42")
        assert num == 42

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Unrecognised"):
            parse_github_pr_url("not-a-pr-url")

    def test_invalid_no_number_raises(self):
        with pytest.raises(ValueError):
            parse_github_pr_url("https://github.com/owner/repo/issues/42")


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    @pytest.mark.parametrize("path,expected", [
        ("src/main.py", "python"),
        ("app/index.ts", "typescript"),
        ("server/handler.go", "go"),
        ("lib/util.rs", "rust"),
        ("Dockerfile", "dockerfile"),
        ("docker/Dockerfile", "dockerfile"),
        ("README.md", "markdown"),
        ("schema.sql", "sql"),
        ("unknown.xyz", None),
        ("no_extension", None),
    ])
    def test_known_extensions(self, path, expected):
        assert detect_language(path) == expected


# ---------------------------------------------------------------------------
# GitHubFetcher
# ---------------------------------------------------------------------------

def _make_gh_file(
    filename: str,
    status: str = "modified",
    additions: int = 5,
    deletions: int = 2,
    patch: str | None = "@@ -1,3 +1,4 @@\n context\n+added line\n context",
) -> MagicMock:
    f = MagicMock()
    f.filename = filename
    f.status = status
    f.additions = additions
    f.deletions = deletions
    f.patch = patch
    return f


def _make_gh_pr(
    number: int = 42,
    title: str = "Fix SQL injection",
    body: str = "Parameterize queries",
    login: str = "octocat",
    head_ref: str = "fix/sql",
    base_ref: str = "main",
    html_url: str = "https://github.com/owner/repo/pull/42",
    changed_files: int = 1,
    files: list | None = None,
) -> MagicMock:
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.body = body
    pr.user.login = login
    pr.head.ref = head_ref
    pr.base.ref = base_ref
    pr.html_url = html_url
    pr.changed_files = changed_files
    pr.get_files.return_value = files or [_make_gh_file("src/auth.py")]
    return pr


class TestGitHubFetcher:
    @pytest.fixture
    def fetcher(self):
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            instance = MockGithub.return_value
            yield fetcher_instance := GitHubFetcher(pat="ghp_fake"), instance

    def _setup_repo(self, gh_instance, gh_pr):
        repo = MagicMock()
        repo.get_pull.return_value = gh_pr
        gh_instance.get_repo.return_value = repo
        return repo

    def test_fetch_pr_returns_pull_request(self):
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            gh_pr = _make_gh_pr()
            repo = MagicMock()
            repo.get_pull.return_value = gh_pr
            MockGithub.return_value.get_repo.return_value = repo

            fetcher = GitHubFetcher(pat="ghp_fake")
            pr = fetcher.fetch_pr("https://github.com/owner/repo/pull/42")

        assert isinstance(pr, PullRequest)
        assert pr.id == "42"
        assert pr.title == "Fix SQL injection"
        assert pr.author == "octocat"
        assert pr.provider == "github"
        assert len(pr.files) == 1

    def test_binary_files_are_excluded(self):
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            binary_file = _make_gh_file("image.png", patch=None)
            text_file = _make_gh_file("src/main.py")
            gh_pr = _make_gh_pr(files=[binary_file, text_file], changed_files=2)
            repo = MagicMock()
            repo.get_pull.return_value = gh_pr
            MockGithub.return_value.get_repo.return_value = repo

            fetcher = GitHubFetcher(pat="ghp_fake")
            pr = fetcher.fetch_pr("owner/repo#42")

        assert len(pr.files) == 1
        assert pr.files[0].path == "src/main.py"

    def test_language_detected_on_files(self):
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            gh_pr = _make_gh_pr(files=[_make_gh_file("app/handler.go")])
            repo = MagicMock()
            repo.get_pull.return_value = gh_pr
            MockGithub.return_value.get_repo.return_value = repo

            fetcher = GitHubFetcher(pat="ghp_fake")
            pr = fetcher.fetch_pr("owner/repo#42")

        assert pr.files[0].language == "go"

    def test_large_diff_is_truncated(self):
        big_patch = "+" + "x" * (600 * 1024)
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            gh_pr = _make_gh_pr(files=[_make_gh_file("big.py", patch=big_patch)])
            repo = MagicMock()
            repo.get_pull.return_value = gh_pr
            MockGithub.return_value.get_repo.return_value = repo

            fetcher = GitHubFetcher(pat="ghp_fake")
            pr = fetcher.fetch_pr("owner/repo#42")

        assert len(pr.files[0].diff_text.encode()) <= 500 * 1024

    def test_get_file_diff_returns_correct_file(self):
        pr = PullRequest(
            id="1", title="t", description="", author="a",
            source_branch="x", target_branch="main",
            files=[
                FileDiff(path="a.py", status="modified", additions=1, deletions=0, diff_text=""),
                FileDiff(path="b.py", status="added", additions=5, deletions=0, diff_text=""),
            ],
            provider="github",
            url="https://github.com/o/r/pull/1",
        )
        fetcher = GitHubFetcher.__new__(GitHubFetcher)
        assert fetcher.get_file_diff(pr, "b.py").path == "b.py"

    def test_get_file_diff_raises_for_missing_file(self):
        pr = PullRequest(
            id="1", title="t", description="", author="a",
            source_branch="x", target_branch="main",
            files=[],
            provider="github",
            url="https://github.com/o/r/pull/1",
        )
        fetcher = GitHubFetcher.__new__(GitHubFetcher)
        with pytest.raises(ValueError, match="not found"):
            fetcher.get_file_diff(pr, "missing.py")

    def test_github_exception_raises_runtime_error(self):
        from github import GithubException
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            MockGithub.return_value.get_repo.side_effect = GithubException(
                status=401, data={"message": "Bad credentials"}
            )
            fetcher = GitHubFetcher(pat="bad_token")
            with pytest.raises(RuntimeError, match="Failed to fetch PR"):
                fetcher.fetch_pr("owner/repo#1")

    def test_unknown_status_normalised_to_modified(self):
        with patch("pr_review_agent.fetchers.github.Github") as MockGithub:
            gh_pr = _make_gh_pr(files=[_make_gh_file("f.py", status="changed")])
            repo = MagicMock()
            repo.get_pull.return_value = gh_pr
            MockGithub.return_value.get_repo.return_value = repo

            fetcher = GitHubFetcher(pat="ghp_fake")
            pr = fetcher.fetch_pr("owner/repo#42")

        assert pr.files[0].status == "modified"
