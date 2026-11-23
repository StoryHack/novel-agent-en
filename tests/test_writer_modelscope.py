"""Integration test: Phase 5 Chapter Writing with ModelScope/Qwen3.

Runs WriterAgent.generate_chapter() and extract_facts_and_changes()
against ModelScope and reports any Pydantic validation failures.

Usage:
    cd E:/projects/novel-agent
    uv run python -m pytest tests/test_writer_modelscope.py -v -s
"""

import asyncio
import logging
import sys
import traceback
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src.agents.writer import ChapterContentOutput, FactExtractionOutput, WriterAgent
from src.llm.scheduler import ModelScheduler
from src.models.bible import (
    CoreConflict,
    Faction,
    NarrativeRules,
    NovelBible,
    StyleContract,
    Theme,
    WorldBuilding,
)
from src.models.chapter import ChapterDraft
from src.models.characters import CharacterProfile, CharacterRegistry
from src.models.memory import MemoryState
from src.models.outline import (
    ChapterPlan,
    EmotionalBeat,
    Hook,
    MasterOutline,
    PlotArc,
    Scene,
    TurningPoint,
    Volume,
)
from src.models.project import ProjectConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def scheduler():
    """Create ModelScheduler from .env settings."""
    return ModelScheduler()


@pytest.fixture
def writer(scheduler):
    """Create WriterAgent."""
    return WriterAgent(scheduler)


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
        name="Azure Continent",
        world_type="fantasy",
        geography="Nine great states, the center of which is holy land, and the Quarters of which is a wilderness",
        history="A thousand years ago, after the Great War of the Dynasty, the spirit of the world was thin and the civilization was deformed",
        culture="It's all about strength, and it's all about the fundamentals",
        technology_level="True civilization. Human beings are in feudal times",
        magic_system="Realization system: →, building base →, Kimdan, baby →, baby →, chemical God, →, →, taking → to the beach",
        power_progression="It's a nine-storey border",
    )
    factions = [
        Faction(name="Green Yunzong", faction_type="sect", goal="Build a true man and maintain the right path", resources="Psychic veins, hidden in the loft"),
        Faction(name="Heavenly Demon Sect", faction_type="cult", goal="To overthrow the rule of the right path and seize the heart of the heavens and earth", resources="A source of magic, a group of assassins"),
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
            conflict_type="person_vs_society", description="The main character was abandoned by the family and proved himself in the court", stakes="Survival and dignity"
        ),
        CoreConflict(conflict_type="person_vs_person", description="The final rivalry between the protagonist and the enemy", stakes="There's a fight in the streets"),
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
            "char_003": CharacterProfile(
                id="char_003",
                name="Zhao Tieshan",
                role="antagonist",
                personality="Proud and narrow-minded",
                motivation="To defend his position and authority in the kingdom",
                flaw="Jealousy is too strong to allow others to outdo themselves",
                backstory="Azure Cloud Sect-nemen is a student of high self-esteem",
            ),
        }
    )


@pytest.fixture
def outline():
    """Minimal master outline for testing."""
    return MasterOutline(
        title="I'm not going anywhere",
        logline="Qin, a child who is a waste of wood, awakens the ancient veins and rises to the top in a world where the weak and the weak have to eat.",
        main_plot=[
            PlotArc(
                name="Main Plot", description="Qin Mo's path from wastewood to strong men", arc_type="main", start_chapter=1, end_chapter=30
            ),
        ],
        subplots=[
            PlotArc(
                name="Su Wan Qing Qing Qing lines",
                description="Su Wanqing is looking for a line of inquiry for the separated master",
                arc_type="subplot",
                start_chapter=3,
                end_chapter=20,
            ),
        ],
        volumes=[
            Volume(
                title="Volume I: Wake-up of wastewood",
                logline="From the family's abandonment to the transformation of my disciples,",
                number=1,
                start_chapter=1,
                end_chapter=10,
            ),
        ],
        major_turning_points=[
            TurningPoint(turning_type="inciting_incident", chapter=1, description="Qin Mo accidentally acquired an ancient blood line in the mine"),
            TurningPoint(turning_type="midpoint", chapter=15, description="Qinmu's famous in the First World War"),
        ],
        chapter_count=30,
    )


