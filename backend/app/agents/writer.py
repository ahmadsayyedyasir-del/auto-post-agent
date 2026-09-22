"""Writer Agent for generating platform-tailored, source-grounded social media copy."""

import asyncio
import logging
import re
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.models.content import (
    InvalidPlanError,
    PlatformConstraintError,
    SocialPost,
    UngroundedContentError,
    WriterError,
    WriterRequest,
    WriterValidationFailedError,
)
from backend.app.models.planning import ContentPlan
from backend.app.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)

WRITER_SYSTEM_PROMPT = """You are an expert Social Media Content Writer.
Your responsibility is to craft high-engagement, platform-optimized social media post copy strictly adhering to the provided Content Strategy Plan.

CRITICAL INSTRUCTIONS:
1. You are writing the FINAL, PUBLISH-READY social media post copy.
2. STRICTLY follow the provided ContentPlan:
   - Focus on the exact Planned Topic and Strategic Angle.
   - Craft an opening hook following the Planned Hook Direction.
   - Incorporate the Planned Key Points naturally into the post body.
   - Conclude with the Planned Call to Action (CTA).
   - Write in the specified Tone and Language.
3. GROUNDING AND INTEGRITY:
   - DO NOT invent new factual statistics, claims, research developments, or fake URLs.
   - Only reference source URLs or citations that are explicitly listed in the ContentPlan's source_references.
4. CONTENT QUALITY AND FORMATTING:
   - DO NOT include meta-commentary, introductory remarks (e.g., 'Here is your post:'), or mention that you are an AI.
   - Format paragraphs, line breaks, and spacing specifically for the target platform.
   - Include 2-5 relevant, non-spammy hashtags suitable for the target platform."""

# Platform specific guidance templates
PLATFORM_GUIDELINES: dict[str, str] = {
    "linkedin": (
        "PLATFORM GUIDELINES FOR LINKEDIN:\n"
        "- Tone: Professional, insightful, authentic, and human.\n"
        "- Formatting: Strong 1-2 line opening hook, clean short paragraphs (1-3 sentences per paragraph), ample white space.\n"
        "- Structure: Hook -> Core insight / context -> 2-3 structured takeaways / bullet points -> Discussion prompt CTA.\n"
        "- Hashtags: 3 to 5 targeted, industry-relevant hashtags at the end.\n"
        "- Length: Engaging medium-form post (typically 500 to 1800 characters)."
    ),
    "twitter": (
        "PLATFORM GUIDELINES FOR X / TWITTER:\n"
        "- Tone: Punchy, concise, high-signal, engaging.\n"
        "- Formatting: High-impact opening hook line, compact bullet points or crisp sentences.\n"
        "- Structure: Immediate punchy hook -> 1-2 concise insights -> Direct CTA question.\n"
        "- Hashtags: 1 to 3 relevant hashtags max.\n"
        "- Strict Constraint: Concise single-post format (strictly keep post content under 280 characters if possible, maximum 320 characters including hashtags)."
    ),
    "x": (
        "PLATFORM GUIDELINES FOR X / TWITTER:\n"
        "- Tone: Punchy, concise, high-signal, engaging.\n"
        "- Formatting: High-impact opening hook line, compact bullet points or crisp sentences.\n"
        "- Structure: Immediate punchy hook -> 1-2 concise insights -> Direct CTA question.\n"
        "- Hashtags: 1 to 3 relevant hashtags max.\n"
        "- Strict Constraint: Concise single-post format (strictly keep post content under 280 characters if possible, maximum 320 characters including hashtags)."
    ),
}

DEFAULT_PLATFORM_GUIDELINES = (
    "PLATFORM GUIDELINES:\n"
    "- Tone: Engaging, clear, and audience-appropriate.\n"
    "- Structure: Clear hook -> structured body with planned key points -> clear CTA.\n"
    "- Hashtags: 2 to 4 relevant hashtags."
)


