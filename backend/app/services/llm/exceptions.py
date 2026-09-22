"""Custom exception hierarchy for the LLM service layer."""


class LLMError(Exception):
    """Base exception for all LLM service-related errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is missing, invalid, or an unsupported provider is requested."""


class LLMProviderError(LLMError):
    """Raised when an upstream LLM provider fails during invocation or communication."""


class LLMResponseError(LLMError):
    """Raised when the LLM response cannot be parsed into the expected structured format."""


class LLMRetryExhaustedError(LLMError):
    """Raised when bounded retry attempts are exhausted without successful generation."""
