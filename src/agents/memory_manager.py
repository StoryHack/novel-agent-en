"""Memory Manager Agent — updates memory artifacts after each chapter."""

import logging

from pydantic import AliasChoices, BaseModel, Field, field_validator

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft, Fact, PolishedChapter
from ..models.characters import CharacterRegistry
from ..models.memory import (
    ForeshadowingEntry,
    LongTermMemory,
    MemoryState,
    ShortTermMemory,
    TimelineEvent,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)

# Consolidation thresholds
STAGE_CHAPTERS = 10   # Every 10 chapters → stage summary
ARC_CHAPTERS = 50     # Every 50 chapters → arc summary
GLOBAL_CHAPTERS = 100  # Every 100 chapters → global summary


# ============================================================
# Structured output schemas
# ============================================================


class ChapterSummaryOutput(BaseModel):
    """LLM output for chapter summary and memory updates."""

    chapter_summary: str = Field(
        default="",
        description="Summary of this chapter (200 words)",
        validation_alias=AliasChoices("chapter_summary", "本章摘要（200字以内）"),
    )
    timeline_events: list[TimelineEvent] = Field(
        default_factory=list,
        description="Timeline Events",
        validation_alias=AliasChoices("timeline_events", "时间线事件"),
    )
    foreshadowing_updates: list[ForeshadowingEntry] = Field(
        default_factory=list,
        description="New, developed, or resolved foreshadowing",
        validation_alias=AliasChoices("foreshadowing_updates", "伏笔更新（新增/推进/回收）"),
    )
    world_changes: list[str] = Field(
        default_factory=list,
        description="Changes in the state of the world",
        validation_alias=AliasChoices("world_changes", "世界观变化"),
    )
    unresolved_issues: list[str] = Field(
        default_factory=list,
        description="Unresolved questions or plot threads",
        validation_alias=AliasChoices("unresolved_issues", "未解决的问题/线索"),
    )

    @field_validator("world_changes", "unresolved_issues", mode="before")
    @classmethod
    def coerce_list_field(cls, v):
        """Coerce non-list values into a list for list-typed fields.

        Local LLMs sometimes return booleans (True) or strings ('True')
        instead of a list — wrap them into a single-element list or
        return an empty list for bare True.
        """
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, bool):
            return [] if v is True else [v]
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                import json

                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            return [stripped]
        if isinstance(v, (int, float)):
            return [str(v)]
        return [str(v)]


# ============================================================
# Agent
# ============================================================


