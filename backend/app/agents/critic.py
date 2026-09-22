"""Critic / Reviewer Agent for comprehensive quality, plan adherence, and source grounding evaluation."""

import asyncio
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.config import Settings, get_settings
from backend.app.models.critic import (
    CriticDecision,
    CriticError,
    CriticResult,
    CriticValidationFailedError,
    InvalidReviewRequestError,
    QualityChecks,
    ReviewRequest,
)
from backend.app.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """You are an expert Social Media Content Critic and Quality Reviewer.
Your responsibility is to objectively evaluate a generated SocialPost against the original ContentPlan, supplied Research evidence, and platform guidelines.

CRITICAL INSTRUCTIONS:
1. You are a CRITIC, NOT a writer. DO NOT rewrite the post.
2. Evaluate across the following dimensions:
   - Relevance & Topic Adherence: Does the post stay focused on the planned topic and angle?
   - Source Grounding & Accuracy: Are claims supported by the supplied research? Reject fabricated facts or sources.
   - Clarity & Structure: Is the post readable, well-paced, with good whitespace and hook?
   - Tone & Platform Fit: Does it match the requested platform tone (e.g., professional for LinkedIn, punchy for X)?
   - Call to Action (CTA): Is the closing CTA clear, engaging, and aligned with the plan?
   - Originality & Repetition: Is the post free from repetitive sentences, boilerplate filler, or generic AI clichés?
3. DECISION RULES:
   - Return 'APPROVED' ONLY if the post satisfies all criteria with no major defects.
   - Return 'REVISE' if there are factual issues, ungrounded sources, tone mismatches, weak hooks, length issues, or missing CTA.
4. ACTIONABLE FEEDBACK:
   - Provide concrete, specific issues and actionable feedback that a writer can immediately use to revise the post."""


class _LLMEvaluation(BaseModel):
    """Internal schema for structured LLM review output."""

    model_config = ConfigDict(extra="ignore")

    decision: Literal["APPROVED", "REVISE"] = Field(..., description="Verdict from semantic evaluation")
    issues: list[str] = Field(default_factory=list, description="Specific problems identified by LLM")
    feedback: list[str] = Field(default_factory=list, description="Actionable revision recommendations")
    relevance_ok: bool = Field(default=True, description="Topic and angle alignment")
    plan_adherence_ok: bool = Field(default=True, description="Inclusion of key points and planned structure")
    clarity_ok: bool = Field(default=True, description="Readability and structure")
    tone_ok: bool = Field(default=True, description="Voice and tone appropriateness")
    platform_fit_ok: bool = Field(default=True, description="Platform conventions")
    cta_ok: bool = Field(default=True, description="Call to action presence and quality")
    originality_ok: bool = Field(default=True, description="Absence of filler and repetition")
    unverified_claims: list[str] = Field(default_factory=list, description="Claims that lack research support")
    evaluation_notes: str | None = Field(default=None, description="Summary notes")


