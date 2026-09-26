"""Unit tests for the LLM service layer, providers, and retry behaviors."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from backend.app.config import Settings
from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.exceptions import (
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMResponseError,
    LLMRetryExhaustedError,
)
from backend.app.services.llm.providers.groq import GroqProvider
from backend.app.services.llm.service import LLMService, get_llm_service


class SampleLLMResponse(BaseModel):
    """Sample schema for structured output verification."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


class MockLLMProvider(LLMProvider):
    """In-memory mock provider for unit testing LLMService behaviors."""

    def __init__(
        self,
        provider_name: str = "mock",
        model_name: str = "mock-model",
        fail_count: int = 0,
        always_fail: bool = False,
    ) -> None:
        self._provider_name = provider_name
        self._model_name = model_name
        self.call_count = 0
        self.fail_count = fail_count
        self.always_fail = always_fail

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        self.call_count += 1
        if self.always_fail or self.call_count <= self.fail_count:
            raise LLMProviderError(f"Mock failure on attempt {self.call_count}")
        return f"Response to: {prompt}"

    async def generate_structured(
        self,
        schema: type[SampleLLMResponse],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> SampleLLMResponse:
        self.call_count += 1
        if self.always_fail or self.call_count <= self.fail_count:
            raise LLMProviderError(f"Mock failure on attempt {self.call_count}")
        return schema(answer="mocked structured answer", confidence=0.95)


# ------------------------------------------------------------------------------
# 1. Configuration Tests
# ------------------------------------------------------------------------------


def test_settings_llm_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default LLM settings in Settings model."""
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "llama-3.3-70b-versatile"
    assert settings.llm_temperature == 0.2
    assert settings.llm_max_retries == 3
    assert settings.groq_api_key is None or isinstance(settings.groq_api_key, str)


def test_settings_custom_llm_configuration() -> None:
    """Verify custom LLM settings loading."""
    settings = Settings(
        llm_provider="groq",
        llm_model="custom-model",
        llm_temperature=0.7,
        llm_max_tokens=1024,
        llm_max_retries=5,
        groq_api_key="gsk_test_mock_key",
    )
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "custom-model"
    assert settings.llm_temperature == 0.7
    assert settings.llm_max_tokens == 1024
    assert settings.llm_max_retries == 5
    assert settings.groq_api_key == "gsk_test_mock_key"


# ------------------------------------------------------------------------------
# 2. Provider Abstraction & Initialization Tests
# ------------------------------------------------------------------------------


def test_groq_provider_missing_api_key() -> None:
    """Verify GroqProvider raises LLMConfigurationError when API key is missing."""
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY is missing"):
        GroqProvider(api_key=None)

    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY is missing"):
        GroqProvider(api_key="")

    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY is missing"):
        GroqProvider(api_key="   ")


def test_service_unsupported_provider() -> None:
    """Verify LLMService raises LLMConfigurationError for unknown providers."""
    settings = Settings(llm_provider="unsupported_provider_xyz")
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM provider"):
        LLMService(settings=settings)


def test_service_initialization_with_injected_provider() -> None:
    """Verify LLMService can be initialized with an injected provider instance."""
    mock_provider = MockLLMProvider(provider_name="custom_mock", model_name="model-1")
    service = LLMService(provider=mock_provider, max_retries=2)

    assert service.provider_name == "custom_mock"
    assert service.model_name == "model-1"
    assert service.max_retries == 2


@patch("backend.app.services.llm.providers.groq.ChatGroq")
def test_service_initialization_with_groq_settings(mock_chat_groq: MagicMock) -> None:
    """Verify LLMService initializes GroqProvider from settings."""
    settings = Settings(
        llm_provider="groq",
        groq_api_key="gsk_valid_mock_key",
        llm_model="llama-3.3-70b-versatile",
        llm_temperature=0.5,
    )
    service = get_llm_service(settings=settings)

    assert service.provider_name == "groq"
    assert service.model_name == "llama-3.3-70b-versatile"
    mock_chat_groq.assert_called_once()


# ------------------------------------------------------------------------------
# 3. Text Generation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_generate_text_success() -> None:
    """Verify normal text generation through LLMService."""
    mock_provider = MockLLMProvider()
    service = LLMService(provider=mock_provider)

    result = await service.generate(prompt="Hello AI", system_prompt="Be helpful")
    assert result == "Response to: Hello AI"
    assert mock_provider.call_count == 1


@pytest.mark.asyncio
@patch("backend.app.services.llm.providers.groq.ChatGroq")
async def test_groq_provider_generate_text(mock_chat_groq_class: MagicMock) -> None:
    """Verify GroqProvider.generate calls ChatGroq.ainvoke and returns text."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Mocked Groq text output"
    mock_client.ainvoke = AsyncMock(return_value=mock_response)
    mock_chat_groq_class.return_value = mock_client

    provider = GroqProvider(api_key="gsk_mock_key", model="llama-3.3-70b-versatile")
    result = await provider.generate(prompt="Explain quantum computing", system_prompt="Act as a physicist")

    assert result == "Mocked Groq text output"
    mock_client.ainvoke.assert_awaited_once()


# ------------------------------------------------------------------------------
# 4. Structured Output Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_generate_structured_success() -> None:
    """Verify structured output parsing into Pydantic schema through LLMService."""
    mock_provider = MockLLMProvider()
    service = LLMService(provider=mock_provider)

    result = await service.generate_structured(
        schema=SampleLLMResponse,
        prompt="Analyze sentiment",
    )
    assert isinstance(result, SampleLLMResponse)
    assert result.answer == "mocked structured answer"
    assert result.confidence == 0.95


@pytest.mark.asyncio
@patch("backend.app.services.llm.providers.groq.ChatGroq")
async def test_groq_provider_generate_structured(mock_chat_groq_class: MagicMock) -> None:
    """Verify GroqProvider.generate_structured uses with_structured_output."""
    mock_client = MagicMock()
    mock_structured_client = MagicMock()
    mock_structured_client.ainvoke = AsyncMock(
        return_value=SampleLLMResponse(answer="structured test response", confidence=0.88)
    )
    mock_client.with_structured_output.return_value = mock_structured_client
    mock_chat_groq_class.return_value = mock_client

    provider = GroqProvider(api_key="gsk_mock_key")
    result = await provider.generate_structured(
        schema=SampleLLMResponse,
        prompt="Score this draft",
    )

    assert isinstance(result, SampleLLMResponse)
    assert result.answer == "structured test response"
    assert result.confidence == 0.88
    mock_client.with_structured_output.assert_called_once_with(SampleLLMResponse)


@pytest.mark.asyncio
@patch("backend.app.services.llm.providers.groq.ChatGroq")
async def test_groq_provider_generate_structured_dict_fallback(mock_chat_groq_class: MagicMock) -> None:
    """Verify GroqProvider parses dictionary into Pydantic schema when returned."""
    mock_client = MagicMock()
    mock_structured_client = MagicMock()
    mock_structured_client.ainvoke = AsyncMock(
        return_value={"answer": "from dict", "confidence": 0.77}
    )
    mock_client.with_structured_output.return_value = mock_structured_client
    mock_chat_groq_class.return_value = mock_client

    provider = GroqProvider(api_key="gsk_mock_key")
    result = await provider.generate_structured(
        schema=SampleLLMResponse,
        prompt="Score this draft",
    )

    assert isinstance(result, SampleLLMResponse)
    assert result.answer == "from dict"
    assert result.confidence == 0.77


@pytest.mark.asyncio
@patch("backend.app.services.llm.providers.groq.ChatGroq")
async def test_groq_provider_generate_structured_validation_error(mock_chat_groq_class: MagicMock) -> None:
    """Verify GroqProvider raises LLMResponseError on invalid structured payload."""
    mock_client = MagicMock()
    mock_structured_client = MagicMock()
    # Invalid confidence value > 1.0 violates Field(le=1.0)
    mock_structured_client.ainvoke = AsyncMock(
        return_value={"answer": "invalid confidence", "confidence": 999.0}
    )
    mock_client.with_structured_output.return_value = mock_structured_client
    mock_chat_groq_class.return_value = mock_client

    provider = GroqProvider(api_key="gsk_mock_key")
    with pytest.raises(LLMResponseError, match="Structured output parsing failed"):
        await provider.generate_structured(
            schema=SampleLLMResponse,
            prompt="Score this draft",
        )


# ------------------------------------------------------------------------------
# 5. Error Handling and Bounded Retry Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_retry_recovery_success() -> None:
    """Verify LLMService retries on transient errors and succeeds within limit."""
    # Fails 2 times, succeeds on 3rd attempt
    mock_provider = MockLLMProvider(fail_count=2)
    service = LLMService(provider=mock_provider, max_retries=3)

    result = await service.generate(prompt="Retry test")
    assert result == "Response to: Retry test"
    assert mock_provider.call_count == 3


@pytest.mark.asyncio
async def test_service_retry_exhaustion() -> None:
    """Verify LLMService stops after max_retries and raises LLMRetryExhaustedError."""
    # Always fails
    mock_provider = MockLLMProvider(always_fail=True)
    service = LLMService(provider=mock_provider, max_retries=3)

    with pytest.raises(LLMRetryExhaustedError, match="failed after 3 attempts"):
        await service.generate(prompt="Will fail")

    assert mock_provider.call_count == 3


@pytest.mark.asyncio
async def test_service_non_transient_error_no_retry() -> None:
    """Verify non-transient LLMResponseError is raised immediately without retries."""
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.generate_structured = AsyncMock(
        side_effect=LLMResponseError("Malformed schema output")
    )
    service = LLMService(provider=mock_provider, max_retries=5)

    with pytest.raises(LLMResponseError, match="Malformed schema output"):
        await service.generate_structured(schema=SampleLLMResponse, prompt="Test")

    # Should have called only once
    assert mock_provider.generate_structured.await_count == 1
