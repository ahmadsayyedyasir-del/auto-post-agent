"""Centralized LLM service orchestrator managing provider dispatch and bounded retries."""

import asyncio
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.exceptions import (
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMResponseError,
    LLMRetryExhaustedError,
)
from backend.app.services.llm.providers.groq import GroqProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """Central service facade decoupling agents from direct LLM provider implementations."""

    _PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
        "groq": GroqProvider,
    }

    def __init__(
        self,
        settings: Settings | None = None,
        provider: LLMProvider | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._max_retries = (
            max_retries
            if max_retries is not None
            else getattr(self._settings, "llm_max_retries", 3)
        )

        if provider is not None:
            self._provider = provider
        else:
            self._provider = self._initialize_provider(self._settings)

    def _initialize_provider(self, settings: Settings) -> LLMProvider:
        """Instantiate configured LLM provider from settings."""
        provider_key = (settings.llm_provider or "").lower().strip()

        if provider_key not in self._PROVIDER_REGISTRY:
            supported = ", ".join(self._PROVIDER_REGISTRY.keys())
            raise LLMConfigurationError(
                f"Unsupported LLM provider '{provider_key}'. Supported providers: [{supported}]"
            )

        if provider_key == "groq":
            return GroqProvider(
                api_key=settings.groq_api_key,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )

        # Future provider extensions can be added here
        raise LLMConfigurationError(f"Provider '{provider_key}' factory not implemented.")

    @property
    def provider(self) -> LLMProvider:
        """Return the active provider instance."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Return the active provider identifier."""
        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        """Return the active model identifier."""
        return self._provider.model_name

    @property
    def max_retries(self) -> int:
        """Return the maximum retry limit."""
        return self._max_retries

    async def _execute_with_retry(self, coroutine_func, *args: Any, **kwargs: Any) -> Any:
        """Execute a provider call with bounded retry handling for transient errors."""
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return await coroutine_func(*args, **kwargs)
            except (LLMConfigurationError, LLMResponseError):
                # Non-transient errors: do not retry
                raise
            except LLMProviderError as err:
                last_exception = err
                logger.warning(
                    "LLM provider call failed (attempt %d/%d): %s",
                    attempt,
                    self._max_retries,
                    err,
                )
                if attempt < self._max_retries:
                    # Bounded exponential backoff: 0.2s, 0.4s, 0.8s...
                    delay = 0.2 * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
            except Exception as err:
                # Unexpected exceptions wrapped in LLMProviderError
                last_exception = LLMProviderError(f"Unexpected error: {err}", original_error=err)
                logger.error("Unexpected error in LLM execution: %s", err)
                if attempt < self._max_retries:
                    delay = 0.2 * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        raise LLMRetryExhaustedError(
            f"LLM request failed after {self._max_retries} attempts: {last_exception}",
            original_error=last_exception,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate text output using the active LLM provider.

        Args:
            prompt: User or task prompt.
            system_prompt: Optional system prompt.
            **kwargs: Extra parameters passed to provider.

        Returns:
            Generated text string.
        """
        return await self._execute_with_retry(
            self._provider.generate,
            prompt=prompt,
            system_prompt=system_prompt,
            **kwargs,
        )

    async def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Generate structured Pydantic output using the active LLM provider.

        Args:
            schema: Target Pydantic model.
            prompt: User or task prompt.
            system_prompt: Optional system prompt.
            **kwargs: Extra parameters passed to provider.

        Returns:
            An instance of the requested schema model.
        """
        return await self._execute_with_retry(
            self._provider.generate_structured,
            schema=schema,
            prompt=prompt,
            system_prompt=system_prompt,
            **kwargs,
        )


def get_llm_service(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> LLMService:
    """Factory helper to obtain an LLMService instance."""
    return LLMService(settings=settings, provider=provider)