class WriterAgent:
    """Agent that consumes a validated ContentPlan and writes platform-tailored social copy."""

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

    def _validate_input_plan(self, plan: ContentPlan) -> None:
        """Verify that the input ContentPlan is complete and well-formed before LLM generation."""
        if not plan.topic or len(plan.topic.strip()) < 3:
            raise InvalidPlanError("ContentPlan topic is missing or too short.")
        if not plan.angle or len(plan.angle.strip()) < 10:
            raise InvalidPlanError("ContentPlan angle is missing or too short.")
        if not plan.key_points or len(plan.key_points) == 0:
            raise InvalidPlanError("ContentPlan key_points must contain at least one point.")
        if not plan.hook_direction or len(plan.hook_direction.strip()) < 5:
            raise InvalidPlanError("ContentPlan hook_direction is missing or too short.")
        if not plan.cta_direction or len(plan.cta_direction.strip()) < 5:
            raise InvalidPlanError("ContentPlan cta_direction is missing or too short.")

    def _build_writer_prompt(
        self,
        request: WriterRequest,
        corrective_feedback: str | None = None,
    ) -> str:
        """Construct prompt with ContentPlan strategy and platform guidelines."""
        plan = request.plan
        effective_platform = request.get_effective_platform()
        effective_audience = request.get_effective_audience()
        effective_language = request.get_effective_language()
        effective_tone = request.get_effective_tone()

        platform_guide = PLATFORM_GUIDELINES.get(effective_platform, DEFAULT_PLATFORM_GUIDELINES)

        key_points_formatted = "\n".join(f"- {kp}" for kp in plan.key_points)
        sources_formatted = (
            "\n".join(f"- {src}" for src in plan.source_references)
            if plan.source_references
            else "- (No external links required; keep claims grounded in topic)"
        )

        prompt_parts = [
            f"### CONTENT STRATEGY PLAN:\n"
            f"- Topic: {plan.topic}\n"
            f"- Target Platform: {effective_platform}\n"
            f"- Target Audience: {effective_audience}\n"
            f"- Language: {effective_language}\n"
            f"- Desired Tone: {effective_tone}\n"
            f"- Strategic Angle: {plan.angle}\n"
            f"- Hook Direction: {plan.hook_direction}\n"
            f"- Key Points to Cover:\n{key_points_formatted}\n"
            f"- Call-to-Action (CTA) Direction: {plan.cta_direction}\n"
            f"- Allowed Source Citations:\n{sources_formatted}\n",
            f"### {platform_guide}\n",
        ]

        if request.previous_post:
            prompt_parts.append(
                f"### PREVIOUS POST DRAFT:\n"
                f"\"\"\"\n{request.previous_post.content}\n\"\"\"\n"
            )

        if request.revision_feedback:
            feedback_formatted = "\n".join(f"- {fb}" for fb in request.revision_feedback)
            prompt_parts.append(
                f"### CRITIC REVISION FEEDBACK:\n"
                f"The Critic Agent reviewed the previous draft and requested the following improvements:\n"
                f"{feedback_formatted}\n"
                f"Address all of these points in the revised post copy.\n"
            )

        prompt_parts.append(
            f"### TASK:\n"
            f"Generate a structured SocialPost for {effective_platform.upper()} in {effective_language}."
        )

        if corrective_feedback:
            prompt_parts.append(
                f"\n### PREVIOUS ATTEMPT CORRECTION:\n"
                f"Your previous generation had the following issue:\n{corrective_feedback}\n"
                f"Please correct this issue and ensure all constraints are strictly met."
            )

        return "\n".join(prompt_parts)

    def _validate_and_ground_post(
        self,
        post: SocialPost,
        request: WriterRequest,
    ) -> SocialPost:
        """Perform deterministic validation, platform constraint checks, and source grounding."""
        plan = request.plan
        effective_platform = request.get_effective_platform()
        effective_language = request.get_effective_language()

        # 1. Non-empty content check
        if not post.content or len(post.content.strip()) < 10:
            raise UngroundedContentError("Generated post content is empty or too short.")

        # 2. Topic alignment check
        plan_topic_lower = plan.topic.strip().lower()
        post_topic_lower = (post.topic or "").strip().lower()

        if (
            post_topic_lower != plan_topic_lower
            and plan_topic_lower not in post_topic_lower
            and post_topic_lower not in plan_topic_lower
        ):
            # If the generated topic completely diverged from the planned topic
            if not post_topic_lower or len(post_topic_lower) < 3:
                post.topic = plan.topic
            else:
                raise UngroundedContentError(
                    f"Generated post topic '{post.topic}' does not match planned topic '{plan.topic}'."
                )
        else:
            post.topic = plan.topic

        # 3. Platform & Language normalization
        post.platform = effective_platform
        post.language = effective_language

        # 4. Platform length constraint checks
        content_len = len(post.content.strip())
        if effective_platform in ("twitter", "x"):
            # Max character limit for single tweet on X/Twitter
            if content_len > 350 and plan.content_type == "single_post":
                raise PlatformConstraintError(
                    f"Generated post length ({content_len} chars) exceeds X/Twitter single-post limit (max 350 chars). "
                    "Make the copy more concise and compact."
                )

        # 5. Hashtag cleaning and normalization
        cleaned_hashtags: list[str] = []
        for tag in post.hashtags:
            clean_tag = tag.strip().lstrip("#")
            clean_tag = re.sub(r"[^\w]", "", clean_tag)
            if clean_tag and f"#{clean_tag}" not in cleaned_hashtags:
                cleaned_hashtags.append(f"#{clean_tag}")

        post.hashtags = cleaned_hashtags

        # 6. Source Grounding & Anti-Hallucination
        # Ensure post only retains source URLs or citations present in the ContentPlan
        valid_sources = {src.strip() for src in plan.source_references if src}
        grounded_sources: list[str] = []

        for ref in post.source_references:
            ref_clean = ref.strip()
            if ref_clean in valid_sources or any(vs in ref_clean for vs in valid_sources):
                grounded_sources.append(ref_clean)

        # If post omitted sources but plan provided them, preserve plan sources
        if not grounded_sources and plan.source_references:
            grounded_sources = list(plan.source_references)

        post.source_references = grounded_sources

        # 7. CTA normalization
        if not post.cta or len(post.cta.strip()) < 3:
            post.cta = plan.cta_direction

        return post

    async def write(self, request: WriterRequest) -> SocialPost:
        """Generate a structured, platform-tailored SocialPost from the given WriterRequest."""
        # Step 1: Pre-validation of input plan
        self._validate_input_plan(request.plan)

        effective_platform = request.get_effective_platform()
        logger.info(
            "WriterAgent generating post for topic: '%s' (platform: %s, tone: %s)",
            request.plan.topic,
            effective_platform,
            request.get_effective_tone(),
        )

        last_error: Exception | None = None
        corrective_feedback: str | None = None

        # Step 2: Bounded Generation & Validation Loop
        for attempt in range(1, self._max_retries + 1):
            prompt = self._build_writer_prompt(request, corrective_feedback=corrective_feedback)

            try:
                logger.debug("Generating SocialPost (attempt %d/%d)", attempt, self._max_retries)
                raw_post: SocialPost = await self._llm_service.generate_structured(
                    schema=SocialPost,
                    prompt=prompt,
                    system_prompt=WRITER_SYSTEM_PROMPT,
                )

                validated_post = self._validate_and_ground_post(
                    post=raw_post,
                    request=request,
                )

                logger.info(
                    "WriterAgent successfully generated post for topic '%s' on %s (%d chars, %d hashtags)",
                    validated_post.topic,
                    validated_post.platform,
                    len(validated_post.content),
                    len(validated_post.hashtags),
                )
                return validated_post

            except (InvalidPlanError,):
                raise
            except Exception as err:
                last_error = err
                corrective_feedback = str(err)
                logger.warning(
                    "Writer generation attempt %d/%d validation failed: %s",
                    attempt,
                    self._max_retries,
                    err,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(0.3 * attempt)

        raise WriterValidationFailedError(
            f"Writer Agent failed to generate a valid post after {self._max_retries} attempts: {last_error}",
            original_error=last_error,
        )
