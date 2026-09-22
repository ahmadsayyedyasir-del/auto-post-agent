"""Unit tests for the Critic Agent, schemas, deterministic checks, grounding, and retries."""

from typing import Any, Literal

import pytest
from pydantic import ValidationError

from backend.app.agents.critic import CriticAgent, _LLMEvaluation
from backend.app.models.content import SocialPost
from backend.app.models.critic import (
    CriticDecision,
    CriticError,
    CriticResult,
    CriticValidationFailedError,
    InvalidReviewRequestError,
    QualityChecks,
    ReviewRequest,
)
from backend.app.models.planning import ContentPlan
from backend.app.models.research import (
    ResearchRequest,
    ResearchResponse,
    Trend,
)
from backend.app.services.llm import LLMProvider, LLMService


# ------------------------------------------------------------------------------
# Fixtures and Helpers
# ------------------------------------------------------------------------------


def create_sample_plan(platform: str = "linkedin") -> ContentPlan:
    """Create a sample ContentPlan for testing."""
    return ContentPlan(
        topic="Agentic AI in Enterprise Workflows",
        angle="How multi-agent loops reduce hallucination by 40% and automate engineering workflows",
        platform=platform,
        audience="AI Practitioners and Tech Leads",
        language="English",
        content_type="single_post",
        tone="professional and insightful",
        hook_direction="Stop treating LLMs like simple chatbots—autonomous loops change everything.",
        key_points=[
            "Moving from prompt engineering to agentic workflow orchestration",
            "Error-correction cycles reduce operational errors by 40%",
            "The 3-node blueprint: Research -> Plan -> Write",
        ],
        cta_direction="What is the biggest barrier you face deploying agentic AI? Let's discuss.",
        source_references=["https://venturebeat.com/ai/agentic-systems"],
        selected_trend_topic="Agentic AI in Enterprise Workflows",
    )


def create_sample_post(
    platform: str = "linkedin",
    content: str | None = None,
    source_references: list[str] | None = None,
    hashtags: list[str] | None = None,
    cta: str | None = None,
    topic: str = "Agentic AI in Enterprise Workflows",
) -> SocialPost:
    """Create a sample SocialPost for testing."""
    default_content = (
        "Stop treating LLMs like simple chatbots—autonomous loops change everything.\n\n"
        "Single prompt chains hit a ceiling in production. Enterprise engineering teams are adopting multi-agent loops:\n\n"
        "1. Iterative error correction reduces hallucinations by 40%\n"
        "2. Specialized roles outperform single monolithic prompts\n"
        "3. Autonomous workflows execute multi-step research and planning\n\n"
        "What is the biggest barrier you face deploying agentic AI? Let's discuss in the comments below."
    )

    return SocialPost(
        platform=platform,
        content=content if content is not None else default_content,
        topic=topic,
        language="English",
        content_type="single_post",
        hashtags=hashtags if hashtags is not None else ["#AgenticAI", "#MachineLearning", "#SoftwareEngineering"],
        cta=cta if cta is not None else "What is the biggest barrier you face deploying agentic AI? Let's discuss in the comments below.",
        source_references=source_references if source_references is not None else ["https://venturebeat.com/ai/agentic-systems"],
    )


def create_sample_research() -> ResearchResponse:
    """Create a sample ResearchResponse for testing."""
    trend = Trend(
        topic="Agentic AI in Enterprise Workflows",
        summary="Autonomous multi-agent architectures are replacing traditional workflow scripts across tech companies.",
        relevance_score=0.95,
        source="venturebeat.com",
        source_title="Enterprise Multi-Agent Systems",
        url="https://venturebeat.com/ai/agentic-systems",
        keywords=["Agentic AI", "Enterprise", "Automation"],
    )
    return ResearchResponse(
        request=ResearchRequest(niche="Artificial Intelligence"),
        trends=[trend],
        total_results_found=1,
        status="success",
    )


