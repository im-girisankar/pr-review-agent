from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int | None = None


class LLMProvider(ABC):
    """Abstract base for LLM backends."""

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Synchronous completion."""

    @abstractmethod
    async def acomplete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Async completion (used for parallel passes)."""
