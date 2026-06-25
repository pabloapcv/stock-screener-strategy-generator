"""Morning run orchestrator."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.config import load_config
from src.daily.email import send_report
from src.daily.report import build_report, report_to_dict
from src.ideas.generator import generate_ideas
from src.ideas.printer import save_ideas
from src.paper.engine import (
    PaperTradingError,
    check_stops_and_targets,
    get_portfolio_summary,
    open_position,
)
from src.paper.store import load_portfolio

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


@dataclass
class MorningRunResult:
    ideas_path: Path | None = None
    report_path: Path | None = None
    report_json_path: Path | None = None
    ideas_count: int = 0
    opened_count: int = 0
    email_sent: bool = False
    report_text: str = ""
    skipped: list[str] = field(default_factory=list)


def run_morning(
    max_ideas: int | None = None,
    max_new_trades: int | None = None,
    open_trades: bool = True,
    send_email: bool | None = None,
    quiet: bool = False,
) -> MorningRunResult:
    """
    Full morning workflow:
      1. Check stops/targets on existing positions
      2. Generate ideas from pipeline
      3. Open new paper trades
      4. Save + email morning report
    """
    load_dotenv()
    config = load_config()
    daily_cfg = config.get("daily", {})

    max_ideas = max_ideas or daily_cfg.get("max_ideas", 10)
    max_new_trades = max_new_trades or daily_cfg.get("max_new_trades", 3)
    if send_email is None:
        send_email = daily_cfg.get("email_enabled", False)

    result = MorningRunResult()

    # Step 1: Auto-close stops/targets
    auto_closed = check_stops_and_targets()
    if auto_closed and not quiet:
        logger.info("Auto-closed %d positions", len(auto_closed))

    # Step 2: Generate ideas
    if not quiet:
        logger.info("Generating ideas from pipeline...")
    ideas = generate_ideas(from_pipeline=True, max_ideas=max_ideas)
    result.ideas_count = len(ideas)

    ideas_path = None
    if ideas:
        ideas_path = save_ideas(ideas)
        result.ideas_path = ideas_path

    # Step 3: Open paper trades for top ideas (skip already-open tickers)
    opened: list = []
    if open_trades and ideas:
        portfolio = load_portfolio()
        open_tickers = {p.ticker for p in portfolio.open_positions}
        opened_count = 0

        for idea in ideas:
            if opened_count >= max_new_trades:
                result.skipped.append(f"Max new trades ({max_new_trades}) reached")
                break
            if idea.ticker in open_tickers:
                result.skipped.append(f"{idea.ticker}: already have open position")
                continue
            try:
                pos, _ = open_position(idea.ticker)
                opened.append((pos, idea))
                open_tickers.add(idea.ticker)
                opened_count += 1
                if not quiet:
                    logger.info("Opened paper trade: %s", idea.ticker)
            except PaperTradingError as e:
                result.skipped.append(f"{idea.ticker}: {e}")

    result.opened_count = len(opened)

    # Step 4: Portfolio summary
    summary = get_portfolio_summary()

    # Step 5: Build and save report
    result.report_text = build_report(
        ideas=ideas,
        opened=opened,
        skipped_opens=result.skipped,
        portfolio_summary=summary,
        auto_closed=auto_closed,
        ideas_path=str(ideas_path) if ideas_path else None,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    report_path = OUTPUT_DIR / f"morning_{ts}.txt"
    report_json_path = OUTPUT_DIR / f"morning_{ts}.json"

    report_path.write_text(result.report_text)
    report_json_path.write_text(json.dumps(
        report_to_dict(
            ideas, opened, result.skipped, summary, auto_closed,
            str(ideas_path) if ideas_path else None,
        ),
        indent=2,
    ))
    result.report_path = report_path
    result.report_json_path = report_json_path

    if not quiet:
        print(result.report_text)

    # Step 6: Email
    if send_email:
        subject = (
            f"Morning Report — ${summary['equity']:,.0f} "
            f"({summary['return_pct']:+.1f}%) — {len(ideas)} ideas"
        )
        result.email_sent = send_report(subject, result.report_text)

    return result
