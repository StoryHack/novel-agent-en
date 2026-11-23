"""Topic research and commercial web novel pipeline models.

Covers the upstream workflow: platform scanning → benchmark analysis →
topic generation → scoring → title/synopsis → mini-arc outline.
"""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

# ============================================================
# Step 1A/1B: Platform Scanning
# ============================================================


class ScanEntry(BaseModel):
    """A single entry from a platform rankings scan."""

    rank: int = Field(default=0, description="Rank position on the list")
    title: str = Field(default="", description="Book title")
    genre: str = Field(default="", description="Genre / category tags")
    title_appeal: str = Field(default="", description="What makes the title attention-grabbing")
    one_liner: str = Field(default="", description="One-sentence selling point")
    golden_finger: str = Field(default="", description="Core cheat / unique ability")
    opening_pressure: str = Field(default="", description="Chapter 1 opening pressure / conflict")
    pleasure_loop: str = Field(default="", description="Core pleasure-point loop pattern")
    tomato_adaptable: bool = Field(default=False, description="Whether suitable for Tomato (free) platform")

    @field_validator("tomato_adaptable", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "是", "1", "y")
        if isinstance(v, (int, float)):
            return bool(v)
        return False


class ScanReport(BaseModel):
    """Complete platform scan report (Step 1A or 1B)."""

    platform: str = Field(default="", description="Platform name: Feilu or Fanqie")
    list_name: str = Field(default="", description="Name of the ranking list consulted")
    date: str = Field(default="", description="Date of scan (YYYY-MM-DD)")
    entries: list[ScanEntry] = Field(default_factory=list, description="Top 10-20 entries")
    summary: str = Field(default="", description="Overall trends and observations")
    scan_failed: bool = Field(default=False, description="True if scan could not access real data")

    @model_validator(mode="before")
    @classmethod
    def coerce_from_dict(cls, data: Any) -> Any:
        if isinstance(data, str):
            if data.strip() in ("Ranking scan failed", "本次扫榜失败"):
                return {"scan_failed": True, "summary": data}
            return {"summary": data}
        return data


# ============================================================
# Step 1C: Cross-Platform Analysis
# ============================================================


class CrossPlatformEntry(BaseModel):
    """A single genre/direction in the cross-platform comparison table."""

    genre: str = Field(default="", description="Genre / topic direction name")
    feilu_heat: bool = Field(
        default=False,
        description="Whether the genre is popular on Feilu",
        validation_alias=AliasChoices("feilu_heat", "是否有飞卢明显热度"),
    )
    tomato_audience: bool = Field(
        default=False,
        description="Whether there is an established audience on Fanqie",
        validation_alias=AliasChoices("tomato_audience", "番茄是否有对应读者基础"),
    )
    feilu_appeal: str = Field(
        default="",
        description="What attracts readers on Feilu",
        validation_alias=AliasChoices("feilu_appeal", "飞卢吸引读者的点"),
    )
    tomato_adjustment: str = Field(
        default="",
        description="Adaptations needed for Fanqie",
        validation_alias=AliasChoices("tomato_adjustment", "到番茄需要调整什么"),
    )
    risk: str = Field(default="", description="Risk points")
    recommendation: str = Field(
        default="medium",
        description="Recommended level: high / medium / low",
        validation_alias=AliasChoices("recommendation", "推荐等级: high / medium / low"),
    )

    @field_validator("feilu_heat", "tomato_audience", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "是", "1", "y")
        return False


class CrossPlatformReport(BaseModel):
    """Complete cross-platform comparison report (Step 1C)."""

    entries: list[CrossPlatformEntry] = Field(default_factory=list)
    selected_directions: list[str] = Field(
        default_factory=list,
        description="3-5 recommended directions with rationale",
    )


# ============================================================
# Step 2: Benchmark Book Skeleton Analysis
# ============================================================


