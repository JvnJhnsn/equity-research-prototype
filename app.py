"""
app.py
======
Streamlit web UI for the Automated Equity Research Report Writer.

Run locally:
    streamlit run app.py

Deploy free:
    https://streamlit.io/cloud  (point at this repo, set ANTHROPIC_API_KEY in
    Secrets, done)

The UI lets a user:
  1. Pick a ticker from the supported list (or type a custom one).
  2. Choose Demo Mode (instant, NVDA only, no API key) or Live Mode (any
     supported ticker, requires API key).
  3. Watch the pipeline run stage by stage with live progress.
  4. Read the rendered report inline and download the PDF.
  5. Inspect the source inventory and QC findings in collapsible panels.

Author: Jovan Johansen
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st

# Make src/ importable
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Automated Equity Research",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# STYLING
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main > div { padding-top: 1.5rem; }
    .stButton button {
        background-color: #0B2545;
        color: white;
        font-weight: 600;
        border: none;
        padding: 0.5rem 2rem;
    }
    .stButton button:hover {
        background-color: #C9A227;
        color: white;
    }
    .rec-positive { color: #0B6E4F; font-weight: 700; font-size: 1.4rem; }
    .rec-watchlist { color: #1B6CA8; font-weight: 700; font-size: 1.4rem; }
    .rec-neutral { color: #6C757D; font-weight: 700; font-size: 1.4rem; }
    .rec-cautious { color: #B23A48; font-weight: 700; font-size: 1.4rem; }
    .metric-card {
        background: #F5F5F5;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #C9A227;
    }
    .citation { color: #C9A227; font-weight: 700; }
    h1, h2, h3 { color: #0B2545; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown("# 📊")
with col_title:
    st.title("Automated Equity Research Report Writer")
    st.caption("Tsunami Advisors AI Intern Case Study · Jovan Johansen")

st.markdown("---")


# ---------------------------------------------------------------------------
# SIDEBAR - INPUTS
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    mode = st.radio(
        "Run mode",
        ["Demo (NVDA, instant)", "Live (any ticker, uses API)"],
        help=(
            "Demo mode reproduces the pre-built NVDA report instantly using "
            "real public-source data — no API key required.\n\n"
            "Live mode runs the full pipeline against the Anthropic API and "
            "SEC EDGAR. Takes 60-90 seconds. Requires an Anthropic API key."
        ),
    )

    if mode.startswith("Live"):
        ticker_options = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]
        ticker = st.selectbox(
            "Ticker",
            ticker_options,
            help="Pre-loaded tickers with SEC CIK lookup. Add more in "
                 "data_ingestion.py CIK_MAP.",
        )

        # Use environment variable or Streamlit secrets if available, else prompt
        default_key = os.getenv("ANTHROPIC_API_KEY", "")
        try:
            default_key = default_key or st.secrets.get("ANTHROPIC_API_KEY", "")
        except (FileNotFoundError, KeyError):
            pass

        api_key = st.text_input(
            "Anthropic API key",
            value=default_key,
            type="password",
            help="Get one at https://console.anthropic.com. "
                 "Free signup gives $5 in credits.",
        )

        model = st.selectbox(
            "Model",
            ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            index=0,
            help="Opus = highest quality. Haiku = fastest and cheapest "
                 "(roughly 1/15th the cost) but slightly less polished prose.",
        )
    else:
        ticker = "NVDA"
        api_key = None
        model = None

    st.markdown("---")

    st.markdown("### 📚 About")
    st.markdown(
        "This prototype turns a single ticker into a structured, fully-cited "
        "equity research report using a Generative-AI-first workflow.\n\n"
        "**Pipeline:** ingest → extract → draft → review → render → human sign-off.\n\n"
        "Every quantitative claim is tagged with `[SRC-X]` and traceable to a "
        "real public source."
    )

    with st.expander("📖 How it works"):
        st.markdown("""
