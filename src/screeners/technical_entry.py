"""Screener 4 — Technical Entry Setup."""

from __future__ import annotations

from src.data.fetcher import StockData
from src.screeners.base import BaseScreener, ScreenerResult


class TechnicalEntryScreener(BaseScreener):
    """
    Final stage: identify high-conviction entry setups.
    Looks for pullbacks, breakouts, relative strength, volume confirmation.
    """

    name = "Technical Entry Setup"
    description = "High-conviction entry setups from narrowed universe"

    def screen(self, stocks: dict[str, StockData]) -> ScreenerResult:
        signals = self.config.get("signals", [
            "pullback_to_sma_20",
            "pullback_to_sma_50",
            "breakout_from_consolidation",
            "relative_strength_vs_spy",
            "volume_confirmation",
        ])

        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, dict] = {}

        signal_map = {
            "pullback_to_sma_20": lambda s: s.pullback_to_sma_20,
            "pullback_to_sma_50": lambda s: s.pullback_to_sma_50,
            "breakout_from_consolidation": lambda s: s.breakout_from_consolidation,
            "relative_strength_vs_spy": lambda s: s.relative_strength_vs_spy,
            "volume_confirmation": lambda s: s.volume_confirmation,
        }

        for ticker, s in stocks.items():
            active_signals = []
            for sig in signals:
                checker = signal_map.get(sig)
                if checker and checker(s):
                    active_signals.append(sig)

            entry_score = len(active_signals)
            # Require at least 2 confirming signals
            qualifies = entry_score >= 2

            details[ticker] = {
                "price": s.price,
                "sma_20": s.sma_20,
                "sma_50": s.sma_50,
                "rsi": s.rsi,
                "active_signals": active_signals,
                "entry_score": entry_score,
            }

            if qualifies:
                passed.append(ticker)
            else:
                failed.append(ticker)

        # Sort by entry score descending
        passed.sort(key=lambda t: details[t]["entry_score"], reverse=True)

        return ScreenerResult(
            name=self.name,
            description=self.description,
            passed=passed,
            failed=failed,
            details=details,
        )
