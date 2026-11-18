# SI-AI — Termux Final Validation Runbook

This runbook tests the consolidated Futures-only signal-provider branch in a **new folder**. It does not overwrite the existing `~/SI-AI_FINAL` checkout or change the global Python package environment.

## Safety and scope

This validation branch includes the scanner's independent net Reward/Risk and position-sizing checks. It is an isolated draft validation candidate; it has not been merged into the integration branch or main.

- Binance USD-M USDT perpetual Futures only. Spot scanning/backtesting is excluded.
- Signal provider only. SI-AI does not place, amend, or cancel orders.
- No Binance API key or private account permission is needed.
- Reference paper wallet: 100 USDT; risk budget 0.5% (0.50 USDT); margin allocation cap 20% (20 USDT); recommended leverage 1x; minimum reward/risk 2:1.
- Historical mark-price candles are collected, but historical liquidation events are not yet simulated because time-matched historical maintenance-tier snapshots are unavailable. Profitability certification remains INCONCLUSIVE. Do not treat backtest returns as proof of profitability or a live-trading green light.

## 1. Install prerequisites and get the exact validation branch

Run each block in Termux. The clone target is intentionally separate; if it already exists, stop rather than overwrite it.

```bash
pkg update -y
pkg install -y git python python-cryptography clang termux-api

cd "$HOME" || exit 1
if [ -e "$HOME/SI-AI_FINAL_VALIDATION" ]; then
  echo "STOP: $HOME/SI-AI_FINAL_VALIDATION already exists; do not overwrite it."
  exit 1
fi

git clone --branch fix/scanner-risk-audit-2026-11-18 --single-branch https://github.com/Eventodigital473/SI-AI.git "$HOME/SI-AI_FINAL_VALIDATION" || exit 1
cd "$HOME/SI-AI_FINAL_VALIDATION/recovered/SI-AI" || exit 1
```

## 2. Install an isolated Termux dependency profile

The validation clone uses its own ignored `.venv`. This prevents pip from changing the global Termux Python environment used by your existing project.

```bash
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-termux.txt
.venv/bin/python -m pip install --no-deps "ccxt==4.5.93"
.venv/bin/python -c "import ccxt, requests, certifi, cryptography, typing_extensions, flask, pytest; print('SI-AI dependencies OK; CCXT', ccxt.__version__)"
```

Do not run `pip check` against this intentionally minimal CCXT install: SI-AI uses CCXT's synchronous public REST client and does not install unused async/accelerator extras.

## 3. Run local static and automated tests

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m pytest -q
.venv/bin/python termux_preflight.py
```

Expected: Python compilation succeeds, all tests pass, and preflight reports no FAIL items. A WARN for a confirmed missing Termux:API companion app means notifications will not work until the companion app is installed from the same signing source as Termux. INFO means Android package inspection was unavailable and the phone-side notification test is still required.

## 4. Test the live public Futures scanner without notifications

```bash
.venv/bin/python si_ai_scanner.py --once --dry-run
```

This makes public Binance market-data requests, scans the eligible Futures universe, and prints confirmed signal previews. It does not send trade alerts, save scanner state, read credentials, or place orders.

Review the output for:
- At least 15 eligible Futures contracts before a scan is accepted.
- Volume-qualified, bookTicker-matched, valid-bid/ask, spread-qualified and selected counts.
- 15m, 1h, 4h and 1d closed-candle analysis.
- BUY/SELL only when the scanner's multi-timeframe and risk checks confirm; otherwise WAIT.
- No fabricated symbols when the live universe refresh fails.

The previous Termux diagnosis found 182 volume-qualified contracts; a fresh phone-side bookTicker check is still required to confirm which pass the remaining spread/book filters.

## 5. Test Android notification appearance

First install/enable the Termux:API companion app from the same signing source as the main Termux app (for example, do not mix F-Droid and GitHub APK signatures), then grant Android notification permission to Termux. The offline preflight checks the separate `com.termux.api` package when Android package-manager access is available.

```bash
.venv/bin/python si_ai_scanner.py --test-notifications
```

It sends three clearly labelled TEST ONLY notifications: BUY (green styling), SELL (red styling), and WAIT (neutral). These are not trading signals and do not contact Binance. Check notification permission, title markers, sound/vibration, and whether the phone hardware actually supports notification LED behavior.

## 6. Run a 180-day Futures historical backtest

Start with BTC only:

```bash
.venv/bin/python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

The runner downloads 15m, 1h, 4h, 1d last-trade OHLCV, timestamped funding history with its associated settlement mark prices, and 1h mark-price candles. It verifies local datasets and writes JSON reports under `data/reports/`; historical datasets are under `data/historical/`.

Only after BTC completes successfully, optionally test more symbols:

```bash
.venv/bin/python run_public_futures_backtest.py --days 180 --symbol BTC/USDT --symbol ETH/USDT --symbol SOL/USDT
```

Reports are per-symbol with separate reference equity; they are not a shared-wallet portfolio simulation. The profitability gate is expected to remain INCONCLUSIVE until historical liquidation event simulation and timestamp-matched maintenance-tier snapshots are implemented and validated.

## 7. Install Termux:Widget shortcuts (optional)

```bash
bash termux-widget/install-shortcuts.sh
```

The Widget scripts search for `~/SI-AI_FINAL_VALIDATION` first and use its `.venv` when present; otherwise they fall back to the existing `~/SI-AI_FINAL` or `~/SI-AI_FUTURES` project. Refresh Termux:Widget. Use **SI-AI Check** first, then **SI-AI Dry Run**. Start launches the 120-second scanner after offline preflight; Stop requests a graceful stop.

## 8. Continuous signal monitoring (only after reviewing all test results)

```bash
.venv/bin/python si_ai_scanner.py --interval 120
```

Stop with Ctrl+C or the SI-AI Stop Widget. Review every signal and verify live contract filters, quantity precision, current mark price, margin mode and liquidation display yourself before any manual decision. SI-AI never executes trades.

## 9. What to send back for final device sign-off

Share the complete output of:
1. `.venv/bin/python -m pytest -q`
2. `.venv/bin/python termux_preflight.py`
3. `.venv/bin/python si_ai_scanner.py --once --dry-run`
4. `.venv/bin/python si_ai_scanner.py --test-notifications`
5. The final JSON summary and profitability-gate status from the 180-day backtest.

Do not share API keys, passwords, account identifiers, or private account screenshots. If Binance returns a network/region error, share only the error text; do not add private credentials to work around it.
