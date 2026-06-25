"""Paper trading engine — open, close, and manage positions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.config import load_config
from src.ideas.generator import generate_idea
from src.ideas.strategies import TradeIdea
from src.paper.models import PaperLeg, PaperPortfolio, PaperPosition
from src.paper.mtm import fetch_stock_price, unrealized_pnl
from src.paper.store import load_portfolio, save_portfolio


class PaperTradingError(Exception):
    pass


def _position_max_loss(position: PaperPosition, idea: TradeIdea | None = None) -> float:
    if position.strategy_type == "stock":
        return max(0.0, (position.entry_stock_price - position.stock_stop) * position.size)
    if idea and idea.max_loss:
        return idea.max_loss * position.size
    return abs(position.entry_cost)


def _cash_to_open(position: PaperPosition, idea: TradeIdea) -> float:
    if position.strategy_type == "stock":
        return position.entry_stock_price * position.size
    if position.strategy_type == "credit":
        return _position_max_loss(position, idea)
    return abs(position.entry_cost)


def _cash_on_close(position: PaperPosition, pnl: float) -> float:
    if position.strategy_type == "stock":
        return position.exit_stock_price * position.size  # type: ignore
    if position.strategy_type == "credit":
        return _position_max_loss(position) + pnl
    return abs(position.entry_cost) + pnl


def _idea_to_position(idea: TradeIdea, size: int) -> PaperPosition:
    unit = "shares" if idea.strategy_type == "stock" else "contracts"
    entry_cost = idea.net_debit * size

    legs = [
        PaperLeg(
            action=leg.action,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            entry_premium=leg.premium,
            contracts=leg.contracts,
        )
        for leg in idea.legs
    ]

    return PaperPosition(
        id=PaperPosition.new_id(),
        ticker=idea.ticker,
        strategy=idea.strategy,
        strategy_type=idea.strategy_type,
        direction=idea.direction,
        setup=idea.setup,
        conviction=idea.conviction,
        size=size,
        size_unit=unit,
        opened_at=datetime.now().isoformat(),
        entry_stock_price=idea.stock_price,
        entry_cost=entry_cost,
        stock_target=idea.stock_target,
        stock_stop=idea.stock_stop,
        expiration=idea.expiration,
        dte_at_entry=idea.dte,
        legs=legs,
    )


def generate_idea_from_ticker(ticker: str) -> TradeIdea | None:
    from src.data.fetcher import fetch_universe
    stocks = fetch_universe([ticker.upper()])
    if ticker.upper() not in stocks:
        return None
    return generate_idea(stocks[ticker.upper()], force=True)


def open_position(
    ticker: str,
    contracts: int | None = None,
    shares: int | None = None,
) -> tuple[PaperPosition, TradeIdea]:
    """Open a paper trade from a freshly generated idea."""
    config = load_config()
    pt_cfg = config.get("paper_trading", {})

    idea = generate_idea_from_ticker(ticker)
    if idea is None:
        raise PaperTradingError(f"No trade idea could be generated for {ticker}")

    if idea.strategy_type == "stock":
        size = shares or pt_cfg.get("default_shares", 10)
    else:
        size = contracts or pt_cfg.get("default_contracts", 1)

    position = _idea_to_position(idea, size)
    portfolio = load_portfolio()

    if any(p.ticker == ticker.upper() and p.status == "open" for p in portfolio.positions):
        raise PaperTradingError(f"Already have an open paper trade for {ticker.upper()}")

    cash_needed = _cash_to_open(position, idea)
    max_pos_pct = pt_cfg.get("max_position_pct", 0.10)
    max_allowed = portfolio.starting_capital * max_pos_pct
    if cash_needed > max_allowed:
        raise PaperTradingError(
            f"Position requires ${cash_needed:,.0f} — exceeds "
            f"{max_pos_pct:.0%} limit (${max_allowed:,.0f})"
        )
    if cash_needed > portfolio.cash:
        raise PaperTradingError(
            f"Insufficient cash: need ${cash_needed:,.0f}, have ${portfolio.cash:,.0f}"
        )

    portfolio.cash -= cash_needed
    portfolio.positions.append(position)
    save_portfolio(portfolio)
    return position, idea


def open_from_ideas_file(
    path: Path | None = None,
    contracts: int | None = None,
    shares: int | None = None,
    max_trades: int | None = None,
) -> list[tuple[PaperPosition, TradeIdea]]:
    """Open paper trades from a saved ideas JSON file."""
    if path is None:
        output_dir = Path(__file__).resolve().parents[2] / "output"
        files = sorted(output_dir.glob("ideas_*.json"), reverse=True)
        if not files:
            raise PaperTradingError("No ideas files found in output/")
        path = files[0]

    with open(path) as f:
        data = json.load(f)

    opened: list[tuple[PaperPosition, TradeIdea]] = []
    limit = max_trades or len(data.get("ideas", []))

    for item in data.get("ideas", [])[:limit]:
        ticker = item["ticker"]
        try:
            opened.append(open_position(ticker, contracts=contracts, shares=shares))
        except PaperTradingError as e:
            if "Already have" not in str(e) and "Insufficient" not in str(e):
                raise
    return opened


def close_position(
    position_id: str | None = None,
    ticker: str | None = None,
    reason: str = "manual",
) -> PaperPosition:
    """Close an open paper position at current market marks."""
    portfolio = load_portfolio()
    position = _find_open_position(portfolio, position_id, ticker)
    if not position:
        raise PaperTradingError("No open position found")

    stock_price = fetch_stock_price(position.ticker)
    if stock_price is None:
        raise PaperTradingError(f"Could not fetch price for {position.ticker}")

    pnl = unrealized_pnl(position, stock_price)

    position.status = "closed"
    position.closed_at = datetime.now().isoformat()
    position.exit_stock_price = stock_price
    position.realized_pnl = pnl
    position.close_reason = reason

    portfolio.cash += _cash_on_close(position, pnl)
    save_portfolio(portfolio)
    return position


def check_stops_and_targets() -> list[PaperPosition]:
    """Auto-close positions that hit stop or target."""
    portfolio = load_portfolio()
    closed: list[PaperPosition] = []

    for position in list(portfolio.open_positions):
        price = fetch_stock_price(position.ticker)
        if price is None:
            continue

        if position.direction == "bullish":
            if price >= position.stock_target:
                closed.append(close_position(position_id=position.id, reason="target"))
            elif price <= position.stock_stop:
                closed.append(close_position(position_id=position.id, reason="stop"))

    return closed


def _find_open_position(
    portfolio: PaperPortfolio,
    position_id: str | None,
    ticker: str | None,
) -> PaperPosition | None:
    for p in portfolio.open_positions:
        if position_id and p.id == position_id:
            return p
        if ticker and p.ticker.upper() == ticker.upper():
            return p
    return None


def get_portfolio_summary() -> dict:
    """Return portfolio with live marks for all open positions."""
    check_stops_and_targets()
    portfolio = load_portfolio()

    open_marks = []
    total_unrealized = 0.0

    for pos in portfolio.open_positions:
        price = fetch_stock_price(pos.ticker)
        if price is None:
            continue
        upnl = unrealized_pnl(pos, price)
        total_unrealized += upnl
        open_marks.append({
            "position": pos,
            "current_price": price,
            "unrealized_pnl": upnl,
            "pct_change": (price - pos.entry_stock_price) / pos.entry_stock_price * 100,
        })

    total_realized = sum(p.realized_pnl or 0 for p in portfolio.closed_positions)
    equity = portfolio.starting_capital + total_realized + total_unrealized
    return_pct = (equity - portfolio.starting_capital) / portfolio.starting_capital * 100

    return {
        "portfolio": portfolio,
        "open_marks": open_marks,
        "total_unrealized": total_unrealized,
        "total_realized": total_realized,
        "equity": equity,
        "return_pct": return_pct,
    }