1. **Ingest** SEC filings (10-K, 10-Q, 8-K) and market data
2. **Extract** structured JSON insights from each source
3. **Draft** five report sections using the structured insights
4. **Review** for citation coverage and hallucination risk
5. **Render** the polished PDF
6. **Human sign-off** on flagged QC items
""")


# ---------------------------------------------------------------------------
# MAIN PANEL
# ---------------------------------------------------------------------------
st.markdown(f"### Generate report for **{ticker}**")

if mode.startswith("Live"):
    if not api_key:
        st.warning(
            "⚠️ Enter your Anthropic API key in the sidebar to run the live "
            "pipeline. Or switch to Demo mode for an instant NVDA report."
        )

generate_btn = st.button(
    "🚀 Generate research report",
    type="primary",
    disabled=(mode.startswith("Live") and not api_key),
    use_container_width=False,
)


# ---------------------------------------------------------------------------
# PIPELINE EXECUTION
# ---------------------------------------------------------------------------
def run_demo():
    """Run the deterministic demo pipeline for NVDA."""
    import demo_runner  # imports SOURCES, SECTIONS
    from review_layer import RuleBasedReviewer, QCReport, ReviewOrchestrator
    from report_generator import PDFReportGenerator, ReportPayload

    progress = st.progress(0, text="Starting demo pipeline...")
    log = st.empty()

    log.info("📥 Loading pre-collected source inventory (9 documents)...")
    progress.progress(20, text="Ingesting sources...")
    time.sleep(0.4)
    sources = demo_runner.SOURCES
    sections = demo_runner.SECTIONS

    log.info("🔍 Aggregating structured insights...")
    progress.progress(40, text="Aggregating insights...")
    time.sleep(0.3)

    log.info("✍️ Loading pre-drafted sections (5 sections, all citations validated)...")
    progress.progress(60, text="Drafting sections...")
    time.sleep(0.3)

    full_draft = "\n\n".join(f"## {k.upper()} ##\n{v}" for k, v in sections.items())

    log.info("🛡️ Running rule-based QC review...")
    progress.progress(80, text="Running QC...")
    rule_review = RuleBasedReviewer().review(full_draft, sources)
    qc = QCReport(
        citation_coverage_pct=rule_review["citation_coverage_pct"],
        invalid_citations=rule_review["invalid_citations"],
        suspicious_uncited_numbers=rule_review["suspicious_uncited_numbers"],
        llm_review={
            "potentially_hallucinated_facts": [],
            "tone_or_compliance_issues": [],
            "internal_inconsistencies": [],
            "missing_required_elements": [],
            "_note": "Demo run: structured LLM review skipped.",
        },
        overall_severity="low" if not rule_review["invalid_citations"] else "medium",
        ready_for_human_review=True,
    )

    log.info("📄 Rendering PDF...")
    progress.progress(95, text="Rendering PDF...")
    market_data = sources[7].metadata
    payload = ReportPayload(
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        sector="Technology",
        industry="Semiconductors",
        recommendation="POSITIVE",
        market_data=market_data,
        sections=sections,
        sources=sources,
        qc_report=qc,
    )

    pdf_buffer = BytesIO()
    PDFReportGenerator().generate(payload, pdf_buffer)
    pdf_buffer.seek(0)

    progress.progress(100, text="Complete!")
    time.sleep(0.3)
    progress.empty()
    log.empty()

    return {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "recommendation": "POSITIVE",
        "market_data": market_data,
        "sections": sections,
        "sources": sources,
        "qc": qc,
        "pdf_bytes": pdf_buffer.getvalue(),
    }


def run_live(ticker: str, api_key: str, model: str):
    """Run the full live pipeline with real API calls."""
    os.environ["ANTHROPIC_API_KEY"] = api_key

    from data_ingestion import DataIngestionOrchestrator
    from analysis_engine import LLMClient, InsightExtractor, SectionDrafter
    from review_layer import ReviewOrchestrator
    from report_generator import PDFReportGenerator, ReportPayload
    from main import extract_recommendation

    progress = st.progress(0, text="Starting live pipeline...")
    log = st.empty()

    # Stage 1
    log.info(f"📥 Ingesting SEC filings and market data for {ticker}...")
    progress.progress(10, text="Ingesting sources...")
    ingestor = DataIngestionOrchestrator()
    sources = ingestor.gather_sources(ticker)
    if not sources:
        st.error(f"No sources found for {ticker}. Check the CIK mapping.")
        st.stop()
    log.success(f"✅ Retrieved {len(sources)} source documents")

    market_src = next((s for s in sources if s.source_type == "market_data"), None)
    market_data = market_src.metadata if market_src else {}

    # Stage 2
    log.info(f"🔍 Extracting structured insights from {len(sources)} sources via Claude {model}...")
    progress.progress(25, text="Extracting insights...")
    llm = LLMClient(model=model, api_key=api_key)
    extractor = InsightExtractor(llm)
    insights = extractor.extract_all(ticker, sources)
    log.success(f"✅ Extracted insights from {len(insights)} sources")

    # Stage 3
    drafter = SectionDrafter(llm)
    company_name = market_data.get("company_name") or ticker
    sector = market_data.get("sector") or "n/a"
    industry = market_data.get("industry") or "n/a"

    sections = {}
    section_steps = [
        ("company_overview", "Company snapshot",
         lambda: drafter.draft_company_overview(ticker, company_name, sector, insights)),
        ("performance", "Financial performance",
         lambda: drafter.draft_performance(ticker, insights)),
        ("drivers_risks", "Drivers and risks",
         lambda: drafter.draft_drivers_risks(ticker, insights)),
        ("news_highlights", "Earnings commentary",
         lambda: drafter.draft_news_highlights(ticker, insights)),
        ("thesis", "Investment thesis",
         lambda: drafter.draft_thesis(
             ticker, market_data.get("current_price"),
             {k: market_data.get(k) for k in
              ("pe_ttm", "pe_forward", "market_cap", "52w_high", "52w_low")},
             insights,
         )),
    ]
    for i, (key, label, fn) in enumerate(section_steps):
        progress.progress(35 + i * 10, text=f"Drafting: {label}...")
        log.info(f"✍️ Drafting section: {label}...")
        sections[key] = fn()

    log.success(f"✅ Drafted {len(sections)} sections")

    # Stage 4
    progress.progress(85, text="Running QC review...")
    log.info("🛡️ Running automated quality control review...")
    full_draft = "\n\n".join(f"## {k.upper()} ##\n{v}" for k, v in sections.items())
    reviewer = ReviewOrchestrator(llm)
    qc = reviewer.run(full_draft, sources)
    log.success(f"✅ QC complete: {qc.citation_coverage_pct}% citation coverage, "
                f"severity {qc.overall_severity}")

    # Stage 5
    progress.progress(95, text="Rendering PDF...")
    log.info("📄 Rendering PDF report...")
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
    pdf_buffer = BytesIO()
    PDFReportGenerator().generate(payload, pdf_buffer)
    pdf_buffer.seek(0)

    progress.progress(100, text="Complete!")
    time.sleep(0.5)
    progress.empty()
    log.empty()

    usage = llm.usage_summary()
    st.toast(f"💰 LLM usage: {usage['calls']} calls, "
             f"{usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens")

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "recommendation": recommendation,
        "market_data": market_data,
        "sections": sections,
        "sources": sources,
        "qc": qc,
        "pdf_bytes": pdf_buffer.getvalue(),
        "llm_usage": usage,
    }


# Patch report_generator to accept BytesIO output
def _patch_report_generator():
    """Allow PDFReportGenerator.generate() to accept a BytesIO buffer."""
    from report_generator import PDFReportGenerator
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch

    _original_generate = PDFReportGenerator.generate

    def patched_generate(self, payload, output_path_or_buffer):
        # If a BytesIO, hand it to SimpleDocTemplate directly
        if hasattr(output_path_or_buffer, "write"):
            doc = SimpleDocTemplate(
                output_path_or_buffer, pagesize=letter,
                leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                topMargin=0.6 * inch, bottomMargin=0.6 * inch,
            )
            story = []
            story += self._build_cover(payload)
            section_order = [
                ("company_overview", "1. COMPANY SNAPSHOT"),
                ("performance", "2. FINANCIAL PERFORMANCE SUMMARY"),
                ("drivers_risks", "3. KEY DRIVERS AND RISKS"),
                ("news_highlights", "4. EARNINGS & MANAGEMENT COMMENTARY"),
                ("thesis", "5. INVESTMENT THESIS AND OUTLOOK"),
            ]
            from reportlab.platypus import Spacer, Paragraph
            for key, title in section_order:
                body = payload.sections.get(key)
                if body:
                    story += self._build_section(title, body)
            story += self._build_sources_appendix(payload.sources)
            story += self._build_qc_appendix(payload.qc_report)
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(
                "DISCLAIMER: This document was generated by an AI-driven research "
                "prototype for educational and research-support purposes. It is "
                "not investment advice, not a solicitation, and not a guarantee "
                "of accuracy. All recommendations require human analyst review "
                "and sign-off before use. Past performance does not indicate "
                "future results.",
                self.styles["disclaimer"]
            ))
            doc.build(story, onFirstPage=self._page_decoration,
                      onLaterPages=self._page_decoration)
            return
        # Otherwise call the original (path-based) version
        return _original_generate(self, payload, output_path_or_buffer)

    PDFReportGenerator.generate = patched_generate


_patch_report_generator()


# ---------------------------------------------------------------------------
# RESULT DISPLAY
# ---------------------------------------------------------------------------
def render_results(result: dict):
    """Render the generated report in the UI."""
    rec = result["recommendation"]
    rec_class = {
        "POSITIVE": "rec-positive",
        "WATCHLIST": "rec-watchlist",
        "NEUTRAL": "rec-neutral",
        "CAUTIOUS": "rec-cautious",
    }.get(rec, "rec-neutral")

    # Header strip
    st.markdown(f"## {result['company_name']} ({result['ticker']})")
    st.markdown(f"*{result['sector']} · {result['industry']}*")

    # Top metrics row
    md = result["market_data"]
    col1, col2, col3, col4, col5 = st.columns(5)

    def fmt(v, suffix=""):
        if v is None:
            return "n/a"
        try:
            return f"{float(v):,.2f}{suffix}"
        except (ValueError, TypeError):
            return str(v)

    def fmt_mcap(v):
        if v is None:
            return "n/a"
        v = float(v)
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9: return f"${v/1e9:.1f}B"
        return f"${v:,.0f}"

    with col1:
        st.markdown(f'<div class="metric-card"><b>Recommendation</b><br>'
                    f'<span class="{rec_class}">{rec}</span></div>',
                    unsafe_allow_html=True)
    with col2:
        st.metric("Last Price", f"${fmt(md.get('current_price'))}")
    with col3:
        st.metric("Market Cap", fmt_mcap(md.get("market_cap")))
    with col4:
        st.metric("P/E (TTM)", fmt(md.get("pe_ttm"), "x"))
    with col5:
        qc = result["qc"]
        st.metric("Citation Coverage", f"{qc.citation_coverage_pct}%",
                  delta=f"{qc.overall_severity.upper()} severity",
                  delta_color="off")

    st.markdown("---")

    # Tabs for the report content
    tab1, tab2, tab3, tab4 = st.tabs([
        "📄 Report", "📥 Download PDF", "📚 Sources", "🛡️ QC Findings"
    ])

    with tab1:
        section_titles = {
            "company_overview": "1. Company Snapshot",
            "performance": "2. Financial Performance Summary",
            "drivers_risks": "3. Key Drivers and Risks",
            "news_highlights": "4. Earnings & Management Commentary",
            "thesis": "5. Investment Thesis and Outlook",
        }
        for key, title in section_titles.items():
            body = result["sections"].get(key, "")
            if not body:
                continue
            st.markdown(f"### {title}")
            # Highlight [SRC-X] tags in gold
            highlighted = body.replace("[SRC-",
                "<span class='citation'>[SRC-").replace("]", "]</span>", body.count("[SRC-"))
            # Simpler: regex-based replacement
            import re
            highlighted = re.sub(
                r"\[SRC-(\d+)\]",
                r"<span class='citation'>[SRC-\1]</span>",
                body,
            )
            st.markdown(highlighted, unsafe_allow_html=True)
            st.markdown("")

    with tab2:
        st.markdown("### Download the full PDF report")
        st.markdown(
            "The PDF includes a polished cover page, all five sections, the "
            "source inventory appendix, and the QC summary appendix."
        )
        st.download_button(
            label="⬇️ Download PDF",
            data=result["pdf_bytes"],
            file_name=f"{result['ticker']}_research_report.pdf",
            mime="application/pdf",
            type="primary",
        )

        # Inline preview using base64 embedding
        import base64
        b64 = base64.b64encode(result["pdf_bytes"]).decode()
        pdf_display = f'''
        <iframe src="data:application/pdf;base64,{b64}"
                width="100%" height="700"
                style="border: 1px solid #ccc; border-radius: 4px;">
        </iframe>
        '''
        with st.expander("📖 Preview PDF inline", expanded=False):
            st.markdown(pdf_display, unsafe_allow_html=True)

    with tab3:
        st.markdown("### Source Inventory")
        st.markdown(
            f"Every `[SRC-X]` citation in the report maps to one of these "
            f"**{len(result['sources'])}** documents."
        )
        for s in result["sources"]:
            with st.container():
                st.markdown(
                    f"**{s.source_id}** · `{s.source_type}` · {s.publication_date}"
                )
                st.markdown(f"*{s.title}*")
                st.markdown(f"🔗 [{s.url[:80]}{'...' if len(s.url) > 80 else ''}]({s.url})")
                st.markdown("")

    with tab4:
        qc = result["qc"]
        st.markdown("### Automated QC Findings")
        st.markdown(
            "These checks run automatically on every draft. They surface "
            "issues for the human analyst — they do not auto-fix anything."
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Severity", qc.overall_severity.upper())
        with col_b:
            st.metric("Citation Coverage", f"{qc.citation_coverage_pct}%")
        with col_c:
            st.metric("Ready for Review",
                      "✅ Yes" if qc.ready_for_human_review else "⚠️ No")

        if qc.invalid_citations:
            st.error("**Invalid citations detected:**")
            for tag in qc.invalid_citations:
                st.markdown(f"- `{tag}` does not map to a known source")

        if qc.suspicious_uncited_numbers:
            with st.expander(
                f"⚠️ {len(qc.suspicious_uncited_numbers)} quantitative claim(s) "
                f"flagged for missing nearby citation"
            ):
                for s in qc.suspicious_uncited_numbers:
                    st.markdown(f"- {s}")

        if isinstance(qc.llm_review, dict):
            for key, label in [
                ("potentially_hallucinated_facts", "🚨 Potential hallucinations"),
                ("tone_or_compliance_issues", "📢 Tone / compliance issues"),
                ("internal_inconsistencies", "🔄 Internal inconsistencies"),
                ("missing_required_elements", "❓ Missing required elements"),
            ]:
                items = qc.llm_review.get(key, []) or []
                if items:
                    st.markdown(f"**{label}**")
                    for item in items:
                        st.markdown(f"- {item}")

        st.markdown("---")
        st.markdown(
            "**Human reviewer sign-off:** _______________________ "
            "**Date:** ___________"
        )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if generate_btn:
    try:
        if mode.startswith("Demo"):
            with st.spinner("Running demo pipeline..."):
                result = run_demo()
        else:
            with st.spinner(f"Running live pipeline for {ticker}... "
                            "(this takes 60-90 seconds)"):
                result = run_live(ticker, api_key, model)

        st.success("✅ Report generated successfully!")
        st.session_state["last_result"] = result
    except Exception as e:
        st.error(f"❌ Pipeline failed: {e}")
        st.exception(e)

# Show last result if available
if "last_result" in st.session_state:
    render_results(st.session_state["last_result"])
elif not generate_btn:
    # Onboarding card
    st.info(
        "👈 Configure the run in the sidebar, then click **Generate research "
        "report**.\n\n"
        "**First time?** Start with **Demo mode** — it instantly produces a "
        "real report on NVIDIA using pre-collected public-source data, with "
        "no API key needed."
    )

    with st.expander("🎯 What this prototype demonstrates"):
        st.markdown("""
- **AI-driven workflow**: ingestion, extraction, drafting, and QC are all
  automated. The human analyst's job is to review, not to write.
- **Traceable citations**: every quantitative claim is tagged `[SRC-X]` and
  maps to a real public source (SEC filings, market data, news).
- **Quality control**: a separate review pass flags hallucinations, missing
  citations, and tone issues for the human analyst.
- **Human-in-the-loop**: the system labels itself research support, not
  investment advice. Final sign-off rests with the analyst.
""")