class MockCriticLLMProvider(LLMProvider):
    """Mock LLM provider returning structured _LLMEvaluation."""

    def __init__(
        self,
        decision: Literal["APPROVED", "REVISE"] = "APPROVED",
        issues: list[str] | None = None,
        feedback: list[str] | None = None,
        fail_count: int = 0,
        always_fail: bool = False,
        tone_ok: bool = True,
        clarity_ok: bool = True,
    ) -> None:
        self.decision = decision
        self.issues = issues or []
        self.feedback = feedback or []
        self.fail_count = fail_count
        self.always_fail = always_fail
        self.tone_ok = tone_ok
        self.clarity_ok = clarity_ok
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_critic"

    @property
    def model_name(self) -> str:
        return "mock-critic-model"

    async def generate(self, prompt: str, system_prompt: str | None = None, **kwargs: Any) -> str:
        return ""

    async def generate_structured(
        self,
        schema: type[_LLMEvaluation],
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> _LLMEvaluation:
        self.call_count += 1

        if self.always_fail or self.call_count <= self.fail_count:
            raise CriticError(f"Simulated LLM error on attempt {self.call_count}")

        return schema(
            decision=self.decision,
            issues=self.issues,
            feedback=self.feedback,
            relevance_ok=True,
            plan_adherence_ok=True,
            clarity_ok=self.clarity_ok,
            tone_ok=self.tone_ok,
            platform_fit_ok=True,
            cta_ok=True,
            originality_ok=True,
            unverified_claims=[],
            evaluation_notes="Evaluation executed successfully by mock provider.",
        )


# ------------------------------------------------------------------------------
# 1. Schema Validation Tests
# ------------------------------------------------------------------------------


def test_review_request_and_critic_result_schemas() -> None:
    """Verify ReviewRequest and CriticResult schemas and default properties."""
    plan = create_sample_plan()
    post = create_sample_post()

    req = ReviewRequest(post=post, plan=plan)
    assert req.post == post
    assert req.plan == plan
    assert req.research is None
    assert req.brand_guidelines is None

    result = CriticResult(
        decision="APPROVED",
        issues=[],
        feedback=[],
        checks=QualityChecks(),
    )
    assert result.decision == "APPROVED"
    assert result.checks.relevance is True
    assert result.checks.source_grounding is True


# ------------------------------------------------------------------------------
# 2. Critic Agent Evaluation Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critic_agent_approves_valid_post() -> None:
    """Verify CriticAgent returns APPROVED for a valid, grounded, well-formatted post."""
    plan = create_sample_plan()
    post = create_sample_post()
    research = create_sample_research()

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan, research=research))

    assert result.decision == "APPROVED"
    assert len(result.issues) == 0
    assert result.checks.relevance is True
    assert result.checks.source_grounding is True
    assert result.checks.platform_fit is True
    assert len(result.verified_sources) >= 1
    assert mock_provider.call_count == 1


@pytest.mark.asyncio
async def test_critic_agent_rejects_empty_post() -> None:
    """Verify CriticAgent detects empty content and forces REVISE."""
    plan = create_sample_plan()
    post = create_sample_post(content="   ")  # Whitespace only

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert any("empty" in issue.lower() for issue in result.issues)
    assert result.checks.clarity is False


@pytest.mark.asyncio
async def test_critic_agent_detects_platform_mismatch() -> None:
    """Verify CriticAgent detects platform mismatch between plan and post."""
    plan = create_sample_plan(platform="linkedin")
    post = create_sample_post(platform="twitter")  # Mismatch

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.platform_fit is False
    assert any("Platform mismatch" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_detects_topic_mismatch() -> None:
    """Verify CriticAgent detects topic divergence between plan and post."""
    plan = create_sample_plan()
    post = create_sample_post(topic="Cryptocurrency Day Trading Tips")

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.relevance is False
    assert any("Topic divergence" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_detects_unsupported_fabricated_source() -> None:
    """Verify CriticAgent detects fabricated citations not present in research or plan."""
    plan = create_sample_plan()
    research = create_sample_research()
    post = create_sample_post(
        source_references=["https://fake-hallucinated-blog.com/secret-post"]
    )

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan, research=research))

    assert result.decision == "REVISE"
    assert result.checks.source_grounding is False
    assert any("fabricated source" in issue.lower() for issue in result.issues)
    assert len(result.unverified_claims) >= 1


