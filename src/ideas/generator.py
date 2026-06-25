"""Generate actionable trading ideas from screened stocks."""

from __future__ import annotations

import logging
from datetime import datetime

from src.config import load_config
from src.data.fetcher import StockData, fetch_universe
from src.data.options import analyze_options
from src.data.options_chain import fetch_options_chain, liquidity_ok
from src.ideas.strategies import (
    TradeIdea,
    bull_call_spread,
    bull_put_spread,
    cash_secured_put,
    long_call,
    stock_swing_trade,
    weekly_momentum_call,
)
from src.scoring.composite import score_stock

logger = logging.getLogger(__name__)

IV_BUY_MAX = 50
IV_SELL_MIN = 50


def _classify_setup(stock: StockData) -> tuple[str, str, str]:
    """Return (setup, direction, conviction)."""
    bullish_signals = sum([
        stock.breakout_from_consolidation,
        stock.pullback_to_sma_20 or stock.pullback_to_sma_50,
        stock.relative_strength_vs_spy,
        stock.price_above_sma_50,
        stock.sma_50_above_sma_200,
    ])
    bearish_signals = sum([
        not stock.price_above_sma_50 and stock.price_above_sma_200 is False,
        stock.rsi is not None and stock.rsi > 70,
    ])

    if stock.breakout_from_consolidation and stock.relative_strength_vs_spy:
        conviction = "high" if stock.relative_volume >= 1.5 else "medium"
        return "breakout", "bullish", conviction

    if stock.pullback_to_sma_50 or stock.pullback_to_sma_20:
        conviction = "high" if stock.price_above_sma_200 else "medium"
        return "pullback", "bullish", conviction

    if stock.relative_strength_vs_spy and stock.price_above_sma_50:
        return "momentum", "bullish", "medium"

    if bullish_signals >= 3:
        return "trend", "bullish", "medium"

    if bearish_signals >= 2:
        return "weakness", "bearish", "low"

    return "neutral", "neutral", "low"


def _stock_levels(stock: StockData, setup: str, direction: str) -> tuple[float, float]:
    """Compute stock target and stop."""
    price = stock.price
    if direction == "bullish":
        if setup == "breakout":
            return price * 1.10, price * 0.97
        if setup == "pullback":
            stop = stock.sma_50 or stock.sma_20 or price * 0.95
            return price * 1.08, min(stop * 0.98, price * 0.96)
        return price * 1.06, price * 0.95
    if direction == "bearish":
        return price * 0.94, price * 1.03
    return price * 1.03, price * 0.97


def _pick_weekly_expiration(expirations: list[str]) -> str | None:
    today = datetime.now().date()
    for exp in expirations:
        try:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if 0 < dte <= 10:
                return exp
        except ValueError:
            continue
    return expirations[0] if expirations else None


def _options_liquid_enough(stock: StockData, min_oi: int = 100) -> bool:
    od = stock.options_details
    return (
        od.get("atm_open_interest", 0) >= min_oi
        or od.get("atm_volume", 0) >= 50
    )


