# AI Product Acceptance Review Report v2.0

## Basic Information
- **Product/Function Name**: Novel Agent v0.1.1 – Multi-Agent AI Novel Writing System
- **Review Date**: 2026-07-28 (Second review; optimization completed on the same day as v1.0 review)
- **Review Phase**: Alpha / Technical Preview (Optimization followed by re-review)
- **Reviewer**: AI Product Review Framework
- **North Star Metrics**: (Team did not specify) It is reasonable to assume that these metrics would include the human acceptance rate of generated chapters, and the average number of iterations required to complete a chapter until it is ready for publication.
- **Technical Stack**: LangGraph + FastAPI + Anthropic/OpenAI/OpenRouter/Ollama (multiple providers)
- **Score from Last Review**: 13.5/25 (v1.0, 2026-07-28)
- **Score for This Review**: 16.0/25 (+2.5 points increase)

### Evaluation of Data Sources

| Source | Description |
|--------|-------------|
| Source Code | All core modules in the src/ directory have been thoroughly reviewed. Additionally, 6 new modules have been reviewed this time. |
| Project Configuration | pyproject.toml, .env.example, model_assignments.py |
| Prompt Templates | Jinja2 templates used in writer/editor/reviewer. Also includes the version management system. |
| Test Coverage | The tests/ directory contains test cases ranging from 0 to 44. |
| Actual Execution | The cost calculator has been used to verify the cost ranges for 3 different model combinations. |

## Review Summary

| Dimension | Score (1-5) | v1 Score | Changes | Issues | Status |
|----------|-----------|--------|------|--------|------|
| I. Core Intelligence Layer | 4.0 | 4.0 | — | None | Pass (Excellent) |
| II. Experience and Interaction Layer | 2.5 | 2.5 | — | None | Needs improvement |
| III. Data and Flywheel Layer | 3.0 | 1.5 | **+1.5** | 1 issue | Significant improvement; 1 issue still needs fixing |
| IV. Cost and Commercialization Layer | 3.5 | 3.0 | **+0.5** | None | Needs improvement → Nearly pass |
| V. Security and Compliance Layer | 3.5 | 2.5 | **+1.0** | None | Needs improvement → Nearly pass |

**Overall Score**: 16.0 / 25 (v1: 13.5, +2.5)

**Overall Evaluation**: ⚠️ Excellent architecture. This round of improvements has been effective – 2 out of 3 issues in the Data Flywheel Layer have been resolved. Security and cost-related issues have also been addressed. It’s recommended to proceed with beta testing, with one condition attached.

## v1.0 → v2.0 Optimization Comparison Table

| v1.0 Issues/Problems | v2.0 Solutions | Status |
|-------------------|-----------------|---------|
| B1: No explicit feedback mechanism | `models/feedback.py` – FeedbackEntry model, 8 categories of reasons, API endpoints | ✅ Resolved |
| B2: No mechanism for managing bad cases | `GET /projects/{id}/feedback/bad-cases` – Automatically aggregating low-quality sections | ✅ Resolved |
| B3: No mechanism for implicit feedback | Not implemented yet (design documentation needs to be written) | ❌ Still a problem |
| No versioning for prompts | `config/prompts/prompt_versioning.py` – SHA-256 hash + diff + rollback | ✅ Resolved |
| No testing for edge cases | 44 tests covering 7 types of abnormal inputs | ✅ Resolved |
| No content safety checks | `utils/content_safety.py` – Keyword filtering, two levels of feedback: block/warning | ✅ Resolved |
| No cost budget table | `utils/cost_calculator.py` – 3 model combinations, revised scenario analysis | ✅ Resolved |

---

## Detailed Review

### I. Core Intelligence Layer – Score: 4.0/5
> This round of optimization has addressed the shortcomings in testing in edge scenarios. The core AI design (12 agents + three-layer quality control mechanisms + dynamic routing based on difficulty level) has been rated as excellent in version 1. No structural changes were made in this round of optimization.

#### Key Findings

**1. Edge scenario testing from 0 to 44 (Criterion 1 – significant improvement)**

The v1 review noted that the “tests/” directory was essentially empty. It’s a high-risk signal when a generative AI product doesn’t have a regression test set.

