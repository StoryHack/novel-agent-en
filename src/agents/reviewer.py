"""Adversarial Reviewer Agent — fresh-context independent chapter critique.

Inspired by ai-job-search-master's drafter-reviewer dual-agent pattern:
  WriterAgent drafts → ReviewerAgent (fresh context) adversarially critiques
  → WriterAgent/RefinerAgent revises

KEY DESIGN: The reviewer uses an INDEPENDENT ModelScheduler call with a
fresh context. It does NOT share the writer's reasoning process, preventing
"self-satisfied" blind spots where an agent misses its own errors.

The reviewer's job is to be a SKEPTIC — find problems, not be nice.
"""

import logging

from pydantic import AliasChoices, BaseModel, Field

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft
from ..models.characters import CharacterRegistry
from ..models.memory import MemoryState
from ..models.outline import ChapterPlan, MasterOutline
from ..models.project import ProjectConfig
from ..models.review import Issue, ReviewReport
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


class AdversarialReviewOutput(BaseModel):
    """Structured output from the adversarial reviewer.

    More detailed than the standard ReviewOutput — designed to catch issues
    that a same-context reviewer would miss.
    """

    overall_score: float = Field(default=7.0, ge=0.0, le=10.0)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    # ── Adversarial-specific fields ──
    plot_holes: list[str] = Field(
        default_factory=list,
        description="Plot holes and contradictions the author may have missed",
        validation_alias=AliasChoices("plot_holes", "逻辑漏洞或情节矛盾（可能被作者忽略的）"),
    )
    character_inconsistencies: list[str] = Field(
        default_factory=list,
        description="Behavior that conflicts with established characterization",
        validation_alias=AliasChoices("character_inconsistencies", "角色行为与设定不符的地方"),
    )
    missed_opportunities: list[str] = Field(
        default_factory=list,
        description="Missed opportunities for payoffs, foreshadowing, or new information",
        validation_alias=AliasChoices("missed_opportunities", "本章应该做但没有做的事（爽点、伏笔、信息增量）"),
    )
    reader_drop_points: list[str] = Field(
        default_factory=list,
        description="Passages where readers may stop and the reasons why",
        validation_alias=AliasChoices("reader_drop_points", "读者可能弃书的段落及原因"),
    )
    revision_required: bool = Field(
        default=False,
        description="Whether revision is required",
        validation_alias=AliasChoices("revision_required", "是否需要强制修订"),
    )


# ============================================================
# Agent
# ============================================================


