"""Editor Agent — quality review across multiple dimensions."""

import logging

from pydantic import BaseModel, Field

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft
from ..models.characters import CharacterRegistry
from ..models.memory import MemoryState
from ..models.outline import ChapterPlan
from ..models.review import Issue, ReviewReport
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


class ReviewOutput(BaseModel):
    """LLM output for quality review."""

    overall_score: float = Field(default=7.0, ge=0.0, le=10.0)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ConsistencyOutput(BaseModel):
    """LLM output for continuity/consistency check."""

    issues: list[Issue] = Field(default_factory=list)


class AiFlavorOutput(BaseModel):
    """LLM output for AI-flavor detection."""

    score: float = Field(default=8.0, ge=0.0, le=10.0, description="Naturalness score (higher is more natural)")
    issues: list[Issue] = Field(default_factory=list)


# ============================================================
# Agent
# ============================================================


class EditorAgent(BaseAgent):
    """Performs multi-dimensional quality review of chapter drafts.

    Review dimensions:
    - consistency: Setting/world consistency
    - character: Character behavior consistency
    - pacing: Narrative pacing
    - hook: Hook and pleasure-point effectiveness
    - style: Writing style stability
    - ai_flavor: AI-generated text detection
    """

    agent_type = "editor"

    async def review_chapter(
        self,
        draft: ChapterDraft,
        chapter_plan: ChapterPlan,
        bible: NovelBible,
        characters: CharacterRegistry,
        memory: MemoryState | None = None,
    ) -> ReviewReport:
        """Run all quality checks and produce a review report."""
        logger.info(f"Reviewing chapter {draft.chapter_number}...")

        # Run checks (could be parallel, but sequential is simpler for MVP)
        consistency_issues = await self.check_consistency(draft, bible, characters, memory)
        pacing_issues = await self.check_pacing(draft, chapter_plan)
        style_issues = await self.check_style(draft, bible)
        ai_flavor_result = await self.detect_ai_flavor(draft)

        # Combine into a comprehensive review
        system_default = self.build_system_prompt(
            role="lead fiction editor",
            expertise="Review novel chapters across multiple dimensions, score them accurately, and give constructive revision suggestions.",
        )

        all_issues = consistency_issues + pacing_issues + style_issues + ai_flavor_result.issues

        issues_text = "\n".join(f"[{i.severity}][{i.category}] {i.description}" for i in all_issues)

        chapter_text = self._chapter_excerpt(draft.content)

        template_vars = {
            "chapter_number": draft.chapter_number,
            "goal": chapter_plan.goal,
            "emotional_curve": str([(b.position, b.emotion) for b in chapter_plan.emotional_curve]),
            "ending_hook": chapter_plan.ending_hook,
            "chapter_text": chapter_text,
            "issues_text": issues_text or "No specific issues",
        }

        user_default = f"""Review Chapter {draft.chapter_number}.

Goal: {chapter_plan.goal}
Planned emotional curve: {str([(b.position, b.emotion) for b in chapter_plan.emotional_curve])}
Planned ending hook: {chapter_plan.ending_hook}

Full chapter:
{chapter_text}

Issues from specialized checks:
{issues_text or 'No specific issues'}

Give an overall score (0–10) and individual scores for:
- consistency: Continuity with established facts and rules
- character: Consistency of characterization
- pacing: Narrative pace
- hook: Effectiveness of payoffs and hooks
- style: Consistency of prose style
- ai_flavor: Naturalness of the prose (higher is more natural)

List major issues in order of severity, describe what works, and give actionable revisions. Score objectively and identify problems directly."""

        system, user = self.render_prompts(
            "review_chapter",
            system_default=system_default,
            user_default=user_default,
            **template_vars,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ReviewOutput,
            temperature_override=0.3,
        )

        # Add AI flavor score from the specialized check
        if "ai_flavor" not in result.dimension_scores:
            result.dimension_scores["ai_flavor"] = ai_flavor_result.score
        result.issues.extend(ai_flavor_result.issues)

        # Determine pass/fail
        avg_score = sum(result.dimension_scores.values()) / max(len(result.dimension_scores), 1)
        has_critical = any(i.severity == "critical" for i in result.issues)
        passed = avg_score >= 6.5 and not has_critical

        report = ReviewReport(
            chapter_number=draft.chapter_number,
            overall_score=result.overall_score,
            dimension_scores=result.dimension_scores,
            issues=result.issues,
            strengths=result.strengths,
            suggestions=result.suggestions,
            passed=passed,
        )

        logger.info(
            f"Chapter {draft.chapter_number} review: score={report.overall_score}, "
            f"passed={report.passed}, issues={len(report.issues)}"
        )
        return report

    # ================================================================
    # Individual check methods
    # ================================================================

    async def check_consistency(
        self,
        draft: ChapterDraft,
        bible: NovelBible,
        characters: CharacterRegistry,
        memory: MemoryState | None = None,
    ) -> list[Issue]:
        """Check world setting and character behavior consistency."""
        system = self.build_system_prompt(
            role="story continuity editor",
            expertise="Compare the chapter with the world rules, character profiles, and known facts to identify inconsistencies.",
        )

        # Build known facts summary (increase from 20 to 50)
        known_facts = ""
        if memory and memory.long_term:
            facts_list = list(memory.long_term.facts.values())
            known_facts = "\n".join(f"- [{f.category}] {f.description}" for f in facts_list[:50])

        chapter_text = self._chapter_excerpt(draft.content)

        user = f"""Check this chapter for continuity problems.

World rules: {bible.rules.model_dump_json() if bible.rules else "None specified"}
Character summaries: {self._format_character_briefs(characters)}
Known facts (up to 50): {known_facts or "None (first chapter)"}

Chapter text:
{chapter_text}

Identify violations of world rules, behavior that conflicts with a character's traits or motives, contradictions with known facts, and problems with chronology or causality. Include even minor inconsistencies."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ConsistencyOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )
        return result.issues

    async def check_pacing(
        self,
        draft: ChapterDraft,
        chapter_plan: ChapterPlan,
    ) -> list[Issue]:
        """Check narrative pacing."""
        system = self.build_system_prompt(
            role="narrative pacing editor",
            expertise="Assess scene pacing and emotional variation. Identify passages that drag or rush important events.",
        )

        chapter_text = self._chapter_excerpt(draft.content)

        user = f"""Review the chapter's pacing.

