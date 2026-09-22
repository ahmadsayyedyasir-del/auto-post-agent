"""Abstract base provider interface for LLM operations."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract interface that all concrete LLM provider adapters must implement."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a raw text response for the given prompt.

        Args:
            prompt: User or task prompt.
            system_prompt: Optional system prompt to instruct model behavior.
            **kwargs: Additional provider-specific runtime overrides.

        Returns:
            The generated text response string.

        Raises:
            LLMProviderError: If the upstream provider request fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> T:
        """Generate a structured response parsed into the specified Pydantic schema.

        Args:
            schema: Pydantic model class to parse response into.
            prompt: User or task prompt.
            system_prompt: Optional system prompt.
            **kwargs: Additional provider-specific runtime overrides.

        Returns:
            An instance of the specified Pydantic schema model.

        Raises:
            LLMProviderError: If the upstream provider request fails.
            LLMResponseError: If response cannot be parsed into the schema.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name identifier of the provider."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the configured model name."""
        raise NotImplementedError