In this round, 3 test files were created, with 44 test cases covering 7 types of edge scenarios:
- Empty inputs/blank inputs
- Pure dialogue scenarios (dialogue ratio of 100%)
- Extremely long texts (<50 words vs >10,000 words)
- AI-generated text (highly AI-generated vs natural human text)
- Mixed Chinese-English texts
- Special characters (Emoji, HTML tags)
- Repetitive paragraphs/very short paragraphs

All 44 test cases passed. The tests covered ChapterInspector (15 cases), ContentSafetyChecker (15 cases), and Feedback model (14 cases).

**2. Multi-Agent architecture design (Criterion 5 – maintaining v1’s excellent rating)**

The differentiated model allocation strategy remains a strength: the creation phase uses Sonnet with a temperature of 0.7-0.9, while the inspection phase uses Haiku with a temperature of 0.3. There’s also an automatic failover mechanism between Primary and Fallback.

**3. Three-layer quality control mechanism (Criterion 3 – maintaining v1’s excellent rating)**

The design of Layer 0 (ChapterInspector) → Layer 1 (Editor+Continuity+Reader parallel processing) → Layer 2 (Re reviewer adversarial review) remains a rare “deep defense” mechanism in AI products.

**4. Areas that need attention (v1 legacy issues)**

- **No confidence-based output (Criterion 2):** The quality review results are binary: pass/fail (threshold 6.5). However, both scores of 6.4 and 8.9 indicate “pass”. This represents a significant loss of information. This issue wasn’t addressed in this round of testing.
- **No L1-L5 hallucination grading:** The adversarial review can detect plot holes, but there’s no systematic definition of hallucination levels. This issue wasn’t addressed in this round of testing either.

#### Blocking items: None

#### Improvement suggestions (sorted by priority)

1. 🟡 Important: Introduce a dimension-level confidence level for quality reviews. Instead of just a pass/fail evaluation, sections with low confidence levels should automatically trigger manual review.
2. 🟡 Important: Define L1-L5 levels of hallucinations for online writing scenarios. It’s important to ensure that there are no errors in L1 levels (such as character names, relationships, and key events).
3. 🟢 Optimization: Consider adding more checks to ChapterInspector, such as checking for flat emotional expressions in dialogue sequences, or uneven distribution of dialogue assignments.

### II. Experience and Interaction Layer – Score: 2.5/5
This round of optimization did not involve any changes to the experience layer. All of the findings and recommendations from the v1 review remain valid.

#### Key findings (to maintain v1 assessment)

**1. Human-in-the-loop design is correct (criteria 7, 10) — maintained**

The `human_confirmation` node supports four decision-making options: accept, revise, rewrite, and rollback. The architecture is correctly designed.

**2. Lack of user experience for creators (criteria 6, 8) — no improvement**

- No progressive disclosure. All issues are presented in the review report at once.
- No options for fixing errors in a “one-click” manner. There are no detailed options like “fixing role-related errors” or similar features.
- WebSocket is available, but not utilized effectively. There’s no streaming display of content based on chapters.

**3. Cold start issues (criteria 12) — no improvement**

No example libraries (Playbooks) are available. New users don’t know what to write when they are asked to “inspire their creativity” with just one sentence.

#### Blocking items: None

#### Improvement suggestions (Keep the v1 suggestions, with unchanged priority)

1. 🔴 Urgent: Create a “creative inspiration library” that covers at least 5 popular types of online articles.
2. 🔴 Urgent: Implement streaming output for chapter generation (WebSocket push tokens).
3. 🟡 Important: Design a “progressive disclosure” approach for design review reports: overall evaluation → dimension scoring → specific issues → detailed comments for each section.
4. 🟡 Important: Provide options for fine-grained error recovery.

### III. Data and Flywheel Layer – Score: 3.0/5 (v1: 1.5, +1.5)
> **The dimension where the most improvement was made in this round.** In v1, there were 3 blocking issues in this dimension. In this round, 2 of these blocking issues were resolved. The remaining 1 blocking issue (implicit feedback tracking) can be downgraded to a conditional issue during the Alpha phase.

#### Key Findings

**1. Explicit feedback entry: From scratch (Criterion 10 — ✅ Block B1 has been resolved)**

The v1 review noted that “human_confirmation has four buttons, but there are no 👍/👎 buttons, nor any tags for reasons.”