class CriticAgent:
    """Agent that performs multi-dimensional deterministic and LLM evaluation of social content."""

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

    def _validate_request(self, request: ReviewRequest) -> None:
        """Ensure the ReviewRequest contains valid post and plan instances."""
        if not request.post or not hasattr(request.post, "content"):
            raise InvalidReviewRequestError("ReviewRequest must contain a valid SocialPost.")
        if not request.plan or not hasattr(request.plan, "topic"):
            raise InvalidReviewRequestError("ReviewRequest must contain a valid ContentPlan.")

    def _run_deterministic_checks(
        self,
        request: ReviewRequest,
    ) -> tuple[QualityChecks, list[str], list[str], list[str], list[str]]:
        """Perform deterministic quality, grounding, platform, and formatting checks."""
        post = request.post
        plan = request.plan
        research = request.research

        checks = QualityChecks()
        issues: list[str] = []
        feedback: list[str] = []
        verified_sources: list[str] = []
        unverified_claims: list[str] = []

        # 1. Content presence check
        content_stripped = (post.content or "").strip()
        if not content_stripped:
            checks.clarity = False
            issues.append("Post content is empty or contains only whitespace.")
            feedback.append("Generate substantive post copy adhering to the ContentPlan.")

        # 2. Platform alignment check
        plan_platform = (plan.platform or "").strip().lower()
        post_platform = (post.platform or "").strip().lower()
        if plan_platform and post_platform and plan_platform != post_platform:
            checks.platform_fit = False
            issues.append(
                f"Platform mismatch: Post was formatted for '{post.platform}', but plan requested '{plan.platform}'."
            )
            feedback.append(f"Reformat the post specifically for the {plan.platform} platform.")

        # 3. Topic alignment check
        plan_topic_lower = (plan.topic or "").strip().lower()
        post_topic_lower = (post.topic or "").strip().lower()
        if (
            plan_topic_lower
            and post_topic_lower
            and plan_topic_lower != post_topic_lower
            and plan_topic_lower not in post_topic_lower
            and post_topic_lower not in plan_topic_lower
        ):
            checks.relevance = False
            issues.append(
                f"Topic divergence: Post topic '{post.topic}' does not match planned topic '{plan.topic}'."
            )
            feedback.append(f"Ensure the post focuses directly on the planned topic: '{plan.topic}'.")

        # 4. Platform length constraint checks
        content_len = len(content_stripped)
        if post_platform in ("twitter", "x"):
            if content_len > 350 and plan.content_type == "single_post":
                checks.length = False
                issues.append(
                    f"Platform length violation: X/Twitter post ({content_len} chars) exceeds maximum single-post limit of 350 chars."
                )
                feedback.append("Condense post copy to remain strictly under 350 characters for X/Twitter.")
        elif post_platform == "linkedin":
            if content_len > 0 and content_len < 30:
                checks.length = False
                issues.append(f"Platform length violation: LinkedIn post is too brief ({content_len} chars).")
                feedback.append("Expand on key insights to provide a valuable, readable LinkedIn post.")

        # 5. Hashtags count and format checks
        if post_platform in ("twitter", "x") and len(post.hashtags) > 4:
            checks.hashtags = False
            issues.append(f"Excessive hashtags for X/Twitter ({len(post.hashtags)} tags; recommended max is 3).")
            feedback.append("Reduce hashtags to 1-3 highly relevant tags.")
        elif post_platform == "linkedin" and len(post.hashtags) > 8:
            checks.hashtags = False
            issues.append(f"Excessive hashtags for LinkedIn ({len(post.hashtags)} tags; recommended max is 5).")
            feedback.append("Limit LinkedIn hashtags to 3-5 industry tags.")

        # 6. Call to Action (CTA) presence check
        if plan.cta_direction and len(plan.cta_direction.strip()) > 3:
            has_cta = bool(post.cta and len(post.cta.strip()) > 2)
            has_cta_in_text = (
                "?" in content_stripped
                or any(
                    phrase in content_stripped.lower()
                    for phrase in [
                        "let's discuss",
                        "what are your thoughts",
                        "comment below",
                        "share your",
                        "what do you think",
                        "how do you",
                        "tell us",
                        "join the conversation",
                    ]
                )
            )
            if not has_cta and not has_cta_in_text:
                checks.cta = False
                issues.append("Missing or unaligned Call to Action (CTA).")
                feedback.append(f"Add an engaging concluding question or CTA aligned with: '{plan.cta_direction}'.")

        # 7. Source grounding and citation checks
        valid_sources = {src.strip() for src in plan.source_references if src}
        if research and research.trends:
            for trend in research.trends:
                if trend.url:
                    valid_sources.add(trend.url.strip())
                if trend.source:
                    valid_sources.add(trend.source.strip())

        for ref in post.source_references:
            ref_clean = ref.strip()
            if ref_clean in valid_sources or any(vs in ref_clean for vs in valid_sources):
                verified_sources.append(ref_clean)
            else:
                checks.source_grounding = False
                issues.append(f"Unsupported or fabricated source reference: '{ref_clean}'.")
                feedback.append(f"Remove unverified source reference '{ref_clean}' and only cite grounded research.")
                unverified_claims.append(f"Fabricated source citation: {ref_clean}")

        if research is None and not plan.source_references:
            unverified_claims.append("Research evidence was not supplied for external factual verification.")

        # 8. Repetition and duplication checks
        sentences = [
            s.strip()
            for s in re.split(r"[.!?\n]+", content_stripped)
            if len(s.strip()) > 15
        ]
        sentence_counts: dict[str, int] = {}
        for s in sentences:
            s_lower = s.lower()
            sentence_counts[s_lower] = sentence_counts.get(s_lower, 0) + 1
            if sentence_counts[s_lower] == 2:
                checks.originality = False
                issues.append(f"Detected duplicate sentence repetition: '{s[:40]}...'")
                feedback.append("Eliminate repetitive sentence structures and duplicate phrases.")

        return checks, issues, feedback, verified_sources, unverified_claims

    def _build_critic_prompt(
        self,
        request: ReviewRequest,
        deterministic_issues: list[str],
    ) -> str:
        """Build structured prompt for LLM quality evaluation."""
        post = request.post
        plan = request.plan
        research = request.research

        research_context = "No external research evidence provided."
        if research and research.trends:
            trends_summary = []
            for t in research.trends:
                trends_summary.append(f"- Trend: {t.topic} | Summary: {t.summary} | Source: {t.source} ({t.url or 'no URL'})")
            research_context = "\n".join(trends_summary)

        key_points_formatted = "\n".join(f"- {kp}" for kp in plan.key_points)
        sources_formatted = "\n".join(f"- {src}" for src in plan.source_references) if plan.source_references else "- None"

        deterministic_summary = (
            "\n".join(f"- [Deterministic Warning]: {issue}" for issue in deterministic_issues)
            if deterministic_issues
            else "- All deterministic structural checks passed."
        )

        brand_context = f"\n### BRAND GUIDELINES:\n{request.brand_guidelines}\n" if request.brand_guidelines else ""

        return (
            f"### ORIGINAL CONTENT PLAN:\n"
            f"- Topic: {plan.topic}\n"
            f"- Strategic Angle: {plan.angle}\n"
            f"- Target Platform: {plan.platform}\n"
            f"- Target Audience: {plan.audience}\n"
            f"- Target Language: {plan.language}\n"
            f"- Planned Tone: {plan.tone}\n"
            f"- Hook Direction: {plan.hook_direction}\n"
            f"- Key Points:\n{key_points_formatted}\n"
            f"- CTA Direction: {plan.cta_direction}\n"
            f"- Planned Sources:\n{sources_formatted}\n"
            f"{brand_context}\n"
            f"### RESEARCH EVIDENCE CONTEXT:\n"
            f"{research_context}\n\n"
            f"### GENERATED SOCIAL POST TO EVALUATE:\n"
            f"- Platform: {post.platform}\n"
            f"- Topic: {post.topic}\n"
            f"- Language: {post.language}\n"
            f"- Content:\n\"\"\"\n{post.content}\n\"\"\"\n"
            f"- Hashtags: {', '.join(post.hashtags) if post.hashtags else 'None'}\n"
            f"- CTA: {post.cta or 'None'}\n"
            f"- Citations / Sources: {', '.join(post.source_references) if post.source_references else 'None'}\n\n"
            f"### PRELIMINARY DETERMINISTIC CHECKS:\n"
            f"{deterministic_summary}\n\n"
            f"### TASK:\n"
            f"Evaluate the generated SocialPost objectively. Identify any defects in tone, clarity, plan adherence, or grounding. "
            f"Return 'APPROVED' only if the post is publish-ready, or 'REVISE' with clear, actionable revision feedback."
        )

    async def review(self, request: ReviewRequest) -> CriticResult:
        """Evaluate a SocialPost against ContentPlan and ResearchResponse."""
        # Step 1: Pre-validation of input
        self._validate_request(request)

        logger.info(
            "CriticAgent evaluating post for topic '%s' on platform '%s'",
            request.post.topic,
            request.post.platform,
        )

        # Step 2: Run deterministic validation
        checks, det_issues, det_feedback, verified_sources, unverified_claims = (
            self._run_deterministic_checks(request)
        )

        prompt = self._build_critic_prompt(request, deterministic_issues=det_issues)
        last_error: Exception | None = None

        # Step 3: Bounded LLM Evaluation Loop
        llm_eval: _LLMEvaluation | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.debug("Generating Critic evaluation (attempt %d/%d)", attempt, self._max_retries)
                llm_eval = await self._llm_service.generate_structured(
                    schema=_LLMEvaluation,
                    prompt=prompt,
                    system_prompt=CRITIC_SYSTEM_PROMPT,
                )
                break
            except Exception as err:
                last_error = err
                logger.warning("Critic LLM evaluation attempt %d/%d failed: %s", attempt, self._max_retries, err)
                if attempt < self._max_retries:
                    await asyncio.sleep(0.3 * attempt)

        if llm_eval is None:
            raise CriticValidationFailedError(
                f"Critic Agent failed to evaluate post after {self._max_retries} attempts: {last_error}",
                original_error=last_error,
            )

        # Step 4: Decision Fusion & Normalization
        # Merge quality checks from LLM findings
        if not llm_eval.relevance_ok:
            checks.relevance = False
        if not llm_eval.plan_adherence_ok:
            checks.plan_adherence = False
        if not llm_eval.clarity_ok:
            checks.clarity = False
        if not llm_eval.tone_ok:
            checks.tone = False
        if not llm_eval.platform_fit_ok:
            checks.platform_fit = False
        if not llm_eval.cta_ok:
            checks.cta = False
        if not llm_eval.originality_ok:
            checks.originality = False

        # Consolidate issues (deterministic + LLM without duplicate strings)
        combined_issues: list[str] = list(det_issues)
        for issue in llm_eval.issues:
            if issue and issue not in combined_issues:
                combined_issues.append(issue)

        # Consolidate feedback (deterministic + LLM without duplicate strings)
        combined_feedback: list[str] = list(det_feedback)
        for fb in llm_eval.feedback:
            if fb and fb not in combined_feedback:
                combined_feedback.append(fb)

        # Consolidate unverified claims
        for claim in llm_eval.unverified_claims:
            if claim and claim not in unverified_claims:
                unverified_claims.append(claim)

        # Determine final decision:
        # If any deterministic check failed OR deterministic issues exist -> REVISE
        # If LLM evaluation is REVISE OR combined issues exist -> REVISE
        has_critical_failures = (
            not checks.relevance
            or not checks.plan_adherence
            or not checks.source_grounding
            or not checks.clarity
            or not checks.tone
            or not checks.platform_fit
            or not checks.length
            or not checks.cta
            or not checks.hashtags
            or not checks.originality
            or len(combined_issues) > 0
        )

        if has_critical_failures or llm_eval.decision == "REVISE":
            final_decision: CriticDecision = "REVISE"
        else:
            final_decision = "APPROVED"

        logger.info(
            "CriticAgent verdict for '%s': %s (%d issues, %d feedback items)",
            request.post.topic,
            final_decision,
            len(combined_issues),
            len(combined_feedback),
        )

        return CriticResult(
            decision=final_decision,
            issues=combined_issues,
            feedback=combined_feedback,
            checks=checks,
            verified_sources=verified_sources,
            unverified_claims=unverified_claims,
            evaluation_notes=llm_eval.evaluation_notes,
        )
