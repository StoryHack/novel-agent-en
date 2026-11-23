"""Plot Planner Agent — master outline, volume structure, chapter planning."""

import logging
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator

from ..models.bible import NovelBible
from ..models.characters import CharacterRegistry
from ..models.memory import MemoryState
from ..models.outline import (
    ChapterPlan,
    EmotionalBeat,
    Hook,
    MasterOutline,
    PlotArc,
    Scene,
    TurningPoint,
    Volume,
)
from ..models.project import ProjectConfig
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


class MasterOutlineOutput(BaseModel):
    """LLM output for master outline."""

    title: str = Field(default="", description="Title of the novel", validation_alias=AliasChoices("title", "小说标题"))
    subtitle: str | None = Field(
        default=None,
        description="Subheading",
        validation_alias=AliasChoices("subtitle", "副标题"),
    )
    logline: str = Field(
        default="",
        description="A brief description",
        validation_alias=AliasChoices("logline", "一句话简介"),
    )
    main_plot: list[PlotArc] = Field(default_factory=list)
    subplots: list[PlotArc] = Field(default_factory=list)
    volumes: list[Volume] = Field(default_factory=list)
    major_turning_points: list[TurningPoint] = Field(default_factory=list)
    chapter_count: int = Field(default=0)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        """Coerce Chinese LLM quirks: string turning points → TurningPoint."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "major_turning_points" in d:
            tps = d["major_turning_points"]
            if isinstance(tps, list):
                coerced = []
                for i, tp in enumerate(tps):
                    if isinstance(tp, str):
                        coerced.append({"description": tp, "chapter": i + 1})
                    elif isinstance(tp, dict):
                        coerced.append(tp)
                    else:
                        coerced.append(tp)
                d["major_turning_points"] = coerced
        # Also coerce string plot arcs
        for field in ("main_plot", "subplots"):
            if field in d and isinstance(d[field], list):
                d[field] = [{"description": x} if isinstance(x, str) else x for x in d[field]]
        # "Vol. X: Title..."
        if "volumes" in d and isinstance(d["volumes"], list):
            coerced_vols = []
            for i, v in enumerate(d["volumes"]):
                if isinstance(v, str):
                    # Parse, "Vol. X: Title" or "Vol. X" or just "Title."
                    import re as _re

                    vol_num = i + 1
                    vol_title = v
                    # Try to extract volume number from string
                    m = _re.match(
                        r"(?:Vol(?:ume)?\.?\s+(\d+)|第\s*([\d一二三四五六七八九十]+)\s*[卷部篇])\s*[：:\s]\s*(.+)",
                        v,
                        _re.IGNORECASE,
                    )
                    if m:
                        # Convert Chinese number if needed (simplified: use index-based fallback)
                        try:
                            vol_num = int(m.group(1) or m.group(2))
                        except ValueError:
                            vol_num = i + 1
                        vol_title = m.group(3).strip()
                    else:
                        # Fallback: use the whole string as title, auto-number
                        vol_title = v
                    coerced_vols.append(
                        {
                            "title": vol_title,
                            "number": vol_num,
                            "start_chapter": (i * 10) + 1,
                            "end_chapter": (i + 1) * 10,
                        }
                    )
                elif isinstance(v, dict):
                    coerced_vols.append(v)
                else:
                    coerced_vols.append(v)
            d["volumes"] = coerced_vols
        return d


def _parse_emotional_beat_string(raw: str, index: int = 0) -> dict:
    """Parse a plain-text emotional beat returned by a model.

    Handles formats such as "Tension, intensity 0.9", "Anger 0.7",
    "Excitement: 0.95", and "Dread (intensity 0.9)".
    """
    import re

    s = raw.strip()

    # Try an intensity in parentheses.
    m = re.search(r"[（(]\s*(?:intensity|强度)\s*:?\s*([\d.]+)\s*[）)]", s, re.IGNORECASE)
    if m:
        emotion = s[: m.start()].strip()
        intensity = float(m.group(1))
        if intensity > 1.0:
            intensity /= 10.0
        return {"position": index * 0.25, "emotion": emotion, "intensity": intensity}

    # Try a comma followed by an intensity label.
    m = re.search(r"[，,]\s*(?:intensity|强度)\s*:?\s*([\d.]+)", s, re.IGNORECASE)
    if m:
        emotion = s[: m.start()].strip()
        intensity = float(m.group(1))
        if intensity > 1.0:
            intensity /= 10.0
        return {"position": index * 0.25, "emotion": emotion, "intensity": intensity}

    # Try "emotion followed by number"
    m = re.search(r"[：:]\s*([\d.]+)$", s)
    if m:
        emotion = s[: m.start()].strip()
        intensity = float(m.group(1))
        if intensity > 1.0:
            intensity /= 10.0
        return {"position": index * 0.25, "emotion": emotion, "intensity": intensity}

    m = re.search(r"\s+([\d.]+)$", s)
    if m:
        emotion = s[: m.start()].strip()
        intensity = float(m.group(1))
        if intensity > 1.0:
            intensity /= 10.0
        return {"position": index * 0.25, "emotion": emotion, "intensity": intensity}

    # Fallback: treat entire string as emotion name
    return {"position": index * 0.25, "emotion": s, "intensity": 0.5}


def _parse_emotional_curve_string(raw: str) -> list[dict]:
    """Parse a comma/line-separated emotional curve string into a list of dicts.

    Accepts plain-text beats separated by commas or newlines.
    """
    import re

    # Split on Chinese or English commas, or on newlines.
    # Strategy: split on "，" or "," and parse each fragment
    parts = re.split(r"[，,]\s*", raw.strip())
    if len(parts) <= 1:
        parts = re.split(r"\n+", raw.strip())

    result = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        beat = _parse_emotional_beat_string(part, i)
        result.append(beat)
    return result


class ChapterPlanOutput(BaseModel):
    """LLM output for chapter plan."""

    chapter_number: int = Field(default=0)
    title: str = Field(default="")
    goal: str = Field(default="")
    scenes: list[Scene] = Field(default_factory=list)
    pov_character: str = Field(default="")
    conflict: str = Field(default="")
    hooks: list[Hook] = Field(default_factory=list)
    characters_involved: list[str] = Field(default_factory=list)
    information_increment: str = Field(default="")
    reveals: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    emotional_curve: list[EmotionalBeat] = Field(default_factory=list)
    ending_hook: str = Field(default="")
    word_count_target: int = Field(default=4000)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        """Pre-normalize nested fields before model validation."""
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # ── emotional_curve: coerce string items & clamp intensities ──
        if "emotional_curve" in d:
            curve = d["emotional_curve"]
            if isinstance(curve, list):
                coerced = []
                for i, beat in enumerate(curve):
                    if isinstance(beat, str):
                        beat = _parse_emotional_beat_string(beat, i)
                    if isinstance(beat, dict):
                        # If emotion field contains parenthesized intensity, extract it
                        if "emotion" in beat and isinstance(beat["emotion"], str):
                            raw_emotion = beat["emotion"]
                            parsed = _parse_emotional_beat_string(raw_emotion, i)
                            # Use parsed emotion if it's cleaner (shorter, no parens)
                            if "（" not in parsed["emotion"] and "(" not in parsed["emotion"]:
                                beat["emotion"] = parsed["emotion"]
                            else:
                                # Use the parsed emotion when it has a recognized intensity.
                                import re

                                cleaned = re.sub(r"^[\d.]+\s+", "", raw_emotion, count=1)
                                if cleaned != raw_emotion:
                                    beat["emotion"] = cleaned
                            # Use parsed intensity if current is missing or default
                            if "intensity" not in beat or beat.get("intensity") in (0, 0.5):
                                beat["intensity"] = parsed["intensity"]
                        # Clamp intensity: model often uses 0–10 scale
                        if "intensity" in beat:
                            v = beat["intensity"]
                            if isinstance(v, (int, float)) and v > 1.0:
                                beat["intensity"] = v / 10.0
                    coerced.append(beat)
                d["emotional_curve"] = coerced
            elif isinstance(curve, str):
                # Single string — try to parse as comma-separated list
                d["emotional_curve"] = _parse_emotional_curve_string(curve)

        return d


# ============================================================
# Agent
# ============================================================


class PlotPlannerAgent(BaseAgent):
    """Plans the complete story structure — from master outline to individual chapters."""

    agent_type = "plot_planner"

    # ================================================================
    # Master Outline
    # ================================================================

    async def create_master_outline(
        self,
        config: ProjectConfig,
        bible: NovelBible,
        characters: CharacterRegistry,
    ) -> MasterOutline:
        """Create the complete master outline with volumes and turning points."""
        logger.info("Creating master outline...")

        system = self.build_system_prompt(
            role="story architect",
            expertise="Plan main plots, subplots, turning points, and chapter pacing for an engaging story.",
        )

        # Build character summary
        char_lines = []
        for cid, char in characters.characters.items():
            char_lines.append(f"- [{cid}] {char.name} ({char.role}): {char.motivation[:80]}")
        char_summary = "\n".join(char_lines)

        world = bible.world
        conflicts = bible.core_conflicts
        themes = bible.themes

        conflict_lines = "\n".join(f"- [{c.id}] {c.description}" for c in conflicts)
        theme_lines = ", ".join(t.name for t in themes)

        # Estimate chapter count
        avg_words_per_chapter = 4000
        total_chapters = max(10, config.target_word_count // avg_words_per_chapter)

        user = f"""Plan the full story for this novel.

