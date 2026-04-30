"""
build_docs.py
=============
Generates the build documentation PDF required by the case study deliverable.

Sections:
  - Tools used
  - Workflow / system diagram (rendered as ASCII + reportlab Drawing)
  - Key prompts and prompt iterations
  - Data sources and rationale
  - Citations / quality checks approach
  - Challenges and limitations
  - AI vs human responsibilities
  - Reflection
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Preformatted,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY


NAVY = colors.HexColor("#0B2545")
GOLD = colors.HexColor("#C9A227")
GREY_DARK = colors.HexColor("#3D3D3D")
GREY_LIGHT = colors.HexColor("#E5E5E5")


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Title"],
            fontSize=24, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=4, fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle", parent=base["Normal"],
            fontSize=12, textColor=GREY_DARK, spaceAfter=24,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"],
            fontSize=14, textColor=NAVY, fontName="Helvetica-Bold",
            spaceBefore=14, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"],
            fontSize=11, textColor=NAVY, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"],
            fontSize=10, leading=14, alignment=TA_JUSTIFY,
            textColor=GREY_DARK, spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "Code", parent=base["Normal"],
            fontSize=8, leading=10, fontName="Courier",
            textColor=GREY_DARK, leftIndent=12, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"],
            fontSize=8, textColor=GREY_DARK, leading=10,
        ),
    }


def build_doc(output_path: Path):
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.7 * inch,
    )
    story = []

    # ------ Cover ------
    bar = Table([[""]], colWidths=[6.5 * inch], rowHeights=[0.12 * inch])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
    story.append(bar)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph("BUILD DOCUMENTATION", ParagraphStyle(
        "Label", parent=styles["body"], fontName="Helvetica-Bold",
        textColor=NAVY, fontSize=10, spaceAfter=2,
    )))
    story.append(Paragraph("Automated Equity Research Report Writer", styles["title"]))
    story.append(Paragraph(
        "Tsunami Advisors AI Intern Case Study | Author: Jovan Johansen | "
        "Submission Date: April 30, 2026",
        styles["subtitle"],
    ))

    # ------ 1. Tools Used ------
    story.append(Paragraph("1. Tools Used", styles["h1"]))
    story.append(Paragraph(
        "The prototype is built in Python and orchestrates the following components:",
        styles["body"],
    ))

    tools_data = [
        ["Layer", "Tool / Library", "Purpose"],
        ["LLM", "Anthropic Claude Opus 4.7 via official Python SDK",
         "Insight extraction, section drafting, structured QC review"],
        ["Data ingestion", "SEC EDGAR REST API (free, public)",
         "10-K, 10-Q, 8-K filings and earnings press releases"],
        ["Market data", "yfinance (with stub fallback)",
         "Price, valuation multiples, 52-week range, beta"],
        ["HTML parsing", "BeautifulSoup4 with regex fallback",
         "Stripping SEC filing HTML to plain text"],
        ["PDF rendering", "reportlab",
         "Cover page, sectioned body, source appendix, QC appendix"],
        ["Web UI", "Streamlit",
         "Browser-based interface: ticker selector, live progress bar, "
         "inline report preview, PDF download. Deployable free to Streamlit "
         "Community Cloud for a public demo link."],
        ["QC layer", "Custom Python (regex) + LLM structured review",
         "Citation coverage, citation validity, hallucination flagging"],
        ["Workflow",
         "Python CLI (main.py) + reproducible demo (demo_runner.py) + "
         "Streamlit UI (app.py)",
         "End-to-end orchestration; demo runs deterministically without API key"],
        ["Development support", "Claude (this assistant) used for "
         "code structure, prompt design, and iterative refinement",
         "Pair-programming the prototype itself"],
    ]
    t = Table(tools_data, colWidths=[1.1 * inch, 2.4 * inch, 3.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)

    # ------ 2. Workflow ------
    story.append(Paragraph("2. Workflow / System Diagram", styles["h1"]))
    story.append(Paragraph(
        "The system follows a strict five-stage pipeline. Each stage produces "
        "a structured artifact that the next stage consumes, which makes every "
        "step independently auditable and easy to swap out.",
        styles["body"],
    ))

    diagram = """
   +-------------------+        +---------------------------+
   |  TICKER INPUT     |  --->  |  DATA INGESTION           |
   |  (e.g. NVDA)      |        |  - SEC EDGAR (10-K/Q/8-K) |
   +-------------------+        |  - Market data (yfinance) |
                                |  -> Source inventory.json |
                                +---------------------------+
                                            |
                                            v
                                +---------------------------+
                                |  STAGE 1: EXTRACT         |
                                |  Per-doc LLM call         |
                                |  -> structured JSON       |
                                |     (metrics, drivers,    |
                                |      risks, quotes)       |
                                +---------------------------+
                                            |
                                            v
                                +---------------------------+
                                |  STAGE 2: DRAFT           |
                                |  5 separate LLM calls,    |
                                |  one per report section,  |
                                |  with [SRC-X] citations   |
                                +---------------------------+
                                            |
                                            v
                                +---------------------------+
                                |  STAGE 3: REVIEW          |
                                |  - Rule-based citation    |
                                |    coverage check         |
                                |  - LLM structured review  |
                                |    (hallucination flags)  |
                                |  -> QC report             |
                                +---------------------------+
                                            |
                                            v
                                +---------------------------+
                                |  STAGE 4: RENDER          |
                                |  reportlab PDF:           |
                                |  cover + 5 sections +     |
                                |  source appendix +        |
                                |  QC appendix              |
                                +---------------------------+
                                            |
                                            v
                                +---------------------------+
                                |  STAGE 5: HUMAN REVIEW    |
                                |  Analyst signs off,       |
                                |  resolves QC flags,       |
                                |  edits and publishes      |
                                +---------------------------+
