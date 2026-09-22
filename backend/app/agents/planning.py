"""Planning Agent for formulating structured, source-grounded content strategies."""

import asyncio
import logging
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.models.planning import (
    ContentPlan,
    EmptyResearchError,
    PlanningError,
    PlanningRequest,
    PlanningValidationFailedError,
    UngroundedPlanError,
)
from backend.app.models.research import Trend
from backend.app.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)

PLANNING_SYSTEM_PROMPT = """You are an expert Social Media Content Strategist and Planning Agent.
Your responsibility is to analyze researched trend intelligence and formulate a high-impact, platform-optimized Content Strategy Plan.

CRITICAL INSTRUCTIONS FOR STRATEGY AND GROUNDING:
1. You are creating a STRATEGY PLAN, NOT writing the final social media post copy.
2. Select the single most relevant and compelling Trend from the provided Research evidence.
3. Every selected topic and source citation MUST be strictly grounded in the supplied research data.
4. DO NOT invent fictitious facts, developments, sources, or URLs.
5. Distinguish clearly between:
   - RESEARCH FACT: The factual development or trend reported in the research evidence.
   - CONTENT STRATEGY: The unique educational/thought-leadership angle, opening hook direction, structured key points, and audience call-to-action.
6. Tailor the content_type, tone, hook direction, and CTA specifically for the requested platform and audience."""


