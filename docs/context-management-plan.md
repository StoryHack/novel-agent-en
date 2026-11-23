# Long Context Consistency Scheme

## Problem Definition

In current novels where writing spans over 50 chapters, what can be seen in each chapter are as follows:
- The entire world’s setting (static, unchanged for hundreds of chapters)
- Complete character profiles (static `current_state`, never updated after creation)
- A 200-word summary of the previous chapter
- A list of active plot threads (without descriptions)
- Unsolved hooks

What isn’t visible: What happened in Chapter 3, the evolution of characters over 50 chapters, the details of early plot threads, and established world facts.

In short, when the writer writes Chapter 200, their level of knowledge is similar to when they write Chapter 5. They only know about “the previous chapter that just happened” and “the world’s initial settings”.

## Comparison of Solutions

### Option A: Hierarchical Summarization

**Core Idea:** For every N chapters, the content is compressed into one level, creating a tree-like structure. During writing, the latest summaries from each level are integrated into the context of the chapter.

```
Chapter 1-10 → Stage Summary 1 ┐
Chapter 11-20 → Stage Summary 2 ├─→ Arc Summary I
Chapter 21-30 → Stage Summary 3 │
Chapter 31-40 → Stage Summary 4 ┘
...
Chapter 91-100 → Stage Summary 10 → Global Summary
```

**Contextual Information Integrated into Each Chapter:**
```
[Summary from previous chapter] 200 words
[Summary for the current stage] ~500 words (compression of the last 10 chapters)
[Summary for the current arc] ~800 words (compression of the last 50 chapters)
[Global Summary] ~1000 words (an overview of the entire book, updated every 100 chapters)
```

**Advantages:**
- Zero new dependencies; pure Python implementation.
- LLMs are naturally good at summarizing information (with the existing MemoryManagerAgent as a foundation).
- Zero latency in processing; no additional queries required.
- The total amount of contextual information is manageable (about 2500 words of summaries for the entire book).

**Disadvantages:**
- Information loss: Summaries may miss details that become important later on.
- The quality of summaries depends on the capabilities of the LLM.
- It’s impossible to accurately answer questions like “What happened to that person in Chapter 37?”

**Implementation Complexity:** ~200 lines of core logic + additional model-related code.

### Option B: Retrieval-Augmented Generation

**Core idea:** All chapter summaries/facts/events → embedding → vector database. When writing the Nth chapter, use “characters involved in this chapter, locations, and plotlines” as queries to retrieve the top K most relevant items from earlier chapters.

**Writing process:**
1. Extract key words from the chapter (character names, locations, plot themes).
2. Query = “Character A relationship Character B important events”.
3. Vector retrieval of the top 20 most relevant memories.
4. Injection: Summary from the previous chapter + relevant memories retrieved.

**Advantages:**
- Precise retrieval – only injects content related to the chapter.
- No information decay – original facts are stored in the vector database.
- Naturally handles long novels (can retrieve from 1,000 or more chapters).
- Supports “cross-chapter retrieval”: When writing Chapter 500, retrieve details from Chapter 50.

**Disadvantages:**
- **New dependencies:** Embedding model (local sentence-transformers or API) + vector storage (ChromaDB/Qdrant/lance).
- **Additional costs:** Costs of using an embedding API (if using cloud models), or local memory usage (~500MB for all-MiniLM-L6-v2).
- **Query construction matters:** If the query isn’t well-structured, the results won’t be useful.
- **Can’t replace global perception:** Retrieval only provides “points”; it can’t give you “surfaces” – writing still requires knowing where you are in the story and the overall rhythm.

**Implementation complexity:** ~500 lines of code + installation of new dependencies.

### Option C: Mixed Approach (Recommended)

**Hierarchical summaries provide a global context, while RAG provides precise retrieval capabilities.** These two approaches complement each other.

| Requirement | What to use | Why |
|------------|-------------|-------|
| Know which story arc one is in | Hierarchical summaries | Provides structural information without losing any details |
| Know the current state of characters | Memory.character_states (already available) | Structured data; no need for additional retrieval |
| Retrieve details about a particular character | RAG retrieval | Exact matching; summaries may miss some details |
| Retrieve information about the state of certain foreshadowings | ForeshadowingTracker (already available) | Structured tracking with precise results |
| Know the overall writing style and rules | Bible (static, already available) | Remains unchanged; injected each time needed |
| Ensure consistency across chapters | RAG retrieval + contradiction detection | Compare both sources |

**Total context length:**
```
1. [Static] Worldview + Style conventions – ~1000 tokens
2. [Structured] Information about characters and their current states – ~500 tokens
3. [Hierarchical summaries] Previous chapters, stages, arcs, and global summaries – ~1500 tokens
4. [RAG retrieval] Top 10 historical facts related to this chapter – ~500 tokens
5. [Structured] Details about active foreshadowings – ~300 tokens
6. [Chapter planning] Scenarios and emotional trends – ~500 tokens
─────────────────────────────────────────────────────────────
Total: ~4300 tokens
```

This is significantly less than 8192/16384 tokens. There’s plenty of room to write over 3000 words.

## Recommended implementation path

It can be carried out in two stages. First, create a hierarchical summary (which yields quick results). Then, add RAG as an additional step to enhance the results.

### Phase 1: Hierarchical Summaries (1-2 days)

**Changes made:**

