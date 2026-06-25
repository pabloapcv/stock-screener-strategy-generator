"""Persist paper trading portfolio to disk."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.config import load_config
from src.paper.models import PaperPortfolio

PORTFOLIO_DIR = Path(__file__).resolve().parents[2] / "paper"
PORTFOLIO_FILE = PORTFOLIO_DIR / "portfolio.json"


def _default_portfolio() -> PaperPortfolio:
    config = load_config()
    capital = config.get("paper_trading", {}).get("starting_capital", 100_000.0)
    return PaperPortfolio(starting_capital=capital, cash=capital)


def load_portfolio() -> PaperPortfolio:
    if not PORTFOLIO_FILE.exists():
        return _default_portfolio()
    with open(PORTFOLIO_FILE) as f:
        return PaperPortfolio.from_dict(json.load(f))


def save_portfolio(portfolio: PaperPortfolio) -> None:
    PORTFOLIO_DIR.mkdir(exist_ok=True)
    portfolio.updated_at = datetime.now().isoformat()
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio.to_dict(), f, indent=2)


def reset_portfolio() -> PaperPortfolio:
    portfolio = _default_portfolio()
    save_portfolio(portfolio)
    return portfolio
