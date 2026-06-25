# Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI (main.py)                           │
│  run │ score │ diagnose │ explain │ ideas │ paper │ daily        │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐
│ ScreeningPipeline│  │ IdeaGenerator │  │ PaperTradingEngine│
│  4-stage funnel  │  │ + strategies  │  │ + mark-to-market  │
└────────┬─────────┘  └──────┬───────┘  └────────┬─────────┘
         │                   │                    │
         ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Layer (src/data/)                     │
│  universe.py │ fetcher.py │ options.py │ options_chain.py       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    Yahoo Finance (yfinance)
                    NASDAQ API / GitHub CSV
```

## Module map

| Module | Responsibility |
|--------|----------------|
| `src/pipeline.py` | Orchestrates 4 screeners, funnel output, ranking |
| `src/screeners/` | Stage-specific filter logic |
| `src/scoring/composite.py` | Weighted multi-factor score |
| `src/ideas/` | Trade idea generation, P&L calculator, strategies |
| `src/paper/` | Virtual portfolio, MTM, stop/target automation |
| `src/daily/` | Morning cron workflow, report, email |
| `config/screeners.yaml` | All thresholds — no magic numbers in code |

## Data flow (daily run)

1. Load universe (S&P 500 ∪ NASDAQ 100)
2. Batch-fetch OHLCV + fundamentals (50 tickers/request)
3. Compute technicals (SMA, RSI, rel volume, performance)
4. Apply stage 1→4 filters sequentially
5. Score survivors → generate options ideas with chain data
6. Open paper trades (position sizing rules)
7. Persist report to `output/`, optional SMTP email

## Configuration-driven design

All screening thresholds live in YAML. Changing a filter (e.g. `revenue_growth_min: 0.25`) requires no code change — supports rapid iteration during research.