class ReviewerAgent(BaseAgent):
    """Adversarial chapter reviewer with fresh, independent context.

    This agent is designed to be instantiated with a SEPARATE scheduler
    instance (or at minimum, a separate provider) so it doesn't share
    the writer's LLM context. This is the key architectural insight
    from ai-job-search-master: a single agent reviewing its own work
    is "self-satisfied" and misses blind spots.

    Usage:
        # In orchestrator:
        reviewer = ReviewerAgent(scheduler)  # same scheduler, but...
        report = await reviewer.adversarial_review(
            draft=draft,
            chapter_plan=chapter_plan,
            bible=bible,
            characters=characters,
            outline=outline,
            memory=memory,
            # NOTE: does NOT receive the writer's internal reasoning
        )
    """

    agent_type = "reviewer"

    async def adversarial_review(
        self,
        draft: ChapterDraft,
        chapter_plan: ChapterPlan,
        bible: NovelBible,
        characters: CharacterRegistry,
        outline: MasterOutline | None = None,
        memory: MemoryState | None = None,
        config: ProjectConfig | None = None,
    ) -> AdversarialReviewOutput:
        """Perform an adversarial review of a chapter draft.

        Key difference from EditorAgent.review_chapter():
        - This is a SINGLE comprehensive pass (not multiple specialized checks)
        - The prompt is designed to make the LLM a SKEPTIC, not an editor
        - The reviewer does NOT see the writer's reasoning or the draft process
        - The reviewer independently verifies against the source materials

        Args:
            draft: The chapter draft to review.
            chapter_plan: The chapter plan the writer was supposed to follow.
            bible: World bible for consistency checking.
            characters: Character registry for behavior verification.
            outline: Master outline for plot coherence.
            memory: Memory state for continuity.
            config: Project config for style/tone verification.

        Returns:
            AdversarialReviewOutput with detailed critique.
        """
        logger.info(f"Adversarial review of chapter {draft.chapter_number}...")

        system_default = self._build_adversarial_system_prompt(bible, config)
        user_default = self._build_adversarial_user_prompt(
            draft=draft,
            chapter_plan=chapter_plan,
            bible=bible,
            characters=characters,
            outline=outline,
            memory=memory,
        )

        system, user = self.render_prompts(
            "adversarial_review",
            system_default=system_default,
            user_default=user_default,
            chapter_number=draft.chapter_number,
            chapter_title=draft.title,
        )

        try:
            result = await self.generate_structured(
                system_prompt=system,
                user_prompt=user,
                response_model=AdversarialReviewOutput,
                temperature_override=0.4,  # slightly more creative than Editor's 0.3
                max_tokens_override=4096,
            )
            logger.info(
                f"Adversarial review complete: score={result.overall_score}, "
                f"issues={len(result.issues)}, plot_holes={len(result.plot_holes)}, "
                f"revision_required={result.revision_required}"
            )
            return result
        except Exception as e:
            logger.error(f"Adversarial review failed: {e}")
            # Return a minimal output — don't block the pipeline
            return AdversarialReviewOutput(
                overall_score=7.0,
                issues=[],
                suggestions=[f"Adversarial review failed: {e}. Using Editor review only."],
                revision_required=False,
            )

    def to_review_report(self, adversarial: AdversarialReviewOutput) -> ReviewReport:
        """Convert adversarial review output to a standard ReviewReport.

        This allows the adversarial review to be merged into the existing
        review pipeline without changing downstream consumers.
        """
        # Add plot holes and reader drop points as critical issues
        all_issues = list(adversarial.issues)

        for hole in adversarial.plot_holes:
            all_issues.append(
                Issue(
                    severity="critical",
                    category="plot_hole",
                    description=hole,
                    suggestion="Need to repair this logical loophole: ensure the integrity of the causal chain",
                )
            )

        for drop in adversarial.reader_drop_points:
            all_issues.append(
                Issue(
                    severity="major",
                    category="reader_engagement",
                    description=f"Risk of losing readers: {drop}",
                    suggestion="Increase the payoff, suspense or information increment here",
                )
            )

        for missed in adversarial.missed_opportunities:
            all_issues.append(
                Issue(
                    severity="major",
                    category="missed_opportunity",
                    description=missed,
                    suggestion="Consider adding this element to this chapter",
                )
            )

        for inc in adversarial.character_inconsistencies:
            all_issues.append(
                Issue(
                    severity="major",
                    category="character",
                    description=inc,
                    suggestion="Check role-setting to ensure that there's a reasonable motive to act",
                )
            )

        # Calculate pass/fail
        avg_score = sum(adversarial.dimension_scores.values()) / max(len(adversarial.dimension_scores), 1)
        has_critical = any(i.severity == "critical" for i in all_issues) or bool(adversarial.plot_holes)

        return ReviewReport(
            chapter_number=0,  # Will be set by caller
            overall_score=adversarial.overall_score,
            dimension_scores=adversarial.dimension_scores,
            issues=all_issues,
            strengths=adversarial.strengths,
            suggestions=adversarial.suggestions,
            passed=avg_score >= 6.5 and not has_critical,
        )

    # ================================================================
    # Prompt builders
    # ================================================================

    def _build_adversarial_system_prompt(
        self,
        bible: NovelBible,
        config: ProjectConfig | None = None,
    ) -> str:
        """Build the adversarial system prompt.

        The key case is "picky reviewer" -- we want the LLM
        to actively look for problems, not to be balanced or diplomatic.
        """
        style = bible.style_contract

        prompt = f"""You are a rigorous fiction reviewer. Find contradictions, plot holes, pacing problems, inconsistent characterization, formulaic phrasing, and places where readers might stop.

1. Scrutinize each scene for problems.
2. Ask where readers might lose interest.
3. Check whether the setup will remain coherent later in the story.
4. Look for passages that could be cut without affecting the story.
5. State each issue directly.

Style reference:
- Tone: {style.tone}
- Sentence style: {style.sentence_style}
- Expressions to avoid: {", ".join(style.forbidden_phrases) if style.forbidden_phrases else "None"}
- Recommended techniques: {", ".join(style.preferred_techniques) if style.preferred_techniques else "None"}
"""

        if config:
            prompt += f"\nTarget readers: {config.target_readers}"

        return prompt

    def _build_adversarial_user_prompt(
        self,
        draft: ChapterDraft,
        chapter_plan: ChapterPlan,
        bible: NovelBible,
        characters: CharacterRegistry,
        outline: MasterOutline | None = None,
        memory: MemoryState | None = None,
    ) -> str:
        """Build the adversarial user prompt with independent context.

        IMPORTANT: This prompt is designed to give the reviewer the RAW MATERIALS
        (bible, characters, outline, chapter plan) but NOT the writer's reasoning
        or the drafting process. The reviewer forms its own judgment independently.
        """
        parts = []

        # ── Chapter metadata ──
        parts.append(f"## Review Chapter {draft.chapter_number}: {draft.title}")
        parts.append("")
        parts.append("Review this chapter closely and identify issues the author might have overlooked.")

        # ── What the chapter was SUPPOSED to do ──
        parts.append("")
        parts.append("## Chapter Plan")
        parts.append(f"- Goal: {chapter_plan.goal}")
        parts.append(f"- Central conflict: {chapter_plan.conflict}")
        parts.append(f"- New information: {chapter_plan.information_increment}")
        parts.append(f"- Planned ending hook: {chapter_plan.ending_hook}")
        parts.append(f"- Planned scenes: {len(chapter_plan.scenes)}")
        parts.append(f"- Target words: {chapter_plan.word_count_target} | Actual words: {draft.word_count}")
        parts.append(f"- Characters: {', '.join(chapter_plan.characters_involved)}")

        # ── Source materials (independent verification) ──
        parts.append("")
        parts.append("## World and Narrative Rules")
        if bible.rules:
            parts.append(f"- Point of view: {bible.rules.pov_constraint}")
            parts.append(f"- Tense: {bible.rules.tense}")
            parts.append(f"- Scene separator: {bible.rules.scene_break_style}")
        parts.append(f"- World type: {bible.world.world_type}")
        if bible.world.magic_system:
            parts.append(f"- Power system: {bible.world.magic_system}")

        # ── Character references ──
        parts.append("")
        parts.append("## Character Profiles")
        involved_ids = set()
        for cid, char in characters.characters.items():
            if char.name in chapter_plan.characters_involved:
                involved_ids.add(cid)
                parts.append(
                    f"- [{cid}] {char.name} ({char.role}): "
                    f"Personality: {char.personality[:80]} | Motivation: {char.motivation[:80]} | Flaw: {char.flaw[:60]}"
                )
        if not involved_ids:
            # Include all characters if none matched
            for cid, char in list(characters.characters.items())[:5]:
                parts.append(
                    f"- [{cid}] {char.name} ({char.role}): Personality: {char.personality[:80]} | Motivation: {char.motivation[:80]}"
                )

        # ── Outline context ──
        if outline:
            parts.append("")
            parts.append("## Story Outline")
            parts.append(f"- Main plot: {outline.logline}")
            current_volume = None
            for vol in outline.volumes or []:
                if hasattr(vol, "start_chapter") and hasattr(vol, "end_chapter"):
                    if vol.start_chapter <= draft.chapter_number <= vol.end_chapter:
                        current_volume = vol
                        break
            if current_volume:
                parts.append(f"- Current volume: {current_volume.title}")
                parts.append(f"- Volume spans chapters {current_volume.start_chapter}–{current_volume.end_chapter}")

        # ── Memory context ──
        if memory:
            st = memory.short_term
            if st:
                parts.append("")
                parts.append("## Previous Events")
                parts.append(f"- Previous chapter summary: {st.current_chapter_summary}")
                if st.unresolved_hooks:
                    parts.append(f"- Unresolved hooks: {st.unresolved_hooks}")

        # ── THE CHAPTER TEXT ──
        parts.append("")
        parts.append("## Chapter Text")
        parts.append("")
        # Include full text for thorough review
        max_len = 8000
        content = draft.content
        if len(content) > max_len:
            # Include first 1/3 and last 1/3, summarize middle
            third = max_len // 3
            parts.append(content[: third * 2])
            parts.append(f"\n... ({len(content) - third * 3} characters omitted) ...\n")
            parts.append(content[-third:])
        else:
            parts.append(content)

        # ── Review instructions ──
        parts.append("")
        parts.append("## Review Criteria")
        parts.append("""
### 1. Plot logic (plot_holes)
Identify forced events, missing causes, implausible decisions, and timeline problems.

### 2. Character consistency (character_inconsistencies)
Check actions against established traits, motives, and current states. Check whether characters have distinct voices. Flag out-of-character moments.

### 3. Payoffs and pacing (reader_drop_points)
Identify sections readers might skip. Assess how often satisfying developments occur, whether the first 300 words hook the reader, and whether the ending makes them want the next chapter. Check the emotional curve for variation.

### 4. Missed opportunities (missed_opportunities)
Identify important things the chapter omits and opportunities to develop the setting, advance foreshadowing, or strengthen payoffs.

### 5. Formulaic prose
Flag phrases such as "in summary" and "it is worth noting," overly regular paragraph structure, emotions stated without supporting action, and purely functional dialogue.

### 6. Overall assessment
Identify at least one major problem. Set revision_required to true if there is a plot hole, an out-of-character moment, or a score below 6.0. Otherwise set it to false.
""")

        return "\n".join(parts)
