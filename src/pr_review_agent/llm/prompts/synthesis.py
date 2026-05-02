_CRITIQUE_SYSTEM_HEAD = "You are a code review quality checker."

_CRITIQUE_SYSTEM_TAIL = """\
 Your job is to verify that each finding \
is accurately grounded in the diff — not hallucinated or based on code outside \
the diff.

For each finding, answer: does the specific issue described actually appear at \
the stated file and line range in the diff?

Return valid JSON:
{
  "results": [
    {
      "index": <int>,
      "grounded": true|false,
      "reasoning": "<one sentence>"
    }
  ]
}

Be strict. If the file or lines are not in the diff, grounded must be false.\
"""

_CRITIQUE_USER_TEMPLATE = """\
Findings to verify:
{findings_json}

Diff:
{diff}

Verify each finding against the diff.\
"""

_SUMMARY_SYSTEM_HEAD = "You are a staff engineer writing a concise code review summary."

_SUMMARY_SYSTEM_TAIL = """\
 \
Write 2-3 sentences covering: overall quality, the most important issues, \
and a clear recommendation (approve / approve with nits / request changes).\
"""

_SUMMARY_USER_TEMPLATE = """\
Pull Request: {title}

Findings ({total} total, {critical_high} critical/high severity):
{finding_list}

Write the summary.\
"""


def build_critique_prompt(
    findings_json: str,
    diff: str,
    project_context: str = "",
) -> tuple[str, str]:
    ctx_block = (
        f"\n<project_context>\n{project_context.strip()}\n</project_context>"
        if project_context.strip()
        else ""
    )
    system = _CRITIQUE_SYSTEM_HEAD + ctx_block + _CRITIQUE_SYSTEM_TAIL
    return system, _CRITIQUE_USER_TEMPLATE.format(
        findings_json=findings_json,
        diff=diff,
    )


def build_summary_prompt(
    title: str,
    findings: list,
    total: int,
    critical_high: int,
    project_context: str = "",
) -> tuple[str, str]:
    ctx_block = (
        f"\n<project_context>\n{project_context.strip()}\n</project_context>"
        if project_context.strip()
        else ""
    )
    system = _SUMMARY_SYSTEM_HEAD + ctx_block + _SUMMARY_SYSTEM_TAIL
    finding_list = "\n".join(
        f"- [{f.severity.upper()}] {f.title} ({f.file})" for f in findings[:10]
    )
    return system, _SUMMARY_USER_TEMPLATE.format(
        title=title,
        total=total,
        critical_high=critical_high,
        finding_list=finding_list or "None",
    )
