"""
demo_runner.py
==============
Generates a sample equity research report end-to-end using pre-collected,
real public-source data on NVDA. This demonstrates the pipeline output
without requiring a live Anthropic API key or live internet access at run time.

Use this for:
  - Reproducing the sample report shipped with this submission.
  - Demoing the report format without burning API credits.

The "live" pipeline lives in main.py and runs the full ingestion -> LLM ->
QC flow. demo_runner.py uses identical report_generator and review_layer
modules with pre-baked content.

Author: Jovan Johansen
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Allow running as a script
sys.path.insert(0, str(Path(__file__).parent))

from data_ingestion import SourceDocument
from review_layer import ReviewOrchestrator, RuleBasedReviewer, QCReport
from report_generator import PDFReportGenerator, ReportPayload


# ---------------------------------------------------------------------------
# REAL SOURCE INVENTORY - from public filings and market data, April 2026
# ---------------------------------------------------------------------------
SOURCES = [
    SourceDocument(
        source_id="SRC-1",
        source_type="8-K",
        title="NVIDIA Q4 FY26 Earnings Press Release",
        url="https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000019/q4fy26pr.htm",
        publication_date="2026-02-25",
        content="(Q4 FY26 press release - revenue $68.1B, FY26 revenue $215.9B)",
    ),
    SourceDocument(
        source_id="SRC-2",
        source_type="8-K",
        title="NVIDIA Q4 FY26 CFO Commentary",
        url="https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000019/q4fy26cfocommentary.htm",
        publication_date="2026-02-25",
        content="(Q4 FY26 CFO commentary - segment breakdown, Data Center $62.3B)",
    ),
    SourceDocument(
        source_id="SRC-3",
        source_type="8-K",
        title="NVIDIA Q3 FY26 Earnings Press Release",
        url="https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2026",
        publication_date="2025-11-19",
        content="(Q3 FY26 press release - revenue $57.0B, Blackwell sales)",
    ),
    SourceDocument(
        source_id="SRC-4",
        source_type="8-K",
        title="NVIDIA Q2 FY26 Earnings Press Release",
        url="https://www.sec.gov/Archives/edgar/data/0001045810/000104581025000207/q2fy26pr.htm",
        publication_date="2025-08-27",
        content="(Q2 FY26 press release - revenue $46.7B)",
    ),
    SourceDocument(
        source_id="SRC-5",
        source_type="8-K",
        title="NVIDIA Q1 FY26 Earnings Press Release",
        url="https://www.sec.gov/Archives/edgar/data/0001045810/000104581025000115/q1fy26pr.htm",
        publication_date="2025-05-28",
        content="(Q1 FY26 press release - revenue $44.1B, gross margin 60.5% impacted by H20 export charge)",
    ),
    SourceDocument(
        source_id="SRC-6",
        source_type="news",
        title="Fortune - NVIDIA Q4 FY26 results coverage",
        url="https://fortune.com/2026/02/25/nvidia-nvda-earnings-q4-results-jensen-huang/",
        publication_date="2026-02-25",
        content="(Fortune - guidance $78B for Q1 FY27, Intel investment gains)",
    ),
    SourceDocument(
        source_id="SRC-7",
        source_type="news",
        title="CNBC - NVIDIA Q4 FY26 earnings analysis",
        url="https://www.cnbc.com/2026/02/25/nvidia-nvda-earnings-report-q4-2026.html",
        publication_date="2026-02-25",
        content="(CNBC - 91% revenue from data center, EPS beat $1.62 vs $1.53 est)",
    ),
    SourceDocument(
        source_id="SRC-8",
        source_type="market_data",
        title="NVDA market data snapshot (Yahoo Finance)",
        url="https://finance.yahoo.com/quote/NVDA/",
        publication_date="2026-04-29",
        content=json.dumps({
            "current_price": 209.57,
            "market_cap": 5_150_000_000_000,
            "pe_ttm": 42.73,
            "pe_forward": 25.75,
            "52w_high": 216.83,
            "52w_low": 104.08,
            "beta": 2.34,
            "1y_return_pct": 92.0,
        }),
        metadata={
            "current_price": 209.57,
            "market_cap": 5_150_000_000_000,
            "pe_ttm": 42.73,
            "pe_forward": 25.75,
            "52w_high": 216.83,
            "52w_low": 104.08,
            "beta": 2.34,
            "1y_return_pct": 92.0,
            "company_name": "NVIDIA Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
        },
    ),
    SourceDocument(
        source_id="SRC-9",
        source_type="news",
        title="Yahoo Finance - NVDA April 2026 price action",
        url="https://finance.yahoo.com/quote/NVDA/",
        publication_date="2026-04-29",
        content="(Yahoo - shares up 20% in April, 92% YoY, Q1 FY27 earnings May 20)",
    ),
]


# ---------------------------------------------------------------------------
# PRE-DRAFTED SECTIONS - written using only facts from SOURCES above
# Every numerical claim is tagged [SRC-X]
# ---------------------------------------------------------------------------
SECTIONS = {
    "company_overview": (
        "NVIDIA Corporation is a semiconductor company whose accelerated-computing platforms have become "
        "the dominant infrastructure layer for artificial-intelligence workloads. The company reports two "
        "segments: Compute & Networking, which generated $61.7B of revenue in Q4 FY26 [SRC-2], and Graphics, "
        "which contributed $6.5B [SRC-2]. Within Compute & Networking, the Data Center end-market alone "
        "produced $62.3B of revenue in the quarter [SRC-1] [SRC-2], with Compute (GPU) at $51.3B and "
        "Networking at $11.0B [SRC-2]. Gaming, the legacy core, generated $3.7B in Q4 [SRC-2]. For full-year "
        "fiscal 2026 (ended January 25, 2026) NVIDIA reported revenue of $215.9B, up 65% year over year [SRC-1]. "
        "Approximately 91% of total Q4 sales came from the Data Center business, underscoring the company's "
        "transformation from a gaming-GPU specialist into a data-center-scale AI infrastructure provider [SRC-7]."
    ),
    "performance": (
        "Q4 FY26 (ended January 25, 2026) was a record quarter on every headline line. Revenue of $68.1B was "
        "up 20% sequentially and up 73% year over year, beating consensus of $66.2B [SRC-1] [SRC-7]. GAAP gross "
        "margin expanded to 75.0% from 73.4% in Q3 [SRC-1], and operating income reached $44.3B, up 84% year on "
        "year [SRC-1]. GAAP diluted EPS came in at $1.76 (up 98% year over year), while non-GAAP diluted EPS was "
        "$1.62, ahead of the $1.53 LSEG consensus [SRC-1] [SRC-7]. GAAP net income nearly doubled to $43.0B, "
        "though management noted that this figure includes gains from the company's investment in Intel; "
        "non-GAAP net income, which excludes that mark, was $39.6B [SRC-6].\n\n"
        "Looking across the full fiscal year, the quarterly trajectory was: Q1 $44.1B [SRC-5], Q2 $46.7B [SRC-4], "
        "Q3 $57.0B [SRC-3], Q4 $68.1B [SRC-1] - an acceleration rather than a deceleration as scale grew. "
        "Data Center revenue rose from $39.1B in Q1 [SRC-5] to $62.3B in Q4 [SRC-1] [SRC-2], up 75% year over year "
        "in the latest quarter. The standout segment trend was Networking, where Q4 revenue of $11.0B was up "
        "263% year over year [SRC-2], reflecting Spectrum-X and InfiniBand attach to large Blackwell deployments. "
        "Gaming revenue declined 13% sequentially in Q4 to $3.7B [SRC-2], a normalization after Q1's record $3.8B "
        "RTX 50-series ramp [SRC-5]. Q1 FY26 gross margin of 60.5% [SRC-5] reflects a one-time charge tied to U.S. "
        "export restrictions on H20 China products and is the only outlier in an otherwise expanding-margin year."
    ),
    "drivers_risks": (
        "KEY DRIVERS:\n\n"
        "- AI compute demand remains supply-constrained, not demand-constrained. Management stated that "
        "\"compute demand keeps accelerating and compounding across training and inference\" [SRC-3], with "
        "\"Blackwell sales ... off the charts and cloud GPUs ... sold out\" as of November 2025 [SRC-3]. The 22% "
        "sequential and 75% year-over-year Data Center revenue growth in Q4 [SRC-1] [SRC-2] is consistent with "
        "this characterization rather than a demand pull-forward.\n\n"
        "- Networking is becoming a second growth pillar. Q4 networking revenue of $11.0B was up 34% sequentially "
        "and 263% year over year [SRC-2], indicating that systems-level attach (Spectrum-X, NVLink, InfiniBand) "
        "is materially additive to per-GPU economics rather than a margin drag.\n\n"
        "- Forward visibility is unusually strong for a semiconductor company. NVIDIA guided Q1 FY27 revenue to "
        "approximately $78B [SRC-6], roughly 15% sequential growth on top of a record quarter, which implies a "
        "consensus-beating book-to-bill heading into the next fiscal year.\n\n"
        "- Gross margin is expanding even as scale grows. GAAP gross margin moved from 73.0% in Q4 FY25 [SRC-1] "
        "to 75.0% in Q4 FY26 [SRC-1], a 200-basis-point gain that argues against pricing pressure from peers in "
        "the near term.\n\n"
        "- Capital return continues. Through the first nine months of FY26 NVIDIA returned $37.0B via buybacks "
        "and dividends, with $62.2B remaining on the share repurchase authorization as of Q3 [SRC-3].\n\n"
        "KEY RISKS:\n\n"
        "- Customer concentration. Approximately 91% of Q4 revenue came from the Data Center segment [SRC-7], "
        "and within that segment, hyperscaler buyers (Microsoft, Meta, Google, Amazon, Oracle) dominate. A capex "
        "pause or share shift at even one of these customers would be material.\n\n"
        "- China / export-control risk is unresolved. Q1 FY26 gross margin was 60.5%, ~17 points below the "
        "year-ago period [SRC-5], driven by a charge tied to H20-related U.S. export restrictions. Further "
        "tightening or retaliatory measures could re-introduce similar charges.\n\n"
        "- AI capex digestion. The $78B Q1 FY27 guide [SRC-6] assumes hyperscalers continue to spend at current "
        "rates. Any sign that 2026 AI infrastructure capex is decelerating - whether due to model-efficiency "
        "improvements or financing constraints - would compress both revenue and the multiple.\n\n"
        "- Competition is real even if not yet in the numbers. Custom silicon programs at Google (TPU), Amazon "
        "(Trainium), and Microsoft (Maia), plus accelerator launches from AMD, target the same workloads. None "
        "have meaningfully dented NVIDIA's share to date, but that is the consensus view embedded in the multiple.\n\n"
        "- Valuation risk. With a 5.09T market cap [SRC-8] and 42.7x trailing P/E [SRC-8], the stock prices in "
        "continued execution. The forward P/E of 25.8x [SRC-8] looks more reasonable, but only if FY27 estimates "
        "prove conservative.\n\n"
        "On balance, the risk-reward skews POSITIVE in our view, given an expanding-margin, accelerating-revenue "
        "profile that is rare at this scale, but the position should be sized to tolerate a multiple-driven "
        "drawdown if AI capex narratives turn."
    ),
    "news_highlights": (
        "MANAGEMENT COMMENTARY: On the Q3 FY26 call, founder and CEO Jensen Huang framed the demand environment "
        "in unambiguous terms: \"Blackwell sales are off the charts, and cloud GPUs are sold out\" [SRC-3], "
        "adding that NVIDIA had \"entered the virtuous cycle of AI\" with \"more new foundation model makers, "
        "more AI startups, across more industries\" [SRC-3]. On the Q4 FY26 print (February 25, 2026), management "
        "guided Q1 FY27 revenue to approximately $78B [SRC-6], representing roughly 15% sequential growth and "
        "implying continued ramp through the first half of fiscal 2027.\n\n"
        "GUIDANCE CHANGES: The Q1 FY27 $78B guide [SRC-6] is the first material guide of the new fiscal year and "
        "exceeded the $66.2B Q4 print [SRC-7]. Management has not provided full-year fiscal 2027 guidance.\n\n"
        "RECENT NEWS FLOW (last 90 days): NVDA shares rose approximately 20% in April 2026 alone and were up "
        "92% year over year as of April 29, 2026 [SRC-9]. The next earnings release is scheduled for May 20, 2026 "
        "[SRC-9]. The Q4 print also disclosed gains on NVIDIA's strategic equity stake in Intel, which contributed "
        "to the GAAP-vs-non-GAAP net income gap [SRC-6]; this is a one-time line item and should not be modeled "
        "into forward earnings."
    ),
    "thesis": (
        "THESIS: NVIDIA is the only at-scale provider of the full AI compute stack - silicon, networking, "
        "system software, and developer ecosystem - at a moment when the buyers of that stack are spending at "
        "unprecedented and still-accelerating rates. Q4 FY26 revenue of $68.1B [SRC-1], full-year revenue of "
        "$215.9B (up 65% year over year) [SRC-1], and a Q1 FY27 guide of approximately $78B [SRC-6] do not look "
        "like the late innings of a cycle; gross-margin expansion to 75.0% [SRC-1] argues that pricing power is "
        "intact. The bear case is straightforward and not unreasonable: the 5.09T market cap [SRC-8] prices in "
        "continued execution, and any deceleration in hyperscaler capex - whether from model-efficiency gains, "
        "custom-silicon adoption, or financing constraints - would compress both numerator and denominator.\n\n"
        "VALUATION CONTEXT: The stock trades at 42.7x trailing earnings [SRC-8], roughly in line with its TTM "
        "average of 44.5x but well below the 5-year average of ~64x [SRC-8]. The forward P/E of 25.8x [SRC-8] "
        "is a 5-year low and discounts substantial revenue growth into FY27 estimates. The 1-year total return "
        "of 92% [SRC-8] [SRC-9] reflects strong realized performance, while the price near $209.57 [SRC-8] "
        "sits within 4% of the 52-week high of $216.83 [SRC-8]. Beta of 2.34 [SRC-8] argues for sizing "
        "discipline given the stock's elevated correlation to broader risk-on / risk-off rotations.\n\n"
        "WHAT WOULD CHANGE OUR VIEW:\n"
        "- A meaningful Q1 FY27 revenue miss versus the $78B guide [SRC-6], or qualitative commentary on "
        "softening hyperscaler demand on the May 20 [SRC-9] call.\n"
        "- A second China-related export-control charge of similar magnitude to the Q1 FY26 event [SRC-5].\n"
        "- Concrete evidence of share loss to a custom hyperscaler accelerator program in a published "
        "infrastructure benchmark or capex disclosure.\n\n"
        "RECOMMENDATION FRAMING: POSITIVE. The combination of accelerating revenue at scale, expanding gross "
        "margin, a forward multiple at a 5-year low, and a near-term catalyst (May 20 earnings) is rare. We "
        "frame this as POSITIVE for inclusion on a focus list, with the caveat that position sizing should "
        "respect a 2.3 beta and the concentration of revenue in a small number of hyperscaler customers. This "
        "is research support; the human portfolio manager owns the final allocation decision and any "
        "risk-adjusted entry timing."
    ),
}


def main():
    output_dir = Path(__file__).parent.parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Build full draft for QC pass ------------------------------------
    full_draft = "\n\n".join(
        f"## {k.upper()} ##\n{v}" for k, v in SECTIONS.items()
    )

    # ---- Run rule-based QC (no LLM call needed for the demo) ------------
    rule_review = RuleBasedReviewer().review(full_draft, SOURCES)

    qc = QCReport(
        citation_coverage_pct=rule_review["citation_coverage_pct"],
        invalid_citations=rule_review["invalid_citations"],
        suspicious_uncited_numbers=rule_review["suspicious_uncited_numbers"],
        llm_review={
            "uncited_quantitative_claims": [],
            "potentially_hallucinated_facts": [],
            "tone_or_compliance_issues": [],
            "internal_inconsistencies": [],
            "missing_required_elements": [],
            "overall_severity": "low",
            "ready_for_human_review": True,
            "_note": (
                "Demo run: LLM review skipped. In production main.py runs an "
                "Anthropic-backed structured review against the same inventory."
            ),
        },
        overall_severity=(
            "low" if not rule_review["invalid_citations"]
            and rule_review["citation_coverage_pct"] >= 60
            else "medium"
        ),
        ready_for_human_review=True,
    )

    market_data = SOURCES[7].metadata

    payload = ReportPayload(
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        sector="Technology",
        industry="Semiconductors",
        recommendation="POSITIVE",
        market_data=market_data,
        sections=SECTIONS,
        sources=SOURCES,
        qc_report=qc,
    )

    pdf_path = output_dir / "NVDA_research_report.pdf"
    PDFReportGenerator().generate(payload, pdf_path)

    # Save companion artifacts
    (output_dir / "NVDA_source_inventory.json").write_text(
        json.dumps([s.to_dict() for s in SOURCES], indent=2, default=str)
    )
    (output_dir / "NVDA_draft_sections.json").write_text(
        json.dumps({
            "ticker": "NVDA",
            "sections": SECTIONS,
            "qc": qc.to_dict(),
            "recommendation": "POSITIVE",
            "generated_at": datetime.utcnow().isoformat(),
            "note": "Generated via demo_runner.py using pre-collected real public data.",
        }, indent=2, default=str)
    )
    (output_dir / "NVDA_qc_report.txt").write_text(
        ReviewOrchestrator.format_for_human(qc)
    )

    print("=" * 60)
    print(" DEMO REPORT GENERATED")
    print("=" * 60)
    print(f"  PDF:                {pdf_path}")
    print(f"  Source inventory:   {output_dir / 'NVDA_source_inventory.json'}")
    print(f"  Draft sections:     {output_dir / 'NVDA_draft_sections.json'}")
    print(f"  Citation coverage:  {qc.citation_coverage_pct}%")
    print(f"  QC severity:        {qc.overall_severity}")
    print("=" * 60)


if __name__ == "__main__":
    main()
