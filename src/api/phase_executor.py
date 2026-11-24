"""Phase executor — runs individual workflow phases with streaming support."""

import logging

from ..agents.orchestrator import OrchestratorAgent
from ..models.state import MainState
from ..models.topic import TopicResearchState
from ..storage.file_manager import ProjectFileManager

logger = logging.getLogger(__name__)

# Display labels for each phase
PHASE_LABELS = {
    "project_init": "Project Initialization",
    "platform_scan": "Research Snapshots",
    "topic_selection": "Topic Research",
    "mini_arc_outline": "Opening Arc Outline",
    "bible_construction": "Worldbuilding",
    "character_creation": "Character Creation",
    "master_outline": "Outline Generation",
    "chapter_planning": "Chapter Planning",
    "chapter_writing": "Chapter Writing",
    "quality_review": "Quality Review",
    "polish_revision": "Polish and Revision",
    "memory_update": "Memory Update",
}

# Tab mapping for frontend auto-navigation
PHASE_TAB_MAP = {
    "platform_scan": "topics",
    "topic_selection": "topics",
    "mini_arc_outline": "topics",
    "bible_construction": "bible",
    "character_creation": "characters",
    "master_outline": "outline",
    "chapter_planning": "chapters",
    "chapter_writing": "chapters",
    "quality_review": "chapters",
    "polish_revision": "chapters",
}


async def execute_phase_bible(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute world-building phase."""
    state = await orchestrator.build_bible_world(state)
    if state.bible:
        fm.save_bible(state.bible)
    return state


async def execute_phase_characters(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute character creation phase."""
    state = await orchestrator.create_characters(state)
    if state.characters:
        fm.save_characters(state.characters)
    return state


async def execute_phase_outline(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute master outline phase."""
    state = await orchestrator.create_outline(state)
    if state.outline:
        fm.save_master_outline(state.outline)
    return state


async def execute_phase_chapter_planning(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute chapter planning phase."""
    state = await orchestrator.plan_chapter(state)
    if state.chapter_plan:
        fm.save_chapter_plan(state.chapter_plan)
    return state


async def execute_phase_chapter_writing(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
    ws_manager,
    project_id: str,
) -> MainState:
    """Execute chapter writing phase with streaming token output."""
    state = await orchestrator.write_chapter(state)
    if state.chapter_draft:
        fm.save_chapter_draft(state.chapter_draft)
    return state


async def execute_phase_review(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute quality review phase."""
    state = await orchestrator.review_chapter(state)
    if state.review_report:
        fm.save_review_report(state.review_report)
    return state


async def execute_phase_polish(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute polish/revision phase."""
    state = await orchestrator.polish_chapter(state)
    if state.polished_chapter:
        fm.save_chapter_markdown(state.polished_chapter)
    return state


async def execute_phase_memory(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute memory update phase."""
    state = await orchestrator.update_memory(state)
    if state.memory:
        fm.save_memory(state.memory)
    return state


# ================================================================
# Phase 0: Commercial Research Pipeline
# ================================================================


async def execute_phase_platform_scan(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Build the scan from the snapshot pinned at workflow start."""
    if state.research_input is None:
        if state.topic_research is None:
            state.topic_research = TopicResearchState()
        return state
    return await orchestrator.scan_platforms(state)


async def execute_phase_topic_selection(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute topic selection phase (Phase 0b).

    Runs cross-platform analysis → benchmark analysis → candidate generation →
    scoring → title/synopsis generation.
    """
    state = await orchestrator.select_topic(state)
    return state


async def execute_phase_mini_arc(
    state: MainState,
    orchestrator: OrchestratorAgent,
    fm: ProjectFileManager,
) -> MainState:
    """Execute mini-arc outline phase (Phase 0c).

    Generates 10-chapter mini-arc outlines for the top 2 selected topics.
    """
    state = await orchestrator.plan_mini_arc(state)
    # Save mini-arc outlines to disk
    if state.mini_arc_outline:
        fm.save_mini_arc_outlines(state.mini_arc_outline)
    return state


# Registry mapping phase names to executor functions
PHASE_EXECUTORS = {
    "platform_scan": execute_phase_platform_scan,
    "topic_selection": execute_phase_topic_selection,
    "mini_arc_outline": execute_phase_mini_arc,
    "bible_construction": execute_phase_bible,
    "character_creation": execute_phase_characters,
    "master_outline": execute_phase_outline,
    "chapter_planning": execute_phase_chapter_planning,
    "chapter_writing": execute_phase_chapter_writing,
    "quality_review": execute_phase_review,
    "polish_revision": execute_phase_polish,
    "memory_update": execute_phase_memory,
}


def get_phase_data(state: MainState, phase: str) -> dict:
    """Extract phase output data for frontend display."""
    source = state.research_input
    if phase == "platform_scan":
        snapshots = []
        for snapshot in source.snapshots if source else ():
            snapshot_data = snapshot.model_dump(mode="json", exclude={"observations"})
            snapshot_data["observations"] = [
                {**story.model_dump(), "story_ref": snapshot.story_ref(story)} for story in snapshot.observations
            ]
            snapshots.append(snapshot_data)
        return {
            "coverage": source.coverage() if source else {},
            "snapshots": snapshots,
            "historical": bool(
                state.topic_research and (state.topic_research.feilu_scan or state.topic_research.fanqie_scan)
            ),
        }
    elif phase == "topic_selection" and state.topic_research:
        research = state.topic_research
        tags = source.english_tags() if source else {}
        historical = not source and bool(research.feilu_scan or research.fanqie_scan)
        data = {
            "coverage": source.coverage() if source else {},
            "shared_tags": {tag: refs for tag, refs in tags.items() if len(refs) == 2},
            "historical": historical,
        }
        if research.cross_platform and source:
            data["cross_platform"] = research.cross_platform.model_dump()
        if research.benchmarks and source:
            data["benchmarks"] = research.benchmarks.model_dump()
        if research.candidates:
            data["candidates"] = research.candidates.model_dump()
        if research.scores and not historical:
            data["scores"] = research.scores.model_dump()
        if research.title_synopsis:
            data["title_synopsis"] = [ts.model_dump() for ts in research.title_synopsis]
        return data
    elif phase == "mini_arc_outline" and state.mini_arc_outline:
        return {"mini_arc_outline": {genre: outline.model_dump() for genre, outline in state.mini_arc_outline.items()}}
    elif phase == "bible_construction" and state.bible:
        return {
            "world": state.bible.world.model_dump(),
            "factions": [f.model_dump() for f in state.bible.factions],
            "themes": [t.model_dump() for t in state.bible.themes],
            "style_contract": state.bible.style_contract.model_dump(),
        }
    elif phase == "character_creation" and state.characters:
        return {
            "characters": {cid: c.model_dump() for cid, c in state.characters.characters.items()},
        }
    elif phase == "master_outline" and state.outline:
        d = state.outline.model_dump()
        d["main_plot"] = [a.model_dump() for a in state.outline.main_plot]
        d["subplots"] = [a.model_dump() for a in state.outline.subplots]
        d["volumes"] = [v.model_dump() for v in state.outline.volumes]
        d["major_turning_points"] = [tp.model_dump() for tp in state.outline.major_turning_points]
        return d
    return {}
