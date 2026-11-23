"""Base agent class with prompt rendering and structured LLM generation.

Supports both inline prompts (for backward compat) and Jinja2 template-based
prompts (for externalized, editable prompt management).
"""

import logging
from abc import ABC
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel

from ..config.prompts.prompt_loader import PromptLoader, get_prompt_loader
from ..llm.client import LLMResponse
from ..llm.scheduler import ModelScheduler

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all novel-writing agents.

    Each agent has:
    - An agent_type string that maps to a ModelAssignment
    - A reference to the ModelScheduler for LLM calls
    - Prompt rendering via Jinja2 templates (with inline fallback)
    """

    agent_type: str = "base"

    def __init__(self, scheduler: ModelScheduler, prompt_loader: PromptLoader | None = None):
        self.scheduler = scheduler
        self._prompt_loader = prompt_loader

    # ================================================================
    # Core generation methods
    # ================================================================

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMResponse:
        """Generate a text response from the assigned LLM.

        Args:
            system_prompt: System-level instructions for the LLM.
            user_prompt: The actual task content.
            temperature_override: Override the default temperature.
            max_tokens_override: Override the default max tokens.

        Returns:
            LLMResponse with the generated text and metadata.
        """
        return await self.scheduler.generate(
            agent_type=self.agent_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> BaseModel:
        """Generate a structured response and parse it into a Pydantic model.

        Args:
            system_prompt: System-level instructions.
            user_prompt: The actual task content.
            response_model: Pydantic model class to parse the response into.
            temperature_override: Override the default temperature.
            max_tokens_override: Override the default max tokens.

        Returns:
            An instance of response_model populated from the LLM output.
        """
        return await self.scheduler.generate_structured(
            agent_type=self.agent_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a text response from the assigned LLM, yielding tokens.

        For structured (JSON) output, use generate_structured() instead.
        """
        async for token in self.scheduler.generate_stream(
            agent_type=self.agent_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
        ):
            yield token

    # ================================================================
    # Template-based prompt rendering
    # ================================================================

    @property
    def prompt_loader(self) -> PromptLoader:
        """Get the prompt loader, lazily initializing from singleton if needed."""
        if self._prompt_loader is None:
            self._prompt_loader = get_prompt_loader()
        return self._prompt_loader

    def render_prompt(
        self,
        method: str,
        prompt_type: str = "system",
        default: str = "",
        **variables: Any,
    ) -> str:
        """Render a prompt from a Jinja2 template, with inline fallback.

        Template path: {agent_type}/{method}_{prompt_type}.j2

        Args:
            method: Method name (e.g. 'generate_chapter').
            prompt_type: 'system' or 'user'.
            default: Fallback string if template doesn't exist.
            **variables: Variables passed to the template.

        Returns:
            Rendered prompt string (or default if template not found).
        """
        result = self.prompt_loader.render_or_none(
            agent=self.agent_type,
            method=method,
            prompt_type=prompt_type,
            **variables,
        )
        if result is not None:
            return result
        # Template not found — log once and use default
        logger.debug(f"No template for {self.agent_type}/{method}_{prompt_type}.j2 — using inline prompt")
        return default

    def render_prompts(
        self,
        method: str,
        system_default: str = "",
        user_default: str = "",
        **variables: Any,
    ) -> tuple[str, str]:
        """Render both system and user prompts for a method.

        Returns (system_prompt, user_prompt) — using templates when available,
        falling back to the provided defaults.

        This is the primary method agents should call. It centralizes the
        template-vs-inline decision so individual agents don't repeat the logic.
        """
        system = self.render_prompt(method, "system", system_default, **variables)
        user = self.render_prompt(method, "user", user_default, **variables)
        return system, user

    def has_template(self, method: str) -> bool:
        """Check if both system+user templates exist for a method."""
        return self.prompt_loader.has_template(self.agent_type, method)

    # ================================================================
    # Prompt helpers (inline fallback — kept for backward compat)
    # ================================================================

    # ── Shared truncation helper (used by Editor & ContinuityChecker) ──
    _MAX_CHAPTER_CHARS: int = 8000

    @staticmethod
    def _chapter_excerpt(content: str, max_chars: int | None = None) -> str:
        """Return chapter content, truncated if it exceeds budget.

        When truncation is needed, keeps the first 60% and last 40% so the
        caller sees both setup and resolution.
        """
        limit = max_chars or BaseAgent._MAX_CHAPTER_CHARS
        if len(content) <= limit:
            return content
        head = int(limit * 0.6)
        tail = limit - head
        return (
            content[:head]
            + f"\n\n... ({len(content) - limit} characters omitted) ...\n\n"
            + content[-tail:]
        )

    @staticmethod
    def build_system_prompt(role: str, expertise: str, constraints: str = "", inspiration: str = "") -> str:
        """Build a standard system prompt for an agent.

        Args:
            role: The agent's role description.
            expertise: What the agent is expert at.
            constraints: Any specific constraints or rules.
            inspiration: Optional human-provided inspiration/ideas.

        Returns:
            Formatted system prompt string.
        """
        prompt = f"""You are a {role}.

Your expertise: {expertise}

Working principles:
1. Follow the requested output format and return structured data.
2. Base your work on the supplied context without inventing unsupported facts.
3. Maintain internal and logical consistency.
4. Use English unless the context specifies another language.
"""
        if constraints:
            prompt += f"\n\nAdditional constraints:\n{constraints}"

        if inspiration:
            prompt += f"\n\nUser inspiration and requirements:\n{inspiration}\nUse these ideas and requirements to guide your work."

        return prompt

    @staticmethod
    def build_context_block(
        project_config: dict | None = None,
        bible: dict | None = None,
        characters: dict | None = None,
        outline: dict | None = None,
        memory: dict | None = None,
    ) -> str:
        """Build a context block string from available artifacts.

        Pass dicts obtained from model_dump() to avoid coupling to model imports.
        """
        parts = []

        if project_config:
            parts.append("=== Project Configuration ===")
            parts.append(f"Genre: {project_config.get('genre', [])}")
            parts.append(f"Target audience: {project_config.get('target_readers', '')}")
            parts.append(f"Tone: {project_config.get('tone', '')}")
            parts.append(f"Language: {project_config.get('language', 'en')}")
            parts.append("")

        if bible:
            parts.append("=== Worldbuilding ===")
            world = bible.get("world", {})
            if world:
                parts.append(f"World name: {world.get('name', '')}")
                parts.append(f"World type: {world.get('world_type', '')}")
                parts.append(f"Geography: {world.get('geography', '')}")
                parts.append(f"History: {world.get('history', '')}")
                parts.append(f"Culture: {world.get('culture', '')}")
                if world.get("magic_system"):
                    parts.append(f"Magic or power system: {world['magic_system']}")

            style = bible.get("style_contract", {})
            if style:
                parts.append(f"Tone: {style.get('tone', '')}")
                parts.append(f"Sentence style: {style.get('sentence_style', '')}")

            themes = bible.get("themes", [])
            if themes:
                theme_names = [t.get("name", "") for t in themes]
                parts.append(f"Themes: {', '.join(theme_names)}")

            parts.append("")

        if characters:
            parts.append("=== Character Profiles ===")
            for char_id, char in characters.items():
                if isinstance(char, dict):
                    parts.append(f"[{char_id}] {char.get('name', '')} ({char.get('role', '')})")
                    parts.append(f"  Personality: {char.get('personality', '')}")
                    parts.append(f"  Motivation: {char.get('motivation', '')}")
                    parts.append(f"  Flaw: {char.get('flaw', '')}")
                    state = char.get("current_state", {})
                    if state:
                        parts.append(f"  Current status: {state}")
            parts.append("")

        if outline:
            parts.append("=== Outline Reference ===")
            parts.append(f"Main Plot: {outline.get('logline', '')}")
            volumes = outline.get("volumes", [])
            if volumes:
                for v in volumes:
                    if isinstance(v, dict):
                        parts.append(f"  Volume {v.get('number', '?')}: {v.get('title', '')}")
            parts.append("")

        if memory:
            # ── Short-term (previous chapter) ──
            st = memory.get("short_term", {})
            if st:
                parts.append("=== Recent Memory ===")
                prev = st.get("current_chapter_summary", "")
                if prev:
                    parts.append(f"Summary of the previous chapter: {prev}")
                parts.append(f"Unresolved hooks: {st.get('unresolved_hooks', [])}")
                parts.append(f"Active foreshadowing: {st.get('active_foreshadowing', [])}")
                parts.append("")

            # ── Hierarchical summaries (long-term context) ──
            lt = memory.get("long_term", {})
            if lt:
                parts.append("=== Story Context ===")
                # Current stage summary (most recent 10-chapter block)
                stages = lt.get("stage_summaries", {})
                if stages:
                    latest_stage = stages.get(max(stages.keys()), "")
                    if latest_stage:
                        parts.append(f"Current stage (latest 10 chapters): {latest_stage}")

                # Current arc summary (most recent 50-chapter block)
                arcs = lt.get("arc_summaries", {})
                if arcs:
                    latest_arc = arcs.get(max(arcs.keys()), "")
                    if latest_arc:
                        parts.append(f"Current arc (latest 50 chapters): {latest_arc}")

                # Global summary (entire book)
                gs = lt.get("global_summary", "")
                if gs:
                    parts.append(f"Story-wide summary: {gs}")

                parts.append("")

        return "\n".join(parts)
