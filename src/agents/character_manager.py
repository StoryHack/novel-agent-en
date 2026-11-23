"""Character Manager Agent — creates and maintains character profiles."""

import logging

from pydantic import BaseModel, Field

from ..models.bible import NovelBible
from ..models.characters import (
    ArcBeat,
    CharacterProfile,
    CharacterRegistry,
    Relationship,
)
from ..models.project import ProjectConfig
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas
# ============================================================


class CharacterProfilesOutput(BaseModel):
    """LLM output schema for character profiles."""

    characters: list[CharacterProfile] = Field(default_factory=list)


class RelationshipMapOutput(BaseModel):
    """LLM output schema for relationship mapping."""

    relationships: dict[str, list[Relationship]] = Field(
        default_factory=dict,
        description="Mapping: character_id -> list of relationships",
    )


class CharacterArcOutput(BaseModel):
    """LLM output schema for character arcs."""

    arcs: dict[str, list[ArcBeat]] = Field(
        default_factory=dict,
        description="Mapping: character_id -> arc beats",
    )


# ============================================================
# Agent
# ============================================================


class CharacterManagerAgent(BaseAgent):
    """Creates and manages character profiles, relationships, and arcs."""

    agent_type = "character_manager"

    async def create_all_characters(
        self,
        config: ProjectConfig,
        bible: NovelBible,
    ) -> CharacterRegistry:
        """Create all major characters for the novel.

        This is a multi-step process:
        1. Generate core character profiles
        2. Build relationships between characters
        3. Design character arcs
        """
        logger.info("Creating characters...")

        # Step 1: Generate profiles
        profiles = await self._generate_profiles(config, bible)

        # Build registry
        registry = CharacterRegistry()
        for profile in profiles:
            registry.characters[profile.id] = profile

        # Step 2: Build relationships
        registry = await self.build_relationships(registry, bible)

        # Step 3: Design arcs (for major characters)
        registry = await self.design_arcs(registry, bible)

        logger.info(f"Created {len(registry.characters)} characters")
        return registry

    async def _generate_profiles(
        self,
        config: ProjectConfig,
        bible: NovelBible,
    ) -> list[CharacterProfile]:
        """Generate core character profiles."""
        # Build context
        world = bible.world
        themes = bible.themes
        conflicts = bible.core_conflicts

        theme_names = ", ".join(t.name for t in themes)
        conflict_descs = "\n".join(f"- {c.description}" for c in conflicts)

        system_default = self.build_system_prompt(
            role="character designer",
            expertise="Create memorable, multidimensional characters. Give each one a distinctive voice, motivation, and flaw. Draw on archetypes such as hero, mentor, ally, herald, trickster, and shadow.",
        )
        user_default = f"""Create a cast for this novel.

Inspiration: {config.inspiration}
Genre: {', '.join(config.genre)}
World: {world.name} ({world.world_type})
Themes: {theme_names}
Central conflicts:
{conflict_descs}

Create 4–6 characters:
1. A protagonist (required).
2. An antagonist or rival (required).
3. A deuteragonist who is the protagonist's ally or companion.
4. An optional mentor or guide.
5. One or two other important supporting characters.

For each character, provide:
- id: Unique ID, such as char_mc, char_ant, or char_ally
- name: Character name
- role: protagonist/antagonist/deuteragonist/supporting/minor
- archetype: hero/mentor/herald/trickster/shadow, etc.
- age: Age
- gender: Gender
- appearance: Distinctive physical details
- personality: Strengths, weaknesses, and contradictions
- motivation: What the character truly wants
- flaw: A trait that holds them back
- backstory: One or two paragraphs explaining who they have become
- abilities: List of abilities

Give the protagonist a relatable motivation and a clear flaw. Give the antagonist credible motives. Create potential conflicts and complementary relationships. Give each character a distinct voice and manner that serves the story's themes and conflicts."""

        if config.taboo_content:
            user_default += f"\n\nContent to avoid: {', '.join(config.taboo_content)}"

        system, user = self.render_prompts(
            "generate_profiles",
            system_default=system_default,
            user_default=user_default,
            inspiration=config.inspiration,
            genre=", ".join(config.genre),
            world_name=world.name,
            world_type=world.world_type,
            theme_names=theme_names,
            conflict_descs=conflict_descs,
            taboo_content=", ".join(config.taboo_content) if config.taboo_content else "",
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=CharacterProfilesOutput,
            temperature_override=0.7,
            max_tokens_override=8192,
        )
        return result.characters

    async def build_relationships(
        self,
        registry: CharacterRegistry,
        bible: NovelBible,
    ) -> CharacterRegistry:
        """Build relationship network between all characters."""
        char_summaries = []
        for cid, char in registry.characters.items():
            char_summaries.append(f"[{cid}] {char.name} ({char.role}) - {char.personality[:100]}")
        char_list = "\n".join(char_summaries)

        system_default = self.build_system_prompt(
            role="character relationship designer",
            expertise="Build believable relationships with tension and room for change. Consider power dynamics, emotional depth, trust, and how relationships develop over time.",
        )
        user_default = f"""Design relationships between pairs of characters.

Characters:
{char_list}

Themes: {', '.join(t.name for t in bible.themes)}

For each relationship, provide:
- relationship_type: friend/rival/lover/enemy/family/mentor/subordinate/acquaintance
- trust: 0.0–1.0
- intimacy: 0.0–1.0
- power_balance: 0.0 for deference, 0.5 for equality, 1.0 for dominance
- history: Their shared history in 1–2 sentences
- notes: Additional details

Use relationships to serve the story's conflicts and themes. Give the relationships tension and room to change. Pay special attention to the protagonist and antagonist."""

        system, user = self.render_prompts(
            "build_relationships",
            system_default=system_default,
            user_default=user_default,
            char_list=char_list,
            theme_names=", ".join(t.name for t in bible.themes),
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=RelationshipMapOutput,
            temperature_override=0.6,
        )

        # Apply relationships to characters
        for char_id, relationships in result.relationships.items():
            if char_id in registry.characters:
                registry.characters[char_id].relationships = relationships

        return registry

    async def design_arcs(
        self,
        registry: CharacterRegistry,
        bible: NovelBible,
    ) -> CharacterRegistry:
        """Design character arcs for major characters."""
        major_chars = {
            cid: char
            for cid, char in registry.characters.items()
            if char.role in ("protagonist", "antagonist", "deuteragonist")
        }

        char_descriptions = []
        for cid, char in major_chars.items():
            char_descriptions.append(f"[{cid}] {char.name} - Motivation: {char.motivation} - Flaw: {char.flaw}")
        char_list = "\n".join(char_descriptions)

        system_default = self.build_system_prompt(
            role="character arc designer",
            expertise="Build layered growth, downfall, redemption, or disillusionment arcs with developments that are surprising and believable.",
        )
        user_default = f"""Design arcs for the major characters.

Characters:
{char_list}

Give each character 3–5 ArcBeat entries:
- chapter: Approximate chapter number
- event: What happens
- change: How the character changes as a result
- new_trait: Trait gained or revealed (optional)
- lost_trait: Trait lost or suppressed (optional)

Show gradual growth or decline, with a clear cause for each change. Align major beats with plot turning points."""

        system, user = self.render_prompts(
            "design_arcs",
            system_default=system_default,
            user_default=user_default,
            char_list=char_list,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=CharacterArcOutput,
            temperature_override=0.7,
        )

        for char_id, arc_beats in result.arcs.items():
            if char_id in registry.characters:
                registry.characters[char_id].arc = arc_beats

        return registry
