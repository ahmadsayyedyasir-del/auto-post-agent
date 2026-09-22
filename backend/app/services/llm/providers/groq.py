"""Groq LLM provider implementation using LangChain's ChatGroq."""

import logging
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GroqProvider(LLMProvider):
    """Concrete LLM provider adapter for Groq API."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise LLMConfigurationError(
                "GROQ_API_KEY is missing. Please set GROQ_API_KEY in your environment or .env file."
            )

        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        try:
            self._client = ChatGroq(
                groq_api_key=api_key,
                model_name=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as err:
            raise LLMProviderError(
                f"Failed to initialize Groq client: {err}", original_error=err
            ) from err

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self._model

    def _build_messages(
        self, prompt: str, system_prompt: str | None = None
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return messages

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        messages = self._build_messages(prompt=prompt, system_prompt=system_prompt)
        try:
            logger.debug("Dispatching generation request to Groq (%s)", self._model)
            response = await self._client.ainvoke(messages, **kwargs)
            content = response.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # Handle multi-part content blocks if returned
                return "".join(
                    part if isinstance(part, str) else str(part.get("text", ""))
                    for part in content
                )
            return str(content)
        except Exception as err:
            logger.error("Groq text generation failed: %s", type(err).__name__)
            raise LLMProviderError(
                f"Groq API error during text generation: {err}",
                original_error=err,
            ) from err

    async def generate_structured(
        self,
        schema: type[T],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> T:
        messages = self._build_messages(prompt=prompt, system_prompt=system_prompt)
        try:
            structured_model = self._client.with_structured_output(schema)
            logger.debug(
                "Dispatching structured generation request to Groq (%s) for schema [%s]",
                self._model,
                schema.__name__,
            )
            result = await structured_model.ainvoke(messages, **kwargs)

            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)

            raise LLMResponseError(
                f"Unexpected structured output type from Groq: {type(result).__name__}"
            )
        except (ValidationError, TypeError) as err:
            logger.error(
                "Failed to validate Groq structured output against schema %s",
                schema.__name__,
            )
            raise LLMResponseError(
                f"Structured output parsing failed for schema {schema.__name__}: {err}",
                original_error=err,
            ) from err
        except LLMResponseError:
            raise
        except Exception as err:
            logger.error("Groq structured generation failed: %s", type(err).__name__)
            raise LLMProviderError(
                f"Groq API error during structured generation: {err}",
                original_error=err,
            ) from err