class MemoryManagerAgent(BaseAgent):
    """Manages short-term and long-term memory after each chapter is completed.

    Updates:
    - Chapter summaries (short-term + long-term)
    - Timeline events
    - Foreshadowing tracker (new / advance / payoff)
    - Character states
    - World changes
    - Known facts registry
    """

    agent_type = "memory_manager"

    async def update_memory(
        self,
        polished: PolishedChapter,
        draft: ChapterDraft,
        bible: NovelBible,
        characters: CharacterRegistry,
        existing_memory: MemoryState | None = None,
    ) -> MemoryState:
        """Update all memory artifacts after chapter completion.

        Args:
            polished: The polished/final chapter.
            draft: The original draft (has extracted facts and state changes).
            bible: Novel bible for context.
            characters: Character registry.
            existing_memory: Previous memory state to update.

        Returns:
            Updated MemoryState.
        """
        logger.info(f"Updating memory for chapter {polished.chapter_number}...")

        # Build context
        prev_summary = ""
        prev_foreshadowing = ""
        if existing_memory:
            prev_summary = existing_memory.short_term.current_chapter_summary
            active_fs = existing_memory.foreshadowing.active
            prev_foreshadowing = "\n".join(
                f"- [{e.id}] Introduced in Chapter {e.planted_chapter}: {e.description} (expected payoff chapter: {e.expected_payoff_chapter})"
                for e in active_fs
            )

        system_default = self.build_system_prompt(
            role="story memory manager",
            expertise="Keep a precise record of chapter events, character changes, new foreshadowing, and developments in existing plot threads. Preserve all important information.",
        )
        user_default = f"""Update the story memory for Chapter {polished.chapter_number}: {polished.title}.

Chapter excerpt: {draft.content[:600]}

New facts:
{self._format_facts(draft.new_facts)}

Character state changes:
{self._format_state_changes(draft.character_state_changes)}

Previous chapter summary: {prev_summary or 'This is the first chapter'}

Active foreshadowing:
{prev_foreshadowing or 'None'}

Produce:
1. A chapter summary of at most 200 words covering key events and developments.
2. One to three important timeline events, with in-world time, description, characters, and importance.
3. Foreshadowing updates for new setups, developments, and payoffs.
4. Changes to the state of the world.
5. Unresolved questions or clues left by the chapter."""

        system, user = self.render_prompts(
            "update_memory",
            system_default=system_default,
            user_default=user_default,
            chapter_number=polished.chapter_number,
            chapter_title=polished.title,
            chapter_excerpt=draft.content[:600],
            facts_text=self._format_facts(draft.new_facts),
            state_changes_text=self._format_state_changes(draft.character_state_changes),
            prev_summary=prev_summary or "This is the first chapter",
            prev_foreshadowing=prev_foreshadowing or "None",
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ChapterSummaryOutput,
            temperature_override=0.3,
        )

        # Build updated memory
        memory = existing_memory or MemoryState()

        # Short-term memory
        memory.short_term = ShortTermMemory(
            current_chapter_summary=result.chapter_summary,
            previous_chapter_summary=(memory.short_term.current_chapter_summary if memory.short_term else ""),
            recent_character_states=memory.character_states if memory.character_states else {},
            active_foreshadowing=[e.id for e in result.foreshadowing_updates if e.status == "active"],
            unresolved_hooks=result.unresolved_issues,
        )

        # Long-term memory
        if memory.long_term is None:
            memory.long_term = LongTermMemory()

        memory.long_term.chapter_summaries[polished.chapter_number] = result.chapter_summary

        # Merge facts
        for fact in draft.new_facts:
            memory.long_term.facts[fact.id] = fact

        # Timeline
        memory.timeline.extend(result.timeline_events)

        # Foreshadowing
        for entry in result.foreshadowing_updates:
            existing = next(
                (e for e in memory.foreshadowing.entries if e.id == entry.id),
                None,
            )
            if existing:
                # Update existing entry
                existing.status = entry.status
                existing.payoff_chapter = entry.payoff_chapter
            else:
                memory.foreshadowing.entries.append(entry)

        # Character states
        for change in draft.character_state_changes:
            if change.character_id not in memory.character_states:
                memory.character_states[change.character_id] = {}
            memory.character_states[change.character_id][change.attribute] = change.new_value

        logger.info(
            f"Memory updated: {len(result.timeline_events)} timeline events, "
            f"{len(result.foreshadowing_updates)} foreshadowing updates"
        )
        return memory

    # ================================================================
    # Hierarchical consolidation
    # ================================================================

    async def consolidate_periodically(
        self,
        memory: MemoryState,
        chapter_num: int,
    ) -> MemoryState:
        """Generate hierarchical summaries at threshold boundaries.

        - Every 10 chapters → stage summary (~500 chars)
        - Every 50 chapters → arc summary (~800 chars)
        - Every 100 chapters → global summary (~1000 chars)

        Returns the updated memory (mutated in place).
        """
        if chapter_num % STAGE_CHAPTERS == 0 and chapter_num > 0:
            memory = await self._consolidate_stage(memory, chapter_num)

        if chapter_num % ARC_CHAPTERS == 0 and chapter_num > 0:
            memory = await self._consolidate_arc(memory, chapter_num)

        if chapter_num % GLOBAL_CHAPTERS == 0 and chapter_num > 0:
            memory = await self._consolidate_global(memory, chapter_num)

        return memory

    async def _consolidate_stage(
        self, memory: MemoryState, chapter_num: int
    ) -> MemoryState:
        """Compress the last 10 chapters into a stage summary."""
        stage_num = chapter_num // STAGE_CHAPTERS
        start_ch = chapter_num - STAGE_CHAPTERS + 1
        end_ch = chapter_num

        # Gather chapter summaries for this stage
        summaries = []
        for ch in range(start_ch, end_ch + 1):
            s = memory.long_term.chapter_summaries.get(ch, "")
            if s:
                summaries.append(f"Chapter {ch}: {s}")

        if not summaries:
            logger.warning(f"No summaries found for stage {stage_num} (chapters {start_ch}-{end_ch})")
            return memory

        # Gather timeline events in this range
        stage_events = [e for e in memory.timeline if start_ch <= e.chapter <= end_ch]
        events_text = "\n".join(
            f"- Chapter {e.chapter} {e.in_story_time}: {e.description}" for e in stage_events[-20:]
        )

        system = self.build_system_prompt(
            role="story summarizer",
            expertise="Condense chapters while retaining key plot developments, character changes, and foreshadowing.",
        )

        user = f"""Condense the following {STAGE_CHAPTERS} chapters into a stage summary of at most 500 words.

Chapter range: {start_ch}–{end_ch}

Chapter summaries:
{chr(10).join(summaries)}

Key timeline events:
{events_text or "None"}

Active foreshadowing:
{chr(10).join(f"- {e.description}" for e in memory.foreshadowing.active[:10]) or "None"}

Cover the two or three most important plot developments, changes to major characters, important setups introduced or developed, and where the story stands at the end of the stage. Return only the summary text."""

        result = await self.generate(
            system_prompt=system,
            user_prompt=user,
            temperature_override=0.3,
        )

        summary = result.content.strip()
        memory.long_term.stage_summaries[stage_num] = summary
        memory.stage_boundaries.append(chapter_num)
        logger.info(
            f"Stage {stage_num} summary generated ({len(summary)} chars): chapters {start_ch}-{end_ch}"
        )
        return memory

    async def _consolidate_arc(
        self, memory: MemoryState, chapter_num: int
    ) -> MemoryState:
        """Compress the last 50 chapters into an arc summary."""
        arc_num = chapter_num // ARC_CHAPTERS
        start_ch = chapter_num - ARC_CHAPTERS + 1
        end_ch = chapter_num

        # Use stage summaries as building blocks
        stage_texts = []
        for sn in sorted(memory.long_term.stage_summaries.keys()):
            s_start = (sn - 1) * STAGE_CHAPTERS + 1
            s_end = sn * STAGE_CHAPTERS
            if s_start >= start_ch and s_end <= end_ch:
                stage_texts.append(f"Stage {sn} (Chapters {s_start}–{s_end}): {memory.long_term.stage_summaries[sn]}")

        if not stage_texts:
            # Fallback: use raw chapter summaries
            summaries = []
            for ch in range(start_ch, end_ch + 1):
                s = memory.long_term.chapter_summaries.get(ch, "")
                if s:
                    summaries.append(f"Chapter {ch}: {s}")
            if not summaries:
                logger.warning(f"No data for arc {arc_num}")
                return memory
            stage_texts = [chr(10).join(summaries[:50])]

        # Key timeline events for this arc
        arc_events = [
            e for e in memory.timeline
            if start_ch <= e.chapter <= end_ch and e.importance == "major"
        ]
        events_text = "\n".join(
            f"- Chapter {e.chapter}: {e.description}" for e in arc_events[-15:]
        )

        system = self.build_system_prompt(
            role="story arc summarizer",
            expertise="Summarize the arc's conflicts, character development, and themes.",
        )

        user = f"""Condense the following {ARC_CHAPTERS} chapters into an arc summary of at most 800 words.

Chapter range: {start_ch}–{end_ch}

Stage summaries:
{chr(10).join(stage_texts)}

Major events:
{events_text or "None"}

Active foreshadowing:
{chr(10).join(f"- {e.description} (introduced in Chapter {e.planted_chapter})" for e in memory.foreshadowing.active[:15]) or "None"}

Cover the arc's main conflicts and how they evolved, the development of key characters, setups resolved and still active, important world changes or revelations, and the story state at the end of the arc. Return only the summary text."""

        result = await self.generate(
            system_prompt=system,
            user_prompt=user,
            temperature_override=0.3,
        )

        summary = result.content.strip()
        memory.long_term.arc_summaries[arc_num] = summary
        memory.arc_boundaries.append(chapter_num)
        logger.info(f"Arc {arc_num} summary generated ({len(summary)} chars): chapters {start_ch}-{end_ch}")
        return memory

    async def _consolidate_global(
        self, memory: MemoryState, chapter_num: int
    ) -> MemoryState:
        """Update the global story summary from arc summaries."""
        arc_texts = []
        for an in sorted(memory.long_term.arc_summaries.keys()):
            arc_texts.append(f"Arc {an}: {memory.long_term.arc_summaries[an]}")

        if not arc_texts:
            logger.warning("No arc summaries for global consolidation")
            return memory

        system = self.build_system_prompt(
            role="novel summarizer",
            expertise="Summarize completed arcs so the author can see the overall structure of the novel.",
        )

        user = f"""Condense the completed arcs into a story-wide summary of at most 1,000 words.

Completed arcs:
{chr(10).join(arc_texts)}

Summarize the story's major phases to date, the protagonist's growth, resolved and ongoing conflicts, the current situation, and remaining plot threads. Return only the summary text."""

        result = await self.generate(
            system_prompt=system,
            user_prompt=user,
            temperature_override=0.3,
        )

        memory.long_term.global_summary = result.content.strip()
        logger.info(
            f"Global summary updated ({len(memory.long_term.global_summary)} chars) at chapter {chapter_num}"
        )
        return memory

    def _format_facts(self, facts: list[Fact]) -> str:
        if not facts:
            return "(No new facts)"
        return "\n".join(f"- [{f.category}] {f.description} (Certainty: {f.certainty})" for f in facts)

    def _format_state_changes(self, changes: list) -> str:
        if not changes:
            return "(No character state changes)"
        return "\n".join(f"- {c.character_id}: {c.attribute} ({c.old_value} → {c.new_value})" for c in changes)
