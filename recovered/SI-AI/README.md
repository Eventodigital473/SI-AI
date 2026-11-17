# SI-AI

SI-AI is a market-analysis and signal-generation project. It uses public Binance market data through `ccxt`, dynamically discovers eligible USDT spot and USD-M perpetual markets, analyzes selected coins across configured timeframes, and exposes a Flask API plus a Termux scanner.

## Dynamic coin universe

- Discovers each market independently from Binance's active USDT-quoted spot and linear USD-M perpetual markets.
- Targets 50 selected coins per market, with a 15-coin minimum required before the scanner will scan that market. 100 is the configurable hard maximum; priority assets replace the lowest-ranked eligible candidate rather than expanding the target list.
- Ranks candidates by 24-hour quote volume; minimum quote-volume filters are 5 million USDT for spot and 10 million USDT for futures.
- Rejects markets with a spread above 0.15%, missing bid/ask/volume data, inactive market metadata, stablecoin base assets, wrapped assets, and leveraged-token naming patterns.
- SOL, BNB, BTC, and ETH are prioritized only if they pass the same eligibility filters.
- Refreshes the universe every 15 minutes. A failed refresh preserves the last-known-good list; a market with fewer than 15 eligible coins is skipped rather than padded with unqualified symbols.
- The `/api/config` endpoint reports selected symbols by market, eligibility status, and filter settings.

These are initial configurable screening thresholds, not a guarantee of liquidity or profitable execution. Public market data is used only; no private keys or order endpoints are required.

## Safety model

- Signal provider only: this project is intended to report signals for manual review.
- It must not place Binance orders automatically.
- Risk values use a $100 USDT reference wallet, 0.5% maximum risk budget per trade, and a 20% margin allocation cap ($20). The sizing cap is applied to notional at the configured leverage.
- Futures leverage is conservatively fixed at 1x; higher leverage is not recommended until an exchange-specific maintenance-margin and liquidation model is validated. Spot trading has no leverage.
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

Missing metrics or insufficient samples return `INCONCLUSIVE`; observed threshold breaches return `FAIL`. Missing or undersized walk-forward fold evidence also remains `INCONCLUSIVE`. Futures certification additionally requires timestamped historical funding events and an explicit liquidation/maintenance-margin model. The current backtester does not yet supply those two futures models, so futures profitability cannot be certified by this gate. No real historical profitability result is claimed. Run the full suite with `python -m pytest -q`.


## $100 reference wallet and 20% margin policy

- Reference wallet: **100 USDT** (static planning value; SI-AI does not read the user's Binance wallet).
- Margin allocation cap: **20% = 20 USDT** per signal, not a required amount to spend.
- Risk budget: **0.5% = 0.50 USDT** maximum planned loss per trade before any unmodelled execution differences; actual position size is the lower of the risk-based size and the margin-cap size.
- Futures leverage recommendation: **1x only** until historical funding, exchange maintenance-margin tiers, and liquidation modelling are validated. This deliberately avoids guessing higher leverage.
- Spot: leverage is not applicable. Position notional is still capped by the 20 USDT allocation.
- Alerts include the coin name when known plus exact Binance symbol, market, BUY/SELL/WAIT, 1h entry setup timeframe, 4h confirmation timeframe, last-closed-candle entry reference, SL, TP1/TP2/TP3 reference levels, reward/risk, futures leverage, and estimated margin usage. TP1 (1R) and TP2 (1.5R) are reference levels; TP3 is the engine target. SI-AI does not execute partial exits.
- The entry reference is not a guaranteed fill; the user must check the live price before manual execution. Unknown coin names are labelled honestly as unknown while preserving the exact symbol. Spot SELL is an exit signal, never a short entry.
- Stale/future-dated candles are rejected. Multi-timeframe API results are forced to WAIT if any requested timeframe fails; partial data is marked INCOMPLETE.
- WAIT notifications are sent only when a previously actionable BUY/SELL state changes to WAIT, avoiding an initial flood of hundreds of WAIT notifications.
- User manually decides and places trades. No automatic Binance order placement is implemented.


## Public historical OHLCV research data

Use `historical_data.py` to download public Binance spot or linear USDT perpetual OHLCV candles for a selected symbol/timeframe. It paginates with a guarded cursor, excludes incomplete candles, checks active market metadata, and writes a local JSON dataset with a SHA-256 checksum. Dataset files are stored under `data/historical/` and are git-ignored.

Example CLI shape (timestamps are Unix milliseconds; end is exclusive):

```bash
python historical_data.py --market SPOT --symbol BTC/USDT --timeframe 1h --start-ms 1700000000000 --end-ms 1710000000000
```

Load and verify a saved dataset with `load_dataset(path)` before passing its candles to `backtesting.run_backtest`, `evaluate_chronological_validation`, or `evaluate_walk_forward`. The downloader uses public market-data endpoints only; it does not request API keys or place orders. Historical data is not a profitability guarantee.


Run chronological holdout, expanding-window walk-forward evaluation, and the fail-closed profitability gate on a verified local dataset:

```bash
python historical_backtest.py --dataset data/historical/spot/BTC-USDT_1h_START_END.json
```

The runner saves a JSON report under `data/reports/` by default. Insufficient samples remain INCONCLUSIVE. Futures certification remains INCONCLUSIVE without historical funding and liquidation/maintenance-margin evidence. Synthetic test fixtures are used only to test report plumbing; they are not market-performance evidence.


Historical-only downloads may include a currently inactive/delisted market when Binance still retains its market metadata and explicitly marks its status. Live coin-universe discovery remains stricter and includes only markets explicitly marked active. This separation helps avoid silently applying live eligibility rules to historical research.
