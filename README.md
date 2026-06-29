# Automated Equity Research Report Writer

**Author:** Jovan Mikael Johansen· 

A prototype that turns a single ticker into a structured, fully-cited equity research report using a Generative-AI-first workflow. Built in Python with Anthropic Claude as the reasoning engine, SEC EDGAR + Yahoo Finance for source data, and `reportlab` for the final PDF.

---

## What it produces

For a given ticker, the system outputs:

1. **A polished PDF research report** — cover page with snapshot, five drafted sections (Company Snapshot, Financial Performance, Drivers & Risks, Earnings & Management Commentary, Investment Thesis & Outlook), a source-inventory appendix, and an automated QC summary appendix.
2. **A source inventory JSON** — every document used, each with a stable `[SRC-X]` citation handle that maps to a real public URL.
3. **A draft-sections JSON** — the raw section text and QC findings, for traceability.
4. **A human-readable QC report** (`.txt`) — citation coverage, invalid citations, suspicious uncited numbers, and LLM-flagged hallucination risks.

A full sample run (NVDA, April 2026) is included in `outputs/`.

---

## Pipeline at a glance

```
   ticker
     │
     ▼
   data_ingestion        ──► SEC filings + market data + source IDs
     │
     ▼
   InsightExtractor      ──► per-document JSON insights (Claude)
     │
     ▼
   SectionDrafter        ──► 5 section drafts with [SRC-X] citations (Claude)
     │
     ▼
   ReviewOrchestrator    ──► rule-based + LLM QC findings
     │
     ▼
   PDFReportGenerator    ──► final PDF with cover, sections, appendices
     │
     ▼
   HUMAN ANALYST          (resolves QC flags, signs off)
```

Two-stage extract→draft is the core architectural decision. It forces Claude to anchor in pre-validated structured facts, which is what raised citation coverage from ~50% in early single-prompt prototypes to >95% in the current build.

---

## Repository layout

```
equity-research-prototype/
├── README.md                    ← you are here
├── app.py                       ← Streamlit web UI (the front-end)
├── requirements.txt
├── .streamlit/
│   ├── config.toml              ← theme matching the report palette
│   └── secrets.toml.example     ← template for API key (never commit real one)
├── src/
│   ├── main.py                  ← live pipeline orchestrator (CLI)
│   ├── demo_runner.py           ← deterministic demo (no API key needed)
│   ├── data_ingestion.py        ← SEC EDGAR + market-data clients
│   ├── analysis_engine.py       ← Claude wrapper, extractor, drafter
│   ├── review_layer.py          ← rule-based + LLM QC
│   ├── report_generator.py      ← reportlab PDF rendering
│   ├── prompts.py               ← all prompts in one place
│   └── build_docs.py            ← generates docs/build_documentation.pdf
├── outputs/
│   ├── NVDA_research_report.pdf       ← sample output
│   ├── NVDA_source_inventory.json
│   ├── NVDA_draft_sections.json
│   └── NVDA_qc_report.txt
├── docs/
│   └── build_documentation.pdf  ← case-study build doc deliverable
└── sample_inputs/
    └── tickers.txt              ← starter tickers
```

---

## Running it

The fastest way to demo this is the **web UI**. Pick a ticker, click a button, get a report.

### Option A — Web UI (recommended for demos)

```bash
pip install -r requirements.txt
streamlit run app.py
```

That opens `http://localhost:8501` in your browser. From there:

1. **Pick a mode** in the sidebar — **Demo** for instant NVDA repro (no API key), or **Live** for any supported ticker (requires Anthropic API key).
2. **Click "Generate research report"**.
3. The app shows a live progress bar through all five pipeline stages, then renders the report inline with tabs for the report body, PDF download, source inventory, and QC findings.

This is the version to show Neil. It runs locally with one command and you can deploy it free to Streamlit Community Cloud (see "Deployment" below).

### Option B — Reproduce the sample report from CLI (no API key)

The demo runner produces the exact NVDA report shipped in `outputs/` using pre-collected real public-source data. Useful for grading and CI checks.

```bash
pip install -r requirements.txt
cd src
python demo_runner.py
```

This will overwrite `outputs/NVDA_research_report.pdf`, the source inventory JSON, and the draft sections JSON.

### Option C — Full live pipeline from CLI

Requires an Anthropic API key.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
cd src
python main.py NVDA --output-dir ../outputs
# or any other supported ticker:
python main.py AAPL
python main.py MSFT --verbose
```

CIKs are pre-loaded for NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA. Adding more is a one-line change to `data_ingestion.SECClient.CIK_MAP`.

---

## Deployment (free public link for Neil to try)

Streamlit Community Cloud lets you deploy this app for free in about three minutes:

1. Push the repo to GitHub (public or private — Streamlit Cloud supports both).
2. Go to https://streamlit.io/cloud and sign in with GitHub.
3. Click **New app**, point it at your repo, set the main file to `app.py`.
4. In the app's **Settings → Secrets**, paste:
   ```
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```
5. Click **Deploy**. You get a public URL like `https://your-app.streamlit.app`.

---

## Design choices worth calling out

**Why two-stage extract→draft.** A single mega-prompt with all filings concatenated produces fluent prose but contradicts itself across sections and cites poorly. Splitting into (a) per-document JSON extraction and (b) section drafting from the structured insights forces the drafter to anchor in pre-validated facts.

**Why one LLM call per section.** Smaller context windows produce sharper, more cite-able output than a single mega-prompt. Each section also has its own prompt with section-specific guardrails and word counts.

**Why a separate review LLM call.** Asking the same model to self-correct in one pass is unreliable. A clean, cold (`temperature=0`) review pass that is told to *flag, not fix* surfaces issues that the drafter missed without silently rewriting facts.

**Why the regex citation-coverage check.** The LLM review is good but expensive and non-deterministic. A regex pass for `[SRC-X]` proximity to financial-looking numbers is essentially free, fully deterministic, and catches the same class of issue most of the time.

**Why I labeled outputs "research support, not advice."** Compliance-by-design. The model is good enough to produce something that *looks* publishable, which is exactly when the disclaimers matter most.

---

## Limitations (full list in `docs/build_documentation.pdf`)

- 18K-character cap per filing per call truncates risk-factor and exhibit detail in long 10-Ks. Production fix: chunked retrieval.
- `yfinance` is unofficial and rate-limited. Production: Bloomberg / Refinitiv.
- No real-time event handling. If material news breaks during a run, the report doesn't pick it up.
- English-language US-listed equities only. HK / Indonesian markets need localized prompts and source hookups.

---

## Reflection (1 paragraph)

The two-stage extract→draft architecture was the single biggest quality unlock — citation coverage rose from ~50% to >95% by forcing the LLM to first produce structured JSON insights from each source and then draft from those structured facts rather than from raw filings. The biggest weakness I couldn't fully solve was forward-looking commentary: even with a careful prompt asking for monitorable triggers, the model occasionally drifted toward implicit recommendations, which is why the human-review layer is non-negotiable rather than a nice-to-have. In a v2 I would replace the character-cap ingestion with chunked embedding-based retrieval, add a peer-comparison module, swap the single review pass for a bull-vs-bear debate pattern, and separate the recommendation framing from the drafter so the human picks POSITIVE / WATCHLIST / NEUTRAL / CAUTIOUS *before* the thesis is drafted (which avoids the AI choosing its own framing).

---

## Disclaimer

This prototype is for educational and research-support purposes. Outputs are not investment advice, not a solicitation, and not a guarantee of accuracy. All recommendations require human analyst review and sign-off before use.
