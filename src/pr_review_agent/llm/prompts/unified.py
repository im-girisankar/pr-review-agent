_SYSTEM = """\
You are an expert code reviewer. Analyze the diff for a single file and report \
all issues: bugs, security vulnerabilities, performance problems, and missing test coverage.

Return valid JSON matching this schema exactly:
{
  "findings": [
    {
      "category": "bug|security|performance|test_coverage",
      "severity": "critical|high|medium|low|informational",
      "file": "<path from diff header>",
      "line_start": <int>,
      "line_end": <int>,
      "title": "<max 80 chars>",
      "description": "<clear explanation>",
      "suggestion": "<concrete fix>"
    }
  ]
}

Category guide:
- bug: crashes, null dereferences, logic errors, resource leaks, incorrect API usage
- security: injection, auth bypass, hardcoded secrets, insecure crypto, data exposure
- performance: N+1 queries, unnecessary allocations, blocking I/O, missing indexes
- test_coverage: new or changed logic that has no corresponding test

Only report issues directly visible in the added/changed lines (+).
Return {"findings": []} if no issues are found.\
"""

_USER_TEMPLATE = """\
Pull Request: {title}
Description: {description}

File diff:
{diff}

Identify all issues in this file.\
"""


def build_prompt(
    title: str,
    description: str,
    diff: str,
    project_context: str = "",
) -> tuple[str, str]:
    ctx_block = (
        f"\n<project_context>\n{project_context.strip()}\n</project_context>"
        if project_context.strip()
        else ""
    )
    system = _SYSTEM + ctx_block if ctx_block else _SYSTEM
    return system, _USER_TEMPLATE.format(
        title=title,
        description=description or "No description provided.",
        diff=diff,
    )
