"""Continuity Checker Agent — timeline, causality, and foreshadowing verification."""

import logging

from pydantic import BaseModel, Field

from ..models.chapter import ChapterDraft
from ..models.characters import CharacterRegistry
from ..models.memory import MemoryState
from ..models.review import Issue
from .base import BaseAgent

logger = logging.getLogger(__name__)


class ContinuityOutput(BaseModel):
    """LLM output for continuity check."""

    issues: list[Issue] = Field(default_factory=list)


class ContinuityCheckerAgent(BaseAgent):
    """Verifies timeline consistency, causality chains, and character behavior continuity.

    This agent focuses on factual/logical consistency — it's not about style or pacing.
    It answers: "Does this make sense given everything we know?"
    """

    agent_type = "continuity_checker"

    async def check_timeline(
        self,
        draft: ChapterDraft,
        memory: MemoryState | None = None,
    ) -> list[Issue]:
        """Check that timeline events are consistent and correctly ordered."""
        prev_events = ""
        if memory and memory.timeline:
            recent = memory.timeline[-30:]  # Last 30 events (was 10)
            prev_events = "\n".join(
                f"- [{e.id}] Chapter {e.chapter}: {e.description} (story time: {e.in_story_time})" for e in recent
            )
        prev_events = prev_events or "None (first chapter)"

        chapter_text = self._chapter_excerpt(draft.content)

        system_default = self.build_system_prompt(
            role="timeline reviewer",
            expertise="Compare the full chapter with the timeline to find unexplained time jumps, events out of order, and other chronological inconsistencies.",
        )
        user_default = f"""Check this chapter against the story timeline.

Previous events (up to 30):
{prev_events}

Full chapter:
{chapter_text}

Check the order of events and whether time references such as "three days later" fit the preceding chapters. Look for unexplained time jumps and events that could not plausibly fit into the same day. List even minor inconsistencies."""

        system, user = self.render_prompts(
            "check_timeline",
            system_default=system_default,
            user_default=user_default,
            prev_events=prev_events,
            chapter_text=chapter_text,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ContinuityOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )
        return result.issues

    async def check_character_consistency(
        self,
        draft: ChapterDraft,
        characters: CharacterRegistry,
        memory: MemoryState | None = None,
    ) -> list[Issue]:
        """Check that characters behave consistently with their profiles and recent states."""
        char_briefs = []
        for cid, char in characters.characters.items():
            state = char.current_state
            if memory and cid in memory.character_states:
                state = memory.character_states[cid]
            char_briefs.append(
                f"- [{cid}] {char.name} ({char.role}): Personality: {char.personality[:80]}, "
                f"Motivation: {char.motivation[:80]}, Flaw: {char.flaw[:60]}, Current state: {state}"
            )
        char_text = "\n".join(char_briefs)

        chapter_text = self._chapter_excerpt(draft.content)

        system_default = self.build_system_prompt(
            role="character continuity reviewer",
            expertise="Compare each character's words and actions in the chapter with their profile, motivation, and current state. Flag abrupt changes that lack a convincing explanation, while allowing credible growth.",
        )
        user_default = f"""Check the characters' behavior in this chapter.

Full character profiles:
{char_text}

Full chapter:
{chapter_text}

For each character, check whether their words and actions match their personality, motivation, and flaws. Verify that key decisions have sufficient setup and that interactions reflect established relationships and shared history. Flag unmotivated out-of-character behavior and assess whether growth feels credible. Include even subtle inconsistencies."""

        system, user = self.render_prompts(
            "check_character_consistency",
            system_default=system_default,
            user_default=user_default,
            char_text=char_text,
            chapter_text=chapter_text,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ContinuityOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )
        return result.issues

    async def check_causality(
        self,
        draft: ChapterDraft,
        memory: MemoryState | None = None,
    ) -> list[Issue]:
        """Check that events have proper cause-and-effect relationships."""
        chapter_text = self._chapter_excerpt(draft.content)

        # Include recent timeline for cross-chapter causality context
        prev_context = ""
        if memory and memory.timeline:
            recent = memory.timeline[-15:]
            prev_context = "\n" + "\n".join(
                f"- Chapter {e.chapter}: {e.description}" for e in recent
            )

        system_default = self.build_system_prompt(
            role="narrative causality reviewer",
            expertise="Trace the causal chain between events. Flag plot-driven contrivances and coincidences without credible setup. Inspect each event in the full chapter.",
        )
        user_default = f"""{prev_context}

Full chapter:
{chapter_text}

Review each event:
- Does the event have a credible cause?
- Do coincidences drive the plot more than twice?
- Do the characters have enough motivation for their key decisions?
- Do any resolutions rely on a deus ex machina?
- Is the causal chain missing a link?"""

        system, user = self.render_prompts(
            "check_causality",
            system_default=system_default,
            user_default=user_default,
            prev_context=prev_context,
            chapter_text=chapter_text,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ContinuityOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )
        return result.issues

    async def check_foreshadowing(
        self,
        draft: ChapterDraft,
        memory: MemoryState | None = None,
    ) -> list[Issue]:
        """Check foreshadowing usage — what's being planted, advanced, or paid off."""
        active_fs = ""
        if memory and memory.foreshadowing:
            all_entries = memory.foreshadowing.entries
            active_fs = "\n".join(
                f"- [{e.id}] Introduced in Chapter {e.planted_chapter}: {e.description} "
                f"(status: {e.status}, expected payoff chapter: {e.expected_payoff_chapter})"
                for e in all_entries
            )
        active_fs = active_fs or "None"

        chapter_text = self._chapter_excerpt(draft.content)

        system_default = self.build_system_prompt(
            role="foreshadowing reviewer",
            expertise="Track each setup through its introduction, development, and payoff. Compare the chapter with all active foreshadowing and flag forgotten setups or weak payoffs.",
        )
        user_default = f"""Review the handling of foreshadowing in this chapter.

Foreshadowing records:
{active_fs}

Full chapter:
{chapter_text}

- Identify new setups and cite their locations.
- Note any existing setups developed further and how they build anticipation.
- Identify setups paid off here and assess whether the payoffs feel earned.
- Flag abrupt or underdeveloped payoffs.
- Flag active setups unmentioned for more than 50 chapters.
- Flag setups past their planned payoff chapter."""

        system, user = self.render_prompts(
            "check_foreshadowing",
            system_default=system_default,
            user_default=user_default,
            active_fs=active_fs,
            chapter_text=chapter_text,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ContinuityOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )
        return result.issues
