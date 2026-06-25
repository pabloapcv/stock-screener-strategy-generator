"""Options strategy constructors for trade ideas."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.data.options_chain import (
    OptionContract,
    OptionsChainSnapshot,
    _row_to_contract,
    find_strike,
)


@dataclass
class OptionLeg:
    action: str  # BUY or SELL
    option_type: str  # call or put
    strike: float
    expiration: str
    premium: float
    contracts: int = 1

    def describe(self) -> str:
        return f"{self.action} {self.contracts}x {self.option_type.upper()} ${self.strike:.0f} @ ${self.premium:.2f}"


@dataclass
class TradeIdea:
    ticker: str
    direction: str
    conviction: str
    setup: str
    strategy: str
    strategy_type: str  # debit, credit, stock
    stock_price: float
    stock_target: float
    stock_stop: float
    expiration: str
    dte: int
    legs: list[OptionLeg] = field(default_factory=list)
    max_profit: float | None = None
    max_loss: float | None = None
    breakeven: float | None = None
    risk_reward: str = ""
    iv_rank: float = 0.0
    rationale: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    composite_score: float = 0.0
    timeframe: str = "2-6 weeks"
    profit_report: object | None = None

    @property
    def net_debit(self) -> float:
        total = 0.0
        for leg in self.legs:
            sign = 1 if leg.action == "BUY" else -1
            total += sign * leg.premium * leg.contracts * 100
        return total


def _leg_from_contract(action: str, c: OptionContract, contracts: int = 1) -> OptionLeg:
    return OptionLeg(
        action=action,
        option_type=c.option_type,
        strike=c.strike,
        expiration=c.expiration,
        premium=c.mid,
        contracts=contracts,
    )


def long_call(snap: OptionsChainSnapshot, otm_pct: float = 0.02) -> TradeIdea | None:
    c = find_strike(snap.calls, snap.price, offset_pct=otm_pct)
    if not c or c.mid <= 0:
        return None
    target = snap.price * 1.08
    stop = snap.price * 0.97
    return TradeIdea(
        ticker=snap.ticker,
        direction="bullish",
        conviction="medium",
        setup="momentum",
        strategy="Long Call",
        strategy_type="debit",
        stock_price=snap.price,
        stock_target=target,
        stock_stop=stop,
        expiration=snap.selected_expiration,
        dte=snap.dte,
        legs=[_leg_from_contract("BUY", c)],
        max_loss=c.mid * 100,
        max_profit=None,
        breakeven=c.strike + c.mid,
        iv_rank=snap.iv_rank_proxy,
        rationale=["Directional bullish play with defined risk"],
    )


def bull_call_spread(snap: OptionsChainSnapshot) -> TradeIdea | None:
    long_c = find_strike(snap.calls, snap.price, offset_pct=0.0)
    short_c = find_strike(snap.calls, snap.price, offset_pct=0.05)
    if not long_c or not short_c or long_c.strike >= short_c.strike:
        return None
    if long_c.mid <= 0 or short_c.mid <= 0:
        return None
    debit = long_c.mid - short_c.mid
    if debit <= 0:
        return None
    width = short_c.strike - long_c.strike
    return TradeIdea(
        ticker=snap.ticker,
        direction="bullish",
        conviction="medium",
        setup="pullback",
        strategy="Bull Call Spread",
        strategy_type="debit",
        stock_price=snap.price,
        stock_target=short_c.strike,
        stock_stop=snap.price * 0.96,
        expiration=snap.selected_expiration,
        dte=snap.dte,
        legs=[
            _leg_from_contract("BUY", long_c),
            _leg_from_contract("SELL", short_c),
        ],
        max_loss=debit * 100,
        max_profit=(width - debit) * 100,
        breakeven=long_c.strike + debit,
        risk_reward=f"1:{(width - debit) / debit:.1f}" if debit > 0 else "",
        iv_rank=snap.iv_rank_proxy,
        rationale=["Defined-risk bullish spread — lower cost than naked call"],
    )


def bull_put_spread(snap: OptionsChainSnapshot) -> TradeIdea | None:
    short_p = find_strike(snap.puts, snap.price, offset_pct=-0.05, otm_only=True)
    long_p = find_strike(snap.puts, snap.price, offset_pct=-0.10, otm_only=True)
    if not short_p or not long_p or short_p.strike <= long_p.strike:
        return None
    credit = short_p.mid - long_p.mid
    if credit <= 0:
        return None
    width = short_p.strike - long_p.strike
    return TradeIdea(
        ticker=snap.ticker,
        direction="bullish",
        conviction="medium",
        setup="support",
        strategy="Bull Put Credit Spread",
        strategy_type="credit",
        stock_price=snap.price,
        stock_target=snap.price * 1.05,
        stock_stop=long_p.strike,
        expiration=snap.selected_expiration,
        dte=snap.dte,
        legs=[
            _leg_from_contract("SELL", short_p),
            _leg_from_contract("BUY", long_p),
        ],
        max_profit=credit * 100,
        max_loss=(width - credit) * 100,
        breakeven=short_p.strike - credit,
        risk_reward=f"{credit / (width - credit):.1f}:1" if width > credit else "",
        iv_rank=snap.iv_rank_proxy,
        rationale=["Collect premium on bullish thesis — benefits from elevated IV"],
    )


def cash_secured_put(snap: OptionsChainSnapshot) -> TradeIdea | None:
    p = find_strike(snap.puts, snap.price, offset_pct=-0.05, otm_only=True)
    if not p or p.mid <= 0:
        return None
    return TradeIdea(
        ticker=snap.ticker,
        direction="bullish",
        conviction="medium",
        setup="pullback",
        strategy="Cash-Secured Put",
        strategy_type="credit",
        stock_price=snap.price,
        stock_target=snap.price * 1.05,
        stock_stop=p.strike * 0.95,
        expiration=snap.selected_expiration,
        dte=snap.dte,
        legs=[_leg_from_contract("SELL", p)],
        max_profit=p.mid * 100,
        max_loss=(p.strike - p.mid) * 100,
        breakeven=p.strike - p.mid,
        iv_rank=snap.iv_rank_proxy,
        rationale=["Get paid to buy stock at support — ideal for pullback entries"],
    )


def stock_swing_trade(
    snap: OptionsChainSnapshot,
    direction: str,
    setup: str,
    target_pct: float,
    stop_pct: float,
) -> TradeIdea:
    sign = 1 if direction == "bullish" else -1
    return TradeIdea(
        ticker=snap.ticker,
        direction=direction,
        conviction="medium",
        setup=setup,
        strategy="Stock Swing Trade",
        strategy_type="stock",
        stock_price=snap.price,
        stock_target=snap.price * (1 + sign * target_pct),
        stock_stop=snap.price * (1 - sign * stop_pct),
        expiration="",
        dte=0,
        iv_rank=snap.iv_rank_proxy,
        rationale=["Options not liquid enough — stock-only alternative"],
        warnings=["Verify options liquidity in your broker before using options"],
    )


def weekly_momentum_call(snap: OptionsChainSnapshot, weekly_exp: str) -> TradeIdea | None:
    """ATM/slight OTM call for breakout momentum using weekly expiration."""
    dte = _dte(weekly_exp)
    try:
        import yfinance as yf
        chain = yf.Ticker(snap.ticker).option_chain(weekly_exp)
        calls = [_row_to_contract(r, weekly_exp, dte, "call") for _, r in chain.calls.iterrows()]
    except Exception:
        return None
    c = find_strike(calls, snap.price, offset_pct=0.01)
    if not c or c.mid <= 0:
        return None
    return TradeIdea(
        ticker=snap.ticker,
        direction="bullish",
        conviction="high",
        setup="breakout",
        strategy="Weekly Long Call (Momentum)",
        strategy_type="debit",
        stock_price=snap.price,
        stock_target=snap.price * 1.05,
        stock_stop=snap.price * 0.98,
        expiration=weekly_exp,
        dte=dte,
        legs=[_leg_from_contract("BUY", c)],
        max_loss=c.mid * 100,
        breakeven=c.strike + c.mid,
        iv_rank=snap.iv_rank_proxy,
        timeframe="1-2 weeks",
        rationale=["Breakout momentum — weekly expiration for fast-moving setup"],
    )


def _dte(exp: str) -> int:
    from datetime import datetime
    try:
        return max((datetime.strptime(exp, "%Y-%m-%d").date() - datetime.now().date()).days, 0)
    except ValueError:
        return 0
