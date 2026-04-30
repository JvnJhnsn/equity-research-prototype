"""
review_layer.py
===============
Automated quality control over generated draft reports. Runs three checks:

  1. CITATION COVERAGE (rule-based): every quantitative claim in the draft
     should have a [SRC-X] tag near it. Flags suspiciously uncited numbers.

  2. CITATION VALIDITY (rule-based): every [SRC-X] tag must map to a real
     source in the inventory.

  3. LLM REVIEW PASS (model-based): a fresh LLM call grades the draft on
     hallucination risk, tone, internal consistency, and completeness.

The output is a structured QC report that travels with the draft to the
human analyst. Nothing is auto-fixed - the human still owns the final call.

Author: Jovan Johansen
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any

from analysis_engine import LLMClient, _extract_json
from data_ingestion import SourceDocument
import prompts

logger = logging.getLogger(__name__)


@dataclass
class QCReport:
    citation_coverage_pct: float
    invalid_citations: List[str] = field(default_factory=list)
    suspicious_uncited_numbers: List[str] = field(default_factory=list)
    llm_review: Dict[str, Any] = field(default_factory=dict)
    overall_severity: str = "low"
    ready_for_human_review: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuleBasedReviewer:
    """Cheap, deterministic checks that don't require an LLM call."""

    # Numbers that look like financial figures - $, %, or large bare numbers
    NUMBER_PATTERN = re.compile(
        r"\$\s?\d+(?:\.\d+)?\s?[BMK]?|"          # $68B, $1.2M, $500K
        r"\d+(?:\.\d+)?\s?%|"                     # 75.2%
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"       # 1,234,567
    )

    CITATION_PATTERN = re.compile(r"\[SRC-\d+\]")

    # Window: a number is considered "cited" if a [SRC-X] appears within
    # 100 characters before or after it.
    CITATION_WINDOW = 100

    def review(self, draft: str, sources: List[SourceDocument]) -> Dict[str, Any]:
        valid_ids = {s.source_id for s in sources}

        # Find all citation tags in the draft
        all_citations = self.CITATION_PATTERN.findall(draft)
        invalid = []
        for tag in all_citations:
            inner = tag.strip("[]")  # SRC-1
            if inner not in valid_ids:
                invalid.append(tag)

        # Find quantitative claims and check for nearby citations
        numbers = list(self.NUMBER_PATTERN.finditer(draft))
        if not numbers:
            coverage = 1.0
            uncited = []
        else:
            cited = 0
            uncited = []
            for m in numbers:
                start = max(0, m.start() - self.CITATION_WINDOW)
                end = min(len(draft), m.end() + self.CITATION_WINDOW)
                window = draft[start:end]
                if self.CITATION_PATTERN.search(window):
                    cited += 1
                else:
                    # Surface the surrounding context for the human reviewer
                    context = draft[max(0, m.start() - 40): m.end() + 40].strip()
                    uncited.append(f"...{context}...")
            coverage = cited / len(numbers)

        return {
            "citation_coverage_pct": round(coverage * 100, 1),
            "invalid_citations": invalid,
            "suspicious_uncited_numbers": uncited[:15],  # cap for readability
            "total_quantitative_claims": len(numbers),
            "total_citations": len(all_citations),
        }


class LLMReviewer:
    """Runs the structured review prompt against the draft."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(self, draft: str, sources: List[SourceDocument]) -> Dict[str, Any]:
        # Build the source inventory string for the prompt
        inventory_lines = []
        for s in sources:
            inventory_lines.append(
                f"  {s.source_id}: {s.source_type} | {s.title} | {s.publication_date}"
            )
        inventory_str = "\n".join(inventory_lines)

        prompt = prompts.REVIEW_PROMPT.format(
            draft_report=draft, source_inventory=inventory_str
        )
        try:
            response = self.llm.complete(prompt, max_tokens=2000, temperature=0.0)
        except Exception as e:
            logger.error("LLM review failed: %s", e)
            return {"error": str(e), "ready_for_human_review": True}

        parsed = _extract_json(response)
        if parsed is None:
            return {"error": "Could not parse review JSON", "raw": response[:500]}
        return parsed


class ReviewOrchestrator:
    """Combines rule-based and LLM reviews into a single QC report."""

    def __init__(self, llm: LLMClient):
        self.rule_reviewer = RuleBasedReviewer()
        self.llm_reviewer = LLMReviewer(llm)

    def run(self, draft: str, sources: List[SourceDocument]) -> QCReport:
        rule_results = self.rule_reviewer.review(draft, sources)
        llm_results = self.llm_reviewer.review(draft, sources)

        # Severity heuristic: high if invalid citations or LLM flags hallucinations
        severity = "low"
        if rule_results["invalid_citations"]:
            severity = "high"
        elif rule_results["citation_coverage_pct"] < 60:
            severity = "medium"
        if llm_results.get("potentially_hallucinated_facts"):
            severity = "high"

        ready = severity != "high"

        return QCReport(
            citation_coverage_pct=rule_results["citation_coverage_pct"],
            invalid_citations=rule_results["invalid_citations"],
            suspicious_uncited_numbers=rule_results["suspicious_uncited_numbers"],
            llm_review=llm_results,
            overall_severity=severity,
            ready_for_human_review=ready,
        )

    @staticmethod
    def format_for_human(qc: QCReport) -> str:
        """Plain-text summary the human analyst sees alongside the draft."""
        lines = [
            "=" * 70,
            "AUTOMATED QC REPORT - HUMAN REVIEW REQUIRED",
            "=" * 70,
            f"Overall severity:        {qc.overall_severity.upper()}",
            f"Ready for human review:  {qc.ready_for_human_review}",
            f"Citation coverage:       {qc.citation_coverage_pct}%",
            "",
        ]
        if qc.invalid_citations:
            lines.append(f"INVALID CITATIONS ({len(qc.invalid_citations)}):")
            for tag in qc.invalid_citations:
                lines.append(f"  - {tag} does not map to a known source")
            lines.append("")

        if qc.suspicious_uncited_numbers:
            lines.append(f"UNCITED QUANTITATIVE CLAIMS "
                         f"({len(qc.suspicious_uncited_numbers)} flagged, top 5 shown):")
            for s in qc.suspicious_uncited_numbers[:5]:
                lines.append(f"  - {s}")
            lines.append("")

        if isinstance(qc.llm_review, dict):
            for key in ("uncited_quantitative_claims", "potentially_hallucinated_facts",
                        "tone_or_compliance_issues", "internal_inconsistencies",
                        "missing_required_elements"):
                items = qc.llm_review.get(key, [])
                if items:
                    lines.append(f"{key.upper().replace('_', ' ')}:")
                    for item in items[:5]:
                        lines.append(f"  - {item}")
                    lines.append("")

        lines.append("=" * 70)
        lines.append("Human reviewer: please verify all flagged items before sign-off.")
        lines.append("=" * 70)
        return "\n".join(lines)
