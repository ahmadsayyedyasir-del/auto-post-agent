"""Mock search tool implementation for offline testing and development."""

from typing import Any

from backend.app.models.research import SearchResult
from backend.app.tools.research.base import SearchTool, SearchToolExecutionError


class MockSearchTool(SearchTool):
    """In-memory mock search tool returning deterministic or configured search results."""

    def __init__(
        self,
        results: list[SearchResult] | None = None,
        fail_count: int = 0,
        always_fail: bool = False,
    ) -> None:
        self.results = results
        self.fail_count = fail_count
        self.always_fail = always_fail
        self.call_count = 0
        self.last_query: str | None = None

    @property
    def tool_name(self) -> str:
        return "mock_search"

    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: str = "week",
        **kwargs: Any,
    ) -> list[SearchResult]:
        self.call_count += 1
        self.last_query = query

        if self.always_fail or self.call_count <= self.fail_count:
            raise SearchToolExecutionError(f"Mock search failure on attempt {self.call_count}")

        if self.results is not None:
            return self.results[:max_results]

        # Generate default deterministic mock results
        return [
            SearchResult(
                title=f"Trend {i+1} in {query}",
                url=f"https://techcrunch.com/article-{i+1}",
                content=f"Detailed analysis regarding {query} developments and practical industry applications item {i+1}.",
                source="techcrunch.com",
                published_at="2026-09-20",
                score=0.9 - (i * 0.1),
            )
            for i in range(max_results)
        ]