Current implementation:
- `models/feedback.py`: The `FeedbackEntry` model supports emotions like “thumbs_up” and “thumbs_down”, along with 8 categories of reasons.
  - Not as expected / Characters wrote poorly / Story is boring / AI influence is too strong / Rhythm issues / Dialogue problems / Worldbuilding issues / Others
- `HumanDecisionRequest` extension: Added fields for “sentiment” and “reason_tags”.
- `submit_human_decision` endpoint: Automatically records feedback and stores it in `feedback.json`.
- Intelligent inference: Automatically records `thumbs_down` when the user chooses revise, rewrite, or rollback.
- `GET /projects/{id}/feedback`: Returns a complete history of feedback along with `FeedbackSummary` (acceptance rate, reason distribution, trend direction).
- The `MainState` now has a `feedback_records` field to track feedback for each chapter.

**2. Management of bad cases: From scratch (Criterion 10 — ✅ Block B2 has been resolved)**

The v1 review noted that there was no automatic aggregation of chapters with low scores, nor any weekly summaries.

Current implementation:
- `GET /projects/{id}/feedback/bad-cases`: Automatically aggregates chapters with scores < 6.5, or those that have been revised ≥ 2 times.
  - Ranked by score from lowest to highest.
  - Top 5 reasons for rejection are listed.
- The `FeedbackSummary` model provides information like acceptance rate, reason distribution, score correlation, and trends (improving, declining, stable).

**3. Implicit feedback tracking: Not yet implemented (Criterion 10 — ❌ Block B3 still exists)**

The v1 review noted that there was no tracking of user engagement time, acceptance/rejection rates, or frequency of re-generetion after modifications.

No implicit feedback tracking has been implemented yet. However, the `revision_count` and `review_score` fields in the feedback model provide data structures for future tracking purposes.

**4. Data observability (Criterion 11) — No improvement**

There is still no annotation pipeline, model distillation/fine-tuning mechanisms, online verification framework, A/B testing capabilities, or a unified monitoring dashboard.

#### Blocked Items

| # | Blocked Items | v1 Status | v2 Status | Description |
|---|-------------|----------|----------|-------------|
| B1 | No explicit feedback mechanism | Not implemented | **✅ Implemented** | FeedbackEntry + API |
| B2 | No mechanism for handling bad cases | Not implemented | **✅ Implemented** | bad-cases endpoint |
| B3 | No buried data scheme (implicit feedback) | Not implemented | **⚠️ Downgraded to conditional requirement** | This can be delayed until 4 weeks after beta testing |

**Changes in blocked items: 3 items → 1 item (downgraded to conditional requirement)**

#### Improvement suggestions (sorted by priority)

1. 🔴 Urgent: Develop a document describing the implicit feedback tracking mechanism. This should include information on the number of times and content of user modifications, changes in satisfaction after revisions, and the proportion of users who accept the changes. This should be implemented within 4 weeks after beta testing.
2. 🟡 Important: Establish a unified monitoring dashboard (e.g., Grafana or similar tools). This would allow for tracking of usage/ costs/delay associated with each agent, as well as trends in quality scores for each section and user acceptance rates.
3. 🟡 Important: Develop an automated process for “marking → fine-tuning → verification”. Provide an expected improvement in F1 score over the next 3 months.
4. 🟢 Optimization: Analyze feedback data by scenario/user group.

### IV. Costs and Commercialization – Score: 3.5/5 (v1: 3.0, +0.5)
> **Two key gaps have been addressed:** The cost budget table and the management of Prompt versions. It has been upgraded from “conscious but not quantified” to “quantified and traceable”.

#### Key Findings

**1. Cost Budgeting: From scratch (Criterion 13 — ✅ Major improvement)**

The v1 review noted: “How much does it cost to write a 100,000-word online article, consisting of 30 chapters? — Unable to answer.”

This iteration has implemented `utils/cost_calculator.py`:

| Model Combination | Basic Cost for 30 Chapters | Cost with 30% revisions | Cost with 15% secondary revisions |
|-------------------|-------------------------|-----------------------|----------------------------------|
| **Sonnet+Haiku Combination (Recommended)** | **$7.04** | $8.17 | $9.30 |
| Full Sonnet Approach | $12.30 | $14.74 | $17.18 |
| Budgeted Approach (Primarily GPT-4o-mini) | $3.27 | $3.38 | $3.49 |

