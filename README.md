# SI-AI — Binance USD-M Futures Only

SI-AI is a signal-generation and market-analysis assistant for **Binance USD-M USDT perpetual Futures only**. Spot scanning, Spot API modes, and Spot backtesting are not part of the active project.

- Public exchange market data only; no private account keys or order endpoints.
- Signal provider only: all trades are manually reviewed and executed by the user.
- No automatic order placement, cancellation, amendment, or leverage-setting.
- 15m, 1h, 4h, and 1d closed-candle analysis.
- Dynamic Futures universe: 10M USDT minimum 24h quote volume, maximum 0.15% midpoint-relative spread, 50-symbol target, 15-symbol minimum, 100-symbol hard ceiling.
- Risk policy: 0.5% risk per trade, 20% margin allocation cap, conservative 1x Futures leverage.
- Historical backtesting uses public OHLCV and includes fee/slippage assumptions, next-open fills, conservative same-bar stop handling, chronological holdout, and walk-forward evaluation.
- Futures profitability certification remains INCONCLUSIVE until timestamped historical funding events and exchange-specific maintenance-margin/liquidation modelling are implemented.

## Termux setup

See [the detailed Futures-only README](recovered/SI-AI/README.md) for install, scanner, API, and backtesting instructions.

## Backtest

```bash
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

The old Spot portfolio experiment is retired. Its archived historical result is not evidence for the Futures strategy.
