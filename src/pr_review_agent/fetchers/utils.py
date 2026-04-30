import re

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".sql": "sql",
    ".tf": "terraform",
    ".dockerfile": "dockerfile",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".xml": "xml",
}


def detect_language(file_path: str) -> str | None:
    """Return a language name from a file path extension, or None for unknowns."""
    path = file_path.lower()
    if path.endswith("dockerfile") or path.split("/")[-1].lower() == "dockerfile":
        return "dockerfile"
    dot = path.rfind(".")
    if dot == -1:
        return None
    return _EXTENSION_TO_LANGUAGE.get(path[dot:])


def parse_github_pr_url(identifier: str) -> tuple[str, str, int]:
    """
    Parse a GitHub PR identifier into (owner, repo, pr_number).

    Accepts:
      - Full URL:  https://github.com/owner/repo/pull/123
      - Short form: owner/repo#123
    """
    url_pattern = re.compile(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    )
    short_pattern = re.compile(r"([^/]+)/([^#]+)#(\d+)")

    if m := url_pattern.match(identifier.strip()):
        return m.group(1), m.group(2), int(m.group(3))
    if m := short_pattern.match(identifier.strip()):
        return m.group(1), m.group(2), int(m.group(3))

    raise ValueError(
        f"Unrecognised GitHub PR identifier: {identifier!r}. "
        "Expected 'owner/repo#123' or a full GitHub PR URL."
    )
