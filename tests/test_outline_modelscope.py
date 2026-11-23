"""Integration test: Outline stage Pydantic validation with ModelScope/Qwen3.

Runs the PlotPlannerAgent.create_master_outline() against ModelScope
and reports any Pydantic validation failures with full tracebacks.

Usage:
    cd E:/projects/novel-agent
    uv run python -m pytest tests/test_outline_modelscope.py -v -s
"""

import asyncio
import logging
import sys
import traceback
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src.agents.plot_planner import PlotPlannerAgent
from src.llm.scheduler import ModelScheduler
from src.models.bible import CoreConflict, Faction, NarrativeRules, NovelBible, StyleContract, Theme, WorldBuilding
from src.models.characters import CharacterProfile, CharacterRegistry
from src.models.outline import MasterOutline
from src.models.project import ProjectConfig

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def scheduler():
    """Create ModelScheduler from .env settings."""
    return ModelScheduler()


@pytest.fixture
def plot_planner(scheduler):
    """Create PlotPlannerAgent."""
    return PlotPlannerAgent(scheduler)


@pytest.fixture
def project_config():
    """Minimal project config for testing."""
    return ProjectConfig(
        title="Test the novel",
        inspiration="The story of a child who accidentally awakens ancient bloodlines and emerges step by step in a world where the weak and the weak eat.",
        genre=["Fantasy", "Cultivation Fantasy", "It's a piece of shit"],
        target_readers="A male reader who likes hot blood to escalate",
        tone="Hot blood",
        target_word_count=90000,
    )


@pytest.fixture
def bible():
    """Minimal novel bible for testing."""
    world = WorldBuilding(
        name="Gentle Continent",
        world_type="fantasy",
        geography="Nine great states, the center of which is holy land, and the Quarters of which is a wilderness",
        history="A thousand years ago, after the Great War of the Dynasty, the spirit of the world was thin and the civilization was deformed",
        culture="It's all about strength, and it's all about the fundamentals",
        technology_level="True civilization. Human beings are in feudal times",
        magic_system="Realization system: →, building base →, Kimdan, baby →, baby →, chemical God, →, →, taking → to the beach",
        power_progression="It's a nine-storey border",
    )
    factions = [
        Faction(
            name="Green Yunzong",
            faction_type="sect",
            goal="Build a true man and maintain the right path",
            resources="Psychic veins, hidden in the loft, in the purgatory",
        ),
        Faction(
            name="Heavenly Demon Sect",
            faction_type="cult",
            goal="To overthrow the rule of the right path and seize the heart of the heavens and earth",
            resources="A source of magic, a group of assassins",
        ),
    ]
    style = StyleContract(
        tone="Hot blood",
        pacing_preference="fast",
        sentence_style="varied",
        dialogue_ratio=0.35,
        description_ratio=0.25,
    )
    themes = [
        Theme(name="Growth Against the Odds", description="The lead is moving from wastewood to the top"),
        Theme(name="Friendship and betrayal", description="Allies and enemies on the path to the truth"),
    ]
    conflicts = [
        CoreConflict(
            conflict_type="person_vs_society",
            description="The main character was abandoned by the family and proved himself in the court",
            stakes="Survival and dignity",
        ),
        CoreConflict(
            conflict_type="person_vs_person",
            description="The final rivalry between the protagonist and the enemy",
            stakes="There's a fight in the streets",
        ),
    ]
    return NovelBible(
        world=world,
        factions=factions,
        rules=NarrativeRules(),
        style_contract=style,
        themes=themes,
        core_conflicts=conflicts,
        pleasure_point_model="One small orgasm for every 10 chapters: breaking the border, beating the face, getting the chance",
    )


