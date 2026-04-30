"""
analysis_engine.py
==================
Wraps the Anthropic API to perform per-document insight extraction and
section-level drafting. All prompts live in prompts.py - this module is
just orchestration and error handling.

Design choices:
  - Two-stage flow: extract -> draft. This forces the model to anchor in
    structured insights rather than free-associate from raw filings.
  - Each section is a separate API call. Smaller context windows produce
    sharper, more cite-able output than a single mega-prompt.
  - Token usage and call counts are tracked for cost transparency.

Author: Jovan Johansen
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from data_ingestion import SourceDocument
import prompts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM CLIENT WRAPPER
# ---------------------------------------------------------------------------
class LLMClient:
    """Thin wrapper around the Anthropic SDK with retry and usage tracking."""

    def __init__(self, model: str = "claude-opus-4-7", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key) if self.api_key else Anthropic()
            except ImportError as e:
                raise RuntimeError(
                    "anthropic SDK not installed. Run: pip install anthropic"
                ) from e
        return self._client

    def complete(
        self,
        user_prompt: str,
        system: str = prompts.SYSTEM_PROMPT,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        retries: int = 2,
    ) -> str:
        """Single completion with retry on transient errors."""
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                self.call_count += 1
                self.total_input_tokens += resp.usage.input_tokens
                self.total_output_tokens += resp.usage.output_tokens
                # Concatenate all text blocks
                return "".join(
                    block.text for block in resp.content if hasattr(block, "text")
                )
            except Exception as e:
                last_err = e
                logger.warning("LLM call failed (attempt %d): %s", attempt + 1, e)
                time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_err}")

    def usage_summary(self) -> Dict[str, int]:
        return {
            "calls": self.call_count,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
        }


# ---------------------------------------------------------------------------
# JSON EXTRACTION HELPER
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response. Tolerant of fences."""
    # Strip code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")

    # Find the first balanced JSON object
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start: i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


# ---------------------------------------------------------------------------
# STAGE 1: PER-DOCUMENT EXTRACTION
# ---------------------------------------------------------------------------
@dataclass
class DocumentInsights:
    source_id: str
    source_type: str
    source_date: str
    raw: Dict[str, Any] = field(default_factory=dict)


class InsightExtractor:
    """Runs the extraction prompt over each source document."""

    # Skip extraction for sources where structured insights are not useful
    SKIP_TYPES = {"market_data"}

    # Cap content length per call to control cost
    MAX_DOC_CHARS = 18000

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(self, ticker: str, source: SourceDocument) -> Optional[DocumentInsights]:
        if source.source_type in self.SKIP_TYPES:
            return None

        content = source.content[: self.MAX_DOC_CHARS]
        prompt = prompts.EXTRACTION_PROMPT.format(
            ticker=ticker,
            source_id=source.source_id,
            source_type=source.source_type,
            source_date=source.publication_date,
            document_text=content,
        )

        try:
            response = self.llm.complete(prompt, max_tokens=2000)
        except Exception as e:
            logger.error("Extraction failed for %s: %s", source.source_id, e)
            return None

        parsed = _extract_json(response)
        if parsed is None:
            logger.warning("Could not parse extraction JSON for %s", source.source_id)
            return None

        return DocumentInsights(
            source_id=source.source_id,
            source_type=source.source_type,
            source_date=source.publication_date,
            raw=parsed,
        )

    def extract_all(
        self, ticker: str, sources: List[SourceDocument]
    ) -> List[DocumentInsights]:
        results = []
        for src in sources:
            insights = self.extract(ticker, src)
            if insights:
                results.append(insights)
        logger.info("Extracted insights from %d / %d sources", len(results), len(sources))
        return results


# ---------------------------------------------------------------------------
# STAGE 2: SECTION DRAFTING
# ---------------------------------------------------------------------------
class SectionDrafter:
    """Generates each report section using extracted insights + market data."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    @staticmethod
    def _aggregate_insights(insights_list: List[DocumentInsights]) -> str:
        """Build a compact JSON view of all extracted insights for the drafter."""
        agg = []
        for i in insights_list:
            entry = {"source_id": i.source_id, "source_type": i.source_type,
                     "date": i.source_date, **i.raw}
            agg.append(entry)
        return json.dumps(agg, indent=2, default=str)

    def draft_company_overview(
        self, ticker: str, company_name: str, sector: str,
        insights: List[DocumentInsights],
    ) -> str:
        prompt = prompts.COMPANY_OVERVIEW_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            sector=sector,
            insights=self._aggregate_insights(insights),
        )
        return self.llm.complete(prompt, max_tokens=600)

    def draft_performance(self, ticker: str, insights: List[DocumentInsights]) -> str:
        prompt = prompts.PERFORMANCE_SUMMARY_PROMPT.format(
            ticker=ticker, insights=self._aggregate_insights(insights),
        )
        return self.llm.complete(prompt, max_tokens=900)

    def draft_drivers_risks(self, ticker: str, insights: List[DocumentInsights]) -> str:
        prompt = prompts.DRIVERS_RISKS_PROMPT.format(
            ticker=ticker, insights=self._aggregate_insights(insights),
        )
        return self.llm.complete(prompt, max_tokens=1100)

    def draft_news_highlights(self, ticker: str, insights: List[DocumentInsights]) -> str:
        prompt = prompts.NEWS_HIGHLIGHTS_PROMPT.format(
            ticker=ticker, insights=self._aggregate_insights(insights),
        )
        return self.llm.complete(prompt, max_tokens=700)

    def draft_thesis(
        self, ticker: str, current_price: Any, valuation_metrics: Dict[str, Any],
        insights: List[DocumentInsights],
    ) -> str:
        prompt = prompts.INVESTMENT_THESIS_PROMPT.format(
            ticker=ticker,
            current_price=current_price,
            valuation_metrics=json.dumps(valuation_metrics, default=str),
            insights=self._aggregate_insights(insights),
        )
        return self.llm.complete(prompt, max_tokens=1300)
