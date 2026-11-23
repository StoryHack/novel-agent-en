"""Architect Agent — responsible for world building and novel bible construction."""

import json
import logging
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator

from ..models.bible import (
    CoreConflict,
    Faction,
    StyleContract,
    Theme,
    WorldBuilding,
)
from ..models.project import ProjectConfig
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


def _normalize_str_list(value: Any) -> list[str]:
    """Normalise a field that should be list[str] but may arrive as a string."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return [stripped] if stripped else []
    return [str(value)]


def _normalize_optional_str(value: Any) -> str | None:
    """Normalise a field that should be Optional[str] but may arrive as dict/list."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class WorldBuildingOutput(BaseModel):
    """LLM output schema for world building."""

    name: str = Field(..., description="World name", validation_alias=AliasChoices("name", "世界名称"))
    world_type: str = Field(..., description="World type", validation_alias=AliasChoices("world_type", "世界类型"))
    geography: str = Field(default="", description="Geography", validation_alias=AliasChoices("geography", "地理环境"))
    history: str = Field(
        default="",
        description="Key historical events",
        validation_alias=AliasChoices("history", "关键历史"),
    )
    culture: str = Field(default="", description="Cultural practices", validation_alias=AliasChoices("culture", "文化习俗"))
    technology_level: str = Field(
        default="",
        description="Technology/magic level",
        validation_alias=AliasChoices("technology_level", "科技/魔法水平"),
    )
    magic_system: str | None = Field(
        default=None,
        description="Magic/power systems",
        validation_alias=AliasChoices("magic_system", "魔法/力量体系"),
    )
    power_progression: str | None = Field(
        default=None,
        description="Power progression",
        validation_alias=AliasChoices("power_progression", "力量进阶体系"),
    )
    special_rules: list[str] = Field(
        default_factory=list,
        description="Special World Rules",
        validation_alias=AliasChoices("special_rules", "特殊世界规则"),
    )

    @field_validator("special_rules", mode="before")
    @classmethod
    def coerce_special_rules(cls, v: Any) -> list[str]:
        return _normalize_str_list(v)

    @field_validator("magic_system", "power_progression", mode="before")
    @classmethod
    def coerce_optional_str(cls, v: Any) -> str | None:
        return _normalize_optional_str(v)


class FactionsOutput(BaseModel):
    """LLM output schema for faction design."""

    factions: list[Faction] = Field(default_factory=list)


class StyleContractOutput(BaseModel):
    """LLM output schema for style contract."""

    tone: str = Field(default="", description="Tone", validation_alias=AliasChoices("tone", "语调"))
    pacing_preference: str = Field(
        default="medium",
        description="Preferred pacing",
        validation_alias=AliasChoices("pacing_preference", "节奏偏好"),
    )
    sentence_style: str = Field(
        default="varied",
        description="Sentence style",
        validation_alias=AliasChoices("sentence_style", "句式风格"),
    )
    dialogue_ratio: float = Field(
        default=0.35,
        description="Percentage of dialogue",
        validation_alias=AliasChoices("dialogue_ratio", "对话比例"),
    )
    description_ratio: float = Field(
        default=0.30,
        description="Proportion of description",
        validation_alias=AliasChoices("description_ratio", "描写比例"),
    )
    narrative_distance: str = Field(
        default="close",
        description="Narrative distance",
        validation_alias=AliasChoices("narrative_distance", "叙事距离"),
    )
    forbidden_phrases: list[str] = Field(
        default_factory=list,
        description="Expressions to avoid",
        validation_alias=AliasChoices("forbidden_phrases", "禁用表达"),
    )
    preferred_techniques: list[str] = Field(
        default_factory=list,
        description="Recommended techniques",
        validation_alias=AliasChoices("preferred_techniques", "推荐技法"),
    )


class ThemesOutput(BaseModel):
    """LLM output schema for themes."""

    themes: list[Theme] = Field(default_factory=list)


class ConflictsOutput(BaseModel):
    """LLM output schema for core conflicts."""

    conflicts: list[CoreConflict] = Field(default_factory=list)


class PleasurePointOutput(BaseModel):
    """LLM output schema for pleasure point design."""

    pleasure_point_model: str = Field(
        default="",
        description="Payoff Model Description",
        validation_alias=AliasChoices("pleasure_point_model", "爽点模型描述"),
    )
    narrative_constraints: list[str] = Field(
        default_factory=list,
        description="Narrative constraints",
        validation_alias=AliasChoices("narrative_constraints", "叙事约束"),
    )


