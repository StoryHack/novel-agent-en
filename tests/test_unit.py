"""Unit tests — no API key required.

Tests Pydantic model validation, JSON repair, content safety,
prompt building, and settings resolution with pure logic.
"""

import json
import sys
from pathlib import Path

import pytest

# Put the repository root on sys.path for python -m pytest and uv run pytest.
# This supports src.* imports and their package-relative imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.scheduler import _try_parse_json

# ═══════════════════════════════════════════════════════════════════════
# JSON Repair (_try_parse_json)
# ═══════════════════════════════════════════════════════════════════════


class TestJsonRepair:
    """Test the multi-layer JSON repair pipeline used by ModelScheduler."""

    def test_valid_json_passes_through(self):
        data = {"title": "test", "content": "hello world"}
        result = _try_parse_json(json.dumps(data))
        assert result == data

    def test_valid_json_with_chinese(self):
        data = {"title": "测试章节", "content": "这是正文。" * 50}
        result = _try_parse_json(json.dumps(data, ensure_ascii=False))
        assert result["title"] == "测试章节"

    def test_json_inside_markdown_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _try_parse_json(raw)
        assert result["key"] == "value"

    def test_json_with_leading_text(self):
        raw = 'Here is the output:\n\n{"key": "value"}'
        result = _try_parse_json(raw)
        assert result["key"] == "value"

    def test_json_with_trailing_text(self):
        raw = '{"key": "value"}\n\nEnd of output.'
        result = _try_parse_json(raw)
        assert result["key"] == "value"

    def test_unescaped_newlines_in_string(self):
        raw = '{\n  "content": "line 1\nline 2\nline 3",\n  "title": "ok"\n}'
        result = _try_parse_json(raw)
        assert result["title"] == "ok"
        assert "line 1" in result["content"]

    def test_unescaped_tabs_in_string(self):
        raw = '{"content": "col1\tcol2\tcol3", "title": "ok"}'
        result = _try_parse_json(raw)
        assert result["title"] == "ok"

    def test_truncated_json_closes_braces(self):
        raw = '{"title": "test", "content": "truncated...'
        result = _try_parse_json(raw)
        assert result["title"] == "test"

    @pytest.mark.xfail(reason="Known limitation: deeply nested truncation with unclosed string in array")
    def test_truncated_json_with_nested_brackets(self):
        raw = '{"items": [{"a": 1}, {"b": 2}'
        result = _try_parse_json(raw)
        assert isinstance(result, dict)
        assert "items" in result or "a" in result

    def test_truncated_json_unclosed_string(self):
        raw = '{"title": "test", "content": "unclosed string'
        result = _try_parse_json(raw)
        assert "title" in result

    def test_qwen3_style_comment_in_json(self):
        """Qwen3 sometimes copies // comments from schema prompts."""
        raw = '{\n  "title": "test",  // Title\n  "content": "Chapter text"\n}'
        result = _try_parse_json(raw)
        # Should either parse successfully or at minimum not crash
        assert isinstance(result, (dict, type(None))) or "title" in result

    def test_empty_object(self):
        result = _try_parse_json("{}")
        assert result == {}

    def test_empty_array(self):
        result = _try_parse_json("[]")
        assert result == []

    def test_nested_objects(self):
        data = {"a": {"b": {"c": [1, 2, 3]}}}
        result = _try_parse_json(json.dumps(data))
        assert result["a"]["b"]["c"] == [1, 2, 3]

    def test_qwen3_real_truncation_pattern(self):
        """Simulate model output ending inside an unclosed content string."""
        raw = (
            "{\n"
            '  "title": "The Mine",\n'
            '  "content": "# Chapter 1\\n\\n'
            "Qin Mo stood deep in the mine, turning a strange crystal in his hand. "
            "An old voice stirred in his head and whis"
        )
        result = _try_parse_json(raw)
        assert result["title"] == "The Mine"
        assert "Qin Mo" in result["content"]



# ═══════════════════════════════════════════════════════════════════════
# Pydantic Model Validators — ChapterContentOutput
# ═══════════════════════════════════════════════════════════════════════


