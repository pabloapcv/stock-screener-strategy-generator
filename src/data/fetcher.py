"""Fetch and cache stock price history and fundamentals via yfinance."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator

logger = logging.getLogger(__name__)


@dataclass
class StockData:
    """Enriched stock snapshot for screening."""

    ticker: str
    price: float = 0.0
    market_cap: float = 0.0
    avg_volume: float = 0.0
    relative_volume: float = 0.0
    beta: float = 0.0
    revenue_growth: float | None = None
    eps_growth: float | None = None
    roe: float | None = None
    analyst_rating: float | None = None
    analyst_count: int = 0
    target_mean_price: float | None = None
    target_high_price: float | None = None
    performance_1w: float | None = None
    performance_1m: float | None = None
    performance_3m: float | None = None
    # Technicals
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_52w_high: float | None = None
    price_above_sma_50: bool = False
    price_above_sma_200: bool = False
    sma_50_above_sma_200: bool = False
    # Entry signals
    pullback_to_sma_20: bool = False
    pullback_to_sma_50: bool = False
    breakout_from_consolidation: bool = False
    relative_strength_vs_spy: bool = False
    volume_confirmation: bool = False
    # Options (populated by options module)
    options_score: float = 0.0
    options_pass: bool = False
    options_details: dict[str, Any] = field(default_factory=dict)
    # Analyst momentum proxies
    eps_revision_trend: float = 0.0
    # Metadata
    errors: list[str] = field(default_factory=list)


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _compute_relative_volume(
    volume: pd.Series,
    avg_volume_info: float | None = None,
) -> tuple[float, float]:
    """Relative volume using the best recent complete session vs average daily volume."""
    avg_vol_20 = float(volume.tail(20).mean())
    avg_vol = avg_volume_info if avg_volume_info and avg_volume_info > 0 else avg_vol_20

    complete_threshold = avg_vol_20 * 0.55
    rel_vols: list[float] = []
    session_vol = None

    for i in range(-1, -min(len(volume), 8) - 1, -1):
        v = float(volume.iloc[i])
        if v >= complete_threshold:
            if session_vol is None:
                session_vol = v
            rel_vols.append(v / avg_vol if avg_vol > 0 else 0.0)

    if session_vol is None:
        session_vol = float(volume.iloc[-2]) if len(volume) > 1 else float(volume.iloc[-1])
        rel_vols.append(session_vol / avg_vol if avg_vol > 0 else 0.0)

    # Best recent session — institutions accumulate over multiple days
    rel_vol = max(rel_vols) if rel_vols else 0.0
    return avg_vol, rel_vol


def _compute_technicals(
    hist: pd.DataFrame,
    spy_hist: pd.DataFrame | None,
    avg_volume_info: float | None = None,
) -> dict[str, Any]:
    """Calculate technical indicators from price history."""
    result: dict[str, Any] = {}
    if hist is None or len(hist) < 50:
        return result

    close = hist["Close"]
    volume = hist["Volume"]
    price = float(close.iloc[-1])

    sma_20 = SMAIndicator(close, window=20).sma_indicator()
    sma_50 = SMAIndicator(close, window=50).sma_indicator()
    sma_200 = SMAIndicator(close, window=200).sma_indicator() if len(close) >= 200 else None

    rsi_series = RSIIndicator(close, window=14).rsi()

    high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
    low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())

    result["price"] = price
    result["sma_20"] = _safe_float(sma_20.iloc[-1])
    result["sma_50"] = _safe_float(sma_50.iloc[-1])
    result["sma_200"] = _safe_float(sma_200.iloc[-1]) if sma_200 is not None else None
    result["rsi"] = _safe_float(rsi_series.iloc[-1])
    result["high_52w"] = high_52w
    result["low_52w"] = low_52w
    result["pct_from_52w_high"] = (high_52w - price) / high_52w if high_52w > 0 else None

    sma50_val = result["sma_50"]
    sma200_val = result["sma_200"]
    result["price_above_sma_50"] = sma50_val is not None and price > sma50_val
    result["price_above_sma_200"] = sma200_val is not None and price > sma200_val
    result["sma_50_above_sma_200"] = (
        sma50_val is not None and sma200_val is not None and sma50_val > sma200_val
    )

    # Performance
    if len(close) >= 5:
        result["performance_1w"] = float(close.iloc[-1] / close.iloc[-5] - 1)
    if len(close) >= 21:
        result["performance_1m"] = float(close.iloc[-1] / close.iloc[-21] - 1)
    if len(close) >= 63:
        result["performance_3m"] = float(close.iloc[-1] / close.iloc[-63] - 1)

    avg_vol, rel_vol = _compute_relative_volume(volume, avg_volume_info)
    result["avg_volume"] = avg_vol
    result["relative_volume"] = rel_vol

    # Pullback signals: price within 2% above SMA (touching support)
    if result["sma_20"]:
        dist_20 = (price - result["sma_20"]) / result["sma_20"]
        result["pullback_to_sma_20"] = -0.02 <= dist_20 <= 0.03
    if sma50_val:
        dist_50 = (price - sma50_val) / sma50_val
        result["pullback_to_sma_50"] = -0.02 <= dist_50 <= 0.03

    # Breakout: price at 20-day high with above-average volume
    high_20 = float(close.tail(20).max())
    result["breakout_from_consolidation"] = (
        price >= high_20 * 0.995 and result["relative_volume"] >= 1.3
    )

    # Volume confirmation: rising volume on up day
    if len(close) >= 2:
        price_up = close.iloc[-1] > close.iloc[-2]
        vol_up = volume.iloc[-1] > volume.iloc[-2]
        result["volume_confirmation"] = bool(price_up and vol_up)

    # Relative strength vs SPY (1-month)
    if spy_hist is not None and len(spy_hist) >= 21 and len(close) >= 21:
        stock_ret = close.iloc[-1] / close.iloc[-21] - 1
        spy_ret = spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[-21] - 1
        result["relative_strength_vs_spy"] = float(stock_ret) > float(spy_ret)

    return result


def _extract_fundamentals(info: dict) -> dict[str, Any]:
    """Pull fundamental metrics from yfinance info dict."""
    result: dict[str, Any] = {}

    result["market_cap"] = _safe_float(info.get("marketCap")) or 0.0
    result["beta"] = _safe_float(info.get("beta")) or 0.0

    # Revenue growth
    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        result["revenue_growth"] = float(rev_growth)

    # EPS growth — yfinance provides earningsGrowth or trailingEps change
    eps_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
    if eps_growth is not None:
        result["eps_growth"] = float(eps_growth)
    else:
        # Fallback: infer from forward vs trailing EPS
        trailing_eps = _safe_float(info.get("trailingEps"))
        forward_eps = _safe_float(info.get("forwardEps"))
        if trailing_eps and forward_eps and trailing_eps != 0:
            result["eps_growth"] = (forward_eps - trailing_eps) / abs(trailing_eps)

    # ROE
    roe = info.get("returnOnEquity")
    if roe is not None:
        result["roe"] = float(roe)

    # Analyst data
    rec = info.get("recommendationMean")
    if rec is not None:
        # yfinance: 1=Strong Buy, 5=Strong Sell — invert for intuitive scoring
        result["analyst_rating"] = 6.0 - float(rec)
    result["analyst_count"] = int(info.get("numberOfAnalystOpinions") or 0)
    result["target_mean_price"] = _safe_float(info.get("targetMeanPrice"))
    result["target_high_price"] = _safe_float(info.get("targetHighPrice"))

    # EPS revision proxy: compare current vs prior year EPS
    trailing_eps = _safe_float(info.get("trailingEps"))
    forward_eps = _safe_float(info.get("forwardEps"))
    if trailing_eps and forward_eps and trailing_eps != 0:
        result["eps_revision_trend"] = (forward_eps - trailing_eps) / abs(trailing_eps)

    return result


def _download_history(symbols: list[str], period: str = "1y") -> pd.DataFrame:
    """Download price history with retry on rate limits."""
    for attempt in range(4):
        try:
            return yf.download(
                symbols,
                period=period,
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            if "Rate" in str(e) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def _history_for_ticker(downloaded: pd.DataFrame, ticker: str, multi: bool) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        try:
            hist = downloaded[ticker]
            return hist.dropna(how="all") if hist is not None else pd.DataFrame()
        except KeyError:
            return pd.DataFrame()
    return downloaded.dropna(how="all")


def fetch_stock_from_data(
    ticker: str,
    hist: pd.DataFrame,
    spy_hist: pd.DataFrame | None,
    info: dict | None = None,
) -> StockData:
    """Build StockData from pre-fetched history and optional info."""
    stock = StockData(ticker=ticker)
    if hist is None or hist.empty:
        stock.errors.append("No price history")
        return stock

    try:
        if info is None:
            for attempt in range(3):
                try:
                    info = yf.Ticker(ticker).info or {}
                    break
                except Exception as e:
                    if "Rate" in str(e) and attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    info = {}

        avg_volume_info = _safe_float(info.get("averageVolume"))
        fundamentals = _extract_fundamentals(info)
        technicals = _compute_technicals(hist, spy_hist, avg_volume_info)

        for key, val in {**fundamentals, **technicals}.items():
            if hasattr(stock, key):
                setattr(stock, key, val)
    except Exception as e:
        stock.errors.append(str(e))

    return stock


def fetch_stock(ticker: str, spy_hist: pd.DataFrame | None = None) -> StockData:
    """Fetch and enrich data for a single ticker."""
    stock = StockData(ticker=ticker)
    for attempt in range(3):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="1y")

            if hist.empty:
                stock.errors.append("No price history")
                return stock

            return fetch_stock_from_data(ticker, hist, spy_hist, info)

        except Exception as e:
            err = str(e)
            if "Rate limited" in err or "Too Many Requests" in err:
                time.sleep(2 ** attempt)
                continue
            stock.errors.append(err)
            logger.debug("Error fetching %s: %s", ticker, e)
            return stock

    stock.errors.append("Rate limited")
    return stock


def fetch_universe(
    tickers: list[str],
    workers: int = 4,
    progress_callback=None,
) -> dict[str, StockData]:
    """Fetch data for all tickers using batched price downloads."""
    for name in ("yfinance", "peewee"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    if not tickers:
        return {}

    # SPY benchmark
    spy_downloaded = _download_history(["SPY"])
    spy_hist = _history_for_ticker(spy_downloaded, "SPY", multi=False)

    results: dict[str, StockData] = {}
    chunk_size = 50
    done = 0

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        multi = len(chunk) > 1
        try:
            downloaded = _download_history(chunk)
        except Exception as e:
            logger.warning("Batch download failed for chunk: %s", e)
            downloaded = pd.DataFrame()

        # Fetch fundamentals in parallel (smaller worker pool)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for ticker in chunk:
                hist = _history_for_ticker(downloaded, ticker, multi)
                futures[executor.submit(fetch_stock_from_data, ticker, hist, spy_hist)] = ticker

            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    results[ticker] = future.result()
                except Exception as e:
                    results[ticker] = StockData(ticker=ticker, errors=[str(e)])
                done += 1
                if progress_callback:
                    progress_callback(done, len(tickers))

        if i + chunk_size < len(tickers):
            time.sleep(1)  # pause between batches to avoid rate limits

    return {
        ticker: stock
        for ticker, stock in results.items()
        if stock.price > 0 and not stock.errors
    }
