"""Weighted composite scoring model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.data.fetcher import StockData


@dataclass
class ScoredStock:
    ticker: str
    composite_score: float
    components: dict[str, float]
    rank: int = 0


def _normalize(value: float | None, low: float, high: float) -> float:
    """Clamp and normalize a value to 0-1 range."""
    if value is None:
        return 0.0
    if high == low:
        return 1.0 if value >= low else 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def score_stock(stock: StockData, weights: dict[str, float]) -> ScoredStock:
    """
    Compute weighted composite score:
      25% Analyst Rating
      20% EPS Revision Trend
      20% Revenue Growth
      15% Technical Momentum
      10% Relative Volume
      10% Options Liquidity
    """
    components: dict[str, float] = {}

    components["analyst_rating"] = _normalize(stock.analyst_rating, 3.0, 5.0)
    components["eps_revision_trend"] = _normalize(stock.eps_revision_trend, 0.0, 0.30)
    components["revenue_growth"] = _normalize(stock.revenue_growth, 0.10, 0.50)

    # Technical momentum: blend of performance + trend alignment
    perf_1m = _normalize(stock.performance_1m, 0.0, 0.20)
    trend = 0.0
    if stock.price_above_sma_50:
        trend += 0.33
    if stock.price_above_sma_200:
        trend += 0.33
    if stock.sma_50_above_sma_200:
        trend += 0.34
    components["technical_momentum"] = 0.6 * perf_1m + 0.4 * trend

    components["relative_volume"] = _normalize(stock.relative_volume, 1.0, 3.0)
    components["options_liquidity"] = stock.options_score

    composite = sum(
        components.get(key, 0.0) * weight
        for key, weight in weights.items()
    )

    return ScoredStock(
        ticker=stock.ticker,
        composite_score=round(composite * 100, 2),
        components={k: round(v * 100, 1) for k, v in components.items()},
    )


def rank_stocks(
    stocks: dict[str, StockData],
    weights: dict[str, float],
    top_n: int = 20,
) -> list[ScoredStock]:
    """Score and rank all stocks, return top N."""
    scored = [score_stock(s, weights) for s in stocks.values()]
    scored.sort(key=lambda x: x.composite_score, reverse=True)
    for i, s in enumerate(scored[:top_n]):
        s.rank = i + 1
    return scored[:top_n]