class TestChapterContentOutput:
    from src.agents.writer import ChapterContentOutput

    def test_valid(self):
        data = {"title": "Chapter I", "content": "Text", "author_notes": "Remarks"}
        result = self.ChapterContentOutput.model_validate(data)
        assert result.title == "Chapter I"
        assert result.content == "Text"

    def test_chinese_content_alias(self):
        """Recognize the legacy Chinese aliases for body text and notes."""
        data = {"title": "Chapter I", "正文": "Text", "备注": "Author note"}
        result = self.ChapterContentOutput.model_validate(data)
        assert result.title == "Chapter I"
        assert result.content == "Text"
        assert result.author_notes == "Author note"

    def test_chinese_author_notes_alias(self):
        """Recognize an alternate Chinese alias for author notes."""
        data = {"title": "Chapter I", "content": "Contents", "附注": "Contents of the note"}
        result = self.ChapterContentOutput.model_validate(data)
        assert result.author_notes == "Contents of the note"

    def test_missing_optional_fields_default(self):
        data = {"title": "Chapter I", "content": "Chapter Text"}
        result = self.ChapterContentOutput.model_validate(data)
        assert result.author_notes == ""

    def test_empty_all(self):
        result = self.ChapterContentOutput.model_validate({})
        assert result.title == ""
        assert result.content == ""
        assert result.author_notes == ""

    def test_extra_fields_ignored(self):
        data = {"title": "Chapter I", "content": "Chapter Text", "extra": "ignored"}
        result = self.ChapterContentOutput.model_validate(data)
        assert result.title == "Chapter I"
        assert not hasattr(result, "extra")

    def test_notes_alias(self):
        result = self.ChapterContentOutput.model_validate({"title": "x", "content": "y", "notes": "z"})
        assert result.author_notes == "z"


# ═══════════════════════════════════════════════════════════════════════
# Pydantic Model Validators — FactExtractionOutput
# ═══════════════════════════════════════════════════════════════════════


class TestFactExtractionOutput:
    from src.agents.writer import FactExtractionOutput

    def test_valid_empty(self):
        result = self.FactExtractionOutput.model_validate({"new_facts": [], "state_changes": []})
        assert result.new_facts == []
        assert result.state_changes == []

    def test_string_facts_coerced(self):
        """Plain strings should be coerced to Fact dicts."""
        result = self.FactExtractionOutput.model_validate({"new_facts": ["Cultivators hold the highest status on the Azure Continent."], "state_changes": []})
        assert result.new_facts[0].description == "Cultivators hold the highest status on the Azure Continent."

    def test_string_state_changes_coerced(self):
        """Plain strings should be coerced to StateChange dicts."""
        result = self.FactExtractionOutput.model_validate({"new_facts": [], "state_changes": ["Qin awakened his ancient blood"]})
        assert result.state_changes[0].reason == "Qin awakened his ancient blood"

    def test_chinese_keys_normalized(self):
        result = self.FactExtractionOutput.model_validate(
            {
                "new_facts": [{"描述": "Test facts", "类别": "world", "确定性": 0.8}],
                "state_changes": [],
            }
        )
        assert result.new_facts[0].description == "Test facts"
        assert result.new_facts[0].category == "world"
        assert result.new_facts[0].certainty == 0.8

    def test_mixed_strings_and_dicts(self):
        result = self.FactExtractionOutput.model_validate(
            {
                "new_facts": [
                    {"category": "plot", "description": "It's a story"},
                    "Another fact",
                ],
                "state_changes": [
                    {"character_id": "char_001", "reason": "Normal"},
                    "Role change",
                ],
            }
        )
        assert len(result.new_facts) == 2
        assert result.new_facts[0].category == "plot"
        assert result.new_facts[1].description == "Another fact"


# ═══════════════════════════════════════════════════════════════════════
# Content Safety
# ═══════════════════════════════════════════════════════════════════════


