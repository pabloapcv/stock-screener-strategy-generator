"""Screener 3 — High-Quality Options Candidates."""

from __future__ import annotations

from src.data.fetcher import StockData
from src.data.options import analyze_options
from src.screeners.base import BaseScreener, ScreenerResult


class OptionsLiquidityScreener(BaseScreener):
    """
    Focus on execution quality — liquid option chains with tight spreads.
    Uses yfinance options data; verify in broker for final execution.
    """

    name = "High-Quality Options Candidates"
    description = "Execution-quality names with liquid option chains"

    def screen(self, stocks: dict[str, StockData]) -> ScreenerResult:
        f = self.config.get("filters", {})
        opts = self.config.get("options", {})

        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, dict] = {}

        for ticker, s in stocks.items():
            reasons_fail = []

            # Stock-level pre-filters (TradingView narrowing)
            if s.market_cap < f.get("market_cap_min", 5e9):
                reasons_fail.append("market_cap")
            if s.avg_volume < f.get("avg_volume_min", 2_000_000):
                reasons_fail.append("avg_volume")
            if s.price < f.get("price_min", 20.0):
                reasons_fail.append("price")
            if s.beta < f.get("beta_min", 1.0):
                reasons_fail.append("beta")
            if s.relative_volume < f.get("relative_volume_min", 1.0):
                reasons_fail.append("relative_volume")

            if reasons_fail:
                details[ticker] = {"failed": reasons_fail, "options": {}}
                failed.append(ticker)
                continue

            # Options analysis
            analyze_options(
                s,
                atm_oi_min=opts.get("atm_open_interest_min", 1000),
                daily_vol_min=opts.get("daily_option_volume_min", 500),
                spread_pct_max=opts.get("bid_ask_spread_pct_max", 0.05),
                require_weekly=opts.get("weekly_expirations", True),
            )

            if not s.options_pass:
                reasons_fail.append("options_liquidity")

            details[ticker] = {
                "price": s.price,
                "options_score": round(s.options_score, 2),
                "options": s.options_details,
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
