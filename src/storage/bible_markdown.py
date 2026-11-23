"""Bible Markdown Store — thin-pointer modular bible files.

Inspired by ai-job-search-master's modular profile system:
  01-candidate-profile.md  ← hard facts only
  02-behavioral-profile.md ← soft skills only
  03-writing-style.md      ← tone & voice rules
  ...

Applied to novel writing:
  bible/
  ├── 01-world-building.md    ← World setting (geography, history, rules)
  ├── 02-factions.md          ← Factions & organizations
  ├── 03-writing-style.md     ← Style contract (tone, sentence style, forbidden phrases)
  ├── 04-themes.md            ← Themes & core conflicts
  ├── 05-pleasure-points.md   ← Pleasure point model & narrative constraints
  └── 06-characters.md        ← Character registry (thin reference)

Key principle: NO INFORMATION DUPLICATION across files. Each fact lives in
exactly one file. Agents load only the files they need for their task.
"""

import logging
from datetime import datetime
from pathlib import Path

from ..models.bible import (
    CoreConflict,
    Faction,
    NovelBible,
    StyleContract,
    Theme,
    WorldBuilding,
)
from ..models.characters import CharacterRegistry

logger = logging.getLogger(__name__)

# File name constants
FILE_WORLD = "01-world-building.md"
FILE_FACTIONS = "02-factions.md"
FILE_STYLE = "03-writing-style.md"
FILE_THEMES = "04-themes.md"
FILE_PLEASURE = "05-pleasure-points.md"
FILE_CHARACTERS = "06-characters.md"

ALL_BIBLE_FILES = [
    FILE_WORLD,
    FILE_FACTIONS,
    FILE_STYLE,
    FILE_THEMES,
    FILE_PLEASURE,
    FILE_CHARACTERS,
]


