from openai import AsyncOpenAI, OpenAI, RateLimitError

from .openai_provider import OpenAIProvider

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAIProvider):
    """
    Groq-hosted inference. Uses the OpenAI-compatible Groq API.
    Recommended models: llama-3.3-70b-versatile, llama3-8b-8192
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 2000,
        retry_attempts: int = 2,
    ) -> None:
        # Bypass OpenAIProvider.__init__ and set clients directly with Groq base URL
        self._client = OpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
        self._async_client = AsyncOpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
        self._model = model
        self._max_tokens = max_tokens
        self._retry_attempts = retry_attempts
