import pytest
import responses as resp_mock
from responses import RequestsMock

from pr_review_agent.fetchers.azure_devops import AzureDevOpsFetcher, _parse_azure_pr_url
from pr_review_agent.fetchers.models import PullRequest


# ---------------------------------------------------------------------------
# _parse_azure_pr_url
# ---------------------------------------------------------------------------

class TestParseAzurePrUrl:
    def test_new_format(self):
        org, project, repo, pr_id = _parse_azure_pr_url(
            "https://dev.azure.com/myorg/myproject/_git/myrepo/pullrequest/99"
        )
        assert org == "myorg"
        assert project == "myproject"
        assert repo == "myrepo"
        assert pr_id == 99

    def test_old_visualstudio_format(self):
        org, project, repo, pr_id = _parse_azure_pr_url(
            "https://myorg.visualstudio.com/myproject/_git/myrepo/pullrequest/42"
        )
        assert org == "myorg"
        assert pr_id == 42

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Unrecognised"):
            _parse_azure_pr_url("https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# AzureDevOpsFetcher
# ---------------------------------------------------------------------------

_BASE = "https://dev.azure.com/org/project/_apis/git/repositories/repo"
_PR_URL = "https://dev.azure.com/org/project/_git/repo/pullrequest/1"


def _pr_response() -> dict:
    return {
        "pullRequestId": 1,
        "title": "Add feature X",
        "description": "Implements feature X",
        "createdBy": {"displayName": "Alice"},
        "sourceRefName": "refs/heads/feature/x",
        "targetRefName": "refs/heads/main",
        "lastMergeSourceCommit": {"commitId": "abc123"},
        "lastMergeTargetCommit": {"commitId": "def456"},
    }


def _iterations_response() -> dict:
    return {"value": [{"id": 1}, {"id": 2}]}


def _changes_response() -> dict:
    return {
        "changeEntries": [
            {"item": {"path": "/src/feature.py", "isFolder": False}, "changeType": "edit"},
        ]
    }


class TestAzureDevOpsFetcher:
    @resp_mock.activate
    def test_fetch_pr_returns_pull_request(self):
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1", json=_pr_response())
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations", json=_iterations_response())
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations/2/changes", json=_changes_response())
        # File content at source and target
        resp_mock.add(resp_mock.GET, f"{_BASE}/items", body="old content\n")
        resp_mock.add(resp_mock.GET, f"{_BASE}/items", body="new content\n")

        fetcher = AzureDevOpsFetcher(org="org", pat="fake_pat")
        pr = fetcher.fetch_pr(_PR_URL)

        assert isinstance(pr, PullRequest)
        assert pr.title == "Add feature X"
        assert pr.author == "Alice"
        assert pr.provider == "azure_devops"
        assert pr.source_branch == "feature/x"
        assert pr.target_branch == "main"

    @resp_mock.activate
    def test_folder_items_are_skipped(self):
        changes = {
            "changeEntries": [
                {"item": {"path": "/src/", "isFolder": True}, "changeType": "edit"},
                {"item": {"path": "/src/main.py", "isFolder": False}, "changeType": "add"},
            ]
        }
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1", json=_pr_response())
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations", json=_iterations_response())
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations/2/changes", json=changes)
        resp_mock.add(resp_mock.GET, f"{_BASE}/items", body="")
        resp_mock.add(resp_mock.GET, f"{_BASE}/items", body="new file\n")

        fetcher = AzureDevOpsFetcher(org="org", pat="fake_pat")
        pr = fetcher.fetch_pr(_PR_URL)

        assert all(not f.path.endswith("/") for f in pr.files)

    @resp_mock.activate
    def test_latest_iteration_is_used(self):
        iterations = {"value": [{"id": 1}, {"id": 3}, {"id": 2}]}
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1", json=_pr_response())
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations", json=iterations)
        resp_mock.add(resp_mock.GET, f"{_BASE}/pullrequests/1/iterations/3/changes", json={"changeEntries": []})

        fetcher = AzureDevOpsFetcher(org="org", pat="fake_pat")
        pr = fetcher.fetch_pr(_PR_URL)

        assert pr.files == []

    def test_get_file_diff_found(self):
        from pr_review_agent.fetchers.models import FileDiff
        pr = PullRequest(
            id="1", title="t", description="", author="a",
            source_branch="x", target_branch="main",
            files=[FileDiff(path="src/a.py", status="modified", additions=1, deletions=0, diff_text="")],
            provider="azure_devops",
            url=_PR_URL,
        )
        fetcher = AzureDevOpsFetcher.__new__(AzureDevOpsFetcher)
        assert fetcher.get_file_diff(pr, "src/a.py").path == "src/a.py"

    def test_get_file_diff_missing_raises(self):
        pr = PullRequest(
            id="1", title="t", description="", author="a",
            source_branch="x", target_branch="main",
            files=[],
            provider="azure_devops",
            url=_PR_URL,
        )
        fetcher = AzureDevOpsFetcher.__new__(AzureDevOpsFetcher)
        with pytest.raises(ValueError, match="not found"):
            fetcher.get_file_diff(pr, "missing.py")
