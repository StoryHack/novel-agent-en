# Novel Agent

[![CI](https://github.com/HuangLeijiana/novel-agent/actions/workflows/test.yml/badge.svg)](https://github.com/HuangLeijiana/novel-agent/actions/workflows/test.yml)

**Multi-agent AI novel writing system** — 12 specialized agents collaborate through a LangGraph pipeline to produce complete, coherent web novels from idea to finished chapters. Forked from https://github.com/HuangLeijiana/novel-agent in order to make the UI be in English and tweak some of the setup.

> 🤖 Powered by LLMs (ModelScope, DeepSeek, Claude, OpenAI, Ollama) | 🎨 Frontend control panel | 📋 Structured planning pipeline

---

## Features

- **12-Agent Pipeline** — Topic Scout → Architect → Character Manager → Plot Planner → Writer → Editor → Continuity Checker → Reader Simulator → Reviewer → Refiner → Memory Manager → Orchestrator
- **Provider Agnostic** — Works with ModelScope (free), DeepSeek, DashScope, Claude, OpenAI, OpenRouter, or local Ollama
- **Structured Planning** — World bible, character profiles, master outline, scene-level chapter plans before a single word is written
- **Quality Control** — Multi-pass review: editorial feedback → continuity checks → reader simulation → adversarial review → refinement
- **Memory System** — Tracks world facts, character states, foreshadowing, and continuity across the entire novel
- **Web UI** — Real-time control panel with WebSocket progress updates
- **Zero-cost Start** — ModelScope free tier (2000 calls/day) lets you generate a complete novel for free

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### 1. Clone & Install

```bash
git clone https://github.com/StoryHack/novel-agent-en.git
cd novel-agent-en
uv sync
```

### 2. Configure (30 seconds)

```bash
cp .env.example .env
```

Edit `.env` and choose your LLM provider. **To start for free with ModelScope:**

```bash
# 1. Register at https://modelscope.cn → get your SDK Token
# 2. Uncomment these three lines in .env:
OPENAI_API_KEY=ms-your-token-here
OPENAI_BASE_URL=https://api-inference.modelscope.cn/v1
DEFAULT_PROVIDER=modelscope
DEFAULT_MODEL=Qwen/Qwen3-235B-A22B
```

Other providers: DeepSeek (¥5-10/novel), DashScope (¥4/M tokens), Claude ($15/M output), Ollama (free, local GPU).

> Pricing in `src/utils/cost_calculator.py` uses each provider's native currency. Anthropic, OpenAI, and OpenRouter prices are in USD per million tokens. DashScope and ModelScope prices are in CNY. `estimate.format(display_currency="CNY")` converts the display currency, and `print_cost_comparison()` shows native prices and approximate USD equivalents. The `USD_TO_CNY` rate defaults to 7.2 for comparison. Actual charges depend on provider pricing and billing.

### 3. Launch

```bash
uv run novel-agent
# Or: uv run python -m src.main
```

Open **http://127.0.0.1:8000** in your browser.

### 4. Write Your Novel

1. Enter your novel idea, genre, and target audience
2. Click through the pipeline phases — each phase builds on the previous one
3. Watch as agents collaborate: outline → characters → chapters → review → polish
4. Export finished chapters as `.docx`

### Import Wattpad and Royal Road research

1. In **Workspace**, click **Import Research**. This opens the form and creates a draft project if needed.
2. Click **Load Sample CSV** and keep both synthetic rows to try the full flow. For your own research, replace the example rows with observations from an English-language Wattpad genre or tag list or from Royal Road's Rising Stars or Best Rated. Record the exact list and date. Use short notes in your own words.
3. Click **Analyze Snapshots**. Check the counts, lists, and dates, then click **Continue to Topic Research**.
4. Select a concept, generate and edit its title and synopsis, then confirm to generate an opening arc. To start worldbuilding directly, choose **Skip to Writing** in the import form.

The six required CSV columns are `platform,list_name,source_url,captured_on,story_url,title`. Use `wattpad` or `royal_road`, an ISO date such as `2026-01-01`, and HTTPS platform links. Use the main story page URL with its numeric story ID. Optional columns are `filters,language,fiction_type,rank,tags,reads,votes,views,followers,rating,note`. Use `en` when the story language is known, separate tags with `|`, and quote cells containing commas. Optional cells may be blank. Enter counts as whole numbers and ratings on a 0–5 scale. Keep one story row per list and date. The same work can appear on other lists.

```csv
platform,list_name,source_url,captured_on,story_url,title,language,rank,tags,note
wattpad,Fantasy example,https://www.wattpad.com/,2026-01-01,https://www.wattpad.com/story/101-example,Example Moon Garden,en,3,Fantasy|Romance,A gardener inherits a moonlit estate.
royal_road,Rising Stars example,https://www.royalroad.com/fictions/rising-stars,2026-01-01,https://www.royalroad.com/fiction/201/example,Example Clockwork Map,en,,Fantasy|Progression,A map grows as its maker completes challenges.
```

Each validated import replaces the project's staged snapshot on disk. An active run and its retries keep the snapshot pinned at start. Choose **Replace Snapshot** at the scan confirmation to apply a new import to that run. **Skip to Writing** bypasses the staged snapshot. The default workflow checkpointer is in memory, so after a server restart the saved import can be used to start research again. Earlier project artifacts and old checkpoint fields retain their original source labels.

List observations describe a dated sample. Platform counts have different meanings, and missing values stay unknown. Topic scores average six creative dimensions and, when available, one market dimension made from the mean of the supported platform-fit scores. Each platform assessment requires cited English-language observations. Listing metadata can inform positioning and a promised payoff. Actual chapter structure stays unknown from a listing. The app uses the imported data and opens provenance links on request. It has no live collection dependency.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Web UI (Vanilla JS)                    │
│              Real-time WebSocket progress                 │
└──────────────────────┬───────────────────────────────────┘
                       │ FastAPI + WebSocket
┌──────────────────────▼───────────────────────────────────┐
│                   Orchestrator Agent                      │
│              Coordinates 12-agent pipeline                │
└──────┬───────┬───────┬───────┬───────┬──────────────────┘
       │       │       │       │       │
  ┌────▼──┐ ┌─▼──┐ ┌──▼──┐ ┌─▼───┐ ┌─▼──────┐
  │Topic  │ │Arch│ │Char │ │Plot │ │Writer   │   Creative
  │Scout  │ │itect│ │Mgr │ │Plan │ │(2-pass) │   Tier
  └───────┘ └────┘ └─────┘ └─────┘ └────────┘
  ┌───────┐ ┌────┐ ┌─────┐ ┌─────┐ ┌────────┐
  │Editor │ │Cont│ │Read │ │Rev  │ │Refiner │   Review
  │       │ │inuity│ │Sim  │ │iewer│ │        │   Tier
  └───────┘ └────┘ └─────┘ └─────┘ └────────┘
                       │
              ┌────────▼────────┐
              │  Memory Manager  │   State
              │ (facts, states,  │   Tier
              │  foreshadowing)  │
              └─────────────────┘
```

### Project Structure

```
novel-agent/
├── src/
│   ├── agents/          # 12 AI agents (writer, editor, reviewer, etc.)
│   ├── api/             # FastAPI server, WebSocket, routes
│   ├── config/          # Settings, model assignments
│   ├── frontend/        # Web UI (index.html + vanilla JS + CSS)
│   ├── graph/           # ★ LangGraph workflow — the real runtime engine
│   │   ├── workflow.py  #   StateGraph: Phase 0 → bible → characters → outline → chapter loop
│   │   ├── nodes.py     #   Phase nodes (executors + persistence + progress broadcasts)
│   │   └── edges.py     #   Conditional routing: review accept/revise/rewrite, next-chapter/done
│   ├── llm/             # Model scheduler, providers, JSON repair
│   ├── models/          # Pydantic data models (outline, bible, chapter, etc.)
│   ├── storage/         # Workspace file I/O
│   └── utils/           # Jinja2 templates, helpers
├── tests/               # Unit + integration tests
├── .env.example         # Configuration template with 5 provider presets
├── pyproject.toml
└── README.md
```

### How the graph runs

The workflow is a **real LangGraph StateGraph** (`src/graph/workflow.py`) — the
FastAPI layer invokes it directly; there is no parallel hand-written loop.

- **Routing is live**: `edges.py` decides review accept/revise/rewrite (with
  `MAX_REVIEW_ITERATIONS` forcing acceptance) and the next-chapter/done
  transition; chapters loop until the outline's chapter count is reached.
- **Human-in-the-loop is `interrupt()`-based**: after each top-level phase
  (scan → topic → mini-arc → bible → characters → outline) the graph pauses;
  the API layer broadcasts `phase_blocked` and resumes with
  `Command(resume=...)` when you confirm — persisted by the checkpointer
  (MemorySaver, or AsyncSqliteSaver via `build_async_workflow(db_path)`).
- **Resume & skip are preserved**: completed artifacts are detected from disk,
  so re-running a project skips finished phases and resumes mid-chapter.


## Pipeline Phases

| Phase | Agent | What It Does |
|-------|-------|-------------|
| 1 | **Topic Scout** | Market analysis, trending topics, title generation |
| 2 | **Architect** | World-building bible (geography, magic system, factions) |
| 3 | **Character Manager** | Character profiles with arcs, flaws, motivations |
| 4 | **Plot Planner** | Master outline with volumes, chapters, turning points |
| 5 | **Writer** | Chapter drafts with scene-level planning + auto-expansion |
| 6 | **Editor** | Structural feedback, pacing, dialogue review |
| 7 | **Continuity Checker** | Fact consistency, timeline validation |
| 8 | **Reader Simulator** | Reader engagement scoring, "boring" detection |
| 9 | **Reviewer** | Adversarial review — finds blind spots |
| 10 | **Refiner** | Applies edits based on review feedback |
| ∞ | **Memory Manager** | Runs continuously: tracks world facts, character states, foreshadowing |

## Configuration

### Provider Presets

| Provider | Model (Quality) | Cost | Setup |
|----------|----------------|------|-------|
| **ModelScope** | Qwen3-235B | Free (2000 calls/day) | SDK Token |
| **DeepSeek** | deepseek-chat | ~¥5-10/novel | API Key |
| **DashScope** | qwen-max | ¥4/M output tokens | API Key |
| **Claude** | claude-sonnet-4 | $15/M output | API Key |
| **OpenAI** | gpt-4o | $10/M output | API Key |
| **OpenRouter** | 200+ models | Varies | API Key |
| **Ollama** | qwen3:32b | Free (local GPU) | None |

### Per-Agent Overrides

You can assign different models to different agents for cost optimization:

```bash
# Writer needs the best model — use Claude
WRITER_MODEL=anthropic:claude-sonnet-4-20250514
# Reviewers can use cheaper models
EDITOR_MODEL=deepseek-chat
CONTINUITY_CHECKER_MODEL=deepseek-chat
```

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_CHAPTER_WORD_COUNT` | 3000 | Target words per chapter |
| `MAX_REVIEW_ITERATIONS` | 3 | Max edit-review cycles |
| `MIN_REVIEW_SCORE_ACCEPT` | 6.5 | Minimum score to pass review |
| `MAX_CONTEXT_CHAPTERS` | 5 | Recent chapters in context window |
| `WORKSPACE_ROOT` | ./workspace | Where novels are saved |

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run unit tests (no API key needed, runs in < 1s)
uv run pytest tests/test_unit.py -v

# Run integration tests (needs API key configured in .env)
uv run pytest tests/ -v -k "modelscope"

# Run all tests
uv run pytest tests/ -v

# Run the app in dev mode
uv run python -m src.main
```

### Docker

On Linux with Docker's default UID/GID mapping, create `./workspace` as your regular host user. Compose runs the app as `1000:1000` by default. If your IDs differ, set `APP_UID` and `APP_GID` in `.env` to the values from `id -u` and `id -g`. With matching IDs, the app and your host account can edit each other's files in `./workspace`.

```bash
cp .env.example .env   # edit with your API key first
mkdir -p workspace
docker compose up -d --build
```

If an earlier container left `./workspace` or its contents owned by root, stop the old container and reclaim the existing files once:

```bash
docker compose stop
sudo chown -R "$(id -u):$(id -g)" ./workspace
docker compose up -d --build
```

To run without Compose, use the same `.env` and `workspace` paths:

```bash
docker build -t novel-agent .
docker run --user "$(id -u):$(id -g)" -p 8000:8000 \
  -e HOST=0.0.0.0 -e PORT=8000 -e WORKSPACE_ROOT=/app/workspace \
  --mount "type=bind,source=$PWD/.env,target=/app/.env,readonly" \
  --mount "type=bind,source=$PWD/workspace,target=/app/workspace" \
  novel-agent
```

### Testing

| Type | Command | API Key | What It Tests |
|------|---------|---------|---------------|
| **Unit** | `pytest tests/ -k "not modelscope"` | No | Pydantic models, JSON repair, content safety, prompts, settings, graph, feedback (126+ tests) |
| **Integration** | `pytest tests/ -v -k "modelscope"` | Yes | End-to-end agent pipeline against real LLMs |

CI runs the full non-integration suite on Python 3.11/3.12/3.13 on every push and PR via GitHub Actions.

## Memory retrieval evaluation

The benchmark uses 42 story facts and 30 timeline events from `eval/fixtures/memory`.

```bash
uv sync --extra rag
uv run python eval/eval_rag_retrieval.py
```

The script indexes the fixtures with `NovelVectorStore` and `Embedder`. It uses local Ollama `qwen3:8b` to paraphrase each entry into an English search query. If Ollama is unavailable, it searches with the original entry. Pass `--bge-model` to select a different embedding model or a local model path.

The checked-in `eval/rag_retrieval_results.json` records the original Chinese-language run: 100% recall@1 for facts, 86.7% recall@5 for events, and 0.78 event MRR. Running the script with the translated fixtures produces a new result.

## Product evaluation reports

The automated [AI Product Evaluation Framework](https://github.com/HuangLeijiana/ai-product-evaluation) assessed the project twice. It evaluates 19 criteria across five dimensions, with up to five points per dimension. A blocking issue can override the overall score.

| Report | Score | Findings |
|---|---|---|
| [v1.0](eval/evaluation_report.md) | **13.5 / 25** | Three blockers: no explicit feedback, no process for reviewing failed outputs, and no plan for collecting implicit feedback. |
| [v2.0](eval/evaluation_report_v2.md) | **16.0 / 25 (+2.5)** | The first two blockers were resolved, and implicit feedback collection became a condition for launch. All 44 new edge-case tests passed. The estimated Anthropic cost for 30 chapters fell from USD 12.30 to USD 7.04 (43%). |

## FAQ

**Q: Can I really write a complete novel for free?**
A: Yes. ModelScope provides 2000 free API calls per day. A 30-chapter novel uses ~150 calls (5 phases + 30 chapters × ~5 agent calls each).

**Q: What genre does it support?**
A: All genres. The system works with any setting — xianxia, sci-fi, romance, urban, horror. You define the genre and tone in the project config.

**Q: How much manual editing is needed?**
A: The pipeline produces complete, coherent drafts. Most users do light editing (dialogue polish, pacing tweaks) rather than rewrites. The multi-pass review system catches most issues automatically.

**Q: Can I write in other languages?**
A: English is the default. Set `language` in your project config to request another language supported by your model.

## License

MIT © [Huang Lei](https://github.com/HuangLeijiana)
