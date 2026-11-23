"""Topic Scout Agent — market research and topic selection for commercial web novels.

Covers Steps 1-4 of the commercial writing pipeline:
  1A/1B: Platform Scanning (Feilu + Fanqie real rankings)
  1C: Cross-platform analysis
  2: Benchmark book skeleton analysis
  3A/3B: 12 candidate topics → scoring → top 4 → manual select 2
  4A: Title & synopsis generation
"""

import logging

from pydantic import AliasChoices, BaseModel, Field, field_validator

from ..models.topic import (
    BenchmarkReport,
    BenchmarkSkeleton,
    CandidateTopic,
    CandidateTopicsOutput,
    CrossPlatformEntry,
    CrossPlatformReport,
    MiniArcChapter,
    MiniArcOutline,
    ScanEntry,
    ScanReport,
    TitleSynopsisPair,
    TitleSynopsisReport,
    TopicScoreCard,
    TopicScoringReport,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


# ============================================================
# Structured output schemas for LLM responses
# ============================================================


class ScanReportOutput(BaseModel):
    """LLM output for platform scan analysis."""

    platform: str = Field(default="", description="Name of Platform", validation_alias=AliasChoices("platform", "平台名称"))
    list_name: str = Field(default="", description="List Name", validation_alias=AliasChoices("list_name", "榜单名称"))
    date: str = Field(default="", description="Scan Date", validation_alias=AliasChoices("date", "扫描日期"))
    entries: list[ScanEntry] = Field(default_factory=list)
    summary: str = Field(default="", description="Trend Summary", validation_alias=AliasChoices("summary", "趋势总结"))
    scan_failed: bool = Field(default=False)

    @field_validator("entries", mode="before")
    @classmethod
    def coerce_string_entries(cls, v: list) -> list:
        """Convert plain-string entries to ScanEntry objects on the fly."""
        if not v:
            return v
        result = []
        for i, item in enumerate(v):
            if isinstance(item, str):
                # LLM returned a bare book title → wrap as minimal ScanEntry
                result.append(ScanEntry(rank=i + 1, title=item))
            elif isinstance(item, dict):
                result.append(item)
            else:
                result.append(item)
        return result


class CrossPlatformOutput(BaseModel):
    """LLM output for cross-platform comparison."""

    entries: list[CrossPlatformEntry] = Field(default_factory=list)
    selected_directions: list[str] = Field(default_factory=list)


class BenchmarkOutput(BaseModel):
    """LLM output for benchmark skeleton analysis."""

    entries: list[BenchmarkSkeleton] = Field(default_factory=list)
    structural_summary: str = Field(default="")


class CandidateTopicsListOutput(BaseModel):
    """LLM output for 12 candidate topics."""

    topics: list[CandidateTopic] = Field(default_factory=list)


class TopicScoresOutput(BaseModel):
    """LLM output for topic scoring."""

    scores: list[TopicScoreCard] = Field(default_factory=list)
    top_4: list[str] = Field(default_factory=list)


class TitleSynopsisListOutput(BaseModel):
    """LLM output for title/synopsis generation."""

    genre_name: str = Field(default="")
    title_candidates: list[TitleSynopsisPair] = Field(default_factory=list)
    final_title: str = Field(default="")
    final_synopsis: str = Field(default="")


class MiniArcOutlineOutput(BaseModel):
    """LLM output for 10-chapter mini-arc outline."""

    genre_name: str = Field(default="")
    total_words: str = Field(default="20,000-21,000")
    chapters: list[MiniArcChapter] = Field(default_factory=list)
    arc_goal: str = Field(default="")
    next_arc_hook: str = Field(default="")


# ============================================================
# Agent
# ============================================================


class TopicScoutAgent(BaseAgent):
    """Market research and topic selection for commercial web novels.

    Implements the complete upstream pipeline: real platform scanning →
    cross-platform comparison → benchmark skeleton analysis →
    candidate topic generation → scoring → title/synopsis selection.

    Usage:
        agent = TopicScoutAgent(scheduler)
        # Step 1A: scan Feilu
        feilu = await agent.scan_feilu(page_content=feilu_html)
        # Step 1B: scan Fanqie
        fanqie = await agent.scan_fanqie(page_content=fanqie_html)
        # ... etc
    """

    agent_type = "topic_scout"

    # ================================================================
    # Step 1A: Feilu Rankings
    # ================================================================

    async def scan_platform(self, platform: str, page_content: str | None = None) -> ScanReport:
        """Scan a real platform rankings page and extract structured data.

        Tries structured generation first, falls back to plain-text generation
        + regex parsing on failure (needed for ModelScope which lacks JSON mode).

        Args:
            platform: 'Feilu' or 'Fanqie'
            page_content: Raw HTML or text content from the platform page.
                          If None/empty, the scan fails gracefully.

        Returns:
            ScanReport with entries and summary, or scan_failed=True.
        """
        if not page_content or not page_content.strip():
            logger.warning(f"{platform} scan: no page content provided → scan failed")
            return ScanReport(
                platform=platform,
                scan_failed=True,
                summary="Ranking scan failed because no page content was provided.",
            )

        system_prompt = self.build_system_prompt(
            role="web fiction rankings editor" if platform == "Feilu" else "web fiction market analyst",
            expertise=(
                f"You understand {platform}'s rankings, genre trends, and readers. "
                "Extract rank, title, genre, payoff, and premise from the supplied ranking data. "
                "Ground the analysis in the supplied page."
            ),
        )

        user_prompt = f"""Analyze the {platform} rankings below, one book at a time.

Ranking page:
{page_content[:15000]}

1. Extract at least ten real titles. If fewer are available, explain why.
2. Return a separate object for each book in entries. Copy titles and ranks exactly from the page. Infer other fields from title keywords, title structure, and genre conventions when needed.
3. Include these fields for each book:
   - rank: Numeric rank from the page
   - title: Exact title from the page
   - genre: Genre inferred from the title
   - title_appeal: What makes the title compelling, such as a contrast, a mystery, or a distinctive advantage
   - one_liner: The hook in one line, inferred from title and genre
   - golden_finger: The protagonist's signature advantage or the core premise
   - opening_pressure: Conflict or pressure at the start
   - pleasure_loop: Recurring source of reader satisfaction
4. Describe genre trends in summary.
5. Set scan_failed to true if you cannot extract any titles.
"""

        # Attempt 1: structured generation
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ScanReportOutput,
                temperature_override=0.3,
            )
            if result.entries and len(result.entries) >= 3:
                return ScanReport(
                    platform=result.platform or platform,
                    list_name=result.list_name,
                    date=result.date,
                    entries=[ScanEntry(**e.model_dump()) for e in result.entries],
                    summary=result.summary,
                    scan_failed=False,
                )
            logger.warning(
                f"{platform} structured scan returned only {len(result.entries or [])} entries → falling back to text"
            )
        except Exception as e:
            logger.warning(f"{platform} structured scan failed: {e} → falling back to text")

        # Attempt 2: plain-text generation + regex parsing
        logger.info(f"{platform}: falling back to text-based scan")
        try:
            text_prompt = (
                user_prompt
                + """

Return plain text with a line per book:
#Rank | Title | Genre | Title appeal | One-line hook | Signature advantage | Opening pressure | Payoff loop

Finish with this heading and two to four sentences describing the trends:
=== Trend Summary ===
"""
            )
            text_result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=text_prompt,
                temperature_override=0.3,
            )
            text = text_result.content if hasattr(text_result, "content") else str(text_result)
            entries = self._parse_text_scan_entries(text)

            if entries:
                import re

                summary_match = re.search(r"===?\s*(?:Trend Summary|趋势总结)\s*===?\s*\n(.+)", text, re.DOTALL | re.IGNORECASE)
                summary = summary_match.group(1).strip()[:200] if summary_match else f"{platform} ranking analysis complete"
                logger.info(f"{platform} text fallback: parsed {len(entries)} entries")
                return ScanReport(
                    platform=platform,
                    list_name=f"{platform} rankings",
                    date="",
                    entries=entries,
                    summary=summary,
                    scan_failed=False,
                )
        except Exception as e2:
            logger.error(f"{platform} text fallback also failed: {e2}")

        return ScanReport(platform=platform, scan_failed=True, summary="No titles could be extracted from the ranking page.")

    @staticmethod
    def _parse_text_scan_entries(text: str) -> list[ScanEntry]:
        """Parse pipe-delimited scan entries from plain-text LLM output.

        Expected format: #N | title | genre | title_appeal | one_liner | golden_finger | opening_pressure | pleasure_loop
        """

        entries = []
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            try:
                rank = int(parts[0].lstrip("#").strip())
            except ValueError:
                continue

            entries.append(
                ScanEntry(
                    rank=rank,
                    title=parts[1] if len(parts) > 1 else "",
                    genre=parts[2] if len(parts) > 2 else "",
                    title_appeal=parts[3] if len(parts) > 3 else "",
                    one_liner=parts[4] if len(parts) > 4 else "",
                    golden_finger=parts[5] if len(parts) > 5 else "",
                    opening_pressure=parts[6] if len(parts) > 6 else "",
                    pleasure_loop=parts[7] if len(parts) > 7 else "",
                )
            )
        return entries

    async def scan_feilu(self, page_content: str | None = None) -> ScanReport:
        """Scan the Feilu novel rankings."""
        return await self.scan_platform("Feilu", page_content)

    async def scan_fanqie(self, page_content: str | None = None) -> ScanReport:
        """Scan the Fanqie novel rankings.

        For Fanqie, the scraper already produces clean structured text.
        We use the direct parser to extract clean book entries (no LLM needed
        for extraction), then enrich with LLM-based genre/market analysis.
        """
        if not page_content or not page_content.strip():
            logger.warning("Fanqie scan: no page content provided → scan failed")
            return ScanReport(
                platform="Fanqie",
                scan_failed=True,
                summary="Ranking scan failed because no page content was provided.",
            )

        # Step 1: Direct parse to get clean book titles + abstracts
        direct_entries = self._parse_fanqie_scraper_text(page_content)
        if direct_entries:
            logger.info(f"Fanqie direct parse: {len(direct_entries)} books")

            # Step 2: Enrich with LLM analysis (genre, golden_finger, trend summary)
            enriched, trend_summary = await self._enrich_fanqie_with_llm(page_content, direct_entries)
            if enriched:
                summary = trend_summary or f"Fanqie rankings: analyzed {len(enriched)} books."
                return ScanReport(
                    platform="Fanqie",
                    list_name="Combined rankings (new and most read, across both readerships)",
                    date="",
                    entries=enriched,
                    summary=summary,
                    scan_failed=False,
                )

            # LLM enrichment failed — return direct-parsed entries
            return ScanReport(
                platform="Fanqie",
                list_name="Combined rankings (new and most read, across both readerships)",
                date="",
                entries=direct_entries,
                summary=f"Fanqie rankings: extracted {len(direct_entries)} titles and synopses. Genre analysis is unavailable.",
                scan_failed=False,
            )

        # Direct parsing failed — fall back to full LLM scan (like Feilu)
        logger.info("Fanqie direct parse failed, falling back to LLM scan")
        return await self.scan_platform("Fanqie", page_content)

    async def _enrich_fanqie_with_llm(
        self, page_content: str, direct_entries: list[ScanEntry]
    ) -> tuple[list[ScanEntry] | None, str]:
        """Use LLM to enrich Fanqie entries with genre analysis and trend summary.

        Uses plain-text generation (not structured output) for reliability
        with all API providers. Parses the result with regex.
        """
        system_prompt = self.build_system_prompt(
            role="web fiction market analyst",
            expertise=(
                "Identify genres, title appeal, signature advantages, opening conflict, and payoff patterns in the Fanqie rankings."
            ),
        )

        book_list = "\n".join(
            f"#{e.rank} 《{e.title}》" + (f" — {e.one_liner[:80]}" if e.one_liner else "") for e in direct_entries[:15]
        )

        user_prompt = f"""Analyze the following Fanqie rankings. Identify each book's genre and core premise, then summarize the overall trends.

Ranking data:
{book_list}

Use this format:

=== Trend Summary ===
Write two to four sentences on the overall trends.

=== Book-by-Book Analysis ===
#Rank | Genre | Title appeal | Signature advantage | Opening pressure | Payoff loop
#1 | Urban fiction | Contrasting identities | Returning war hero | A broken engagement | A comeback that proves doubters wrong
#2 | Historical romance | ... | ... | ... | ...

Keep the original ranks and titles. Give each book exactly one line."""

        try:
            result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature_override=0.4,
            )
            text = result.content if hasattr(result, "content") else str(result)

            # Parse trend summary
            import re

            summary_match = re.search(r"===?\s*(?:Trend Summary|趋势总结)\s*===?\s*\n(.+?)(?:\n===|\n\n===|\Z)", text, re.DOTALL | re.IGNORECASE)
            summary = summary_match.group(1).strip() if summary_match else ""

            # Parse per-book analysis
            enriched = []
            for line in text.split("\n"):
                line = line.strip()
                if not line.startswith("#"):
                    continue
                # Format: #N | genre | title_appeal | golden_finger | opening_pressure | pleasure_loop
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue

                try:
                    rank = int(parts[0].lstrip("#").strip())
                except ValueError:
                    continue

                # Find matching direct entry
                direct = next((d for d in direct_entries if d.rank == rank), None)
                title = direct.title if direct else parts[0]

                enriched.append(
                    ScanEntry(
                        rank=rank,
                        title=title,
                        genre=parts[1] if len(parts) > 1 else "",
                        title_appeal=parts[2] if len(parts) > 2 else "",
                        golden_finger=parts[3] if len(parts) > 3 else "",
                        opening_pressure=parts[4] if len(parts) > 4 else "",
                        pleasure_loop=parts[5] if len(parts) > 5 else "",
                        one_liner=direct.one_liner if direct else "",
                    )
                )

            if enriched:
                return enriched, summary
        except Exception as e:
            logger.warning(f"Fanqie LLM enrichment failed: {e}")

        return None, ""

    @staticmethod
    def _parse_fanqie_scraper_text(text: str) -> list[ScanEntry]:
        """Parse Fanqie scraper output directly into ScanEntry list.

        The scraper produces formatted text like:
            ===== Fanqie's list data (X copies covering...) =====

            #1 《Book Title》 Author: Author Name
                Synopsis: synopsis text
            #2 《Book Title》 Author: Author Name
                Synopsis: synopsis text

        Multi-line abstracts are handled (new entries start with #N pattern).
        """
        import re

        entries = []
        # Split into entry blocks: each starts with #N pattern
        # Remove the header line
        lines = text.strip().split("\n")

        # Collect entry blocks
        current_block = []
        for line in lines:
            # Strip whitespace but preserve the content
            stripped = line.strip()
            # Detect start of a new entry: #N 《 or #N（
            if re.match(r"^#\d+\s*[《（]", stripped):
                if current_block:
                    entry = TopicScoutAgent._parse_one_fanqie_block(current_block)
                    if entry:
                        entries.append(entry)
                current_block = [stripped]
            elif current_block:  # continuation of current entry (e.g. multi-line abstract)
                current_block.append(stripped)

        # Don't forget the last block
        if current_block:
            entry = TopicScoutAgent._parse_one_fanqie_block(current_block)
            if entry:
                entries.append(entry)

        return entries

    @staticmethod
    def _parse_one_fanqie_block(lines: list[str]) -> ScanEntry | None:
        """Parse a single Fanqie book entry block into a ScanEntry."""
        import re

        if not lines:
            return None

        first_line = lines[0]
        # Extract rank: #1, #2, etc.
        rank_match = re.match(r"^#(\d+)", first_line)
        rank = int(rank_match.group(1)) if rank_match else 0

        # Extract title from 《...》
        title_match = re.search(r"《(.+?)》", first_line)
        title = title_match.group(1).strip() if title_match else ""

        # Extractor from:...
        author_match = re.search(r"(?:Author|作者)[：:]\s*(.+?)$", first_line, re.IGNORECASE)
        author = author_match.group(1).strip() if author_match else ""

        # Extract abstract from subsequent lines
        abstract = ""
        for line in lines[1:]:
            # Remove Profile: Prefix
            clean = re.sub(r"^(?:Synopsis|简介)[：:]\s*", "", line, flags=re.IGNORECASE)
            if clean:
                abstract += clean

        if not title:
            return None

        return ScanEntry(
            rank=rank,
            title=title,
            genre="",
            title_appeal="",
            one_liner=abstract[:200] if abstract else f"Author: {author}" if author else "",
            golden_finger="",
            opening_pressure="",
            pleasure_loop="",
        )

    # ================================================================
    # Step 1C: Cross-platform analysis
    # ================================================================

    async def cross_platform_analysis(self, feilu: ScanReport | None, fanqie: ScanReport | None) -> CrossPlatformReport:
        """Step 1C: Cross-platform comparison — narrow down topic directions.

        Works with whatever platform data is available. If only one platform
        has data, analyzes that platform alone and produces directions.
        Falls back to extracting genre keywords from scan entries when the
        LLM produces no directions.
        """
        feilu_ok = feilu is not None and not feilu.scan_failed and len(feilu.entries) > 0
        fanqie_ok = fanqie is not None and not fanqie.scan_failed and len(fanqie.entries) > 0

        # If no platform data at all, return empty
        if not feilu_ok and not fanqie_ok:
            logger.warning("Cross-platform analysis: no valid scan data from either platform")
            return CrossPlatformReport()

        feilu_text = self._format_scan_for_prompt(feilu) if feilu else "[no Feilu data]"
        fanqie_text = self._format_scan_for_prompt(fanqie) if fanqie else "[No Fanqie data available]"

        # Adjust role and prompt based on data availability
        if feilu_ok and fanqie_ok:
            role = "cross-platform web fiction analyst"
            expertise = (
                "Compare genre trends and reader preferences across Feilu and Fanqie using the supplied rankings."
            )
            prompt_intro = 'Use the supplied rankings to make a cross-platform comparison.'
        else:
            role = "web fiction market analyst"
            platform_name = "Feilu" if feilu_ok else "Fanqie"
            expertise = (
                f"Identify popular genres and promising directions using the {platform_name} rankings."
            )
            prompt_intro = f"Identify popular genres and recommend story directions based on the following {platform_name} rankings."

        system_prompt = self.build_system_prompt(role=role, expertise=expertise)

        user_prompt = f"""{prompt_intro}

=== A. Feilu Rankings ===
{feilu_text}

=== B. Fanqie Rankings ===
{fanqie_text}

Use one row per genre:

| Genre | Popular on Feilu? | Established Fanqie audience? | Feilu reader appeal | Adaptations for Fanqie | Risks | Recommendation |

Choose 3–5 promising directions for further benchmark analysis and put them in selected_directions."""

        # Attempt 1: structured generation
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=CrossPlatformOutput,
                temperature_override=0.5,
            )
            if result.selected_directions:
                return CrossPlatformReport(
                    entries=[CrossPlatformEntry(**e.model_dump()) for e in result.entries] if result.entries else [],
                    selected_directions=result.selected_directions,
                )
            logger.warning("Cross-platform structured output: no selected_directions → falling back to text")
        except Exception as e:
            logger.warning(f"Cross-platform structured generation failed: {e} → falling back to text")

        # Attempt 2: plain-text generation + regex parsing
        try:
            text_prompt = (
                user_prompt
                + """

List recommended directions, one per line, using this format:
Recommended Direction: Genre 1
Recommended Direction: Genre 2
Recommended Direction: Genre 3
"""
            )
            text_result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=text_prompt,
                temperature_override=0.5,
            )
            text = text_result.content if hasattr(text_result, "content") else str(text_result)
            import re

            directions = re.findall(r"(?:Recommended Direction|推荐方向)[：:]\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
            directions = [d.strip() for d in directions if d.strip()]
            if directions:
                logger.info(f"Cross-platform text fallback: {len(directions)} directions")
                return CrossPlatformReport(selected_directions=directions[:5])
        except Exception as e2:
            logger.error(f"Cross-platform text fallback also failed: {e2}")

        # Attempt 3: extract genres directly from scan data
        scan_entries = []
        if feilu_ok:
            scan_entries.extend(feilu.entries)
        if fanqie_ok:
            scan_entries.extend(fanqie.entries)

        genre_set: set[str] = set()
        for entry in scan_entries[:20]:
            g = (entry.genre or "").strip()
            if g:
                for sub in g.replace("／", "/").split("/"):
                    sub = sub.strip()
                    if sub:
                        genre_set.add(sub)

        if genre_set:
            logger.info(f"Cross-platform genre fallback: {len(genre_set)} genres from scan data")
            return CrossPlatformReport(selected_directions=list(genre_set)[:5])

        return CrossPlatformReport()

    # ================================================================
    # Step 2: Benchmark book analysis
    # ================================================================

    async def analyze_benchmarks(
        self,
        directions: list[str],
        feilu_scan: ScanReport | None = None,
        fanqie_scan: ScanReport | None = None,
    ) -> BenchmarkReport:
        """Step 2: Analyze benchmark book skeletons.

        For each retained direction, pick 2 representative books and
        extract their structural skeleton (not the content).
        """
        context = ""
        if feilu_scan:
            context += f"\n Feilu:{self._format_scan_for_prompt(feilu_scan)}"
        if fanqie_scan:
            context += f"\n Fanqie:{self._format_scan_for_prompt(fanqie_scan)}"

        system_prompt = self.build_system_prompt(
            role="web fiction story analyst",
            expertise=(
                "Identify the structural patterns behind a book's opening, signature advantage, pressure, and payoff loop. "
                "Distinguish techniques that can be adapted from story details that require an original approach."
            ),
        )

        user_prompt = f"""Choose the two most representative benchmark books for each direction, for 6–10 books total.

Selected directions:
{chr(10).join(f"- {d}" for d in directions)}
{context}

Extract structural patterns without reproducing the books' plots or prose. Analyze each book using these fields:

| Title | Genre | Title appeal | Payoff promised by synopsis | Protagonist's starting position | Signature advantage or hidden strength | Opening pressure | How the first arc starts | Payoff loop | Elements worth adapting | Elements to replace for originality |

Summarize the strongest structural pattern for each genre.
"""

        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=BenchmarkOutput,
                temperature_override=0.5,
            )
            return BenchmarkReport(
                entries=[BenchmarkSkeleton(**e.model_dump()) for e in result.entries] if result.entries else [],
                structural_summary=result.structural_summary,
            )
        except Exception as e:
            logger.error(f"Benchmark analysis error: {e}")
            return BenchmarkReport()

    # ================================================================
    # Step 3A: Generate 12 candidates
    # ================================================================

    async def generate_topics(
        self,
        cross_platform: CrossPlatformReport,
        benchmarks: BenchmarkReport,
    ) -> CandidateTopicsOutput:
        """Step 3A: Generate 12 candidate topics from research.

        Generates in 3 batches of 4 to reduce structured-output complexity.
        Falls back to text-based parsing if structured generation fails.
        """
        cross_text = self._format_cross_platform(cross_platform)
        bench_text = self._format_benchmarks(benchmarks)

        system_prompt = self.build_system_prompt(
            role="web fiction concept designer",
            expertise=(
                "Develop commercially viable web fiction concepts from market research. "
                "Use original characters, openings, events, advantages, and payoffs that suit Fanqie and are easy to explain in a short video."
            ),
        )

        base_prompt = f"""Generate candidate concepts using the ranking analysis and benchmark books.

Cross-platform analysis:
{cross_text}

Benchmark structures:
{bench_text}

Use structural inspiration from the benchmarks and create original characters, openings, events, signature advantages, and payoffs. Each concept should suit Fanqie readers, be easy to explain in a short video, and support a complete opening arc of roughly ten chapters.

For each concept, include:
- genre_name: Genre name
- one_line_setting: Premise in one sentence
- golden_finger: Protagonist's signature advantage
- chapter1_conflict: First-chapter conflict
- first_event_direction: Direction of the opening arc
- first_pleasure_wave: First major payoff
- tomato_fit: high/medium/low
- video_potential: high/medium/low
- risk: Risks to consider"""

        all_topics = []
        # Generate in 3 batches of 4 to reduce per-call complexity
        for batch_idx in range(3):
            batch_num = batch_idx + 1
            batch_prompt = (
                base_prompt
                + f"\n\nGenerate batch {batch_num} with exactly four concepts (numbers {batch_idx * 4 + 1}–{batch_idx * 4 + 4})."
            )

            batch_topics = await self._generate_topic_batch(
                system_prompt=system_prompt,
                user_prompt=batch_prompt,
                batch_num=batch_num,
            )
            all_topics.extend(batch_topics)
            logger.info(f"Batch {batch_num}: generated {len(batch_topics)} topics")

        logger.info(f"Total topics generated: {len(all_topics)} across 3 batches")
        return CandidateTopicsOutput(topics=all_topics)

    async def _generate_topic_batch(self, system_prompt: str, user_prompt: str, batch_num: int) -> list[CandidateTopic]:
        """Generate one batch of topics. Falls back to text parsing if structured fails."""

        # Attempt 1: structured generation
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=CandidateTopicsListOutput,
                temperature_override=0.8,
            )
            if result.topics:
                return [CandidateTopic(**t.model_dump()) for t in result.topics]
        except Exception as e:
            logger.warning(f"Batch {batch_num} structured generation failed: {e}")

        # Attempt 2: plain text generation + regex parsing
        logger.info(f"Batch {batch_num}: falling back to text-based generation")
        try:
            text_result = await self.generate(
                system_prompt=system_prompt
                + "\n\nUse a Markdown ## heading for each concept and a list of fields in the form - field_name: value.",
                user_prompt=user_prompt,
                temperature_override=0.8,
            )
            topics = self._parse_text_topics(text_result.content)
            if topics:
                return topics
        except Exception as e2:
            logger.error(f"Batch {batch_num} text fallback also failed: {e2}")

        return []

    @staticmethod
    def _parse_text_topics(text: str) -> list[CandidateTopic]:
        """Parse markdown/text topic descriptions into CandidateTopic objects."""
        import re

        topics = []
        # Split by ## heading or numbered entries
        blocks = re.split(r"\n(?=## |\d+[\.\)]\s*)", text)

        for block in blocks:
            block = block.strip()
            if not block or len(block) < 20:
                continue

            # Extract fields with regex
            def _field(pattern, default=""):
                m = re.search(pattern, block, re.IGNORECASE)
                return m.group(1).strip() if m else default

            genre = _field(r"(?:题材名|genre_name)[：:]\s*(.+)", "")
            if not genre:
                # Try to get from heading
                m = re.match(r"##\s*(.+)", block)
                if m:
                    genre = m.group(1).strip()

            if not genre:
                continue

            topics.append(
                CandidateTopic(
                    genre_name=genre,
                    one_line_setting=_field(r"(?:一句话设定|one_line_setting)[：:]\s*(.+)"),
                    golden_finger=_field(r"(?:核心金手指|golden_finger)[：:]\s*(.+)"),
                    chapter1_conflict=_field(r"(?:第一章冲突|chapter1_conflict)[：:]\s*(.+)"),
                    first_event_direction=_field(r"(?:首个小事件闭环方向|first_event_direction)[：:]\s*(.+)"),
                    first_pleasure_wave=_field(r"(?:第一波爽点|first_pleasure_wave)[：:]\s*(.+)"),
                    tomato_fit=_field(r"(?:番茄适配度|tomato_fit)[：:]\s*(.+)", "medium"),
                    video_potential=_field(r"(?:视频表现力|video_potential)[：:]\s*(.+)", "medium"),
                    risk=_field(r"(?:风险点|risk)[：:]\s*(.+)"),
                )
            )

        return topics

    # ================================================================
    # Step 3B: Score candidate concepts
    # ================================================================

    async def score_topics(self, candidates: CandidateTopicsOutput) -> TopicScoringReport:
        """Step 3B: Score 12 candidates across 8 dimensions, recommend top 4.

        Does NOT make the final decision — outputs a score table and
        top-4 recommendation for human selection.
        """
        topics_text = self._format_candidates(candidates)

        system_prompt = self.build_system_prompt(
            role="web fiction concept evaluator",
            expertise=(
                "Rate commercial fit, creative stability, and promotional potential. Provide scores and concrete trade-offs so the author can decide."
            ),
        )

        user_prompt = f"""Score these 12 candidate concepts so the author can make the final decision.

Candidates:
{topics_text}

Score each criterion from 1 to 10:
1. Title appeal: Does the concept lend itself to a title readers will click?
2. Opening pressure: Does the first chapter introduce a strong conflict quickly?
3. Opening arc clarity: Can the first 10 chapters tell a complete story arc?
4. Signature advantage: Can the central premise sustain recurring payoffs?
5. Fanqie fit: Does the story suit readers of free-to-read fiction on Fanqie?
6. AI writing stability: Can an AI continue the story while respecting the premise?
7. Video potential: Can a short promotional video explain and sell the concept?
8. Continuity risk: How likely is the premise to break down in a long novel? Use low scores for high risk.

Provide all eight scores and the overall score for each concept. Rank the top four by overall score and explain the trade-offs for each choice.
"""

        # Attempt 1: structured generation
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=TopicScoresOutput,
                temperature_override=0.3,
            )
            if result.top_4 and len(result.top_4) >= 2:
                return TopicScoringReport(
                    scores=[TopicScoreCard(**s.model_dump()) for s in result.scores] if result.scores else [],
                    top_4=result.top_4,
                )
            logger.warning(
                f"Topic scoring structured: only {len(result.top_4 or [])} top entries → falling back to text"
            )
        except Exception as e:
            logger.warning(f"Topic scoring structured generation failed: {e} → falling back to text")

        # Attempt 2: plain-text generation + regex parsing
        logger.info("Topic scoring: falling back to text-based generation")
        import re

        try:
            text_prompt = (
                user_prompt
                + """

Use this format:

Top 4 Recommendations:
1. Genre 1
2. Genre 2
3. Genre 3
4. Genre 4

Scores:
#Rank | Genre | Title appeal | Opening pressure | Arc clarity | Signature advantage | Fanqie fit | AI stability | Video potential | Continuity risk | Overall score
"""
            )
            text_result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=text_prompt,
                temperature_override=0.3,
            )
            text = text_result.content if hasattr(text_result, "content") else str(text_result)

            # Parse top 4 from text
            top_4 = []
            top_match = re.search(r"(?:Top 4 Recommendations|推荐前4名)[：:]?\s*\n((?:[ \t]*\d+\.[^\n]+(?:\n|$))+)", text, re.IGNORECASE)
            if top_match:
                top_4 = re.findall(r"\d+\.\s*(.+?)(?:\n|$)", top_match.group(1))
                top_4 = [t.strip() for t in top_4 if t.strip()]
            if not top_4:
                # Try alternative formats
                top_4 = re.findall(r"(?:top|推荐)[\s_]*(?:4|四)[：:]\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
                if top_4:
                    top_4 = [t.strip() for t in re.split(r"[,，、]", top_4[0]) if t.strip()]

            if top_4:
                logger.info(f"Topic scoring text fallback: top_4={top_4}")
                return TopicScoringReport(top_4=top_4)
        except Exception as e2:
            logger.error(f"Topic scoring text fallback also failed: {e2}")

        # Attempt 3: use first 4 candidate genres directly
        logger.info("Topic scoring: using first 4 candidate genres as fallback")
        if candidates.topics:
            fallback_top_4 = [t.genre_name for t in candidates.topics[:4] if t.genre_name]
            if fallback_top_4:
                return TopicScoringReport(top_4=fallback_top_4)

        return TopicScoringReport()

    # ================================================================
    # Step 4A: Generate and assess titles and synopses
    # ================================================================

    async def generate_titles(self, genre_name: str, topic: CandidateTopic) -> TitleSynopsisReport:
        """Step 4A: Generate title + synopsis for one topic.

        Uses plain-text generation with regex parsing (not structured output)
        for reliability across all LLM providers including ModelScope.
        """
        system_prompt = self.build_system_prompt(
            role="web fiction marketing editor",
            expertise=(
                "Write clear, conflict-driven titles and concise synopses for free-to-read web fiction. "
                "Set expectations quickly, promise a payoff, and leave a hook suitable for short-form video promotion."
            ),
        )

        user_prompt = f"""Write a title and synopsis for this concept.

Concept:
- Genre: {genre_name}
- One-line premise: {topic.one_line_setting}
- Signature advantage: {topic.golden_finger}
- Chapter 1 conflict: {topic.chapter1_conflict}
- Opening arc direction: {topic.first_event_direction}
- First payoff: {topic.first_pleasure_wave}

Use this format:

Final Title: <title>
Synopsis: <2–4 sentences and 80–150 words that set expectations quickly, promise a payoff, and leave a hook>
"""

        # Attempt 1: structured generation (fast path for providers with JSON mode)
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=TitleSynopsisListOutput,
                temperature_override=0.8,
            )
            if result.final_title and result.final_synopsis:
                return TitleSynopsisReport(
                    genre_name=result.genre_name or genre_name,
                    title_candidates=[TitleSynopsisPair(**t.model_dump()) for t in result.title_candidates]
                    if result.title_candidates
                    else [],
                    final_title=result.final_title,
                    final_synopsis=result.final_synopsis,
                )
            logger.warning("Title structured: empty title/synopsis → falling back to text")
        except Exception as e:
            logger.warning(f"Title structured generation failed: {e} → falling back to text")

        # Attempt 2: plain-text generation + regex parsing
        try:
            text_result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature_override=0.8,
            )
            text = text_result.content if hasattr(text_result, "content") else str(text_result)
            import re

            # Parse: Final book name: XXX or XXX
            title_match = re.search(r"(?:(?:Final )?Title|(?:最终)?书名)[：:]\s*[《]?(.+?)[》]?(?:\n|$)", text, re.IGNORECASE)
            final_title = title_match.group(1).strip() if title_match else ""

            # Parse: Brief: XXX
            syn_match = re.search(r"(?:Synopsis|简介)[：:]\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL | re.IGNORECASE)
            final_synopsis = syn_match.group(1).strip() if syn_match else ""

            # Fallback: use first line as title if no match
            if not final_title:
                lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not ln.startswith("#")]
                if lines:
                    # Clean up common artifacts
                    first = re.sub(r"^[《「]|[》」]$", "", lines[0]).strip()
                    if len(first) >= 4:
                        final_title = first[:50]
                    if len(lines) >= 2:
                        final_synopsis = " ".join(lines[1:3])[:300]

            if final_title:
                logger.info(f"Title text fallback: '{final_title}' for '{genre_name}'")
                return TitleSynopsisReport(
                    genre_name=genre_name,
                    final_title=final_title,
                    final_synopsis=final_synopsis or topic.one_line_setting or f"A novel in the {genre_name} genre.",
                )
        except Exception as e2:
            logger.error(f"Title text fallback also failed: {e2}")

        # Attempt 3: build from topic data (no LLM)
        fallback_title = topic.one_line_setting or genre_name
        return TitleSynopsisReport(
            genre_name=genre_name,
            final_title=fallback_title[:50],
            final_synopsis=f"A {genre_name} novel featuring {topic.golden_finger or 'a signature advantage'}, {topic.chapter1_conflict or 'an immediate conflict'}, and {topic.first_pleasure_wave or 'recurring payoffs'}.",
        )

    # ================================================================
    # Step 5: 10 chapters self-contained opening arc outline
    # ================================================================

    async def plan_mini_arc(
        self,
        genre_name: str,
        topic: CandidateTopic,
        title_report: TitleSynopsisReport,
    ) -> MiniArcOutline:
        """Step 5: Design a 10-chapter mini-arc with a complete small event loop.

        Each chapter is 2000-2100 words, total ~20,000-21,000 words.
        The first small event must form a complete closed loop.

        Tries structured generation first, falls back to plain-text generation
        + regex parsing on failure (needed for ModelScope which lacks JSON mode).
        """
        system_prompt = self.build_system_prompt(
            role="web fiction outline designer",
            expertise=(
                "Plan a compact ten-chapter arc that builds from opening pressure to the protagonist's response and payoff. "
                "Resolve the first conflict and end with a hook for the next arc."
            ),
        )

        user_prompt = f"""Design a complete 10-chapter opening arc for this concept.

Concept:
- Genre: {genre_name}
- One-line premise: {topic.one_line_setting}
- Signature advantage: {topic.golden_finger}
- Chapter 1 conflict: {topic.chapter1_conflict}
- Opening arc direction: {topic.first_event_direction}
- First payoff: {topic.first_pleasure_wave}

Title: {title_report.final_title}
Synopsis: {title_report.final_synopsis}

Plan 2,000–2,100 words per chapter and about 20,000–21,000 words in total. Resolve the opening conflict within the arc.

For each chapter, describe the goal, conflict, payoff, new information, character change, foreshadowing, and ending hook.

Pacing:
- Chapter 1: Establish immediate pressure.
- Chapters 2–3: Show the world's rules and the protagonist's advantage.
- Chapters 4–7: Escalate obstacles and conflict.
- Chapters 8–9: Put the protagonist's response into motion.
- Chapter 10: Deliver the payoff, resolve the arc, and set up the next one.
"""

        # Attempt 1: structured generation
        try:
            result = await self.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=MiniArcOutlineOutput,
                temperature_override=0.6,
            )
            # Check chapters exist AND have actual content (not just empty shells)
            if result.chapters and len(result.chapters) >= 5:
                filled = sum(1 for c in result.chapters if c.goal or c.conflict or c.pleasure_point)
                if filled >= 5:
                    return MiniArcOutline(
                        genre_name=result.genre_name or genre_name,
                        total_words=result.total_words or "20,000-21,000",
                        chapters=[MiniArcChapter(**c.model_dump()) for c in result.chapters],
                        arc_goal=result.arc_goal,
                        next_arc_hook=result.next_arc_hook,
                    )
                logger.warning(
                    f"Mini-arc structured: {len(result.chapters)} chapters but only {filled} have content → falling back to text"
                )
            else:
                logger.warning(
                    f"Mini-arc structured: only {len(result.chapters or [])} chapters → falling back to text"
                )
        except Exception as e:
            logger.warning(f"Mini-arc structured generation failed: {e} → falling back to text")

        # Attempt 2: plain-text generation + regex parsing
        logger.info(f"Mini-arc for '{genre_name}': falling back to text-based generation")
        try:
            text_prompt = (
                user_prompt
                + """

Return all ten chapters in plain text using these labels:

Chapter 1
Chapter Goal: ...
Chapter Conflict: ...
Chapter Payoff: ...
New Information: ...
Character Change: ...
Foreshadowing: ...
Ending Hook: ...

Chapter 2
Chapter Goal: ...
(Repeat through Chapter 10.)

Arc Summary
Arc Goal: ...
Next Arc Hook: ...
"""
            )
            text_result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=text_prompt,
                temperature_override=0.6,
            )
            text = text_result.content if hasattr(text_result, "content") else str(text_result)
            chapters, arc_goal, next_hook = self._parse_text_mini_arc(text)

            if chapters and len(chapters) >= 5:
                logger.info(f"Mini-arc text fallback: parsed {len(chapters)} chapters for '{genre_name}'")
                return MiniArcOutline(
                    genre_name=genre_name,
                    total_words="20,000-21,000",
                    chapters=chapters,
                    arc_goal=arc_goal,
                    next_arc_hook=next_hook,
                )
            logger.warning(f"Text fallback produced only {len(chapters)} chapters → building deterministic chapters")
        except Exception as e2:
            logger.error(f"Mini-arc text fallback also failed: {e2}")

        # Attempt 3: deterministic chapter generation from topic data
        logger.info(f"Mini-arc for '{genre_name}': building deterministic chapters from topic data")
        return _build_deterministic_mini_arc(genre_name, topic, title_report)

    @staticmethod
    def _parse_text_mini_arc(text: str) -> tuple[list[MiniArcChapter], str, str]:
        """Parse plain-text mini-arc outline into chapter list.

        Accepts multiple formats:
          === Chapter N === / ## Chapter N / Chapter N / N.
        Accepts English and legacy Chinese labels.
        """
        import re

        heading = re.compile(
            r"^[ \t]*(?:={2,}[ \t]*|#{1,6}[ \t]*)?"
            r"(?:Chapter[ \t]+(\d+)\b|第[ \t]*(\d+)[ \t]*章|(\d+)[.)）、])",
            re.IGNORECASE | re.MULTILINE,
        )
        summary_heading = re.search(
            r"^[ \t]*(?:={2,}[ \t]*|#{1,6}[ \t]*)?(?:Arc Summary|Summary|闭环总结|总结|概要)\b",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        chapter_text = text[:summary_heading.start()] if summary_heading else text
        headings = list(heading.finditer(chapter_text))

        def field(block: str, labels: str) -> str:
            match = re.search(rf"^[ \t]*(?:[-*][ \t]+)?(?:{labels})[：:][ \t]*([^\n]+)", block, re.IGNORECASE | re.MULTILINE)
            return match.group(1).strip() if match else ""

        chapters = []
        for i, match in enumerate(headings):
            chapter_number = int(next(group for group in match.groups() if group is not None))
            if not 1 <= chapter_number <= 50:
                continue
            end = headings[i + 1].start() if i + 1 < len(headings) else len(chapter_text)
            block = chapter_text[match.end():end]
            chapters.append(
                MiniArcChapter(
                    chapter_number=chapter_number,
                    goal=field(block, r"(?:Chapter )?Goal|(?:本章)?目标"),
                    conflict=field(block, r"(?:Chapter )?Conflict|(?:本章)?冲突|矛盾"),
                    pleasure_point=field(block, r"(?:Chapter )?Payoff|(?:本章)?爽点"),
                    new_info=field(block, r"New Information|新(?:增)?信息"),
                    character_change=field(block, r"Character Change|人物(?:状态)?变化|人物状态"),
                    foreshadowing=field(block, r"Foreshadowing|伏笔(?:推进|推前)?"),
                    ending_hook=field(block, r"Ending Hook|(?:结尾)?钩子"),
                )
            )

        chapters.sort(key=lambda c: c.chapter_number)
        summary_text = text[summary_heading.end():] if summary_heading else text
        arc_goal = field(summary_text, r"Arc Goal|弧目标") or field(text, r"Arc Goal|弧目标")
        next_hook = field(summary_text, r"Next Arc Hook|下一弧钩子")
        if not next_hook and summary_heading:
            next_hook = field(summary_text, r"钩子")
        next_hook = next_hook or field(text, r"Next Arc Hook|下一弧钩子")

        return chapters, arc_goal, next_hook

    # ================================================================
    # Prompt formatters (private)
    # ================================================================

    @staticmethod
    def _format_scan_for_prompt(report: ScanReport) -> str:
        """Format a ScanReport as prompt text."""
        if report.scan_failed:
            return f"[{report.platform}] Ranking scan failed: {report.summary}"
        lines = [
            f"Platform: {report.platform}",
            f"Rankings: {report.list_name}",
            f"Date: {report.date}",
            f"{len(report.entries)} entries",
            "",
        ]
        for e in report.entries:
            lines.append(
                f"#{e.rank} {e.title} | Genre: {e.genre} | Signature advantage: {e.golden_finger} | Payoff loop: {e.pleasure_loop}"
            )
        lines.append(f"\nTrend summary: {report.summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_cross_platform(report: CrossPlatformReport) -> str:
        """Format a CrossPlatformReport as prompt text."""
        lines = []
        for e in report.entries:
            lines.append(
                f"- {e.genre}: Popular on Feilu: {'Yes' if e.feilu_heat else 'No'}, "
                f"Established Fanqie audience: {'Yes' if e.tomato_audience else 'No'}, "
                f"Feilu appeal: {e.feilu_appeal}, "
                f"Fanqie adaptation: {e.tomato_adjustment}, "
                f"Risk: {e.risk}, Recommendation: {e.recommendation}"
            )
        if report.selected_directions:
            lines.append(f"\nSelected directions: {', '.join(report.selected_directions)}")
        return "\n".join(lines)

    @staticmethod
    def _format_benchmarks(report: BenchmarkReport) -> str:
        """Format a BenchmarkReport as prompt text."""
        lines = []
        for e in report.entries:
            lines.append(
                f"- {e.title} ({e.genre}): "
                f"Start ={e.protagonist_opening}, signature advantage ={e.golden_finger}, "
                f"Payoff loop ={e.pleasure_loop}"
            )
        lines.append(f"\nStructure summary: {report.structural_summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_candidates(output: CandidateTopicsOutput) -> str:
        """Format CandidateTopicsOutput as prompt text."""
        lines = []
        for i, t in enumerate(output.topics, 1):
            lines.append(
                f"{i}. {t.genre_name}: {t.one_line_setting}\n"
                f"   Signature advantage: {t.golden_finger}, Chapter Conflict ={t.chapter1_conflict}, "
                f"Fanqie fit: {t.tomato_fit}, Video Performance ={t.video_potential}"
            )
        return "\n".join(lines)


# ============================================================
# Deterministic mini-arc builder (final fallback, no LLM)
# ============================================================


def _build_deterministic_mini_arc(
    genre_name: str,
    topic: "CandidateTopic",
    title_report: "TitleSynopsisReport",
) -> "MiniArcOutline":
    """Build a basic 10-chapter mini-arc outline from topic data with no LLM.

    This is the ultimate fallback when both structured and text generation fail.
    Uses standard web novel pacing: pressure → rules → obstacles → counterattack → payoff.
    """
    golden = topic.golden_finger or "Signature Advantage"
    conflict = topic.chapter1_conflict or "the opening conflict"
    pleasure = topic.first_pleasure_wave or "a satisfying comeback"
    title = title_report.final_title or genre_name

    chapter_template = [
        {
            "goal": f"Establish the opening conflict: {conflict}",
            "conflict": f"The protagonist faces {conflict}",
            "pleasure_point": "Use immediate pressure to make readers anticipate a reversal",
            "new_info": "Introduce the setting and the protagonist's circumstances",
            "character_change": "The main character has moved from passive to active response",
            "foreshadowing": f"Hint at {golden}",
            "ending_hook": f"The protagonist discovers a clue about {golden}",
        },
        {
            "goal": f"Show what {golden} can do",
            "conflict": "The lead tries to use signature advantage but encounters resistance",
            "pleasure_point": f"{golden} provides its first payoff",
            "new_info": f"Reveal the basic rules and limits of {golden}",
            "character_change": "The lead starts to build confidence",
            "foreshadowing": "Set up a larger revelation about the world",
            "ending_hook": f"The protagonist uses {golden} to win a small victory",
        },
        {
            "goal": "Create the lead's first little goal",
            "conflict": "The outside world is beginning to notice the change of the main actor",
            "pleasure_point": "The main character uses his power to solve a small problem",
            "new_info": "Showing the power system or social rules of the world",
            "character_change": "The main character is starting to plan the operation",
            "foreshadowing": "To introduce the first little villain or rival",
            "ending_hook": "The villains are beginning to notice the main character",
        },
        {
            "goal": "The main character suffered a first major setback",
            "conflict": "The opponent uses the rules or the power to suppress the main actor",
            "pleasure_point": "A setback reveals a new use for the protagonist's advantage",
            "new_info": "The background and motive of the opponent",
            "character_change": "The main character realizes the need to be strong",
            "foreshadowing": "Insinuate a bigger conspiracy",
            "ending_hook": "The main character is planning a counterattack",
        },
        {
            "goal": "The main character starts to set up a counterattack",
            "conflict": "Inadequate resources, need for allies or resources",
            "pleasure_point": "The protagonists use wisdom to gain access to critical resources or allies",
            "new_info": "Introduction of new roles (allies or mentors)",
            "character_change": "The protagonist gains support after working alone",
            "foreshadowing": "Plant a clue about the ally's identity",
            "ending_hook": "The preparation phase is complete. The operation is about to begin",
        },
        {
            "goal": "Stage the first direct confrontation",
            "conflict": f"The protagonist uses {golden} in a direct confrontation",
            "pleasure_point": "High-light moments in battle or battle",
            "new_info": "Discovering the weakness and secrets of the opponent",
            "character_change": "The main actor's experience in the field has grown",
            "foreshadowing": "There's more power behind the enemy",
            "ending_hook": "The protagonist drives off the opponent and discovers a greater threat",
        },
        {
            "goal": "The main character digests the gains and prepares for greater action",
            "conflict": "There's a new threat. The main character needs to be upgraded",
            "pleasure_point": f"Upgrade {golden} or reveal a new ability",
            "new_info": "To reveal a deeper view of the world",
            "character_change": "He grew up with both strength and mind",
            "foreshadowing": "Insinuating the existence of a boss in the end",
            "ending_hook": "The main character is determined to face the ultimate challenge",
        },
        {
            "goal": "The lead is on his way",
            "conflict": "Deep into the enemy's territory or sphere of influence",
            "pleasure_point": "The protagonist gains ground by repeatedly proving opponents wrong",
            "new_info": "To reveal the truth behind the events",
            "character_change": "From passive to active control",
            "foreshadowing": "Pay off earlier foreshadowing",
            "ending_hook": "We're on our way to a final match",
        },
        {
            "goal": "It's a duel",
            "conflict": "The main character fights the final enemy with all his might",
            "pleasure_point": "The peak payoff release",
            "new_info": "To reveal the full truth about what happened",
            "character_change": "The protagonist completes this phase of their growth",
            "foreshadowing": "Plant a clue for the next volume",
            "ending_hook": "Victory is on the horizon",
        },
        {
            "goal": "Resolve the opening storyline",
            "conflict": "Deal with the aftermath of the final confrontation",
            "pleasure_point": f"Deliver the full payoff: {pleasure}",
            "new_info": "Reveal the protagonist's new role or circumstances",
            "character_change": "Complete the protagonist's arc for this volume",
            "foreshadowing": "Set up the next volume",
            "ending_hook": "New challenges or opportunities arise and readers look forward to the next round",
        },
    ]

    chapters = []
    for i, tmpl in enumerate(chapter_template, 1):
        chapters.append(
            MiniArcChapter(
                chapter_number=i,
                goal=tmpl["goal"],
                conflict=tmpl["conflict"],
                pleasure_point=tmpl["pleasure_point"],
                new_info=tmpl["new_info"],
                character_change=tmpl["character_change"],
                foreshadowing=tmpl["foreshadowing"],
                ending_hook=tmpl["ending_hook"],
            )
        )

    return MiniArcOutline(
        genre_name=genre_name,
        total_words="20,000-21,000",
        chapters=chapters,
        arc_goal=f"Resolve {conflict} and deliver {pleasure}",
        next_arc_hook=f"With the opening conflict resolved, a larger world opens up to the protagonist in the next volume of {title}.",
    )