class BenchmarkSkeleton(BaseModel):
    """Structural skeleton of a single benchmark book (Step 2)."""

    title: str = Field(default="", description="Title", validation_alias=AliasChoices("title", "书名"))
    genre: str = Field(default="", description="Genre", validation_alias=AliasChoices("genre", "题材"))
    title_appeal: str = Field(
        default="",
        description="What makes the title compelling",
        validation_alias=AliasChoices("title_appeal", "书名吸量点"),
    )
    synopsis_promise: str = Field(
        default="",
        description="Payoff promised by the synopsis",
        validation_alias=AliasChoices("synopsis_promise", "简介承诺的爽点"),
    )
    protagonist_opening: str = Field(
        default="",
        description="Protagonist's starting situation",
        validation_alias=AliasChoices("protagonist_opening", "主角开局处境"),
    )
    golden_finger: str = Field(
        default="",
        description="Signature advantage or hidden strength",
        validation_alias=AliasChoices("golden_finger", "金手指或核心底牌"),
    )
    opening_pressure: str = Field(
        default="",
        description="Opening pressure",
        validation_alias=AliasChoices("opening_pressure", "开篇压力"),
    )
    first_event: str = Field(
        default="",
        description="How the opening arc starts",
        validation_alias=AliasChoices("first_event", "首个小事件如何启动"),
    )
    pleasure_loop: str = Field(
        default="",
        description="Payoff Loop",
        validation_alias=AliasChoices("pleasure_loop", "爽点循环"),
    )
    borrow_elements: list[str] = Field(
        default_factory=list,
        description="Which elements are worth borrowing?",
        validation_alias=AliasChoices("borrow_elements", "哪些元素值得借"),
    )
    replace_elements: list[str] = Field(
        default_factory=list,
        description="Elements to replace for originality",
        validation_alias=AliasChoices("replace_elements", "哪些元素必须换掉避免高仿"),
    )


class BenchmarkReport(BaseModel):
    """Complete benchmark skeleton analysis (Step 2)."""

    entries: list[BenchmarkSkeleton] = Field(default_factory=list)
    structural_summary: str = Field(
        default="",
        description="Promising structural patterns for each genre",
        validation_alias=AliasChoices("structural_summary", "每个题材最值得借的结构骨架总结"),
    )


# ============================================================
# Step 3A: Candidate Topics
# ============================================================


class CandidateTopic(BaseModel):
    """A single candidate topic generated from research (Step 3A)."""

    genre_name: str = Field(default="", description="Genre name", validation_alias=AliasChoices("genre_name", "题材名称"))
    one_line_setting: str = Field(
        default="",
        description="One-sentence premise",
        validation_alias=AliasChoices("one_line_setting", "一句话设定"),
    )
    golden_finger: str = Field(
        default="",
        description="Signature Advantage",
        validation_alias=AliasChoices("golden_finger", "核心金手指"),
    )
    chapter1_conflict: str = Field(
        default="",
        description="First-chapter conflict",
        validation_alias=AliasChoices("chapter1_conflict", "第一章冲突"),
    )
    first_event_direction: str = Field(
        default="",
        description="Direction of the opening arc",
        validation_alias=AliasChoices("first_event_direction", "首个小事件闭环方向"),
    )
    first_pleasure_wave: str = Field(
        default="",
        description="First Wave Payoff",
        validation_alias=AliasChoices("first_pleasure_wave", "第一波爽点"),
    )
    tomato_fit: str = Field(
        default="medium",
        description="Fit for Fanqie readers: high / medium / low",
        validation_alias=AliasChoices("tomato_fit", "番茄适配度: high / medium / low"),
    )
    video_potential: str = Field(
        default="medium",
        description="Short-form video potential: high / medium / low",
        validation_alias=AliasChoices("video_potential", "视频表现力: high / medium / low"),
    )
    risk: str = Field(default="", description="Potential risks", validation_alias=AliasChoices("risk", "风险点"))


class CandidateTopicsOutput(BaseModel):
    """12 candidate topics output (Step 3A)."""

    topics: list[CandidateTopic] = Field(default_factory=list, description="12 Candidates")


# ============================================================
# Step 3B: Topic Scoring
# ============================================================


