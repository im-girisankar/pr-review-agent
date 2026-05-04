"""
File-chunked unified analysis node.

One LLM call per file, all four categories in a single prompt. This fits
any model regardless of context window — each call sees only one file diff
instead of the whole PR. All files run concurrently via asyncio.gather.
"""

import asyncio
import json
from collections.abc import Callable

import structlog
from pydantic import ValidationError

from pr_review_agent.core.settings import Settings
from pr_review_agent.core.state import ReviewState
from pr_review_agent.fetchers.models import FileDiff
from pr_review_agent.llm.base import LLMProvider
from pr_review_agent.llm.prompts import unified as unified_prompts
from pr_review_agent.nodes.analysis import _strip_json_fences
from pr_review_agent.output.models import Finding

log = structlog.get_logger(__name__)

_VALID_CATEGORIES = {"bug", "security", "performance", "test_coverage"}


def _format_file_diff(file: FileDiff) -> str:
    lang = file.language or "diff"
    return (
        f"### {file.path}  ({file.status}, +{file.additions} -{file.deletions})\n"
        f"```{lang}\n{file.diff_text}\n```"
    )


def _parse_file_findings(raw: str, expected_path: str) -> list[Finding]:
    data = json.loads(_strip_json_fences(raw))
    findings: list[Finding] = []
    for item in data.get("findings", []):
        # Normalise category; drop unknown values
        cat = item.get("category", "")
        if cat not in _VALID_CATEGORIES:
            log.warning("unified_invalid_category", category=cat, file=expected_path)
            continue
        # Ensure file path is set (models sometimes omit it for single-file prompts)
        if not item.get("file"):
            item["file"] = expected_path
        try:
            findings.append(Finding(**item))
        except (ValidationError, TypeError):
            log.warning("unified_invalid_finding_skipped", item=item)
    return findings


def make_file_analysis_node(llm: LLMProvider, settings: Settings) -> Callable:
    async def _analyze_file(
        file: FileDiff,
        pr_title: str,
        pr_description: str,
        project_context: str,
    ) -> list[Finding]:
        if not file.diff_text or not file.diff_text.strip():
            return []

        diff = _format_file_diff(file)
        system, user = unified_prompts.build_prompt(
            pr_title, pr_description, diff, project_context=project_context
        )

        last_preview = ""
        for attempt in range(settings.retry_attempts + 1):
            try:
                resp = await llm.acomplete(
                    system=system,
                    user=user,
                    json_mode=True,
                    temperature=settings.temperature,
                )
                last_preview = (resp.content or "")[:200]
                findings = _parse_file_findings(resp.content, file.path)
                if findings:
                    log.info(
                        "file_analysis_done",
                        file=file.path,
                        count=len(findings),
                        model=resp.model,
                    )
                return findings
            except json.JSONDecodeError as exc:
                if attempt == settings.retry_attempts:
                    log.error(
                        "file_analysis_json_failed",
                        file=file.path,
                        error=str(exc),
                        response_preview=last_preview,
                    )
                    return []
                log.warning(
                    "file_analysis_retry",
                    file=file.path,
                    attempt=attempt,
                    response_preview=last_preview,
                )
            except Exception as exc:
                log.error("file_analysis_failed", file=file.path, error=str(exc))
                return []

        return []

    async def node(state: ReviewState) -> dict:
        if "analyze" in state.get("completed_passes", []):
            log.info("file_analysis_skipped_already_done")
            return {}

        pr = state.get("pull_request")
        if pr is None:
            return {}

        ctx = state.get("project_context")
        project_context = (
            ctx.retrieve("analysis", settings.context_budget_tokens) if ctx else ""
        )

        files_with_diffs = [f for f in pr.files if f.diff_text and f.diff_text.strip()]
        log.info("file_analysis_start", files=len(files_with_diffs))

        tasks = [
            _analyze_file(f, pr.title, pr.description, project_context)
            for f in files_with_diffs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_findings: list[Finding] = []
        for file, result in zip(files_with_diffs, results):
            if isinstance(result, list):
                all_findings.extend(result)
            else:
                log.error("file_analysis_gather_error", file=file.path, error=str(result))

        log.info("file_analysis_all_done", total_findings=len(all_findings))
        return {"findings": all_findings, "completed_passes": ["analyze"]}

    return node
