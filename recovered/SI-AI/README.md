# SI-AI — Binance USD-M Futures Only

SI-AI is a public-market-data analysis and signal-generation system for **Binance USD-M USDT perpetual Futures only**. Spot market discovery, Spot scanning, Spot API modes, and Spot backtesting have been removed from the active project.

## Safety model

- Signal provider only. The user manually reviews and executes trades on Binance.
- No automatic order placement, cancellation, amendment, or leverage-setting.
- The retired legacy 10%-risk/high-leverage paper planner is disabled; active policy remains 0.5% risk, 20% margin allocation, and recommended 1x leverage.
- Public exchange data only. No private account keys or order endpoints are required.
- Reference wallet: 100 USDT; per-trade risk budget: 0.5% (0.50 USDT).
- Margin allocation cap: 20% (20 USDT); recommended Futures leverage remains 1x.
- A signal is not a guarantee of execution or profit. Verify current price, contract rules, and margin requirements before any manual trade.

## Futures universe

- Binance USD-M linear USDT-settled perpetual contracts only.
- Minimum 10 million USDT 24-hour quote volume.
- Maximum midpoint-relative spread: 0.15%.
- Target 50 symbols, hard maximum 100; at least 15 eligible contracts are required before scanning.
- BTC, ETH, BNB, and SOL are prioritized only when they pass the same eligibility filters.
- Inactive contracts, stablecoin bases, wrapped assets, leveraged tokens, missing quotes, and invalid/crossed books are excluded.
- Universe refresh interval: 15 minutes. Failed refreshes preserve the last-known-good universe; no symbols are fabricated.

## Timeframes and signals

The scanner uses 15m, 1h, 4h, and 1d closed candles. The 1h timeframe supplies the entry setup, 4h confirms direction, and all requested timeframes must be available before an actionable signal is emitted. BUY and SELL represent Futures long and short setups; otherwise the system reports WAIT.

## Install in Termux

For the complete safe clone, install, CI/device smoke-test, notification, and 180-day Futures backtest sequence, follow [`TERMUX_FINAL_TEST_RUNBOOK.md`](TERMUX_FINAL_TEST_RUNBOOK.md). The runbook uses a separate validation folder and preserves the existing checkout.

Install Termux and its Android companion app from trusted sources, then run:

```bash
pkg update -y
pkg install -y git python python-cryptography clang termux-api
cd "$HOME"
git clone --branch main --single-branch https://github.com/Eventodigital473/SI-AI.git SI-AI_FUTURES
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
python -m pip install -r requirements-termux.txt
python -m pip install --no-deps "ccxt==4.5.93"
python -c "import ccxt, requests, certifi, cryptography, typing_extensions, flask, pytest; print('SI-AI Termux dependencies OK; CCXT', ccxt.__version__)"
python -m compileall -q .
python -m pytest -q
```

If the destination folder already exists, do not overwrite it. Choose a new folder or safely inspect the existing checkout first. Android notification permission must be granted to Termux:API separately.

The `main`-branch clone above is the final-install instruction only after PRs #1–#12 have been merged in dependency order into the recovery branch **and** a final recovery-to-`main` integration pull request has been merged. Do not use it before that complete sequence. For the current existing checkout, wait for the final merge/refresh instructions. The Termux profile installs CCXT's synchronous public REST client without its unused async/accelerator extras; Termux supplies `python-cryptography`. Do not run `pip check` against this intentionally minimal CCXT install because CCXT declares optional async/accelerator packages that SI-AI does not import. The standard `requirements.txt` remains the full desktop/CI profile.

### Signal notification appearance

- BUY: green 🟢 title marker, high-priority notification, green LED request, short vibration, and sound.
- SELL: red 🔴 title marker, high-priority notification, red LED request, a distinct longer vibration, and sound.
- WAIT after a previously active signal: neutral ⚪ title marker, no LED request, no vibration, and no sound.
- LED behavior depends on the phone having a notification LED and on Android/OEM notification settings. The colored title marker is the visual fallback; Android does not let Termux force colored/glowing notification text.

### Termux:Widget shortcuts

