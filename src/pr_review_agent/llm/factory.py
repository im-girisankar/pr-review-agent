from .base import LLMProvider


def get_llm(provider: str, settings: object) -> LLMProvider:
    match provider:
        case "openai":
            raise NotImplementedError("OpenAIProvider not yet implemented")
        case "anthropic":
            raise NotImplementedError("AnthropicProvider not yet implemented")
        case "ollama":
            raise NotImplementedError("OllamaProvider not yet implemented")
        case _:
            raise ValueError(f"Unknown LLM provider: {provider}")
