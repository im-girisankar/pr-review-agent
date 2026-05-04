from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PR sources
    github_pat: str = Field(default="", alias="GITHUB_PAT")
    azure_org: str = Field(default="", alias="AZURE_ORG")
    azure_pat: str = Field(default="", alias="AZURE_PAT")

    # LLM providers
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    # Defaults
    default_provider: str = Field(default="github", alias="DEFAULT_PROVIDER")
    default_llm: str = Field(default="ollama", alias="DEFAULT_LLM")
    default_model: str = Field(default="llama3.1:8b", alias="DEFAULT_MODEL")

    # From config.yaml
    parallel: bool = True
    max_diff_size_kb: int = 500
    temperature: float = 0.2
    max_tokens: int = 2000
    retry_attempts: int = 2
    enable_self_critique: bool = True
    default_format: str = "markdown"
    project_context_path: Path | None = None
    context_budget_tokens: int = 1500
    # "chunked": one LLM call per file, all categories — works with any model size
    # "full": 4 passes on the whole diff — better cross-file reasoning, needs large context
    analysis_mode: str = "chunked"

    @classmethod
    def from_yaml(cls, yaml_path: Path = Path("config.yaml")) -> "Settings":
        overrides: dict = {}
        if yaml_path.exists():
            raw = yaml.safe_load(yaml_path.read_text())
            ctx_cfg = raw.get("context", {}) or {}
            ctx_path = ctx_cfg.get("path")
            overrides = {
                "parallel": raw.get("analysis", {}).get("parallel", True),
                "max_diff_size_kb": raw.get("analysis", {}).get("max_diff_size_kb", 500),
                "temperature": raw.get("llm", {}).get("temperature", 0.2),
                "max_tokens": raw.get("llm", {}).get("max_tokens", 2000),
                "retry_attempts": raw.get("llm", {}).get("retry_attempts", 2),
                "enable_self_critique": raw.get("synthesis", {}).get("enable_self_critique", True),
                "default_format": raw.get("output", {}).get("default_format", "markdown"),
                "context_budget_tokens": ctx_cfg.get("budget_tokens", 1500),
                "analysis_mode": raw.get("analysis", {}).get("mode", "chunked"),
                **({"project_context_path": Path(ctx_path)} if ctx_path else {}),
            }
        return cls(**overrides)