class BibleMarkdownStore:
    """Reads and writes bible components as modular Markdown files.

    Each file is self-contained and can be loaded independently by agents.
    This enables the thin-pointer pattern: agents load only the specific
    files they need, reducing token waste and preventing information drift.

    Usage:
        store = BibleMarkdownStore(project_dir)
        store.save_bible(bible, characters)
        # ... later ...
        world = store.load_world()
        style = store.load_style()
    """

    def __init__(self, project_dir: Path):
        self._bible_dir = project_dir / "bible"
        self._bible_dir.mkdir(parents=True, exist_ok=True)

    # ── Save ──────────────────────────────────────────────────────

    def save_bible(
        self,
        bible: NovelBible,
        characters: CharacterRegistry | None = None,
    ) -> None:
        """Save all bible components as modular Markdown files."""
        self._save_world(bible.world)
        self._save_factions(bible.factions)
        self._save_style(bible.style_contract)
        self._save_themes(bible.themes, bible.core_conflicts)
        self._save_pleasure_points(bible.pleasure_point_model, bible.narrative_constraints)
        if characters:
            self._save_characters(characters)
        logger.info(f"Bible saved to {self._bible_dir} ({len(ALL_BIBLE_FILES)} files)")

    def _save_world(self, world: WorldBuilding) -> None:
        """Save world building as Markdown."""
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: world-building",
            "---",
            "",
            f"# World: {world.name}",
            "",
            f"**World type**: {world.world_type}",
            "",
            "## Geography",
            "",
            world.geography or "(To be completed)",
            "",
            "## Key Historical Events",
            "",
            world.history or "(To be completed)",
            "",
            "## Cultural practices",
            "",
            world.culture or "(To be completed)",
            "",
            f"**Technology or magic level**: {world.technology_level or 'To be decided'}",
            "",
        ]
        if world.magic_system:
            lines.extend(
                [
                    "## Magic or Power System",
                    "",
                    world.magic_system,
                    "",
                ]
            )
        if world.power_progression:
            lines.extend(
                [
                    "## Power Progression",
                    "",
                    world.power_progression,
                    "",
                ]
            )
        if world.special_rules:
            lines.extend(
                [
                    "## Special World Rules",
                    "",
                ]
            )
            for rule in world.special_rules:
                lines.append(f"- {rule}")
            lines.append("")

        self._write(FILE_WORLD, "\n".join(lines))

    def _save_factions(self, factions: list[Faction]) -> None:
        """Save factions as Markdown."""
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: factions",
            "---",
            "",
            f"# Factions and Organizations ({len(factions)})",
            "",
        ]

        for i, f in enumerate(factions, 1):
            lines.extend(
                [
                    f"## {i}. {f.name}",
                    "",
                    f"- **ID**: {f.id}",
                    f"- **Type**: {f.type}",
                    f"- **Goal**: {f.goal}",
                    f"- **Hierarchy**: {f.hierarchy or 'To be decided'}",
                    f"- **Resources**: {f.resources or 'To be decided'}",
                    f"- **Ideology**: {f.ideology or 'To be decided'}",
                    "",
                ]
            )
            if f.description:
                lines.append(f.description)
                lines.append("")

        self._write(FILE_FACTIONS, "\n".join(lines))

    def _save_style(self, style: StyleContract) -> None:
        """Save style contract as Markdown."""
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: writing-style",
            "---",
            "",
            "# Style Contract",
            "",
            "| Parameter | Value |",
            "|------|-----|",
            f"| Tone | {style.tone} |",
            f"| Pacing | {style.pacing_preference} |",
            f"| Sentence Style | {style.sentence_style} |",
            f"| Dialogue | {style.dialogue_ratio:.0%} |",
            f"| Description | {style.description_ratio:.0%} |",
            f"| Narrative Distance | {style.narrative_distance} |",
            "",
        ]

        if style.forbidden_phrases:
            lines.append("## Expressions to Avoid")
            lines.append("")
            for phrase in style.forbidden_phrases:
                lines.append(f"- {phrase}")
            lines.append("")

        if style.preferred_techniques:
            lines.append("## Recommended techniques")
            lines.append("")
            for tech in style.preferred_techniques:
                lines.append(f"- {tech}")
            lines.append("")

        self._write(FILE_STYLE, "\n".join(lines))

    def _save_themes(self, themes: list[Theme], conflicts: list[CoreConflict]) -> None:
        """Save themes and conflicts as Markdown."""
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: themes-and-conflicts",
            "---",
            "",
            "# Themes and Central Conflicts",
            "",
            f"## Themes ({len(themes)})",
            "",
        ]

        for t in themes:
            lines.append(f"### {t.name}")
            lines.append(f"{t.description}")
            if t.expression:
                lines.append(f"\nExpression: {t.expression}")
            lines.append("")

        lines.append(f"## Central Conflicts ({len(conflicts)})")
        lines.append("")

        for c in conflicts:
            lines.append(f"### {c.type}")
            lines.append(f"{c.description}")
            lines.append(f"- Parties: {c.parties_involved}")
            lines.append(f"- Stakes: {c.stakes}")
            lines.append("")

        self._write(FILE_THEMES, "\n".join(lines))

    def _save_pleasure_points(
        self,
        pleasure_model: str,
        constraints: list[str],
    ) -> None:
        """Save pleasure point model as Markdown."""
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: pleasure-points",
            "---",
            "",
            "# Payoff model and narrative constraints",
            "",
            "## Payoff Model",
            "",
            pleasure_model or "(To be completed)",
            "",
        ]

        if constraints:
            lines.append("## Narrative constraints")
            lines.append("")
            for c in constraints:
                lines.append(f"- {c}")
            lines.append("")

        self._write(FILE_PLEASURE, "\n".join(lines))

    def _save_characters(self, characters: CharacterRegistry) -> None:
        """Save character registry as thin-reference Markdown.

        Note: This is a THIN REFERENCE. Full character details live in
        the character YAML files. This file provides quick lookup for
        agents that need character names + roles without the full profile.
        """
        lines = [
            "---",
            'framework_version: "1.0.0"',
            f'generated_at: "{datetime.now().isoformat()}"',
            "category: characters",
            "---",
            "",
            f"# Characters ({len(characters.characters)})",
            "",
            "> Full character profiles are in `characters/`.",
            "",
            "| ID | Name | Role | Personality | Motivation |",
            "|----|------|------|----------|------|",
        ]

        for cid, char in characters.characters.items():
            personality_brief = (char.personality or "")[:40]
            motivation_brief = (char.motivation or "")[:40]
            lines.append(f"| {cid} | {char.name} | {char.role} | {personality_brief} | {motivation_brief} |")
        lines.append("")

        self._write(FILE_CHARACTERS, "\n".join(lines))

    # ── Load (individual files) ───────────────────────────────────

    def load_world(self) -> str | None:
        """Load world-building Markdown for agent context."""
        return self._read(FILE_WORLD)

    def load_factions(self) -> str | None:
        """Load factions Markdown for agent context."""
        return self._read(FILE_FACTIONS)

    def load_style(self) -> str | None:
        """Load style contract Markdown for agent context."""
        return self._read(FILE_STYLE)

    def load_themes(self) -> str | None:
        """Load themes & conflicts Markdown for agent context."""
        return self._read(FILE_THEMES)

    def load_pleasure_points(self) -> str | None:
        """Load pleasure point model Markdown for agent context."""
        return self._read(FILE_PLEASURE)

    def load_characters(self) -> str | None:
        """Load character reference Markdown for agent context."""
        return self._read(FILE_CHARACTERS)

    def load_all(self) -> dict[str, str]:
        """Load all bible files as a dict of filename → content."""
        result = {}
        for filename in ALL_BIBLE_FILES:
            content = self._read(filename)
            if content:
                result[filename] = content
        return result

    # ── Helpers ────────────────────────────────────────────────────

    def _write(self, filename: str, content: str) -> None:
        """Write a bible file."""
        path = self._bible_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.debug(f"Wrote {path}")

    def _read(self, filename: str) -> str | None:
        """Read a bible file, returning None if it doesn't exist."""
        path = self._bible_dir / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @property
    def bible_dir(self) -> Path:
        return self._bible_dir

    def exists(self) -> bool:
        """Check if bible files have been saved."""
        return (self._bible_dir / FILE_WORLD).exists()
