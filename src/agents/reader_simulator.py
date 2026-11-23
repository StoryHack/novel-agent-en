"""Reader Simulator Agent — simulates reader experience and emotional response."""

import logging

from pydantic import AliasChoices, BaseModel, Field

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft
from ..models.review import Issue
from .base import BaseAgent

logger = logging.getLogger(__name__)


class ReaderFeedbackOutput(BaseModel):
    """LLM output for reader simulation."""

    engagement_score: float = Field(
        default=7.0,
        ge=0.0,
        le=10.0,
        description="Reader engagement score",
        validation_alias=AliasChoices("engagement_score", "沉浸感评分"),
    )
    emotional_impact: str = Field(
        default="",
        description="Emotional impact description",
        validation_alias=AliasChoices("emotional_impact", "情感冲击描述"),
    )
    boring_sections: list[str] = Field(
        default_factory=list,
        description="Passages the reader might skip",
        validation_alias=AliasChoices("boring_sections", "可能让读者感到无聊的段落"),
    )
    exciting_sections: list[str] = Field(
        default_factory=list,
        description="Passages the reader found engaging",
        validation_alias=AliasChoices("exciting_sections", "让读者兴奋的段落"),
    )
    continuation_likelihood: float = Field(
        default=7.0,
        ge=0.0,
        le=10.0,
        description="The reader wants to continue reading the next chapter",
        validation_alias=AliasChoices("continuation_likelihood", "读者想继续读下一章的可能性"),
    )
    reader_questions: list[str] = Field(
        default_factory=list,
        description="Problems that readers may have in reading",
        validation_alias=AliasChoices("reader_questions", "读者在阅读时可能会产生的问题"),
    )
    issues: list[Issue] = Field(
        default_factory=list,
        description="Issues identified from the reader's perspective",
        validation_alias=AliasChoices("issues", "从读者视角发现的问题"),
    )


class ReaderSimulatorAgent(BaseAgent):
    """Simulates a target reader's experience to provide reader-centric feedback.

    This agent is distinct from the Editor — it doesn't judge technical quality,
    it judges reading enjoyment. It answers: "Would the target reader enjoy this?"
    """

    agent_type = "reader_simulator"

    async def simulate_reading(
        self,
        draft: ChapterDraft,
        bible: NovelBible,
        target_reader: str = "",
    ) -> dict:
        """Simulate a target reader reading this chapter.

        Returns a dict with engagement metrics and reader-centric feedback.
        """
        reader = target_reader or "General fiction reader"
        chapter_text = self._chapter_excerpt(draft.content, max_chars=6000)

        system_default = self.build_system_prompt(
            role="reader experience simulator",
            expertise=f"Read as {reader} would. Respond to hooks, boredom, emotional identification, and surprises from that reader's perspective.",
        )
        user_default = f"""Read the chapter from the intended reader's perspective.

Reader profile: {reader}
Tone: {bible.style_contract.tone}
Setting type: {bible.world.world_type}

Full chapter:
{chapter_text}

Report:
1. Immersion (0–10).
2. Your emotional response, such as excitement, anticipation, or indifference.
3. Passages you wanted to skip, with quotes.
4. Passages that drew you in, with quotes.
5. Desire to continue immediately (0–10).
6. Questions or curiosities that arose while reading.
7. How strongly the ending made you want the next chapter."""

        system, user = self.render_prompts(
            "simulate_reading",
            system_default=system_default,
            user_default=user_default,
            target_reader=reader,
            tone=bible.style_contract.tone,
            world_type=bible.world.world_type,
            chapter_text=chapter_text,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=ReaderFeedbackOutput,
            temperature_override=0.5,
        )

        return {
            "engagement_score": result.engagement_score,
            "emotional_impact": result.emotional_impact,
            "boring_sections": result.boring_sections,
            "exciting_sections": result.exciting_sections,
            "continuation_likelihood": result.continuation_likelihood,
            "reader_questions": result.reader_questions,
            "issues": [i for i in result.issues if i.category not in ("consistency", "style")],
        }