1. **`models/memory.py`** – Added new fields:
```python
class LongTermMemory(BaseModel):
    # Existing fields remain unchanged…
    stage_summaries: dict[int, str] = {}  # stage_num -> 500-word stage summaries
    arc_summaries: dict[int, str] = {}    # arc_num -> 800-word arc summaries
    global_summary: str = ""            # Global summary of the entire book; updated every 100 chapters

class MemoryState(BaseModel):
    # New fields added:
    stage_boundaries: list[int] = []       # Chapter numbers representing stage boundaries, e.g., [10, 20, 30, …]
    arc_boundaries: list[int] = []         # Chapter numbers representing arc boundaries, e.g., [50, 100, 150, …]
```

2. **`agents/memory_manager.py`** – Added `consolidate_periodically()` method:
```python
async def consolidate_periodically(self, memory: MemoryState, chapter_num: int):
    """Generates stage summaries every 10 chapters, arc summaries every 50 chapters, and updates the global summary every 100 chapters."""
    if chapter_num % 10 == 0:
        stage_num = chapter_num // 10
        # Collect summaries for all chapters in that stage and compress them using LLM
        stage_summary = await self._generate_stage_summary(...)
        memory.long_term.stage_summaries[stage_num] = stage_summary

    if chapter_num % 50 == 0:
        # Collect summaries for all stages in that arc and compress them using LLM
        arc_summary = await self._generate_arc_summary(...)
        memory.long_term.arc_summaries[arc_num] = arc_summary

    if chapter_num % 100 == 0:
        # Compress the arc summaries with the LLM.
        memory.long_term.global_summary = await self._generate_global_summary(...)
```

3. **`agents/base.py`** – `build_context_block` uses hierarchical summaries:
```python
if memory:
    # Replace the previous logic that only used `short_term` summaries
    lt = memory.get("long_term", {})
    parts.append("=== Recent memories ===")
    parts.append(f"Previous chapter: {st.get('current_chapter_summary', '')}")

    # Hierarchical summaries
    stage = lt.get("stage_summaries", {})
    if stage:
        latest = stage[max(stage.keys())]
        parts.append(f"Current stage (last 10 chapters): {latest}")

    arc = lt.get("arc_summaries", {})
    if arc:
        latest = arc[max(arc.keys())]
        parts.append(f"Current arc (last 50 chapters): {latest}")

    if lt.get("global_summary"):
        parts.append(f"Overall summary of the book: {lt['global_summary']}")
```

4. **`agents/writer.py`** – `_build_full_context` adds additional facts for context building:
```python
# Filter relevant facts from long_term.facts based on role/place keywords
relevant = self._filter_relevant_facts(
    chapter_plan=chapter_plan,
    facts=memory.long_term.facts,
    max_facts=20,
)
```

5. **`api/routes.py`** – `start_workflow` restores the memory state:
```python
# Load memory along with the bible, characters, and outline.
memory = await file_manager.load_memory()
if memory:
    state.memory = memory
```

6. **`models/state.py`** — Fixing the issue with character state splitting:
```python
# In advance_chapter(), write the character states from memory back to the character registry.
for cid, state_updates in self.memory.character_states.items():
    if cid in self.characters.characters:
        self.characters.characters[cid].current_state.update(state_updates)
```

### Phase 2: RAG Retrieval (Can be developed in parallel)

1. **Vector Storage**: Choose `ChromaDB` (lightweight, zero-configuration, Python-native, SQLite backend).
2. **Embedding Model**: `BAAI/bge-small-zh-v1.5` (Chinese optimization, 512 dimensions, ~100MB in size, CPU-friendly).
3. **Index Contents**: Information related to each chapter, including chapter summaries, new facts, timeline events, and foreshadowings.
4. **Retrieval Triggers**:
   - `WriterAgent._build_full_context`: Retrieves information related to this chapter.
   - `ContinuityCheckerAgent`: Retrieves conflicting historical facts.
   - `PlotPlannerAgent.plan_chapter`: Retrieves relevant foreshadowings and unresolved clues.

**New Modules**:
```
src/
├── rag/
│   ├── __init__.py
│   ├── embedder.py      # Encapsulation of the embedding model
│   ├── store.py          # ChromaDB CRUD operations
│   └── retriever.py      # Query construction and retrieval logic
```

## Cost Analysis

| Option | Additional Dependencies | Additional LLM Calls per Chapter | Additional Costs per Chapter (Estimated) |
|-------|-------------------------|----------------------------------|--------------------------------------------|
| A: Hierarchical Summaries | None | 1 call per 10/50/100 chapters | ~0.001$ per chapter (depreciation) |
| B: Pure RAG | ChromaDB + Embedding Model | 1 embedding per chapter (approx. 10 items) | ~0.0001$ per chapter (local embedding) |
| C: Hybrid Approach | ChromaDB + Embedding Model | Summary calls from Option A + embedding per chapter | ~0.001$ per chapter |

The local embedding model (bge-small-zh) operates at a rate of about 5-10 ms per operation. With 10 items per chapter, the total time is less than 100 ms, so it has little impact on latency.

## Conclusion

It’s recommended to implement Phase 1 (hierarchical summaries) immediately. This is currently the most critical issue – the system has stored all the data in the `chapter_summaries`, `facts`, and `timeline` fields. However, there isn’t any mechanism for compressing or organizing this data. The changes are minimal, but they have an immediate effect.

As the next step, if hierarchical summaries aren’t sufficient (e.g., when it’s necessary to retrieve specific, less-known details), then adding an RAG layer is recommended. These two layers complement each other: the summaries provide the “big picture”, while RAG provides more detailed information about individual details.