@pytest.fixture
def chapter_plan():
    """Minimal but realistic chapter plan for Chapter 1."""
    return ChapterPlan(
        chapter_number=1,
        title="The Boy Who Could Not Cultivate",
        goal="Create the characters' dilemmas and the world context, make the readers feel for the protagonists, and look forward to a turn of events",
        scenes=[
            Scene(
                number=1,
                setting="Qin mine - midday",
                pov="char_001",
                characters_present=["char_001"],
                goal="Showing Qinmeo's humble place in the family",
                conflict="The scoffing of other miners and the oppression of supervisors",
                outcome="Qin Meer has endured it, but he's got a flash in his eyes",
            ),
            Scene(
                number=2,
                setting="Deep in the mine - evening",
                pov="char_001",
                characters_present=["char_001"],
                goal="There's an unusual mine",
                conflict="The mine collapsed and Qin Mo was trapped",
                outcome="In the end, we found a strange crystal that was reeking of ancient air",
            ),
            Scene(
                number=3,
                setting="Deep in the mine - night",
                pov="char_001",
                characters_present=["char_001"],
                goal="Activate ancient bloodlines",
                conflict="The force in the crystals is pouring into his body, and his body is almost torn apart by severe pain",
                outcome="Qin Mo has successfully integrated his ancient bloodline and felt the power he has never seen before",
            ),
        ],
        pov_character="char_001",
        conflict="Qin Mo's humble position in the family is in conflict with his own heart; the physical pain of the awakening of ancient blood",
        hooks=[
            Hook(hook_type="cliffhanger", description="When Qin Mo's veins awakened, an old voice sounded in his mind..."),
        ],
        characters_involved=["char_001"],
        information_increment="The creation of a world view (required system, status of the Qin family) and the introduction of the main character's dilemma, which reveals the existence of ancient bloodlines",
        reveals=["Qin Mo's blood is hidden in ancient blood"],
        foreshadowing=["It's a sign of ancient blood", "Qin's relationship with Qin's family"],
        emotional_curve=[
            EmotionalBeat(position=0.0, emotion="Repression", intensity=0.7),
            EmotionalBeat(position=0.3, emotion="Struggle", intensity=0.6),
            EmotionalBeat(position=0.6, emotion="Despair", intensity=0.8),
            EmotionalBeat(position=0.8, emotion="Pain", intensity=0.9),
            EmotionalBeat(position=1.0, emotion="Stunny", intensity=0.95),
        ],
        ending_hook="When Qin Mo's veins awakened, an old and powerful voice sounded in his mind: 'Twilight years ... finally wait for you'",
        word_count_target=4000,
    )


@pytest.fixture
def memory():
    """Empty memory state for first chapter."""
    return MemoryState()


# ═══════════════════════════════════════════════════════════════════════
# Pydantic Unit Tests: ChapterContentOutput
# ═══════════════════════════════════════════════════════════════════════


