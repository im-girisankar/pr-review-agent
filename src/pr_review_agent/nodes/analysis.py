import json
from collections.abc import Callable

import structlog
from pydantic import ValidationError

from pr_review_agent.core.settings import Settings
from pr_review_agent.core.state import ReviewState
from pr_review_agent.fetchers.models import FileDiff, PullRequest
from pr_review_agent.llm.base import LLMProvider
from pr_review_agent.output.models import Finding

log = structlog.get_logger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}


def format_diff(pr: PullRequest) -> str:
    """Format all file diffs as a single annotated string for LLM consumption."""
    parts: list[str] = []
    for f in pr.files:
        if not f.diff_text:
            continue
        lang = f.language or "diff"
        parts.append(f"### {f.path}  ({f.status}, +{f.additions} -{f.deletions})")
        parts.append(f"```{lang}")
        parts.append(f.diff_text)
        parts.append("```\n")
    return "\n".join(parts)


def _parse_findings(raw: str, expected_category: str) -> list[Finding]:
    """
    Parse LLM JSON output into Finding objects.
    Retries are handled at the call site; this raises on failure so the
    caller can decide whether to retry or swallow the error.
    """
    data = json.loads(raw)
    findings = []
    for item in data.get("findings", []):
        item["category"] = expected_category  # enforce correct category
        try:
            findings.append(Finding(**item))
        except (ValidationError, TypeError):
            log.warning("invalid_finding_skipped", item=item)
    return findings


def make_analysis_node(
    category: str,
    build_prompt: Callable[[str, str, str], tuple[str, str]],
    llm: LLMProvider,
    settings: Settings,
) -> Callable:
    async def node(state: ReviewState) -> dict:
        pr = state.get("pull_request")
        if pr is None:
            return {"findings": [], "errors": [f"{category}: skipped — PR fetch failed"]}

        diff = format_diff(pr)
        system, user = build_prompt(pr.title, pr.description, diff)

        for attempt in range(settings.retry_attempts + 1):
            try:
                resp = await llm.acomplete(
                    system=system,
                    user=user,
                    json_mode=True,
                    temperature=settings.temperature,
                )
                findings = _parse_findings(resp.content, category)
                log.info("analysis_done", category=category, count=len(findings))
                return {"findings": findings, "errors": []}
            except json.JSONDecodeError as exc:
                if attempt == settings.retry_attempts:
                    log.error("analysis_json_failed", category=category, error=str(exc))
                    return {"findings": [], "errors": [f"{category}: malformed JSON response"]}
                log.warning("analysis_retry", category=category, attempt=attempt)
            except Exception as exc:
                log.error("analysis_failed", category=category, error=str(exc))
                return {"findings": [], "errors": [f"{category}: {exc}"]}

        return {"findings": [], "errors": [f"{category}: all retry attempts exhausted"]}

    return node
