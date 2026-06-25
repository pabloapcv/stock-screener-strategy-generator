"""Full per-ticker breakdown across all pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import load_config
from src.data.fetcher import StockData, fetch_universe
from src.data.options import analyze_options
from src.scoring.composite import score_stock
from src.screeners.analyst_momentum import AnalystMomentumScreener, EXTERNAL_SOURCES
from src.screeners.institutional_growth import InstitutionalGrowthScreener
from src.screeners.options_liquidity import OptionsLiquidityScreener
from src.screeners.technical_entry import TechnicalEntryScreener
from src.screeners.base import ScreenerResult

console = Console()


@dataclass
class ExplainResult:
    ticker: str
    stock: StockData
    stages: list[tuple[int, ScreenerResult]]
    stopped_at: int | None
    composite_score: float
    score_components: dict[str, float]


def _fmt_pct(val: float | None) -> str:
    return f"{val:.1%}" if val is not None else "—"


def _fmt_money(val: float | None) -> str:
    return f"${val:,.2f}" if val is not None else "—"


def _fmt_billions(val: float) -> str:
    return f"${val / 1e9:.1f}B" if val else "—"


def _check_row(
    label: str,
    actual: str,
    required: str,
    passed: bool,
) -> tuple[str, str, str, str]:
    status = "[green]✓[/green]" if passed else "[red]✗[/red]"
    return (label, actual, required, status)


def explain_ticker(ticker: str, config: dict | None = None) -> ExplainResult | None:
    """Fetch data and evaluate a single ticker through all stages."""
    config = config or load_config()
    ticker = ticker.strip().upper()

    stocks = fetch_universe([ticker])
    if ticker not in stocks:
        console.print(f"[red]No data available for {ticker}[/red]")
        return None

    stock = stocks[ticker]
    weights = config.get("scoring", {}).get("weights", {})

    # Always analyze options for the explain view
    opts_cfg = config["screener_3_options_liquidity"].get("options", {})
    analyze_options(
        stock,
        atm_oi_min=opts_cfg.get("atm_open_interest_min", 1000),
        daily_vol_min=opts_cfg.get("daily_option_volume_min", 500),
        spread_pct_max=opts_cfg.get("bid_ask_spread_pct_max", 0.05),
        require_weekly=opts_cfg.get("weekly_expirations", True),
    )

    screeners = [
        (1, InstitutionalGrowthScreener(config["screener_1_institutional_growth"])),
        (2, AnalystMomentumScreener(config["screener_2_analyst_momentum"])),
        (3, OptionsLiquidityScreener(config["screener_3_options_liquidity"])),
        (4, TechnicalEntryScreener(config["screener_4_technical_entry"])),
    ]

    stages: list[tuple[int, ScreenerResult]] = []
    stopped_at: int | None = None
    pool = {ticker: stock}

    for num, screener in screeners:
        result = screener.screen(pool)
        stages.append((num, result))
        if ticker not in result.passed:
            stopped_at = num
            break
        pool = {ticker: stock}

    scored = score_stock(stock, weights)
    return ExplainResult(
        ticker=ticker,
        stock=stock,
        stages=stages,
        stopped_at=stopped_at,
        composite_score=scored.composite_score,
        score_components=scored.components,
    )


def print_explain(result: ExplainResult, config: dict | None = None) -> None:
    """Render a full explain report to the terminal."""
    config = config or load_config()
    s = result.stock
    t = result.ticker

    console.print(Panel.fit(
        f"[bold cyan]{t}[/bold cyan]  { _fmt_money(s.price) }\n"
        f"[dim]Composite score: [bold]{result.composite_score:.1f}[/bold] / 100[/dim]",
        border_style="cyan",
    ))

    # Fundamentals
    fund = Table(title="Fundamentals (Yahoo Finance)", show_header=True, header_style="bold")
    fund.add_column("Metric")
    fund.add_column("Value", justify="right")
    fund.add_row("Market Cap", _fmt_billions(s.market_cap))
    fund.add_row("Revenue Growth (TTM)", _fmt_pct(s.revenue_growth))
    fund.add_row("EPS Growth (TTM)", _fmt_pct(s.eps_growth))
    fund.add_row("ROE", _fmt_pct(s.roe))
    fund.add_row("Beta", f"{s.beta:.2f}" if s.beta else "—")
    fund.add_row("Analyst Rating", f"{s.analyst_rating:.2f} / 5" if s.analyst_rating else "—")
    fund.add_row("Analyst Count", str(s.analyst_count))
    fund.add_row("Target Mean Price", _fmt_money(s.target_mean_price))
    fund.add_row("EPS Revision Trend", _fmt_pct(s.eps_revision_trend))
    console.print(fund)
    console.print()

    # Technicals
    s1 = config["screener_1_institutional_growth"]
    f = s1.get("filters", {})
    tech_cfg = s1.get("technicals", {})

    tech = Table(title="Technicals (computed from 1Y daily bars)", show_header=True, header_style="bold")
    tech.add_column("Metric")
    tech.add_column("Value", justify="right")
    tech.add_column("Required", justify="right")
    tech.add_column("", justify="center")

    tech.add_row(*_check_row(
        "Relative Volume",
        f"{s.relative_volume:.2f}x",
        f"≥ {f.get('relative_volume_min', 1.2):.1f}x",
        s.relative_volume + 0.005 >= f.get("relative_volume_min", 1.2),
    ))
    tech.add_row(*_check_row(
        "Avg Volume",
        f"{s.avg_volume:,.0f}",
        f"≥ {f.get('avg_volume_min', 2_000_000):,.0f}",
        s.avg_volume >= f.get("avg_volume_min", 2_000_000),
    ))
    tech.add_row(*_check_row(
        "RSI (14)",
        f"{s.rsi:.0f}" if s.rsi else "—",
        f"{tech_cfg.get('rsi_min', 50)}–{tech_cfg.get('rsi_max', 70)}",
        s.rsi is not None and tech_cfg.get("rsi_min", 50) <= s.rsi <= tech_cfg.get("rsi_max", 70),
    ))
    tech.add_row(*_check_row(
        "Price vs 50 SMA",
        "Above" if s.price_above_sma_50 else "Below",
        "Above",
        s.price_above_sma_50,
    ))
    tech.add_row(*_check_row(
        "Price vs 200 SMA",
        "Above" if s.price_above_sma_200 else "Below",
        "Above",
        s.price_above_sma_200,
    ))
    tech.add_row(*_check_row(
        "50 SMA vs 200 SMA",
        "Golden cross" if s.sma_50_above_sma_200 else "No",
        "Golden cross",
        s.sma_50_above_sma_200,
    ))
    dist = _fmt_pct(s.pct_from_52w_high) if s.pct_from_52w_high is not None else "—"
    tech.add_row(*_check_row(
        "Distance from 52W High",
        dist,
        f"≤ {_fmt_pct(tech_cfg.get('within_pct_of_52w_high', 0.10))}",
        s.pct_from_52w_high is not None and s.pct_from_52w_high <= tech_cfg.get("within_pct_of_52w_high", 0.10),
    ))
    tech.add_row("SMA 20", _fmt_money(s.sma_20), "", "")
    tech.add_row("SMA 50", _fmt_money(s.sma_50), "", "")
    tech.add_row("SMA 200", _fmt_money(s.sma_200), "", "")
    tech.add_row("1W Performance", _fmt_pct(s.performance_1w), "", "")
    tech.add_row("1M Performance", _fmt_pct(s.performance_1m), "", "")
    tech.add_row("3M Performance", _fmt_pct(s.performance_3m), "", "")
    console.print(tech)
    console.print()

    # Entry signals
    signals = Table(title="Entry Signals", show_header=True, header_style="bold")
    signals.add_column("Signal")
    signals.add_column("Active", justify="center")
    signal_list = [
        ("Pullback to 20 SMA", s.pullback_to_sma_20),
        ("Pullback to 50 SMA", s.pullback_to_sma_50),
        ("Breakout from consolidation", s.breakout_from_consolidation),
        ("Relative strength vs SPY", s.relative_strength_vs_spy),
        ("Volume confirmation", s.volume_confirmation),
    ]
    for name, active in signal_list:
        signals.add_row(name, "[green]✓[/green]" if active else "[dim]—[/dim]")
    active_count = sum(1 for _, a in signal_list if a)
    signals.add_row("[bold]Total[/bold]", f"[bold]{active_count}[/bold] (need ≥ 2 for stage 4)")
    console.print(signals)
    console.print()

    # Options
    od = s.options_details
    opts = Table(title="Options Liquidity (Yahoo Finance)", show_header=True, header_style="bold")
    opts.add_column("Metric")
    opts.add_column("Value", justify="right")
    opts.add_column("Required", justify="right")
    opts.add_column("", justify="center")
    opts_cfg = config["screener_3_options_liquidity"].get("options", {})

    opts.add_row(*_check_row(
        "Weekly expirations",
        "Yes" if od.get("has_weekly") else "No",
        "Yes",
        bool(od.get("has_weekly")),
    ))
    atm_oi = od.get("atm_open_interest", 0)
    opts.add_row(*_check_row(
        "ATM Open Interest",
        f"{atm_oi:,}",
        f"≥ {opts_cfg.get('atm_open_interest_min', 1000):,}",
        atm_oi >= opts_cfg.get("atm_open_interest_min", 1000),
    ))
    atm_vol = od.get("atm_volume", 0)
    opts.add_row(*_check_row(
        "ATM Volume",
        f"{atm_vol:,}",
        f"≥ {opts_cfg.get('daily_option_volume_min', 500):,}",
        atm_vol >= opts_cfg.get("daily_option_volume_min", 500),
    ))
    spread = od.get("avg_bid_ask_spread_pct")
    opts.add_row(*_check_row(
        "Bid/Ask Spread",
        f"{spread:.1%}" if spread is not None else "—",
        f"< {_fmt_pct(opts_cfg.get('bid_ask_spread_pct_max', 0.05))}",
        spread is not None and spread <= opts_cfg.get("bid_ask_spread_pct_max", 0.05),
    ))
    if od.get("atm_strike"):
        opts.add_row("ATM Strike", f"${od['atm_strike']:.2f}", "", "")
    opts.add_row("Options Score", f"{s.options_score:.0%}", "", "")
    console.print(opts)
    console.print()

    # Pipeline stages
    pipeline = Table(title="Pipeline Funnel", show_header=True, header_style="bold")
    pipeline.add_column("Stage")
    pipeline.add_column("Result", justify="center")
    pipeline.add_column("Details")

    for num, stage_result in result.stages:
        passed = t in stage_result.passed
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        detail = stage_result.details.get(t, {})
        failed = detail.get("failed", [])
        if failed:
            detail_str = f"Blocked by: {', '.join(failed)}"
        elif num == 4:
            active = detail.get("active_signals", [])
            detail_str = f"Signals: {', '.join(active) or 'none'}"
        else:
            detail_str = "All filters passed"
        pipeline.add_row(f"{num}. {stage_result.name}", status, detail_str)

    # Stages not reached because funnel stopped early
    reached = {num for num, _ in result.stages}
    all_stages = [
        (1, "Institutional Growth Leaders"),
        (2, "Analyst Upgrade Momentum"),
        (3, "High-Quality Options Candidates"),
        (4, "Technical Entry Setup"),
    ]
    for num, name in all_stages:
        if num not in reached:
            pipeline.add_row(f"{num}. {name}", "[dim]SKIPPED[/dim]", "Did not pass prior stage")

    console.print(pipeline)
    console.print()

    # Composite score breakdown
    weights = config.get("scoring", {}).get("weights", {})
    scores = Table(title="Composite Score Breakdown", show_header=True, header_style="bold")
    scores.add_column("Component")
    scores.add_column("Weight", justify="right")
    scores.add_column("Score", justify="right")
    scores.add_column("Contribution", justify="right")

    for key, weight in weights.items():
        comp = result.score_components.get(key, 0)
        contrib = comp * weight
        scores.add_row(
            key.replace("_", " ").title(),
            f"{weight:.0%}",
            f"{comp:.0f}",
            f"{contrib:.1f}",
        )
    scores.add_row("[bold]Total[/bold]", "", "", f"[bold]{result.composite_score:.1f}[/bold]")
    console.print(scores)
    console.print()

    # External links (stage 2 manual checks)
    ext_checks = config["screener_2_analyst_momentum"].get("external_checks", [])
    if ext_checks:
        console.print("[bold]Manual verification links:[/bold]")
        for check in ext_checks:
            url = EXTERNAL_SOURCES.get(check, "").format(ticker=t)
            if url:
                console.print(f"  • {check.replace('_', ' ')}: {url}")
        console.print()

    # Verdict
    if result.stopped_at is None:
        verdict = f"[green]{t} passes all 4 stages — high-conviction candidate.[/green]"
    else:
        stage_name = next(n for num, n in all_stages if num == result.stopped_at)
        verdict = (
            f"[yellow]{t} stopped at stage {result.stopped_at} ({stage_name}).[/yellow]\n"
            f"Composite score {result.composite_score:.1f} reflects quality, "
            f"but hard filters block pipeline progression."
        )
    console.print(Panel(verdict, title="Verdict", border_style="blue"))


def run_explain(ticker: str) -> None:
    """CLI entry point for explain command."""
    result = explain_ticker(ticker)
    if result:
        print_explain(result)
