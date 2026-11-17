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

Install Termux and its Android companion app from trusted sources, then run:

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

If the destination folder already exists, do not overwrite it. Choose a new folder or safely inspect the existing checkout first. Android notification permission must be granted to Termux:API separately.

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

## Futures historical backtesting

The runner downloads public Binance USD-M OHLCV history for 15m, 1h, 4h, and 1d, verifies each saved dataset, then evaluates the production multi-timeframe signal logic using chronological holdout and walk-forward windows.

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

The lower-level multi-timeframe runner accepts the verified dataset with `--funding-dataset PATH`. Funding events exactly tied to a trade's entry or exit timestamp are conservatively charged without assuming a funding credit and are flagged as ambiguous; any such ambiguity blocks profitability certification.

**Important remaining limitation:** exchange-specific maintenance-margin tiers and liquidation-price/liquidation-fee modelling are not yet implemented. Therefore the profitability gate must remain **INCONCLUSIVE** for Futures, even if net historical metrics look positive. Funding costs are now included, but position sizing still follows the configured 0.5% stop-risk budget and does not guarantee a maximum loss under gaps, funding changes, liquidation, or exchange execution. Do not treat a report as a profitability guarantee or permission for live trading.

## Validation status

GitHub CI verifies dependency consistency, Python compilation, Termux shell syntax, and automated regression tests, including deterministic timestamped funding calculations. CI does not validate live Binance responses from the phone, Android notification permissions/LED hardware, historical liquidation modelling, or profitability. A real device smoke test remains required.

## Project files

- `SI_AI_smc.py` — Futures discovery, market data, SMC analysis, and risk calculations.
- `si_ai_scanner.py` — Futures-only multi-timeframe scanner and Termux notifications.
- `main.py` — Futures-only Flask API.
- `historical_data.py` — public Futures OHLCV download and integrity-checked datasets.
- `funding_data.py` — timestamped Binance funding events, exact associated settlement mark prices, and signed funding cashflows.
- `backtesting.py` / `historical_backtest.py` — offline Futures backtesting and evaluation.
- `run_public_futures_backtest.py` — public historical data collection and backtest runner.
- `profitability_gate.py` — fail-closed evidence gate requiring historical funding and liquidation modelling for Futures.
- `termux_preflight.py` — offline Android/Termux runtime, dependency, Widget, and safety-policy checks.

The previous Spot portfolio experiment is retired and is not part of the active SI-AI codebase. Its historical result is not evidence for the Futures strategy.