@pytest.fixture
def characters():
    """Minimal character registry."""
    return CharacterRegistry(
        characters={
            "char_001": CharacterProfile(
                id="char_001",
                name="Qin Mo",
                role="protagonist",
                personality="Strong, well-thought-out, sometimes too risky",
                motivation="Breaking the shackles of fate and becoming the strongest of true men",
                flaw="Too stubborn to trust people",
                backstory="Qin's family is a natural waste of life and is exiled by the family to a remote mine",
            ),
            "char_002": CharacterProfile(
                id="char_002",
                name="Su Wanqing",
                role="deuteragonist",
                personality="It's cold, it's hot, it's smart",
                motivation="Looking for a teacher who's been separated for years",
                flaw="I'm not good at expressing feelings",
                backstory="It's only been the first day, and it's a mystery",
            ),
        }
    )


# ── Test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_master_outline(plot_planner, project_config, bible, characters):
    """Execute the full master outline creation against ModelScope.

    This is the main test — it will surface any Pydantic validation
    errors that Qwen3's output causes.
    """
    print("\n" + "=" * 70)
    print("Testing create_master_outline() against ModelScope...")
    print("=" * 70)

    try:
        outline = await plot_planner.create_master_outline(
            config=project_config,
            bible=bible,
            characters=characters,
        )
    except Exception as e:
        print("\n" + "!" * 70)
        print(f"FAILED: {type(e).__name__}: {e}")
        print("!" * 70)
        traceback.print_exc()
        pytest.fail(f"create_master_outline raised {type(e).__name__}: {e}")
        return

    # ── Validate the result ──
    assert isinstance(outline, MasterOutline), f"Expected MasterOutline, got {type(outline).__name__}"
    assert outline.title, "Title must not be empty"
    print(f"\n[OK] Title: {outline.title}")
    print(f"[OK] Logline: {outline.logline[:100]}...")
    print(f"[OK] Volumes: {len(outline.volumes)}")
    for v in outline.volumes:
        print(f"  - Vol {v.number}: {v.title} (ch {v.start_chapter}-{v.end_chapter})")
    print(f"[OK] Main plots: {len(outline.main_plot)}")
    for p in outline.main_plot:
        print(f"  - {p.name}: {p.description[:80]}...")
    print(f"[OK] Subplots: {len(outline.subplots)}")
    for p in outline.subplots:
        print(f"  - {p.name}: {p.description[:80]}...")
    print(f"[OK] Turning points: {len(outline.major_turning_points)}")
    for tp in outline.major_turning_points:
        print(f"  - [{tp.turning_type}] ch{tp.chapter}: {tp.description[:80]}...")
    print(f"[OK] Chapter count: {outline.chapter_count}")

    # ── Structural assertions ──
    assert len(outline.main_plot) >= 1, "Must have at least 1 main plot arc"
    assert len(outline.volumes) >= 1, "Must have at least 1 volume"
    assert len(outline.major_turning_points) >= 2, "Must have at least 2 turning points"
    assert outline.chapter_count >= 5, "Must plan at least 5 chapters"

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED")
    print("=" * 70)


# ── Pydantic model unit tests (no LLM calls) ───────────────────────


