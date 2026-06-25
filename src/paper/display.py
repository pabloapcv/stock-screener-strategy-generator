"""Paper trading CLI display."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.paper.engine import get_portfolio_summary
from src.paper.models import PaperPosition
from src.paper.store import reset_portfolio

console = Console()


def _fmt_pnl(val: float) -> str:
    if val >= 0:
        return f"[green]+${val:,.0f}[/green]"
    return f"[red]−${abs(val):,.0f}[/red]"


def print_status() -> None:
    summary = get_portfolio_summary()
    portfolio = summary["portfolio"]

    console.print(Panel.fit(
        f"[bold cyan]Paper Portfolio[/bold cyan]\n"
        f"Equity: [bold]${summary['equity']:,.0f}[/bold]  "
        f"({summary['return_pct']:+.1f}% vs ${portfolio.starting_capital:,.0f} start)\n"
        f"Cash: ${portfolio.cash:,.0f}  |  "
        f"Realized: {_fmt_pnl(summary['total_realized'])}  |  "
        f"Unrealized: {_fmt_pnl(summary['total_unrealized'])}",
        border_style="cyan",
    ))

    if summary["open_marks"]:
        table = Table(title="Open Positions", header_style="bold")
        table.add_column("ID", style="dim")
        table.add_column("Ticker", style="cyan")
        table.add_column("Strategy")
        table.add_column("Size", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("%", justify="right")
        table.add_column("Target", justify="right", style="green")
        table.add_column("Stop", justify="right", style="red")

        for mark in summary["open_marks"]:
            pos: PaperPosition = mark["position"]
            table.add_row(
                pos.id,
                pos.ticker,
                pos.strategy,
                f"{pos.size} {pos.size_unit}",
                f"${pos.entry_stock_price:.2f}",
                f"${mark['current_price']:.2f}",
                _fmt_pnl(mark["unrealized_pnl"]),
                f"{mark['pct_change']:+.1f}%",
                f"${pos.stock_target:.2f}",
                f"${pos.stock_stop:.2f}",
            )
        console.print(table)
    else:
        console.print("[dim]No open positions.[/dim]")

    closed = portfolio.closed_positions
    if closed:
        console.print()
        hist = Table(title="Closed Trades", header_style="bold")
        hist.add_column("Ticker")
        hist.add_column("Strategy")
        hist.add_column("Reason")
        hist.add_column("P&L", justify="right")
        hist.add_column("Closed", style="dim")

        for pos in reversed(closed[-10:]):
            pnl = pos.realized_pnl or 0
            hist.add_row(
                pos.ticker,
                pos.strategy,
                pos.close_reason or "—",
                _fmt_pnl(pnl),
                (pos.closed_at or "")[:10],
            )
        console.print(hist)

        wins = sum(1 for p in closed if (p.realized_pnl or 0) > 0)
        console.print(
            f"\n[dim]Win rate: {wins}/{len(closed)} "
            f"({wins/len(closed)*100:.0f}%)  |  "
            f"Total realized: {_fmt_pnl(summary['total_realized'])}[/dim]"
        )


def print_open_result(position: PaperPosition, idea) -> None:
    console.print(Panel.fit(
        f"[green]Opened paper trade[/green]  [bold]{position.ticker}[/bold]  "
        f"({position.strategy})\n"
        f"ID: {position.id}  |  "
        f"Size: {position.size} {position.size_unit}  |  "
        f"Entry: ${position.entry_stock_price:.2f}\n"
        f"Target: [green]${position.stock_target:.2f}[/green]  |  "
        f"Stop: [red]${position.stock_stop:.2f}[/red]",
        border_style="green",
    ))
    if idea.legs:
        for leg in idea.legs:
            console.print(f"  [dim]{leg.describe()}[/dim]")


def print_close_result(position: PaperPosition) -> None:
    pnl = position.realized_pnl or 0
    color = "green" if pnl >= 0 else "red"
    console.print(Panel.fit(
        f"[{color}]Closed {position.ticker}[/{color}]  "
        f"({position.close_reason})  P&L: {_fmt_pnl(pnl)}",
        border_style=color,
    ))


def run_reset() -> None:
    reset_portfolio()
    console.print("[yellow]Paper portfolio reset to $100,000.[/yellow]")
