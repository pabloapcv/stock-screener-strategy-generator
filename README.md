# Stock Screener & Strategy Generator

**A systematic equity screening pipeline with options strategy generation, paper trading, and daily automation.**

Built as a quant research project: multi-stage funnel filtering, composite factor scoring, options P&L modeling, and walk-forward paper trading on live market data.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/pabloapcv/stock-screener-strategy-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/pabloapcv/stock-screener-strategy-generator/actions/workflows/ci.yml)

---

## Why this project exists

Institutional traders don't use a single screener. They run a **pipeline** — each stage narrows the universe for a different purpose. This project automates that workflow in Python:

```
~500 stocks → Growth screen → Momentum screen → Options liquidity → Technical entry → Ranked trades
```

It demonstrates skills relevant to **quant research** and **systematic trading** roles: signal engineering, portfolio construction, options mechanics, data pipelines, and production-style automation.

## Skills demonstrated

| Area | Implementation |
|------|----------------|
| **Quant research** | Multi-factor screening, weighted scoring, regime-based strategy selection |
| **Options** | Chain analysis, spread construction, mark-to-market P&L, breakeven math |
| **Data science** | pandas, feature engineering (SMA, RSI, rel volume), batch ETL from APIs |
| **Engineering** | Modular CLI, YAML config, rate-limit handling, cron automation, email reports |
| **Risk** | Position sizing, stop/target rules, max portfolio exposure per trade |

## Quick start

```bash
git clone https://github.com/pabloapcv/stock-screener-strategy-generator.git
cd stock-screener-strategy-generator

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional: API keys + email

python main.py daily   # full morning workflow
python main.py paper status
```

## Pipeline architecture

```
~500 Stocks (S&P 500 + NASDAQ 100)
      │
      ▼  Stage 1: Institutional Growth      (~30–80 stocks)
      ▼  Stage 2: Analyst Momentum          (~15–20 stocks)
      ▼  Stage 3: Options Liquidity         (~8 stocks)
      ▼  Stage 4: Technical Entry           (2–5 trades)
      ▼  Composite Scoring + Strategy Generator
      ▼  Paper Trading + Daily Report
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for quant methodology detail.

## CLI commands

| Command | Description |
|---------|-------------|
| `python main.py run` | Full 4-stage screening pipeline |
| `python main.py ideas` | Generate options trade ideas with P&L calculator |
| `python main.py explain NVDA` | Full breakdown for one ticker |
| `python main.py paper open-ideas` | Paper trade top ideas ($100k virtual portfolio) |
| `python main.py paper status` | Live mark-to-market P&L |
| `python main.py daily` | Morning automation: screen → ideas → paper → report |

```bash
python main.py diagnose --tickers NVDA,META    # which filters block a name
python main.py score --tickers NVDA,TER        # composite factor score
python main.py daily --email                   # email morning report
```

## Composite scoring model

```
Score = 25% Analyst Rating + 20% EPS Revision + 20% Revenue Growth
      + 15% Technical Momentum + 10% Relative Volume + 10% Options Liquidity
```

## Options strategies (regime-based)

| Market setup | Low IV | High IV |
|--------------|--------|---------|
| Breakout | Weekly long call | Bull put credit spread |
| Pullback | Bull call spread | Cash-secured put |
| Trend | Long call | Bull put credit spread |

Each idea includes strikes, premiums, max P&L, breakeven, and 1/3/5 contract profit scenarios.

## Paper trading

Virtual $100,000 portfolio with:
- Live Yahoo Finance marks (stock + option mids)
- Auto-exit on stop/target
- Position sizing rules (max 10% per trade)
- Full audit trail in `paper/portfolio.json` (local, gitignored)

## Daily automation

```bash
# Weekdays 8 AM via cron
./scripts/morning.sh --quiet
```

Generates ideas, opens paper trades, saves report to `output/morning_YYYYMMDD.txt`, optional email.

## Tech stack

Python · pandas · numpy · yfinance · ta · PyYAML · Rich · python-dotenv

**Data:** Yahoo Finance (prices, fundamentals, options), NASDAQ API (index constituents)

## Project structure

```
├── main.py                 # CLI entry point
├── config/screeners.yaml   # All thresholds (config-driven research)
├── scripts/morning.sh      # Cron wrapper
├── docs/
│   ├── ARCHITECTURE.md
│   ├── METHODOLOGY.md
│   └── samples/
└── src/
    ├── pipeline.py         # Funnel orchestrator
    ├── screeners/          # 4 screening stages
    ├── scoring/            # Composite factor model
    ├── ideas/              # Strategy generator + P&L
    ├── paper/              # Paper trading engine
    ├── daily/              # Morning automation
    └── data/               # Fetchers, universe, options
```

## Roadmap

- [ ] Historical backtest with point-in-time fundamentals
- [ ] Polygon.io / IBKR data adapters
- [ ] ML ranker (XGBoost) replacing linear composite score
- [ ] Slippage and transaction cost model
- [ ] Streamlit dashboard for portfolio analytics

## Disclaimer

This is a research and education project. Not financial advice. Paper trading uses delayed free data — verify all prices in your broker before live trading.

## Author

**Pablo Pena** — Quant & data science portfolio project

- GitHub: [@pabloapcv](https://github.com/pabloapcv)

## License

MIT — see [LICENSE](LICENSE)
