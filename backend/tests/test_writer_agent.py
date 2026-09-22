"""Unit tests for the Writer Agent, schemas, platform constraints, grounding, and retries."""

from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.agents.writer import WriterAgent
from backend.app.models.content import (
    InvalidPlanError,
    PlatformConstraintError,
    SocialPost,
    UngroundedContentError,
    WriterError,
    WriterRequest,
    WriterValidationFailedError,
)
from backend.app.models.planning import (
    ContentPlan,
    PlanningRequest,
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


def create_sample_content_plan(
    platform: str = "linkedin",
    content_type: str = "single_post",
) -> ContentPlan:
    """Create a sample ContentPlan from Phase 4 for writer testing."""
    return ContentPlan(
        topic="Agentic AI in Enterprise Workflows",
        angle="How multi-agent architectures reduce hallucination and automate complex engineering workflows",
        platform=platform,
        audience="AI Engineers and Tech Leaders",
        language="English",
        content_type=content_type,
        tone="professional, insightful, and actionable",
        hook_direction="Most teams treat LLMs like chatbots. Here is why autonomous agentic loops change the game.",
        key_points=[
            "Moving from prompt engineering to agentic workflow loops",
            "Error-correction cycles reduce operational errors by 40%",
            "The 3-node blueprint: Research -> Plan -> Write",
        ],
        cta_direction="What is the biggest challenge your team faces with multi-agent deployments? Let's discuss below.",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
        selected_trend_topic="Agentic AI in Enterprise Workflows",
        reasoning="High relevance to developers building automated AI pipelines.",
    )


class MockWriterLLMProvider(LLMProvider):
    """Mock LLM provider returning a structured SocialPost."""

    def __init__(
        self,
        content: str | None = None,
        topic: str = "Agentic AI in Enterprise Workflows",
        platform: str = "linkedin",
        fail_count: int = 0,
        always_fail: bool = False,
        return_oversized_tweet: bool = False,
        return_hallucinated_sources: bool = False,
        return_divergent_topic: bool = False,
    ) -> None:
        self.custom_content = content
        self.topic = topic
        self.platform = platform
        self.fail_count = fail_count
        self.always_fail = always_fail
        self.return_oversized_tweet = return_oversized_tweet
        self.return_hallucinated_sources = return_hallucinated_sources
        self.return_divergent_topic = return_divergent_topic
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_writer"

    @property
    def model_name(self) -> str:
        return "mock-writer-model"

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
        return ""

    async def generate_structured(
        self,
        schema: type[SocialPost],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> SocialPost:
        self.call_count += 1

        if self.always_fail or self.call_count <= self.fail_count:
            raise WriterError(f"Simulated LLM generation error on attempt {self.call_count}")

        if self.return_divergent_topic:
            return schema(
                platform=self.platform,
                content="Completely unrelated post about cryptocurrency trading signals and moon tokens.",
                topic="Cryptocurrency Day Trading",
                language="English",
                hashtags=["#crypto", "#trading"],
                cta="Buy now!",
                source_references=[],
            )

        if self.return_oversized_tweet and self.call_count == 1:
            # First attempt returns oversized tweet (>350 chars)
            oversized_text = (
                "Autonomous multi-agent architectures are fundamentally revolutionizing the landscape of enterprise AI. "
                "Instead of single prompt-response chains, agent loops allow iterative reflection and validation. "
                "This reduces errors significantly while automating end-to-end pipelines. "
                "Are you ready for the next evolution in software automation and generative AI systems?"
            )
            return schema(
                platform="twitter",
                content=oversized_text,
                topic=self.topic,
                language="English",
                hashtags=["#AI", "#Agents"],
                cta="What do you think?",
                source_references=["https://venturebeat.com/ai/agentic-systems"],
            )

        sources = (
            ["https://fake-hallucinated-source.com/scam"]
            if self.return_hallucinated_sources
            else ["https://venturebeat.com/ai/agentic-systems"]
        )

        default_linkedin_content = (
            "Most teams treat LLMs like chatbots. Here is why autonomous agentic loops change the game.\n\n"
            "Single prompt-response calls have hit a ceiling. Enterprise engineering teams are moving toward structured multi-agent workflows:\n\n"
            "1. Iterative error correction reduces hallucination by 40%\n"
            "2. Specialized roles outperform single monolithic prompts\n"
            "3. Autonomous loops execute multi-step research and planning\n\n"
            "What is the biggest barrier your team faces when deploying agentic workflows?"
        )

        default_twitter_content = (
            "LLMs as chatbots are old news. Autonomous multi-agent loops are the future.\n\n"
            "• Self-correcting cycles\n"
            "• 40% fewer hallucinations\n"
            "• Research -> Plan -> Write pipelines\n\n"
            "What is your biggest agent deployment challenge?"
        )

        post_content = self.custom_content or (
            default_twitter_content if self.platform in ("twitter", "x") else default_linkedin_content
        )

        return schema(
            platform=self.platform,
            content=post_content,
            topic=self.topic,
            language="English",
            content_type="single_post",
            hashtags=["#AgenticAI", "#MachineLearning", "#SoftwareEngineering"],
            cta="What is your biggest agent deployment challenge?",
            source_references=sources,
        )


# ------------------------------------------------------------------------------
# 1. Schema Validation Tests
# ------------------------------------------------------------------------------


def test_writer_request_defaults_and_overrides() -> None:
    """Verify WriterRequest derives values from ContentPlan or applies explicit overrides."""
    plan = create_sample_content_plan()

    # Default derivation
    req_default = WriterRequest(plan=plan)
    assert req_default.get_effective_platform() == "linkedin"
    assert req_default.get_effective_audience() == "AI Engineers and Tech Leaders"
    assert req_default.get_effective_language() == "English"
    assert "professional" in req_default.get_effective_tone()

    # Explicit override
    req_override = WriterRequest(
        plan=plan,
        platform="twitter",
        audience="Junior Developers",
        language="Spanish",
        tone="casual and punchy",
    )
    assert req_override.get_effective_platform() == "twitter"
    assert req_override.get_effective_audience() == "Junior Developers"
    assert req_override.get_effective_language() == "Spanish"
    assert req_override.get_effective_tone() == "casual and punchy"


def test_social_post_validation_constraints() -> None:
    """Verify SocialPost field constraints and validation."""
    valid_post = SocialPost(
        platform="linkedin",
        content="Insightful post content about agentic architectures...",
        topic="Agentic AI",
        language="English",
        hashtags=["#AI", "#Tech"],
        cta="Share your thoughts!",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
    )
    assert valid_post.platform == "linkedin"
    assert len(valid_post.hashtags) == 2

    # Validation: empty content must fail
    with pytest.raises(ValidationError):
        SocialPost(
            platform="linkedin",
            content="",  # Invalid min_length < 1
            topic="Agentic AI",
        )


# ------------------------------------------------------------------------------
# 2. Writer Agent Execution & Platform Support Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writer_agent_linkedin_generation_success() -> None:
    """Verify WriterAgent generates a structured LinkedIn post adhering to plan."""
    plan = create_sample_content_plan(platform="linkedin")
    mock_provider = MockWriterLLMProvider(platform="linkedin")
    llm_service = LLMService(provider=mock_provider)

    agent = WriterAgent(llm_service=llm_service)
    request = WriterRequest(plan=plan)

    post = await agent.write(request)

    assert isinstance(post, SocialPost)
    assert post.platform == "linkedin"
    assert post.topic == plan.topic
    assert "agentic loops" in post.content.lower()
    assert len(post.hashtags) >= 1
    assert post.hashtags[0].startswith("#")
    assert post.cta is not None
    assert "https://venturebeat.com/ai/agentic-systems" in post.source_references[0]
    assert mock_provider.call_count == 1


@pytest.mark.asyncio
async def test_writer_agent_twitter_generation_success() -> None:
    """Verify WriterAgent generates a concise X / Twitter post under platform bounds."""
    plan = create_sample_content_plan(platform="twitter")
    mock_provider = MockWriterLLMProvider(platform="twitter")
    llm_service = LLMService(provider=mock_provider)

    agent = WriterAgent(llm_service=llm_service)
    request = WriterRequest(plan=plan, platform="twitter")

    post = await agent.write(request)

    assert isinstance(post, SocialPost)
    assert post.platform == "twitter"
    assert len(post.content) <= 350
    assert post.topic == plan.topic
    assert mock_provider.call_count == 1


# ------------------------------------------------------------------------------
# 3. Grounding, Adherence, and Failure Handling Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writer_agent_invalid_plan_fast_fail() -> None:
    """Verify WriterAgent raises InvalidPlanError without invoking LLM when plan is invalid."""
    invalid_plan = ContentPlan.model_construct(
        topic="",  # Invalid missing topic
        angle="Too short",
        platform="linkedin",
        audience="Devs",
        language="English",
        content_type="single_post",
        tone="professional",
        hook_direction="",
        key_points=[],  # Empty list
        cta_direction="",
    )

    mock_provider = MockWriterLLMProvider()
    llm_service = LLMService(provider=mock_provider)
    agent = WriterAgent(llm_service=llm_service)

    request = WriterRequest(plan=invalid_plan)

    with pytest.raises(InvalidPlanError):
        await agent.write(request)

    assert mock_provider.call_count == 0


@pytest.mark.asyncio
async def test_writer_agent_sanitizes_hallucinated_sources() -> None:
    """Verify WriterAgent filters out fake citations not grounded in ContentPlan."""
    plan = create_sample_content_plan()
    mock_provider = MockWriterLLMProvider(return_hallucinated_sources=True)
    llm_service = LLMService(provider=mock_provider)

    agent = WriterAgent(llm_service=llm_service)
    request = WriterRequest(plan=plan)

    post = await agent.write(request)

    # Hallucinated source should be removed, and valid plan source preserved
    assert "fake-hallucinated-source" not in str(post.source_references)
    assert "https://venturebeat.com/ai/agentic-systems" in post.source_references[0]


@pytest.mark.asyncio
async def test_writer_agent_divergent_topic_retry_and_recovery() -> None:
    """Verify WriterAgent catches divergent topic and retries."""
    plan = create_sample_content_plan()
    # Fails topic validation on attempt 1, returns valid post on attempt 2
    mock_provider = MockWriterLLMProvider(fail_count=1)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = WriterAgent(llm_service=llm_service, max_retries=2)
    request = WriterRequest(plan=plan)

    post = await agent.write(request)

    assert post.topic == plan.topic
    assert mock_provider.call_count == 2


@pytest.mark.asyncio
async def test_writer_agent_twitter_oversized_retry_recovery() -> None:
    """Verify WriterAgent triggers retry when Twitter post exceeds length limit."""
    plan = create_sample_content_plan(platform="twitter")
    mock_provider = MockWriterLLMProvider(platform="twitter", return_oversized_tweet=True)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = WriterAgent(llm_service=llm_service, max_retries=2)
    request = WriterRequest(plan=plan, platform="twitter")

    post = await agent.write(request)

    assert post.platform == "twitter"
    assert len(post.content) <= 350
    assert mock_provider.call_count == 2


@pytest.mark.asyncio
async def test_writer_agent_retry_exhaustion() -> None:
    """Verify WriterAgent raises WriterValidationFailedError when all retries are exhausted."""
    plan = create_sample_content_plan()
    mock_provider = MockWriterLLMProvider(always_fail=True)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = WriterAgent(llm_service=llm_service, max_retries=2)
    request = WriterRequest(plan=plan)

    with pytest.raises(WriterValidationFailedError, match="failed to generate a valid post after 2 attempts"):
        await agent.write(request)

    assert mock_provider.call_count == 2


# ------------------------------------------------------------------------------
# 4. Pipeline Integration: Research -> Plan -> Write
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_research_to_planning_to_writer_flow() -> None:
    """Verify end-to-end data flow from ResearchResponse to ContentPlan to SocialPost."""
    # 1. Phase 3 Research output
    trend = Trend(
        topic="Agentic AI in Enterprise Workflows",
        summary="Autonomous multi-agent architectures are replacing traditional scripts.",
        relevance_score=0.95,
        source="venturebeat.com",
        source_title="Enterprise Agents",
        url="https://venturebeat.com/ai/agentic-systems",
        keywords=["Agentic AI", "Enterprise"],
    )
    research = ResearchResponse(
        request=ResearchRequest(niche="Artificial Intelligence"),
        trends=[trend],
        total_results_found=1,
        status="success",
    )

    # 2. Phase 4 ContentPlan
    plan = ContentPlan(
        topic=trend.topic,
        angle="Detailed comparison of agentic workflows vs prompt chains",
        platform="linkedin",
        audience="AI Engineers",
        language="English",
        content_type="single_post",
        tone="professional and insightful",
        hook_direction="Why agent loops are replacing prompt chains.",
        key_points=["Error correction", "Autonomous decision loops", "Multi-agent coordination"],
        cta_direction="What agent pattern are you using?",
        source_references=[trend.url],
        selected_trend_topic=trend.topic,
    )

    # 3. Phase 5 WriterAgent
    mock_provider = MockWriterLLMProvider(topic=plan.topic, platform="linkedin")
    llm_service = LLMService(provider=mock_provider)
    writer = WriterAgent(llm_service=llm_service)

    post = await writer.write(WriterRequest(plan=plan))

    assert post.topic == trend.topic
    assert post.platform == "linkedin"
    assert len(post.source_references) == 1
    assert post.source_references[0] == trend.url
    assert len(post.hashtags) > 0
