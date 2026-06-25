# Quantitative Methodology

This document describes the systematic approach behind the screener — useful for interviews and portfolio reviews.

## Problem framing

**Objective:** Narrow a large equity universe (~500 liquid US large-caps) to 2–5 high-conviction swing trade candidates per day, with explicit risk parameters and options execution quality.

**Horizon:** 2–6 week swing trades (medium-term institutional accumulation thesis).

**Constraints:**
- Liquid names only (volume, market cap, options OI)
- Defined risk per position (stops, max loss on spreads)
- Portfolio-level position sizing (max 10% capital per trade)

## Pipeline as a sequential filter

Each stage applies **hard AND filters** — mimicking how discretionary portfolio managers narrow a universe before sizing:

| Stage | Economic intuition | Key signals |
|-------|-------------------|-------------|
| 1. Institutional Growth | Quality + trend + institutional footprint | Growth, ROE, SMA stack, RSI, rel volume |
| 2. Analyst Momentum | Information diffusion / estimate revisions | 1W/1M performance, rel volume, growth |
| 3. Options Liquidity | Execution cost minimization | OI, spread, weekly expirations |
| 4. Technical Entry | Timing | Pullback, breakout, RS vs SPY, volume |

Funnel design reduces false positives from any single signal dominating.

## Composite scoring model

Survivors are ranked with a weighted linear model (0–100):

```
Score = 0.25 × Analyst Rating
      + 0.20 × EPS Revision Trend
      + 0.20 × Revenue Growth
      + 0.15 × Technical Momentum
      + 0.10 × Relative Volume
      + 0.10 × Options Liquidity
```

Features are min-max normalized to [0, 1] before weighting. This separates **ranking** (soft) from **screening** (hard gates).

## Options strategy selection

Strategy maps to **setup regime × volatility regime**:

| Setup | Low IV (buy) | High IV (sell) |
|-------|--------------|----------------|
| Breakout | Weekly long call | Bull put spread |
| Pullback | Bull call spread | Cash-secured put |
| Trend | Long call | Bull put spread |

IV proxy uses median chain implied vol (Yahoo Finance). Production systems would use IV rank from historical vol surface.

## Paper trading & attribution

Paper portfolio tracks:
- Entry marks (stock + option mids at open)
- Mark-to-market P&L (live option marks, not just intrinsic)
- Auto-exit on stop/target (simulates systematic risk rules)
- Realized vs unrealized attribution

Enables walk-forward evaluation of the signal pipeline without broker integration.

## Data limitations (honest assessment)

| Limitation | Impact | Production fix |
|------------|--------|----------------|
| Yahoo Finance delay | ~15 min stale | Polygon, IBKR |
| No true IV rank history | Rough IV proxy | ORATS, CBOE |
| No analyst revision feed | Momentum proxy only | FactSet, Bloomberg |
| Batch daily run | No intraday | Streaming + event-driven |

## Skills demonstrated

- **Python:** pandas, concurrent fetching, CLI design, modular architecture
- **Quant:** multi-factor screening, scoring, options P&L, position sizing
- **Data engineering:** batched API calls, rate-limit handling, config-driven pipelines
- **Systems:** cron automation, email reporting, JSON audit trail

## Extensions for production

1. Backtest module (historical point-in-time fundamentals)
2. Polygon/IBKR data adapters
3. Kelly / vol-target position sizing
4. ML ranker replacing linear composite score
5. Execution simulation with slippage model
