"""Screener 2 — Analyst Upgrade Momentum."""

from __future__ import annotations

from src.data.fetcher import StockData
from src.screeners.base import BaseScreener, ScreenerResult

# External verification URLs for manual review
EXTERNAL_SOURCES = {
    "analyst_upgrades_30d": "https://www.marketbeat.com/ratings/",
    "eps_estimate_revisions": "https://finviz.com/quote.ashx?t={ticker}",
    "price_target_increases": "https://www.tipranks.com/stocks/{ticker}/forecast",
    "insider_buying": "https://openinsider.com/search?q={ticker}",
    "earnings_revisions": "https://www.zacks.com/stock/quote/{ticker}/detailed-earning-estimates",
}


class AnalystMomentumScreener(BaseScreener):
    """
    Identify names attracting analyst attention.
    TradingView-style filters + flags for external verification.
    """

    name = "Analyst Upgrade Momentum"
    description = "Names attracting analyst attention with upgrade momentum"

    def screen(self, stocks: dict[str, StockData]) -> ScreenerResult:
        f = self.config.get("filters", {})
        external_checks = self.config.get("external_checks", [])

        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, dict] = {}

        for ticker, s in stocks.items():
            reasons_fail = []

            if not self._passes_threshold(s.analyst_rating, f.get("analyst_rating_min", 4.0)):
                reasons_fail.append("analyst_rating")
            if s.relative_volume < f.get("relative_volume_min", 1.5):
                reasons_fail.append("relative_volume")
            if not self._passes_threshold(s.performance_1w, f.get("performance_1w_min", 0.03)):
                reasons_fail.append("performance_1w")
            if not self._passes_threshold(s.performance_1m, f.get("performance_1m_min", 0.08)):
                reasons_fail.append("performance_1m")
            if not self._passes_threshold(s.revenue_growth, f.get("revenue_growth_min", 0.20)):
                reasons_fail.append("revenue_growth")
            if not self._passes_threshold(s.eps_growth, f.get("eps_growth_min", 0.20)):
                reasons_fail.append("eps_growth")

            # Momentum bonus: EPS revision trend positive
            momentum_score = 0
            if s.eps_revision_trend and s.eps_revision_trend > 0:
                momentum_score += 1
            if s.breakout_from_consolidation:
                momentum_score += 1

            external_urls = {
                check: EXTERNAL_SOURCES.get(check, "").format(ticker=ticker)
                for check in external_checks
                if check in EXTERNAL_SOURCES
            }

            details[ticker] = {
                "price": s.price,
                "performance_1w": s.performance_1w,
                "performance_1m": s.performance_1m,
                "eps_revision_trend": s.eps_revision_trend,
                "momentum_score": momentum_score,
                "breakout": s.breakout_from_consolidation,
                "external_urls": external_urls,
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
            external_checks=external_checks,
        )