Key features:
- 3 preset model combinations (full_sonnet / sonnet_haiku_mixed / budget)
- Support for custom word count and number of chapters
- Costs are broken down by agent: Writer 45%, Review 25%, Polish 15%, Adversarial 10%, Memory 5%
- 3 scenarios for analysis: All in one go, 30% revisions, 15% secondary revisions
- `print_cost_comparison()` for quick comparison

**Conclusion:** The Sonnet+Haiku combination costs approximately **$7-9 USD** for writing a 30-chapter article. The full Sonnet approach costs around **$12-17 USD**. From a commercial SaaS subscription perspective, this cost level is completely acceptable.

**2. Prompt Version Management: From scratch (Criterion 14 — ✅ Major improvement)**

The v1 review noted: “The Jinja2 template exists in the code repository, but there is no version tracking or rollback mechanism.”

This iteration has implemented `config/prompts/prompt_versioning.py`:
- SHA-256 hash for integrity verification
- Automatic generation of unified diffs for each modification
- Complete record of changes, including timestamp, reason, and author
- Snapshots are stored in the `_versions/` directory, allowing rollback to any version
- `rollback(template_path, version)` – allows quick restoration to previous versions
- `verify_integrity()` – checks whether the template has been accidentally modified
- `get_changed_since(timestamp)` – helps identify the root cause of quality issues in prompts
- `scan_all()` – generates a summary of the version history of all templates

**3. Token Waste Issues (Criterion 14) – Some improvements have been made**
`build_context_block` (base.py:200) still builds the entire `world/bible/characters/outline/memory` context block each time. `max_context_chapters=5` limits the number of recent chapters. However, there is still no mechanism for paginating or loading data as needed for `bible` and `character` data.

**4. Business Attribution (Criterion 15)** – No improvement.

The recommended metrics for a good business strategy (proposed in v1) remain valid: chapter adoption rate, average number of revisions, time from project initiation to completion, NPS.

#### Blocking items: None (Alpha phase)
v1 review confirmation: “The Alpha phase can be postponed.” The cost budget has been completed, and the requirements of the Alpha phase have been met.

#### Improvement suggestions (sorted by priority)

1. 🟡 Important: Implement Prompt Caching for frequently used System Prompt segments. This will prevent the need to send the same world-setting information for each chapter.
2. 🟡 Important: Define the product’s key metrics (suggested: chapter adoption rate) and establish corresponding attribution links.
3. 🟢 Optimization: When the amount of Bible content exceeds a certain threshold, enable loading on demand. This way, the writer only needs to have access to the relevant world-building information for the current chapter, rather than all the information for that chapter.
4. 🟢 Optimization: Integrate a cost calculator into the project creation process. This will allow users to see an estimated cost before starting the project.

### V. Security, compliance, and explainability – Score: 3.5/5 (v1: 2.5, +1.0)
> **It addresses two major gaps: content security detection and prompt version management.** It has improved from having “risk awareness but no effective defenses” to having “basic defenses along with auditability.”

#### Key Findings

**1. Content Safety Barriers: From None to Present (Criterion 16 – ✅ Significant Improvement)**

The v1 review noted that “Writer Agent directly receives user ideas and generates chapters without any safety filtering. Although the content safety boundaries for creator tools are broader than those for customer service/educational products, zero detection is a risk.”

In this iteration, `utils/content_safety.py` is implemented as follows:
- **Block-level keywords**: Chapters with these keywords are rejected immediately. Examples include pornographic content like “sex” or “intercourse,” as well as extreme violence, such as dismemberment or skinning. Additionally, politically sensitive content is also blocked.
- **Warning-level keywords**: These keywords are marked but not blocked. Examples include suggestive content like “sugary breasts” or descriptions of violence, such as “blood and flesh.” Additionally, certain terms related to the platform are also blocked.
- These functions are integrated into `orchestrator.write_chapter`. They run after ChapterInspector and before LLM review, thereby avoiding unnecessary use of the LLM.
- `check_with_correction()` automatically replaces warning-level content with a marker indicating that the content has been edited.
- The `SafetyResult` includes context snippets (50 characters before and after the match), making it easier to review manually.
- It’s possible to customize the keywords based on the platform being used (e.g., Qidian, Tomato, Feilu). This functionality is already implemented, and more keywords can be added as needed.

