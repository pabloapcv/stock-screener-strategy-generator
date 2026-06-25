#!/usr/bin/env python3
"""CLI for the multi-stage stock screening pipeline."""

from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_config
from src.pipeline import ScreeningPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Multi-stage institutional stock screening pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Daily Workflow:
  8:00 AM  python main.py run                    # Full pipeline
  8:00 AM  python main.py run --stage 1          # Institutional growth only
  8:05 AM  python main.py run --tickers NVDA,META,CRWD  # Specific tickers
  8:15 AM  python main.py run --skip-options     # Skip slow options check
  8:25 AM  python main.py score --tickers AAPL,NVDA     # Score specific names
  8:25 AM  python main.py explain NVDA                  # Full breakdown for one ticker
  8:30 AM  python main.py ideas                        # Generate options trade ideas
  8:30 AM  python main.py ideas --tickers TER,GLW      # Ideas for specific tickers
  8:35 AM  python main.py paper open-ideas             # Paper trade latest ideas
  8:35 AM  python main.py paper status                 # Check P&L
  8:00 AM  python main.py daily                        # Full morning automation
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run the screening pipeline")
    run_parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated tickers (default: S&P 500 + NASDAQ 100)",
    )
    run_parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2, 3, 4],
        help="Run only up to this stage",
    )
    run_parser.add_argument(
        "--skip-options",
        action="store_true",
        help="Skip options liquidity screening (faster)",
    )
    run_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to output/",
    )
    run_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    # score command
    score_parser = subparsers.add_parser("score", help="Score specific tickers")
    score_parser.add_argument(
        "--tickers",
        type=str,
        required=True,
        help="Comma-separated tickers to score",
    )

    # config command
    subparsers.add_parser("config", help="Show current configuration")

    # diagnose command
    diag_parser = subparsers.add_parser(
        "diagnose", help="Show which filters block specific tickers"
    )
    diag_parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated tickers (default: example growth names)",
    )
    diag_parser.add_argument(
        "--stage",
        type=int,
        default=1,
        choices=[1, 2, 3, 4],
        help="Screener stage to diagnose (default: 1)",
    )

    # explain command
    explain_parser = subparsers.add_parser(
        "explain", help="Full data breakdown for a single ticker"
    )
    explain_parser.add_argument(
        "ticker",
        type=str,
        help="Ticker symbol (e.g. NVDA)",
    )

    # ideas command
    ideas_parser = subparsers.add_parser(
        "ideas", help="Generate options trading ideas from screened stocks"
    )
    ideas_parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated tickers (default: run pipeline and use survivors)",
    )
    ideas_parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum number of ideas to generate (default: 10)",
    )
    ideas_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save ideas to output/",
    )

    # paper trading command group
    paper_parser = subparsers.add_parser("paper", help="Paper trade generated ideas")
    paper_sub = paper_parser.add_subparsers(dest="paper_command", required=True)

    paper_sub.add_parser("status", help="Show portfolio and live P&L")

    paper_open = paper_sub.add_parser("open", help="Open a paper trade for one ticker")
    paper_open.add_argument("ticker", type=str)
    paper_open.add_argument("--contracts", type=int, help="Number of option contracts")
    paper_open.add_argument("--shares", type=int, help="Number of shares (stock trades)")

    paper_open_ideas = paper_sub.add_parser(
        "open-ideas", help="Open paper trades from latest ideas file"
    )
    paper_open_ideas.add_argument("--file", type=str, help="Path to ideas JSON")
    paper_open_ideas.add_argument("--contracts", type=int)
    paper_open_ideas.add_argument("--shares", type=int)
    paper_open_ideas.add_argument("--max", type=int, help="Max trades to open")

    paper_close = paper_sub.add_parser("close", help="Close an open paper trade")
    paper_close.add_argument("ticker", type=str, nargs="?", help="Ticker to close")
    paper_close.add_argument("--id", type=str, help="Position ID to close")

    paper_sub.add_parser("reset", help="Reset portfolio to starting capital")

    # daily morning automation
    daily_parser = subparsers.add_parser(
        "daily", help="Run full morning workflow (ideas + paper trades + report)"
    )
    daily_parser.add_argument(
        "--max-ideas", type=int, help="Max ideas to generate (default: from config)"
    )
    daily_parser.add_argument(
        "--max-trades", type=int, help="Max new paper trades to open (default: from config)"
    )
    daily_parser.add_argument(
        "--no-open", action="store_true", help="Generate ideas/report only, don't open trades"
    )
    daily_parser.add_argument(
        "--email", action="store_true", help="Send report via email (requires .env SMTP)"
    )
    daily_parser.add_argument(
        "--quiet", action="store_true", help="Suppress report output to terminal"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "config":
        config = load_config()
        import yaml
        print(yaml.dump(config, default_flow_style=False, sort_keys=False))
        return

    if args.command == "score":
        from src.data.fetcher import fetch_universe
        from src.scoring.composite import rank_stocks
        from rich.console import Console
        from rich.table import Table

        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        config = load_config()
        weights = config.get("scoring", {}).get("weights", {})

        console = Console()
        console.print(f"Scoring {len(tickers)} tickers...")
        stocks = fetch_universe(tickers)
        ranked = rank_stocks(stocks, weights, top_n=len(tickers))

        table = Table(title="Composite Scores")
        table.add_column("Rank", justify="right")
        table.add_column("Ticker", style="bold")
        table.add_column("Score", justify="right")
        for comp in weights:
            table.add_column(comp.replace("_", " ").title(), justify="right")

        for r in ranked:
            row = [str(r.rank), r.ticker, f"{r.composite_score:.1f}"]
            row.extend(f"{r.components.get(k, 0):.0f}" for k in weights)
            table.add_row(*row)

        console.print(table)
        return

    if args.command == "diagnose":
        from collections import Counter

        from rich.console import Console
        from rich.table import Table

        from src.data.fetcher import fetch_universe
        from src.screeners.analyst_momentum import AnalystMomentumScreener
        from src.screeners.institutional_growth import InstitutionalGrowthScreener
        from src.screeners.options_liquidity import OptionsLiquidityScreener
        from src.screeners.technical_entry import TechnicalEntryScreener

        tickers = (
            [t.strip().upper() for t in args.tickers.split(",")]
            if args.tickers
            else ["NVDA", "META", "CRWD", "PANW", "ANET", "APP", "MELI"]
        )
        config = load_config()
        stage_map = {
            1: InstitutionalGrowthScreener(config["screener_1_institutional_growth"]),
            2: AnalystMomentumScreener(config["screener_2_analyst_momentum"]),
            3: OptionsLiquidityScreener(config["screener_3_options_liquidity"]),
            4: TechnicalEntryScreener(config["screener_4_technical_entry"]),
        }
        screener = stage_map[args.stage]

        console = Console()
        console.print(f"Diagnosing stage {args.stage} for {len(tickers)} tickers...")
        stocks = fetch_universe(tickers)
        result = screener.screen(stocks)

        table = Table(title=f"Stage {args.stage}: {screener.name}")
        table.add_column("Ticker", style="cyan")
        table.add_column("Pass", justify="center")
        table.add_column("Rel Vol", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("Rev Gr", justify="right")
        table.add_column("Failed Filters", style="dim")

        fail_counts: Counter = Counter()
        for ticker in tickers:
            if ticker not in result.details:
                table.add_row(ticker, "—", "—", "—", "—", "no data")
                continue
            detail = result.details[ticker]
            stock = stocks.get(ticker)
            failed = detail.get("failed", [])
            for f in failed:
                fail_counts[f] += 1
            rev = detail.get("revenue_growth")
            table.add_row(
                ticker,
                "✓" if ticker in result.passed else "✗",
                f"{detail.get('relative_volume', 0):.2f}x" if stock else "—",
                f"{detail.get('rsi', 0):.0f}" if detail.get("rsi") else "—",
                f"{rev:.0%}" if rev is not None else "—",
                ", ".join(failed) or "—",
            )

        console.print(table)
        if fail_counts:
            console.print("\n[bold]Most common blockers:[/bold]")
            for reason, count in fail_counts.most_common():
                console.print(f"  {reason}: {count}/{len(tickers)}")
        return

    if args.command == "explain":
        from src.explain import run_explain
        run_explain(args.ticker)
        return

    if args.command == "ideas":
        from rich.console import Console

        from src.ideas.generator import generate_ideas
        from src.ideas.printer import print_ideas, save_ideas

        console = Console()
        tickers = None
        if args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",")]

        if tickers:
            console.print(f"Generating ideas for {len(tickers)} tickers...")
        else:
            console.print("[dim]Running pipeline to find candidates...[/dim]")

        ideas = generate_ideas(
            tickers=tickers,
            from_pipeline=tickers is None,
            max_ideas=args.max,
        )
        print_ideas(ideas)

        if not args.no_save and ideas:
            path = save_ideas(ideas)
            console.print(f"[dim]Ideas saved to {path}[/dim]")
        return

    if args.command == "paper":
        from pathlib import Path

        from src.paper.display import print_close_result, print_open_result, print_status, run_reset
        from src.paper.engine import (
            PaperTradingError,
            close_position,
            open_from_ideas_file,
            open_position,
        )

        if args.paper_command == "status":
            print_status()
        elif args.paper_command == "open":
            try:
                pos, idea = open_position(
                    args.ticker,
                    contracts=args.contracts,
                    shares=args.shares,
                )
                print_open_result(pos, idea)
            except PaperTradingError as e:
                print(f"Error: {e}")
        elif args.paper_command == "open-ideas":
            try:
                path = Path(args.file) if args.file else None
                opened = open_from_ideas_file(
                    path=path,
                    contracts=args.contracts,
                    shares=args.shares,
                    max_trades=args.max,
                )
                for pos, idea in opened:
                    print_open_result(pos, idea)
                if not opened:
                    print("No positions opened.")
            except PaperTradingError as e:
                print(f"Error: {e}")
        elif args.paper_command == "close":
            try:
                pos = close_position(position_id=args.id, ticker=args.ticker)
                print_close_result(pos)
            except PaperTradingError as e:
                print(f"Error: {e}")
        elif args.paper_command == "reset":
            run_reset()
        return

    if args.command == "daily":
        from src.config import load_config
        from src.daily.morning import run_morning

        result = run_morning(
            max_ideas=args.max_ideas,
            max_new_trades=args.max_trades,
            open_trades=not args.no_open,
            send_email=args.email,
            quiet=args.quiet,
        )
        if args.quiet:
            from rich.console import Console
            c = Console()
            c.print(f"[green]Morning run complete.[/green]")
            c.print(f"  Ideas: {result.ideas_count}  |  Opened: {result.opened_count}")
            if result.report_path:
                c.print(f"  Report: {result.report_path}")
            if args.email or load_config().get("daily", {}).get("email_enabled"):
                if result.email_sent:
                    c.print("  Email: sent")
                else:
                    c.print("[yellow]  Email: not sent — add SMTP_PASSWORD to .env[/yellow]")
        return

    if args.command == "run":
        tickers = None
        if args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",")]

        pipeline = ScreeningPipeline()
        pipeline.run(
            tickers=tickers,
            skip_options=args.skip_options,
            save_output=not args.no_save,
            max_stage=args.stage or 4,
        )


if __name__ == "__main__":
    main()
