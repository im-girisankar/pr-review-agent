import json
from collections.abc import Callable

import structlog

from pr_review_agent.core.settings import Settings
from pr_review_agent.core.state import ReviewState
from pr_review_agent.llm.base import LLMProvider
from pr_review_agent.llm.prompts import synthesis as synthesis_prompts
from pr_review_agent.nodes.analysis import format_diff, _strip_json_fences
from pr_review_agent.output.models import Finding

log = structlog.get_logger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    """
    Drop findings that reference the same file, same category, and
    overlapping line ranges — keeping the highest-severity one.
    """
    # Sort so critical findings win when deduping
    sorted_findings = sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 5), f.file, f.line_start),
    )
    kept: list[Finding] = []
    for candidate in sorted_findings:
        duplicate = any(
            k.file == candidate.file
            and k.category == candidate.category
            and candidate.line_start <= k.line_end
            and candidate.line_end >= k.line_start
            for k in kept
        )
        if not duplicate:
            kept.append(candidate)
    return kept


async def _self_critique(
    findings: list[Finding],
    diff: str,
    llm: LLMProvider,
    settings: Settings,
    project_context: str = "",
) -> list[Finding]:
    """Drop findings that the LLM cannot ground in the actual diff."""
    if not findings:
        return []

    findings_json = json.dumps([f.model_dump() for f in findings], indent=2)
    system, user = synthesis_prompts.build_critique_prompt(
        findings_json, diff, project_context=project_context
    )

    last_content: str | None = None
    for attempt in range(settings.retry_attempts + 1):
        try:
            resp = await llm.acomplete(
                system=system,
                user=user,
                json_mode=True,
                temperature=0.1,
            )
            last_content = resp.content
            data = json.loads(_strip_json_fences(resp.content))
            grounded = {r["index"] for r in data.get("results", []) if r.get("grounded", True)}
            verified = [f for i, f in enumerate(findings) if i in grounded]
            dropped = len(findings) - len(verified)
            if dropped:
                log.info("self_critique_dropped", count=dropped)
            return verified
        except json.JSONDecodeError as exc:
            preview = (last_content or "")[:200]
            if attempt == settings.retry_attempts:
                log.error(
                    "self_critique_failed",
                    error=str(exc),
                    response_preview=preview,
                    response_len=len(last_content or ""),
                )
                return findings  # fail open
            log.warning("self_critique_retry", attempt=attempt, response_preview=preview)
        except Exception as exc:
            log.error("self_critique_failed", error=str(exc))
            return findings  # fail open — return all findings rather than dropping everything

    return findings  # fail open after exhausting retries


async def _generate_summary(
    findings: list[Finding],
    pr_title: str,
    llm: LLMProvider,
    settings: Settings,
    project_context: str = "",
) -> str:
    if not findings:
        return "No significant issues found in this pull request."

    critical_high = [f for f in findings if f.severity in ("critical", "high")]
    system, user = synthesis_prompts.build_summary_prompt(
        title=pr_title,
        findings=findings,
        total=len(findings),
        critical_high=len(critical_high),
        project_context=project_context,
    )
    try:
        resp = await llm.acomplete(system=system, user=user, temperature=0.3)
        return resp.content.strip()
    except Exception as exc:
        log.error("summary_generation_failed", error=str(exc))
        n_files = len({f.file for f in findings})
        n_ch = len(critical_high)
        return (
            f"Found {len(findings)} issue(s) across {n_files} file(s). "
            f"{n_ch} critical/high severity."
        )


def make_synthesis_node(llm: LLMProvider, settings: Settings) -> Callable:
    async def synthesis(state: ReviewState) -> dict:
        raw_findings: list[Finding] = state.get("findings", [])
        pr = state.get("pull_request")
        failed_passes = state.get("failed_passes", [])

        # Stop-and-report: if any analysis pass failed, halt before synthesis so
        # the caller can show the failure and offer to resume. Successful
        # passes' findings are preserved in state for the resume path.
        if failed_passes:
            failed_names = ", ".join(p.get("category", "?") for p in failed_passes)
            log.warning("synthesis_halted_failed_passes", count=len(failed_passes))
            return {
                "final_findings": None,
                "summary": f"Run halted — {len(failed_passes)} pass(es) failed: {failed_names}",
                "errors": [f"halted: {failed_names}"],
            }

        if pr is None:
            log.warning("synthesis_halted_no_pr")
            return {
                "final_findings": None,
                "summary": "Run halted — PR fetch failed.",
                "errors": ["halted: PR fetch failed"],
            }

        log.info("synthesis_start", raw_findings=len(raw_findings))

        ctx = state.get("project_context")
        budget = settings.context_budget_tokens
        critique_context = ctx.retrieve("synthesis_critique", budget) if ctx else ""
        summary_context = ctx.retrieve("synthesis_summary", budget) if ctx else ""

        deduped = _deduplicate(raw_findings)
        log.info("synthesis_deduped", before=len(raw_findings), after=len(deduped))

        if settings.enable_self_critique and pr:
            diff = format_diff(pr)
            verified = await _self_critique(
                deduped, diff, llm, settings, project_context=critique_context
            )
        else:
            verified = deduped

        final = sorted(
            verified,
            key=lambda f: (_SEVERITY_ORDER.get(f.severity, 5), f.file, f.line_start),
        )

        summary = await _generate_summary(
            findings=final,
            pr_title=pr.title if pr else "Unknown PR",
            llm=llm,
            settings=settings,
            project_context=summary_context,
        )

        log.info("synthesis_done", final_findings=len(final))
        return {"final_findings": final, "summary": summary, "errors": []}

    return synthesis