class TopicScoreCard(BaseModel):
    """Score card for a single topic (Step 3B)."""

    genre_name: str = Field(default="", description="Genre name", validation_alias=AliasChoices("genre_name", "题材名称"))
    score_title_appeal: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Title appeal",
        validation_alias=AliasChoices("score_title_appeal", "书名吸量潜力"),
    )
    score_opening_pressure: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Strength of the first-chapter conflict",
        validation_alias=AliasChoices("score_opening_pressure", "第一章开篇压力"),
    )
    score_event_clarity: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Clarity of the opening arc",
        validation_alias=AliasChoices("score_event_clarity", "首个小事件闭环是否清楚"),
    )
    score_golden_finger: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Ability of the premise to sustain payoffs",
        validation_alias=AliasChoices("score_golden_finger", "金手指是否能持续制造爽点"),
    )
    score_tomato_fit: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Fit for Fanqie readers",
        validation_alias=AliasChoices("score_tomato_fit", "番茄适配度"),
    )
    score_ai_stability: float = Field(default=5.0, ge=0.0, le=10.0, description="Stability during AI-assisted writing")
    score_video_potential: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Short-form video potential",
        validation_alias=AliasChoices("score_video_potential", "视频表现力"),
    )
    score_breakdown_risk: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Risk of contradictions in a long novel",
        validation_alias=AliasChoices("score_breakdown_risk", "吃书/崩设定风险（越低越好）"),
    )
    total_score: float = Field(
        default=0.0,
        description="Combined score (auto-calculated)",
        validation_alias=AliasChoices("total_score", "综合得分（自动计算）"),
    )
    human_note: str = Field(
        default="",
        description="Trade-offs for the author to consider",
        validation_alias=AliasChoices("human_note", "人工选择建议：每个题材适合什么取舍"),
    )


class TopicScoringReport(BaseModel):
    """Complete topic scoring report (Step 3B)."""

    scores: list[TopicScoreCard] = Field(default_factory=list)
    top_4: list[str] = Field(
        default_factory=list,
        description="Top four recommended genres",
        validation_alias=AliasChoices("top_4", "推荐前4名题材名称"),
    )


# ============================================================
# Step 4A: Title & Synopsis
# ============================================================


class TitleSynopsisPair(BaseModel):
    """A single title + synopsis candidate (Step 4A)."""

    title: str = Field(default="", description="Title", validation_alias=AliasChoices("title", "书名"))
    synopsis: str = Field(default="", description="Synopsis", validation_alias=AliasChoices("synopsis", "简介"))
    score_clarity: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Clarity at a glance",
        validation_alias=AliasChoices("score_clarity", "一眼能否看懂"),
    )
    score_click_appeal: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Click appeal",
        validation_alias=AliasChoices("score_click_appeal", "吸点击感"),
    )
    score_tomato_taste: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Fit for free-to-read fiction on Fanqie",
        validation_alias=AliasChoices("score_tomato_taste", "番茄免费文口味"),
    )
    score_video_spread: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Potential to spread through short-form video",
        validation_alias=AliasChoices("score_video_spread", "视频传播性"),
    )
    score_ch1_conflict: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Whether or not it's easy to trigger conflict in Chapter One",
        validation_alias=AliasChoices("score_ch1_conflict", "是否容易引出第一章冲突"),
    )
    score_10chapter_viable: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Goal of the opening arc",
        validation_alias=AliasChoices("score_10chapter_viable", "是否方便写出10章小事件闭环"),
    )


class TitleSynopsisReport(BaseModel):
    """Title & synopsis report for one topic (Step 4A)."""

    genre_name: str = Field(default="", description="Genre name", validation_alias=AliasChoices("genre_name", "题材名称"))
    title_candidates: list[TitleSynopsisPair] = Field(default_factory=list, description="Ten title options and three synopsis variants")
    final_title: str = Field(
        default="",
        description="Selected title",
        validation_alias=AliasChoices("final_title", "最终选定的书名"),
    )
    final_synopsis: str = Field(
        default="",
        description="Selected synopsis",
        validation_alias=AliasChoices("final_synopsis", "最终选定的简介"),
    )


# ============================================================
# Step 5: Mini-Arc Outline (10-Chapter Small Event Loop)
# ============================================================


class MiniArcChapter(BaseModel):
    """A single chapter in the 10-chapter mini-arc outline (Step 5)."""

    chapter_number: int = Field(
        default=0,
        description="Chapter No. (1-10)",
        validation_alias=AliasChoices("chapter_number", "章节号 (1-10)"),
    )
    goal: str = Field(default="", description="Chapter Goal", validation_alias=AliasChoices("goal", "本章目标"))
    conflict: str = Field(default="", description="Chapter Conflict", validation_alias=AliasChoices("conflict", "本章冲突"))
    pleasure_point: str = Field(
        default="",
        description="Chapter Payoff",
        validation_alias=AliasChoices("pleasure_point", "本章爽点"),
    )
    new_info: str = Field(default="", description="New Information", validation_alias=AliasChoices("new_info", "新增信息"))
    character_change: str = Field(
        default="",
        description="Character Change",
        validation_alias=AliasChoices("character_change", "人物状态变化"),
    )
    foreshadowing: str = Field(
        default="",
        description="Foreshadowing",
        validation_alias=AliasChoices("foreshadowing", "伏笔推进"),
    )
    ending_hook: str = Field(
        default="",
        description="Ending Hook",
        validation_alias=AliasChoices("ending_hook", "结尾钩子"),
    )


class MiniArcOutline(BaseModel):
    """Complete 10-chapter mini-arc outline for one topic (Step 5)."""

    genre_name: str = Field(default="", description="Genre name", validation_alias=AliasChoices("genre_name", "题材名称"))
    total_words: str = Field(
        default="20,000-21,000",
        description="Total expected words",
        validation_alias=AliasChoices("total_words", "预计总字数"),
    )
    chapters: list[MiniArcChapter] = Field(default_factory=list, description="Ten-chapter outline (2,000–2,100 words per chapter)")
    arc_goal: str = Field(
        default="",
        description="Goal of the opening arc",
        validation_alias=AliasChoices("arc_goal", "小事件闭环总目标"),
    )
    next_arc_hook: str = Field(
        default="",
        description="Hook for the next arc",
        validation_alias=AliasChoices("next_arc_hook", "下一事件的钩子"),
    )


# ============================================================
# Aggregated Pipeline State
# ============================================================


class TopicResearchState(BaseModel):
    """Aggregated state for the entire topic research pipeline (Steps 1-4).

    Stored in MainState.topic_research.
    """

    feilu_scan: ScanReport | None = Field(
        default=None,
        description="Feilu ranking scan results",
        validation_alias=AliasChoices("feilu_scan", "飞卢扫榜结果"),
    )
    fanqie_scan: ScanReport | None = Field(
        default=None,
        description="Fanqie ranking scan results",
        validation_alias=AliasChoices("fanqie_scan", "番茄扫榜结果"),
    )
    cross_platform: CrossPlatformReport | None = Field(
        default=None,
        description="Cross-platform analysis",
        validation_alias=AliasChoices("cross_platform", "双榜交叉结论"),
    )
    benchmarks: BenchmarkReport | None = Field(
        default=None,
        description="Benchmark book analysis",
        validation_alias=AliasChoices("benchmarks", "对标书骨架拆解"),
    )
    candidates: CandidateTopicsOutput | None = Field(default=None, description="12 Candidates")
    scores: TopicScoringReport | None = Field(
        default=None,
        description="Concept scores",
        validation_alias=AliasChoices("scores", "题材评分"),
    )
    title_synopsis: list[TitleSynopsisReport] = Field(
        default_factory=list,
        description="Titles and synopses for the final two concepts",
        validation_alias=AliasChoices("title_synopsis", "最终2个题材的书名和简介"),
    )
    selected_genres: list[str] = Field(
        default_factory=list,
        description="Genres selected by the author",
        validation_alias=AliasChoices("selected_genres", "人工选定的最终题材名称"),
    )