class TestMasterOutlineValidation:
    """Test Pydantic validation with various malformed inputs Qwen3 might produce."""

    def test_string_turning_points(self):
        """Turning points as plain strings should be coerced."""
        from src.agents.plot_planner import MasterOutlineOutput

        data = {
            "title": "Test the novel",
            "logline": "A test story",
            "main_plot": [
                {"name": "Main Plot", "description": "The protagonist's growth"},
            ],
            "subplots": [],
            "volumes": [
                {"title": "Volume I", "start_chapter": 1, "end_chapter": 10},
            ],
            "major_turning_points": [
                "The hero's unexpectedly inherited",  # plain string!
                "The hero beats the first enemy",
            ],
            "chapter_count": 15,
        }
        result = MasterOutlineOutput.model_validate(data)
        assert len(result.major_turning_points) == 2
        assert result.major_turning_points[0].description == "The hero's unexpectedly inherited"
        assert result.major_turning_points[1].description == "The hero beats the first enemy"

    def test_string_plot_arcs(self):
        """Plot arcs as plain strings should be coerced."""
        from src.agents.plot_planner import MasterOutlineOutput

        data = {
            "title": "Test the novel",
            "logline": "A test story",
            "main_plot": [
                "The main character is from a loser to a strong man",  # plain string!
            ],
            "subplots": [
                "Loveline",  # plain string!
            ],
            "volumes": [
                {"title": "Volume I", "start_chapter": 1, "end_chapter": 10},
            ],
            "major_turning_points": [],
            "chapter_count": 15,
        }
        result = MasterOutlineOutput.model_validate(data)
        assert len(result.main_plot) == 1
        assert result.main_plot[0].description == "The main character is from a loser to a strong man"
        assert len(result.subplots) == 1
        assert result.subplots[0].description == "Loveline"

    def test_volume_string_chapter_numbers(self):
        """Volume start/end chapter as strings should be coerced by Pydantic."""
        data = {
            "title": "Test the novel",
            "logline": "Test",
            "main_plot": [],
            "subplots": [],
            "volumes": [
                {"title": "Volume I", "start_chapter": "1", "end_chapter": "10"},
            ],
            "major_turning_points": [],
            "chapter_count": 15,
        }
        from src.agents.plot_planner import MasterOutlineOutput

        result = MasterOutlineOutput.model_validate(data)
        assert result.volumes[0].start_chapter == 1
        assert result.volumes[0].end_chapter == 10

    def test_turning_point_chinese_type_key(self):
        """TurningPoint with The type key should be mapped to turning_type."""
        from src.models.outline import TurningPoint

        # Qwen might output "type" in English, which TurningPoint already handles
        data = {"type": "inciting_incident", "chapter": 1, "description": "The protagonist awakens"}
        result = TurningPoint.model_validate(data)
        assert result.turning_type == "inciting_incident"

    def test_plot_arc_chinese_keys(self):
        """Recognize the arc alias for a plot arc name."""
        from src.models.outline import PlotArc

        data = {"arc": "Protagonist Arc", "description": "The protagonist grows", "start_chapter": 1, "end_chapter": 30}
        result = PlotArc.model_validate(data)
        assert result.name == "Protagonist Arc"

    def test_emotional_beat_intensity_clamp(self):
        """EmotionalBeat intensity 0-10 scale should be clamped to 0-1."""
        from src.models.outline import EmotionalBeat

        data = {"position": 0.5, "emotion": "Excitement", "intensity": 8}
        result = EmotionalBeat.model_validate(data)
        assert result.intensity == 0.8

    def test_emotional_beat_intensity_string(self):
        """EmotionalBeat intensity as string should be parsed."""
        from src.models.outline import EmotionalBeat

        data = {"position": 0.5, "emotion": "Excited", "intensity": "0.7"}
        result = EmotionalBeat.model_validate(data)
        assert result.intensity == 0.7

    def test_hook_plain_string(self):
        """Hook as plain string should be coerced to description."""
        from src.models.outline import Hook

        result = Hook.model_validate("The main character found a hidden cave")
        assert result.description == "The main character found a hidden cave"
        assert result.hook_type == "cliffhanger"

    def test_scene_plain_string(self):
        """Scene as plain string should be coerced."""
        from src.models.outline import Scene

        result = Scene.model_validate("Azure Cloud Sect Square: The protagonist takes the entrance exam")
        assert result.setting == "Azure Cloud Sect Square"
        assert "entrance exam" in result.goal

    def test_empty_lists_accepted(self):
        """All empty lists should be accepted without issues."""
        from src.agents.plot_planner import MasterOutlineOutput

        data = {
            "title": "Empty Test",
            "logline": "",
            "main_plot": [],
            "subplots": [],
            "volumes": [],
            "major_turning_points": [],
            "chapter_count": 0,
        }
        result = MasterOutlineOutput.model_validate(data)
        assert result.title == "Empty Test"
        assert result.chapter_count == 0

    def test_volume_with_introduction_alias(self):
        """Volume with 'introduction' key should map to logline."""
        from src.models.outline import Volume

        data = {
            "title": "Volume I",
            "introduction": "From family abandonment to the growth of my disciples",
            "start_chapter": 1,
            "end_chapter": 10,
        }
        result = Volume.model_validate(data)
        assert result.logline == "From family abandonment to the growth of my disciples"

    def test_volume_with_key_events_alias(self):
        """Volume with 'key_events' key should map to major_events."""
        from src.models.outline import Volume

        data = {
            "title": "Volume I",
            "key_events": ["Blood and blood awakening", "Zongmen's exam", "The first battle is a big one"],
            "start_chapter": 1,
            "end_chapter": 10,
        }
        result = Volume.model_validate(data)
        assert len(result.major_events) == 3
        assert result.major_events[0] == "Blood and blood awakening"

    def test_plot_arc_auto_name_from_description(self):
        """PlotArc with no name should derive from description."""
        from src.models.outline import PlotArc

        data = {
            "type": "subplot",
            "description": "Su Wanqing searches for her missing mentor",
        }
        result = PlotArc.model_validate(data)
        assert result.name == data["description"][:20]
        assert result.arc_type == "subplot"

    def test_plot_arc_auto_name_from_arc_type(self):
        """PlotArc with no name and no description should derive from arc_type."""
        from src.models.outline import PlotArc

        data = {
            "type": "b_plot",
        }
        result = PlotArc.model_validate(data)
        assert result.name == "Secondary Plot"
        assert result.arc_type == "b_plot"

    def test_volume_strings_in_output(self):
        """Volumes as plain strings should be coerced to Volume dicts."""
        from src.agents.plot_planner import MasterOutlineOutput

        data = {
            "title": "Test the novel",
            "logline": "Test Story",
            "main_plot": [],
            "subplots": [],
            "volumes": [
                "Volume 1: Awakening in the Wasteland",
                "Volume 2: The Blood Pact",
            ],
            "major_turning_points": [],
            "chapter_count": 20,
        }
        result = MasterOutlineOutput.model_validate(data)
        assert len(result.volumes) == 2
        assert result.volumes[0].title == "Awakening in the Wasteland"
        assert result.volumes[0].number == 1
        assert result.volumes[0].start_chapter == 1
        assert result.volumes[0].end_chapter == 10
        assert result.volumes[1].title == "The Blood Pact"
        assert result.volumes[1].number == 2
        assert result.volumes[1].start_chapter == 11
        assert result.volumes[1].end_chapter == 20

    def test_volume_string_no_chapter_prefix(self):
        """Volume string without chapter prefix should use full string as title."""
        from src.agents.plot_planner import MasterOutlineOutput

        data = {
            "title": "Test",
            "logline": "Test",
            "main_plot": [],
            "subplots": [],
            "volumes": ["Wake up", "Growing", "Top of the line"],
            "major_turning_points": [],
            "chapter_count": 30,
        }
        result = MasterOutlineOutput.model_validate(data)
        assert len(result.volumes) == 3
        assert result.volumes[0].title == "Wake up"
        assert result.volumes[0].number == 1
        assert result.volumes[1].title == "Growing"
        assert result.volumes[1].number == 2