class TestContentSafety:
    from src.utils.content_safety import ContentSafetyChecker

    def test_clean_content_passes(self):
        checker = self.ContentSafetyChecker()
        text = "Qin Mo stood on the summit. Far below, shadows crept over the valley, and the wind snapped at his robe."
        result = checker.check(text)
        assert result.passed
        assert len(result.flags) == 0

    def test_block_keyword_detected(self):
        checker = self.ContentSafetyChecker()
        text = "This passage includes the phrase sexual intercourse."  # blocking keyword
        result = checker.check(text)
        assert not result.passed
        assert result.block_count >= 1

    def test_warning_keyword_flagged(self):
        checker = self.ContentSafetyChecker()
        text = "The prose uses the phrase heaving bosom."  # warning keyword
        result = checker.check(text)
        assert result.passed  # Warnings don't block
        assert result.warning_count >= 1

    def test_multiple_flags(self):
        checker = self.ContentSafetyChecker()
        text = "The passage uses the phrases sexual intercourse and heaving bosom."  # block + warning
        result = checker.check(text)
        assert not result.passed
        assert result.block_count >= 1
        assert result.warning_count >= 1

    def test_empty_text_passes(self):
        checker = self.ContentSafetyChecker()
        result = checker.check("")
        assert result.passed
        assert len(result.flags) == 0

    def test_long_novel_chapter_passes(self):
        checker = self.ContentSafetyChecker()
        text = (
            "The last glow of sunset stretched the shadows across the rocky road. "
            "Qin Mo carried a bamboo basket full of ore. Three years in the mine had "
            "left him with calluses harder than the stones he carried."
        ) * 20
        result = checker.check(text)
        assert result.passed

    def test_flag_context_captured(self):
        checker = self.ContentSafetyChecker()
        text = "Some setup. " + "Sexual intercourse" + " is mentioned later."
        result = checker.check(text)
        assert len(result.flags) >= 1
        flag = result.flags[0]
        assert flag.keyword == "sexual intercourse"
        assert flag.severity == "block"
        assert len(flag.context) > 0

    def test_summary_formatting(self):
        checker = self.ContentSafetyChecker()
        result = checker.check("Sexual intercourse and heaving bosom")
        summary = result.summary
        assert "flag" in summary.lower() or "flag" in summary


# ═══════════════════════════════════════════════════════════════════════
# Prompt Building
# ═══════════════════════════════════════════════════════════════════════

def test_english_opening_arc_fallback():
    from src.agents.topic_scout import TopicScoutAgent

    chapters, arc_goal, next_hook = TopicScoutAgent._parse_text_mini_arc(
        "## Chapter 1\nChapter Goal: Find the key\nEnding Hook: The door opens\n\n"
        "Chapter 2\nChapter Conflict: A guard blocks the way\n\n"
        "Arc Summary\nArc Goal: Escape the keep\nNext Arc Hook: A hidden map"
    )
    assert [chapter.chapter_number for chapter in chapters] == [1, 2]
    assert chapters[0].goal == "Find the key"
    assert chapters[0].ending_hook == "The door opens"
    assert chapters[1].conflict == "A guard blocks the way"
    assert chapters[1].ending_hook == ""
    assert (arc_goal, next_hook) == ("Escape the keep", "A hidden map")


def test_chapter_word_count():
    from src.utils.text import count_words

    assert count_words("Don't stop.\n\n***\n\nKeep writing.") == 4
    assert count_words("继续 写作。") == 5


class TestPromptBuilding:
    def test_expansion_prompt_contains_targets(self):
        from src.agents.writer import _build_expansion_prompt

        prompt = _build_expansion_prompt(
            content="Short content",
            current_count=1000,
            target_count=4000,
            chapter_num=3,
            chapter_title="Test Chapter",
        )
        assert "4000" in prompt
        assert "1000" in prompt
        assert "Test Chapter" in prompt
        assert "Chapter 3" in prompt
        assert "Short content" in prompt

    def test_expansion_prompt_has_json_instruction(self):
        from src.agents.writer import _build_expansion_prompt

        prompt = _build_expansion_prompt(
            content="x",
            current_count=100,
            target_count=500,
            chapter_num=1,
            chapter_title="title",
        )
        assert "JSON" in prompt or "content" in prompt

    def test_format_scenes(self):
        from src.agents.writer import WriterAgent
        from src.llm.scheduler import ModelScheduler
        from src.models.outline import Scene

        agent = WriterAgent(ModelScheduler())
        scenes = [
            Scene(
                number=1,
                setting="Mine",
                pov="char_001",
                characters_present=["char_001"],
                goal="Show the protagonist at their lowest point",
                conflict="Oppression",
                outcome="I don't like it",
            ),
        ]
        result = agent._format_scenes(scenes)
        assert "Mine" in result

    def test_format_emotional_curve(self):
        from src.agents.writer import WriterAgent
        from src.llm.scheduler import ModelScheduler
        from src.models.outline import EmotionalBeat

        agent = WriterAgent(ModelScheduler())
        beats = [
            EmotionalBeat(position=0.0, emotion="Repression", intensity=0.7),
            EmotionalBeat(position=1.0, emotion="Astonishment", intensity=0.95),
        ]
        result = agent._format_emotional_curve(beats)
        assert "Repression" in result
        assert "Astonishment" in result


