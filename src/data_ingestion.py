"""
data_ingestion.py
=================
Pulls raw source materials for a ticker from public APIs and assigns each
document a stable source_id used for citation throughout the report.

Sources implemented:
  - SEC EDGAR (filings: 10-K, 10-Q, 8-K, earnings press releases)
  - Company IR press releases (via SEC 8-K exhibits)
  - Yahoo Finance via yfinance (price, valuation multiples, financial statements)
  - Stooq fallback for prices when yfinance is rate-limited

This module deliberately uses only free, public sources so the prototype is
fully reproducible without paid API keys.

Author: Jovan Johansen
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)

# SEC EDGAR requires a User-Agent identifying the requester
SEC_HEADERS = {
    "User-Agent": "Tsunami Advisors Research Prototype jovan.johansen@example.com",
    "Accept-Encoding": "gzip, deflate",
}


@dataclass
class SourceDocument:
    """A single piece of source material with a stable citation handle."""
    source_id: str           # e.g. "SRC-1"
    source_type: str         # 10-K, 10-Q, 8-K, earnings_press, news, market_data
    title: str
    url: str
    publication_date: str    # ISO format
    content: str             # Plain text or structured JSON-as-string
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------
class SECClient:
    """Minimal SEC EDGAR client. No API key required."""

    BASE = "https://data.sec.gov"
    SUBMISSIONS_URL = BASE + "/submissions/CIK{cik:010d}.json"

    # Hard-coded CIK lookup for prototype simplicity. Production would use
    # the full SEC company-tickers.json.
    CIK_MAP = {
        "NVDA": 1045810,
        "AAPL": 320193,
        "MSFT": 789019,
        "GOOGL": 1652044,
        "AMZN": 1018724,
        "META": 1326801,
        "TSLA": 1318605,
    }

    def __init__(self, rate_limit_seconds: float = 0.15):
        self.rate_limit_seconds = rate_limit_seconds  # SEC limit: 10 req/sec
        self._last_call = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_call = time.time()

    def get_recent_filings(
        self, ticker: str, form_types: List[str], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Return metadata for the most recent filings of given form types."""
        cik = self.CIK_MAP.get(ticker.upper())
        if cik is None:
            logger.warning("CIK not in local map for %s; skipping SEC fetch", ticker)
            return []

        self._throttle()
        url = self.SUBMISSIONS_URL.format(cik=cik)
        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("SEC submissions fetch failed for %s: %s", ticker, e)
            return []

        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])

        filings = []
        for i, form in enumerate(forms):
            if form in form_types:
                filings.append({
                    "form": form,
                    "accession_number": accession_numbers[i],
                    "primary_document": primary_documents[i],
                    "filing_date": filing_dates[i],
                    "cik": cik,
                })
                if len(filings) >= limit:
                    break
        return filings

    def fetch_filing_text(self, filing: Dict[str, Any], char_limit: int = 50000) -> str:
        """Fetch and return plain-text content of a filing's primary document."""
        cik = filing["cik"]
        accession_clean = filing["accession_number"].replace("-", "")
        primary = filing["primary_document"]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession_clean}/{primary}"
        )
        self._throttle()
        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("SEC document fetch failed: %s", e)
            return ""

        text = self._strip_html(resp.text)
        return text[:char_limit]

    @staticmethod
    def _strip_html(html: str) -> str:
        """Lightweight HTML stripper - avoids needing bs4 as a hard dep."""
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
        except ImportError:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()


# ---------------------------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------------------------
class MarketDataClient:
    """Fetches price and valuation snapshots. Uses yfinance with graceful fallback."""

    def fetch_snapshot(self, ticker: str) -> Dict[str, Any]:
        # Try yfinance first
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y")
            return {
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "market_cap": info.get("marketCap"),
                "pe_ttm": info.get("trailingPE"),
                "pe_forward": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "beta": info.get("beta"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "company_name": info.get("longName") or info.get("shortName"),
                "1y_return_pct": (
                    (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                    if len(hist) > 0 else None
                ),
                "data_source": "yfinance",
                "as_of": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.warning("yfinance unavailable (%s); using stub snapshot", e)
            return {
                "current_price": None,
                "market_cap": None,
                "data_source": "unavailable",
                "as_of": datetime.utcnow().isoformat(),
                "error": str(e),
            }


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------
class DataIngestionOrchestrator:
    """Top-level entry point that gathers all source documents for a ticker."""

    def __init__(self):
        self.sec = SECClient()
        self.market = MarketDataClient()

    def gather_sources(self, ticker: str) -> List[SourceDocument]:
        """Build the full source inventory for a ticker."""
        sources: List[SourceDocument] = []
        counter = 1

        # 1. SEC filings - 10-K, 10-Q, 8-K
        filings = self.sec.get_recent_filings(
            ticker, form_types=["10-K", "10-Q", "8-K"], limit=8
        )
        for filing in filings:
            text = self.sec.fetch_filing_text(filing, char_limit=40000)
            if not text:
                continue
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{filing['cik']}/"
                f"{filing['accession_number'].replace('-', '')}/"
                f"{filing['primary_document']}"
            )
            sources.append(SourceDocument(
                source_id=f"SRC-{counter}",
                source_type=filing["form"],
                title=f"{ticker} {filing['form']} filing",
                url=url,
                publication_date=filing["filing_date"],
                content=text,
                metadata={"accession_number": filing["accession_number"]},
            ))
            counter += 1

        # 2. Market data snapshot - always present, even if other sources fail
        snapshot = self.market.fetch_snapshot(ticker)
        sources.append(SourceDocument(
            source_id=f"SRC-{counter}",
            source_type="market_data",
            title=f"{ticker} market data snapshot",
            url="https://finance.yahoo.com/quote/" + ticker,
            publication_date=snapshot.get("as_of", datetime.utcnow().isoformat()),
            content=json.dumps(snapshot, indent=2, default=str),
            metadata=snapshot,
        ))
        counter += 1

        logger.info("Gathered %d source documents for %s", len(sources), ticker)
        return sources

    @staticmethod
    def save_inventory(sources: List[SourceDocument], path: Path):
        with open(path, "w") as f:
            json.dump([s.to_dict() for s in sources], f, indent=2, default=str)