The project includes Start, Stop, Dry Run, and Check shortcuts. After cloning, install them with:

```bash
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
bash termux-widget/install-shortcuts.sh
```

Then open/refresh Termux:Widget. Run **SI-AI Check** first: it performs an offline preflight of Python/dependencies, Futures-only settings, risk limits, Widget shortcuts, and Termux:API command availability. Start runs the offline safety preflight before launching the 120-second scanner in the background; Stop sends a graceful termination request to the scanner started by that shortcut; Dry Run performs one preview cycle without sending trade alerts or placing orders. The installer preserves existing shortcuts and installs only missing ones. To replace an older SI-AI shortcut, move/rename it yourself first, then rerun the installer. The shortcuts recognize the existing `~/SI-AI_FINAL/recovered/SI-AI` path as well as the documented fresh-install path.

## Run modes

### One-cycle public-data preview (no notifications or orders)

```bash
cd "$HOME/SI-AI_FUTURES/recovered/SI-AI"
python si_ai_scanner.py --once --dry-run
```

### Test Android notifications (no market requests or orders)

```bash
python si_ai_scanner.py --test-notifications
```

This sends three clearly labelled TEST ONLY notifications (BUY, SELL, WAIT) so you can verify Android permission, title colors, sound/vibration, and whether the device supports LED behavior. These are not trading signals and do not contact Binance.

### Continuous scanner with Android notifications

```bash
python si_ai_scanner.py --interval 120
```

Stop with Ctrl+C. Confirm notification permission and behavior on the actual phone.

### Local API

```bash
python main.py
```

Open `http://127.0.0.1:5000/status` and `http://127.0.0.1:5000/api/config` locally.

## Liquidation-price model (isolated one-way estimate)

The project includes a fail-closed Binance USD-M isolated liquidation-price calculator in `liquidation_model.py`. It uses Binance's one-way liquidation formula with the symbol's maintenance-margin rate and maintenance amount, and resolves the maintenance tier using the calculated liquidation notional. It refuses stale (over 24 hours), future-dated, wrong-symbol, incomplete, overlapping, or non-contiguous tier snapshots, and rejects leverage above the selected entry tier maximum.

To calculate a live alert estimate, place a current, verified, symbol-specific maintenance bracket snapshot at:

`data/liquidation_brackets/BASE-USDT.json` (for example, the filename for BTC/USDT is `BTC-USDT.json`).

The JSON object must contain:
- `source`: exactly `BINANCE_USDM_LEVERAGE_BRACKET`
- `symbol`: canonical symbol such as `BTC/USDT`
- `retrieved_at`: timezone-aware ISO-8601 UTC timestamp
- `tiers`: ordered tier objects with `notional_floor`, `notional_cap` (null only for the final tier), `maintenance_margin_rate`, `maintenance_amount`, and `max_leverage`

Copy the exact current tier values for that contract from Binance's USD-M Futures leverage/margin information. Do not reuse BTC values for another contract or invent a generic maintenance rate. Refresh the snapshot at least every 24 hours. If no valid snapshot is present, the alert explicitly says liquidation is NOT CERTIFIED rather than guessing.

**Scope limitation:** this calculator is for one-way isolated margin only. It uses the paper margin estimate as isolated wallet balance; the actual Binance isolated wallet balance, margin mode, leverage, mark price, funding/fee adjustments and exchange display must be checked manually. Cross margin, hedge mode, other positions, auto-add margin and liquidation fees are not modelled. A 1x long may have no positive liquidation threshold in the idealized formula; that is not a guarantee against liquidation.

The public Futures backtest runner now also archives Binance USD-M 1h historical mark-price candles from `/fapi/v1/markPriceKlines` into a separate integrity-checked dataset. These are distinct from last-trade OHLCV and are included in the report manifest with a SHA-256 digest. The mark-price data is currently captured for research only: liquidation events are not yet simulated because historical, timestamp-matched maintenance-tier snapshots are not available through the public market-data endpoint. Do not substitute today's maintenance tiers for historical tiers. The profitability gate therefore remains INCONCLUSIVE. No private API key, account endpoint or order permission is added.

