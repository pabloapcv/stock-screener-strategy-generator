"""Stock universe definitions — S&P 500 and NASDAQ 100 tickers."""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd
import requests

logger = logging.getLogger(__name__)

SP500_CSV = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)
NASDAQ100_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-screener/1.0)"}

# Delisted / renamed tickers to exclude from fallback lists
_EXCLUDED = {"ANSS", "SQ", "WBA", "PARA"}


def _normalize_ticker(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


@lru_cache(maxsize=1)
def get_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 constituents."""
    try:
        resp = requests.get(SP500_CSV, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(pd.io.common.StringIO(resp.text))
        tickers = [_normalize_ticker(s) for s in df["Symbol"].tolist()]
        tickers = [t for t in tickers if t not in _EXCLUDED]
        logger.info("Loaded %d S&P 500 tickers", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("Failed to fetch S&P 500 list: %s. Using fallback.", e)
        return _FALLBACK_SP500


@lru_cache(maxsize=1)
def get_nasdaq100_tickers() -> list[str]:
    """Fetch current NASDAQ 100 constituents."""
    try:
        resp = requests.get(NASDAQ100_API, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("data", {}).get("rows", [])
        tickers = [_normalize_ticker(r["symbol"]) for r in rows if r.get("symbol")]
        tickers = [t for t in tickers if t not in _EXCLUDED]
        logger.info("Loaded %d NASDAQ 100 tickers", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("Failed to fetch NASDAQ 100 list: %s. Using fallback.", e)
        return _FALLBACK_NASDAQ100


def get_combined_universe(sources: list[str] | None = None) -> list[str]:
    """Return deduplicated ticker universe from configured sources."""
    sources = sources or ["sp500", "nasdaq100"]
    tickers: set[str] = set()
    if "sp500" in sources:
        tickers.update(get_sp500_tickers())
    if "nasdaq100" in sources:
        tickers.update(get_nasdaq100_tickers())
    return sorted(t for t in tickers if t not in _EXCLUDED)


# Curated fallback if remote sources are unreachable
_FALLBACK_SP500 = [
    t for t in [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JNJ",
        "V", "XOM", "JPM", "WMT", "MA", "PG", "HD", "CVX", "MRK", "ABBV", "KO", "PEP",
        "COST", "AVGO", "LLY", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "NEE", "TXN",
        "NKE", "PM", "UNP", "RTX", "HON", "LOW", "ORCL", "IBM", "QCOM", "INTC", "AMD",
        "CRM", "NOW", "ADBE", "NFLX", "PANW", "CRWD", "ANET", "APP", "MELI", "SNPS",
        "CDNS", "FTNT", "ZS", "DDOG", "NET", "SNOW", "PLTR", "UBER", "ABNB",
        "SHOP", "COIN", "ARM", "SMCI", "DELL", "HPE", "MU", "LRCX", "KLAC", "AMAT",
    ]
    if t not in _EXCLUDED
]

_FALLBACK_NASDAQ100 = [
    t for t in [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", "AVGO", "COST",
        "NFLX", "AMD", "PEP", "ADBE", "CSCO", "TMUS", "INTC", "CMCSA", "QCOM", "INTU",
        "AMGN", "TXN", "HON", "AMAT", "ISRG", "BKNG", "VRTX", "ADP", "SBUX", "GILD",
        "MDLZ", "ADI", "REGN", "LRCX", "PANW", "MU", "SNPS", "CDNS", "KLAC", "MELI",
        "PYPL", "CRWD", "MAR", "ORLY", "CTAS", "ABNB", "FTNT", "WDAY", "DXCM", "MNST",
        "KDP", "ADSK", "CPRT", "PAYX", "ROST", "ODFL", "FAST", "BIIB", "EA", "VRSK",
        "XEL", "CSGP", "GEHC", "FANG", "KHC", "CTSH", "EXC", "LULU", "ON", "TTD",
        "ZS", "DDOG", "TEAM", "MRVL", "IDXX", "WBD", "ILMN", "DLTR", "ALGN",
        "ARM", "SMCI", "APP", "COIN",
    ]
    if t not in _EXCLUDED
]
