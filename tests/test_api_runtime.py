"""Runtime-path smoke tests for the FastAPI layer.

Covers the previously-untested parts of ``src/api/routes.py`` and
``src/api/phase_executor.py``:

- Project CRUD roundtrip (file-manager + route layer, no LLM)
- LLM-backed endpoint (``/projects/suggest-titles``) driven by a fake
  scheduler — no network, no API keys
- ``/start`` workflow failure survival (a failing provider must not crash
  the app; the error is caught by the workflow's top-level handler)
- Error paths (``retry-phase`` on unknown project → 404)
- Project-scoped research import and confirmation through the real graph

Run: pytest tests/test_api_runtime.py -v   (no API key needed)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Isolate the workspace BEFORE any settings/app import.
os.environ["WORKSPACE_ROOT"] = str(REPO_ROOT / ".test_workspace")

sys.path.insert(0, str(REPO_ROOT / "src"))

import httpx  # noqa: E402
import pytest  # noqa: E402

from src.agents.orchestrator import _build_topic_context  # noqa: E402
from src.agents.topic_scout import TopicScoutAgent  # noqa: E402
from src.api import dependencies, phase_executor, routes  # noqa: E402
from src.api.server import create_app  # noqa: E402
from src.graph import workflow  # noqa: E402
from src.llm.client import LLMResponse  # noqa: E402
from src.llm.scheduler import ModelScheduler  # noqa: E402
from src.models.research import ResearchImport  # noqa: E402
from src.models.state import MainState  # noqa: E402
from src.models.topic import CandidateTopic, CandidateTopicsOutput  # noqa: E402


class FakeScheduler(ModelScheduler):
    """Deterministic ModelScheduler stub — no network, no API keys.

    ``generate`` returns canned text; ``generate_structured`` returns a valid
    instance of the requested response model when it looks like a titles
    response, otherwise a default-constructed instance.
    """

    def __init__(
        self,
        *,
        content: str = "Title: The Talking Cat\nSynopsis: A cat learns to talk.",
        titles: list[str] | None = None,
        fail: bool = False,
    ):
        super().__init__(assignments=[])
        self.content = content
        self.titles = titles or ["Title One", "Title Two", "Title Three"]
        self.fail = fail
        self.calls: list[str] = []

    async def generate(
        self,
        agent_type,
        system_prompt,
        user_prompt,
        response_model=None,
        temperature_override=None,
        max_tokens_override=None,
    ):
        self.calls.append(agent_type)
        if self.fail:
            raise RuntimeError("fake provider failure (intentional)")
        return LLMResponse(content=self.content, model="fake-model", provider="fake")

    async def generate_structured(
        self,
        agent_type,
        system_prompt,
        user_prompt,
        response_model,
        temperature_override=None,
        max_tokens_override=None,
    ):
        self.calls.append(agent_type)
        if self.fail:
            raise RuntimeError("fake provider failure (intentional)")
        if "titles" in response_model.model_fields:
            return response_model.model_validate({"titles": self.titles})
        if response_model.__name__ == "WorldBuildingOutput":
            return response_model.model_validate({"name": "Example World", "world_type": "fantasy"})
        return response_model.model_construct()


@pytest.fixture(autouse=True)
def _isolate_scheduler(monkeypatch):
    """Give each test its own scheduler, workflow registry, and checkpointer."""
    fake = FakeScheduler()
    monkeypatch.setattr(dependencies, "_scheduler", fake)
    monkeypatch.setattr(routes, "_active_projects", {})
    monkeypatch.setattr(workflow, "_graph", None)
    yield fake


@pytest.fixture
def client():
    app = create_app()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


PROJECT_PAYLOAD = {
    "config": {
        "title": "To test his life against his will",
        "inspiration": "A young mountain boy has to break a fairy book and change his life.",
        "genre": ["Fantasy", "Cultivation Fantasy"],
        "target_readers": "Male readers ages 18–35",
        "target_word_count": 80000,
    }
}


async def test_project_crud_roundtrip(client):
    # create
    r = await client.post("/api/projects", json=PROJECT_PAYLOAD)
    assert r.status_code == 200, r.text
    body = r.json()
    project_id = body["project_id"]
    assert body["status"] == "initialized"

    # list contains it
    r = await client.get("/api/projects")
    assert r.status_code == 200
    ids = [p["project_id"] for p in r.json()]
    assert project_id in ids

    # detail
    r = await client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["config"]["title"] == PROJECT_PAYLOAD["config"]["title"]

    # update title
    r = await client.put(f"/api/projects/{project_id}/title", json={"title": "Book name after name change"})
    assert r.status_code == 200
    r = await client.get(f"/api/projects/{project_id}")
    assert r.json()["meta"]["title"] == "Book name after name change"

    # delete
    r = await client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 200
    r = await client.get(f"/api/projects/{project_id}")
    assert r.status_code == 404


async def test_suggest_titles_uses_fake_scheduler(client, _isolate_scheduler):
    fake: FakeScheduler = _isolate_scheduler
    r = await client.post(
        "/api/projects/suggest-titles",
        json={"inspiration": "A talking cat", "genre": ["Urban Fiction"]},
    )
    assert r.status_code == 200, r.text
    titles = r.json()["titles"]
    assert titles == fake.titles
    assert fake.calls, "scheduler should have been called by suggest-titles"


async def test_generate_synopsis_parses_english_labels(client):
    r = await client.post(
        "/api/projects/test-project/generate-synopsis",
        json={"genre_name": "Fantasy", "inspiration": "A talking cat"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["final_title"] == "The Talking Cat"
    assert r.json()["final_synopsis"] == "A cat learns to talk."


async def test_start_workflow_survives_fake_llm_failure(client, _isolate_scheduler):
    fake: FakeScheduler = _isolate_scheduler
    fake.fail = True

    r = await client.post("/api/projects", json=PROJECT_PAYLOAD)
    project_id = r.json()["project_id"]

    r = await client.post(f"/api/projects/{project_id}/start")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "started"

    await asyncio.wait_for(routes._active_projects[project_id]["task"], timeout=5)
    assert fake.calls, "workflow should have hit the (failing) scheduler"

    # The app must remain healthy: project still listed, no 500s.
    r = await client.get("/api/projects")
    assert r.status_code == 200
    assert project_id in [p["project_id"] for p in r.json()]


async def test_retry_phase_unknown_project_returns_404(client):
    r = await client.post("/api/projects/nonexistent/retry-phase/bible_construction", json={"inspiration": None})
    assert r.status_code == 404


CSV_HEADER = "platform,list_name,source_url,captured_on,story_url,title,language,rank,tags,note"
WATTPAD = (
    "wattpad,Fantasy example,https://www.wattpad.com/,2026-01-01,"
    "https://www.wattpad.com/story/101-example,Example Moon Garden,en,3,Fantasy|Romance,"
    "A gardener inherits a moonlit estate."
)
ROYAL_ROAD = (
    "royal_road,Rising Stars example,https://www.royalroad.com/fictions/rising-stars,2026-01-01,"
    "https://www.royalroad.com/fiction/201/example,Example Clockwork Map,en,,Fantasy|Progression,"
    "A map grows as its maker completes challenges."
)


class ResearchScheduler(FakeScheduler):
    """Return shaped research results with deliberately invalid source claims."""

    def __init__(self, *, text_scores=False, fail_analysis=False):
        super().__init__()
        self.text_scores = text_scores
        self.fail_analysis = fail_analysis
        self.prompts = []

    @staticmethod
    def evaluations():
        return {
            "scores": [
                {
                    "genre_name": "Fantasy",
                    "score_title_appeal": 8,
                    "score_opening_pressure": 8,
                    "score_event_clarity": 8,
                    "score_golden_finger": 8,
                    "score_ai_stability": 8,
                    "score_breakdown_risk": 8,
                    "platform_fit": {
                        "wattpad": {"score": 9, "evidence": ["wattpad:101"], "rationale": "Fantasy tag."},
                        "royal_road": {"score": 2, "evidence": ["royal_road:999"], "rationale": "Invented reference."},
                    },
                }
            ]
        }

    async def generate_structured(self, agent_type, system_prompt, user_prompt, response_model, **kwargs):
        self.prompts.append(system_prompt + "\n" + user_prompt)
        name = response_model.__name__
        if self.fail_analysis and name in ("CrossPlatformOutput", "BenchmarkOutput"):
            raise RuntimeError("Offline enrichment unavailable")
        if self.text_scores and name == "TopicScoresOutput":
            raise RuntimeError("Structured scoring unavailable")
        data = {
            "CrossPlatformOutput": {
                "directions": [
                    {
                        "genre": "Fantasy",
                        "findings": [
                            {
                                "platform": "wattpad",
                                "observation": "Fantasy tag in the sample.",
                                "evidence": ["wattpad:101"],
                            },
                            {
                                "platform": "royal_road",
                                "observation": "Progression tag in the sample.",
                                "evidence": ["royal_road:201"],
                            },
                        ],
                    },
                    {
                        "genre": "Invented trend",
                        "findings": [
                            {
                                "platform": "wattpad",
                                "observation": "No valid citation.",
                                "evidence": ["wattpad:999"],
                            }
                        ],
                    },
                ]
            },
            "BenchmarkOutput": {
                "entries": [
                    {
                        "story_ref": "wattpad:101",
                        "opening_pressure": "Invented battle in chapter one.",
                        "positioning": "An invented opening",
                        "title": "Invented title",
                    },
                    {"story_ref": "royal_road:999"},
                ]
            },
            "CandidateTopicsListOutput": {
                "topics": [
                    {"genre_name": "Fantasy", "one_line_setting": "An apprentice must teach the stars to navigate."},
                    {"genre_name": "Mystery", "one_line_setting": "A clockmaker investigates missing hours."},
                ]
            },
            "TopicScoresOutput": self.evaluations(),
            "TitleSynopsisListOutput": {
                "final_title": "An Apprentice Among Stars",
                "final_synopsis": "A new serial premise.",
            },
        }
        if name not in data:
            return await super().generate_structured(agent_type, system_prompt, user_prompt, response_model, **kwargs)
        return response_model.model_validate(data[name])

    async def generate(self, agent_type, system_prompt, user_prompt, **kwargs):
        if 'a "scores" array' in user_prompt:
            return LLMResponse(content=json.dumps(self.evaluations()), model="fake", provider="fake")
        return await super().generate(agent_type, system_prompt, user_prompt, **kwargs)


async def create_project(client):
    response = await client.post("/api/projects", json=PROJECT_PAYLOAD)
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


async def wait_for_phase(project_id, phase):
    project = routes._active_projects[project_id]
    await asyncio.wait_for(asyncio.shield(project["task"]), timeout=5)
    assert project["current_phase"] == phase
    return project["state"]


async def submit_snapshot(client, project_id, *rows):
    return await client.post(
        f"/api/projects/{project_id}/submit-scan",
        json={"csv": "\n".join((CSV_HEADER, *rows))},
    )


async def test_platform_scan_without_data_initializes_topic_state():
    state = MainState()
    await phase_executor.execute_phase_platform_scan(state, None, None)
    assert state.topic_research is not None
    assert phase_executor.get_phase_data(state, "platform_scan")["coverage"] == {}


async def test_scan_data_is_project_scoped(client):
    a, b = await create_project(client), await create_project(client)
    assert (await submit_snapshot(client, a, WATTPAD)).status_code == 200
    assert (await submit_snapshot(client, b, ROYAL_ROAD)).status_code == 200
    a_url, b_url = (f"/api/projects/{project_id}" for project_id in (a, b))
    await asyncio.gather(client.post(f"{a_url}/start"), client.post(f"{b_url}/start"))
    a_state, b_state = await asyncio.gather(wait_for_phase(a, "platform_scan"), wait_for_phase(b, "platform_scan"))
    assert a_state.research_input.coverage() == {"wattpad": 1, "royal_road": 0}
    assert b_state.research_input.coverage() == {"wattpad": 0, "royal_road": 1}

    assert (await submit_snapshot(client, a, ROYAL_ROAD)).status_code == 200
    assert (await submit_snapshot(client, a, "broken row")).status_code == 422
    assert (await client.post(f"{a_url}/start")).json()["status"] == "awaiting_confirmation"
    retry, other = await asyncio.gather(
        client.post(f"{a_url}/retry-phase/platform_scan"),
        client.post(f"{b_url}/retry-phase/platform_scan"),
    )
    assert retry.status_code == other.status_code == 200, (retry.text, other.text)
    assert routes._active_projects[a]["state"].research_input == a_state.research_input
    assert routes._active_projects[b]["state"].research_input == b_state.research_input

    retry = await client.post(f"{a_url}/retry-phase/platform_scan", json={"use_staged_research": True})
    assert retry.status_code == 200, retry.text
    assert routes._active_projects[a]["state"].research_input == b_state.research_input
    assert (await client.post(f"{a_url}/confirm-phase", json={})).status_code == 200
    a_state = await wait_for_phase(a, "topic_selection")
    assert a_state.research_input == b_state.research_input


@pytest.mark.parametrize("rows", [(WATTPAD, ROYAL_ROAD), (WATTPAD,), (ROYAL_ROAD,)])
async def test_research_workflow_through_mini_arc(client, monkeypatch, rows):
    fake = ResearchScheduler()
    monkeypatch.setattr(dependencies, "_scheduler", fake)
    project_id = await create_project(client)
    url = f"/api/projects/{project_id}"
    response = await submit_snapshot(client, project_id, *rows)
    assert response.status_code == 200, response.text
    await client.post(f"{url}/start")
    scanned = await wait_for_phase(project_id, "platform_scan")
    scan_data = phase_executor.get_phase_data(scanned, "platform_scan")
    assert sum(scan_data["coverage"].values()) == len(rows)
    assert (await client.post(f"{url}/confirm-phase", json={})).status_code == 200
    state = await wait_for_phase(project_id, "topic_selection")
    data = phase_executor.get_phase_data(state, "topic_selection")
    assert bool(data["shared_tags"]) == (len(rows) == 2)
    if len(rows) == 2:
        assert data["shared_tags"]["fantasy"] == {"wattpad": ["wattpad:101"], "royal_road": ["royal_road:201"]}
    assert len(state.topic_research.cross_platform.entries) == 1
    assert len(state.topic_research.cross_platform.entries[0].evidence) == len(rows)
    assert "Invented trend" not in state.topic_research.cross_platform.selected_directions
    if WATTPAD in rows:
        (entry,) = state.topic_research.benchmarks.entries
        assert entry.title == "Example Moon Garden"
        assert entry.positioning == "A gardener inherits a moonlit estate."
        assert entry.opening_pressure == ""
        assert data["scores"]["scores"][0]["platform_fit"]["wattpad"]["score"] == 9
        assert data["scores"]["scores"][0]["total_score"] == 8.14
    else:
        assert not data["benchmarks"]["entries"]
        assert data["scores"]["scores"][0]["total_score"] == 8
    assert "royal_road" not in data["scores"]["scores"][0]["platform_fit"]
    assert any("Sample-based positioning:" in prompt for prompt in fake.prompts)
    assert any("English-language serial fiction" in prompt for prompt in fake.prompts)

    assert (
        await client.post(
            f"{url}/confirm-phase",
            json={
                "genre_name": "Mystery",
                "selected_title": "The Missing Hours",
                "selected_synopsis": "A clockmaker investigates missing hours.",
            },
        )
    ).status_code == 200
    state = await wait_for_phase(project_id, "mini_arc_outline")
    assert len(state.mini_arc_outline["Mystery"].chapters) == 10
    brief, _ = _build_topic_context(state)
    assert "The Missing Hours" in brief
    assert "Dated sample findings" in brief
    assert "A clockmaker investigates missing hours" in brief


async def test_import_validation_and_explicit_skip(client):
    project_id = await create_project(client)
    url = f"/api/projects/{project_id}"
    assert (await submit_snapshot(client, project_id)).status_code == 422
    assert (
        await submit_snapshot(
            client, project_id, WATTPAD.replace("https://www.wattpad.com/story", "https://example.org/story")
        )
    ).status_code == 422
    assert (await client.post(f"{url}/auto-scan")).status_code == 410
    assert (await submit_snapshot(client, project_id, WATTPAD)).status_code == 200
    response = await client.post(f"{url}/start", json={"skip_research": True})
    assert response.status_code == 200, response.text
    state = await wait_for_phase(project_id, "bible_construction")
    assert state.research_input is None


def test_duplicate_story_appearances_and_unknown_metrics():
    second_list = WATTPAD.replace("Fantasy example", "Romance example").replace("/101-example", "/101-other-slug")
    research = ResearchImport.from_csv("\n".join((CSV_HEADER, WATTPAD, second_list, ROYAL_ROAD)))
    assert len(research.snapshots) == 3
    assert research.coverage() == {"wattpad": 1, "royal_road": 1}
    royal = research.snapshots[-1].observations[0]
    assert royal.rank is None and royal.metrics.views is None
    with pytest.raises(ValueError, match="Duplicate story"):
        ResearchImport.from_csv("\n".join((CSV_HEADER, WATTPAD, WATTPAD)))


async def test_text_scoring_and_failed_enrichment_preserve_evidence():
    research = ResearchImport.from_csv("\n".join((CSV_HEADER, WATTPAD)))
    scout = TopicScoutAgent(ResearchScheduler(text_scores=True, fail_analysis=True))
    assert not (await scout.cross_platform_analysis(research)).entries
    assert not (await scout.analyze_benchmarks(["Fantasy"], research)).entries
    candidates = CandidateTopicsOutput(topics=[CandidateTopic(genre_name="Fantasy")])
    (score,) = (await scout.score_topics(candidates, research)).scores
    assert score.total_score == 8.14
    assert list(score.platform_fit) == ["wattpad"]
    assert research.snapshots[0].observations[0].title == "Example Moon Garden"


async def test_legacy_checkpoint_can_resume_without_current_evidence(client):
    project_id = await create_project(client)
    url = f"/api/projects/{project_id}"
    assert (await submit_snapshot(client, project_id, WATTPAD)).status_code == 200
    await client.post(f"{url}/start")
    await wait_for_phase(project_id, "platform_scan")
    project = routes._active_projects[project_id]
    context = routes._build_run_context(project_id)
    graph = workflow.get_graph()
    await graph.aupdate_state(
        context,
        {
            "research_input": None,
            "topic_research": {
                "飞卢扫榜结果": {"platform": "Feilu", "entries": [{"title": "Historical story"}]},
                "番茄扫榜结果": {"platform": "Fanqie", "entries": [{"title": "Another historical story"}]},
                "题材评分": {"scores": [{"题材名称": "Historical genre", "番茄适配度": 9}]},
            },
        },
        as_node="platform_scan_work",
    )
    result = await graph.ainvoke(None, config=context)
    routes._save_run_state(project, result)
    assert project["state"].topic_research.scores.scores[0].score_tomato_fit == 9
    historical_topic_data = phase_executor.get_phase_data(project["state"], "topic_selection")
    assert historical_topic_data["historical"] and "scores" not in historical_topic_data
    assert phase_executor.get_phase_data(project["state"], "platform_scan") == {
        "coverage": {},
        "snapshots": [],
        "historical": True,
    }
    assert (await client.post(f"{url}/confirm-phase", json={})).status_code == 200
    state = await wait_for_phase(project_id, "topic_selection")
    assert not state.topic_research.cross_platform.entries
    assert state.topic_research.feilu_scan.entries[0].title == "Historical story"


async def test_structured_import_survives_workflow_restart(client, monkeypatch):
    project_id = await create_project(client)
    url = f"/api/projects/{project_id}"
    snapshot = ResearchImport.from_csv("\n".join((CSV_HEADER, WATTPAD)))
    response = await client.post(f"{url}/submit-scan", json=snapshot.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    # The default graph and active registry are in memory. An import lives on disk.
    monkeypatch.setattr(routes, "_active_projects", {})
    monkeypatch.setattr(workflow, "_graph", None)
    assert (await client.post(f"{url}/start")).json()["status"] == "started"
    state = await wait_for_phase(project_id, "platform_scan")
    assert state.research_input == snapshot
    detail = (await client.get(url)).json()["awaiting_confirmation"]
    assert detail["phase"] == "platform_scan"
    assert detail["data"]["snapshots"][0]["observations"][0]["story_ref"] == "wattpad:101"
