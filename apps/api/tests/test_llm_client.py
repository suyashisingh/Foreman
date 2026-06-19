"""Unit tests for the LLM client abstraction (llm_client.py).

GeminiClient is tested with the google-genai client mocked at the module
level — no real API calls are made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.agents.llm_client import GeminiClient, LLMError, LLMResponse, get_llm_client


class _SimpleSchema(BaseModel):
    name: str
    value: int


def _make_mock_response(parsed_obj=None, text_json='{"name":"test","value":42}'):
    """Build a mock response that mimics google-genai's GenerateContentResponse."""
    mock_resp = MagicMock()
    mock_resp.parsed = parsed_obj
    mock_resp.text = text_json
    mock_resp.usage_metadata.prompt_token_count = 10
    mock_resp.usage_metadata.candidates_token_count = 20
    return mock_resp


# ---------------------------------------------------------------------------
# GeminiClient tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_client_calls_generate_content():
    """GeminiClient calls aio.models.generate_content with the right arguments."""
    mock_response = _make_mock_response(parsed_obj=_SimpleSchema(name="test", value=42))
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.agents.llm_client.genai.Client") as MockClient:
        MockClient.return_value.aio = mock_aio
        client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
        result = await client.generate_structured("Hello", _SimpleSchema)

    mock_aio.models.generate_content.assert_called_once()
    call_kwargs = mock_aio.models.generate_content.call_args
    assert call_kwargs.kwargs["model"] == "gemini-2.0-flash"
    assert call_kwargs.kwargs["contents"] == "Hello"
    assert isinstance(result, LLMResponse)


@pytest.mark.asyncio
async def test_gemini_client_returns_parsed_model_from_parsed_attr():
    """When response.parsed is already a schema instance, it is used directly."""
    expected = _SimpleSchema(name="hello", value=99)
    mock_response = _make_mock_response(parsed_obj=expected)
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.agents.llm_client.genai.Client") as MockClient:
        MockClient.return_value.aio = mock_aio
        client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
        resp = await client.generate_structured("prompt", _SimpleSchema)

    assert isinstance(resp.result, _SimpleSchema)
    assert resp.result.name == "hello"
    assert resp.result.value == 99
    assert resp.input_tokens == 10
    assert resp.output_tokens == 20


@pytest.mark.asyncio
async def test_gemini_client_falls_back_to_text_parse():
    """When response.parsed is None, falls back to parsing response.text as JSON."""
    mock_response = _make_mock_response(
        parsed_obj=None,
        text_json='{"name":"fallback","value":7}',
    )
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.agents.llm_client.genai.Client") as MockClient:
        MockClient.return_value.aio = mock_aio
        client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
        resp = await client.generate_structured("prompt", _SimpleSchema)

    assert resp.result.name == "fallback"
    assert resp.result.value == 7


@pytest.mark.asyncio
async def test_gemini_client_retries_on_failure():
    """First call raises; second succeeds — total of 2 calls made."""
    success_resp = _make_mock_response(parsed_obj=_SimpleSchema(name="ok", value=1))
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(
        side_effect=[RuntimeError("transient error"), success_resp]
    )

    with (
        patch("app.agents.llm_client.genai.Client") as MockClient,
        patch("app.agents.llm_client.asyncio.sleep", new_callable=AsyncMock),
    ):
        MockClient.return_value.aio = mock_aio
        client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
        resp = await client.generate_structured("prompt", _SimpleSchema)

    assert mock_aio.models.generate_content.call_count == 2
    assert resp.result.name == "ok"


@pytest.mark.asyncio
async def test_gemini_client_raises_llm_error_after_all_retries():
    """All attempts fail → LLMError is raised."""
    mock_aio = MagicMock()
    mock_aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("always fails")
    )

    with (
        patch("app.agents.llm_client.genai.Client") as MockClient,
        patch("app.agents.llm_client.asyncio.sleep", new_callable=AsyncMock),
    ):
        MockClient.return_value.aio = mock_aio
        client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
        with pytest.raises(LLMError):
            await client.generate_structured("prompt", _SimpleSchema)


# ---------------------------------------------------------------------------
# get_llm_client factory tests
# ---------------------------------------------------------------------------


def test_get_llm_client_returns_gemini_client(monkeypatch):
    """With LLM_PROVIDER=gemini, returns a GeminiClient."""
    monkeypatch.setattr("app.agents.llm_client.settings.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("app.agents.llm_client.settings.GEMINI_API_KEY", "fake")
    monkeypatch.setattr(
        "app.agents.llm_client.settings.GEMINI_MODEL", "gemini-2.0-flash"
    )

    with patch("app.agents.llm_client.genai.Client"):
        client = get_llm_client()

    assert isinstance(client, GeminiClient)


def test_get_llm_client_raises_for_unknown_provider(monkeypatch):
    """An unknown LLM_PROVIDER raises LLMError immediately."""
    monkeypatch.setattr("app.agents.llm_client.settings.LLM_PROVIDER", "openai")
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        get_llm_client()
