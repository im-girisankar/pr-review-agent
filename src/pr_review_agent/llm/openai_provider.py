import asyncio
import time

import structlog
from openai import AsyncOpenAI, OpenAI, RateLimitError

from .base import LLMProvider, LLMResponse

log = structlog.get_logger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        max_tokens: int = 2000,
        retry_attempts: int = 2,
    ) -> None:
        self._client = OpenAI(api_key=api_key)
        self._async_client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._retry_attempts = retry_attempts

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(system, user, json_mode, temperature)
        for attempt in range(self._retry_attempts + 1):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                return LLMResponse(
                    content=resp.choices[0].message.content or "",
                    model=resp.model,
                    tokens_used=resp.usage.total_tokens if resp.usage else None,
                )
            except RateLimitError:
                if attempt == self._retry_attempts:
                    raise
                wait = 2 ** (attempt + 1)
                log.warning("openai_rate_limited", attempt=attempt, wait_seconds=wait)
                time.sleep(wait)
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def acomplete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(system, user, json_mode, temperature)
        for attempt in range(self._retry_attempts + 1):
            try:
                resp = await self._async_client.chat.completions.create(**kwargs)
                return LLMResponse(
                    content=resp.choices[0].message.content or "",
                    model=resp.model,
                    tokens_used=resp.usage.total_tokens if resp.usage else None,
                )
            except RateLimitError:
                if attempt == self._retry_attempts:
                    raise
                wait = 2 ** (attempt + 1)
                log.warning("openai_rate_limited", attempt=attempt, wait_seconds=wait)
                await asyncio.sleep(wait)
        raise RuntimeError("Unreachable")  # pragma: no cover

    def _build_kwargs(
        self,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
    ) -> dict:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self._max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs
