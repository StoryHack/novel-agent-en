"""Validated observations from English-language fiction discovery lists."""

import csv
import io
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Platform = Literal["wattpad", "royal_road"]
PLATFORM_NAMES = {"wattpad": "Wattpad", "royal_road": "Royal Road"}
PLATFORM_DOMAINS = {"wattpad": "wattpad.com", "royal_road": "royalroad.com"}
STORY_PATHS = {"wattpad": "/story/", "royal_road": "/fiction/"}
CSV_COLUMNS = (
    "platform",
    "list_name",
    "source_url",
    "captured_on",
    "story_url",
    "title",
    "filters",
    "language",
    "fiction_type",
    "rank",
    "tags",
    "reads",
    "votes",
    "views",
    "followers",
    "rating",
    "note",
)
REQUIRED_COLUMNS = CSV_COLUMNS[:6]
MAX_CSV_CHARS = 100_000
MAX_OBSERVATIONS = 100
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Count = Annotated[int, Field(ge=0, le=10**12)]


def _platform_url(url: str, platform: Platform) -> re.Match:
    host = re.escape(PLATFORM_DOMAINS[platform])
    match = re.fullmatch(r"https://(?:www\.)?" + host + r"(/[^\s\\]*)", url)
    if not match:
        raise ValueError(f"Use an HTTPS {PLATFORM_NAMES[platform]} link")
    return match


class StoryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reads: Count | None = None
    votes: Count | None = None
    views: Count | None = None
    followers: Count | None = None
    rating: float | None = Field(default=None, ge=0, le=5)


class StoryObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    story_url: str = Field(max_length=500)
    title: ShortText
    language: Literal["en", "unknown"] = "unknown"
    fiction_type: Literal["original", "fanfiction", "unknown"] = "unknown"
    rank: int | None = Field(default=None, gt=0, le=100_000)
    tags: list[ShortText] = Field(default_factory=list, max_length=15)
    metrics: StoryMetrics = Field(default_factory=StoryMetrics)
    note: str = Field(default="", max_length=400)


class ResearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: Platform
    list_name: ShortText
    source_url: str = Field(max_length=500)
    captured_on: date
    filters: str = Field(default="", max_length=250)
    collection_method: Literal["manual", "authorized_dataset"] = "manual"
    observations: list[StoryObservation] = Field(min_length=1, max_length=MAX_OBSERVATIONS)

    def story_ref(self, story: StoryObservation) -> str:
        match = re.match(
            re.escape(STORY_PATHS[self.platform]) + r"([0-9]{1,20})(?=[-/?#]|$)",
            _platform_url(story.story_url, self.platform)[1],
        )
        if not match:
            raise ValueError(f"Use a {PLATFORM_NAMES[self.platform]} story link with its numeric ID")
        return f"{self.platform}:{int(match[1])}"

    @model_validator(mode="after")
    def validate_provenance(self):
        _platform_url(self.source_url, self.platform)
        refs = [self.story_ref(story) for story in self.observations]
        if len(refs) != len(set(refs)):
            raise ValueError(f"Duplicate story in {self.list_name}. Keep one row per story on each list.")
        return self


class ResearchImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshots: list[ResearchSnapshot] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_batch(self):
        if sum(len(snapshot.observations) for snapshot in self.snapshots) > MAX_OBSERVATIONS:
            raise ValueError(f"Import at most {MAX_OBSERVATIONS} observations")
        lists = {(s.platform, s.list_name, s.source_url, s.captured_on, s.filters) for s in self.snapshots}
        if len(lists) != len(self.snapshots):
            raise ValueError("Combine observations for each list and capture date into one snapshot")
        return self

    def coverage(self) -> dict[Platform, int]:
        refs = {snapshot.story_ref(story) for snapshot in self.snapshots for story in snapshot.observations}
        return {platform: sum(ref.startswith(f"{platform}:") for ref in refs) for platform in PLATFORM_NAMES}

    def english_tags(self) -> dict[str, dict[Platform, list[str]]]:
        """Index shared tag spellings by source and unique English story references."""
        tags: dict[str, dict[Platform, set[str]]] = {}
        for snapshot in self.snapshots:
            for story in snapshot.observations:
                if story.language != "en":
                    continue
                ref = snapshot.story_ref(story)
                for tag in story.tags:
                    tags.setdefault(tag.casefold(), {}).setdefault(snapshot.platform, set()).add(ref)
        return {
            tag: {platform: sorted(refs) for platform, refs in sources.items()} for tag, sources in sorted(tags.items())
        }

    @classmethod
    def from_csv(cls, content: str) -> "ResearchImport":
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers) or not set(REQUIRED_COLUMNS) <= set(headers) <= set(CSV_COLUMNS):
            raise ValueError("Use the CSV template with the six required column names")
        groups = {}
        metadata = (*REQUIRED_COLUMNS[:4], "filters")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Wrong number of columns on CSV line {reader.line_num}")
            row = {key: value.strip() for key, value in row.items()}
            if any(not row[key] for key in REQUIRED_COLUMNS):
                raise ValueError(f"Missing required data on CSV line {reader.line_num}")
            key = tuple(row.get(field, "") for field in metadata)
            snapshot = groups.setdefault(key, dict(zip(metadata, key), observations=[]))
            snapshot["observations"].append(
                {
                    "story_url": row["story_url"],
                    "title": row["title"],
                    "language": row.get("language") or "unknown",
                    "fiction_type": row.get("fiction_type") or "unknown",
                    "rank": row.get("rank") or None,
                    "tags": [tag.strip() for tag in row.get("tags", "").split("|") if tag.strip()],
                    "metrics": {name: row[name] for name in StoryMetrics.model_fields if row.get(name)},
                    "note": row.get("note", ""),
                }
            )
        return cls.model_validate({"snapshots": list(groups.values())})