Planned scenes: {len(chapter_plan.scenes)}
Planned emotional curve: {[(b.position, b.emotion, b.intensity) for b in chapter_plan.emotional_curve]}
Target words: {chapter_plan.word_count_target}
Actual words: {draft.word_count}

Chapter text:
{chapter_text}

Check scene by scene. Does the length of each scene match its importance? Do transitions feel natural and do the emotional beats follow the plan? Point out passages that drag or rush important developments."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ConsistencyOutput,
            temperature_override=0.3,
        )
        return result.issues

    async def check_style(
        self,
        draft: ChapterDraft,
        bible: NovelBible,
    ) -> list[Issue]:
        """Check writing style stability against the style contract."""
        style = bible.style_contract
        system = self.build_system_prompt(
            role="prose style editor",
            expertise="Check the prose against the style contract, including word choice, repetition, and tone.",
        )

        chapter_text = self._chapter_excerpt(draft.content, max_chars=4000)

        user = f"""Check whether the chapter follows the style contract.

Tone: {style.tone}
Sentence style: {style.sentence_style}
Narrative distance: {style.narrative_distance}
Expressions to avoid: {style.forbidden_phrases}
Recommended techniques: {style.preferred_techniques}

Chapter text:
{chapter_text}

Check for repetitive sentence structures (three or more in a row), words repeated too closely, inappropriate shifts in tone, prohibited expressions, an imbalanced dialogue-to-description ratio, and inconsistent narrative distance."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ConsistencyOutput,
            temperature_override=0.3,
        )
        return result.issues

    async def detect_ai_flavor(self, draft: ChapterDraft) -> AiFlavorOutput:
        """Detect AI-generated text patterns."""
        system = self.build_system_prompt(
            role="fiction editor who detects formulaic prose",
            expertise="Identify formulaic transitions, repetitive structure, flat emotions, stock phrasing, and overused conjunctions.",
        )

        chapter_text = self._chapter_excerpt(draft.content, max_chars=3000)

        user = f"""Assess how formulaic this prose sounds.

Text:
{chapter_text}

Look for stock transitions, repetitive paragraph structures, emotions named without supporting actions, interchangeable or overly functional dialogue, and uniformly paced scenes. Examples include "in summary," "it is worth noting," "in the process of," and "not only ... but also."

Score the prose from 0 (highly formulaic) to 10 (fully natural), cite specific passages, and suggest revisions."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=AiFlavorOutput,
            temperature_override=0.3,
        )
        return result

    # ================================================================
    # Helpers
    # ================================================================

    def _format_character_briefs(self, characters: CharacterRegistry) -> str:
        """Format brief character descriptions."""
        lines = []
        for cid, char in characters.characters.items():
            lines.append(f"- [{cid}] {char.name}: {char.personality[:80]} | Motivation: {char.motivation[:60]}")
        return "\n".join(lines)

    def _summarize_chapter(self, draft: ChapterDraft) -> str:
        """Create a brief summary of the chapter content."""
        content = draft.content
        if len(content) <= 500:
            return content
        # Return first 250 + last 250 chars as summary context
        return content[:250] + "\n...\n" + content[-250:]