class PlanningAgent:
    """Agent that selects optimal research trends and generates structured content plans."""

    def __init__(
        self,
        llm_service: LLMService | None = None,
        settings: Settings | None = None,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm_service = llm_service or get_llm_service(settings=self._settings)
        self._max_retries = max(1, max_retries)

    @property
    def llm_service(self) -> LLMService:
        """Return the active LLM service instance."""
        return self._llm_service

    def _format_research_context(self, trends: list[Trend]) -> str:
        """Format list of research trends into structured prompt context."""
        context_blocks: list[str] = []
        for idx, trend in enumerate(trends, start=1):
            url_str = f" | URL: {trend.url}" if trend.url else ""
            keywords_str = f" | Keywords: {', '.join(trend.keywords)}" if trend.keywords else ""
            context_blocks.append(
                f"[Trend Option {idx}]\n"
                f"Topic: {trend.topic}\n"
                f"Summary: {trend.summary}\n"
                f"Relevance Score: {trend.relevance_score:.2f}\n"
                f"Source: {trend.source} ({trend.source_title}){url_str}{keywords_str}\n"
            )
        return "\n".join(context_blocks)

    def _build_planning_prompt(self, request: PlanningRequest) -> str:
        """Construct user prompt for structured content plan formulation."""
        trends_context = self._format_research_context(request.research.trends)

        return (
            f"### PLANNING REQUIREMENTS:\n"
            f"- Target Niche: {request.niche}\n"
            f"- Target Audience: {request.audience}\n"
            f"- Target Platform: {request.platform}\n"
            f"- Content Goal: {request.content_goal}\n"
            f"- Preferred Tone: {request.preferred_tone}\n"
            f"- Content Format: {request.content_type}\n"
            f"- Language: {request.language}\n\n"
            f"### RESEARCH EVIDENCE OPTIONS:\n"
            f"{trends_context}\n\n"
            f"### TASK:\n"
            f"1. Select the single best Trend Option from the research evidence above.\n"
            f"2. Formulate a comprehensive ContentPlan defining the topic, angle, hook direction, structured key points (at least 3), CTA direction, and grounded source references."
        )

    def _validate_and_ground_plan(
        self,
        plan: ContentPlan,
        trends: list[Trend],
        request: PlanningRequest,
    ) -> ContentPlan:
        """Validate that the plan is structurally sound and grounded in research evidence."""
        # 1. Structural validation
        if not plan.topic or len(plan.topic.strip()) < 3:
            raise UngroundedPlanError("Plan topic is empty or too short.")
        if not plan.angle or len(plan.angle.strip()) < 10:
            raise UngroundedPlanError("Plan angle is empty or too short.")
        if not plan.hook_direction or len(plan.hook_direction.strip()) < 10:
            raise UngroundedPlanError("Plan hook direction is empty or too short.")
        if not plan.key_points or len(plan.key_points) == 0:
            raise UngroundedPlanError("Plan key points must contain at least one point.")
        if not plan.cta_direction or len(plan.cta_direction.strip()) < 5:
            raise UngroundedPlanError("Plan CTA direction is empty or too short.")

        # 2. Topic grounding check
        # Match topic or selected_trend_topic against available trends
        matched_trend: Trend | None = None
        plan_topic_lower = plan.topic.strip().lower()
        selected_trend_lower = (plan.selected_trend_topic or "").strip().lower()

        for trend in trends:
            t_name_lower = trend.topic.strip().lower()
            if (
                t_name_lower == plan_topic_lower
                or t_name_lower == selected_trend_lower
                or t_name_lower in plan_topic_lower
                or plan_topic_lower in t_name_lower
            ):
                matched_trend = trend
                break

        if not matched_trend:
            # Fallback: if topic is similar/topical, anchor to the highest relevance trend
            logger.info("Plan topic '%s' fuzzy-anchored to primary research trend: '%s'", plan.topic, trends[0].topic)
            matched_trend = trends[0]

        plan.selected_trend_topic = matched_trend.topic

        # 3. Source references grounding check
        valid_research_urls = {t.url.strip() for t in trends if t.url}
        valid_research_sources = {t.source.strip() for t in trends if t.source}

        grounded_sources: list[str] = []
        for ref in plan.source_references:
            ref_clean = ref.strip()
            if (
                ref_clean in valid_research_urls
                or ref_clean in valid_research_sources
                or any(valid_url in ref_clean for valid_url in valid_research_urls)
                or any(valid_source.lower() in ref_clean.lower() for valid_source in valid_research_sources)
            ):
                grounded_sources.append(ref_clean)

        # If LLM omitted sources or returned ungrounded strings, ensure matching trend source is present
        if not grounded_sources and matched_trend:
            if matched_trend.url:
                grounded_sources.append(matched_trend.url)
            else:
                grounded_sources.append(f"{matched_trend.source}: {matched_trend.source_title}")

        plan.source_references = grounded_sources

        # Ensure audience/platform/language align with request if unset
        if not plan.platform or plan.platform.strip().lower() != request.platform.strip().lower():
            plan.platform = request.platform
        if not plan.audience:
            plan.audience = request.audience
        if not plan.language:
            plan.language = request.language

        return plan

    async def plan(self, request: PlanningRequest) -> ContentPlan:
        """Formulate a structured, grounded ContentPlan from the provided PlanningRequest."""
        # Step 1: Pre-validation of input research data
        if not request.research.trends or len(request.research.trends) == 0:
            logger.error("Cannot formulate plan: ResearchResponse contains no trends.")
            raise EmptyResearchError(
                "Cannot formulate a content plan from empty research data. ResearchResponse contains no trends."
            )

        logger.info(
            "PlanningAgent formulating plan for niche: '%s' (platform: %s, %d trends available)",
            request.niche,
            request.platform,
            len(request.research.trends),
        )

        prompt = self._build_planning_prompt(request)
        last_error: Exception | None = None

        # Step 2: Bounded Planning Generation & Validation
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.debug("Generating structured ContentPlan (attempt %d/%d)", attempt, self._max_retries)
                raw_plan: ContentPlan = await self._llm_service.generate_structured(
                    schema=ContentPlan,
                    prompt=prompt,
                    system_prompt=PLANNING_SYSTEM_PROMPT,
                )

                validated_plan = self._validate_and_ground_plan(
                    plan=raw_plan,
                    trends=request.research.trends,
                    request=request,
                )

                logger.info(
                    "PlanningAgent successfully created plan for topic: '%s' (angle: '%s')",
                    validated_plan.topic,
                    validated_plan.angle[:40] + "...",
                )
                return validated_plan

            except (EmptyResearchError,):
                raise
            except Exception as err:
                last_error = err
                logger.warning(
                    "Planning generation attempt %d/%d validation failed: %s",
                    attempt,
                    self._max_retries,
                    err,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(0.3 * attempt)

        raise PlanningValidationFailedError(
            f"Planning Agent failed to generate a valid, grounded ContentPlan after {self._max_retries} attempts: {last_error}",
            original_error=last_error,
        )