def generate_idea(stock: StockData, config: dict | None = None, force: bool = False) -> TradeIdea | None:
    """Build the best options trade idea for a single stock."""
    config = config or load_config()
    opts_cfg = config.get("screener_3_options_liquidity", {}).get("options", {})
    ideas_cfg = config.get("ideas", {})

    setup, direction, conviction = _classify_setup(stock)
    if direction == "neutral" and conviction == "low" and not force:
        return None
    if direction == "neutral" and force:
        direction, conviction = "bullish", "low"

    target_dte = ideas_cfg.get("default_dte", 21)
    snap = fetch_options_chain(stock.ticker, stock.price, target_dte=target_dte)
    idea: TradeIdea | None = None

    if snap.error and not snap.calls:
        target_pct, stop_pct = (0.08, 0.04) if setup == "breakout" else (0.06, 0.04)
        idea = stock_swing_trade(snap, direction, setup, target_pct, stop_pct)
    else:
        analyze_options(
            stock,
            atm_oi_min=opts_cfg.get("atm_open_interest_min", 1000),
            daily_vol_min=opts_cfg.get("daily_option_volume_min", 500),
            spread_pct_max=opts_cfg.get("bid_ask_spread_pct_max", 0.05),
            require_weekly=False,
        )

        iv = snap.iv_rank_proxy
        use_options = _options_liquid_enough(stock, min_oi=ideas_cfg.get("min_oi_for_ideas", 100))

        if use_options and direction == "bullish":
            if setup == "breakout" and conviction == "high" and snap.has_weekly:
                weekly = _pick_weekly_expiration(snap.expirations)
                if weekly:
                    idea = weekly_momentum_call(snap, weekly)

            if idea is None and iv < IV_BUY_MAX:
                if setup == "pullback":
                    idea = bull_call_spread(snap) or long_call(snap, otm_pct=0.0)
                else:
                    idea = long_call(snap, otm_pct=0.02) or bull_call_spread(snap)

            if idea is None and iv >= IV_SELL_MIN:
                idea = bull_put_spread(snap) or cash_secured_put(snap)

            if idea is None:
                idea = bull_call_spread(snap) or long_call(snap) or cash_secured_put(snap)

        if idea is None:
            target_pct, stop_pct = (0.08, 0.04) if setup == "breakout" else (0.06, 0.04)
            idea = stock_swing_trade(snap, direction, setup, target_pct, stop_pct)

        iv = snap.iv_rank_proxy
        use_options = _options_liquid_enough(stock, min_oi=ideas_cfg.get("min_oi_for_ideas", 100))
        if not use_options and idea.strategy_type != "stock":
            idea.warnings.append("Low options liquidity — verify chain in broker before executing")
        if iv >= IV_SELL_MIN and idea.strategy_type == "debit":
            idea.warnings.append(f"IV rank elevated ({iv:.0f}) — consider credit spreads instead of buying")

    assert idea is not None

    # Enrich with stock context
    target, stop = _stock_levels(stock, setup, direction)
    idea.stock_target = target
    idea.stock_stop = stop
    idea.setup = setup
    idea.direction = direction
    idea.conviction = conviction
    idea.composite_score = score_stock(stock, config.get("scoring", {}).get("weights", {})).composite_score

    # Rationale from signals
    signals = []
    if stock.breakout_from_consolidation:
        signals.append("Breakout from consolidation with volume")
    if stock.pullback_to_sma_50:
        signals.append("Pullback to 50-day SMA support")
    if stock.pullback_to_sma_20:
        signals.append("Pullback to 20-day SMA support")
    if stock.relative_strength_vs_spy:
        signals.append("Outperforming SPY over 1 month")
    if stock.price_above_sma_50 and stock.sma_50_above_sma_200:
        signals.append("Uptrend intact (golden cross)")
    if stock.relative_volume >= 1.2:
        signals.append(f"Elevated relative volume ({stock.relative_volume:.1f}x)")
    if stock.analyst_rating and stock.analyst_rating >= 4.0:
        signals.append(f"Strong analyst consensus ({stock.analyst_rating:.1f}/5)")
    idea.rationale = signals + idea.rationale

    if stock.rsi and stock.rsi > 68:
        idea.warnings.append(f"RSI elevated ({stock.rsi:.0f}) — risk of near-term pullback")

    from src.ideas.pnl import enrich_idea_with_pnl
    return enrich_idea_with_pnl(idea)


def _get_pipeline_candidates(config: dict) -> tuple[list[str], dict[str, StockData]]:
    """Run pipeline silently and return ranked survivor tickers."""
    from src.data.universe import get_combined_universe
    from src.scoring.composite import rank_stocks
    from src.screeners.analyst_momentum import AnalystMomentumScreener
    from src.screeners.institutional_growth import InstitutionalGrowthScreener
    from src.screeners.technical_entry import TechnicalEntryScreener

    sources = config.get("universe", {}).get("sources", ["sp500", "nasdaq100"])
    tickers = get_combined_universe(sources)
    workers = config.get("pipeline", {}).get("parallel_workers", 4)
    stock_data = fetch_universe(tickers, workers=workers)

    stage1 = InstitutionalGrowthScreener(config["screener_1_institutional_growth"]).screen(stock_data)
    narrowed = {t: stock_data[t] for t in stage1.passed if t in stock_data}

    stage2 = AnalystMomentumScreener(config["screener_2_analyst_momentum"]).screen(narrowed)
    narrowed = {t: stock_data[t] for t in stage2.passed if t in stock_data}

    stage4 = TechnicalEntryScreener(config["screener_4_technical_entry"]).screen(narrowed)
    candidates = {t: stock_data[t] for t in stage4.passed if t in stock_data}
    if not candidates:
        candidates = {t: stock_data[t] for t in stage2.passed if t in stock_data}
    if not candidates:
        candidates = {t: stock_data[t] for t in stage1.passed if t in stock_data}

    weights = config.get("scoring", {}).get("weights", {})
    top_n = config.get("pipeline", {}).get("top_n_final", 20)
    ranked = rank_stocks(candidates, weights, top_n=top_n)
    return [r.ticker for r in ranked], stock_data


def generate_ideas(
    tickers: list[str] | None = None,
    from_pipeline: bool = True,
    max_ideas: int = 10,
    config: dict | None = None,
) -> list[TradeIdea]:
    """Generate trade ideas for tickers or pipeline survivors."""
    config = config or load_config()

    if tickers is None and from_pipeline:
        tickers, stocks = _get_pipeline_candidates(config)
    else:
        tickers = tickers or []
        stocks = fetch_universe(tickers)

    ideas: list[TradeIdea] = []
    explicit = tickers is not None and len(tickers) > 0
    for ticker in tickers:
        if ticker not in stocks:
            continue
        idea = generate_idea(stocks[ticker], config, force=explicit)
        if idea:
            ideas.append(idea)

    conviction_order = {"high": 3, "medium": 2, "low": 1}
    ideas.sort(
        key=lambda i: (conviction_order.get(i.conviction, 0), i.composite_score),
        reverse=True,
    )
    return ideas[:max_ideas]
