"""Options chain analysis for liquidity screening."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import yfinance as yf

from src.data.fetcher import StockData

logger = logging.getLogger(__name__)


def _has_weekly_expirations(expirations: list[str]) -> bool:
    """Check if there are expirations within the next 7-14 days."""
    if not expirations:
        return False
    today = datetime.now().date()
    for exp_str in expirations[:6]:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days_out = (exp_date - today).days
            if 0 < days_out <= 14:
                return True
        except ValueError:
            continue
    return False


def _find_atm_strike(strikes: list[float], price: float) -> float | None:
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - price))


def analyze_options(
    stock: StockData,
    atm_oi_min: int = 1000,
    daily_vol_min: int = 500,
    spread_pct_max: float = 0.05,
    require_weekly: bool = True,
) -> StockData:
    """Enrich stock with options liquidity metrics."""
    details: dict[str, Any] = {}
    score_components: list[float] = []

    try:
        t = yf.Ticker(stock.ticker)
        expirations = list(t.options)
        details["expirations_count"] = len(expirations)
        details["has_weekly"] = _has_weekly_expirations(expirations)

        if require_weekly and not details["has_weekly"]:
            stock.options_details = details
            stock.options_pass = False
            stock.options_score = 0.0
            return stock

        if not expirations:
            stock.options_details = details
            return stock

        # Use nearest expiration
        chain = t.option_chain(expirations[0])
        calls = chain.calls
        puts = chain.puts

        atm_strike = _find_atm_strike(calls["strike"].tolist(), stock.price)
        if atm_strike is None:
            stock.options_details = details
            return stock

        atm_call = calls[calls["strike"] == atm_strike]
        atm_put = puts[puts["strike"] == atm_strike]

        call_oi = int(atm_call["openInterest"].sum()) if not atm_call.empty else 0
        put_oi = int(atm_put["openInterest"].sum()) if not atm_put.empty else 0
        atm_oi = call_oi + put_oi
        details["atm_strike"] = atm_strike
        details["atm_open_interest"] = atm_oi

        call_vol = int(atm_call["volume"].sum()) if not atm_call.empty else 0
        put_vol = int(atm_put["volume"].sum()) if not atm_put.empty else 0
        total_vol = call_vol + put_vol
        details["atm_volume"] = total_vol

        # Bid/ask spread
        spreads = []
        for df in (atm_call, atm_put):
            if df.empty:
                continue
            for _, row in df.iterrows():
                bid = row.get("bid", 0) or 0
                ask = row.get("ask", 0) or 0
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                    spreads.append((ask - bid) / mid if mid > 0 else 1.0)
        avg_spread = float(np.mean(spreads)) if spreads else 1.0
        details["avg_bid_ask_spread_pct"] = avg_spread

        # IV rank proxy from implied volatility
        ivs = []
        for df in (calls, puts):
            if "impliedVolatility" in df.columns:
                ivs.extend(df["impliedVolatility"].dropna().tolist())
        if ivs:
            current_iv = float(np.median(ivs))
            details["implied_volatility"] = current_iv
            # Rough IV rank proxy (without historical IV data)
            details["iv_rank_proxy"] = min(current_iv / 0.5, 1.0) * 100

        # Score components (0-1 each)
        score_components.append(min(atm_oi / atm_oi_min, 1.0) if atm_oi >= atm_oi_min else atm_oi / atm_oi_min)
        score_components.append(min(total_vol / daily_vol_min, 1.0) if total_vol >= daily_vol_min else total_vol / daily_vol_min)
        score_components.append(1.0 if avg_spread <= spread_pct_max else max(0, 1 - avg_spread))
        score_components.append(1.0 if details.get("has_weekly") else 0.5)

        stock.options_score = float(np.mean(score_components)) if score_components else 0.0
        stock.options_pass = (
            atm_oi >= atm_oi_min
            and total_vol >= daily_vol_min
            and avg_spread <= spread_pct_max
            and (not require_weekly or details.get("has_weekly"))
        )

    except Exception as e:
        logger.debug("Options analysis failed for %s: %s", stock.ticker, e)
        details["error"] = str(e)

    stock.options_details = details
    return stock


def analyze_options_batch(
    stocks: dict[str, StockData],
    config: dict,
    workers: int = 4,
) -> dict[str, StockData]:
    """Run options analysis on a batch of stocks."""
    opts = config.get("options", {})
    for ticker, stock in stocks.items():
        analyze_options(
            stock,
            atm_oi_min=opts.get("atm_open_interest_min", 1000),
            daily_vol_min=opts.get("daily_option_volume_min", 500),
            spread_pct_max=opts.get("bid_ask_spread_pct_max", 0.05),
            require_weekly=opts.get("weekly_expirations", True),
        )
    return stocks