**Location of Safety Checks**: After Layer 0 (structure checks by ChapterInspector), but before Layer 1 (parallel reviews by Editor+Continuity+Reader). This placement is effective because it prevents problems with structure and safety issues before they require expensive LLM reviews. This avoids wasting tokens.

**2. Improved Auditability of Prompt Versions Management (Criterion 17 – ✅ Improvement)**

The Prompt version management system serves both for tracking compliance and for audit purposes.

**3. Interpretability and Audits (Criterion 17) – Some Improvements**

Currently, there’s only `AgentLogEntry` + `LLMResponse` (model/provider/token/cost) + dimension_scores.

New in v2: Prompt version management, including change history, diff tracking, and one-click rollback.

Still missing: Strategy for releasing model versions in grayscale, rollback records, and automated rollback decisions.

**4. Bias Testing (Criterion 18) – No Improvement**

Bias issues related to gender stereotypes, regional/occupational stereotypes, and value systems remain unaddressed in the testing plan. This is a reasonable approach for the Alpha stage, but it needs to be included in the roadmap after beta testing.

**5. Exit Mechanism (Criterion 19 Additional) – No Improvement, but Risk Controllable**

There’s a natural way to downgrade: BibleMarkdownStore already allows for exporting Markdown files, allowing for manual writing. There’s no option to downgrade without AI assistance (e.g., “Turn off AI-generated content, keep only AI-reviewed content”).

#### Blocking items: None (Alpha phase)
The review in v1 confirmed that there were no blocking issues during the Alpha phase. After adding content security checks in this round, the security situation improved significantly. It has now been upgraded from “no defenses” to “basic defenses”.

#### Improvement suggestions (sorted by priority)

1. 🟡 Important: Expand the content security keyword database. This should be aligned with the latest auditing standards of target platforms like StartPoint/Tomato/Flylu. Additionally, a monthly update mechanism should be implemented.
2. 🟡 Important: Establish a minimal graying mechanism for model switching. The new writer prompts should be tested first on Chapter 5. After comparing the quality scores, they can be switched across all chapters.
3. 🟡 Important: Conduct a rollback experiment. This will help verify whether the rollback function of the Prompt version management system works properly in real-world scenarios.
4. 🟢 Optimization: Add checks for role bias. For example, measures should be taken to ensure that female characters make up a certain percentage of the dialogue content, and that there is diversity among villain characters. These measures should be included in the monthly quality audits.
5. 🟢 Optimization: Include regular statistics on the false positive rates and missed detections for security checks.

## Strategic Review Questions

> “When the accuracy of AI improves from 90% to 95%, it requires 10 million computing resources. When it improves to 96%, it requires another 20 million computing resources. What would you choose?”

**Translation for this product (v2 update):**

> “When switching from using only Sonnet to a combination of Sonnet and Haiku, the chapter adoption rate drops from 78% to 72%. However, the cost is reduced by 43% ($12.30 → $7.04). Would you spend the saved $5.26 on improving that 6% adoption rate, or would you use that money to improve the revision experience for the 28% of chapters that readers rejected?”

**New data support for v2:**

- For 30 chapters using only Sonnet: $12.30 (basic cost)
- For 30 chapters using a combination of Sonnet and Haiku: $7.04 (basic cost) – a savings of **43%**
- For 30 chapters using the budget plan: $3.27 (basic cost) – a savings of **73%**

However, there is no actual data to measure the impact on adoption rate. This data needs to be collected during beta testing.

**Judgment from reviewers:**

- ✅ The team has a clear understanding of investment returns. The cost calculator shows the cost differences between different options.
- ✅ The cost breakdown is clearly defined at the architectural level. ChapterInspector provides zero-cost pre-checks, while Haiku offers low-cost reviews.
- ✅ The Prompt version management system provides a “rollback” option in case things go wrong. This reduces the risk of costly optimizations.
- ⚠️ However, we need to be careful about the tendency to use too many agents. Currently, there are 12 agents, and adding one more agent increases latency and costs. It’s recommended to set a limit on the number of agents used.

