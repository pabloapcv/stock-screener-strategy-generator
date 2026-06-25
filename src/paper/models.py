"""Paper trading data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


def _new_id() -> str:
    return uuid4().hex[:8]


@dataclass
class PaperLeg:
    action: str
    option_type: str
    strike: float
    expiration: str
    entry_premium: float
    contracts: int = 1

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiration": self.expiration,
            "entry_premium": self.entry_premium,
            "contracts": self.contracts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperLeg:
        return cls(**d)


@dataclass
class PaperPosition:
    id: str
    ticker: str
    strategy: str
    strategy_type: str  # debit, credit, stock
    direction: str
    setup: str
    conviction: str
    size: int
    size_unit: str  # contracts or shares
    opened_at: str
    entry_stock_price: float
    entry_cost: float
    stock_target: float
    stock_stop: float
    expiration: str = ""
    dte_at_entry: int = 0
    legs: list[PaperLeg] = field(default_factory=list)
    status: str = "open"
    closed_at: str | None = None
    exit_stock_price: float | None = None
    exit_value: float | None = None
    realized_pnl: float | None = None
    close_reason: str | None = None
    notes: str = ""

    @classmethod
    def new_id(cls) -> str:
        return _new_id()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "strategy": self.strategy,
            "strategy_type": self.strategy_type,
            "direction": self.direction,
            "setup": self.setup,
            "conviction": self.conviction,
            "size": self.size,
            "size_unit": self.size_unit,
            "opened_at": self.opened_at,
            "entry_stock_price": self.entry_stock_price,
            "entry_cost": self.entry_cost,
            "stock_target": self.stock_target,
            "stock_stop": self.stock_stop,
            "expiration": self.expiration,
            "dte_at_entry": self.dte_at_entry,
            "legs": [leg.to_dict() for leg in self.legs],
            "status": self.status,
            "closed_at": self.closed_at,
            "exit_stock_price": self.exit_stock_price,
            "exit_value": self.exit_value,
            "realized_pnl": self.realized_pnl,
            "close_reason": self.close_reason,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperPosition:
        legs = [PaperLeg.from_dict(leg) for leg in d.get("legs", [])]
        return cls(legs=legs, **{k: v for k, v in d.items() if k != "legs"})


@dataclass
class PaperPortfolio:
    starting_capital: float = 100_000.0
    cash: float = 100_000.0
    positions: list[PaperPosition] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions if p.status == "open"]

    @property
    def closed_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions if p.status != "open"]

    def to_dict(self) -> dict:
        return {
            "starting_capital": self.starting_capital,
            "cash": self.cash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "positions": [p.to_dict() for p in self.positions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> PaperPortfolio:
        positions = [PaperPosition.from_dict(p) for p in d.get("positions", [])]
        return cls(
            starting_capital=d.get("starting_capital", 100_000.0),
            cash=d.get("cash", 100_000.0),
            positions=positions,
            created_at=d.get("created_at", datetime.now().isoformat()),
            updated_at=d.get("updated_at", datetime.now().isoformat()),
        )
