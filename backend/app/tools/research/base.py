"""Abstract search tool interface and domain exceptions for web research."""

from abc import ABC, abstractmethod
from typing import Any

from backend.app.models.research import SearchResult


class SearchToolError(Exception):
    """Base exception for search tool failures."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class SearchToolConfigurationError(SearchToolError):
    """Raised when search tool configuration or credentials are missing/invalid."""


class SearchToolExecutionError(SearchToolError):
    """Raised when upstream search tool execution fails."""


class SearchTool(ABC):
    """Abstract interface defining the contract for search tool providers."""

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: str = "week",
        **kwargs: Any,
    ) -> list[SearchResult]:
        """Execute a search query and return normalized SearchResult objects.

        Args:
            query: Search query string.
            max_results: Maximum number of search results to return.
            time_range: Time window ("day", "week", "month", "year").
            **kwargs: Extra provider-specific parameters.

        Returns:
            List of normalized SearchResult instances.

        Raises:
            SearchToolError: If search execution fails.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Identifier name of the search tool."""
        raise NotImplementedError
