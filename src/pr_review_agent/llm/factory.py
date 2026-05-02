from pr_review_agent.core.settings import Settings

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


def get_llm(provider: str, settings: Settings, model_override: str | None = None) -> LLMProvider:
    match provider:
        case "openai":
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                model=model_override or settings.default_model,
                max_tokens=settings.max_tokens,
                retry_attempts=settings.retry_attempts,
            )
        case "anthropic":
            return AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=model_override or settings.default_model,
                max_tokens=settings.max_tokens,
            )
        case "ollama":
            return OllamaProvider(
                base_url=settings.ollama_base_url,
                model=model_override or settings.default_model,
                max_tokens=settings.max_tokens,
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {provider}")