**Suggested threshold for stopping improvements (v2 update):** When the chapter adoption rate reaches 85%, we should stop adding more agents or modifying prompts. Instead, we should focus on improving the overall experience for chapters that need revisions. With the `trend_direction` metric from `FeedbackSummary`, we can continuously monitor this trend during beta testing.

## Final Judgment

### ⚠️ Recommended for a closed beta, subject to conditions

### Conditional Requirements

**Must be completed before the beta test begins (1 item):**

1. **Design document for implicit feedback tracking**: This doesn’t need to be implemented immediately, but there must be a written plan. This document should define which user behaviors are considered “accepted” (no further revisions needed). It should also specify the data collection points and storage methods, as well as how to integrate this with existing explicit feedback data. This is the minimum requirement after downgrading the B3 blocker from the v1.0 review phase.

**Must be completed within 4 weeks after the beta test begins (4 items):**

1. **Implementation of implicit feedback tracking**: Implement the code according to the design document. The tracking coverage must be 100%.
2. **Expansion of content security keyword database**: Align with the review standards of at least 1 target platform (Qingdi/Tomato/Flylu).
3. **Unified monitoring dashboard**: A real-time dashboard that shows agent usage, costs, quality scores, and acceptance rates (e.g., Grafana or similar tools).
4. **Formal definition of key metrics**: Determine the core metrics (suggested: chapter acceptance rate). Establish a clear attribution link between these metrics.

**Must be completed within 8 weeks after the beta test begins (3 items):**

1. **Automated pipeline for data processing**: A complete design document covering labeling, fine-tuning, and verification steps.
2. **Grayscale release mechanism for models**: Implement a grayscale release mechanism for prompts. Test new prompts first on Chapter 5.
3. **Example libraries (Playbooks)**: Templates that provide inspiration for creating 5 types of popular online articles.

## Key features of the product (designs that deserve to be preserved and promoted)

1. **Three-tier quality control mechanism**: Structural inspection → multi-Agent parallel review → adversarial review. This is a rare “deep defense” mechanism found only in AI products.
2. **Model allocation based on Agent complexity**: Use Sonnet for creation purposes, and Haiku for inspection purposes. This is a smart approach to cost management. The cost calculator quantifies its value.
3. **Human-in-the-loop integration into the workflow**: This ensures architectural correctness. Explicit feedback during this process makes the process measurable.
4. **Bible Markdown export**: This provides natural vendor-lock-in protection.
5. **🎖️ New in v2: Explicit feedback + failed-output handling mechanisms**: The infrastructure for data-driven decision-making is in place. This is a significant step towards turning this from a “one-time project” into a “sustainable product”.
6. **🎖️ New in v2: Deterministic quality control mechanism**: ChapterInspector (for structural checks) and ContentSafetyChecker (for security checks) are run before expensive LLM-based reviews. This eliminates any additional costs.

## Appendix: Records of the review process

### Code coverage
- v1 coverage: agent (all 12 agents), graph (workflow + nodes + edges), llm (client + providers + scheduler), api (routes + websocket), config (settings + model_assignments), models (all data models), storage, prompt templates.
- New coverage in v2: `models/feedback.py` (135 lines), `utils/content_safety.py` (247 lines), `utils/cost_calculator.py` (393 lines), `config/prompts/prompt_versioning.py` (279 lines). Also, `models/state.py`, `api/routes.py`, and `agents/orchestrator.py` have been modified.

### Test Case Coverage
- v1: The “tests” directory is empty. Therefore, the test coverage is 0 ❌
- v2: There are 44 test cases. All of them passed ✅
  - ChapterInspector edge cases: 15 cases (empty inputs, pure dialogues, extreme lengths, AI-related content, mixed Chinese and English, special characters, repeated content)
  - ContentSafetyChecker: 15 cases (normal content, blocked content, warning messages, edge cases, correction modes)
  - Feedback model: 14 cases (positive/negative feedback, reason tags, serialization, aggregated summaries)

### Data Sources
- Source code and configuration files: Complete ✓
- Actual running data: The cost calculator has verified the cost ranges for 3 model combinations ✓
- User feedback data: The feedback model and API are in place; further testing is needed during beta testing ✓
- Cost reports: Upgraded from “data structure exists, but no running data” to “complete calculator system with comparison of 3 options” ✓
