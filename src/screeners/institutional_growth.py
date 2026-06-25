"""Screener 1 — Institutional Growth Leaders."""

from __future__ import annotations

from src.data.fetcher import StockData
from src.screeners.base import BaseScreener, ScreenerResult


class InstitutionalGrowthScreener(BaseScreener):
    """
    Find companies institutions accumulate for medium-term swing trades.
    Mirrors TradingView filters: Strong Buy, $5B+ cap, 20% growth, ROE 15%,
  technical trend alignment, RSI 50-70, near 52-week highs.
    """

    name = "Institutional Growth Leaders"
    description = "Companies institutions accumulate for medium-term swing trades"

    def screen(self, stocks: dict[str, StockData]) -> ScreenerResult:
        f = self.config.get("filters", {})
        t = self.config.get("technicals", {})

        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, dict] = {}

        for ticker, s in stocks.items():
            reasons_fail = []

            if not self._passes_threshold(s.analyst_rating, f.get("analyst_rating_min", 4.0)):
                reasons_fail.append("analyst_rating")
            if s.market_cap < f.get("market_cap_min", 5e9):
                reasons_fail.append("market_cap")
            if not self._passes_threshold(s.revenue_growth, f.get("revenue_growth_min", 0.20)):
                reasons_fail.append("revenue_growth")
            if not self._passes_threshold(s.eps_growth, f.get("eps_growth_min", 0.20)):
                reasons_fail.append("eps_growth")
            if not self._passes_threshold(s.roe, f.get("roe_min", 0.15)):
                reasons_fail.append("roe")
            if s.relative_volume + 0.005 < f.get("relative_volume_min", 1.2):
                reasons_fail.append("relative_volume")
            if s.avg_volume < f.get("avg_volume_min", 2_000_000):
                reasons_fail.append("avg_volume")
            if s.price < f.get("price_min", 20.0):
                reasons_fail.append("price")
            if not self._in_range(s.beta, f.get("beta_min", 1.0), f.get("beta_max", 2.5)):
                reasons_fail.append("beta")

            # Technicals
            if t.get("price_above_sma_50") and not s.price_above_sma_50:
                reasons_fail.append("price_above_sma_50")
            if t.get("price_above_sma_200") and not s.price_above_sma_200:
                reasons_fail.append("price_above_sma_200")
            if t.get("sma_50_above_sma_200") and not s.sma_50_above_sma_200:
                reasons_fail.append("sma_50_above_sma_200")
            if not self._in_range(s.rsi, t.get("rsi_min", 50), t.get("rsi_max", 70)):
                reasons_fail.append("rsi")
            max_dist = t.get("within_pct_of_52w_high", 0.10)
            if s.pct_from_52w_high is not None and s.pct_from_52w_high > max_dist:
                reasons_fail.append("near_52w_high")

            details[ticker] = {
                "price": s.price,
                "market_cap_b": round(s.market_cap / 1e9, 1),
                "revenue_growth": s.revenue_growth,
                "eps_growth": s.eps_growth,
                "roe": s.roe,
                "rsi": s.rsi,
                "relative_volume": round(s.relative_volume, 2),
                "failed": reasons_fail,
            }

            if not reasons_fail:
                passed.append(ticker)
            else:
                failed.append(ticker)

        return ScreenerResult(
            name=self.name,
            description=self.description,
            passed=passed,
            failed=failed,
            details=details,
        )
