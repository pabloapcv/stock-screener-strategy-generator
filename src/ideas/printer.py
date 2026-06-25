"""Rich terminal output for trading ideas."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.ideas.strategies import TradeIdea

console = Console()


def print_ideas(ideas: list[TradeIdea]) -> None:
    if not ideas:
        console.print("[yellow]No trading ideas generated.[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Trading Ideas[/bold cyan] — {len(ideas)} setups\n"
        "[dim]Not financial advice. Verify all prices in your broker before executing.[/dim]",
        border_style="cyan",
    ))

    for i, idea in enumerate(ideas, 1):
        _print_single_idea(i, idea)
        console.print()


def _conviction_style(conviction: str) -> str:
    return {"high": "bold green", "medium": "yellow", "low": "dim"}.get(conviction, "white")


def _fmt_pnl(val: float) -> str:
    if val >= 0:
        return f"[green]+${val:,.0f}[/green]"
    return f"[red]−${abs(val):,.0f}[/red]"


def _print_profit_table(idea: TradeIdea) -> None:
    report = idea.profit_report
    if not report:
        return

    unit_label = "shares" if idea.strategy_type == "stock" else "contracts"
    table = Table(
        title=f"Profit Calculator ({unit_label})",
        show_header=True,
        header_style="bold",
    )
    table.add_column(unit_label.title(), justify="right")
    table.add_column("Capital", justify="right")
    table.add_column("At Target", justify="right")
    table.add_column("At Stop", justify="right")
    table.add_column("Max Profit", justify="right")
    table.add_column("Max Loss", justify="right")
    table.add_column("Return", justify="right")

    for s in report.scenarios:
        max_p = f"${s.max_profit:,.0f}" if s.max_profit is not None else "—"
        max_l = f"${s.max_loss:,.0f}" if s.max_loss is not None else "—"
        table.add_row(
            str(s.size),
            f"${s.capital_required:,.0f}",
            _fmt_pnl(s.pnl_at_target),
            _fmt_pnl(s.pnl_at_stop),
            max_p,
            max_l,
            f"{s.return_at_target_pct:+.1f}%",
        )

    console.print(table)

    if idea.breakeven is not None:
        be_status = "above" if report.above_breakeven_at_target else "below"
        console.print(
            f"  [dim]Breakeven: ${idea.breakeven:.2f} — "
            f"target is {be_status} breakeven[/dim]"
        )
    if report.note:
        console.print(f"  [yellow]⚠ {report.note}[/yellow]")


def _print_single_idea(rank: int, idea: TradeIdea) -> None:
    direction_color = "green" if idea.direction == "bullish" else "red" if idea.direction == "bearish" else "yellow"
    header = (
        f"[bold]#{rank} {idea.ticker}[/bold]  "
        f"[{direction_color}]{idea.direction.upper()}[/{direction_color}]  "
        f"[{_conviction_style(idea.conviction)}]{idea.conviction} conviction[/{_conviction_style(idea.conviction)}]  "
        f"Score: {idea.composite_score:.0f}"
    )
    console.print(Panel(header, subtitle=f"{idea.setup.title()} setup → {idea.strategy}", border_style="blue"))

    # Trade structure
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")

    table.add_row("Strategy", f"[bold]{idea.strategy}[/bold] ({idea.strategy_type})")
    table.add_row("Timeframe", idea.timeframe)
    table.add_row("Stock Price", f"${idea.stock_price:.2f}")
    table.add_row("Stock Target", f"[green]${idea.stock_target:.2f}[/green]")
    table.add_row("Stock Stop", f"[red]${idea.stock_stop:.2f}[/red]")

    if idea.expiration:
        table.add_row("Expiration", f"{idea.expiration} ({idea.dte} DTE)")
    if idea.iv_rank:
        table.add_row("IV Rank (proxy)", f"{idea.iv_rank:.0f}")

    if idea.legs:
        table.add_row("Legs", "")
        for leg in idea.legs:
            table.add_row("", f"  {leg.describe()}")

    if idea.max_loss is not None:
        table.add_row("Max Loss", f"[red]${idea.max_loss:,.0f}[/red] per contract")
    if idea.max_profit is not None:
        table.add_row("Max Profit", f"[green]${idea.max_profit:,.0f}[/green] per contract")
    if idea.breakeven is not None:
        table.add_row("Breakeven", f"${idea.breakeven:.2f}")
    if idea.risk_reward:
        table.add_row("Risk/Reward", idea.risk_reward)

    console.print(table)

    _print_profit_table(idea)

    if idea.rationale:
        console.print("[bold]Rationale:[/bold]")
        for r in idea.rationale[:6]:
            console.print(f"  • {r}")

    if idea.warnings:
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for w in idea.warnings:
            console.print(f"  ⚠ {w}")


def save_ideas(ideas: list[TradeIdea], output_dir: Path | None = None) -> Path:
    output_dir = output_dir or Path(__file__).resolve().parents[2] / "output"
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"ideas_{ts}.json"

    payload = []
    for idea in ideas:
        payload.append({
            "ticker": idea.ticker,
            "direction": idea.direction,
            "conviction": idea.conviction,
            "setup": idea.setup,
            "strategy": idea.strategy,
            "strategy_type": idea.strategy_type,
            "timeframe": idea.timeframe,
            "stock_price": idea.stock_price,
            "stock_target": idea.stock_target,
            "stock_stop": idea.stock_stop,
            "expiration": idea.expiration,
            "dte": idea.dte,
            "iv_rank": idea.iv_rank,
            "composite_score": idea.composite_score,
            "legs": [
                {
                    "action": leg.action,
                    "type": leg.option_type,
                    "strike": leg.strike,
                    "expiration": leg.expiration,
                    "premium": leg.premium,
                    "contracts": leg.contracts,
                }
                for leg in idea.legs
            ],
            "max_profit": idea.max_profit,
            "max_loss": idea.max_loss,
            "breakeven": idea.breakeven,
            "risk_reward": idea.risk_reward,
            "rationale": idea.rationale,
            "warnings": idea.warnings,
            "profit_calculator": _profit_to_dict(idea.profit_report) if idea.profit_report else None,
        })

    with open(path, "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "ideas": payload}, f, indent=2)

    return path


def _profit_to_dict(report) -> dict:
    return {
        "profit_at_target_per_unit": report.profit_at_target,
        "profit_at_stop_per_unit": report.profit_at_stop,
        "above_breakeven_at_target": report.above_breakeven_at_target,
        "note": report.note,
        "scenarios": [
            {
                "size": s.size,
                "unit": s.unit,
                "capital_required": s.capital_required,
                "pnl_at_target": s.pnl_at_target,
                "pnl_at_stop": s.pnl_at_stop,
                "max_profit": s.max_profit,
                "max_loss": s.max_loss,
                "return_at_target_pct": s.return_at_target_pct,
            }
            for s in report.scenarios
        ],
    }
