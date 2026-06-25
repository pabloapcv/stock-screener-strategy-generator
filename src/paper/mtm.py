"""Mark-to-market pricing for paper positions."""

from __future__ import annotations

import logging

import yfinance as yf

from src.paper.models import PaperLeg, PaperPosition

logger = logging.getLogger(__name__)


def _option_mid(ticker: str, leg: PaperLeg) -> float | None:
    try:
        chain = yf.Ticker(ticker).option_chain(leg.expiration)
        df = chain.calls if leg.option_type == "call" else chain.puts
        row = df[df["strike"] == leg.strike]
        if row.empty:
            return None
        bid = float(row.iloc[0].get("bid") or 0)
        ask = float(row.iloc[0].get("ask") or 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return float(row.iloc[0].get("lastPrice") or leg.entry_premium)
    except Exception as e:
        logger.debug("Option mark failed %s %s: %s", ticker, leg.strike, e)
        return None


def _leg_mark_value(leg: PaperLeg, mid: float, size_multiplier: int) -> float:
    sign = 1.0 if leg.action == "BUY" else -1.0
    return sign * mid * 100 * leg.contracts * size_multiplier


def position_market_value(position: PaperPosition, stock_price: float) -> float:
    """Current market value of the position (not P&L)."""
    if position.strategy_type == "stock":
        return stock_price * position.size

    multiplier = position.size
    total = 0.0
    for leg in position.legs:
        mid = _option_mid(position.ticker, leg)
        if mid is None:
            # Fallback to intrinsic at expiry-style mark
            if leg.option_type == "call":
                mid = max(0.0, stock_price - leg.strike)
            else:
                mid = max(0.0, leg.strike - stock_price)
        else:
            mid = max(mid, 0.0)
        total += _leg_mark_value(leg, mid, multiplier)
    return total


def unrealized_pnl(position: PaperPosition, stock_price: float) -> float:
    """Unrealized P&L based on current marks."""
    if position.strategy_type == "stock":
        return (stock_price - position.entry_stock_price) * position.size

    current_value = position_market_value(position, stock_price)
    # entry_cost: positive = debit paid, negative = credit received
    return current_value - position.entry_cost


def fetch_stock_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.get("lastPrice") or t.info.get("regularMarketPrice")
        if price:
            return float(price)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.debug("Price fetch failed for %s: %s", ticker, e)
    return None
