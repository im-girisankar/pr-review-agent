import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pr_review_agent.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    def _make_mock_response(self, content: str, model: str = "gpt-4o", total_tokens: int = 100):
        resp = MagicMock()
        resp.choices[0].message.content = content
        resp.model = model
        resp.usage.total_tokens = total_tokens
        return resp

    def test_complete_returns_llm_response(self):
        with patch("pr_review_agent.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_resp = self._make_mock_response('{"findings": []}')
            MockOpenAI.return_value.chat.completions.create.return_value = mock_resp

            from pr_review_agent.llm.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-fake")
            result = provider.complete("sys", "user", json_mode=True)

        assert isinstance(result, LLMResponse)
        assert result.content == '{"findings": []}'
        assert result.tokens_used == 100

    @pytest.mark.asyncio
    async def test_acomplete_returns_llm_response(self):
        with patch("pr_review_agent.llm.openai_provider.AsyncOpenAI") as MockAsync:
            mock_resp = self._make_mock_response("hello")
            MockAsync.return_value.chat.completions.create = AsyncMock(return_value=mock_resp)

            from pr_review_agent.llm.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-fake")
            result = await provider.acomplete("sys", "user")

        assert result.content == "hello"

    def test_json_mode_sets_response_format(self):
        with patch("pr_review_agent.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_resp = self._make_mock_response("{}")
            MockOpenAI.return_value.chat.completions.create.return_value = mock_resp

            from pr_review_agent.llm.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-fake")
            provider.complete("sys", "user", json_mode=True)

            call_kwargs = MockOpenAI.return_value.chat.completions.create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_retries_on_rate_limit(self):
        from openai import RateLimitError
        with patch("pr_review_agent.llm.openai_provider.OpenAI") as MockOpenAI:
            with patch("pr_review_agent.llm.openai_provider.time.sleep"):
                mock_resp = self._make_mock_response("{}")
                create = MockOpenAI.return_value.chat.completions.create
                create.side_effect = [
                    RateLimitError("rate limit", response=MagicMock(), body={}),
                    mock_resp,
                ]

                from pr_review_agent.llm.openai_provider import OpenAIProvider
                provider = OpenAIProvider(api_key="sk-fake", retry_attempts=1)
                result = provider.complete("sys", "user")

        assert result.content == "{}"
        assert create.call_count == 2

    def test_raises_after_all_retries_exhausted(self):
        from openai import RateLimitError
        with patch("pr_review_agent.llm.openai_provider.OpenAI") as MockOpenAI:
            with patch("pr_review_agent.llm.openai_provider.time.sleep"):
                create = MockOpenAI.return_value.chat.completions.create
                create.side_effect = RateLimitError("rate limit", response=MagicMock(), body={})

                from pr_review_agent.llm.openai_provider import OpenAIProvider
                provider = OpenAIProvider(api_key="sk-fake", retry_attempts=1)
                with pytest.raises(RateLimitError):
                    provider.complete("sys", "user")


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------

class TestAnthropicProvider:
    def _make_mock_response(self, content: str, stop_reason: str = "end_turn"):
        resp = MagicMock()
        resp.content[0].text = content
        resp.model = "claude-sonnet-4-6"
        resp.stop_reason = stop_reason
        resp.usage.input_tokens = 50
        resp.usage.output_tokens = 50
        return resp

    def test_complete_returns_content(self):
        with patch("pr_review_agent.llm.anthropic_provider.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                self._make_mock_response('"findings": []}')
            )

            from pr_review_agent.llm.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-ant-fake")
            result = provider.complete("sys", "user", json_mode=True)

        # json_mode prepends '{' prefix
        assert result.content.startswith("{")
        assert result.tokens_used == 100

    def test_json_mode_uses_prefill(self):
        with patch("pr_review_agent.llm.anthropic_provider.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                self._make_mock_response('"key": "val"}')
            )

            from pr_review_agent.llm.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-ant-fake")
            provider.complete("sys", "user", json_mode=True)

            call_kwargs = MockAnthropic.return_value.messages.create.call_args[1]
            messages = call_kwargs["messages"]
            assert messages[-1] == {"role": "assistant", "content": "{"}

    @pytest.mark.asyncio
    async def test_acomplete_async(self):
        with patch("pr_review_agent.llm.anthropic_provider.AsyncAnthropic") as MockAsync:
            MockAsync.return_value.messages.create = AsyncMock(
                return_value=self._make_mock_response("hello")
            )

            from pr_review_agent.llm.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-ant-fake")
            result = await provider.acomplete("sys", "user")

        assert result.content == "hello"


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    def _make_mock_response(self, content: str):
        resp = MagicMock()
        resp.message.content = content
        return resp

    def _make_provider(self):
        with patch("pr_review_agent.llm.ollama_provider.Client") as MockClient:
            MockClient.return_value.list.return_value = MagicMock(models=[])
            with patch("pr_review_agent.llm.ollama_provider.AsyncClient"):
                from pr_review_agent.llm.ollama_provider import OllamaProvider
                return OllamaProvider(model="llama3.1:8b"), MockClient

    def test_complete_returns_content(self):
        with patch("pr_review_agent.llm.ollama_provider.Client") as MockClient:
            with patch("pr_review_agent.llm.ollama_provider.AsyncClient"):
                MockClient.return_value.list.return_value = MagicMock(models=[])
                MockClient.return_value.chat.return_value = self._make_mock_response('{"findings":[]}')

                from pr_review_agent.llm.ollama_provider import OllamaProvider
                provider = OllamaProvider(model="llama3.1:8b")
                result = provider.complete("sys", "user", json_mode=True)

        assert result.content == '{"findings":[]}'
        assert result.model == "llama3.1:8b"

    def test_json_mode_sets_format(self):
        with patch("pr_review_agent.llm.ollama_provider.Client") as MockClient:
            with patch("pr_review_agent.llm.ollama_provider.AsyncClient"):
                MockClient.return_value.list.return_value = MagicMock(models=[])
                MockClient.return_value.chat.return_value = self._make_mock_response("{}")

                from pr_review_agent.llm.ollama_provider import OllamaProvider
                provider = OllamaProvider(model="llama3.1:8b")
                provider.complete("sys", "user", json_mode=True)

                call_kwargs = MockClient.return_value.chat.call_args[1]
                assert call_kwargs.get("format") == "json"

    def test_no_format_when_json_mode_false(self):
        with patch("pr_review_agent.llm.ollama_provider.Client") as MockClient:
            with patch("pr_review_agent.llm.ollama_provider.AsyncClient"):
                MockClient.return_value.list.return_value = MagicMock(models=[])
                MockClient.return_value.chat.return_value = self._make_mock_response("text")

                from pr_review_agent.llm.ollama_provider import OllamaProvider
                provider = OllamaProvider(model="llama3.1:8b")
                provider.complete("sys", "user", json_mode=False)

                call_kwargs = MockClient.return_value.chat.call_args[1]
                assert "format" not in call_kwargs

    @pytest.mark.asyncio
    async def test_acomplete_async(self):
        with patch("pr_review_agent.llm.ollama_provider.Client") as MockClient:
            with patch("pr_review_agent.llm.ollama_provider.AsyncClient") as MockAsync:
                MockClient.return_value.list.return_value = MagicMock(models=[])
                MockAsync.return_value.chat = AsyncMock(
                    return_value=self._make_mock_response("async result")
                )

                from pr_review_agent.llm.ollama_provider import OllamaProvider
                provider = OllamaProvider(model="llama3.1:8b")
                result = await provider.acomplete("sys", "user")

        assert result.content == "async result"
