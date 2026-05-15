import base64
import difflib
import re

import requests
import structlog

from .base import PRFetcher
from .models import FileDiff, PullRequest
from .utils import detect_language

log = structlog.get_logger(__name__)

_API_VERSION = "7.1"
_CHANGE_TYPE_MAP = {
    "add": "added",
    "edit": "modified",
    "delete": "deleted",
    "rename": "renamed",
}


def _parse_azure_pr_url(url: str) -> tuple[str, str, str, int]:
    """Return (org, project, repo, pr_id) from an Azure DevOps PR URL."""
    new = re.compile(
        r"https?://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/pullrequest/(\d+)",
        re.IGNORECASE,
    )
    old = re.compile(
        r"https?://([^.]+)\.visualstudio\.com/([^/]+)/_git/([^/]+)/pullrequest/(\d+)",
        re.IGNORECASE,
    )
    for pattern in (new, old):
        if m := pattern.match(url.strip()):
            return m.group(1), m.group(2), m.group(3), int(m.group(4))
    raise ValueError(
        f"Unrecognised Azure DevOps PR URL: {url!r}. "
        "Expected https://dev.azure.com/{{org}}/{{project}}/_git/{{repo}}/pullrequest/{{id}}"
    )


class AzureDevOpsFetcher(PRFetcher):
    """Fetches PR data from Azure DevOps via REST API."""

    def __init__(self, org: str, pat: str) -> None:
        self._org = org
        token = base64.b64encode(f":{pat}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_pr(self, pr_identifier: str) -> PullRequest:
        org, project, repo, pr_id = _parse_azure_pr_url(pr_identifier)
        log.info("azure_fetch_pr", org=org, project=project, repo=repo, pr=pr_id)

        base_url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}"

        pr_data = self._get(f"{base_url}/pullrequests/{pr_id}")
        iteration_id = self._get_latest_iteration_id(base_url, pr_id)
        changes = self._get_changes(base_url, pr_id, iteration_id)

        source_sha = pr_data["lastMergeSourceCommit"]["commitId"]
        target_sha = pr_data["lastMergeTargetCommit"]["commitId"]

        files = [
            diff
            for change in changes
            if (diff := self._build_file_diff(base_url, change, source_sha, target_sha))
            is not None
        ]

        return PullRequest(
            id=str(pr_id),
            title=pr_data["title"],
            description=pr_data.get("description") or "",
            author=pr_data["createdBy"]["displayName"],
            source_branch=pr_data["sourceRefName"].replace("refs/heads/", ""),
            target_branch=pr_data["targetRefName"].replace("refs/heads/", ""),
            files=files,
            provider="azure_devops",
            url=pr_identifier,
        )

    def get_file_diff(self, pr: PullRequest, file_path: str) -> FileDiff:
        for f in pr.files:
            if f.path == file_path:
                return f
        raise ValueError(f"File {file_path!r} not found in PR {pr.id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        p = {"api-version": _API_VERSION}
        if params:
            p.update(params)
        resp = requests.get(url, headers=self._headers, params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_file_content(self, base_url: str, path: str, sha: str) -> str | None:
        try:
            resp = requests.get(
                f"{base_url}/items",
                headers=self._headers,
                params={
                    "path": path,
                    "versionDescriptor.versionType": "commit",
                    "versionDescriptor.version": sha,
                    "api-version": _API_VERSION,
                },
                timeout=30,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.warning("azure_file_fetch_failed", path=path, error=str(exc))
            return None

    def _get_latest_iteration_id(self, base_url: str, pr_id: int) -> int:
        data = self._get(f"{base_url}/pullrequests/{pr_id}/iterations")
        iterations = data.get("value", [])
        if not iterations:
            raise RuntimeError(f"PR {pr_id} has no iterations")
        return max(it["id"] for it in iterations)

    def _get_changes(self, base_url: str, pr_id: int, iteration_id: int) -> list[dict]:
        data = self._get(
            f"{base_url}/pullrequests/{pr_id}/iterations/{iteration_id}/changes"
        )
        return data.get("changeEntries", [])

    def _build_file_diff(
        self,
        base_url: str,
        change: dict,
        source_sha: str,
        target_sha: str,
    ) -> FileDiff | None:
        item = change.get("item", {})
        path: str = item.get("path", "")
        if not path or item.get("isFolder"):
            return None

        raw_type = change.get("changeType", "edit").lower()
        status = _CHANGE_TYPE_MAP.get(raw_type, "modified")

        source_content = self._get_file_content(base_url, path, source_sha) or ""
        target_content = self._get_file_content(base_url, path, target_sha) or ""

        source_lines = source_content.splitlines(keepends=True)
        target_lines = target_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                source_lines,
                target_lines,
                fromfile=f"a{path}",
                tofile=f"b{path}",
            )
        )
        diff_text = "".join(diff_lines)

        additions = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        deletions = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

        if not diff_text and status not in ("added", "deleted"):
            return None

        return FileDiff(
            path=path.lstrip("/"),
            status=status,  # type: ignore[arg-type]
            additions=additions,
            deletions=deletions,
            diff_text=diff_text,
            language=detect_language(path),
        )
