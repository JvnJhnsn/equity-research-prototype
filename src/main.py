"""
main.py
=======
End-to-end orchestrator for the Automated Equity Research Report Writer.

Workflow:
   ticker
     -> data_ingestion (SEC filings + market data)
     -> analysis_engine.InsightExtractor (per-document JSON insights)
     -> analysis_engine.SectionDrafter (5 report sections)
     -> review_layer.ReviewOrchestrator (rule-based + LLM QC)
     -> report_generator.PDFReportGenerator (final deliverable)

Run:
   python main.py NVDA --output-dir ../outputs

Author: Jovan Johansen
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Local imports
from data_ingestion import DataIngestionOrchestrator
from analysis_engine import LLMClient, InsightExtractor, SectionDrafter
from review_layer import ReviewOrchestrator
from report_generator import PDFReportGenerator, ReportPayload


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def extract_recommendation(thesis_text: str) -> str:
    """Pull the recommendation framing out of the thesis section."""
    text = thesis_text.upper()
    for label in ["POSITIVE", "WATCHLIST", "NEUTRAL", "CAUTIOUS"]:
        # Look for the framing label as a standalone token
        if re.search(r"\b" + label + r"\b", text):
            return label
    return "NEUTRAL"


def run_pipeline(ticker: str, output_dir: Path, model: str, save_inventory: bool = True):
    log = logging.getLogger("main")
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Ingest sources ------------------------------------------------
    log.info("STEP 1: Ingesting source documents for %s", ticker)
    ingestor = DataIngestionOrchestrator()
    sources = ingestor.gather_sources(ticker)
    if not sources:
        log.error("No sources retrieved. Aborting.")
        sys.exit(1)
    log.info("Retrieved %d sources", len(sources))

    if save_inventory:
        inv_path = output_dir / f"{ticker}_source_inventory.json"
        ingestor.save_inventory(sources, inv_path)
        log.info("Saved source inventory to %s", inv_path)

    # Locate the market data source for cover-page metadata
    market_src = next((s for s in sources if s.source_type == "market_data"), None)
    market_data = market_src.metadata if market_src else {}

    # ---- 2. Extract per-document insights --------------------------------
    log.info("STEP 2: Extracting structured insights from each source")
    llm = LLMClient(model=model)
    extractor = InsightExtractor(llm)
    insights = extractor.extract_all(ticker, sources)

    # ---- 3. Draft each section ------------------------------------------
    log.info("STEP 3: Drafting report sections")
    drafter = SectionDrafter(llm)

    company_name = market_data.get("company_name") or ticker
    sector = market_data.get("sector") or "n/a"
    industry = market_data.get("industry") or "n/a"

    sections = {}
    log.info("  - Company overview...")
    sections["company_overview"] = drafter.draft_company_overview(
        ticker, company_name, sector, insights
    )
    log.info("  - Performance summary...")
    sections["performance"] = drafter.draft_performance(ticker, insights)
    log.info("  - Drivers and risks...")
    sections["drivers_risks"] = drafter.draft_drivers_risks(ticker, insights)
    log.info("  - News and management commentary...")
    sections["news_highlights"] = drafter.draft_news_highlights(ticker, insights)
    log.info("  - Investment thesis...")
    valuation_metrics = {
        k: market_data.get(k) for k in
        ("pe_ttm", "pe_forward", "market_cap", "52w_high", "52w_low", "1y_return_pct")
    }
    sections["thesis"] = drafter.draft_thesis(
        ticker, market_data.get("current_price"), valuation_metrics, insights
    )

    full_draft = "\n\n".join(
        f"## {k.upper()} ##\n{v}" for k, v in sections.items()
    )

    # ---- 4. QC layer ----------------------------------------------------
    log.info("STEP 4: Running automated quality control review")
    reviewer = ReviewOrchestrator(llm)
    qc = reviewer.run(full_draft, sources)
    qc_text = reviewer.format_for_human(qc)
    qc_path = output_dir / f"{ticker}_qc_report.txt"
    qc_path.write_text(qc_text)
    log.info("QC severity: %s | Coverage: %.1f%% | Saved %s",
             qc.overall_severity, qc.citation_coverage_pct, qc_path)

    # ---- 5. Render PDF --------------------------------------------------
    log.info("STEP 5: Rendering final PDF report")
    recommendation = extract_recommendation(sections["thesis"])
    payload = ReportPayload(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        recommendation=recommendation,
        market_data=market_data,
        sections=sections,
        sources=sources,
        qc_report=qc,
    )
    pdf_path = output_dir / f"{ticker}_research_report.pdf"
    PDFReportGenerator().generate(payload, pdf_path)
    log.info("Report written to %s", pdf_path)

    # ---- 6. Save raw artifacts for traceability -------------------------
    raw_path = output_dir / f"{ticker}_draft_sections.json"
    raw_path.write_text(json.dumps({
        "ticker": ticker,
        "sections": sections,
        "qc": qc.to_dict(),
        "llm_usage": llm.usage_summary(),
        "recommendation": recommendation,
    }, indent=2, default=str))
    log.info("Saved raw draft and QC to %s", raw_path)

    # ---- Summary -------------------------------------------------------
    print("")
    print("=" * 60)
    print(f"  PIPELINE COMPLETE FOR {ticker}")
    print("=" * 60)
    print(f"  Sources ingested:    {len(sources)}")
    print(f"  Sections drafted:    {len(sections)}")
    print(f"  Recommendation:      {recommendation}")
    print(f"  QC severity:         {qc.overall_severity.upper()}")
    print(f"  Citation coverage:   {qc.citation_coverage_pct}%")
    print(f"  LLM API calls:       {llm.usage_summary()['calls']}")
    print(f"  PDF report:          {pdf_path}")
    print(f"  QC report:           {qc_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Automated Equity Research Report Writer"
    )
    parser.add_argument("ticker", help="Stock ticker (e.g. NVDA)")
    parser.add_argument("--output-dir", type=Path, default=Path("../outputs"),
                        help="Directory for generated files")
    parser.add_argument("--model", default="claude-opus-4-7",
                        help="Anthropic model identifier")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    run_pipeline(args.ticker.upper(), args.output_dir, args.model)


if __name__ == "__main__":
    main()
