import json
import re
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

# Analysis pass names don't always match the Finding.category Literal values.
# Map them at the boundary so pass naming (used in graph, retriever, logs) stays
# decoupled from the canonical finding category.
_PASS_TO_CATEGORY = {
    "bug_detection": "bug",
    "security": "security",
    "performance": "performance",
    "test_coverage": "test_coverage",
}


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


def _strip_json_fences(raw: str) -> str:
    """Strip markdown code fences that some models wrap around JSON output."""
    s = raw.strip()
    # Remove opening ```json or ``` fence
    s = re.sub(r'^```(?:json)?\s*\n?', '', s)
    # Remove closing ``` fence
    s = re.sub(r'\n?```\s*$', '', s)
    return s.strip()


def _parse_findings(raw: str, expected_category: str) -> list[Finding]:
    """
    Parse LLM JSON output into Finding objects.
    Retries are handled at the call site; this raises on failure so the
    caller can decide whether to retry or swallow the error.
    """
    data = json.loads(_strip_json_fences(raw))
    findings = []
    finding_category = _PASS_TO_CATEGORY.get(expected_category, expected_category)
    for item in data.get("findings", []):
        item["category"] = finding_category  # enforce correct category
        try:
            findings.append(Finding(**item))
        except (ValidationError, TypeError):
            log.warning("invalid_finding_skipped", item=item)
    return findings


def make_analysis_node(
    category: str,
    build_prompt: Callable[..., tuple[str, str]],
    llm: LLMProvider,
    settings: Settings,
) -> Callable:
    async def node(state: ReviewState) -> dict:
        # Resume support: if this pass already succeeded in a previous run,
        # skip it. Returning {} contributes nothing to the reducers.
        if category in state.get("completed_passes", []):
            log.info("analysis_skipped_already_done", category=category)
            return {}

        pr = state.get("pull_request")
        if pr is None:
            # Fetch failed; synthesis will detect and halt — don't waste an LLM call.
            return {}

        # Phase 2: chunk per-file here and run map-reduce so big PRs fit on small models.
        diff = format_diff(pr)

        ctx = state.get("project_context")
        project_context = (
            ctx.retrieve(category, settings.context_budget_tokens) if ctx else ""
        )
        system, user = build_prompt(pr.title, pr.description, diff, project_context=project_context)

        last_preview = ""
        last_model = ""
        for attempt in range(settings.retry_attempts + 1):
            try:
                resp = await llm.acomplete(
                    system=system,
                    user=user,
                    json_mode=True,
                    temperature=settings.temperature,
                )
                last_preview = (resp.content or "")[:500]
                last_model = resp.model
                findings = _parse_findings(resp.content, category)
                log.info("analysis_done", category=category, count=len(findings))
                return {"findings": findings, "completed_passes": [category]}
            except json.JSONDecodeError as exc:
                if attempt == settings.retry_attempts:
                    log.error(
                        "analysis_json_failed",
                        category=category,
                        error=str(exc),
                        response_preview=last_preview,
                        model=last_model,
                    )
                    return {"failed_passes": [{
                        "category": category,
                        "error": f"Malformed JSON after {attempt + 1} attempt(s): {exc}",
                        "response_preview": last_preview,
                        "attempt": attempt,
                        "kind": "json_decode",
                        "model": last_model,
                    }]}
                log.warning("analysis_retry", category=category, attempt=attempt)
            except Exception as exc:
                log.error("analysis_failed", category=category, error=str(exc))
                return {"failed_passes": [{
                    "category": category,
                    "error": str(exc),
                    "response_preview": last_preview,
                    "attempt": attempt,
                    "kind": type(exc).__name__,
                    "model": last_model,
                }]}

        return {"failed_passes": [{
            "category": category,
            "error": "all retry attempts exhausted",
            "response_preview": last_preview,
            "attempt": settings.retry_attempts,
            "kind": "exhausted",
            "model": last_model,
        }]}

    return node
