"""Profit/loss calculator for trade ideas."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ideas.strategies import TradeIdea

CONTRACT_SIZES = (1, 3, 5)
STOCK_SHARE_SIZES = (10, 30, 50)  # practical share lots for stock trades


@dataclass
class ScenarioPnL:
    size: int
    unit: str  # "contracts" or "shares"
    capital_required: float
    pnl_at_target: float
    pnl_at_stop: float
    max_profit: float | None
    max_loss: float | None
    return_at_target_pct: float
    return_at_risk_pct: float  # pnl_at_target / max_loss


@dataclass
class ProfitReport:
    profit_at_target: float  # per 1 contract / 100 shares
    profit_at_stop: float
    above_breakeven_at_target: bool
    scenarios: list[ScenarioPnL] = field(default_factory=list)
    note: str = ""


def _leg_value_at_price(leg, stock_price: float) -> float:
    """Position value at expiry for one leg (per 1 contract)."""
    if leg.option_type == "call":
        intrinsic = max(0.0, stock_price - leg.strike)
    else:
        intrinsic = max(0.0, leg.strike - stock_price)
    sign = 1.0 if leg.action == "BUY" else -1.0
    return sign * intrinsic * 100


def _position_value_at_price(idea: TradeIdea, stock_price: float) -> float:
    if not idea.legs:
        return 0.0
    return sum(_leg_value_at_price(leg, stock_price) for leg in idea.legs)


def pnl_at_price(idea: TradeIdea, stock_price: float, size: int = 1) -> float:
    """P&L at expiry for a given stock price and position size."""
    if idea.strategy_type == "stock":
        # For stock, size IS the share count
        return (stock_price - idea.stock_price) * size

    multiplier = size
    exit_value = _position_value_at_price(idea, stock_price) * multiplier
    entry_cost = idea.net_debit * multiplier
    return exit_value - entry_cost


def _capital_required(idea: TradeIdea, size: int) -> float:
    if idea.strategy_type == "stock":
        return idea.stock_price * size
    if idea.strategy_type == "credit":
        # Margin approx = max loss for spreads
        return (idea.max_loss or abs(idea.net_debit)) * size
    return abs(idea.net_debit) * size


def compute_profit_report(idea: TradeIdea) -> ProfitReport:
    """Build full P&L report with 1/3/5 contract scenarios."""
    sizes = STOCK_SHARE_SIZES if idea.strategy_type == "stock" else CONTRACT_SIZES
    unit = "shares" if idea.strategy_type == "stock" else "contracts"

    per_unit = 1
    profit_target = pnl_at_price(idea, idea.stock_target, per_unit)
    profit_stop = pnl_at_price(idea, idea.stock_stop, per_unit)

    above_be = True
    if idea.breakeven is not None and idea.direction == "bullish":
        above_be = idea.stock_target >= idea.breakeven
    elif idea.breakeven is not None and idea.direction == "bearish":
        above_be = idea.stock_target <= idea.breakeven

    note = ""
    if idea.strategy_type == "debit" and profit_target < 0:
        note = (
            f"Stock target (${idea.stock_target:.2f}) is below options breakeven "
            f"(${idea.breakeven:.2f}) — need a larger move to profit"
        )

    scenarios: list[ScenarioPnL] = []
    for size in sizes:
        pt = pnl_at_price(idea, idea.stock_target, size)
        ps = pnl_at_price(idea, idea.stock_stop, size)
        capital = _capital_required(idea, size)
        max_profit = idea.max_profit * size if idea.max_profit else None
        max_loss = idea.max_loss * size if idea.max_loss else None

        if idea.strategy_type == "stock":
            max_profit = None  # uncapped
            max_loss = abs(ps) if ps < 0 else (idea.stock_price - idea.stock_stop) * size

        ret_target = (pt / capital * 100) if capital > 0 else 0.0
        ret_risk = (pt / max_loss * 100) if max_loss and max_loss > 0 else 0.0

        scenarios.append(ScenarioPnL(
            size=size,
            unit=unit,
            capital_required=capital,
            pnl_at_target=pt,
            pnl_at_stop=ps,
            max_profit=max_profit,
            max_loss=max_loss,
            return_at_target_pct=ret_target,
            return_at_risk_pct=ret_risk,
        ))

    per_unit_target = profit_target
    per_unit_stop = profit_stop

    return ProfitReport(
        profit_at_target=per_unit_target,
        profit_at_stop=per_unit_stop,
        above_breakeven_at_target=above_be,
        scenarios=scenarios,
        note=note,
    )


def enrich_idea_with_pnl(idea: TradeIdea) -> TradeIdea:
    """Attach profit report to idea."""
    idea.profit_report = compute_profit_report(idea)
    return idea
