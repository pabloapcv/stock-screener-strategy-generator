"""Build morning report content."""

from __future__ import annotations

from datetime import datetime

from src.ideas.strategies import TradeIdea
from src.paper.models import PaperPosition


def _fmt_pnl(val: float) -> str:
    sign = "+" if val >= 0 else "−"
    return f"{sign}${abs(val):,.0f}"


def build_report(
    ideas: list[TradeIdea],
    opened: list[tuple[PaperPosition, TradeIdea]],
    skipped_opens: list[str],
    portfolio_summary: dict,
    auto_closed: list[PaperPosition],
    ideas_path: str | None = None,
) -> str:
    """Build plain-text morning report."""
    now = datetime.now()
    lines = [
        "=" * 60,
        f"  MORNING TRADING REPORT — {now.strftime('%A %B %d, %Y %H:%M')}",
        "=" * 60,
        "",
    ]

    # Portfolio snapshot
    p = portfolio_summary["portfolio"]
    lines += [
        "PORTFOLIO",
        "-" * 40,
        f"  Equity:      ${portfolio_summary['equity']:,.0f}  ({portfolio_summary['return_pct']:+.1f}%)",
        f"  Cash:        ${p.cash:,.0f}",
        f"  Realized:    {_fmt_pnl(portfolio_summary['total_realized'])}",
        f"  Unrealized:  {_fmt_pnl(portfolio_summary['total_unrealized'])}",
        f"  Starting:    ${p.starting_capital:,.0f}",
        "",
    ]

    if auto_closed:
        lines += ["AUTO-CLOSED (stop/target hit)", "-" * 40]
        for pos in auto_closed:
            lines.append(
                f"  {pos.ticker}  {pos.strategy}  "
                f"{pos.close_reason}  P&L: {_fmt_pnl(pos.realized_pnl or 0)}"
            )
        lines.append("")

    # Open positions
    marks = portfolio_summary.get("open_marks", [])
    if marks:
        lines += ["OPEN POSITIONS", "-" * 40]
        for mark in marks:
            pos: PaperPosition = mark["position"]
            lines.append(
                f"  {pos.ticker:<6} {pos.strategy:<22} "
                f"${mark['current_price']:>8.2f}  "
                f"P&L: {_fmt_pnl(mark['unrealized_pnl']):>10}  "
                f"({mark['pct_change']:+.1f}%)"
            )
            lines.append(
                f"         Target ${pos.stock_target:.2f}  |  Stop ${pos.stock_stop:.2f}  |  ID {pos.id}"
            )
        lines.append("")

    # New ideas
    lines += [f"TODAY'S IDEAS ({len(ideas)})", "-" * 40]
    if not ideas:
        lines.append("  No new ideas passed the screener today.")
    for i, idea in enumerate(ideas, 1):
        lines.append(
            f"  {i}. {idea.ticker}  {idea.direction.upper()}  "
            f"{idea.conviction} conviction  Score {idea.composite_score:.0f}"
        )
        lines.append(f"     {idea.setup} → {idea.strategy}  ({idea.timeframe})")
        lines.append(
            f"     Entry ${idea.stock_price:.2f}  "
            f"Target ${idea.stock_target:.2f}  Stop ${idea.stock_stop:.2f}"
        )
        if idea.legs:
            for leg in idea.legs:
                lines.append(f"     {leg.describe()}")
        if idea.profit_report and idea.profit_report.scenarios:
            s = idea.profit_report.scenarios[0]
            lines.append(
                f"     P&L @ target: {_fmt_pnl(s.pnl_at_target)}  "
                f"@ stop: {_fmt_pnl(s.pnl_at_stop)}  ({s.size} {s.unit})"
            )
        lines.append("")

    # Newly opened paper trades
    lines += [f"NEW PAPER TRADES ({len(opened)})", "-" * 40]
    if not opened:
        lines.append("  No new positions opened.")
    for pos, idea in opened:
        lines.append(
            f"  OPENED {pos.ticker}  {pos.strategy}  "
            f"{pos.size} {pos.size_unit}  ID {pos.id}"
        )
    if skipped_opens:
        lines.append("")
        lines.append("  Skipped:")
        for reason in skipped_opens:
            lines.append(f"    • {reason}")
    lines.append("")

    if ideas_path:
        lines += ["FILES", "-" * 40, f"  Ideas: {ideas_path}", ""]

    lines += [
        "-" * 60,
        "Not financial advice. Verify prices in your broker before trading.",
        "=" * 60,
    ]
    return "\n".join(lines)


def report_to_dict(
    ideas: list[TradeIdea],
    opened: list[tuple[PaperPosition, TradeIdea]],
    skipped_opens: list[str],
    portfolio_summary: dict,
    auto_closed: list[PaperPosition],
    ideas_path: str | None = None,
) -> dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "portfolio": {
            "equity": portfolio_summary["equity"],
            "cash": portfolio_summary["portfolio"].cash,
            "return_pct": portfolio_summary["return_pct"],
            "total_realized": portfolio_summary["total_realized"],
            "total_unrealized": portfolio_summary["total_unrealized"],
        },
        "auto_closed": [
            {"ticker": p.ticker, "reason": p.close_reason, "pnl": p.realized_pnl}
            for p in auto_closed
        ],
        "open_positions": [
            {
                "id": m["position"].id,
                "ticker": m["position"].ticker,
                "strategy": m["position"].strategy,
                "unrealized_pnl": m["unrealized_pnl"],
                "pct_change": m["pct_change"],
            }
            for m in portfolio_summary.get("open_marks", [])
        ],
        "ideas_count": len(ideas),
        "ideas": [{"ticker": i.ticker, "strategy": i.strategy, "score": i.composite_score} for i in ideas],
        "opened_count": len(opened),
        "opened": [{"id": p.id, "ticker": p.ticker, "strategy": p.strategy} for p, _ in opened],
        "skipped": skipped_opens,
        "ideas_file": ideas_path,
    }
