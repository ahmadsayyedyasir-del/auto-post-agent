"""Tavily search provider adapter implementing SearchTool."""

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from backend.app.models.research import SearchResult
from backend.app.tools.research.base import (
    SearchTool,
    SearchToolConfigurationError,
    SearchToolExecutionError,
)

logger = logging.getLogger(__name__)


class TavilySearchTool(SearchTool):
    """Tavily web search tool adapter returning normalized search results."""

    def __init__(
        self,
        api_key: str | None,
        max_retries: int = 2,
    ) -> None:
        if not api_key or not api_key.strip():
            raise SearchToolConfigurationError(
                "TAVILY_API_KEY is missing. Please set TAVILY_API_KEY in your environment or .env file."
            )

        self._api_key = api_key.strip()
        self._max_retries = max(1, max_retries)
        self._client = AsyncTavilyClient(api_key=self._api_key)

    @property
    def tool_name(self) -> str:
        return "tavily"

    def _extract_domain(self, url: str) -> str:
        """Extract clean domain name from URL."""
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc or parsed.path
            return netloc.replace("www.", "").strip()
        except Exception:
            return "web"

    async def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: str = "week",
        **kwargs: Any,
    ) -> list[SearchResult]:
        """Perform search with bounded retries and normalize results to SearchResult."""
        if not query or not query.strip():
            logger.warning("Empty search query provided to TavilySearchTool")
            return []

        logger.info("Executing Tavily search for query: '%s' (max_results=%d)", query, max_results)

        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                # Map time_range if appropriate
                time_range_param = time_range if time_range in {"day", "week", "month", "year"} else None

                search_kwargs: dict[str, Any] = {
                    "query": query,
                    "max_results": max_results,
                    "search_depth": kwargs.get("search_depth", "basic"),
                    "include_answer": False,
                }
                if time_range_param:
                    search_kwargs["time_range"] = time_range_param

                response = await self._client.search(**search_kwargs)
                raw_results = response.get("results", []) if isinstance(response, dict) else []

                normalized_results: list[SearchResult] = []
                for item in raw_results:
                    url = item.get("url", "").strip()
                    title = item.get("title", "").strip() or "Untitled Source"
                    content = item.get("content", "").strip()
                    published_at = item.get("published_date") or item.get("published_at")
                    score = item.get("score")

                    if not url or not content:
                        continue

                    source_name = self._extract_domain(url)

                    normalized_results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            content=content,
                            published_at=str(published_at) if published_at else None,
                            source=source_name,
                            score=float(score) if score is not None else None,
                        )
                    )

                logger.info(
                    "Tavily search successful: %d normalized results retrieved",
                    len(normalized_results),
                )
                return normalized_results

            except SearchToolConfigurationError:
                raise
            except Exception as err:
                last_error = err
                logger.warning(
                    "Tavily search attempt %d/%d failed: %s",
                    attempt,
                    self._max_retries,
                    err,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * attempt)

        raise SearchToolExecutionError(
            f"Tavily search failed after {self._max_retries} attempts: {last_error}",
            original_error=last_error,
        )
