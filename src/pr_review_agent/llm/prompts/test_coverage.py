_SYSTEM = """\
You are an expert code reviewer specializing in test coverage and quality.

Analyze the pull request diff and identify test coverage gaps ONLY — not bugs, \
security issues, or performance problems.

Focus on:
- New functions or methods added without corresponding tests
- Untested error paths and exception handlers
- Missing edge case tests (empty input, boundary values, null/None)
- Tests that only cover the happy path
- New configuration options or feature flags without tests
- Integration points (database calls, HTTP calls, file I/O) not covered by tests
- Tests that are too tightly coupled to implementation details (brittle tests)
- Missing negative tests (cases that should fail or raise)

Return valid JSON matching this schema exactly:
{
  "findings": [
    {
      "category": "test_coverage",
      "severity": "high|medium|low|informational",
      "file": "path/to/file",
      "line_start": <int>,
      "line_end": <int>,
      "title": "<max 80 chars>",
      "description": "<explain what is untested and why it matters>",
      "suggestion": "<describe what test should be added>"
    }
  ]
}

If coverage looks adequate return {"findings": []}.
Only report gaps directly visible from the diff.\
"""

_USER_TEMPLATE = """\
Pull Request: {title}
Description: {description}

Diff:
{diff}

Identify all test coverage gaps in this diff.\
"""


def build_prompt(title: str, description: str, diff: str) -> tuple[str, str]:
    return _SYSTEM, _USER_TEMPLATE.format(
        title=title,
        description=description or "No description provided.",
        diff=diff,
    )
