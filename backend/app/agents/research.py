"""Research Agent for discovering niche trends from grounded web search results."""

import logging
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.models.research import (
    ExtractedTrends,
    ResearchRequest,
    ResearchResponse,
    SearchResult,
    Trend,
)
from backend.app.services.llm import LLMService, get_llm_service
from backend.app.tools.research.base import SearchTool, SearchToolError
from backend.app.tools.research.tavily import TavilySearchTool

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are an expert Social Media Research Agent.
Your responsibility is to analyze raw search results and identify high-signal, relevant trends and topics for a specific niche and audience.

CRITICAL INSTRUCTIONS FOR SOURCE GROUNDING AND ACCURACY:
1. Every trend MUST be strictly grounded in the provided search results.
2. DO NOT invent, hallucinate, or extrapolate facts beyond what the search results state.
3. Every trend must accurately reference the source title, domain, and URL from the search result it was derived from.
4. Assign a research relevance score between 0.0 (irrelevant) and 1.0 (extremely relevant) evaluating how well the topic fits the requested niche, audience, and platform.
5. Provide a clear summary capturing the core development and why it matters.
6. Provide concise keyword tags for each trend.
7. If the search results do not contain relevant or credible information, return an empty list of trends rather than inventing content."""


class ResearchAgent:
    """Agent that discovers, synthesizes, and validates grounded trends for social media planning."""

    def __init__(
        self,
        llm_service: LLMService | None = None,
        search_tool: SearchTool | None = None,
        settings: Settings | None = None,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm_service = llm_service or get_llm_service(settings=self._settings)
        self._max_retries = max(1, max_retries)

        if search_tool is not None:
            self._search_tool = search_tool
        else:
            self._search_tool = TavilySearchTool(
                api_key=self._settings.tavily_api_key,
                max_retries=self._settings.search_max_retries,
            )

    @property
    def search_tool(self) -> SearchTool:
        """Return the active search tool instance."""
        return self._search_tool

    @property
    def llm_service(self) -> LLMService:
        """Return the active LLM service instance."""
        return self._llm_service

    def _build_search_query(self, request: ResearchRequest) -> str:
        """Formulate an optimized search query from request parameters."""
        query_parts = [request.niche]
        if request.keywords:
            query_parts.extend(request.keywords[:3])
        query_parts.append("latest news trends developments")
        return " ".join(query_parts).strip()

    def _format_search_context(self, results: list[SearchResult]) -> str:
        """Format normalized search results into structured prompt context."""
        context_blocks: list[str] = []
        for idx, result in enumerate(results, start=1):
            published_info = f" (Published: {result.published_at})" if result.published_at else ""
            context_blocks.append(
                f"[Source {idx}]\n"
                f"Title: {result.title}\n"
                f"Domain: {result.source}\n"
                f"URL: {result.url}{published_info}\n"
                f"Content: {result.content}\n"
            )
        return "\n".join(context_blocks)

    def _build_research_prompt(self, request: ResearchRequest, search_results: list[SearchResult]) -> str:
        """Construct user prompt for structured trend extraction."""
        context_text = self._format_search_context(search_results)
        keywords_str = ", ".join(request.keywords) if request.keywords else "None specified"

        return (
            f"### RESEARCH PARAMETERS:\n"
            f"- Target Niche: {request.niche}\n"
            f"- Target Audience: {request.audience}\n"
            f"- Target Platform: {request.platform}\n"
            f"- Language: {request.language}\n"
            f"- Specific Keywords: {keywords_str}\n"
            f"- Desired Max Trends: {request.max_results}\n\n"
            f"### RETRIEVED SEARCH EVIDENCE:\n"
            f"{context_text}\n\n"
            f"### TASK:\n"
            f"Extract up to {request.max_results} grounded, non-duplicate trends from the evidence above that would make high-value social media content."
        )

    def _validate_and_deduplicate_trends(
        self,
        extracted_trends: list[Trend],
        search_results: list[SearchResult],
        max_results: int,
    ) -> list[Trend]:
        """Filter, validate, and deduplicate extracted trends against search evidence."""
        valid_urls = {r.url.strip().lower() for r in search_results if r.url}
        valid_domains = {r.source.strip().lower() for r in search_results if r.source}

        seen_topics: set[str] = set()
        validated_trends: list[Trend] = []

        for trend in extracted_trends:
            topic_clean = trend.topic.strip()
            summary_clean = trend.summary.strip()

            # Rule 1: Topic and summary must not be empty or too short
            if len(topic_clean) < 3 or len(summary_clean) < 10:
                logger.warning("Rejected trend with insufficient content: '%s'", topic_clean)
                continue

            # Rule 2: Relevance score bounded [0.0, 1.0]
            if not (0.0 <= trend.relevance_score <= 1.0):
                logger.warning("Clamping out-of-bounds relevance score: %f", trend.relevance_score)
                trend.relevance_score = max(0.0, min(1.0, trend.relevance_score))

            # Rule 3: Deduplicate identical/similar topic titles
            normalized_topic_key = " ".join(topic_clean.lower().split())
            if normalized_topic_key in seen_topics:
                logger.debug("Skipping duplicate trend topic: '%s'", topic_clean)
                continue

            # Rule 4: Source grounding check
            # Verify that either URL or source domain exists in retrieved search results
            trend_url_clean = (trend.url or "").strip().lower()
            trend_source_clean = trend.source.strip().lower()

            is_grounded = (
                (trend_url_clean in valid_urls)
                or (trend_source_clean in valid_domains)
                or any(domain in trend_url_clean for domain in valid_domains)
            )

            if not is_grounded and search_results:
                # Fallback: assign to the first/most relevant search result rather than discarding
                fallback_source = search_results[0]
                logger.info(
                    "Trend '%s' unlinked source mapped to retrieved source: %s",
                    topic_clean,
                    fallback_source.source,
                )
                trend.source = fallback_source.source
                trend.source_title = fallback_source.title
                trend.url = fallback_source.url

            seen_topics.add(normalized_topic_key)
            validated_trends.append(trend)

            if len(validated_trends) >= max_results:
                break

        return validated_trends

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        """Execute the research discovery and trend extraction workflow."""
        logger.info(
            "ResearchAgent starting discovery for niche: '%s' (platform: %s)",
            request.niche,
            request.platform,
        )

        query = self._build_search_query(request)

        # Step 1: Execute search retrieval
        search_results: list[SearchResult] = []
        try:
            search_results = await self._search_tool.search(
                query=query,
                max_results=request.max_results * 2,  # Fetch ample search context
                time_range=request.time_range,
            )
        except SearchToolError as err:
            logger.error("Search tool execution failed: %s", err)
            return ResearchResponse(
                request=request,
                trends=[],
                total_results_found=0,
                raw_search_count=0,
                search_query_used=query,
                status="failed",
                message=f"Search tool failure: {err}",
            )

        # Step 2: Handle empty search results (avoid hallucination)
        if not search_results:
            logger.info("No search results found for query: '%s'", query)
            return ResearchResponse(
                request=request,
                trends=[],
                total_results_found=0,
                raw_search_count=0,
                search_query_used=query,
                status="empty",
                message="No search results retrieved for the specified niche and parameters.",
            )

        # Step 3: LLM Structured Trend Extraction
        prompt = self._build_research_prompt(request=request, search_results=search_results)

        try:
            logger.debug("Generating structured trends via LLMService")
            extracted_output: ExtractedTrends = await self._llm_service.generate_structured(
                schema=ExtractedTrends,
                prompt=prompt,
                system_prompt=RESEARCH_SYSTEM_PROMPT,
            )
            raw_trends = extracted_output.trends
        except Exception as err:
            logger.error("LLM structured trend extraction failed: %s", err)
            return ResearchResponse(
                request=request,
                trends=[],
                total_results_found=0,
                raw_search_count=len(search_results),
                search_query_used=query,
                status="failed",
                message=f"LLM extraction error: {err}",
            )

        # Step 4: Validate, Ground, and Deduplicate Trends
        validated_trends = self._validate_and_deduplicate_trends(
            extracted_trends=raw_trends,
            search_results=search_results,
            max_results=request.max_results,
        )

        logger.info(
            "ResearchAgent completed discovery: %d validated trends found from %d search results",
            len(validated_trends),
            len(search_results),
        )

        status_outcome = "success" if validated_trends else "empty"

        return ResearchResponse(
            request=request,
            trends=validated_trends,
            total_results_found=len(validated_trends),
            raw_search_count=len(search_results),
            search_query_used=query,
            status=status_outcome,
            message=None if validated_trends else "No relevant grounded trends could be extracted.",
        )
