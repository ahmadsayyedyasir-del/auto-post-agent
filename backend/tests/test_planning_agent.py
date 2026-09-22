"""Unit tests for the Planning Agent, schemas, grounding rules, and retry behaviors."""

from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.agents.planning import PlanningAgent
from backend.app.models.planning import (
    ContentPlan,
    EmptyResearchError,
    PlanningError,
    PlanningRequest,
    PlanningValidationFailedError,
    UngroundedPlanError,
)
from backend.app.models.research import (
    ResearchRequest,
    ResearchResponse,
    Trend,
)
from backend.app.services.llm import LLMProvider, LLMService


# ------------------------------------------------------------------------------
# Fixtures and Helpers
# ------------------------------------------------------------------------------


def create_sample_research_response(trends_count: int = 2) -> ResearchResponse:
    """Create a sample ResearchResponse for testing."""
    sample_request = ResearchRequest(
        niche="Artificial Intelligence",
        audience="AI Engineers and Students",
        platform="linkedin",
        keywords=["agents", "reasoning"],
    )

    trends = [
        Trend(
            topic="Agentic AI in Enterprise Workflows",
            summary="Autonomous multi-agent architectures are replacing traditional workflow scripts across tech companies.",
            relevance_score=0.92,
            source="venturebeat.com",
            source_title="Enterprise Multi-Agent Systems",
            url="https://venturebeat.com/ai/agentic-systems",
            keywords=["Agentic AI", "Enterprise", "Automation"],
        ),
        Trend(
            topic="Small Language Models for Edge Inference",
            summary="Sub-3B parameter models achieve high efficiency and low latency directly on mobile and edge devices.",
            relevance_score=0.85,
            source="techcrunch.com",
            source_title="Edge SLM Breakthrough",
            url="https://techcrunch.com/2026/edge-slms",
            keywords=["SLM", "Edge AI"],
        ),
    ]

    return ResearchResponse(
        request=sample_request,
        trends=trends[:trends_count],
        total_results_found=len(trends[:trends_count]),
        raw_search_count=4,
        search_query_used="Artificial Intelligence agents reasoning latest trends",
        status="success",
    )