class TestChapterContentOutput:
    """Test ChapterContentOutput validation with malformed Qwen3 inputs."""

    def test_valid_output(self):
        """Normal valid output should pass."""
        data = {
            "title": "The Boy Who Could Not Cultivate",
            "content": "## Chapter 1\n\nQin Mo labored in a mine beneath the Azure Continent.\n\n",
            "author_notes": "Chapter I focuses on the plight of the protagonists and the world view",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.title == "The Boy Who Could Not Cultivate"
        assert "Azure Continent" in result.content
        assert result.author_notes

    def test_missing_author_notes(self):
        """Missing author_notes should default to empty string."""
        data = {
            "title": "Chapter I",
            "content": "Text",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.author_notes == ""

    def test_notes_alias(self):
        """'notes' key should map to author_notes."""
        data = {
            "title": "Chapter I",
            "content": "Chapter Text",
            "notes": "This is the author's note",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.author_notes == "This is the author's note"

    def test_description_alias(self):
        """'description' key should map to author_notes."""
        data = {
            "title": "Chapter 1",
            "content": "Chapter text",
            "description": "Chapter description",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.author_notes == "Chapter description"

    def test_chinese_notes_alias(self):
        """Chinese '备注' key should map to author_notes."""
        data = {
            "title": "Chapter 1",
            "content": "Chapter text",
            "备注": "Author note",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.author_notes == "Author note"

    def test_chinese_attached_alias(self):
        """Chinese '附注' key should map to author_notes."""
        data = {
            "title": "Chapter 1",
            "content": "Chapter text",
            "附注": "Author note",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.author_notes == "Author note"

    def test_chinese_body_alias(self):
        """Chinese '正文' key should map to content."""
        data = {
            "title": "Chapter 1",
            "正文": "Chapter text",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.content == "Chapter text"

    def test_text_alias(self):
        """'text' key should map to content."""
        data = {
            "title": "Chapter 1",
            "text": "Text Contents",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.content == "Text Contents"

    def test_empty_content_fallback(self):
        """Empty content with body alias should still work."""
        data = {
            "title": "Chapter I",
            "content": "",
            "body": "The truth is here",
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.content == "The truth is here"

    def test_all_empty(self):
        """All empty fields should still validate."""
        data = {}
        result = ChapterContentOutput.model_validate(data)
        assert result.title == ""
        assert result.content == ""
        assert result.author_notes == ""

    def test_extra_fields_ignored(self):
        """Extra unknown fields should be ignored by Pydantic."""
        data = {
            "title": "Chapter I",
            "content": "Chapter Text",
            "extra_field": "should be ignored",
            "another_extra": 123,
        }
        result = ChapterContentOutput.model_validate(data)
        assert result.title == "Chapter I"


# ═══════════════════════════════════════════════════════════════════════
# Pydantic Unit Tests: FactExtractionOutput
# ═══════════════════════════════════════════════════════════════════════


class TestFactExtractionOutput:
    """Test FactExtractionOutput validation with malformed Qwen3 inputs."""

    def test_valid_empty_output(self):
        """Valid but empty output."""
        data = {"new_facts": [], "state_changes": []}
        result = FactExtractionOutput.model_validate(data)
        assert result.new_facts == []
        assert result.state_changes == []

    def test_valid_with_facts(self):
        """Valid output with facts."""
        data = {
            "new_facts": [
                {
                    "id": "fact_001",
                    "category": "world",
                    "description": "Mankind is at the bottom of society",
                    "certainty": 1.0,
                    "source_chapter": 1,
                },
                {
                    "id": "fact_002",
                    "category": "character",
                    "description": "Qin Mo was born with no blood. He was exiled by his family to the mines",
                    "certainty": 1.0,
                    "source_chapter": 1,
                },
            ],
            "state_changes": [
                {
                    "character_id": "char_001",
                    "attribute": "physical.power",
                    "old_value": "Man (Waste veins)",
                    "new_value": "Gas layer (awakening of ancient blood veins)",
                    "reason": "It's the crystal that unites the ancient blood veins",
                },
            ],
        }
        result = FactExtractionOutput.model_validate(data)
        assert len(result.new_facts) == 2
        assert result.new_facts[0].category == "world"
        assert len(result.state_changes) == 1

    def test_state_changes_as_strings(self):
        """State changes as plain strings should be coerced to dicts."""
        data = {
            "new_facts": [],
            "state_changes": [
                "Qin awakened his ancient blood",
                "Qin Mo's renovation was from mortals to gas",
            ],
        }
        result = FactExtractionOutput.model_validate(data)
        assert len(result.state_changes) == 2
        assert result.state_changes[0].reason == "Qin awakened his ancient blood"
        assert result.state_changes[1].reason == "Qin Mo's renovation was from mortals to gas"

    def test_new_facts_as_strings(self):
        """New facts as plain strings should be coerced to dicts (via Fact validator)."""
        data = {
            "new_facts": [
                "Cultivators hold the highest status on the Azure Continent.",
                "Qin Mo was exiled because he was born unable to cultivate.",
            ],
            "state_changes": [],
        }
        result = FactExtractionOutput.model_validate(data)
        assert len(result.new_facts) == 2
        assert result.new_facts[0].description == "Cultivators hold the highest status on the Azure Continent."
        assert result.new_facts[1].description == "Qin Mo was exiled because he was born unable to cultivate."

    def test_facts_with_chinese_keys(self):
        """Facts with Chinese keys should be normalized."""
        data = {
            "new_facts": [
                {"描述": "A test fact", "类别": "world", "确定性": 0.8},
            ],
            "state_changes": [],
        }
        result = FactExtractionOutput.model_validate(data)
        assert len(result.new_facts) == 1
        assert result.new_facts[0].description == "A test fact"
        assert result.new_facts[0].category == "world"
        assert result.new_facts[0].certainty == 0.8

    def test_mixed_valid_and_string_items(self):
        """Mixed valid dicts and string items should both work."""
        data = {
            "new_facts": [
                {"category": "plot", "description": "A plot fact"},
                "Another fact",
            ],
            "state_changes": [
                {"character_id": "char_001", "reason": "Routine change"},
                "The character changed",
            ],
        }
        result = FactExtractionOutput.model_validate(data)
        assert len(result.new_facts) == 2
        assert result.new_facts[0].category == "plot"
        assert result.new_facts[1].description == "Another fact"
        assert len(result.state_changes) == 2
        assert result.state_changes[0].character_id == "char_001"
        assert result.state_changes[1].reason == "The character changed"


# ═══════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_chapter(writer, project_config, bible, characters, outline, chapter_plan, memory):
    """Execute chapter generation against ModelScope.

    This is the main test — it surfaces Pydantic validation errors from Qwen3 output.
    """
    print("\n" + "=" * 70)
    print("Phase 5: Testing generate_chapter() against ModelScope...")
    print("=" * 70)

    try:
        draft = await writer.generate_chapter(
            chapter_plan=chapter_plan,
            config=project_config,
            bible=bible,
            characters=characters,
            outline=outline,
            memory=memory,
        )
    except Exception as e:
        print("\n" + "!" * 70)
        print(f"FAILED: {type(e).__name__}: {e}")
        print("!" * 70)
        traceback.print_exc()
        pytest.fail(f"generate_chapter raised {type(e).__name__}: {e}")
        return

    # ── Validate the result ──
    assert isinstance(draft, ChapterDraft), f"Expected ChapterDraft, got {type(draft).__name__}"
    assert draft.chapter_number == 1, f"Expected chapter 1, got {draft.chapter_number}"
    assert draft.title, "Title must not be empty"
    assert draft.content, "Content must not be empty"
    assert draft.word_count > 0, "Word count must be positive"

    print(f"\n[OK] Title: {draft.title}")
    print(f"[OK] Word count: {draft.word_count}")
    print(f"[OK] Content preview ({len(draft.content)} chars):")
    print(f"    {draft.content[:300]}...")
    if draft.author_notes:
        print(f"[OK] Author notes: {draft.author_notes[:100]}...")

    # ── Content quality checks ──
    content_len = len(draft.content)
    print(f"\n[INFO] Content length: {content_len} chars")
    if content_len < 500:
        print("[WARN] Content is very short — Qwen3 may have truncated output")
    if content_len > 200:
        print("[OK] Content has reasonable length")

    print("\n" + "=" * 70)
    print("CHAPTER GENERATION TEST PASSED")
    print("=" * 70)


@pytest.mark.asyncio
async def test_extract_facts(writer, project_config, bible, characters, outline, chapter_plan, memory):
    """Test fact extraction from a generated chapter.

    First generates a chapter, then extracts facts from it.
    """
    print("\n" + "=" * 70)
    print("Step 1: Generating chapter for fact extraction test...")
    print("=" * 70)

    try:
        draft = await writer.generate_chapter(
            chapter_plan=chapter_plan,
            config=project_config,
            bible=bible,
            characters=characters,
            outline=outline,
            memory=memory,
        )
        print(f"[OK] Generated: {draft.title} ({draft.word_count} chars)")
    except Exception as e:
        traceback.print_exc()
        pytest.fail(f"generate_chapter: {type(e).__name__}: {e}")
        return

    print("\n" + "=" * 70)
    print("Step 2: Extracting facts and state changes...")
    print("=" * 70)

    try:
        draft = await writer.extract_facts_and_changes(
            draft=draft,
            bible=bible,
            characters=characters,
        )
    except Exception as e:
        print("\n" + "!" * 70)
        print(f"FAILED: {type(e).__name__}: {e}")
        print("!" * 70)
        traceback.print_exc()
        pytest.fail(f"extract_facts_and_changes raised {type(e).__name__}: {e}")
        return

    print(f"[OK] New facts extracted: {len(draft.new_facts)}")
    for fact in draft.new_facts:
        print(f"  - [{fact.category}] {fact.description[:80]}... (certainty={fact.certainty})")

    print(f"[OK] State changes: {len(draft.character_state_changes)}")
    for sc in draft.character_state_changes:
        print(f"  - {sc.character_id}: {sc.attribute} {sc.old_value} → {sc.new_value}")
        print(f"    Reason: {sc.reason[:80]}")

    # Validation
    assert isinstance(draft.new_facts, list), "new_facts must be a list"
    assert isinstance(draft.character_state_changes, list), "state_changes must be a list"

    print("\n" + "=" * 70)
    print("FACT EXTRACTION TEST PASSED")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════
# Standalone runner (for debugging without pytest)
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def main():
        logging.basicConfig(level=logging.DEBUG)
        s = ModelScheduler()
        w = WriterAgent(s)

        # Build fixtures inline
        pc = ProjectConfig(
            title="Test the novel",
            inspiration="The story of a child who accidentally awakens ancient bloodlines and emerges step by step in a world where the weak and the weak eat.",
            genre=["Fantasy", "Cultivation Fantasy", "It's a piece of shit"],
            target_readers="A male reader who likes hot blood to escalate",
            tone="Hot blood",
            target_word_count=90000,
        )
        world = WorldBuilding(
            name="Azure Continent",
            world_type="fantasy",
            geography="Nine States",
            history="A thousand years ago, the War of the Wonders",
            culture="It's all about strength",
            magic_system="Truth system",
        )
        b = NovelBible(
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
                "char_002": CharacterProfile(
                    id="char_002",
                    name="Su Wanqing",
                    role="deuteragonist",
                    personality="It's cold inside",
                    motivation="Find Master",
                    flaw="It's not a good expression",
                    backstory="It's a mystery",
                ),
            }
        )
        outline = MasterOutline(
            title="I'm not going anywhere",
            logline="You've changed your life",
            main_plot=[PlotArc(name="Main Plot", description="The main player grows", arc_type="main")],
            subplots=[],
            volumes=[Volume(title="Volume I", number=1, start_chapter=1, end_chapter=10)],
            major_turning_points=[
                TurningPoint(turning_type="inciting_incident", chapter=1, description="Blood and blood awakening"),
            ],
            chapter_count=30,
        )
        plan = ChapterPlan(
            chapter_number=1,
            title="The Boy Who Could Not Cultivate",
            goal="Create a lead character dilemma and a worldview",
            scenes=[
                Scene(
                    number=1,
                    setting="The Qin mine",
                    pov="char_001",
                    characters_present=["char_001"],
                    goal="Showing the low profile of the protagonist",
                    conflict="Miners scoffing and supervision",
                    outcome="Qinmu's eyes flashed a little bit",
                ),
                Scene(
                    number=2,
                    setting="Deep in the mine",
                    pov="char_001",
                    characters_present=["char_001"],
                    goal="There's an unusual mine",
                    conflict="The cave collapses",
                    outcome="Found the ancient crystals",
                ),
            ],
            pov_character="char_001",
            conflict="The main character's heart is indifferent to the oppression of reality",
            hooks=[Hook(hook_type="cliffhanger", description="The old voices are ringing in my head")],
            characters_involved=["char_001"],
            information_increment="Create a world view, introduce the main character's dilemma",
            reveals=["The existence of ancient veins"],
            foreshadowing=["Indictments of blood source"],
            emotional_curve=[
                EmotionalBeat(position=0.0, emotion="Repression", intensity=0.7),
                EmotionalBeat(position=0.5, emotion="Despair", intensity=0.8),
                EmotionalBeat(position=1.0, emotion="Stunny", intensity=0.95),
            ],
            ending_hook="The old sound in my head: 'Twilight years... finally wait for you.'",
            word_count_target=4000,
        )
        mem = MemoryState()

        print("Testing generate_chapter...")
        try:
            draft = await w.generate_chapter(
                chapter_plan=plan,
                config=pc,
                bible=b,
                characters=chars,
                outline=outline,
                memory=mem,
            )
            print(f"SUCCESS: {draft.title} ({draft.word_count} chars)")
            print(f"Content preview:\n{draft.content[:500]}...")

            # Also test fact extraction
            print("\nTesting extract_facts_and_changes...")
            draft = await w.extract_facts_and_changes(draft, b, chars)
            print(f"SUCCESS: {len(draft.new_facts)} facts, {len(draft.character_state_changes)} changes")
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

    asyncio.run(main())
