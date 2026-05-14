from pr_review_agent.output.models import Finding, Review

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "informational": "⚪",
}

_CATEGORY_LABEL = {
    "bug": "Bug",
    "security": "Security",
    "performance": "Performance",
    "test_coverage": "Test Coverage",
}


def _finding_block(i: int, f: Finding) -> str:
    emoji = _SEVERITY_EMOJI.get(f.severity, "⚪")
    label = _CATEGORY_LABEL.get(f.category, f.category.title())
    lines = (
        f"### {i}. {emoji} `{f.severity.upper()}` — {f.title}\n"
        f"**Category:** {label}  \n"
        f"**File:** `{f.file}` (lines {f.line_start}–{f.line_end})\n\n"
        f"{f.description}\n"
    )
    if f.suggestion:
        lines += f"\n**Suggestion:** {f.suggestion}\n"
    return lines


def to_markdown(review: Review) -> str:
    parts: list[str] = [
        f"## PR Review — {review.pr_url}\n",
        f"### Summary\n{review.summary}\n",
    ]

    if not review.findings:
        parts.append("### Findings\nNo issues found. ✅\n")
        return "\n".join(parts)

    by_severity: dict[str, list[Finding]] = {}
    for f in review.findings:
        by_severity.setdefault(f.severity, []).append(f)

    order = ["critical", "high", "medium", "low", "informational"]
    parts.append(f"### Findings ({len(review.findings)} total)\n")

    global_i = 1
    for sev in order:
        group = by_severity.get(sev, [])
        for f in group:
            parts.append(_finding_block(global_i, f))
            global_i += 1

    if review.errors:
        parts.append("### Errors\n")
        for err in review.errors:
            parts.append(f"- ⚠️ {err}")

    return "\n".join(parts)