Inspiration: {config.inspiration}
Genre: {", ".join(config.genre)}
Target readers: {config.target_readers}
Length: {config.target_word_count} words (about {total_chapters} chapters of {avg_words_per_chapter} words)
Language: {config.language}

World: {world.name} ({world.world_type})
Themes: {theme_lines}
Central conflicts:
{conflict_lines}

Characters:
{char_summary}

### 1. Premise
Give the novel a title and a one-sentence logline.

### 2. Main plot (main_plot)
Plan 3–5 major arcs, each with a goal and key beats.

### 3. Subplots (subplots)
Plan 2–3 secondary arcs. Use subplot or b_plot for arc_type.

### 4. Volume structure (volumes)
Divide the story into {max(2, total_chapters // 30)}–{max(3, total_chapters // 20)} volumes. Give each a title, logline, chapter range, main events, and emotional arc.

### 5. Key turning points (major_turning_points)
Include at least one turning point of the following types: inciting_incident, first_plot_point, midpoint, all_is_lost, climax, or denouement.

Let each chapter advance the story with new information. Place major payoffs in key chapters, connect main and secondary plots, and leave room for character growth."""

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=MasterOutlineOutput,
            temperature_override=0.7,
            max_tokens_override=8192,
        )

        outline = MasterOutline(
            title=result.title or "",
            subtitle=result.subtitle,
            logline=result.logline,
            main_plot=result.main_plot,
            subplots=result.subplots,
            volumes=result.volumes,
            major_turning_points=result.major_turning_points,
            chapter_count=result.chapter_count or total_chapters,
        )

        logger.info(
            f"Master outline created: {outline.title}, {len(outline.volumes)} volumes, {outline.chapter_count} chapters"
        )
        return outline

    # ================================================================
    # Chapter Planning
    # ================================================================

    async def plan_chapter(
        self,
        chapter_number: int,
        config: ProjectConfig,
        bible: NovelBible,
        characters: CharacterRegistry,
        outline: MasterOutline,
        memory: MemoryState | None = None,
    ) -> ChapterPlan:
        """Plan a single chapter in detail."""
        logger.info(f"Planning chapter {chapter_number}...")

        # Determine which volume this chapter belongs to
        current_volume = None
        for vol in outline.volumes:
            if vol.start_chapter <= chapter_number <= vol.end_chapter:
                current_volume = vol
                break

        # Find turning points in this chapter
        chapter_tps = [tp for tp in outline.major_turning_points if tp.chapter == chapter_number]

        # Build context
        outline_json = outline.model_dump_json(indent=2)

        prev_chapter_summary = ""
        if memory and memory.short_term:
            prev_chapter_summary = memory.short_term.current_chapter_summary

        vol_title = current_volume.title if current_volume else "Unallocated"
        vol_logline = current_volume.logline if current_volume else ""
        tps_text = str([(tp.turning_type, tp.description) for tp in chapter_tps]) if chapter_tps else "No specific turning point"
        char_states_text = self._format_character_states(characters, memory)
        length_range = f"{bible.rules.chapter_length_range[0]}-{bible.rules.chapter_length_range[1]}"

        system_default = self.build_system_prompt(
            role="chapter planner",
            expertise="Turn an outline into an actionable scene plan, including settings, characters, and emotional beats. Give each chapter a clear goal, conflict, and hook.",
        )
        user_default = f"""Create a detailed plan for Chapter {chapter_number}.

Outline:
{outline_json}

Current volume: {vol_title} — {vol_logline}
Turning points: {tps_text}
Previous chapter summary: {prev_chapter_summary or 'This is the first chapter'}

Current character states:
{char_states_text}

Design:
1. An engaging chapter title.
2. The chapter's goal, including the plot thread it advances and the outcome it must achieve.
3. Two to five scenes, each with a location, POV character, other characters present, goal, conflict, and outcome.
4. The central conflict.
5. New information the reader learns.
6. Reveals or reversals (reveals).
7. New setups (foreshadowing).
8. Five emotional beats, with emotion and intensity at positions 0.0, 0.25, 0.5, 0.75, and 1.0.
9. An ending hook that makes readers want the next chapter.
10. A target length of {length_range.split('-')[0] if '-' in length_range else '2000'}–{length_range.split('-')[1] if '-' in length_range else '4000'} words.

Link scenes through cause and effect. Vary the emotional intensity, end on suspense, emotion, or a reveal, and match the {config.tone} tone."""

        system, user = self.render_prompts(
            "plan_chapter",
            system_default=system_default,
            user_default=user_default,
            chapter_number=chapter_number,
            outline_json=outline_json,
            vol_title=vol_title,
            vol_logline=vol_logline,
            tps_text=tps_text,
            prev_summary=prev_chapter_summary or "This is the first chapter",
            char_states=char_states_text,
            word_count_target_min=length_range.split("-")[0] if "-" in length_range else "2000",
            word_count_target_max=length_range.split("-")[1] if "-" in length_range else "4000",
            tone=config.tone,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ChapterPlanOutput,
            temperature_override=0.7,
        )

        plan = ChapterPlan(
            chapter_number=chapter_number,
            title=result.title,
            goal=result.goal,
            scenes=result.scenes,
            pov_character=result.pov_character,
            conflict=result.conflict,
            hooks=result.hooks,
            characters_involved=result.characters_involved,
            information_increment=result.information_increment,
            reveals=result.reveals,
            foreshadowing=result.foreshadowing,
            emotional_curve=result.emotional_curve,
            ending_hook=result.ending_hook,
            word_count_target=result.word_count_target or 4000,
            status="planned",
        )

        logger.info(f"Chapter {chapter_number} plan ready: {len(plan.scenes)} scenes")
        return plan

    def _format_character_states(
        self,
        characters: CharacterRegistry,
        memory: MemoryState | None,
    ) -> str:
        """Format current character states for the prompt."""
        lines = []
        for cid, char in characters.characters.items():
            state = char.current_state
            # Override with memory state if available
            if memory and cid in memory.character_states:
                state = memory.character_states[cid]

            # Normalise: CharacterState model → dict, memory state may already be dict
            if not isinstance(state, dict):
                state = state.model_dump()

            lines.append(
                f"- [{cid}] {char.name}: Location: {state.get('physical', {}).get('location', 'Unknown')}, "
                f"Emotion: {state.get('emotional', {}).get('mood', 'Normal')}, "
                f"Arc progress: {state.get('arc_progress', 0.0):.0%}"
            )
        return "\n".join(lines)