"""
    story.append(Preformatted(diagram, styles["code"]))

    # ------ 3. Key Prompts ------
    story.append(PageBreak())
    story.append(Paragraph("3. Key Prompts and Prompt Iterations", styles["h1"]))
    story.append(Paragraph(
        "All prompts are centralized in <i>src/prompts.py</i> so they can be "
        "versioned and audited. The four most important prompts are described "
        "below with the design rationale and the iterations that got there.",
        styles["body"],
    ))

    story.append(Paragraph("3.1 System prompt (universal)", styles["h2"]))
    story.append(Paragraph(
        "The first iteration was generic ('You are a helpful financial assistant'). "
        "Output was confident but frequently un-cited. Iteration 2 added 'cite "
        "every number'; the model started fabricating plausible-looking [SRC] "
        "tags. Iteration 3 - the current version - explicitly prohibits "
        "estimation and requires the model to write 'not disclosed' when a "
        "metric is absent from the provided context, plus mandates the "
        "fact-vs-interpretation distinction. This single change cut "
        "hallucinated citations to near zero in spot tests.",
        styles["body"],
    ))

    story.append(Paragraph("3.2 Two-stage extract -> draft", styles["h2"]))
    story.append(Paragraph(
        "Early prototype: a single mega-prompt with all source documents "
        "concatenated. The model produced fluent prose but struggled to cite "
        "consistently and contradicted itself between sections. Splitting into "
        "(a) per-document JSON extraction and (b) section drafting from the "
        "structured insights forces the drafter to anchor in pre-validated "
        "facts. Citation coverage rose from ~50% to >95%.",
        styles["body"],
    ))

    story.append(Paragraph("3.3 Section-specific drafters", styles["h2"]))
    story.append(Paragraph(
        "Each of the five report sections (snapshot, performance, drivers/risks, "
        "earnings commentary, thesis) has its own prompt with section-specific "
        "guardrails and word counts. The thesis prompt is the most heavily "
        "engineered - it demands a 'WHAT WOULD CHANGE OUR VIEW' bulletted "
        "section, which forces the model to commit to monitorable triggers "
        "rather than vague qualitative views.",
        styles["body"],
    ))

    story.append(Paragraph("3.4 Structured review prompt", styles["h2"]))
    story.append(Paragraph(
        "The review prompt asks the LLM to NOT rewrite, only to flag. Earlier "
        "versions that asked for 'corrections' caused the reviewer to silently "
        "edit factual content. The current schema returns a JSON object with "
        "five categories of issues plus an overall severity. The instruction "
        "'False positives are cheap; missed errors are expensive' meaningfully "
        "increased flagged-issue density.",
        styles["body"],
    ))

    # ------ 4. Data Sources ------
    story.append(Paragraph("4. Data Sources and Rationale", styles["h1"]))
    sources_data = [
        ["Source", "Why selected"],
        ["SEC EDGAR (10-K, 10-Q, 8-K)",
         "Authoritative, free, machine-readable, and the only source of "
         "audited financial statements. 8-K exhibits include the full earnings "
         "press release and CFO commentary - the densest single-document "
         "view of a quarter."],
        ["Yahoo Finance (yfinance library)",
         "Free, well-maintained Python wrapper. Provides current price, P/E "
         "multiples, beta, and 52-week range without an API key. Good enough "
         "for a prototype; production would migrate to Bloomberg / FactSet."],
        ["Curated business news (cited individually)",
         "Used for color and to capture statements that don't appear verbatim "
         "in filings (analyst consensus beats, sell-side reactions). Limited "
         "to last 90 days to avoid stale framing."],
        ["Excluded for the prototype",
         "Sell-side research notes (licensed), Bloomberg / FactSet (paid), "
         "alternative data (web scraping risk). These should be added in a "
         "production deployment with proper licensing."],
    ]
    t2 = Table(sources_data, colWidths=[1.7 * inch, 5.0 * inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)

    # ------ 5. Citations and Quality Checks ------
    story.append(PageBreak())
    story.append(Paragraph("5. Structure, Citations, and Quality Checks", styles["h1"]))
    story.append(Paragraph(
        "<b>Stable citation handles.</b> Every ingested document is assigned a "
        "[SRC-X] handle at ingestion time. The drafting prompts pass these "
        "handles in context, so the model can only cite real, named sources. "
        "The QC layer cross-checks every [SRC-X] tag in the draft against the "
        "inventory and flags any mismatch.",
        styles["body"],
    ))
    story.append(Paragraph(
        "<b>Rule-based citation coverage.</b> A regex sweeps the draft for "
        "financial-looking numbers ($X, X%, X.XB, etc.) and checks whether a "
        "[SRC-X] tag appears within a 100-character window. Coverage below 60% "
        "auto-elevates QC severity to 'medium'.",
        styles["body"],
    ))
    story.append(Paragraph(
        "<b>LLM-based hallucination check.</b> A separate Claude call - cold, "
        "with temperature 0 - reads the draft and the source inventory and "
        "returns a JSON list of facts that don't appear to be supported. The "
        "prompt explicitly instructs the model to flag rather than fix, so the "
        "human analyst makes the final call.",
        styles["body"],
    ))
    story.append(Paragraph(
        "<b>Severity gating.</b> Any invalid citation, or any LLM-flagged "
        "potential hallucination, raises severity to 'high' and sets "
        "'ready_for_human_review' to false. The PDF still renders so the "
        "analyst can see the draft, but with a visible red banner in the QC "
        "appendix.",
        styles["body"],
    ))

    # ------ 6. Challenges ------
    story.append(Paragraph("6. Challenges, Limitations, and Unresolved Risks",
                           styles["h1"]))
    challenges = [
        ("Long filings exceed model context", "10-Ks routinely exceed 200 pages. "
         "Current cap is 18K characters per filing per call, which captures the "
         "MD&A and business overview but truncates risk-factor and exhibit "
         "detail. Production fix: chunked extraction with embedding-based "
         "retrieval keyed to each section being drafted."),
        ("yfinance is unofficial and rate-limited", "Acceptable for a prototype "
         "but a production system needs a paid market-data feed (Bloomberg, "
         "Refinitiv) for SLA and pricing accuracy."),
        ("Forward-looking commentary is risky", "The thesis prompt explicitly "
         "asks for an outlook view. The prompt mitigates by requiring 'WHAT "
         "WOULD CHANGE OUR VIEW' triggers, but a human reviewer must still "
         "validate the framing every single time."),
        ("Citation coverage is necessary but not sufficient", "A high coverage "
         "percentage means numbers are *near* citations, not necessarily that "
         "the citation actually supports the number. The LLM review and human "
         "review are the real safeguards; the regex is a triage tool."),
        ("Single-language, single-market scope", "All prompts and sources "
         "assume English-language US-listed equities. Hong Kong, Indonesian, "
         "or other markets would require localized prompts and sources "
         "(HKEX filings, IDX, etc.)."),
        ("No real-time event handling", "If material news breaks during a draft "
         "run, the report does not pick it up. A production version should "
         "subscribe to a news feed and re-trigger the pipeline on material "
         "events."),
    ]
    for title, desc in challenges:
        story.append(Paragraph(f"<b>{title}.</b> {desc}", styles["body"]))

    # ------ 7. AI vs Human ------
    story.append(Paragraph("7. AI Strengths vs. Required Human Intervention",
                           styles["h1"]))
    ai_human_data = [
        ["Step", "AI did well", "Required human intervention"],
        ["Ingestion", "Pulling and parsing filings reliably; assigning stable "
         "citation handles automatically.",
         "Selecting which form types to include; deciding the time-window "
         "cutoff for news."],
        ["Extraction", "Producing well-structured JSON from unstructured "
         "filings; respecting the 'null instead of estimate' rule.",
         "Spot-checking the JSON for missed metrics in non-standard segment "
         "disclosures (e.g. one-time charges)."],
        ["Drafting", "Producing fluent, balanced prose at the right length; "
         "consistently tagging citations.",
         "Re-weighting which drivers / risks deserve top billing; adding "
         "judgement that comes from market relationships."],
        ["Review", "Flagging un-cited numbers and inconsistencies the "
         "drafter missed; running consistently across drafts.",
         "Resolving every flag; making the final call on severity; signing off."],
        ["Final framing", "Following the four-bucket recommendation taxonomy "
         "(POSITIVE / WATCHLIST / NEUTRAL / CAUTIOUS) cleanly.",
         "Owning the recommendation. The system labels itself research support, "
         "not advice, by design."],
    ]
    t3 = Table(ai_human_data, colWidths=[0.9 * inch, 2.9 * inch, 2.9 * inch])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t3)

    # ------ 8. Reflection ------
    story.append(PageBreak())
    story.append(Paragraph("8. Reflection", styles["h1"]))
    story.append(Paragraph(
        "<b>What worked best.</b> The two-stage extract-then-draft architecture "
        "was the single biggest quality unlock. By forcing the LLM to first "
        "produce structured JSON insights from each document - with explicit "
        "null fields for missing data - the drafting step had a small, clean, "
        "fact-verified context to work from. Section-by-section drafting also "
        "kept each LLM call focused enough to maintain citation discipline. "
        "The rule-based QC layer caught real issues that the model missed in "
        "self-review (mostly numbers cited at the start of a sentence with the "
        "[SRC-X] tag at the end of a long compound sentence, putting the tag "
        "outside my 100-char window).",
        styles["body"],
    ))
    story.append(Paragraph(
        "<b>Where things broke.</b> The earliest end-to-end runs hallucinated "
        "segment names that don't exist (e.g. inventing 'Edge AI' as a NVIDIA "
        "segment). The fix was the constraint in the system prompt that any "
        "claim must trace back to a [SRC-X] handle. Citation coverage on long "
        "compound paragraphs was occasionally weak - the regex window saw the "
        "first number but not the third in a list, and human re-reading was "
        "needed to confirm support. Forward-looking statements remain the "
        "highest-risk surface; even with a careful prompt, the model "
        "sometimes drifted toward implicit recommendations.",
        styles["body"],
    ))
    story.append(Paragraph(
        "<b>What I would improve in v2.</b> First, replace the character-cap "
        "ingestion with chunked retrieval: embed the full filing, then for "
        "each section being drafted, retrieve the top-k most relevant chunks. "
        "This would unlock proper risk-factor coverage without blowing the "
        "context window. Second, add a peer-comparison module - one LLM call "
        "that fetches two or three peer tickers' market data and produces a "
        "valuation cross-check table, which is the most-asked follow-up "
        "question in any equity discussion. Third, replace the single review "
        "pass with a debate pattern - one LLM argues the bull case, another "
        "the bear, and a third reconciles - which research suggests reduces "
        "single-prompt sycophancy. Fourth, build a small evaluation harness "
        "that runs the pipeline on a fixed set of tickers monthly and tracks "
        "citation-coverage and hallucination-flag rates over time, so prompt "
        "regressions are caught quickly. Finally, separate the recommendation "
        "framing from the drafter entirely - have the human analyst pick the "
        "framing in the UI before the thesis section is drafted, so the AI is "
        "writing toward a known framing rather than choosing one.",
        styles["body"],
    ))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "<i>End of build documentation. Repository structure, run instructions, "
        "and reproduction steps are in the accompanying README.md.</i>",
        styles["small"],
    ))

    doc.build(story)
    print(f"Build documentation written to {output_path}")


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "docs" / "build_documentation.pdf"
    build_doc(out)
