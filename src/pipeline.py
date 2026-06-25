"""Multi-stage screening pipeline orchestrator."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from src.config import load_config
from src.data.fetcher import StockData, fetch_universe
from src.data.universe import get_combined_universe
from src.scoring.composite import ScoredStock, rank_stocks
from src.screeners.analyst_momentum import AnalystMomentumScreener
from src.screeners.base import ScreenerResult
from src.screeners.institutional_growth import InstitutionalGrowthScreener
from src.screeners.options_liquidity import OptionsLiquidityScreener
from src.screeners.technical_entry import TechnicalEntryScreener

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class PipelineResult:
    """Full pipeline run output."""

    timestamp: str
    universe_size: int
    stage_results: list[ScreenerResult] = field(default_factory=list)
    ranked: list[ScoredStock] = field(default_factory=list)
    stock_data: dict[str, StockData] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "universe_size": self.universe_size,
            "stages": [
                {
                    "name": s.name,
                    "passed_count": s.count,
                    "passed": s.passed,
                }
                for s in self.stage_results
            ],
            "ranked": [
                {
                    "rank": r.rank,
                    "ticker": r.ticker,
                    "score": r.composite_score,
                    "components": r.components,
                }
                for r in self.ranked
            ],
        }


class ScreeningPipeline:
    """
    8000 Stocks → Institutional Growth → Analyst Momentum →
    Options Liquidity → Technical Entry → Ranked List
    """

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.pipeline_cfg = self.config.get("pipeline", {})

    def run(
        self,
        tickers: list[str] | None = None,
        skip_options: bool = False,
        save_output: bool = True,
        max_stage: int = 4,
    ) -> PipelineResult:
        """Execute the full screening pipeline."""
        console.print(Panel.fit(
            "[bold cyan]Stock Screener Pipeline[/bold cyan]\n"
            "Institutional Growth → Analyst Momentum → Options → Technical Entry",
            border_style="cyan",
        ))

        # Stage 0: Load universe
        if tickers is None:
            sources = self.config.get("universe", {}).get("sources", ["sp500", "nasdaq100"])
            tickers = get_combined_universe(sources)

        console.print(f"\n[bold]Universe:[/bold] {len(tickers)} stocks")
        workers = self.pipeline_cfg.get("parallel_workers", 8)

        # Fetch all data
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching market data...", total=len(tickers))

            def on_progress(done, total):
                progress.update(task, completed=done)

            stock_data = fetch_universe(tickers, workers=workers, progress_callback=on_progress)

        skipped = len(tickers) - len(stock_data)
        skip_note = f" ({skipped} skipped — no data)" if skipped else ""
        console.print(f"[green]✓[/green] Loaded {len(stock_data)} stocks{skip_note}\n")

        # Stage 1: Institutional Growth
        stage1 = self._run_stage(
            InstitutionalGrowthScreener(self.config["screener_1_institutional_growth"]),
            stock_data,
            stage_num=1,
        )
        narrowed = {t: stock_data[t] for t in stage1.passed if t in stock_data}

        if max_stage < 2:
            return self._finalize(tickers, stock_data, [stage1], narrowed, save_output)

        # Stage 2: Analyst Momentum (on stage 1 survivors)
        stage2 = self._run_stage(
            AnalystMomentumScreener(self.config["screener_2_analyst_momentum"]),
            narrowed,
            stage_num=2,
        )
        narrowed = {t: stock_data[t] for t in stage2.passed if t in stock_data}

        if max_stage < 3:
            return self._finalize(tickers, stock_data, [stage1, stage2], narrowed, save_output)

        # Stage 3: Options Liquidity
        if skip_options:
            console.print("[yellow]⚠ Skipping options screening (--skip-options)[/yellow]\n")
            stage3 = ScreenerResult(
                name="Options Liquidity (skipped)",
                description="Skipped",
                passed=list(narrowed.keys()),
            )
        else:
            stage3 = self._run_stage(
                OptionsLiquidityScreener(self.config["screener_3_options_liquidity"]),
                narrowed,
                stage_num=3,
            )
            narrowed = {t: stock_data[t] for t in stage3.passed if t in stock_data}

        if max_stage < 4:
            stages = [stage1, stage2, stage3]
            return self._finalize(tickers, stock_data, stages, narrowed, save_output)

        # Stage 4: Technical Entry
        stage4 = self._run_stage(
            TechnicalEntryScreener(self.config["screener_4_technical_entry"]),
            narrowed,
            stage_num=4,
        )

        # Composite scoring — use survivors from the latest stage with results
        weights = self.config.get("scoring", {}).get("weights", {})
        top_n = self.pipeline_cfg.get("top_n_final", 20)
        candidates = self._best_candidates(
            stock_data, [stage1, stage2, stage3, stage4]
        )

        return self._build_result(
            tickers, stock_data, [stage1, stage2, stage3, stage4], candidates, weights, top_n, save_output
        )

    @staticmethod
    def _best_candidates(
        stock_data: dict[str, StockData],
        stages: list[ScreenerResult],
    ) -> dict[str, StockData]:
        """Return stocks from the latest stage that still has survivors."""
        for stage in reversed(stages):
            if stage.passed:
                return {t: stock_data[t] for t in stage.passed if t in stock_data}
        return {}

    def _finalize(
        self,
        tickers: list[str],
        stock_data: dict[str, StockData],
        stages: list[ScreenerResult],
        narrowed: dict[str, StockData],
        save_output: bool,
    ) -> PipelineResult:
        weights = self.config.get("scoring", {}).get("weights", {})
        top_n = self.pipeline_cfg.get("top_n_final", 20)
        return self._build_result(tickers, stock_data, stages, narrowed, weights, top_n, save_output)

    def _build_result(
        self,
        tickers: list[str],
        stock_data: dict[str, StockData],
        stages: list[ScreenerResult],
        candidates: dict[str, StockData],
        weights: dict,
        top_n: int,
        save_output: bool,
    ) -> PipelineResult:
        ranked = rank_stocks(candidates, weights, top_n=top_n) if candidates else []

        result = PipelineResult(
            timestamp=datetime.now().isoformat(),
            universe_size=len(tickers),
            stage_results=stages,
            ranked=ranked,
            stock_data=stock_data,
        )

        self._print_summary(result)
        if not result.ranked and result.stage_results:
            first = result.stage_results[0]
            if first.count == 0 and first.details:
                self._print_near_misses(first)
        self._print_ranked_table(result.ranked, stock_data, result.stage_results)

        if save_output:
            self._save_results(result)

        return result

    def _run_stage(
        self,
        screener,
        stocks: dict[str, StockData],
        stage_num: int,
    ) -> ScreenerResult:
        console.print(f"[bold]Stage {stage_num}:[/bold] {screener.name}")
        console.print(f"  {screener.description}")
        result = screener.screen(stocks)
        console.print(
            f"  [green]✓ {result.count} passed[/green] "
            f"of {len(stocks)} "
            f"([red]{len(result.failed)} filtered out[/red])\n"
        )
        if result.passed:
            preview = ", ".join(result.passed[:10])
            suffix = f" ... +{len(result.passed) - 10} more" if len(result.passed) > 10 else ""
            console.print(f"  [dim]{preview}{suffix}[/dim]\n")
        return result

    def _print_near_misses(self, result: ScreenerResult, top_n: int = 10) -> None:
        """Show stocks closest to passing when a stage returns zero results."""
        near = sorted(
            result.details.items(),
            key=lambda item: len(item[1].get("failed", [])),
        )[:top_n]
        if not near or len(near[0][1].get("failed", [])) > 6:
            return

        table = Table(title="Near Misses (fewest filter failures)", show_header=True)
        table.add_column("Ticker", style="cyan")
        table.add_column("Fails", justify="right")
        table.add_column("Missing Filters", style="dim")

        for ticker, detail in near:
            failed = detail.get("failed", [])
            table.add_row(ticker, str(len(failed)), ", ".join(failed))

        console.print(table)
        console.print(
            "[dim]Tip: relative volume uses the best of recent complete sessions. "
            "Run after market close for best results.[/dim]\n"
        )

    def _print_summary(self, result: PipelineResult) -> None:
        table = Table(title="Pipeline Funnel", show_header=True, header_style="bold")
        table.add_column("Stage", style="cyan")
        table.add_column("Stocks", justify="right", style="green")

        table.add_row("Universe", str(result.universe_size))
        for stage in result.stage_results:
            table.add_row(stage.name, str(stage.count))

        console.print(table)
        console.print()

    def _print_ranked_table(
        self,
        ranked: list[ScoredStock],
        stock_data: dict[str, StockData],
        stage_results: list[ScreenerResult] | None = None,
    ) -> None:
        if not ranked:
            console.print(
                "[yellow]No candidates passed all stages — "
                "showing best survivors from the latest stage with results.[/yellow]"
            )
            return

        table = Table(title="Top Ranked Candidates", show_header=True, header_style="bold")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Ticker", style="bold cyan")
        table.add_column("Score", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("1M Perf", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("Rel Vol", justify="right")
        table.add_column("Signals")

        for r in ranked:
            s = stock_data.get(r.ticker)
            if not s:
                continue
            signals = []
            if s.pullback_to_sma_20:
                signals.append("PB20")
            if s.pullback_to_sma_50:
                signals.append("PB50")
            if s.breakout_from_consolidation:
                signals.append("BO")
            if s.relative_strength_vs_spy:
                signals.append("RS")
            if s.volume_confirmation:
                signals.append("VOL")

            perf = f"{s.performance_1m:.1%}" if s.performance_1m else "—"
            rsi = f"{s.rsi:.0f}" if s.rsi else "—"
            rel_vol = f"{s.relative_volume:.1f}x" if s.relative_volume else "—"

            table.add_row(
                str(r.rank),
                r.ticker,
                f"{r.composite_score:.1f}",
                f"${s.price:.2f}",
                perf,
                rsi,
                rel_vol,
                ", ".join(signals) or "—",
            )

        console.print(table)

    def _save_results(self, result: PipelineResult) -> None:
        output_dir = Path(__file__).resolve().parents[1] / "output"
        output_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"screen_{ts}.json"
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        console.print(f"\n[dim]Results saved to {path}[/dim]")
