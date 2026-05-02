import structlog
from ollama import AsyncClient, Client

from .base import LLMProvider, LLMResponse

log = structlog.get_logger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        max_tokens: int = 2000,
    ) -> None:
        self._client = Client(host=base_url)
        self._async_client = AsyncClient(host=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._check_availability()

    def _check_availability(self) -> None:
        try:
            result = self._client.list()
            pulled = [m.model for m in result.models]
            if self._model not in pulled:
                log.warning(
                    "ollama_model_not_pulled",
                    model=self._model,
                    available=pulled,
                    tip=f"Run: ollama pull {self._model}",
                )
        except Exception as exc:
            log.warning("ollama_unreachable", error=str(exc))

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        resp = self._client.chat(**self._build_kwargs(system, user, json_mode, temperature))
        return LLMResponse(content=resp.message.content or "", model=self._model)

    async def acomplete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        resp = await self._async_client.chat(
            **self._build_kwargs(system, user, json_mode, temperature)
        )
        return LLMResponse(content=resp.message.content or "", model=self._model)

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
            "options": {"temperature": temperature, "num_predict": self._max_tokens},
        }
        if json_mode:
            kwargs["format"] = "json"
        return kwargs