## Futures historical backtesting

The runner downloads public Binance USD-M OHLCV history for 15m, 1h, 4h, and 1d, verifies each saved dataset, then evaluates the production multi-timeframe signal logic using chronological holdout and walk-forward windows. Live and saved candle series are also required to have exact timeframe spacing; missing or irregular candles are rejected before analysis/backtesting.

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

Add more symbols by repeating `--symbol`:

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT --symbol ETH/USDT --symbol SOL/USDT
```

Supported history window: 120–730 days. Each symbol is currently evaluated with its own reference equity; the reports are **not** a shared-wallet multi-symbol portfolio simulation. Local datasets are stored under `data/historical/`; reports are stored under `data/reports/`. These paths are git-ignored.

### Timestamped funding history and Futures backtest

The public backtest runner now downloads Binance USD-M historical funding events alongside the four OHLCV timeframes. Each funding event retains Binance's associated settlement `markPrice`; the engine applies signed funding cashflows using the position quantity and the event-specific mark price. Positive funding is a cost to longs and a credit to shorts; negative funding reverses those directions. The funding dataset is range-checked, symbol-checked, SHA-256 verified, and included in the report manifest.

Run the standard workflow (funding is downloaded automatically):

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

The lower-level funding downloader is also available:

```bash
python funding_data.py --market FUTURES --symbol BTC/USDT --start-ms START_MS --end-ms END_MS --output data/historical/funding/BTC-USDT.json
```

The lower-level multi-timeframe runner accepts the verified dataset with `--funding-dataset PATH`. Funding events exactly tied to a trade's entry or exit timestamp are conservatively charged without assuming a funding credit and are flagged as ambiguous. Because OHLCV cannot reveal the exact intrabar exit time, settlements inside a stop/target exit candle are also conservatively included without assuming a credit and flagged as ambiguous. TIME_EXIT includes settlements through candle close; open-time exits stop at the candle open. Any such ambiguity blocks profitability certification.

**Important remaining limitation:** exchange-specific maintenance-margin tiers and liquidation-price/liquidation-fee modelling are not yet implemented. Therefore the profitability gate must remain **INCONCLUSIVE** for Futures, even if net historical metrics look positive. Funding costs are now included, but position sizing still follows the configured 0.5% stop-risk budget and does not guarantee a maximum loss under gaps, funding changes, liquidation, or exchange execution. Do not treat a report as a profitability guarantee or permission for live trading.

## Validation status

GitHub CI verifies dependency consistency, Python compilation, Termux shell syntax, and automated regression tests, including deterministic timestamped funding calculations. CI does not validate live Binance responses from the phone, Android notification permissions/LED hardware, historical liquidation modelling, or profitability. A real device smoke test remains required.

## Project files

- `SI_AI_smc.py` — Futures discovery, market data, SMC analysis, and risk calculations.
- `smc.py` — legacy compatibility shim; delegates to the Futures engine and does not initialize a Spot client.
- `si_ai_scanner.py` — Futures-only multi-timeframe scanner and Termux notifications.
- `main.py` — Futures-only Flask API.
- `historical_data.py` — public Futures last-trade OHLCV download and integrity-checked datasets.\n- `mark_price_data.py` — public Binance USD-M historical mark-price candles and integrity-checked datasets.
- `funding_data.py` — timestamped Binance funding events, exact associated settlement mark prices, and signed funding cashflows.
- `backtesting.py` / `historical_backtest.py` — offline Futures backtesting and evaluation.
- `run_public_futures_backtest.py` — public historical data collection and backtest runner.
- `profitability_gate.py` — fail-closed evidence gate requiring historical funding and validated liquidation modelling for Futures.\n- `test_mark_price_data.py` — mark-price endpoint pagination, validation, and dataset-integrity regression tests.
- `termux_preflight.py` — offline Android/Termux runtime, dependency, Widget, and safety-policy checks.

The previous Spot portfolio experiment is retired and is not part of the active SI-AI codebase. Its historical result is not evidence for the Futures strategy.