# ── Test ChapterPlanOutput validation ───────────────────────────────


class TestChapterPlanValidation:
    """Test ChapterPlanOutput validation with malformed inputs."""

    def test_emotional_curve_intensity_clamp(self):
        """ChapterPlanOutput should clamp intensities from 0-10 scale."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Building a world view",
            "scenes": [],
            "pov_character": "char_001",
            "conflict": "Test Conflict",
            "emotional_curve": [
                {"position": 0.0, "emotion": "Calm down", "intensity": 3},
                {"position": 0.5, "emotion": "Nervous", "intensity": 8},
                {"position": 1.0, "emotion": "Excited", "intensity": 9},
            ],
            "ending_hook": "End of Suspended",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert result.emotional_curve[0].intensity == 0.3
        assert result.emotional_curve[1].intensity == 0.8
        assert result.emotional_curve[2].intensity == 0.9

    def test_scene_list_with_strings(self):
        """Scenes as mixed strings and dicts."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Test",
            "scenes": [
                "Refinery: The lead is breaking through",
                {"setting": "Zongmen Palace", "goal": "Take the task", "conflict": "Some question the main character"},
            ],
            "pov_character": "char_001",
            "conflict": "Test",
            "emotional_curve": [],
            "ending_hook": "",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert len(result.scenes) == 2
        assert result.scenes[0].setting == "Refinery"
        assert result.scenes[1].setting == "Zongmen Palace"

    def test_emotional_curve_string_items(self):
        """Emotional curve items as strings should be parsed to dicts."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Test",
            "scenes": [],
            "pov_character": "char_001",
            "conflict": "Test",
            "emotional_curve": [
                "Oppression, intensity 0.9",
                "Anger, intensity 0.7",
                "Tension, intensity 0.95",
                "Surprise, intensity 0.85",
                "Resolve, intensity 0.8",
            ],
            "ending_hook": "",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert len(result.emotional_curve) == 5
        assert result.emotional_curve[0].emotion == "Oppression"
        assert result.emotional_curve[0].intensity == 0.9  # Already in 0-1 scale
        assert result.emotional_curve[2].emotion == "Tension"
        assert result.emotional_curve[2].intensity == 0.95

    def test_emotional_curve_string_wrong(self):
        """Emotional curve string items with 0-10 scale should be clamped."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Test",
            "scenes": [],
            "pov_character": "char_001",
            "conflict": "Test",
            "emotional_curve": [
                "Calm, intensity 3",
                "Tension, intensity 8",
                "Excitement, intensity 9",
            ],
            "ending_hook": "",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert result.emotional_curve[0].intensity == 0.3
        assert result.emotional_curve[1].intensity == 0.8
        assert result.emotional_curve[2].intensity == 0.9

    def test_emotional_curve_dict_with_parenthesized_intensity(self):
        """Extract a parenthesized intensity from the emotion field."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Test",
            "scenes": [],
            "pov_character": "char_001",
            "conflict": "Test",
            "emotional_curve": [
                {"position": 0.0, "emotion": "Oppression (intensity 0.9)"},
                {"position": 0.3, "emotion": "Concern (intensity 0.7)"},
                {"position": 0.5, "emotion": "Tension (intensity 0.85)"},
            ],
            "ending_hook": "",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert len(result.emotional_curve) == 3
        assert result.emotional_curve[0].emotion == "Oppression"
        assert result.emotional_curve[0].intensity == 0.9

    def test_emotional_curve_string_parenthesized(self):
        """String items with parenthesized intensity should be parsed."""
        from src.agents.plot_planner import ChapterPlanOutput

        data = {
            "chapter_number": 1,
            "title": "Chapter I",
            "goal": "Test",
            "scenes": [],
            "pov_character": "char_001",
            "conflict": "Test",
            "emotional_curve": [
                "Oppression (intensity 0.9)",
                "Anger (intensity 0.7)",
            ],
            "ending_hook": "",
            "word_count_target": 3000,
        }
        result = ChapterPlanOutput.model_validate(data)
        assert result.emotional_curve[0].emotion == "Oppression"
        assert result.emotional_curve[0].intensity == 0.9


# ── Chapter Planning Integration Test ────────────────────────────────


@pytest.mark.asyncio
async def test_plan_chapter(plot_planner, project_config, bible, characters):
    """Test chapter-level planning against ModelScope.

    This requires a MasterOutline first, then plans chapter 1.
    """
    print("\n" + "=" * 70)
    print("Step 1: Creating master outline...")
    print("=" * 70)

    try:
        outline = await plot_planner.create_master_outline(
            config=project_config,
            bible=bible,
            characters=characters,
        )
        print(f"[OK] Outline: {outline.title}, {outline.chapter_count} chapters")
    except Exception as e:
        print(f"[FAIL] Master outline failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        pytest.fail(f"Master outline failed: {e}")
        return

    print("\n" + "=" * 70)
    print("Step 2: Planning chapter 1...")
    print("=" * 70)

    try:
        plan = await plot_planner.plan_chapter(
            chapter_number=1,
            config=project_config,
            bible=bible,
            characters=characters,
            outline=outline,
        )
    except Exception as e:
        print(f"[FAIL] Chapter planning failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        pytest.fail(f"plan_chapter raised {type(e).__name__}: {e}")
        return

    # Validate
    print(f"[OK] Chapter title: {plan.title}")
    print(f"[OK] Goal: {plan.goal[:100]}...")
    print(f"[OK] Scenes: {len(plan.scenes)}")
    for i, scene in enumerate(plan.scenes):
        print(f"  Scene {i + 1}: {scene.setting} | goal={scene.goal[:40]}...")
    print(f"[OK] POV: {plan.pov_character}")
    print(f"[OK] Conflict: {plan.conflict[:80]}...")
    print(f"[OK] Hooks: {len(plan.hooks)}")
    for h in plan.hooks:
        print(f"  - [{h.hook_type}] {h.description[:60]}...")
    print(f"[OK] Characters involved: {plan.characters_involved}")
    print(f"[OK] Info increment: {plan.information_increment[:80]}...")
    print(f"[OK] Reveals: {plan.reveals}")
    print(f"[OK] Foreshadowing: {plan.foreshadowing}")
    print(f"[OK] Emotional curve: {len(plan.emotional_curve)} beats")
    for beat in plan.emotional_curve:
        print(f"  - pos={beat.position:.2f} {beat.emotion} intensity={beat.intensity:.2f}")
    print(f"[OK] Ending hook: {plan.ending_hook[:80]}...")
    print(f"[OK] Word count target: {plan.word_count_target}")

    assert plan.title, "Chapter must have a title"
    assert len(plan.scenes) >= 1, "Must have at least 1 scene"
    assert plan.goal, "Must have a goal"
    assert plan.conflict, "Must have a conflict"

    print("\n" + "=" * 70)
    print("CHAPTER PLANNING TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    # Allow running directly for debugging
    async def main():
        logging.basicConfig(level=logging.DEBUG)
        s = ModelScheduler()
        pp = PlotPlannerAgent(s)

        pc = ProjectConfig(
            title="Test the novel",
            inspiration="The story of a child who accidentally awakens ancient bloodlines and emerges step by step in a world where the weak and the weak eat.",
            genre=["Fantasy", "Cultivation Fantasy", "It's a piece of shit"],
            target_readers="A male reader who likes hot blood to escalate",
            tone="Hot blood",
            target_word_count=90000,
        )

        world = WorldBuilding(
            name="Gentle Continent",
            world_type="fantasy",
            geography="Nine States",
            history="A thousand years ago, the War of the Wonders",
            culture="It's all about strength",
            magic_system="Truth system",
        )
        bible = NovelBible(
            world=world,
            factions=[
                Faction(name="Green Yunzong", faction_type="sect", goal="Keep it straight"),
                Faction(name="Heavenly Demon Sect", faction_type="cult", goal="Overthrow the orthodox sects"),
            ],
            rules=NarrativeRules(),
            style_contract=StyleContract(tone="Hot blood"),
            themes=[Theme(name="Growth Against the Odds"), Theme(name="Friendship and betrayal")],
            core_conflicts=[
                CoreConflict(conflict_type="person_vs_society", description="The main character was abandoned by the family"),
                CoreConflict(conflict_type="person_vs_person", description="The main character and Hsing are fighting each other"),
            ],
        )
        chars = CharacterRegistry(
            characters={
                "char_001": CharacterProfile(
                    id="char_001",
                    name="Qin Mo",
                    role="protagonist",
                    personality="You're tough",
                    motivation="Be the strongest",
                    flaw="Too stubborn",
                    backstory="Exiled by the family",
                ),
            }
        )

        print("Calling create_master_outline...")
        try:
            outline = await pp.create_master_outline(pc, bible, chars)
            print(f"SUCCESS: {outline.title}")
            print(outline.model_dump_json(indent=2))
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

    asyncio.run(main())
