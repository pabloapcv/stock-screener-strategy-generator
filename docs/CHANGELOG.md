# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-06-25

### Added

- **4-stage screening funnel**: institutional growth → analyst momentum → options liquidity → technical entry
- **Composite factor scoring** with configurable weights in `config/screeners.yaml`
- **Options strategy generator** with regime-based selection and P&L calculator (1/3/5 contracts)
- **Paper trading engine** with mark-to-market P&L and stop/target exits
- **Daily automation** (`python main.py daily`) with morning report and optional email
- **CLI tooling**: `run`, `score`, `diagnose`, `explain`, `ideas`, `paper`
- **Documentation**: architecture, methodology, sample morning report
- **CI**: GitHub Actions lint (Ruff) + stage-1 smoke test

### Data sources

- Yahoo Finance (prices, fundamentals, options)
- S&P 500 constituents (GitHub CSV)
- NASDAQ 100 constituents (NASDAQ API)

### Known limitations

- No historical backtest with point-in-time fundamentals
- Free Yahoo data may be delayed; CI smoke test depends on live API availability
- Email requires Gmail App Password in local `.env`

[0.1.0]: https://github.com/pabloapcv/stock-screener-strategy-generator/releases/tag/v0.1.0
