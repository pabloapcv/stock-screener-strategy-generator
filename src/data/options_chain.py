"""Detailed options chain data for trade idea generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class OptionContract:
    symbol: str
    strike: float
    expiration: str
    dte: int
    option_type: str  # call or put
    bid: float
    ask: float
    mid: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool

    @property
    def spread_pct(self) -> float:
        if self.mid <= 0:
            return 1.0
        return (self.ask - self.bid) / self.mid


@dataclass
class OptionsChainSnapshot:
    ticker: str
    price: float
    expirations: list[str] = field(default_factory=list)
    selected_expiration: str = ""
    dte: int = 0
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)
    atm_strike: float = 0.0
    atm_call: OptionContract | None = None
    atm_put: OptionContract | None = None
    iv_rank_proxy: float = 0.0
    has_weekly: bool = False
    error: str = ""


def _days_to_expiry(exp_str: str) -> int:
    try:
        exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
        return max((exp - datetime.now().date()).days, 0)
    except ValueError:
        return 0


def _pick_expiration(expirations: list[str], target_dte: int = 21, min_dte: int = 7) -> str | None:
    """Pick expiration closest to target DTE with at least min_dte days out."""
    if not expirations:
        return None
    candidates = [
        (exp, _days_to_expiry(exp))
        for exp in expirations
        if _days_to_expiry(exp) >= min_dte
    ]
    if not candidates:
        return expirations[0]
    return min(candidates, key=lambda x: abs(x[1] - target_dte))[0]


def _row_to_contract(row: pd.Series, exp: str, dte: int, opt_type: str) -> OptionContract:
    bid = float(row.get("bid") or 0)
    ask = float(row.get("ask") or 0)
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else float(row.get("lastPrice") or 0)
    return OptionContract(
        symbol=str(row.get("contractSymbol", "")),
        strike=float(row["strike"]),
        expiration=exp,
        dte=dte,
        option_type=opt_type,
        bid=bid,
        ask=ask,
        mid=mid,
        last=float(row.get("lastPrice") or 0),
        volume=int(row.get("volume") or 0),
        open_interest=int(row.get("openInterest") or 0),
        implied_volatility=float(row.get("impliedVolatility") or 0),
        in_the_money=bool(row.get("inTheMoney", False)),
    )


def fetch_options_chain(
    ticker: str,
    price: float,
    target_dte: int = 21,
    min_dte: int = 7,
) -> OptionsChainSnapshot:
    """Fetch full options chain snapshot for trade construction."""
    snap = OptionsChainSnapshot(ticker=ticker, price=price)
    try:
        t = yf.Ticker(ticker)
        expirations = list(t.options)
        snap.expirations = expirations

        today = datetime.now().date()
        snap.has_weekly = any(
            0 < (datetime.strptime(e, "%Y-%m-%d").date() - today).days <= 14
            for e in expirations[:8]
            if _days_to_expiry(e) > 0
        )

        exp = _pick_expiration(expirations, target_dte, min_dte)
        if not exp:
            snap.error = "No expirations available"
            return snap

        snap.selected_expiration = exp
        snap.dte = _days_to_expiry(exp)

        chain = t.option_chain(exp)
        snap.calls = [_row_to_contract(r, exp, snap.dte, "call") for _, r in chain.calls.iterrows()]
        snap.puts = [_row_to_contract(r, exp, snap.dte, "put") for _, r in chain.puts.iterrows()]

        if snap.calls:
            snap.atm_strike = min(snap.calls, key=lambda c: abs(c.strike - price)).strike
            snap.atm_call = next((c for c in snap.calls if c.strike == snap.atm_strike), None)
            snap.atm_put = next((p for p in snap.puts if p.strike == snap.atm_strike), None)

        ivs = [c.implied_volatility for c in snap.calls + snap.puts if c.implied_volatility > 0]
        if ivs:
            snap.iv_rank_proxy = min(float(np.median(ivs)) / 0.5, 1.0) * 100

    except Exception as e:
        snap.error = str(e)
        logger.debug("Chain fetch failed for %s: %s", ticker, e)

    return snap


def find_strike(
    contracts: list[OptionContract],
    reference: float,
    offset_pct: float = 0.0,
    otm_only: bool = True,
) -> OptionContract | None:
    """Find contract closest to reference price with optional % offset."""
    if not contracts:
        return None
    target = reference * (1 + offset_pct)
    pool = [c for c in contracts if c.open_interest > 0 or c.volume > 0]
    if not pool:
        pool = contracts
    if otm_only and offset_pct >= 0:
        pool = [c for c in pool if c.strike >= reference] or pool
    elif otm_only and offset_pct < 0:
        pool = [c for c in pool if c.strike <= reference] or pool
    return min(pool, key=lambda c: abs(c.strike - target))


def find_strike_by_delta_proxy(
    contracts: list[OptionContract],
    price: float,
    delta_target: float = 0.30,
) -> OptionContract | None:
    """Approximate 30-delta strike using % OTM (rough proxy without greeks)."""
    # ~30 delta call ≈ 5-8% OTM for 21-45 DTE; scale by DTE
    otm_pct = 0.05 + delta_target * 0.05
    return find_strike(contracts, price, offset_pct=otm_pct)


def liquidity_ok(contract: OptionContract | None, min_oi: int = 50) -> bool:
    if contract is None:
        return False
    return contract.open_interest >= min_oi or contract.volume >= 10
