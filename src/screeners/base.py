"""Base screener interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.data.fetcher import StockData


@dataclass
class ScreenerResult:
    """Output from a single screening stage."""

    name: str
    description: str
    passed: list[str]
    failed: list[str] = field(default_factory=list)
    details: dict[str, dict] = field(default_factory=dict)
    external_checks: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.passed)


class BaseScreener(ABC):
    """Abstract base for pipeline screeners."""

    name: str = "Base Screener"
    description: str = ""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def screen(self, stocks: dict[str, StockData]) -> ScreenerResult:
        """Filter stocks and return results."""

    def _passes_threshold(self, value: float | None, minimum: float) -> bool:
        return value is not None and value >= minimum

    def _in_range(self, value: float | None, low: float, high: float) -> bool:
        return value is not None and low <= value <= high