# ============================================================
# Agent
# ============================================================


class ArchitectAgent(BaseAgent):
    """Designs the world, factions, style contract, themes, and conflicts.

    This agent builds the foundational "Novel Bible" that all other agents
    reference to maintain consistency.
    """

    agent_type = "architect"

    # ================================================================
    # World Building
    # ================================================================

    async def build_world(self, config: ProjectConfig) -> WorldBuilding:
        """Design the story world based on project configuration."""
        system_default = self.build_system_prompt(
            role="worldbuilding architect",
            expertise="Design expansive, internally consistent fictional worlds. Develop their geography, history, culture, and power systems in support of the story's themes and payoffs.",
        )
        user_default = f"""Build a coherent fictional world for this novel concept.

Inspiration:
{config.inspiration}

Genre: {', '.join(config.genre)}
Target readers: {config.target_readers}
Length: {config.target_length.value} (about {config.target_word_count} words)
Tone: {config.tone}

Design the following:
1. World name and type.
2. Geography, including major locations and climate.
3. Key historical events that shaped the world.
4. Cultural practices such as social norms, taboos, and holidays.
5. Level of technology or magic.
6. Any magic or power system, including its name, rules, and progression.
7. Special rules that distinguish this setting from the real world.

Use details that serve the story and appeal to {config.target_readers}. Leave room to develop the world during drafting."""

        if config.taboo_content:
            user_default += f"\n\nContent to avoid: {', '.join(config.taboo_content)}"

        system, user = self.render_prompts(
            "build_world",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            target_readers=config.target_readers,
            target_length=config.target_length.value,
            target_word_count=config.target_word_count,
            tone=config.tone,
            taboo_content=", ".join(config.taboo_content) if config.taboo_content else "",
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=WorldBuildingOutput,
            temperature_override=0.8,
        )

        world = WorldBuilding(
            name=result.name,
            world_type=result.world_type,
            geography=result.geography,
            history=result.history,
            culture=result.culture,
            technology_level=result.technology_level,
            magic_system=result.magic_system,
            power_progression=result.power_progression,
            special_rules=result.special_rules,
        )
        logger.info(f"World built: {world.name} ({world.world_type})")
        return world

    # ================================================================
    # Faction Design
    # ================================================================

    async def design_factions(self, config: ProjectConfig, world: WorldBuilding) -> list[Faction]:
        """Design factions and organizations in the world."""
        world_summary = json.dumps(world.model_dump(), ensure_ascii=False, indent=2)

        system_default = self.build_system_prompt(
            role="faction designer",
            expertise="Design layered factions with clear goals, internal structures, resources, and relationships to other factions.",
        )
        user_default = f"""Design 3–6 major factions or organizations for this setting.

World:
{world_summary}

Genre: {', '.join(config.genre)}
Target readers: {config.target_readers}

1. Give each faction a name, type (sect, kingdom, guild, family, etc.), goals, hierarchy, resources, and ideology.
2. Define alliances, rivalries, and neutral relationships.
3. Make the factions relevant to the central conflicts.
4. Include at least one faction the protagonist belongs to or opposes.

Use a unique ID of the form faction_xxx for each faction."""

        system, user = self.render_prompts(
            "design_factions",
            system_default=system_default,
            user_default=user_default,
            world_summary=world_summary,
            genre=", ".join(config.genre),
            target_readers=config.target_readers,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=FactionsOutput,
            temperature_override=0.7,
        )
        logger.info(f"Designed {len(result.factions)} factions")
        return result.factions

    # ================================================================
    # Style Contract
    # ================================================================

    async def create_style_contract(self, config: ProjectConfig) -> StyleContract:
        """Define the writing style contract for the novel."""
        system_default = self.build_system_prompt(
            role="fiction style consultant",
            expertise="Define a consistent style contract suited to the genre and intended audience.",
        )
        user_default = f"""Define a style contract for this novel.

Inspiration: {config.inspiration}
Genre: {', '.join(config.genre)}
Target readers: {config.target_readers}
Tone: {config.tone}
Style reference: {config.style_reference or 'No specific reference'}

Specify:
1. Overall tone (dark, light, gritty, whimsical, etc.).
2. Preferred pacing (fast, medium, or slow).
3. Sentence style (simple, ornate, varied, or minimalist).
4. Approximate dialogue proportion (0.0–1.0).
5. Approximate description proportion (0.0–1.0).
6. Narrative distance (close, distant, or omniscient).
7. Clichés and other expressions to avoid.
8. Recommended writing techniques.

Choose a style sustainable for a {config.target_length.value} novel."""

        system, user = self.render_prompts(
            "create_style_contract",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            target_readers=config.target_readers,
            tone=config.tone,
            style_reference=config.style_reference or "No specific reference",
            target_length=config.target_length.value,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=StyleContractOutput,
            temperature_override=0.6,
        )
        style = StyleContract(
            tone=result.tone,
            pacing_preference=result.pacing_preference,
            sentence_style=result.sentence_style,
            dialogue_ratio=result.dialogue_ratio,
            description_ratio=result.description_ratio,
            narrative_distance=result.narrative_distance,
            forbidden_phrases=result.forbidden_phrases,
            preferred_techniques=result.preferred_techniques,
        )
        logger.info(f"Style contract created: tone={style.tone}, pacing={style.pacing_preference}")
        return style

    # ================================================================
    # Themes & Conflicts
    # ================================================================

    async def generate_themes(self, config: ProjectConfig, world: WorldBuilding) -> list[Theme]:
        """Generate thematic elements for the novel."""
        system_default = self.build_system_prompt(
            role="story theme designer",
            expertise="Identify the novel's core themes and express them through its characters, plot, and world.",
        )
        user_default = f"""Develop 3–5 core themes for this novel.

Inspiration: {config.inspiration}
Genre: {', '.join(config.genre)}
World: {world.name} – {world.world_type}

Give each theme a name (such as redemption, sacrifice, or the cost of power), explain its meaning in this story, and describe how it emerges through character, plot, and setting."""

        system, user = self.render_prompts(
            "generate_themes",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            world_name=world.name,
            world_type=world.world_type,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ThemesOutput,
            temperature_override=0.7,
        )
        logger.info(f"Generated {len(result.themes)} themes")
        return result.themes

    async def define_conflicts(
        self,
        config: ProjectConfig,
        world: WorldBuilding,
        factions: list[Faction],
    ) -> list[CoreConflict]:
        """Define core conflicts driving the narrative."""
        factions_summary = json.dumps([f.model_dump() for f in factions], ensure_ascii=False, indent=2)

        system_default = self.build_system_prompt(
            role="story conflict designer",
            expertise="Design the central conflicts that drive the plot. Use interpersonal, social, internal, and environmental conflicts for their distinct narrative functions.",
        )
        user_default = f"""Design 3–5 central conflicts based on the following information.

Inspiration: {config.inspiration}
Genre: {', '.join(config.genre)}
World: {world.name}
Factions: {factions_summary}

For each conflict, provide:
- Type (person_vs_person, person_vs_society, person_vs_self, person_vs_nature, or person_vs_technology).
- Description.
- Characters or factions involved.
- Stakes if the conflict remains unresolved.

Include at least one internal conflict (person_vs_self) and one conflict between factions. Connect the conflicts and distinguish the central ones from the supporting ones."""

        system, user = self.render_prompts(
            "define_conflicts",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            world_name=world.name,
            factions_summary=factions_summary,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ConflictsOutput,
            temperature_override=0.7,
        )
        logger.info(f"Defined {len(result.conflicts)} core conflicts")
        return result.conflicts

    # ================================================================
    # Pleasure Points & Constraints
    # ================================================================

    async def design_pleasure_points(
        self,
        config: ProjectConfig,
        world: WorldBuilding,
        themes: list[Theme],
    ) -> tuple[str, list[str]]:
        """Design the pleasure point model and narrative constraints."""
        system_default = self.build_system_prompt(
            role="narrative payoff designer",
            expertise="Design satisfying payoffs and pace them to sustain different readers' interest across a web novel.",
        )
        user_default = f"""Design a payoff model and narrative constraints for this novel.

Inspiration: {config.inspiration}
Genre: {', '.join(config.genre)}
Target readers: {config.target_readers}
World type: {world.world_type}"""

        system, user = self.render_prompts(
            "design_pleasure_points",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            target_readers=config.target_readers,
            world_type=world.world_type,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=PleasurePointOutput,
            temperature_override=0.7,
        )
        return result.pleasure_point_model, result.narrative_constraints
