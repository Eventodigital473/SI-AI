# SI-AI — Futures-only Release Handoff

Updated: 2026-11-17

## Active project scope

SI-AI is now **Binance USD-M USDT perpetual Futures only**. Spot market discovery, Spot scanning, Spot API support, Spot historical-data ingestion, Spot portfolio backtesting, and Spot-specific CI have been removed from the active code path.

Working branch: `feature/futures-only-backtesting`

The earlier branches and `main` are preserved. This migration is isolated on a feature branch and must be reviewed and CI-verified before merge.

## Safety requirements

- SI-AI is a signal provider only. The user manually reviews and executes any trade.
- No automatic Binance order placement, cancellation, amendment, or leverage-setting.
- Public market data only; no private API keys or account endpoints.
- Reference wallet: 100 USDT.
- Risk budget: 0.5% per trade (0.50 USDT).
- Margin allocation cap: 20% (20 USDT).
- Recommended Futures leverage: conservative 1x.
- Do not call the strategy profitable unless the fail-closed evidence gate passes with valid Futures-specific costs and risk modelling.

## Futures market policy

- Binance USD-M linear USDT-settled perpetual contracts only.
- Minimum 24h quote volume: 10,000,000 USDT.
- Maximum midpoint-relative spread: 0.15%.
- Target universe: 50; configurable hard maximum: 100; minimum: 15.
- BTC, ETH, BNB, and SOL are prioritized only if they pass identical eligibility filters.
- Inactive, stablecoin-base, wrapped, leveraged-token, missing-quote, and invalid/crossed-book contracts are rejected.
- Universe refresh: 15 minutes. Failed refreshes preserve the last-known-good set.

## Signal and execution behaviour

- Timeframes: 15m, 1h, 4h, 1d.
- 1h provides the entry setup; 4h confirms direction; the full requested timeframe set must be available.
- BUY is a Futures long setup; SELL is a Futures short setup; otherwise WAIT.
- Entry/SL/TP and net reward-risk checks are applied before a signal is actionable.
- No order is sent to Binance.

## Backtesting

Run:

```bash
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

Repeat `--symbol` to evaluate more contracts, for example:

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT --symbol ETH/USDT --symbol SOL/USDT
```

The runner downloads 15m, 1h, 4h, and 1d closed Futures OHLCV, saves datasets with SHA-256 integrity checks, and runs the production-equivalent multi-timeframe signal callback through chronological holdout and expanding walk-forward evaluation.

Each symbol currently has a separate reference-equity evaluation. This is not a shared-wallet portfolio simulation and should not be interpreted as aggregate portfolio performance.

### Certification blocker

The backtest engine includes OHLCV, taker fees, adverse slippage, next-candle-open fills, conservative same-bar stop handling, and an optional constant-rate funding proxy. It does not yet include:
1. Timestamped historical Binance Futures funding-rate events.
2. Exchange-specific maintenance-margin tiers and liquidation-price / liquidation-event modelling.

The profitability gate therefore remains **INCONCLUSIVE** for Futures until both are implemented and validated. Positive OHLCV-only metrics do not override this blocker.

## Termux setup

Use a separate new directory. Never overwrite an existing checkout or local state:

```bash
pkg update -y
pkg install -y git python termux-api
cd "$HOME"
git clone --branch feature/futures-only-backtesting --single-branch https://github.com/Eventodigital473/SI-AI.git SI-AI_FUTURES
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
python -m pip install -r requirements.txt
python -m pip check
python -m compileall -q .
python -m pytest -q
```

### Safe one-cycle preview

```bash
python si_ai_scanner.py --once --dry-run
```

This uses public market data, prints/logs signal previews, sends no notification, and places no order.

### Continuous scanner

```bash
python si_ai_scanner.py --interval 120
```

Stop with Ctrl+C. Install the Android Termux:API companion app and grant notification permission separately before testing notifications.

### Local API

```bash
python main.py
```

Local endpoints: `http://127.0.0.1:5000/status` and `http://127.0.0.1:5000/api/config`.

## Historical Spot result — archived, not active strategy evidence

The retired Spot portfolio test reported 15 OOS trades, 26.67% win rate, profit factor 0.736373, net P&L -0.739271 USDT, and profitability gate FAIL. That Spot implementation has been removed from the active codebase. This result is retained here only for audit history; it is not a Futures result and must not be reused as Futures evidence.

## Remaining release checks

1. Run GitHub Actions on this Futures-only branch; require dependency check, compileall, and all pytest tests to pass.
2. Review any failures and correct them before treating the branch as backtesting-ready.
3. Sync to Termux without overwriting local files, then run the same checks on-device.
4. Run the public Futures dry-run and inspect bookTicker matching, valid bid/ask counts, spread-qualified counts, and selected contract count.
5. Confirm Android notifications on the actual device.
6. Implement and validate historical funding and liquidation/maintenance-margin modelling before attempting Futures profitability certification.

No device validation or Futures profitability certification is claimed by this handoff until evidence is recorded in a new checkpoint.