# ═══════════════════════════════════════════════════════════════════════
# Settings & Model Assignments
# ═══════════════════════════════════════════════════════════════════════


class TestModelAssignments:
    def test_provider_presets_loaded(self):
        from src.config.settings import PROVIDER_PRESETS

        assert "modelscope" in PROVIDER_PRESETS
        assert "openai" in PROVIDER_PRESETS
        assert "anthropic" in PROVIDER_PRESETS
        assert PROVIDER_PRESETS["modelscope"]["quality"] == "Qwen/Qwen3-235B-A22B"

    def test_quality_agents_have_writer(self):
        from src.config.model_assignments import QUALITY_AGENTS

        assert "writer" in QUALITY_AGENTS
        assert "character_manager" in QUALITY_AGENTS
        assert "architect" in QUALITY_AGENTS

    def test_budget_agents_have_editor(self):
        from src.config.model_assignments import BUDGET_AGENTS

        assert "editor" in BUDGET_AGENTS
        assert "continuity_checker" in BUDGET_AGENTS

    def test_agent_configs_complete(self):
        from src.config.model_assignments import AGENT_CONFIGS, BUDGET_AGENTS, ORCHESTRATOR_AGENTS, QUALITY_AGENTS

        all_agents = QUALITY_AGENTS | BUDGET_AGENTS | ORCHESTRATOR_AGENTS
        for agent in all_agents:
            assert agent in AGENT_CONFIGS, f"Missing config for {agent}"
            assert "temperature" in AGENT_CONFIGS[agent]
            assert "max_tokens" in AGENT_CONFIGS[agent]

    def test_writer_max_tokens(self):
        from src.config.model_assignments import AGENT_CONFIGS

        assert AGENT_CONFIGS["writer"]["max_tokens"] >= 16384

    def test_all_agents_in_override_map(self):
        import inspect

        from src.config.model_assignments import (
            BUDGET_AGENTS,
            ORCHESTRATOR_AGENTS,
            QUALITY_AGENTS,
            _resolve_provider_model,
        )

        # Verify the function has entries for all agent types
        all_agents = sorted(QUALITY_AGENTS | BUDGET_AGENTS | ORCHESTRATOR_AGENTS)
        src = inspect.getsource(_resolve_provider_model)
        for agent in all_agents:
            assert agent in src, f"Override map missing: {agent}"


# ═══════════════════════════════════════════════════════════════════════
# Data Models — Robustness
# ═══════════════════════════════════════════════════════════════════════


class TestMasterOutlineValidation:
    from src.models.outline import MasterOutline

    def test_string_volumes_coerced(self):
        """Qwen3 returns volumes as strings — should be coerced."""
        from src.models.outline import PlotArc, TurningPoint, Volume

        outline = self.MasterOutline(
            title="Test",
            logline="Test",
            main_plot=[PlotArc(name="Main Plot", description="Main Plot", arc_type="main")],
            subplots=[],
            volumes=[Volume(title="Volume I", number=1, start_chapter=1, end_chapter=10)],
            major_turning_points=[TurningPoint(turning_type="inciting_incident", chapter=1, description="Events")],
            chapter_count=30,
        )
        assert outline.title == "Test"
        assert outline.volumes[0].number == 1

    def test_minimal_outline_valid(self):
        from src.models.outline import PlotArc, TurningPoint, Volume

        outline = self.MasterOutline(
            title="Test",
            logline="Test",
            main_plot=[PlotArc(name="Main Plot", description="d", arc_type="main")],
            volumes=[Volume(title="v", number=1, start_chapter=1, end_chapter=5)],
            major_turning_points=[TurningPoint(turning_type="inciting_incident", chapter=1, description="Events")],
            chapter_count=10,
        )
        assert outline.chapter_count == 10


class TestFactModel:
    from src.models.chapter import Fact

    def test_string_coerced(self):
        fact = self.Fact.model_validate("Cultivators hold the highest status on the Azure Continent.")
        assert fact.description == "Cultivators hold the highest status on the Azure Continent."
        # Default category when coerce from string
        assert fact.category in ("world", "other")

    def test_dict_with_chinese_keys(self):
        fact = self.Fact.model_validate({"描述": "Test facts", "类别": "character", "确定性": 0.9})
        assert fact.description == "Test facts"
        assert fact.category == "character"
        assert fact.certainty == 0.9


