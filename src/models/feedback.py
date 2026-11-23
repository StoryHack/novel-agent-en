"""User feedback models for human-in-the-loop quality tracking.

Implements the explicit feedback entry system required by the evaluation report:
-  thumbs up/down (sentiment)
- Reason tags for negative feedback
- Optional free-text notes
- Timestamped records for data flywheel
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FeedbackSentiment(StrEnum):
    """User sentiment about a chapter or phase output."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackReasonTag(StrEnum):
    """Predefined reason tags for negative feedback.

    These map to the evaluation report's required categories:
    - Not meeting expectations
    - Inconsistent characterization
    - Boring plot
    - Overly generic AI prose
    - Other
    """

    NOT_MEETING_EXPECTATIONS = "not_meeting_expectations"  # Did not meet expectations
    CHARACTER_BROKEN = "character_broken"  # Inconsistent characterization
    PLOT_BORING = "plot_boring"  # Boring plot
    AI_FLAVOR_HEAVY = "ai_flavor_heavy"  # Overly generic AI prose
    PACING_ISSUE = "pacing_issue"  # Pacing issue
    DIALOGUE_ISSUE = "dialogue_issue"  # Dialogue issue
    WORLDBUILDING_INCONSISTENT = "worldbuilding_inconsistent"  # Inconsistent worldbuilding
    OTHER = "other"  # Other


# Human-readable labels for each reason tag
REASON_TAG_LABELS: dict[FeedbackReasonTag, str] = {
    FeedbackReasonTag.NOT_MEETING_EXPECTATIONS: "Did not meet expectations",
    FeedbackReasonTag.CHARACTER_BROKEN: "Inconsistent characterization",
    FeedbackReasonTag.PLOT_BORING: "Boring plot",
    FeedbackReasonTag.AI_FLAVOR_HEAVY: "Overly generic AI prose",
    FeedbackReasonTag.PACING_ISSUE: "Pacing issue",
    FeedbackReasonTag.DIALOGUE_ISSUE: "Dialogue issue",
    FeedbackReasonTag.WORLDBUILDING_INCONSISTENT: "Inconsistent worldbuilding",
    FeedbackReasonTag.OTHER: "Other",
}


class FeedbackEntry(BaseModel):
    """A single feedback record attached to a chapter or phase.

    Stored alongside chapter artifacts for later aggregation into
    Bad Case reports and data-flywheel pipelines.
    """

    # Identity
    chapter_number: int = Field(default=0, description="Chapter this feedback relates to")
    phase: str = Field(default="", description="Workflow phase when feedback was given")

    # Sentiment
    sentiment: FeedbackSentiment = Field(
        default=FeedbackSentiment.THUMBS_UP,
        description="User sentiment: thumbs_up or thumbs_down",
    )

    # Structured reason (for negative feedback)
    reason_tags: list[FeedbackReasonTag] = Field(
        default_factory=list,
        description="Reason tags for the feedback (multiple allowed)",
    )

    # Free-text
    notes: str = Field(
        default="",
        description="Optional free-text feedback from the user",
    )

    # Traceability
    decision: str = Field(
        default="",
        description="The human decision that accompanied this feedback (accept/revise/rewrite/rollback)",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when feedback was submitted",
    )

    # Revision tracking (for data flywheel)
    revision_count: int = Field(
        default=0,
        description="How many times this chapter was revised before this feedback",
    )
    review_score: float = Field(
        default=0.0,
        description="The review score at the time of feedback",
    )

    @property
    def is_positive(self) -> bool:
        """Whether this is positive feedback."""
        return self.sentiment == FeedbackSentiment.THUMBS_UP

    @property
    def reason_labels(self) -> list[str]:
        """Human-readable labels for the reason tags."""
        return [REASON_TAG_LABELS.get(t, t.value) for t in self.reason_tags]


class FeedbackSummary(BaseModel):
    """Aggregated feedback statistics for a project or chapter range.

    Used for Bad Case weekly reports and monitoring dashboards.
    """

    project_id: str = ""
    total_feedback: int = 0
    positive_count: int = 0
    negative_count: int = 0
    acceptance_rate: float = 0.0  # positive / total

    # Reason tag distribution (for negative feedback)
    reason_distribution: dict[str, int] = Field(default_factory=dict)

    # Score correlation
    avg_review_score_accepted: float = 0.0
    avg_review_score_rejected: float = 0.0

    # Trend
    recent_acceptance_rate: float = 0.0  # Last 5 chapters
    trend_direction: str = "stable"  # improving, declining, stable
