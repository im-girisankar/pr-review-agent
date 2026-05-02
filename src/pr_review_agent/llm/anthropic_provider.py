import structlog
from anthropic import AsyncAnthropic, Anthropic

from .base import LLMProvider, LLMResponse

log = structlog.get_logger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2000,
    ) -> None:
        self._client = Anthropic(api_key=api_key)
        self._async_client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        messages, prefix = self._build_messages(user, json_mode)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        if resp.stop_reason == "max_tokens":
            log.warning("anthropic_truncated", model=self._model, tip="increase max_tokens")
        content = prefix + (resp.content[0].text if resp.content else "")
        return LLMResponse(
            content=content,
            model=resp.model,
            tokens_used=resp.usage.input_tokens + resp.usage.output_tokens,
        )

    async def acomplete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        messages, prefix = self._build_messages(user, json_mode)
        resp = await self._async_client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        if resp.stop_reason == "max_tokens":
            log.warning("anthropic_truncated", model=self._model, tip="increase max_tokens")
        content = prefix + (resp.content[0].text if resp.content else "")
        return LLMResponse(
            content=content,
            model=resp.model,
            tokens_used=resp.usage.input_tokens + resp.usage.output_tokens,
        )

    @staticmethod
    def _build_messages(user: str, json_mode: bool) -> tuple[list[dict], str]:
        """
        For json_mode, uses the assistant-turn prefill technique:
        seeding the response with '{' forces valid JSON output.
        """
        messages: list[dict] = [{"role": "user", "content": user}]
        if json_mode:
            messages.append({"role": "assistant", "content": "{"})
            return messages, "{"
        return messages, ""