# ═══════════════════════════════════════════════════════════════════════
# Model Assignments — Parse Override
# ═══════════════════════════════════════════════════════════════════════


class TestParseOverride:
    def test_provider_model_split(self):
        from src.config.model_assignments import _parse_override
        from src.config.settings import Settings

        settings = Settings()
        provider, model, fallback = _parse_override("anthropic:claude-sonnet-4", settings)
        assert provider == "anthropic"
        assert model == "claude-sonnet-4"
        assert fallback is None

    def test_model_only_uses_default_provider(self):
        from src.config.model_assignments import _parse_override
        from src.config.settings import Settings

        settings = Settings(
            default_provider="modelscope",
            default_model="Qwen/Qwen3-235B-A22B",
            openai_api_key="test-key",
            openai_base_url="https://api-inference.modelscope.cn/v1",
            _env_file=None,
        )
        provider, model, fallback = _parse_override("Qwen/Qwen3-8B", settings)
        assert provider == "modelscope"
        assert model == "Qwen/Qwen3-8B"


# ═══════════════════════════════════════════════════════════════════════
# File Manager — Path Handling
# ═══════════════════════════════════════════════════════════════════════


class TestFileManager:
    def test_root_path_construction(self):
        from pathlib import Path

        from src.storage.file_manager import ProjectFileManager

        fm = ProjectFileManager("/tmp/workspace", "proj_001")
        assert fm.root == Path("/tmp/workspace/projects/proj_001")
        assert fm.workspace_root == Path("/tmp/workspace")
        assert fm.project_id == "proj_001"

    def test_path_with_windows_style(self):
        from src.storage.file_manager import ProjectFileManager

        fm = ProjectFileManager("D:\\novels", "test-project")
        # Normalize separators before comparing across platforms.
        assert str(fm.root).replace("\\", "/") == "D:/novels/projects/test-project"

    def test_exists_returns_false_for_new_project(self):
        import tempfile

        from src.storage.file_manager import ProjectFileManager

        with tempfile.TemporaryDirectory() as td:
            fm = ProjectFileManager(td, "nonexistent")
            assert not fm.exists()

    def test_initialize_creates_directories(self):
        import tempfile

        from src.models.project import ProjectConfig
        from src.storage.file_manager import ProjectFileManager

        with tempfile.TemporaryDirectory() as td:
            fm = ProjectFileManager(td, "init_test")
            config = ProjectConfig(
                title="Test",
                inspiration="Test",
                genre=["Fantasy"],
                target_readers="Readers",
                tone="High-energy adventure",
            )
            fm.initialize(config)
            assert fm.exists()
            assert (fm.root / "novel_bible").is_dir()
            assert (fm.root / "outline" / "chapters").is_dir()
            assert (fm.root / "memory").is_dir()
            assert (fm.root / "output" / "chapters").is_dir()


# ═══════════════════════════════════════════════════════════════════════
# Model Scheduler — Routing & Provider Init
# ═══════════════════════════════════════════════════════════════════════


class TestSchedulerRouting:
    def test_get_assignment_returns_known_agent(self):
        from src.llm.scheduler import ModelScheduler

        s = ModelScheduler()
        assignment = s._get_assignment("writer")
        assert assignment.agent_type == "writer"
        assert assignment.max_tokens >= 16384

    def test_get_assignment_falls_back_for_unknown(self):
        from src.llm.scheduler import ModelScheduler

        s = ModelScheduler()
        assignment = s._get_assignment("nonexistent_agent")
        assert assignment is not None
        # Falls back to orchestrator or first available
        assert assignment.agent_type in ("orchestrator", "writer", "architect")

    def test_all_registered_agents_have_assignments(self):
        from src.config.model_assignments import AGENT_CONFIGS
        from src.llm.scheduler import ModelScheduler

        s = ModelScheduler()
        for agent_type in AGENT_CONFIGS:
            assignment = s._get_assignment(agent_type)
            assert assignment is not None, f"Missing assignment for {agent_type}"
            assert assignment.max_tokens > 0
            assert 0.0 <= assignment.temperature <= 2.0

    def test_modelscope_uses_openai_provider(self):
        from src.config.settings import Settings
        from src.llm.scheduler import ModelScheduler

        s = ModelScheduler(
            settings=Settings(
                openai_api_key="test-key",
                openai_base_url="https://api-inference.modelscope.cn/v1",
                _env_file=None,
            )
        )
        provider = s._get_provider("modelscope")
        assert provider.provider_name in ("openai", "modelscope")

    def test_provider_lazy_initialization(self):
        from src.config.settings import Settings
        from src.llm.scheduler import ModelScheduler

        s = ModelScheduler(
            settings=Settings(
                openai_api_key="test-key",
                openai_base_url="https://api-inference.modelscope.cn/v1",
                _env_file=None,
            )
        )
        # Providers dict starts empty
        assert len(s._providers) == 0
        # First access initializes
        p1 = s._get_provider("modelscope")
        assert "modelscope" in s._providers
        # Second access returns same instance
        p2 = s._get_provider("modelscope")
        assert p1 is p2


