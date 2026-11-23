"""Refiner Agent — polishes chapter drafts based on review feedback."""

import logging

from pydantic import AliasChoices, BaseModel, Field

from ..models.bible import NovelBible
from ..models.chapter import ChapterDraft, PolishedChapter
from ..models.review import ReviewReport
from ..utils.text import count_words
from .base import BaseAgent

logger = logging.getLogger(__name__)


class PolishedOutput(BaseModel):
    """LLM output for polished chapter."""

    title: str = Field(default="")
    content: str = Field(..., description="Polished chapter text", validation_alias=AliasChoices("content", "润色后的章节正文"))
    revision_notes: str = Field(
        default="",
        description="Revision notes",
        validation_alias=AliasChoices("revision_notes", "修改说明"),
    )


class RefinerAgent(BaseAgent):
    """Polishes and revises chapter drafts.

    Handles:
    - Language rhythm and flow improvements
    - Duplicate sentence pattern removal
    - Cliché expression elimination
    - Dialogue naturalization
    - Chapter-end hook strengthening
    - AI-flavor removal
    """

    agent_type = "refiner"

    async def polish_chapter(
        self,
        draft: ChapterDraft,
        review: ReviewReport,
        bible: NovelBible,
        human_feedback: str | None = None,
    ) -> PolishedChapter:
        """Polish a chapter draft based on review feedback.

        Args:
            draft: The chapter draft to polish.
            review: Review report with issues and suggestions.
            bible: Novel bible with style contract.
            human_feedback: Optional additional feedback from the human author.

        Returns:
            PolishedChapter with the refined content.
        """
        logger.info(f"Polishing chapter {draft.chapter_number}...")

        style = bible.style_contract

        # Compile issues into actionable feedback
        issues_text = self._format_issues(review)
        suggestions_text = "\n".join(f"- {s}" for s in review.suggestions)

        system_default = self.build_system_prompt(
            role="fiction line editor",
            expertise="Make prose precise, vivid, and engaging. Improve sentence rhythm, cut redundancy, sharpen imagery, and make dialogue sound natural. Watch for formulaic AI phrasing.",
            constraints=f"""Style constraints:
- Tone: {style.tone}
- Sentence style: {style.sentence_style}
- Expressions to avoid: {', '.join(style.forbidden_phrases) if style.forbidden_phrases else 'None'}
- Recommended techniques: {', '.join(style.preferred_techniques) if style.preferred_techniques else 'None'}""",
        )
        user_default = f"""Revise and polish this chapter.

Review:
Overall score: {review.overall_score:.1f}/10
Dimension scores: {str(review.dimension_scores)}

Issues to address:
{issues_text}

Suggested improvements:
{suggestions_text}

Original title: {draft.title}

Original chapter:
{draft.content}

1. Vary sentence structure and length.
2. Remove formulaic phrases such as "in summary," "it is worth noting," and "in the process of."
3. Give dialogue distinct character voices and cut lines that serve only to relay plot information.
4. Add visual, auditory, and tactile detail to key scenes.
5. Strengthen the ending hook.
6. Adjust the pacing and give the most important moments room to develop."""

        if human_feedback:
            user_default += f"\n\nAuthor feedback:\n{human_feedback}"

        system, user = self.render_prompts(
            "polish_chapter",
            system_default=system_default,
            user_default=user_default,
            tone=style.tone,
            sentence_style=style.sentence_style,
            forbidden_phrases=", ".join(style.forbidden_phrases) if style.forbidden_phrases else "None",
            preferred_techniques=", ".join(style.preferred_techniques) if style.preferred_techniques else "None",
            overall_score=review.overall_score,
            dimension_scores=str(review.dimension_scores),
            issues_text=issues_text,
            suggestions_text=suggestions_text,
            draft_title=draft.title,
            draft_content=draft.content,
            human_feedback=human_feedback,
        )

        result = await self.generate_structured(
            system_prompt=system,
            user_prompt=user,
            response_model=PolishedOutput,
            temperature_override=0.4,
            max_tokens_override=8192,
        )

        word_count = count_words(result.content)

        polished = PolishedChapter(
            chapter_number=draft.chapter_number,
            title=result.title or draft.title,
            content=result.content,
            word_count=word_count,
            revision_notes=result.revision_notes,
        )

        logger.info(f"Chapter {draft.chapter_number} polished: {word_count} words")
        return polished

    def _format_issues(self, review: ReviewReport) -> str:
        """Format review issues for the polish prompt."""
        if not review.issues:
            return "(no specific issues)"

        by_severity = {"critical": [], "major": [], "minor": [], "suggestion": []}
        for issue in review.issues:
            sev = issue.severity if isinstance(issue.severity, str) else issue.severity.value
            by_severity.setdefault(sev, []).append(issue)

        lines = []
        for sev in ["critical", "major", "minor", "suggestion"]:
            items = by_severity.get(sev, [])
            if items:
                lines.append(f"\n### {sev.upper()} ({len(items)})")
                for item in items:
                    lines.append(f"- [{item.category}] {item.description}")
                    if item.suggestion:
                        lines.append(f"  Recommendations: {item.suggestion}")

        return "\n".join(lines)
