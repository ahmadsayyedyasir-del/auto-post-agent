"""Unit tests for the Research Agent, search tools, and research schemas."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.app.agents.research import ResearchAgent
from backend.app.config import Settings
from backend.app.models.research import (
    ExtractedTrends,
    ResearchRequest,
    ResearchResponse,
    SearchResult,
    Trend,
)
from backend.app.services.llm import LLMProvider, LLMService
from backend.app.tools.research.base import (
    SearchTool,
    SearchToolConfigurationError,
    SearchToolError,
    SearchToolExecutionError,
)
from backend.app.tools.research.mock import MockSearchTool
from backend.app.tools.research.tavily import TavilySearchTool


# ------------------------------------------------------------------------------
# 1. Schema Validation Tests
# ------------------------------------------------------------------------------


def test_research_request_defaults_and_validation() -> None:
    """Verify ResearchRequest default values and field validations."""
    req = ResearchRequest(niche="Artificial Intelligence")
    assert req.niche == "Artificial Intelligence"
    assert req.audience == "AI practitioners, students, and enthusiasts"
    assert req.platform == "linkedin"
    assert req.language == "English"
    assert req.keywords == []
    assert req.max_results == 5
    assert req.time_range == "week"

    # Validation: niche must have at least 2 characters
    with pytest.raises(ValidationError):
        ResearchRequest(niche="A")

    # Validation: max_results must be within [1, 20]
    with pytest.raises(ValidationError):
        ResearchRequest(niche="AI", max_results=0)
    with pytest.raises(ValidationError):
        ResearchRequest(niche="AI", max_results=25)


def test_search_result_validation() -> None:
    """Verify SearchResult model fields and score constraints."""
    result = SearchResult(
        title="New LLM Architecture Released",
        url="https://example.com/llm-news",
        content="Researchers introduced a new sparse attention mechanism.",
        source="example.com",
        score=0.92,
    )
    assert result.title == "New LLM Architecture Released"
    assert result.url == "https://example.com/llm-news"
    assert result.score == 0.92

    # Score constraint [0.0, 1.0]
    with pytest.raises(ValidationError):
        SearchResult(
            title="Title",
            url="https://example.com",
            content="Content",
            score=1.5,
        )


def test_trend_validation_and_relevance_bounds() -> None:
    """Verify Trend validation requirements and relevance score bounds."""
    trend = Trend(
        topic="Agentic Workflows in Enterprise",
        summary="Enterprises are deploying multi-agent systems for workflow automation.",
        relevance_score=0.88,
        source="venturebeat.com",
        source_title="How Agents Automate Work",
        url="https://venturebeat.com/ai/agents",
        keywords=["AI", "Agents"],
    )
    assert trend.topic == "Agentic Workflows in Enterprise"
    assert trend.relevance_score == 0.88

    # Relevance score out of bounds
    with pytest.raises(ValidationError):
        Trend(
            topic="Test Topic",
            summary="Test summary with enough characters",
            relevance_score=1.5,
            source="source.com",
            source_title="Source Title",
        )

    with pytest.raises(ValidationError):
        Trend(
            topic="Test Topic",
            summary="Test summary with enough characters",
            relevance_score=-0.1,
            source="source.com",
            source_title="Source Title",
        )


# ------------------------------------------------------------------------------
# 2. Search Tool Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_search_tool_execution() -> None:
    """Verify MockSearchTool produces normalized search results."""
    mock_tool = MockSearchTool()
    results = await mock_tool.search(query="LangGraph", max_results=3)

    assert len(results) == 3
    assert mock_tool.call_count == 1
    assert mock_tool.last_query == "LangGraph"
    assert all(isinstance(r, SearchResult) for r in results)
    assert results[0].url.startswith("https://")


@pytest.mark.asyncio
async def test_mock_search_tool_failure() -> None:
    """Verify MockSearchTool failure simulation."""
    mock_tool = MockSearchTool(always_fail=True)
    with pytest.raises(SearchToolExecutionError, match="Mock search failure"):
        await mock_tool.search(query="AI")


def test_tavily_search_tool_missing_api_key() -> None:
    """Verify TavilySearchTool raises SearchToolConfigurationError without API key."""
    with pytest.raises(SearchToolConfigurationError, match="TAVILY_API_KEY is missing"):
        TavilySearchTool(api_key=None)

    with pytest.raises(SearchToolConfigurationError, match="TAVILY_API_KEY is missing"):
        TavilySearchTool(api_key="")


@pytest.mark.asyncio
@patch("backend.app.tools.research.tavily.AsyncTavilyClient")
async def test_tavily_search_tool_success(mock_client_class: MagicMock) -> None:
    """Verify TavilySearchTool normalizes raw Tavily API responses."""
    mock_client = MagicMock()
    mock_client.search = AsyncMock(
        return_value={
            "results": [
                {
                    "title": "Agentic AI Breakthrough",
                    "url": "https://techcrunch.com/2026/09/agentic-ai",
                    "content": "DeepMind announces new agent framework.",
                    "published_date": "2026-09-21",
                    "score": 0.95,
                },
                {
                    "title": "LLM Benchmarks",
                    "url": "https://venturebeat.com/ai/benchmarks",
                    "content": "Benchmark results for open source models.",
                    "published_date": "2026-09-20",
                    "score": 0.85,
                },
            ]
        }
    )
    mock_client_class.return_value = mock_client

    tool = TavilySearchTool(api_key="tvly-mock-key")
    results = await tool.search(query="Agentic AI", max_results=2)

    assert len(results) == 2
    assert results[0].title == "Agentic AI Breakthrough"
    assert results[0].source == "techcrunch.com"
    assert results[0].published_at == "2026-09-21"
    assert results[0].score == 0.95
    assert results[1].source == "venturebeat.com"


@pytest.mark.asyncio
@patch("backend.app.tools.research.tavily.AsyncTavilyClient")
async def test_tavily_search_tool_retry_and_exhaustion(mock_client_class: MagicMock) -> None:
    """Verify TavilySearchTool bounded retries on failure."""
    mock_client = MagicMock()
    mock_client.search = AsyncMock(side_effect=Exception("Connection timeout"))
    mock_client_class.return_value = mock_client

    tool = TavilySearchTool(api_key="tvly-mock-key", max_retries=2)

    with pytest.raises(SearchToolExecutionError, match="failed after 2 attempts"):
        await tool.search(query="AI")

    assert mock_client.search.await_count == 2


# ------------------------------------------------------------------------------
# 3. Research Agent Tests
# ------------------------------------------------------------------------------


class MockGroundedLLMProvider(LLMProvider):
    """Mock LLM provider returning structured ExtractedTrends grounded in search results."""

    @property
    def provider_name(self) -> str:
        return "mock_grounded"

    @property
    def model_name(self) -> str:
        return "mock-grounded-model"

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
        return "Unused"

    async def generate_structured(
        self,
        schema: type[ExtractedTrends],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> ExtractedTrends:
        return schema(
            trends=[
                Trend(
                    topic="Agentic AI in Production",
                    summary="Organizations are rapidly adopting autonomous multi-agent systems for customer operations.",
                    relevance_score=0.92,
                    source="techcrunch.com",
                    source_title="Trend 1 in Artificial Intelligence",
                    url="https://techcrunch.com/article-1",
                    keywords=["Agentic AI", "Multi-Agent"],
                ),
                Trend(
                    topic="Small Language Models on Edge Devices",
                    summary="High-efficiency SLMs are running locally on mobile hardware with high performance.",
                    relevance_score=0.85,
                    source="techcrunch.com",
                    source_title="Trend 2 in Artificial Intelligence",
                    url="https://techcrunch.com/article-2",
                    keywords=["SLM", "Edge AI"],
                ),
            ]
        )


@pytest.mark.asyncio
async def test_research_agent_end_to_end_success() -> None:
    """Verify full ResearchAgent discovery workflow returning validated ResearchResponse."""
    mock_search = MockSearchTool()
    mock_llm_provider = MockGroundedLLMProvider()
    llm_service = LLMService(provider=mock_llm_provider)

    agent = ResearchAgent(llm_service=llm_service, search_tool=mock_search)

    request = ResearchRequest(
        niche="Artificial Intelligence",
        audience="AI Engineers",
        platform="linkedin",
        keywords=["agents", "edge AI"],
        max_results=2,
    )

    response = await agent.research(request)

    assert isinstance(response, ResearchResponse)
    assert response.status == "success"
    assert response.total_results_found == 2
    assert response.raw_search_count > 0
    assert len(response.trends) == 2
    assert response.trends[0].topic == "Agentic AI in Production"
    assert response.trends[0].relevance_score == 0.92
    assert response.trends[0].source == "techcrunch.com"
    assert response.trends[1].topic == "Small Language Models on Edge Devices"


@pytest.mark.asyncio
async def test_research_agent_empty_search_results() -> None:
    """Verify ResearchAgent handles empty search results cleanly without hallucination."""
    mock_search = MockSearchTool(results=[])  # Empty search returns
    mock_llm_provider = MockGroundedLLMProvider()
    llm_service = LLMService(provider=mock_llm_provider)

    agent = ResearchAgent(llm_service=llm_service, search_tool=mock_search)

    request = ResearchRequest(niche="Obscure Niche 12345")
    response = await agent.research(request)

    assert response.status == "empty"
    assert response.total_results_found == 0
    assert response.raw_search_count == 0
    assert response.trends == []
    assert "No search results retrieved" in (response.message or "")


@pytest.mark.asyncio
async def test_research_agent_search_failure() -> None:
    """Verify ResearchAgent handles search provider failure gracefully."""
    mock_search = MockSearchTool(always_fail=True)
    mock_llm_provider = MockGroundedLLMProvider()
    llm_service = LLMService(provider=mock_llm_provider)

    agent = ResearchAgent(llm_service=llm_service, search_tool=mock_search)

    request = ResearchRequest(niche="Cybersecurity")
    response = await agent.research(request)

    assert response.status == "failed"
    assert response.total_results_found == 0
    assert "Search tool failure" in (response.message or "")


@pytest.mark.asyncio
async def test_research_agent_trend_deduplication_and_filtering() -> None:
    """Verify ResearchAgent filters duplicates and respects max_results limits."""
    mock_search = MockSearchTool()

    class DuplicateLLMProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "mock"

        @property
        def model_name(self) -> str:
            return "mock-model"

        async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
            return ""

        async def generate_structured(
            self,
            schema: type[ExtractedTrends],
            prompt: str,
            system_prompt: str | None = None,
            **kwargs: Any,
        ) -> ExtractedTrends:
            return schema(
                trends=[
                    # Item 1: Valid
                    Trend(
                        topic="Autonomous Coding Agents",
                        summary="Coding agents now solve complex software engineering tasks reliably.",
                        relevance_score=0.9,
                        source="techcrunch.com",
                        source_title="Trend 1",
                        url="https://techcrunch.com/article-1",
                    ),
                    # Item 2: Duplicate of Item 1 (case-insensitive)
                    Trend(
                        topic="autonomous coding agents",
                        summary="Duplicate item with identical topic name and valid length summary.",
                        relevance_score=0.8,
                        source="techcrunch.com",
                        source_title="Trend 1",
                        url="https://techcrunch.com/article-1",
                    ),
                    # Item 3: Distinct valid item
                    Trend(
                        topic="AI-Assisted Code Review",
                        summary="Automated PR reviewers provide instant feedback on security vulnerabilities.",
                        relevance_score=0.85,
                        source="techcrunch.com",
                        source_title="Trend 2",
                        url="https://techcrunch.com/article-2",
                    ),
                ]
            )

    llm_service = LLMService(provider=DuplicateLLMProvider())
    agent = ResearchAgent(llm_service=llm_service, search_tool=mock_search)

    request = ResearchRequest(niche="Software Engineering", max_results=5)
    response = await agent.research(request)

    # 2 unique, valid trends should remain (duplicate filtered out)
    assert response.status == "success"
    assert len(response.trends) == 2
    assert response.trends[0].topic == "Autonomous Coding Agents"
    assert response.trends[1].topic == "AI-Assisted Code Review"


@pytest.mark.asyncio
async def test_research_agent_source_grounding_fallback() -> None:
    """Verify ResearchAgent ensures unlinked trend sources are mapped to retrieved evidence."""
    mock_search = MockSearchTool(
        results=[
            SearchResult(
                title="AI Chip Innovations",
                url="https://wired.com/ai-chips",
                content="Next gen GPUs bring massive speedup for training.",
                source="wired.com",
                score=0.95,
            )
        ]
    )

    class UnlinkedLLMProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "mock"

        @property
        def model_name(self) -> str:
            return "mock-model"

        async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
            return ""

        async def generate_structured(
            self,
            schema: type[ExtractedTrends],
            prompt: str,
            system_prompt: str | None = None,
            **kwargs: Any,
        ) -> ExtractedTrends:
            return schema(
                trends=[
                    Trend(
                        topic="GPU Acceleration Advancements",
                        summary="Hardware accelerators are increasing model training speed by 4x.",
                        relevance_score=0.88,
                        source="unknown-domain.org",  # Not in search results
                        source_title="Unknown",
                        url="https://unknown-domain.org/foo",
                    )
                ]
            )

    llm_service = LLMService(provider=UnlinkedLLMProvider())
    agent = ResearchAgent(llm_service=llm_service, search_tool=mock_search)

    request = ResearchRequest(niche="Hardware", max_results=1)
    response = await agent.research(request)

    assert response.status == "success"
    assert len(response.trends) == 1
    # Fallback should map it to the retrieved wired.com evidence
    assert response.trends[0].source == "wired.com"
    assert response.trends[0].url == "https://wired.com/ai-chips"
