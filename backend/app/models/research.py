"""Research domain schemas for the AI Social Media Automation Platform."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ResearchRequest(BaseModel):
    """Input parameters for topic and trend discovery."""

    model_config = ConfigDict(extra="ignore")

    niche: str = Field(..., min_length=2, description="Target domain or subject area (e.g., 'Artificial Intelligence')")
    audience: str = Field(default="AI practitioners, students, and enthusiasts", description="Target reader demographic")
    platform: str = Field(default="linkedin", description="Target social platform (e.g., 'linkedin', 'twitter')")
    language: str = Field(default="English", description="Content language")
    keywords: list[str] = Field(default_factory=list, description="Specific focus keywords or sub-topics")
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of trends to discover")
    time_range: Literal["day", "week", "month", "year"] = Field(
        default="week", description="Time window for search freshness"
    )


class SearchResult(BaseModel):
    """Normalized web search result item retrieved by a search tool."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Document or article headline")
    url: str = Field(..., description="Canonical source URL")
    content: str = Field(..., description="Extracted content snippet or summary")
    published_at: str | None = Field(default=None, description="Publication timestamp or date string")
    source: str = Field(default="web", description="Originating domain or provider name")
    score: float | None = Field(default=None, ge=0.0, le=1.0, description="Raw search relevance score")


class Trend(BaseModel):
    """Validated, source-grounded research trend ready for planning."""

    model_config = ConfigDict(extra="ignore")

    topic: str = Field(..., min_length=3, description="Concise trend title or subject")
    summary: str = Field(..., min_length=10, description="Synthesized summary grounded in search evidence")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score to request niche (0.0 to 1.0)")
    source: str = Field(..., description="Source name or domain from search results")
    source_title: str = Field(..., description="Title of the source document")
    url: str | None = Field(default=None, description="Direct URL to source reference")
    reason_for_relevance: str = Field(default="", description="Justification for why this topic fits the niche/audience")
    keywords: list[str] = Field(default_factory=list, description="Associated conceptual tags or hashtags")
    published_at: str | None = Field(default=None, description="Original publication date if known")


class ExtractedTrends(BaseModel):
    """Structured LLM extraction container for researched trends."""

    model_config = ConfigDict(extra="ignore")

    trends: list[Trend] = Field(default_factory=list, description="List of identified, grounded trends")


class ResearchResponse(BaseModel):
    """Complete output payload from the Research Agent."""

    model_config = ConfigDict(extra="ignore")

    request: ResearchRequest = Field(..., description="Original input research parameters")
    trends: list[Trend] = Field(default_factory=list, description="Grounded, deduplicated trend findings")
    total_results_found: int = Field(default=0, ge=0, description="Number of validated trends returned")
    raw_search_count: int = Field(default=0, ge=0, description="Number of raw search results retrieved")
    search_query_used: str = Field(default="", description="Search query executed by the tool")
    status: Literal["success", "empty", "partial", "failed"] = Field(
        default="success", description="Outcome status of the research operation"
    )
    message: str | None = Field(default=None, description="Operational or informational message")
