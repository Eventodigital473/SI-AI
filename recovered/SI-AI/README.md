# SI-AI

SI-AI is a market-analysis and signal-generation project. It uses public Binance market data through `ccxt`, dynamically discovers eligible USDT spot and USD-M perpetual markets, analyzes selected coins across configured timeframes, and exposes a Flask API plus a Termux scanner.

## Dynamic coin universe

- Discovers each market independently from Binance's active USDT-quoted spot and linear USD-M perpetual markets.
- Selects up to 100 coins per market, with a 15-coin minimum required before the scanner will scan that market. The target universe size is 50.
- Ranks candidates by 24-hour quote volume; minimum quote-volume filters are 5 million USDT for spot and 10 million USDT for futures.
- Rejects markets with a spread above 0.15%, missing bid/ask/volume data, inactive market metadata, stablecoin base assets, wrapped assets, and leveraged-token naming patterns.
- SOL, BNB, BTC, and ETH are prioritized only if they pass the same eligibility filters.
- Refreshes the universe every 15 minutes. A failed refresh preserves the last-known-good list; a market with fewer than 15 eligible coins is skipped rather than padded with unqualified symbols.
- The `/api/config` endpoint reports selected symbols by market, eligibility status, and filter settings.

These are initial configurable screening thresholds, not a guarantee of liquidity or profitable execution. Public market data is used only; no private keys or order endpoints are required.

## Safety model

- Signal provider only: this project is intended to report signals for manual review.
- It must not place Binance orders automatically.
- Risk values are paper estimates based on the constants in `SI_AI_smc.py`, not account-specific balances or exchange-confirmed liquidation calculations.
- Review all signals independently before making any trading decision.

## Project files

- `SI_AI_smc.py` — market discovery, public market data, indicators, SMC analysis, and paper risk calculations.
- `si_ai_scanner.py` — multi-timeframe scanner and Termux notifications.
- `main.py` — Flask API.
- `market.py`, `smc.py` — additional source modules retained from the supplied project.
- `test_smc_risk.py`, `test_main_api.py`, `test_dynamic_universe.py` — risk, API, and dynamic-universe tests.

## Dependencies

Install with:

```bash
python -m pip install -r requirements.txt
```

## Tests

```bash
python -m pytest -q
```

The supplied archive was syntax-compiled successfully during packaging. Full test execution still needs the dependencies above installed.

## Secrets

Do not commit Binance API keys, Telegram tokens, passwords, `.env` files, or private account data. This package does not include runtime state, logs, or historical backup files.


## Backtesting and profitability evidence

`backtesting.py` provides an offline OHLCV evaluation engine for the current SI-AI candle-analysis function or a test callback.

- A signal is calculated only from candles available at that candle close; entry is at the next candle open.
- If stop-loss and take-profit are both touched in one candle, stop-loss is assumed first.
- Fees and adverse slippage are charged on entry and exit; the assumptions are included in every report.
- Position sizing uses a configurable risk percentage and the configured notional cap.
- Reports include win rate, gross profit/loss, profit factor, net P&L, expectancy, max drawdown, trade-based Sharpe, trade ledger, and SHA-256 of the exact OHLCV input.
- Chronological holdout and expanding-window walk-forward evaluators keep out-of-sample periods in time order.
- Futures funding can be approximated only when an explicit per-8-hour rate is supplied. This is a constant-rate proxy, not historical exchange funding data. Liquidation is not modelled.
- No-trade or insufficient-evidence results are marked `INCONCLUSIVE`; positive backtest results are explicitly in-sample or out-of-sample evidence, never a promise of future profit.

Run the offline tests with `python -m pytest -q`. These tests do not establish live profitability. A proper profitability review still requires representative historical data, historical funding series for futures, out-of-sample and walk-forward evidence, and later paper-trading observation. SI-AI remains signal-only; automatic orders are disabled.


## Profitability certification gate

`profitability_gate.py` is a separate fail-closed evidence gate. It requires at least 100 chronological out-of-sample trades, positive net P&L and expectancy after costs, profit factor of at least 1.20, maximum drawdown no greater than 15%, and three sequential walk-forward folds with at least 20 trades and positive net P&L each. These are minimum review thresholds, not performance promises.

Missing metrics or insufficient samples return `INCONCLUSIVE`; observed threshold breaches return `FAIL`. Futures certification additionally requires timestamped historical funding events and an explicit liquidation/maintenance-margin model. The current backtester does not yet supply those two futures models, so futures profitability cannot be certified by this gate. No real historical profitability result is claimed. Run only the focused gate tests with `python -m pytest -q test_profitability_gate.py` when validating this addition; the previously completed 35-test evidence remains historical evidence for its original commit.
