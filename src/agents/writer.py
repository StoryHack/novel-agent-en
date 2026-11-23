"""Writer Agent — generates chapter drafts with full context awareness."""

import logging
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft, Fact, StateChange
from ..models.characters import CharacterRegistry
from ..models.memory import MemoryState
from ..models.outline import ChapterPlan, EmotionalBeat, MasterOutline, Scene
from ..models.project import ProjectConfig
from ..utils.text import count_words
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


class ChapterContentOutput(BaseModel):
    """LLM output for chapter content."""

    title: str = Field(default="", description="Chapter title", validation_alias=AliasChoices("title", "章节标题"))
    content: str = Field(
        default="",
        description="Chapter body (Markdown format)",
        validation_alias=AliasChoices("content", "章节正文（Markdown格式）"),
    )
    author_notes: str = Field(
        default="",
        description="Author notes",
        validation_alias=AliasChoices("author_notes", "作者附注"),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        """Handle Qwen3 output quirks for chapter content."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Alias: description / notes → author_notes
        if "author_notes" not in d or not d.get("author_notes"):
            for alias in ("description", "notes", "备注", "附注"):
                if alias in d and alias != "content":
                    d["author_notes"] = d.pop(alias)
                    break
        # content is required by prompt; use empty string as safe fallback
        if "content" not in d or not d.get("content"):
            for alias in ("正文", "text", "body"):
                if alias in d:
                    d["content"] = d.pop(alias)
                    break
        return d


class FactExtractionOutput(BaseModel):
    """LLM output for fact extraction from chapter."""

    new_facts: list[Fact] = Field(
        default_factory=list,
        description="Newly established facts",
        validation_alias=AliasChoices("new_facts", "新增事实"),
    )
    state_changes: list[StateChange] = Field(
        default_factory=list,
        description="Character state changes",
        validation_alias=AliasChoices("state_changes", "角色状态变化"),
    )
    contradictions: list[str] = Field(
        default_factory=list,
        description="New facts that contradict established facts, or an empty list",
        validation_alias=AliasChoices("contradictions", "与已有事实矛盾的新事实描述（如无矛盾则为空列表）"),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        """Handle Qwen3 output quirks for fact extraction."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Coerce string items in state_changes list
        if "state_changes" in d and isinstance(d["state_changes"], list):
            d["state_changes"] = [{"reason": x} if isinstance(x, str) else x for x in d["state_changes"]]
        # Coerce string items in new_facts list (Fact already handles this,
        # but be extra safe)
        if "new_facts" in d and isinstance(d["new_facts"], list):
            d["new_facts"] = [{"description": x} if isinstance(x, str) else x for x in d["new_facts"]]
        return d


def _build_expansion_prompt(
    content: str,
    current_count: int,
    target_count: int,
    chapter_num: int,
    chapter_title: str,
) -> str:
    """Build a prompt asking the model to expand a too-short chapter."""
    return f"""Chapter {chapter_num}, "{chapter_title}", is {current_count} words. Expand it to at least {target_count} words.

- Add sensory details to each setting, including atmosphere, light, sounds, and smells.
- Add movement, expressions, and thoughts between lines of dialogue.
- Give key events enough setup and smooth transitions.
- Develop the characters' thoughts and reactions.
- Preserve the plot structure and ending while adding detail.

Current chapter:
{content}

Return the complete revised chapter in the same JSON format. Preserve title and author_notes and change only content.
Add at least {target_count - current_count} words to reach the {target_count}-word minimum."""


# ============================================================
# Agent
# ============================================================


class WriterAgent(BaseAgent):
    """Writes chapter drafts with full awareness of the novel bible, outline,
    character states, and memory context."""

    agent_type = "writer"

    async def generate_chapter(
        self,
        chapter_plan: ChapterPlan,
        config: ProjectConfig,
        bible: NovelBible,
        characters: CharacterRegistry,
        outline: MasterOutline,
        memory: MemoryState | None = None,
        revision_feedback: str | None = None,
        rag_context: str = "",
    ) -> ChapterDraft:
        """Generate a complete chapter draft.

        Args:
            chapter_plan: Detailed chapter plan.
            config: Project configuration.
            bible: Novel bible for world/setting reference.
            characters: Character registry with current states.
            outline: Master outline for story context.
            memory: Memory state with recent summaries.
            revision_feedback: If set, this is a revision — include editor feedback.
            rag_context: Optional RAG-retrieved context string for semantic search.

        Returns:
            ChapterDraft with the written content and extracted metadata.
        """
        logger.info(f"Writing chapter {chapter_plan.chapter_number}...")

        # Build context block
        context = self._build_full_context(
            chapter_plan=chapter_plan,
            config=config,
            bible=bible,
            characters=characters,
            outline=outline,
            memory=memory,
            rag_context=rag_context,
        )

        chapter_num = chapter_plan.chapter_number
        chapter_title = chapter_plan.title

        # Template variables
        template_vars = {
            "language": config.language,
            "tone": bible.style_contract.tone,
            "sentence_style": bible.style_contract.sentence_style,
            "word_count_target": chapter_plan.word_count_target,
            "pov_constraint": bible.rules.pov_constraint,
            "tense": bible.rules.tense,
            "forbidden_phrases": ", ".join(bible.style_contract.forbidden_phrases) if bible.style_contract.forbidden_phrases else "None specified",
            "scene_break_style": bible.rules.scene_break_style,
            "chapter_number": chapter_num,
            "chapter_title": chapter_title,
            "goal": chapter_plan.goal,
            "conflict": chapter_plan.conflict,
            "information_increment": chapter_plan.information_increment,
            "ending_hook": chapter_plan.ending_hook,
            "context": context,
            "scenes_formatted": self._format_scenes(chapter_plan.scenes),
            "emotional_curve_formatted": self._format_emotional_curve(chapter_plan.emotional_curve),
            "characters_involved": ", ".join(chapter_plan.characters_involved),
            "scene_count": len(chapter_plan.scenes),
            "per_scene_min": max(1000, chapter_plan.word_count_target // max(len(chapter_plan.scenes), 1)),
            "revision_feedback": revision_feedback or "",
        }

        # Inline defaults (kept in sync with templates)
        system_default = self.build_system_prompt(
            role="fiction writer",
            expertise="Write engaging chapters with precise description, natural dialogue, and deliberate pacing. Work the setting into the prose, give characters clear motivations, and make every scene serve a purpose.",
            constraints=f"""Writing constraints:
- Language: {template_vars['language']}
- Tone: {template_vars['tone']}
- Sentence style: {template_vars['sentence_style']}
- Minimum chapter length: {template_vars['word_count_target']} words. Check the length as you complete each scene and expand underdeveloped material.
- Point of view: {template_vars['pov_constraint']}
- Tense: {template_vars['tense']}
- Expressions to avoid: {template_vars['forbidden_phrases']}
- Scene separator: {template_vars['scene_break_style']}""",
        )

        user_default = f"""Write Chapter {template_vars['chapter_number']} from the following plan.

Write at least {template_vars['word_count_target']} words in total. Develop all {template_vars['scene_count']} scenes, with at least {template_vars['per_scene_min']} words per scene. Check the length after drafting and expand any underdeveloped material before returning the chapter.

{template_vars['context']}

Chapter plan:
- Title: {template_vars['chapter_title']}
- Goal: {template_vars['goal']}
- Central conflict: {template_vars['conflict']}
- New information: {template_vars['information_increment']}
- Ending hook: {template_vars['ending_hook']}

Scenes:
{template_vars['scenes_formatted']}

Emotional curve:
{template_vars['emotional_curve_formatted']}

Characters:
{template_vars['characters_involved']}

1. Follow the planned scene order and emotional curve.
2. Fully develop each scene with setting details (at least 100 words), action and dialogue (at least 200), interiority (at least 100), and plot progression (at least 100).
3. Give each character dialogue that fits their personality and voice.
4. Convey emotion through concrete actions, expressions, and details of the surroundings.
5. Build to the planned ending hook: {template_vars['ending_hook']}
6. Use Markdown and separate scenes with ***.
7. Avoid formulaic expressions such as "in summary," "it is worth noting," and "in the process of."
8. Verify that the full chapter meets the {template_vars['word_count_target']}-word minimum. Expand descriptions, dialogue, and interiority as necessary."""

        if revision_feedback:
            user_default += f"\n\nRevision feedback:\n{revision_feedback}"

        system, user = self.render_prompts(
            "generate_chapter",
            system_default=system_default,
            user_default=user_default,
            **template_vars,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ChapterContentOutput,
            temperature_override=0.9,
            max_tokens_override=16384,
        )

        # Measure the chapter before deciding whether to expand it.
        word_count = count_words(result.content)

        # ── Auto-expand if chapter is too short ──
        target = chapter_plan.word_count_target
        if word_count < target * 0.85:
            logger.info(f"Chapter {chapter_num} first pass only {word_count} words (< {target}), expanding...")
            try:
                expansion_prompt = _build_expansion_prompt(
                    content=result.content,
                    current_count=word_count,
                    target_count=target,
                    chapter_num=chapter_num,
                    chapter_title=chapter_title,
                )
                expand_result = await self.generate_structured(
                    system_prompt=system,
                    user_prompt=expansion_prompt,
                    response_model=ChapterContentOutput,
                    temperature_override=0.8,
                    max_tokens_override=16384,
                )
                expand_count = count_words(expand_result.content)
                if expand_count > word_count:
                    delta = expand_count - word_count
                    result = expand_result
                    word_count = expand_count
                    logger.info(f"Chapter {chapter_num} expanded: {word_count} words (+{delta})")
                else:
                    logger.warning(
                        f"Expansion didn't increase length ({expand_count} <= {word_count}), keeping first pass"
                    )
            except Exception as e:
                logger.warning(f"Expansion failed ({e}), keeping first pass: {word_count} words")

        draft = ChapterDraft(
            chapter_number=chapter_num,
            title=result.title or chapter_title,
            content=result.content,
            word_count=word_count,
            author_notes=result.author_notes,
        )

        logger.info(f"Chapter {chapter_num} drafted: {word_count} words")
        return draft

    async def extract_facts_and_changes(
        self,
        draft: ChapterDraft,
        bible: NovelBible,
        characters: CharacterRegistry,
        memory: MemoryState | None = None,
    ) -> ChapterDraft:
        """Extract new facts and character state changes from the chapter draft.

        Also checks for contradictions with existing facts in long-term memory.
        """
        logger.info(f"Extracting facts from chapter {draft.chapter_number}...")

        system = self.build_system_prompt(
            role="story fact extractor",
            expertise="Extract newly established world facts, changes in character state, and changes in relationships. "
            "Distinguish new facts from established ones and identify contradictions.",
        )

        # Build character ID mapping
        char_names = {c.name: cid for cid, c in characters.characters.items()}

        # ── Gather existing relevant facts for contradiction detection ──
        existing_facts_text = ""
        if memory and memory.long_term.facts:
            # Filter to facts relevant to characters in this chapter
            relevant_chars = set(char_names.keys())
            relevant_facts = []
            for fact in memory.long_term.facts.values():
                desc = fact.description
                if any(c in desc for c in relevant_chars):
                    relevant_facts.append(fact)
            if relevant_facts:
                existing_facts_text = "\n".join(
                    f"- [{f.category}] {f.description} (Certainty: {f.certainty})"
                    for f in relevant_facts[:30]
                )

        chapter_text = draft.content[:8000] if len(draft.content) > 8000 else draft.content
        truncation_note = "... (chapter truncated)" if len(draft.content) > 8000 else ""

        user = f"""Extract new facts and character state changes from this chapter.

Chapter text:
{chapter_text}{truncation_note}

Known characters: {char_names}

Established facts to check against:
{existing_facts_text or "None (first chapter)"}

### 1. New facts (new_facts)
Use the categories character, world, plot, relationship, and item.
For each fact, provide its unique id, category, description, and certainty. Use 1.0 for confirmed facts, 0.5 for a character's subjective belief, and 0.0 for rumors or potentially false claims.

### 2. Character state changes (state_changes)
Provide character_id, attribute (such as physical.location, emotional.mood, or social.status), old_value, new_value, and reason.

### 3. Contradictions (contradictions)
Flag conflicts between facts established here and earlier facts. For example, a character established to have lost the use of one hand should not wield a sword with both hands without an explanation. If there are no contradictions, return an empty list."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=FactExtractionOutput,
            temperature_override=0.3,
            max_tokens_override=2048,
        )

        draft.new_facts = result.new_facts
        draft.character_state_changes = result.state_changes

        if result.contradictions:
            logger.warning(
                f"Chapter {draft.chapter_number}: {len(result.contradictions)} fact contradictions detected!"
            )
            for c in result.contradictions:
                logger.warning(f"  Contradiction: {c}")

        logger.info(
            f"Extracted {len(draft.new_facts)} facts, {len(draft.character_state_changes)} state changes, "
            f"{len(result.contradictions)} contradictions"
        )
        return draft

    # ================================================================
    # Helpers
    # ================================================================

    def _filter_relevant_facts(
        self,
        chapter_plan: ChapterPlan,
        facts: dict[str, Fact],
        max_facts: int = 20,
    ) -> list[Fact]:
        """Filter long-term facts to only those relevant to the current chapter.

        Relevance is determined by keyword overlap between fact text and the
        chapter's characters, settings, and goal.
        """
        if not facts:
            return []

        # Build keyword set from the chapter plan
        keywords: set[str] = set()
        for char_name in chapter_plan.characters_involved:
            keywords.add(char_name)
        for scene in chapter_plan.scenes:
            keywords.add(scene.setting)
            for c in scene.characters_present:
                keywords.add(c)

        # Also include chapter goal and conflict words
        goal_words = set(chapter_plan.goal.replace("，", ",").replace("、", ",").split(","))
        conflict_words = set(chapter_plan.conflict.replace("，", ",").replace("、", ",").split(","))
        keywords.update(w.strip() for w in goal_words | conflict_words if len(w.strip()) >= 2)

        # Score each fact by keyword overlap
        scored: list[tuple[int, Fact]] = []
        for fact in facts.values():
            desc = fact.description + fact.category
            score = sum(1 for kw in keywords if kw and kw in desc)
            if score > 0:
                scored.append((score, fact))

        # Return top-N by relevance score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:max_facts]]

    def _build_full_context(
        self,
        chapter_plan: ChapterPlan,
        config: ProjectConfig,
        bible: NovelBible,
        characters: CharacterRegistry,
        outline: MasterOutline,
        memory: MemoryState | None = None,
        rag_context: str = "",
    ) -> str:
        """Build the comprehensive context block for the writer."""
        ctx = self.build_context_block(
            project_config=config.model_dump(),
            bible=bible.model_dump(),
            characters={cid: c.model_dump() for cid, c in characters.characters.items()}
            if hasattr(characters, "characters")
            else {},
            outline=outline.model_dump(),
            memory=memory.model_dump() if memory else None,
        )

        # ── Inject relevant historical facts from long-term memory ──
        if memory and memory.long_term.facts:
            relevant = self._filter_relevant_facts(
                chapter_plan=chapter_plan,
                facts=memory.long_term.facts,
                max_facts=20,
            )
            if relevant:
                ctx += "\n=== Relevant Established Facts ===\n"
                ctx += "Keep this chapter consistent with the following facts from earlier chapters.\n"
                for fact in relevant:
                    ctx += f"- [{fact.category}] {fact.description} (Certainty: {fact.certainty})\n"

        # ── Inject RAG-retrieved semantic context ──
        if rag_context:
            ctx += "\n=== Semantic Search Context ===\n"
            ctx += rag_context
            ctx += "\n"

        # Add specific scene breakdown
        ctx += "\n=== Detailed Scene Plan ===\n"
        for i, scene in enumerate(chapter_plan.scenes, 1):
            ctx += f"Scene {i}: {scene.setting}\n"
            ctx += f"  POV: {scene.pov}\n"
            ctx += f"  Present: {', '.join(scene.characters_present)}\n"
            ctx += f"  Goal: {scene.goal}\n"
            ctx += f"  Conflict: {scene.conflict}\n"
            ctx += f"  Outcome: {scene.outcome}\n\n"

        return ctx

    def _format_scenes(self, scenes: list[Scene]) -> str:
        """Format scene list for prompt."""
        if not scenes:
            return "(No scenes planned)"
        lines = []
        for s in scenes:
            lines.append(f"Scene {s.number}: [{s.setting}] POV={s.pov}")
            lines.append(f"  Characters: {', '.join(s.characters_present)}")
            lines.append(f"  Goal: {s.goal}")
            lines.append(f"  Conflict: {s.conflict}")
            lines.append(f"  Outcome: {s.outcome}")
        return "\n".join(lines)

    def _format_emotional_curve(self, beats: list[EmotionalBeat]) -> str:
        """Format emotional curve for prompt."""
        if not beats:
            return "(No emotional beats planned)"
        lines = []
        for b in sorted(beats, key=lambda x: x.position):
            lines.append(f"  {b.position:.0%}: {b.emotion} (intensity: {b.intensity:.0%})")
        return "\n".join(lines)