class MockPlanningLLMProvider(LLMProvider):
    """Mock LLM provider returning a valid ContentPlan."""

    def __init__(
        self,
        plan_topic: str = "Agentic AI in Enterprise Workflows",
        fail_count: int = 0,
        always_fail: bool = False,
        return_invalid_plan: bool = False,
    ) -> None:
        self.plan_topic = plan_topic
        self.fail_count = fail_count
        self.always_fail = always_fail
        self.return_invalid_plan = return_invalid_plan
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_planning"

    @property
    def model_name(self) -> str:
        return "mock-planning-model"

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
        return ""

    async def generate_structured(
        self,
        schema: type[ContentPlan],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> ContentPlan:
        self.call_count += 1

        if self.always_fail or self.call_count <= self.fail_count:
            raise PlanningError(f"Simulated LLM error on call {self.call_count}")

        if self.return_invalid_plan:
            # Empty angle / key_points invalidation
            return schema(
                topic=self.plan_topic,
                angle="Too short",  # Invalid length < 10
                platform="linkedin",
                audience="Engineers",
                language="English",
                content_type="single_post",
                tone="professional",
                hook_direction="Did you know?",
                key_points=[],  # Invalid min_length < 1
                cta_direction="Share your thoughts below!",
                source_references=["https://venturebeat.com/ai/agentic-systems"],
            )

        return schema(
            topic=self.plan_topic,
            angle="Educational breakdown of how multi-agent architectures differ from single LLM chains",
            platform="linkedin",
            audience="AI Engineers and Students",
            language="English",
            content_type="single_post",
            tone="insightful, educational, and professional",
            hook_direction="Start with the counter-intuitive shift from prompt engineering to agentic workflow orchestration.",
            key_points=[
                "Single LLM calls vs. specialized collaborative agent loops",
                "Why error-correction cycles reduce hallucination by 40%",
                "Practical architecture pattern: Research -> Critic -> Writer",
            ],
            cta_direction="Ask audience: What is the biggest barrier you have faced deploying multi-agent systems?",
            source_references=["https://venturebeat.com/ai/agentic-systems"],
            selected_trend_topic=self.plan_topic,
            reasoning="Highest relevance to AI developers with rich architectural trade-offs to discuss.",
        )


# ------------------------------------------------------------------------------
# 1. Schema Validation Tests
# ------------------------------------------------------------------------------


def test_planning_request_validation() -> None:
    """Verify PlanningRequest default values and constraints."""
    research = create_sample_research_response()
    req = PlanningRequest(
        research=research,
        niche="Artificial Intelligence",
        audience="Developers",
        platform="linkedin",
    )

    assert req.niche == "Artificial Intelligence"
    assert req.audience == "Developers"
    assert req.platform == "linkedin"
    assert req.language == "English"
    assert req.content_goal == "educational"
    assert req.content_type == "single_post"


def test_content_plan_validation_and_constraints() -> None:
    """Verify ContentPlan field validation and min_length constraints."""
    valid_plan = ContentPlan(
        topic="Agentic AI in Enterprise Workflows",
        angle="Detailed comparison of agent frameworks vs prompt chains",
        platform="linkedin",
        audience="AI Engineers",
        language="English",
        content_type="single_post",
        tone="professional",
        hook_direction="Stop treating LLMs like search engines—here is how agents change the game.",
        key_points=["Point 1: State machines", "Point 2: Tool execution"],
        cta_direction="What agent pattern are you using today?",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )
    assert valid_plan.topic == "Agentic AI in Enterprise Workflows"
    assert len(valid_plan.key_points) == 2

    # Validation: key_points must not be empty
    with pytest.raises(ValidationError):
        ContentPlan(
            topic="Valid Topic",
            angle="Valid detailed angle for content",
            platform="linkedin",
            audience="Audience",
            tone="professional",
            hook_direction="Valid hook direction with enough characters",
            key_points=[],  # Empty key points list
            cta_direction="Valid CTA",
        )


# ------------------------------------------------------------------------------
# 2. Planning Agent Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planning_agent_success() -> None:
    """Verify PlanningAgent generates a valid, grounded ContentPlan."""
    research = create_sample_research_response()
    mock_provider = MockPlanningLLMProvider()
    llm_service = LLMService(provider=mock_provider)

    agent = PlanningAgent(llm_service=llm_service)
    request = PlanningRequest(
        research=research,
        niche="Artificial Intelligence",
        audience="AI Engineers",
        platform="linkedin",
        content_goal="thought_leadership",
    )

    plan = await agent.plan(request)

    assert isinstance(plan, ContentPlan)
    assert plan.topic == "Agentic AI in Enterprise Workflows"
    assert plan.platform == "linkedin"
    assert len(plan.key_points) == 3
    assert len(plan.source_references) >= 1
    assert "https://venturebeat.com/ai/agentic-systems" in plan.source_references[0]
    assert mock_provider.call_count == 1


@pytest.mark.asyncio
async def test_planning_agent_empty_research_error() -> None:
    """Verify PlanningAgent raises EmptyResearchError when research data contains no trends."""
    empty_research = ResearchResponse(
        request=ResearchRequest(niche="Niche"),
        trends=[],
        total_results_found=0,
        status="empty",
    )

    mock_provider = MockPlanningLLMProvider()
    llm_service = LLMService(provider=mock_provider)
    agent = PlanningAgent(llm_service=llm_service)

    request = PlanningRequest(
        research=empty_research,
        niche="Artificial Intelligence",
        audience="Developers",
        platform="linkedin",
    )

    with pytest.raises(EmptyResearchError, match="ResearchResponse contains no trends"):
        await agent.plan(request)

    # LLM should never be invoked when research is empty
    assert mock_provider.call_count == 0


@pytest.mark.asyncio
async def test_planning_agent_source_grounding_preservation() -> None:
    """Verify PlanningAgent preserves and maps source references from research trends."""
    research = create_sample_research_response()

    class UngroundedSourceProvider(LLMProvider):
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
            schema: type[ContentPlan],
            prompt: str,
            system_prompt: str | None = None,
            **kwargs: Any,
        ) -> ContentPlan:
            return schema(
                topic="Small Language Models for Edge Inference",
                angle="Why on-device SLMs represent the real enterprise privacy breakthrough",
                platform="linkedin",
                audience="Engineers",
                language="English",
                content_type="single_post",
                tone="analytical",
                hook_direction="Cloud latency is killing your real-time apps. Edge SLMs solve this.",
                key_points=["Edge computing benefits", "Quantization techniques"],
                cta_direction="Are you running local models yet?",
                source_references=["https://fake-hallucinated-url.com/unrelated"],  # Hallucinated
            )

    llm_service = LLMService(provider=UngroundedSourceProvider())
    agent = PlanningAgent(llm_service=llm_service)

    request = PlanningRequest(
        research=research,
        niche="Artificial Intelligence",
        audience="AI Engineers",
        platform="linkedin",
    )

    plan = await agent.plan(request)

    # Agent should sanitize fabricated URLs and replace with the matched research trend URL
    assert "https://techcrunch.com/2026/edge-slms" in plan.source_references[0]
    assert "fake-hallucinated-url" not in plan.source_references[0]


@pytest.mark.asyncio
async def test_planning_agent_retry_and_recovery() -> None:
    """Verify PlanningAgent retries on transient errors and succeeds within retry limit."""
    research = create_sample_research_response()
    # Fails on attempt 1, succeeds on attempt 2
    mock_provider = MockPlanningLLMProvider(fail_count=1)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = PlanningAgent(llm_service=llm_service, max_retries=2)
    request = PlanningRequest(
        research=research,
        niche="Artificial Intelligence",
        audience="Developers",
        platform="linkedin",
    )

    plan = await agent.plan(request)

    assert plan.topic == "Agentic AI in Enterprise Workflows"
    assert mock_provider.call_count == 2


@pytest.mark.asyncio
async def test_planning_agent_retry_exhaustion() -> None:
    """Verify PlanningAgent raises PlanningValidationFailedError when all retries fail."""
    research = create_sample_research_response()
    mock_provider = MockPlanningLLMProvider(always_fail=True)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = PlanningAgent(llm_service=llm_service, max_retries=2)
    request = PlanningRequest(
        research=research,
        niche="Artificial Intelligence",
        audience="Developers",
        platform="linkedin",
    )

    with pytest.raises(PlanningValidationFailedError, match="failed to generate a valid, grounded ContentPlan after 2 attempts"):
        await agent.plan(request)

    assert mock_provider.call_count == 2