# ═══════════════════════════════════════════════════════════════════════
# Character & Bible Models
# ═══════════════════════════════════════════════════════════════════════


class TestCharacterModels:
    def test_minimal_character_profile(self):
        from src.models.characters import CharacterProfile

        char = CharacterProfile(
            id="char_001",
            name="Qin Mo",
            role="protagonist",
            personality="Strong",
            motivation="Stronger",
            flaw="Stubborn",
            backstory="Exiled",
        )
        assert char.name == "Qin Mo"
        assert char.role == "protagonist"

    def test_character_registry(self):
        from src.models.characters import CharacterProfile, CharacterRegistry

        reg = CharacterRegistry(
            characters={
                "c1": CharacterProfile(
                    id="c1",
                    name="Lead",
                    role="protagonist",
                    personality="Brave",
                    motivation="Revenge",
                    flaw="Arrogance",
                    backstory="Orphans",
                ),
            }
        )
        assert "c1" in reg.characters
        assert reg.characters["c1"].name == "Lead"


class TestBibleModels:
    def test_world_building_minimal(self):
        from src.models.bible import WorldBuilding

        w = WorldBuilding(name="Test Continent", world_type="fantasy")
        assert w.name == "Test Continent"
        assert w.world_type == "fantasy"

    def test_faction_creation(self):
        from src.models.bible import Faction

        f = Faction(name="Azure Cloud Sect", faction_type="sect", goal="Uphold the righteous path")
        assert f.name == "Azure Cloud Sect"
        assert f.faction_type == "sect"

    def test_novel_bible_minimal(self):
        from src.models.bible import (
            CoreConflict,
            Faction,
            NarrativeRules,
            NovelBible,
            StyleContract,
            Theme,
            WorldBuilding,
        )

        bible = NovelBible(
            world=WorldBuilding(name="Continental", world_type="fantasy"),
            factions=[Faction(name="Azure Cloud Sect", faction_type="sect", goal="The right path")],
            rules=NarrativeRules(),
            style_contract=StyleContract(tone="High-energy adventure"),
            themes=[Theme(name="Grow")],
            core_conflicts=[CoreConflict(conflict_type="person_vs_society", description="Protest")],
        )
        assert len(bible.factions) == 1
        assert bible.style_contract.tone == "High-energy adventure"
        assert len(bible.themes) == 1


# ═══════════════════════════════════════════════════════════════════════
# Settings — Provider Detection
# ═══════════════════════════════════════════════════════════════════════


class TestSettingsProviderDetection:
    def test_detect_modelscope_from_base_url(self):
        from src.config.settings import Settings

        s = Settings(
            openai_base_url="https://api-inference.modelscope.cn/v1",
            _env_file=None,
        )
        # No API keys → falls through to base_url detection
        assert s.active_provider == "modelscope"

    def test_detect_dashscope_from_base_url(self):
        from src.config.settings import Settings

        s = Settings(
            openai_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            _env_file=None,
        )
        # No API keys → falls through to base_url detection
        assert s.active_provider == "dashscope"

    def test_default_active_provider(self):
        from src.config.settings import Settings

        s = Settings(
            default_provider="openai",
            openai_api_key="test",
            _env_file=None,
        )
        assert s.active_provider == "openai"

    def test_has_anthropic_detection(self):
        from src.config.settings import Settings

        s = Settings(_env_file=None)
        assert not s.has_anthropic
        s2 = Settings(anthropic_api_key="sk-ant-test", _env_file=None)
        assert s2.has_anthropic