@pytest.mark.asyncio
async def test_critic_agent_detects_missing_cta() -> None:
    """Verify CriticAgent flags missing Call to Action when required by plan."""
    plan = create_sample_plan()
    # Content with no question, no CTA prompt, and empty post.cta
    post = create_sample_post(
        content="Here are 3 facts about artificial intelligence. It is fast, automated, and effective.",
        cta="",
    )

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.cta is False
    assert any("Call to Action" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_detects_twitter_oversized_length() -> None:
    """Verify CriticAgent rejects X/Twitter single post exceeding character bounds."""
    plan = create_sample_plan(platform="twitter")
    oversized_text = "A" * 380
    post = create_sample_post(platform="twitter", content=oversized_text)

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.length is False
    assert any("length violation" in issue.lower() for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_detects_excessive_hashtags() -> None:
    """Verify CriticAgent detects hashtag spam / excessive count."""
    plan = create_sample_plan(platform="twitter")
    post = create_sample_post(
        platform="twitter",
        content="Concise post about agentic loops.",
        hashtags=["#AI", "#Tech", "#Agents", "#Dev", "#Future", "#Automation"],  # 6 tags on Twitter
    )

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.hashtags is False
    assert any("Excessive hashtags" in issue for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_llm_requested_revision_tone_mismatch() -> None:
    """Verify CriticAgent respects LLM recommendation when semantic tone mismatch is found."""
    plan = create_sample_plan()
    post = create_sample_post()

    mock_provider = MockCriticLLMProvider(
        decision="REVISE",
        issues=["Tone is overly casual and sarcastic for an executive LinkedIn audience."],
        feedback=["Rewrite with an analytical and professional tone."],
        tone_ok=False,
    )
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.tone is False
    assert any("sarcastic" in issue for issue in result.issues)
    assert any("analytical" in fb for fb in result.feedback)


@pytest.mark.asyncio
async def test_critic_agent_detects_duplicate_sentence_repetition() -> None:
    """Verify CriticAgent flags duplicate sentence repetition."""
    plan = create_sample_plan()
    repeated_content = (
        "Enterprise engineering teams are adopting multi-agent loops today. "
        "Enterprise engineering teams are adopting multi-agent loops today. "
        "What are your thoughts?"
    )
    post = create_sample_post(content=repeated_content)

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "REVISE"
    assert result.checks.originality is False
    assert any("repetition" in issue.lower() for issue in result.issues)


@pytest.mark.asyncio
async def test_critic_agent_handles_optional_research_gracefully() -> None:
    """Verify CriticAgent evaluates post cleanly when research is None."""
    plan = create_sample_plan()
    post = create_sample_post()

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan, research=None))

    assert result.decision == "APPROVED"
    assert result.checks.source_grounding is True


@pytest.mark.asyncio
async def test_critic_agent_immutability_and_no_post_rewriting() -> None:
    """Verify CriticAgent does not mutate original SocialPost and does not rewrite post text."""
    plan = create_sample_plan()
    original_content = "Original unaltered content for LinkedIn.\n\nWhat are your thoughts?"
    post = create_sample_post(content=original_content)

    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    agent = CriticAgent(llm_service=llm_service)

    result = await agent.review(ReviewRequest(post=post, plan=plan))

    # SocialPost content must remain exactly identical
    assert post.content == original_content
    # CriticResult contains decision and feedback, NOT replaced post copy
    assert isinstance(result, CriticResult)
    assert not hasattr(result, "content")


@pytest.mark.asyncio
async def test_critic_agent_llm_retry_and_recovery() -> None:
    """Verify CriticAgent retries on transient LLM failures and succeeds."""
    plan = create_sample_plan()
    post = create_sample_post()

    # Fails attempt 1, succeeds attempt 2
    mock_provider = MockCriticLLMProvider(fail_count=1)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = CriticAgent(llm_service=llm_service, max_retries=2)
    result = await agent.review(ReviewRequest(post=post, plan=plan))

    assert result.decision == "APPROVED"
    assert mock_provider.call_count == 2


@pytest.mark.asyncio
async def test_critic_agent_retry_exhaustion_raises_error() -> None:
    """Verify CriticAgent raises CriticValidationFailedError when all retries fail."""
    plan = create_sample_plan()
    post = create_sample_post()

    mock_provider = MockCriticLLMProvider(always_fail=True)
    llm_service = LLMService(provider=mock_provider, max_retries=1)

    agent = CriticAgent(llm_service=llm_service, max_retries=2)

    with pytest.raises(CriticValidationFailedError, match="failed to evaluate post after 2 attempts"):
        await agent.review(ReviewRequest(post=post, plan=plan))

    assert mock_provider.call_count == 2


# ------------------------------------------------------------------------------
# 3. Full Multi-Agent Pipeline Test: Research -> Plan -> Write -> Critic
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_research_to_planning_to_writer_to_critic() -> None:
    """Verify full end-to-end multi-agent pipeline data flow from Research to Critic."""
    # 1. Phase 3 Research output
    trend = Trend(
        topic="Agentic AI in Enterprise Workflows",
        summary="Autonomous multi-agent architectures are replacing traditional workflow scripts across tech companies.",
        relevance_score=0.95,
        source="venturebeat.com",
        source_title="Enterprise Multi-Agent Systems",
        url="https://venturebeat.com/ai/agentic-systems",
        keywords=["Agentic AI", "Enterprise", "Automation"],
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
        angle="How multi-agent architectures reduce hallucination and automate workflows",
        platform="linkedin",
        audience="AI Practitioners and Tech Leads",
        language="English",
        content_type="single_post",
        tone="professional and insightful",
        hook_direction="Why autonomous loops outperform standard prompt chains.",
        key_points=[
            "Moving from prompt engineering to agentic orchestration",
            "Error-correction cycles reduce hallucinations by 40%",
        ],
        cta_direction="What is your biggest deployment challenge? Let's discuss.",
        source_references=[trend.url],
        selected_trend_topic=trend.topic,
    )

    # 3. Phase 5 SocialPost
    post = SocialPost(
        platform="linkedin",
        content=(
            "Why autonomous loops outperform standard prompt chains.\n\n"
            "Enterprise teams are moving toward multi-agent orchestration:\n"
            "- Iterative error-correction cycles reduce hallucinations by 40%\n"
            "- Autonomous loops handle multi-step workflows\n\n"
            "What is your biggest deployment challenge? Let's discuss in the comments below."
        ),
        topic=trend.topic,
        language="English",
        content_type="single_post",
        hashtags=["#AgenticAI", "#MachineLearning"],
        cta="What is your biggest deployment challenge? Let's discuss in the comments below.",
        source_references=[trend.url],
    )

    # 4. Phase 6 CriticAgent
    mock_provider = MockCriticLLMProvider(decision="APPROVED")
    llm_service = LLMService(provider=mock_provider)
    critic = CriticAgent(llm_service=llm_service)

    result = await critic.review(ReviewRequest(post=post, plan=plan, research=research))

    assert isinstance(result, CriticResult)
    assert result.decision == "APPROVED"
    assert result.checks.source_grounding is True
    assert result.checks.platform_fit is True
    assert len(result.verified_sources) == 1
    assert result.verified_sources[0] == trend.url
